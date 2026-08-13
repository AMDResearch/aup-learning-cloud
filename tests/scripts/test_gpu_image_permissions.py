# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "dockerfiles" / "Base" / "Dockerfile.rocm"


def test_rocm_base_leaves_gpu_device_permissions_to_the_host() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    forbidden_patterns = (
        r"\b(?:groupadd|groupmod|usermod)\b.*\b(?:video|render)\b",
        r"/etc/udev",
        r"chmod\s+666\b",
        r"chmod\b.*(?:/dev/|kfd|render|card)",
    )
    for pattern in forbidden_patterns:
        assert re.search(pattern, dockerfile) is None, pattern
