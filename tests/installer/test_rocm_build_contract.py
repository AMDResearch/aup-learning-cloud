# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

"""Observable contracts for ROCm image build consumers."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from auplc_installer.rocm_profiles import list_profiles, resolve_profile

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "dockerfiles" / "Base" / "Dockerfile.rocm"
MAKEFILE_DIRECTORY = ROOT / "dockerfiles"
README = ROOT / "dockerfiles" / "Base" / "README.md"
CODE_README = ROOT / "dockerfiles" / "Code" / "README.md"
ROOT_README = ROOT / "README.md"
RESOLVER = ROOT / "dockerfiles" / "Base" / "rocm-targets.py"
WORKFLOW = ROOT / ".github" / "workflows" / "docker-build.yml"


def test_resolver_runs_from_the_docker_copy_layout(tmp_path: Path) -> None:
    copied_root = tmp_path / "opt" / "auplc"
    installer = copied_root / "auplc_installer"
    cli = copied_root / "dockerfiles" / "Base" / "rocm-targets.py"
    installer.mkdir(parents=True)
    cli.parent.mkdir(parents=True)
    (installer / "data").mkdir()

    shutil.copy2(ROOT / "auplc_installer" / "__init__.py", installer / "__init__.py")
    shutil.copy2(ROOT / "auplc_installer" / "rocm_profiles.py", installer / "rocm_profiles.py")
    shutil.copy2(ROOT / "auplc_installer" / "data" / "rocm-7.14-profiles.json", installer / "data")
    shutil.copy2(RESOLVER, cli)

    result = subprocess.run(
        [sys.executable, str(cli), "resolve-profile", "gfx1200"],
        cwd=tmp_path,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["rocm_package"] == resolve_profile("gfx1200").rocm_package


def test_dockerfile_consumes_only_the_canonical_build_plan() -> None:
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    assert "ARG AUP_IMAGE_PROFILE=" in dockerfile
    assert 'resolve-profile "${AUP_IMAGE_PROFILE}" --format lines' in dockerfile
    assert "COPY auplc_installer/__init__.py auplc_installer/rocm_profiles.py /opt/auplc/auplc_installer/" in dockerfile
    assert "COPY auplc_installer/data/rocm-7.14-profiles.json /opt/auplc/auplc_installer/data/" in dockerfile
    assert "COPY dockerfiles/Base/rocm-targets.py /opt/auplc/dockerfiles/Base/" in dockerfile
    for field in (
        "APT_KEY_URL",
        "APT_SOURCE",
        "ROCM_PACKAGE",
        "WHEEL_INDEX_URL",
        "TORCH_REQUIREMENT",
        "TORCHVISION_REQUIREMENT",
        "TORCHAUDIO_REQUIREMENT",
    ):
        assert f'plan_value "{field}"' in dockerfile
    for obsolete_name in (
        "GPU_TARGET",
        "ROCM_SDK_TARGET",
        "PYTORCH_WHL_TARGET",
        "PYTORCH_INDEX_URL",
        "ROCM_VERSION",
        "PYTORCH_VERSION",
        "TORCHVISION_VERSION",
        "TORCHAUDIO_VERSION",
        "amdrocm-core-sdk",
        "device-",
    ):
        assert obsolete_name not in dockerfile


@pytest.mark.parametrize("profile", list_profiles())
def test_make_dry_run_builds_profile_suffixed_images(profile: str) -> None:
    plan = resolve_profile(profile)
    result = subprocess.run(
        ["make", "--dry-run", "base-rocm", "code-gpu", "courses", f"AUP_IMAGE_PROFILE={profile}"],
        cwd=MAKEFILE_DIRECTORY,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert f'--build-arg AUP_IMAGE_PROFILE="{profile}"' in result.stdout
    for image in ("auplc-base", "auplc-code-gpu", "auplc-cv", "auplc-dl", "auplc-llm", "auplc-physim"):
        assert f"ghcr.io/amdresearch/{image}:latest-{plan.tag_suffix}" in result.stdout
    assert "GPU_TARGET" not in result.stdout


def test_workflow_resolves_the_profile_matrix_and_default_from_the_catalog() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "image_profile:" in workflow
    assert "image-profiles:" in workflow
    assert "default-image-profile:" in workflow
    assert 'python3 "$RESOLVER" list-profiles' in workflow
    assert 'python3 "$RESOLVER" resolve-profile' in workflow
    assert "matrix.image_profile" in workflow
    assert "AUP_IMAGE_PROFILE=${{ matrix.image_profile }}" in workflow
    assert "matrix.image_profile == needs.changes.outputs.default-image-profile" in workflow
    for path in (
        "auplc_installer/data/rocm-7.14-profiles.json",
        "auplc_installer/rocm_profiles.py",
        "dockerfiles/Base/rocm-targets.py",
    ):
        assert path in workflow
    for obsolete_name in (
        ".github/build-config.json",
        "gpu_target",
        "gpu-target",
        "GPU_TARGET",
        "ROCM_SDK_TARGET",
        "PYTORCH_WHL_TARGET",
        "gfx120x",
        "gfx110x",
    ):
        assert obsolete_name not in workflow


def test_base_readme_describes_profiles_without_aggregate_target_aliases() -> None:
    readme = README.read_text(encoding="utf-8")

    assert "AUP_IMAGE_PROFILE" in readme
    assert "target" in readme.lower()
    for profile in list_profiles():
        assert profile in readme
    for obsolete_name in ("GPU_TARGET", "gfx120x", "gfx110x", "ROCM_SDK_TARGET", "PYTORCH_WHL_TARGET"):
        assert obsolete_name not in readme


def test_user_facing_readmes_distinguish_build_profiles_from_runtime_accelerators() -> None:
    for readme in (ROOT_README, README, CODE_README):
        text = readme.read_text(encoding="utf-8")
        for profile in list_profiles():
            assert profile in text
        assert "gfx1152" in text
        assert "build-only" in text
