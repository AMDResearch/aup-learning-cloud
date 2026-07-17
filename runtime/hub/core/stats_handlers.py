# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

import json
from datetime import datetime, timedelta
from functools import lru_cache

from jupyterhub.apihandlers import APIHandler
from tornado import web

from core.config import HubConfig
from core.database import session_scope
from core.quota.orm import UsageSession


@lru_cache(maxsize=1)
def _resource_label_data() -> tuple[dict[str, str], dict[str, str], dict[str, set[str]]]:
    """Return cached mappings for resource and accelerator labels."""
    config = HubConfig.get()
    resource_labels: dict[str, str] = {}
    accelerator_labels: dict[str, str] = {}
    accelerator_to_resources: dict[str, set[str]] = {}

    for key, meta in config.resources.metadata.items():
        label = meta.description or key
        resource_labels[key] = label

        accel_keys = set(meta.acceleratorKeys or [])
        if meta.accelerator:
            accel_keys.add(meta.accelerator)
        for acc_key in accel_keys:
            accelerator_to_resources.setdefault(acc_key, set()).add(key)

    for key, accel in config.accelerators.items():
        accelerator_labels[key] = accel.displayName or key

    # Always ensure CPU fallback label
    accelerator_labels.setdefault("cpu", "CPU")

    return (resource_labels, accelerator_labels, accelerator_to_resources)


def _resource_display(resource_type: str) -> str:
    """Resolve a human-friendly label for a given resource or accelerator key."""
    resource_labels, accelerator_labels, accelerator_to_resources = _resource_label_data()

    if resource_type in resource_labels:
        return resource_labels[resource_type]

    candidate_resources = accelerator_to_resources.get(resource_type, set())
    if len(candidate_resources) == 1:
        candidate = next(iter(candidate_resources))
        return resource_labels.get(candidate, candidate)

    if resource_type in accelerator_labels:
        return accelerator_labels[resource_type]

    return resource_type


def _accelerator_display(accelerator_key: str | None) -> str | None:
    """Return a human-friendly accelerator label if available."""
    if not accelerator_key:
        return None

    _, accelerator_labels, _ = _resource_label_data()
    return accelerator_labels.get(accelerator_key, accelerator_key)


def _require_admin(handler):
    if not handler.current_user.admin:
        handler.set_status(403)
        handler.set_header("Content-Type", "application/json")
        handler.finish(json.dumps({"error": "Admin access required"}))
        return False
    return True


class StatsOverviewHandler(APIHandler):
    """Summary stats for the dashboard overview cards."""

    @web.authenticated
    async def get(self):
        assert self.current_user is not None
        if not _require_admin(self):
            return

        loop = __import__("asyncio").get_event_loop()
        result = await loop.run_in_executor(None, self._query)
        self.set_header("Content-Type", "application/json")
        self.finish(json.dumps(result))

    def _query(self):
        from jupyterhub.orm import User

        week_ago = datetime.now() - timedelta(days=7)

        total_users = self.db.query(User).count()
        users_this_week = self.db.query(User).filter(User.last_activity >= week_ago).count()

        with session_scope() as session:
            active_sessions = session.query(UsageSession).filter(UsageSession.status == "active").count()
            total_minutes_row = session.execute(
                __import__("sqlalchemy").text(
                    "SELECT COALESCE(SUM(duration_minutes), 0) FROM quota_usage_sessions "
                    "WHERE status IN ('completed', 'cleaned_up') AND duration_minutes IS NOT NULL"
                )
            ).scalar()

        return {
            "total_users": total_users,
            "active_sessions": active_sessions,
            "total_usage_minutes": int(total_minutes_row or 0),
            "users_this_week": users_this_week,
        }


