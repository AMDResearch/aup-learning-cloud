# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DISK_SHA = "54081f138730dfa15788a46383842cd2f914a1be"


def test_rocm_workflows_keep_profile_and_trust_contracts() -> None:
    docker_build = (ROOT / ".github/workflows/docker-build.yml").read_text(encoding="utf-8")
    pack_bundle = (ROOT / ".github/workflows/pack-bundle.yml").read_text(encoding="utf-8")

    assert "needs.changes.outputs.base-gpu == 'true'" in docker_build
    assert "github.event_name != 'pull_request'" in docker_build
    assert "Determine same-run base image" in docker_build
    assert "github.event.workflow_run.event == 'push'" in pack_bundle
    assert "github.event.workflow_run.head_repository.full_name == github.repository" in pack_bundle
    assert "RAW_IMAGE_TAG: ${{ inputs.image_tag || github.ref_name }}" in pack_bundle
    assert '"${{ inputs.image_tag || github.ref_name }}"' not in pack_bundle
    for workflow in (docker_build, pack_bundle):
        assert "jlumbroso/free-disk-space@main" not in workflow
        assert f"jlumbroso/free-disk-space@{DISK_SHA}" in workflow


def test_pack_bundle_workflow_uses_only_runtime_accelerators_and_profiles() -> None:
    workflow = yaml.load(
        (ROOT / ".github/workflows/pack-bundle.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )

    gpu_input = workflow["on"]["workflow_dispatch"]["inputs"]["gpu_type"]
    assert gpu_input["options"] == ["phx", "strix", "strix-halo", "9060", "9060xt", "9070", "9070xt", "r9700"]
    assert workflow["jobs"]["pack-release"]["strategy"]["matrix"]["include"] == [
        {"image_profile": "gfx1103", "gpu_type": "phx"},
        {"image_profile": "gfx1150", "gpu_type": "strix"},
        {"image_profile": "gfx1151", "gpu_type": "strix-halo"},
        {"image_profile": "gfx1200", "gpu_type": "9060xt"},
        {"image_profile": "gfx1201", "gpu_type": "9070xt"},
    ]
    assert "gfx1152" not in (ROOT / ".github/workflows/pack-bundle.yml").read_text(encoding="utf-8")
