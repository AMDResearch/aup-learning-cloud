# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "dockerfiles" / "Base" / "Dockerfile.rocm"


def test_rocm_base_leaves_gpu_device_permissions_to_the_host() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    forbidden_patterns = (
        r"groupmod\s+-g\s+992\s+render",
        r"groupadd\s+-g\s+992\s+render",
        r"usermod\s+-aG\s+video,render\s+\$\{NB_USER\}",
        r"\brender\b",
        r"/etc/udev",
        r"chmod\s+666\b",
    )
    for pattern in forbidden_patterns:
        assert re.search(pattern, dockerfile) is None, pattern

    assert "echo 'export USER=jovyan' >> /entrypoint.sh" in dockerfile
    assert "echo 'export SHELL=/bin/bash' >> /entrypoint.sh" in dockerfile
    assert 'CMD ["/bin/bash", "/entrypoint.sh"]' in dockerfile
    assert "USER $NB_UID" in dockerfile
    assert "WORKDIR /home/jovyan" in dockerfile