class StatsUsageHandler(APIHandler):
    """Usage time series for the trend line chart, supporting day/week granularity."""

    @web.authenticated
    async def get(self):
        assert self.current_user is not None
        if not _require_admin(self):
            return

        try:
            days = int(self.get_argument("days", "30"))
            days = max(1, min(days, 365))
        except ValueError:
            days = 30

        granularity = self.get_argument("granularity", "day")
        if granularity not in ("day", "week"):
            granularity = "day"

        loop = __import__("asyncio").get_event_loop()
        result = await loop.run_in_executor(None, self._query, days, granularity)
        self.set_header("Content-Type", "application/json")
        self.finish(json.dumps(result))

    def _query(self, days: int, granularity: str):
        import sqlalchemy as sa

        now = datetime.now()
        since = now - timedelta(days=days)

        if granularity == "week":
            group_expr = "strftime('%Y-W%W', start_time)"
        else:
            group_expr = "DATE(start_time)"

        with session_scope() as session:
            rows = session.execute(
                sa.text(
                    f"SELECT {group_expr} as period, "
                    "COALESCE(SUM(duration_minutes), 0) as minutes, "
                    "COUNT(*) as sessions, "
                    "COUNT(DISTINCT username) as users "
                    "FROM quota_usage_sessions "
                    "WHERE status IN ('completed', 'cleaned_up') "
                    "AND start_time >= :since "
                    f"GROUP BY {group_expr} "
                    "ORDER BY period ASC"
                ),
                {"since": since},
            ).fetchall()

        by_period = {str(r[0]): (int(r[1]), int(r[2]), int(r[3])) for r in rows}

        result = []
        if granularity == "day":
            d = since.date()
            today = now.date()
            while d <= today:
                key = str(d)
                mins, sess, users = by_period.get(key, (0, 0, 0))
                result.append({"date": key, "minutes": mins, "sessions": sess, "users": users})
                d += timedelta(days=1)
        else:
            # Iterate week by week from the Monday of the starting week

            d = since.date()
            d -= timedelta(days=d.weekday())  # rewind to Monday
            today = now.date()
            while d <= today:
                key = d.strftime("%Y-W%W")
                mins, sess, users = by_period.get(key, (0, 0, 0))
                result.append({"date": key, "minutes": mins, "sessions": sess, "users": users})
                d += timedelta(weeks=1)

        return {"daily_usage": result}


class StatsDistributionHandler(APIHandler):
    """Resource distribution and top users for pie chart and leaderboard."""

    @web.authenticated
    async def get(self):
        assert self.current_user is not None
        if not _require_admin(self):
            return

        try:
            days = int(self.get_argument("days", "30"))
            days = max(1, min(days, 365))
        except ValueError:
            days = 30

        loop = __import__("asyncio").get_event_loop()
        result = await loop.run_in_executor(None, self._query, days)
        self.set_header("Content-Type", "application/json")
        self.finish(json.dumps(result))

    def _query(self, days: int):
        import sqlalchemy as sa

        since = datetime.now() - timedelta(days=days)

        with session_scope() as session:
            resource_rows = session.execute(
                sa.text(
                    "SELECT resource_type, "
                    "COALESCE(SUM(duration_minutes), 0) as minutes, "
                    "COUNT(*) as sessions, "
                    "COUNT(DISTINCT username) as users, "
                    "COALESCE(AVG(duration_minutes), 0) as avg_minutes "
                    "FROM quota_usage_sessions "
                    "WHERE status IN ('completed', 'cleaned_up') "
                    "AND start_time >= :since "
                    "GROUP BY resource_type "
                    "ORDER BY minutes DESC"
                ),
                {"since": since},
            ).fetchall()

            top_user_rows = session.execute(
                sa.text(
                    "SELECT username, "
                    "COALESCE(SUM(duration_minutes), 0) as total_minutes, "
                    "COUNT(*) as sessions "
                    "FROM quota_usage_sessions "
                    "WHERE status IN ('completed', 'cleaned_up') "
                    "AND start_time >= :since "
                    "GROUP BY username "
                    "ORDER BY total_minutes DESC "
                    "LIMIT 10"
                ),
                {"since": since},
            ).fetchall()

        return {
            "by_resource": [
                {
                    "resource_type": row[0],
                    "resource_display": _resource_display(row[0]),
                    "minutes": int(row[1]),
                    "sessions": int(row[2]),
                    "users": int(row[3]),
                    "avg_minutes": round(float(row[4]), 1),
                }
                for row in resource_rows
            ],
            "top_users": [
                {
                    "username": row[0],
                    "total_minutes": int(row[1]),
                    "sessions": int(row[2]),
                }
                for row in top_user_rows
            ],
        }


