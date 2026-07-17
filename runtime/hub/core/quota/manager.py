# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""
Quota Manager Module for JupyterHub

Manages user quota balances and usage tracking for container time limits.
Uses the shared database module for SQLAlchemy support.
"""

from __future__ import annotations

import re
import threading
from contextlib import suppress
from datetime import datetime, timedelta

from sqlalchemy import inspect, text

from core.database import get_engine, get_session, session_scope
from core.metrics import quota_deducted_total, quota_denied_total
from core.quota.orm import QuotaTransaction, UsageSession, UserQuota

# Re-export models for backwards compatibility
__all__ = [
    "UserQuota",
    "QuotaTransaction",
    "UsageSession",
    "QuotaManager",
    "init_quota_manager",
    "get_quota_manager",
]


class QuotaManager:
    """
    Thread-safe quota management for JupyterHub users.

    Uses the shared database module for database abstraction.
    """

    _instance: QuotaManager | None = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """Ensure singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the QuotaManager."""
        if self._initialized:
            return

        self._op_lock = threading.Lock()
        self._initialized = True
        print("[QUOTA] QuotaManager initialized")
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Ensure expected columns exist on quota tables."""
        try:
            engine = get_engine()
            inspector = inspect(engine)
            columns = {col["name"] for col in inspector.get_columns(UsageSession.__tablename__)}
            added_column = False
            if "accelerator_type" not in columns:
                with engine.begin() as conn:
                    conn.execute(
                        text(f"ALTER TABLE {UsageSession.__tablename__} ADD COLUMN accelerator_type VARCHAR(100)")
                    )
                added_column = True
                print("[QUOTA] Added accelerator_type column to quota_usage_sessions")

            with engine.begin() as conn:
                result = conn.execute(
                    text(
                        f"UPDATE {UsageSession.__tablename__} "
                        "SET accelerator_type = resource_type "
                        "WHERE accelerator_type IS NULL OR accelerator_type = ''"
                    )
                )
                if added_column or (getattr(result, "rowcount", 0) or 0) > 0:
                    print("[QUOTA] Backfilled accelerator_type on quota_usage_sessions")
        except Exception as exc:
            print(f"[QUOTA] Warning: failed to ensure accelerator_type column: {exc}")

    def get_balance(self, username: str) -> int:
        """Get user's current quota balance."""
        username = username.lower()
        session = get_session()
        try:
            user = session.query(UserQuota).filter(UserQuota.username == username).first()
            return user.balance if user else 0
        finally:
            session.close()

    def can_start_container(
        self,
        username: str,
        accelerator_type: str,
        runtime_minutes: int,
        quota_rates: dict[str, int],
        default_quota: int = 0,
    ) -> tuple[bool, str, int]:
        """
        Check if user can start a container based on quota.

        Args:
            username: The user's username
            accelerator_type: The accelerator type (e.g., 'phx', 'strix', 'cpu')
            runtime_minutes: Requested runtime in minutes
            quota_rates: Mapping of accelerator type to quota rate per minute
            default_quota: Default quota to grant if user has no record

        Returns:
            Tuple of (can_start, message, estimated_cost)
        """
        username = username.lower()

        # Ensure user has quota record
        balance = self.ensure_user_quota(username, default_quota)

        # Check if user has unlimited quota
        if self.is_unlimited(username):
            return (True, "Unlimited quota", 0)

        # Calculate estimated cost
        rate = quota_rates.get(accelerator_type, quota_rates.get("cpu", 1))
        estimated_cost = runtime_minutes * rate

        if balance <= 0:
            with suppress(Exception):
                quota_denied_total.labels(reason="zero_balance").inc()
            return (False, f"Insufficient quota (balance: {balance})", estimated_cost)

        if balance < estimated_cost:
            with suppress(Exception):
                quota_denied_total.labels(reason="insufficient_balance").inc()
            max_runtime = balance // rate if rate > 0 else 0
            return (
                False,
                f"Insufficient quota for {runtime_minutes} min (balance: {balance}, need: {estimated_cost}, max: {max_runtime} min)",
                estimated_cost,
            )

        return (True, f"OK (balance: {balance}, cost: {estimated_cost})", estimated_cost)

    def ensure_user_quota(self, username: str, default_quota: int = 0) -> int:
        """
        Ensure user has a quota record. If user doesn't exist and default_quota > 0,
        grant the default quota amount. Returns the user's current balance.
        """
        username = username.lower()
        with session_scope() as session:
            user = session.query(UserQuota).filter(UserQuota.username == username).first()
            if user:
                return user.balance

            user = UserQuota(username=username, balance=default_quota)
            session.add(user)

            if default_quota > 0:
                transaction = QuotaTransaction(
                    username=username,
                    amount=default_quota,
                    transaction_type="initial_grant",
                    balance_before=0,
                    balance_after=default_quota,
                    description="Default quota for new user",
                )
                session.add(transaction)

            return default_quota

    def is_unlimited(self, username: str) -> bool:
        """Check if user has unlimited quota."""
        username = username.lower()
        session = get_session()
        try:
            user = session.query(UserQuota).filter(UserQuota.username == username).first()
            return user.unlimited if user else False
        finally:
            session.close()

    # Alias for backwards compatibility
    is_unlimited_in_db = is_unlimited

    def set_unlimited(self, username: str, unlimited: bool = True, admin: str | None = None) -> None:
        """Set unlimited quota flag for user."""
        username = username.lower()
        with session_scope() as session:
            user = session.query(UserQuota).filter(UserQuota.username == username).first()
            if not user:
                user = UserQuota(username=username, balance=0, unlimited=unlimited)
                session.add(user)
            else:
                user.unlimited = unlimited

            transaction = QuotaTransaction(
                username=username,
                amount=0,
                transaction_type="set_unlimited" if unlimited else "unset_unlimited",
                balance_before=user.balance,
                balance_after=user.balance,
                description=f"Unlimited {'enabled' if unlimited else 'disabled'}",
                created_by=admin,
            )
            session.add(transaction)

    def add_quota(self, username: str, amount: int, description: str = "", admin: str | None = None) -> int:
        """Add quota to user's balance."""
        username = username.lower()
        with self._op_lock, session_scope() as session:
            user = session.query(UserQuota).filter(UserQuota.username == username).first()
            if not user:
                user = UserQuota(username=username, balance=0)
                session.add(user)
                session.flush()

            balance_before = user.balance
            user.balance = balance_before + amount
            balance_after = user.balance

            transaction = QuotaTransaction(
                username=username,
                amount=amount,
                transaction_type="add" if amount >= 0 else "deduct",
                balance_before=balance_before,
                balance_after=balance_after,
                description=description or f"{'Added' if amount >= 0 else 'Deducted'} {abs(amount)} quota",
                created_by=admin,
            )
            session.add(transaction)

            return balance_after

    def set_balance(self, username: str, new_balance: int, admin: str | None = None) -> int:
        """Set user's quota balance to a specific value."""
        username = username.lower()
        with self._op_lock, session_scope() as session:
            user = session.query(UserQuota).filter(UserQuota.username == username).first()
            if not user:
                user = UserQuota(username=username, balance=new_balance)
                session.add(user)
                balance_before = 0
            else:
                balance_before = user.balance
                user.balance = new_balance

            transaction = QuotaTransaction(
                username=username,
                amount=new_balance - balance_before,
                transaction_type="set",
                balance_before=balance_before,
                balance_after=new_balance,
                description=f"Balance set to {new_balance}",
                created_by=admin,
            )
            session.add(transaction)

            return new_balance

    def deduct_quota(self, username: str, amount: int, resource_type: str = "") -> int:
        """Deduct quota from user's balance."""
        username = username.lower()
        with self._op_lock, session_scope() as session:
            user = session.query(UserQuota).filter(UserQuota.username == username).first()
            if not user:
                return 0

            if user.unlimited:
                return user.balance

            balance_before = user.balance
            user.balance = max(0, balance_before - amount)
            balance_after = user.balance

            transaction = QuotaTransaction(
                username=username,
                amount=-amount,
                transaction_type="usage",
                resource_type=resource_type,
                balance_before=balance_before,
                balance_after=balance_after,
                description=f"Usage: {resource_type}" if resource_type else "Usage deduction",
            )
            session.add(transaction)

            return balance_after

    def start_session(self, username: str, resource_type: str, accelerator_type: str | None = None) -> int:
        """Start a usage session and return session ID."""
        username = username.lower()
        with session_scope() as session:
            usage_session = UsageSession(
                username=username,
                resource_type=resource_type,
                accelerator_type=accelerator_type,
                start_time=datetime.now(),
                status="active",
            )
            session.add(usage_session)
            session.flush()
            return usage_session.id

    # Alias for backwards compatibility
    start_usage_session = start_session

    def end_session(self, session_id: int, quota_consumed: int = 0) -> dict | None:
        """End a usage session."""
        with session_scope() as session:
            usage_session = session.query(UsageSession).filter(UsageSession.id == session_id).first()
            if not usage_session or usage_session.status != "active":
                return None

            end_time = datetime.now()
            duration = (end_time - usage_session.start_time).total_seconds() / 60

            usage_session.end_time = end_time
            usage_session.duration_minutes = int(duration)
            usage_session.quota_consumed = quota_consumed
            usage_session.status = "completed"

            return {
                "session_id": usage_session.id,
                "username": usage_session.username,
                "resource_type": usage_session.resource_type,
                "accelerator_type": usage_session.accelerator_type,
                "duration_minutes": int(duration),
                "quota_consumed": quota_consumed,
            }

    def end_usage_session(self, session_id: int, quota_rates: dict[str, int] | None = None) -> tuple[int, int]:
        """
        End a usage session and optionally deduct quota.

        Always records session duration. Quota deduction only happens when
        quota_rates is provided (quota system is enabled).

        Args:
            session_id: The session ID to end
            quota_rates: Mapping of resource_type to quota rate per minute.
                         Pass None to skip quota deduction (usage tracking only).

        Returns:
            Tuple of (duration_minutes, quota_consumed)
        """
        with session_scope() as session:
            usage_session = session.query(UsageSession).filter(UsageSession.id == session_id).first()
            if not usage_session or usage_session.status != "active":
                return (0, 0)

            end_time = datetime.now()
            duration_minutes = int((end_time - usage_session.start_time).total_seconds() / 60)

            usage_session.end_time = end_time
            usage_session.duration_minutes = duration_minutes
            usage_session.status = "completed"

            quota_consumed = 0
            if quota_rates is not None:
                # Calculate and deduct quota
                accelerator_key = usage_session.accelerator_type or usage_session.resource_type
                rate = quota_rates.get(accelerator_key, quota_rates.get("cpu", 1))
                quota_consumed = duration_minutes * rate
                usage_session.quota_consumed = quota_consumed

                if quota_consumed > 0:
                    with suppress(Exception):
                        quota_deducted_total.inc()

                    user = session.query(UserQuota).filter(UserQuota.username == usage_session.username).first()
                    if user and not user.unlimited:
                        balance_before = user.balance
                        user.balance = max(0, balance_before - quota_consumed)

                        transaction = QuotaTransaction(
                            username=usage_session.username,
                            amount=-quota_consumed,
                            transaction_type="usage",
                            resource_type=usage_session.resource_type,
                            balance_before=balance_before,
                            balance_after=user.balance,
                            description=(
                                f"Session {session_id}: {duration_minutes} min @ {accelerator_key} ({rate}/min)"
                            ),
                        )
                        session.add(transaction)

            return (duration_minutes, quota_consumed)

    def get_active_session(self, username: str) -> dict | None:
        """Get user's active session if any."""
        username = username.lower()
        session = get_session()
        try:
            usage_session = (
                session.query(UsageSession)
                .filter(UsageSession.username == username, UsageSession.status == "active")
                .first()
            )
            if not usage_session:
                return None

            return {
                "session_id": usage_session.id,
                "username": usage_session.username,
                "resource_type": usage_session.resource_type,
                "accelerator_type": usage_session.accelerator_type,
                "start_time": usage_session.start_time.isoformat(),
            }
        finally:
            session.close()

    def cleanup_stale_sessions(self, max_duration_minutes: int = 480) -> list[dict]:
        """Clean up stale sessions older than max duration."""
        cutoff_time = datetime.now() - timedelta(minutes=max_duration_minutes)
        cleaned = []

        with self._op_lock, session_scope() as session:
            stale_sessions = (
                session.query(UsageSession)
                .filter(UsageSession.status == "active", UsageSession.start_time < cutoff_time)
                .all()
            )

            for usage_session in stale_sessions:
                duration = (cutoff_time - usage_session.start_time).total_seconds() / 60
                if duration < max_duration_minutes:
                    continue

                duration_minutes = min(int(duration), max_duration_minutes)

                usage_session.end_time = cutoff_time
                usage_session.duration_minutes = duration_minutes
                usage_session.status = "cleaned_up"

                cleaned.append(
                    {
                        "session_id": usage_session.id,
                        "username": usage_session.username,
                        "resource_type": usage_session.resource_type,
                        "accelerator_type": usage_session.accelerator_type,
                        "duration_minutes": duration_minutes,
                    }
                )

                print(
                    f"[QUOTA] Cleaned up stale session {usage_session.id} for {usage_session.username}: {duration_minutes} min"
                )

        return cleaned

    def get_active_sessions_count(self) -> int:
        """Get count of currently active sessions."""
        session = get_session()
        try:
            return session.query(UsageSession).filter(UsageSession.status == "active").count()
        finally:
            session.close()

    def get_user_transactions(self, username: str, limit: int = 50) -> list[dict]:
        """Get user's transaction history."""
        username = username.lower()
        session = get_session()
        try:
            transactions = (
                session.query(QuotaTransaction)
                .filter(QuotaTransaction.username == username)
                .order_by(QuotaTransaction.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": t.id,
                    "username": t.username,
                    "amount": t.amount,
                    "transaction_type": t.transaction_type,
                    "resource_type": t.resource_type,
                    "description": t.description,
                    "balance_before": t.balance_before,
                    "balance_after": t.balance_after,
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "created_by": t.created_by,
                }
                for t in transactions
            ]
        finally:
            session.close()

    def get_all_balances(self) -> list[dict]:
        """Get all user balances for admin."""
        session = get_session()
        try:
            users = session.query(UserQuota).order_by(UserQuota.username).all()
            return [
                {
                    "username": u.username,
                    "balance": u.balance,
                    "unlimited": u.unlimited,
                    "updated_at": u.updated_at.isoformat() if u.updated_at else None,
                }
                for u in users
            ]
        finally:
            session.close()

    def batch_set_quota(self, users: list[tuple[str, int]], admin: str | None = None) -> dict:
        """Set quota for multiple users in a single transaction with per-user savepoints."""
        results = {"success": 0, "failed": 0, "details": []}
        with self._op_lock, session_scope() as session:
            for username, amount in users:
                try:
                    with session.begin_nested():
                        uname = username.lower()
                        user = session.query(UserQuota).filter(UserQuota.username == uname).first()
                        if not user:
                            user = UserQuota(username=uname, balance=amount)
                            session.add(user)
                            balance_before = 0
                        else:
                            balance_before = user.balance
                            user.balance = amount

                        transaction = QuotaTransaction(
                            username=uname,
                            amount=amount - balance_before,
                            transaction_type="set",
                            balance_before=balance_before,
                            balance_after=amount,
                            description=f"Balance set to {amount}",
                            created_by=admin,
                        )
                        session.add(transaction)
                    results["success"] += 1
                    results["details"].append({"username": uname, "status": "success", "balance": amount})
                except Exception as e:
                    results["failed"] += 1
                    results["details"].append({"username": username, "status": "failed", "error": str(e)})
                    print(f"Failed to set quota for {username}: {e}")
        return results

    def _match_targets(self, username: str, balance: int, is_unlimited: bool, targets: dict) -> bool:
        """Check if user matches the target criteria."""
        if is_unlimited and not targets.get("includeUnlimited", False):
            return False

        balance_below = targets.get("balanceBelow")
        if balance_below is not None and balance >= balance_below:
            return False

        balance_above = targets.get("balanceAbove")
        if balance_above is not None and balance <= balance_above:
            return False

        include_users = targets.get("includeUsers", [])
        if include_users and username not in [u.lower() for u in include_users]:
            return False

        exclude_users = targets.get("excludeUsers", [])
        if username in [u.lower() for u in exclude_users]:
            return False

        pattern = targets.get("usernamePattern")
        if pattern:
            try:
                if not re.match(pattern, username, re.IGNORECASE):
                    return False
            except re.error:
                return False

        return True

    def batch_refresh_quota(
        self,
        amount: int,
        action: str = "add",
        max_balance: int | None = None,
        min_balance: int | None = None,
        targets: dict | None = None,
        rule_name: str = "manual",
    ) -> dict:
        """Batch refresh quota for users with flexible targeting."""
        if targets is None:
            targets = {}
        if min_balance is None:
            min_balance = 0

        if action not in ("add", "set"):
            return {"error": f"Invalid action: {action}", "rule_name": rule_name}

        with self._op_lock, session_scope() as session:
            users = session.query(UserQuota).all()

            users_updated = 0
            total_change = 0
            skipped = 0

            for user in users:
                username = user.username
                current = user.balance
                is_unlimited = user.unlimited

                if not self._match_targets(username, current, is_unlimited, targets):
                    skipped += 1
                    continue

                if action == "add":
                    new_balance = current + amount
                    if amount > 0 and max_balance is not None:
                        new_balance = min(new_balance, max_balance)
                    elif amount < 0:
                        new_balance = max(new_balance, min_balance)
                elif action == "set":
                    new_balance = amount
                else:
                    skipped += 1
                    continue

                if new_balance == current:
                    skipped += 1
                    continue

                change = new_balance - current
                user.balance = new_balance

                transaction = QuotaTransaction(
                    username=username,
                    amount=change,
                    transaction_type="auto_refresh",
                    balance_before=current,
                    balance_after=new_balance,
                    description=f"Auto {action}: {rule_name}",
                )
                session.add(transaction)

                users_updated += 1
                total_change += change

            print(
                f"[QUOTA] Refresh '{rule_name}' ({action}): {users_updated} users updated, {skipped} skipped, change={total_change:+d}"
            )
            return {
                "users_updated": users_updated,
                "total_change": total_change,
                "skipped": skipped,
                "action": action,
                "rule_name": rule_name,
            }


# =============================================================================
# Global Instance
# =============================================================================

_quota_manager: QuotaManager | None = None
_init_lock = threading.Lock()


def init_quota_manager() -> QuotaManager:
    """
    Initialize the global QuotaManager instance.

    Should be called once during JupyterHub startup after database is initialized.
    """
    global _quota_manager
    with _init_lock:
        if _quota_manager is None:
            _quota_manager = QuotaManager()
        return _quota_manager


def get_quota_manager() -> QuotaManager:
    """
    Get the global QuotaManager instance.

    Raises RuntimeError if not initialized.
    """
    if _quota_manager is None:
        raise RuntimeError("QuotaManager not initialized. Call init_quota_manager() first.")
    return _quota_manager
