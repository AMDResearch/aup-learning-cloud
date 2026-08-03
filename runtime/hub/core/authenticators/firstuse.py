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
First Use Authenticator

Password-based authenticator with forced password change support.
Uses SQLAlchemy to store passwords in the shared JupyterHub database.
"""

from __future__ import annotations

import secrets
from concurrent.futures import ThreadPoolExecutor

import bcrypt
from firstuseauthenticator import FirstUseAuthenticator

from core.authenticators.models import UserPassword
from core.database import get_session, session_scope


class CustomFirstUseAuthenticator(FirstUseAuthenticator):
    """
    FirstUseAuthenticator with forced password change support.

    Users set their password on first login, and admins can force
    password changes. Passwords are stored in the JupyterHub database
    using SQLAlchemy.
    """

    prefix = ""
    service_name = "Native"
    login_service = "Native"
    create_users = False

    def normalize_username(self, username):
        """Normalize username to lowercase."""
        if not username:
            return username
        return username.lower()

    def _user_exists(self, username):
        """Check if user exists in JupyterHub database."""
        db = getattr(self, "db", None)
        if db is None:
            db = getattr(getattr(self, "parent", None), "db", None)
        if db is None:
            self.log.warning("Native authentication denied because Hub database is unavailable")
            return False

        from jupyterhub.orm import User

        return bool(db.query(User).filter_by(name=username).first())

    def _get_user_password(self, username: str) -> UserPassword | None:
        """Get user password record from database."""
        session = get_session()
        try:
            return session.query(UserPassword).filter_by(username=username).first()
        finally:
            session.close()

    MIN_PASSWORD_LENGTH = 8
    UPPERCASE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    LOWERCASE_CHARS = "abcdefghijkmnpqrstuvwxyz"
    DIGIT_CHARS = "23456789"
    SPECIAL_CHARS = "!@#$%^&*_+-="

    @staticmethod
    def _check_password_strength(password: str) -> str | None:
        """Return an error message if the password is too weak, or None if OK."""
        import re

        min_len = CustomFirstUseAuthenticator.MIN_PASSWORD_LENGTH
        if not password or len(password) < min_len:
            return f"Password must be at least {min_len} characters"
        if not re.search(r"[A-Z]", password):
            return "Password must contain at least one uppercase letter"
        if not re.search(r"[a-z]", password):
            return "Password must contain at least one lowercase letter"
        if not re.search(r"\d", password):
            return "Password must contain at least one digit"
        if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?`~]", password):
            return "Password must contain at least one special character"
        return None

    @classmethod
    def generate_password(cls, length: int = 16) -> str:
        """Generate a password that satisfies the native password policy."""
        password_length = max(length, cls.MIN_PASSWORD_LENGTH)
        all_chars = cls.UPPERCASE_CHARS + cls.LOWERCASE_CHARS + cls.DIGIT_CHARS + cls.SPECIAL_CHARS
        chars = [
            secrets.choice(cls.UPPERCASE_CHARS),
            secrets.choice(cls.LOWERCASE_CHARS),
            secrets.choice(cls.DIGIT_CHARS),
            secrets.choice(cls.SPECIAL_CHARS),
        ]
        chars.extend(secrets.choice(all_chars) for _ in range(password_length - len(chars)))
        secrets.SystemRandom().shuffle(chars)
        return "".join(chars)

    def _validate_password(self, password):
        """Validate password meets strength requirements."""
        return self._check_password_strength(password) is None

    def set_password(self, username: str, password: str, force_change: bool = True) -> str:
        """Set password for a user."""
        strength_error = self._check_password_strength(password)
        if strength_error:
            return strength_error

        password_hash = bcrypt.hashpw(password.encode("utf8"), bcrypt.gensalt())

        with session_scope() as session:
            user_pw = session.query(UserPassword).filter_by(username=username).first()
            if user_pw:
                user_pw.password_hash = password_hash
                user_pw.force_change = force_change
            else:
                user_pw = UserPassword(
                    username=username,
                    password_hash=password_hash,
                    force_change=force_change,
                )
                session.add(user_pw)

        suffix = " (force change on next login)" if force_change else ""
        return f"Password set for {username}{suffix}"

    def batch_set_passwords(
        self,
        users: list[dict],
        force_change: bool = True,
    ) -> dict:
        """Set passwords for multiple users in a single transaction.

        Args:
            users: List of dicts with 'username' and 'password' keys.
            force_change: Whether to force password change on first login.

        Returns:
            Dict with 'success', 'failed' counts and 'results' list.
        """
        results = {"success": 0, "failed": 0, "results": []}

        valid_entries = []
        for entry in users:
            username = entry["username"]
            password = entry["password"]
            strength_error = self._check_password_strength(password)
            if strength_error:
                results["failed"] += 1
                results["results"].append(
                    {
                        "username": username,
                        "status": "failed",
                        "error": strength_error,
                    }
                )
                continue
            valid_entries.append((username, password))

        # Parallel bcrypt hashing (bcrypt releases GIL, threads give real speedup)
        def _hash(pw: str) -> bytes:
            return bcrypt.hashpw(pw.encode("utf8"), bcrypt.gensalt())

        with ThreadPoolExecutor() as pool:
            hash_results = list(pool.map(_hash, [pw for _, pw in valid_entries]))
        hashed = [(username, h) for (username, _), h in zip(valid_entries, hash_results)]

        # Single DB transaction with per-user savepoints
        with session_scope() as session:
            for username, password_hash in hashed:
                try:
                    with session.begin_nested():
                        user_pw = session.query(UserPassword).filter_by(username=username).first()
                        if user_pw:
                            user_pw.password_hash = password_hash
                            user_pw.force_change = force_change
                        else:
                            user_pw = UserPassword(
                                username=username,
                                password_hash=password_hash,
                                force_change=force_change,
                            )
                            session.add(user_pw)
                    results["success"] += 1
                    results["results"].append({"username": username, "status": "success"})
                except Exception as e:
                    results["failed"] += 1
                    results["results"].append(
                        {
                            "username": username,
                            "status": "failed",
                            "error": str(e),
                        }
                    )

        return results

    def mark_force_password_change(self, username: str, force: bool = True) -> None:
        """Mark or unmark a user for forced password change."""
        with session_scope() as session:
            user_pw = session.query(UserPassword).filter_by(username=username).first()
            if user_pw:
                user_pw.force_change = force

    def needs_password_change(self, username: str) -> bool:
        """Check if user needs to change their password."""
        user_pw = self._get_user_password(username)
        return user_pw.force_change if user_pw else False

    def clear_force_password_change(self, username: str) -> None:
        """Clear the forced password change flag for a user."""
        self.mark_force_password_change(username, force=False)

    def check_password(self, username: str, password: str) -> bool:
        """Verify password for a user."""
        user_pw = self._get_user_password(username)
        if not user_pw:
            return False
        return bcrypt.checkpw(password.encode("utf8"), user_pw.password_hash)

    def user_has_password(self, username: str) -> bool:
        """Check if user already has a password set."""
        return self._get_user_password(username) is not None

    async def authenticate(self, _handler, data):
        """Authenticate user with username and password."""
        username = self.normalize_username(data.get("username", ""))
        password = data.get("password", "")

        if not username or not password:
            return None

        if ":" in username:
            self.log.warning("Rejected username containing ':': %s", username)
            return None

        # Check if user exists in JupyterHub
        if not self._user_exists(username):
            self.log.warning(f"User {username} not found in JupyterHub database")
            return None

        # Check if user has a password set
        if self.user_has_password(username):
            # Verify existing password
            if self.check_password(username, password):
                return username
            self.log.warning(f"Invalid password for user {username}")
            return None
        else:
            # First use: set the password
            if not self._validate_password(password):
                self.log.warning(f"Password too weak for new user {username}")
                return None
            self.set_password(username, password, force_change=False)
            self.log.info(f"Password set for new user {username}")
            return username