class StatsUserHandler(APIHandler):
    """Per-user usage detail: time series + resource breakdown + recent sessions."""

    @web.authenticated
    async def get(self, username: str):
        assert self.current_user is not None
        if not _require_admin(self):
            return

        try:
            days = int(self.get_argument("days", "30"))
            days = max(1, min(days, 365))
        except ValueError:
            days = 30

        granularity = self.get_argument("granularity", "day")
        if granularity not in ("day", "week"):
            granularity = "day"

        loop = __import__("asyncio").get_event_loop()
        result = await loop.run_in_executor(None, self._query, username, days, granularity)
        self.set_header("Content-Type", "application/json")
        self.finish(json.dumps(result))

    def _query(self, username: str, days: int, granularity: str):
        import sqlalchemy as sa

        since = datetime.now() - timedelta(days=days)

        if granularity == "week":
            group_expr = "strftime('%Y-W%W', start_time)"
        else:
            group_expr = "DATE(start_time)"

        with session_scope() as session:
            # Time series for this user
            usage_rows = session.execute(
                sa.text(
                    f"SELECT {group_expr} as period, "
                    "COALESCE(SUM(duration_minutes), 0) as minutes, "
                    "COUNT(*) as sessions "
                    "FROM quota_usage_sessions "
                    "WHERE username = :username "
                    "AND status IN ('completed', 'cleaned_up') "
                    "AND start_time >= :since "
                    f"GROUP BY {group_expr} "
                    "ORDER BY period ASC"
                ),
                {"username": username, "since": since},
            ).fetchall()

            # Resource breakdown for this user
            resource_rows = session.execute(
                sa.text(
                    "SELECT resource_type, "
                    "COALESCE(SUM(duration_minutes), 0) as minutes, "
                    "COUNT(*) as sessions "
                    "FROM quota_usage_sessions "
                    "WHERE username = :username "
                    "AND status IN ('completed', 'cleaned_up') "
                    "AND start_time >= :since "
                    "GROUP BY resource_type "
                    "ORDER BY minutes DESC"
                ),
                {"username": username, "since": since},
            ).fetchall()

            # Recent sessions (last 20)
            session_rows = session.execute(
                sa.text(
                    "SELECT resource_type, accelerator_type, start_time, end_time, duration_minutes, status "
                    "FROM quota_usage_sessions "
                    "WHERE username = :username "
                    "AND start_time >= :since "
                    "ORDER BY start_time DESC "
                    "LIMIT 20"
                ),
                {"username": username, "since": since},
            ).fetchall()

            # Totals
            totals_row = session.execute(
                sa.text(
                    "SELECT COALESCE(SUM(duration_minutes), 0), COUNT(*) "
                    "FROM quota_usage_sessions "
                    "WHERE username = :username "
                    "AND status IN ('completed', 'cleaned_up') "
                    "AND start_time >= :since"
                ),
                {"username": username, "since": since},
            ).fetchone()

        return {
            "username": username,
            "total_minutes": int(totals_row[0] or 0),
            "total_sessions": int(totals_row[1] or 0),
            "usage": [{"date": str(r[0]), "minutes": int(r[1]), "sessions": int(r[2])} for r in usage_rows],
            "by_resource": [
                {
                    "resource_type": r[0],
                    "resource_display": _resource_display(r[0]),
                    "minutes": int(r[1]),
                    "sessions": int(r[2]),
                }
                for r in resource_rows
            ],
            "recent_sessions": [
                {
                    "resource_type": r[0],
                    "resource_display": _resource_display(r[0]),
                    "accelerator_type": r[1],
                    "accelerator_display": _accelerator_display(r[1]),
                    "start_time": str(r[2]),
                    "end_time": str(r[3]) if r[3] else None,
                    "duration_minutes": int(r[4]) if r[4] is not None else None,
                    "status": r[5],
                }
                for r in session_rows
            ],
        }


class StatsMyUsageHandler(APIHandler):
    """Current user's own usage stats (no admin required)."""

    @web.authenticated
    async def get(self):
        assert self.current_user is not None
        username = self.current_user.name

        try:
            days = int(self.get_argument("days", "30"))
            days = max(1, min(days, 365))
        except ValueError:
            days = 30

        granularity = self.get_argument("granularity", "day")
        if granularity not in ("day", "week"):
            granularity = "day"

        loop = __import__("asyncio").get_event_loop()
        result = await loop.run_in_executor(
            None,
            StatsUserHandler._query,
            None,
            username,
            days,
            granularity,
        )
        self.set_header("Content-Type", "application/json")
        self.finish(json.dumps(result))


