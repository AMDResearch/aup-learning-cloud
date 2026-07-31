"""Local administrator username validation."""

from __future__ import annotations

import re

from auplc_installer.util import InstallerError

LOCAL_USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


def validate_local_admin_username(username: str) -> str:
    """Return a canonical local administrator username or raise an actionable error."""
    if not LOCAL_USERNAME_PATTERN.fullmatch(username):
        raise InstallerError(
            "Local administrator username must use lowercase ASCII letters, digits, '.', '_' or '-', "
            "start with a letter or digit, and be at most 64 characters."
        )
    return username
