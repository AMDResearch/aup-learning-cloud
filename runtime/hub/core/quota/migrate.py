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
Quota Database Migration Script

Migrates data from the old standalone quota.sqlite database to the new
shared JupyterHub database with prefixed table names.

Old structure (quota.sqlite):
- user_quota
- quota_transactions
- usage_sessions

New structure (jupyterhub.sqlite or PostgreSQL/MySQL):
- quota_user_quota
- quota_transactions
- quota_usage_sessions
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.database import Base
from core.quota.orm import QuotaTransaction, UsageSession, UserQuota

OLD_DB_PATH = "/srv/jupyterhub/quota.sqlite"
MIGRATION_MARKER = "/srv/jupyterhub/.quota_migrated"


def _row_get(row, key, default=None):
    """Safely get a value from sqlite3.Row, returning default if key doesn't exist."""
    try:
        value = row[key]
        return value if value is not None else default
    except (KeyError, IndexError):
        return default


def check_migration_needed() -> bool:
    """Check if migration is needed."""
    # Skip if already migrated
    if os.path.exists(MIGRATION_MARKER):
        return False

    # Skip if old database doesn't exist
    return os.path.exists(OLD_DB_PATH)


def migrate_quota_data(target_db_url: str) -> dict:
    """
    Migrate quota data from old SQLite database to new database.

    Args:
        target_db_url: SQLAlchemy URL for the target database

    Returns:
        Migration statistics
    """
    if not check_migration_needed():
        return {"status": "skipped", "reason": "Migration not needed"}

    print(f"[QUOTA MIGRATION] Starting migration from {OLD_DB_PATH}")

    stats = {
        "users_migrated": 0,
        "transactions_migrated": 0,
        "sessions_migrated": 0,
        "errors": [],
    }

    try:
        # Connect to old SQLite database
        old_conn = sqlite3.connect(OLD_DB_PATH)
        old_conn.row_factory = sqlite3.Row
        old_cursor = old_conn.cursor()

        # Connect to new database
        engine = create_engine(target_db_url)
        Base.metadata.create_all(engine)
        SessionFactory = sessionmaker(bind=engine)
        session = SessionFactory()

        # Migrate user_quota -> quota_user_quota
        print("[QUOTA MIGRATION] Migrating user quotas...")
        old_cursor.execute("SELECT * FROM user_quota")
        for row in old_cursor.fetchall():
            try:
                # Check if user already exists in new table
                existing = session.query(UserQuota).filter(UserQuota.username == row["username"]).first()

                if existing:
                    # Update existing record if old has higher balance
                    if row["balance"] > existing.balance:
                        existing.balance = row["balance"]
                    if _row_get(row, "unlimited"):
                        existing.unlimited = True
                else:
                    user = UserQuota(
                        username=row["username"],
                        balance=row["balance"],
                        unlimited=bool(_row_get(row, "unlimited", 0)),
                        created_at=_parse_datetime(_row_get(row, "created_at")),
                        updated_at=_parse_datetime(_row_get(row, "updated_at")),
                    )
                    session.add(user)

                stats["users_migrated"] += 1
            except Exception as e:
                stats["errors"].append(f"User {row['username']}: {e}")

        session.commit()
        print(f"[QUOTA MIGRATION] Migrated {stats['users_migrated']} users")

        # Migrate quota_transactions
        print("[QUOTA MIGRATION] Migrating transactions...")
        old_cursor.execute("SELECT * FROM quota_transactions")
        for row in old_cursor.fetchall():
            try:
                transaction = QuotaTransaction(
                    username=row["username"],
                    amount=row["amount"],
                    transaction_type=row["transaction_type"],
                    resource_type=_row_get(row, "resource_type"),
                    description=_row_get(row, "description"),
                    balance_before=row["balance_before"],
                    balance_after=row["balance_after"],
                    created_at=_parse_datetime(_row_get(row, "created_at")),
                    created_by=_row_get(row, "created_by"),
                )
                session.add(transaction)
                stats["transactions_migrated"] += 1
            except Exception as e:
                stats["errors"].append(f"Transaction {row['id']}: {e}")

        session.commit()
        print(f"[QUOTA MIGRATION] Migrated {stats['transactions_migrated']} transactions")

        # Migrate usage_sessions -> quota_usage_sessions
        print("[QUOTA MIGRATION] Migrating usage sessions...")
        old_cursor.execute("SELECT * FROM usage_sessions")
        for row in old_cursor.fetchall():
            try:
                usage_session = UsageSession(
                    username=row["username"],
                    resource_type=row["resource_type"],
                    accelerator_type=row["resource_type"],
                    start_time=_parse_datetime(row["start_time"]) or datetime.now(),
                    end_time=_parse_datetime(_row_get(row, "end_time")),
                    duration_minutes=_row_get(row, "duration_minutes"),
                    quota_consumed=_row_get(row, "quota_consumed"),
                    status=_row_get(row, "status", "completed"),
                    created_at=_parse_datetime(_row_get(row, "created_at")),
                )
                session.add(usage_session)
                stats["sessions_migrated"] += 1
            except Exception as e:
                stats["errors"].append(f"Session {row['id']}: {e}")

        session.commit()
        print(f"[QUOTA MIGRATION] Migrated {stats['sessions_migrated']} sessions")

        # Close connections
        session.close()
        old_conn.close()

        # Mark migration as complete
        _mark_migration_complete()

        # Rename old database to backup
        backup_path = OLD_DB_PATH + ".migrated"
        os.rename(OLD_DB_PATH, backup_path)
        print(f"[QUOTA MIGRATION] Old database backed up to {backup_path}")

        stats["status"] = "success"
        print(f"[QUOTA MIGRATION] Migration complete: {stats}")

    except Exception as e:
        stats["status"] = "error"
        stats["errors"].append(str(e))
        print(f"[QUOTA MIGRATION] Migration failed: {e}")

    return stats


def _parse_datetime(value) -> datetime | None:
    """Parse datetime from various formats."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            try:
                return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return None
    return None


def _mark_migration_complete():
    """Create a marker file to indicate migration is complete."""
    Path(MIGRATION_MARKER).touch()


if __name__ == "__main__":
    # CLI usage for manual migration
    import sys

    if len(sys.argv) < 2:
        print("Usage: python migrate.py <target_db_url>")
        print("Example: python migrate.py sqlite:////srv/jupyterhub/jupyterhub.sqlite")
        sys.exit(1)

    target_url = sys.argv[1]
    result = migrate_quota_data(target_url)
    print(f"Result: {result}")