class StatsHourlyHandler(APIHandler):
    """Usage distribution by hour of day."""

    @web.authenticated
    async def get(self):
        assert self.current_user is not None
        if not _require_admin(self):
            return

        try:
            days = int(self.get_argument("days", "30"))
            days = max(1, min(days, 365))
        except ValueError:
            days = 30

        try:
            # tz_offset: minutes ahead of UTC (e.g. UTC+8 → 480, UTC-5 → -300)
            tz_offset = int(self.get_argument("tz_offset", "0"))
            tz_offset = max(-720, min(840, tz_offset))
        except ValueError:
            tz_offset = 0

        start_date = self.get_argument("start_date", None)
        end_date = self.get_argument("end_date", None)

        loop = __import__("asyncio").get_event_loop()
        result = await loop.run_in_executor(None, self._query, days, tz_offset, start_date, end_date)
        self.set_header("Content-Type", "application/json")
        self.finish(json.dumps(result))

    @staticmethod
    def _date_bounds(days: int, tz_offset: int, start_date: str | None, end_date: str | None):
        if start_date and end_date:
            try:
                start = datetime.strptime(start_date, "%Y-%m-%d") - timedelta(minutes=tz_offset)
                end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1) - timedelta(minutes=tz_offset)
                if start < end:
                    return start, end
            except ValueError:
                pass

        return datetime.now() - timedelta(days=days), None

    def _query(self, days: int, tz_offset: int, start_date: str | None = None, end_date: str | None = None):
        import sqlalchemy as sa

        since, until = self._date_bounds(days, tz_offset, start_date, end_date)
        offset_sign = "+" if tz_offset >= 0 else "-"
        offset_abs = abs(tz_offset)
        offset_expr = f"datetime(start_time, '{offset_sign}{offset_abs} minutes')"
        end_clause = "AND start_time < :until " if until is not None else ""
        params = {"since": since}
        if until is not None:
            params["until"] = until

        with session_scope() as session:
            rows = session.execute(
                sa.text(
                    f"SELECT CAST(strftime('%H', {offset_expr}) AS INTEGER) as hour, "
                    "COUNT(*) as sessions, "
                    "COALESCE(SUM(duration_minutes), 0) as minutes "
                    "FROM quota_usage_sessions "
                    "WHERE status IN ('completed', 'cleaned_up') "
                    "AND start_time >= :since "
                    f"{end_clause}"
                    "GROUP BY hour ORDER BY hour ASC"
                ),
                params,
            ).fetchall()

        by_hour = {int(r[0]): {"sessions": int(r[1]), "minutes": int(r[2])} for r in rows}
        return {
            "hourly": [
                {
                    "hour": h,
                    "sessions": by_hour.get(h, {}).get("sessions", 0),
                    "minutes": by_hour.get(h, {}).get("minutes", 0),
                }
                for h in range(24)
            ]
        }


IDLE_WARN_MINUTES = 120  # sessions longer than this are flagged as potentially idle


def _active_sessions_data() -> dict:
    import sqlalchemy as sa

    cutoff = datetime.now() - timedelta(minutes=30)

    with session_scope() as session:
        active_rows = session.execute(
            sa.text(
                "SELECT q.username, q.resource_type, q.accelerator_type, q.start_time "
                "FROM quota_usage_sessions q "
                "JOIN spawners s ON s.server_id IS NOT NULL "
                "JOIN users u ON u.id = s.user_id AND LOWER(u.name) = LOWER(q.username) "
                "WHERE q.status = 'active' "
                "ORDER BY q.start_time ASC"
            )
        ).fetchall()

        pending_rows = session.execute(
            sa.text(
                "SELECT u.name, s.started "
                "FROM spawners s "
                "JOIN users u ON u.id = s.user_id "
                "WHERE s.server_id IS NULL AND s.started IS NOT NULL AND s.started > :cutoff "
                "ORDER BY s.started ASC"
            ),
            {"cutoff": cutoff},
        ).fetchall()

    now = datetime.now()
    return {
        "active_sessions": [
            {
                "username": r[0],
                "resource_type": r[1],
                "resource_display": _resource_display(r[1]),
                "accelerator_type": r[2],
                "accelerator_display": _accelerator_display(r[2]),
                "start_time": str(r[3]),
                "elapsed_minutes": int((now - datetime.fromisoformat(str(r[3]))).total_seconds() / 60),
                "idle_warning": int((now - datetime.fromisoformat(str(r[3]))).total_seconds() / 60)
                >= IDLE_WARN_MINUTES,
            }
            for r in active_rows
        ],
        "pending_spawns": [
            {
                "username": r[0],
                "started": str(r[1]),
                "waiting_minutes": int((now - datetime.fromisoformat(str(r[1]))).total_seconds() / 60),
            }
            for r in pending_rows
        ],
    }


class StatsActiveSSEHandler(APIHandler):
    """SSE stream of currently active sessions, pushed every 5 seconds."""

    def check_xsrf_cookie(self):
        # EventSource cannot send custom headers, so XSRF is skipped for this read-only GET
        pass

    @web.authenticated
    async def get(self):
        import asyncio

        assert self.current_user is not None
        if not _require_admin(self):
            return

        self.set_header("Content-Type", "text/event-stream")
        self.set_header("Cache-Control", "no-cache")
        self.set_header("X-Accel-Buffering", "no")
        self.set_header("Connection", "keep-alive")

        loop = asyncio.get_event_loop()
        try:
            while True:
                data = await loop.run_in_executor(None, _active_sessions_data)
                self.write(f"data: {json.dumps(data)}\n\n")
                await self.flush()
                await asyncio.sleep(5)
        except Exception:
            pass
