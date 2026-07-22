# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

from pathlib import Path

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
