# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import assert_never

from auplc_installer.auth import validate_local_admin_username
from auplc_installer.util import InstallerError


class AccessProfile(str, Enum):
    PERSONAL = "personal"
    LOCAL = "local"


@dataclass(frozen=True, slots=True)
class AccessSettings:
    profile: AccessProfile
    admin_username: str

    @property
    def access_mode(self) -> str:
        return self.profile.value

    @property
    def quota_enabled(self) -> bool:
        match self.profile:
            case AccessProfile.PERSONAL:
                return False
            case AccessProfile.LOCAL:
                return False
            case unreachable:
                assert_never(unreachable)


_ACCESS_HEADER_RE = re.compile(r"^# Access mode\s*:\s*(.+?)\s*$")
_ADMIN_HEADER_RE = re.compile(r"^# Admin username\s*:\s*(.+?)\s*$")


def resolve_access_settings(access_mode: str, admin_username: str) -> AccessSettings:
    username = validate_local_admin_username(admin_username or "admin")
    match access_mode or AccessProfile.PERSONAL.value:
        case AccessProfile.PERSONAL.value:
            return AccessSettings(AccessProfile.PERSONAL, "admin")
        case AccessProfile.LOCAL.value:
            return AccessSettings(AccessProfile.LOCAL, username)
        case _:
            raise InstallerError("--access-mode must be local or personal")


def detect_installer_profile(text: str) -> AccessSettings | None:
    access_mode = _header_value(text, _ACCESS_HEADER_RE)
    admin_username = _header_value(text, _ADMIN_HEADER_RE)
    if access_mode is None or admin_username is None:
        return None
    try:
        return resolve_access_settings(access_mode, admin_username)
    except InstallerError:
        return None


def _header_value(text: str, pattern: re.Pattern[str]) -> str | None:
    matches = [match.group(1) for line in text.splitlines() if (match := pattern.match(line))]
    if len(matches) != 1:
        return None
    return matches[0]
