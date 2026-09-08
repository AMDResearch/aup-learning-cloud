# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "dockerfiles" / "Base" / "Dockerfile.rocm"
BUILD_CONFIG = ROOT / ".github" / "build-config.json"
WORKFLOW = ROOT / ".github" / "workflows" / "docker-build.yml"


def test_rocm_base_tracks_rocm_10_and_gfx1153() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert "ARG ROCM_VERSION=10.0.0" in dockerfile
    assert "stable.repo.amd.com/rocm/core/packages/ubuntu2404" in dockerfile
    assert "stable.repo.amd.com/rocm/whl-next" in dockerfile
    assert "gfx1153" in dockerfile
    assert "amdrocm-core-sdk${SDK_VER}-${isa}" in dockerfile
    assert "torch[${EXTRAS}]" in dockerfile


def test_build_config_gpu_targets_match_rocm_10_isa_lists() -> None:
    config = json.loads(BUILD_CONFIG.read_text(encoding="utf-8"))
    by_name = {entry["name"]: entry for entry in config["gpu_targets"]}
    assert list(by_name) == [
        "gfx110x",
        "gfx1150",
        "gfx1151",
        "gfx1152",
        "gfx1153",
        "gfx120x",
    ]
    assert config["default_gpu_target"] == "gfx1151"
    assert by_name["gfx110x"]["rocm_sdk"] == ["gfx1100", "gfx1101", "gfx1102", "gfx1103"]
    assert by_name["gfx110x"]["pytorch_devices"] == by_name["gfx110x"]["rocm_sdk"]
    assert by_name["gfx120x"]["rocm_sdk"] == ["gfx1200", "gfx1201"]
    assert by_name["gfx1153"]["rocm_sdk"] == ["gfx1153"]
    assert by_name["gfx1153"]["pytorch_devices"] == ["gfx1153"]


def test_docker_build_workflow_dispatch_lists_every_build_config_target() -> None:
    config = json.loads(BUILD_CONFIG.read_text(encoding="utf-8"))
    names = [entry["name"] for entry in config["gpu_targets"]]
    workflow = WORKFLOW.read_text(encoding="utf-8")
    options = re.search(
        r"gpu_target:\n(?:.*\n)*?        options:\n((?:          - .+\n)+)",
        workflow,
    )
    assert options is not None
    listed = [
        line.strip().removeprefix("- ") for line in options.group(1).splitlines() if line.strip().startswith("- ")
    ]
    assert listed[0] == "all"
    assert listed[1:] == names
