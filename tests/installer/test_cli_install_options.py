# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Tests for CLI/TUI parity helpers (summary + install image-source resolution)."""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pytest

from auplc_installer.catalog import COURSE_PRESET_ALL, CourseSelection
from auplc_installer.cli import HELP_TEXT, _apply_global_flags, _build_parser, cmd_install_plan, main
from auplc_installer.gpu import CURATED_ACCELERATOR_KEYS
from auplc_installer.state import InstallerState
from auplc_installer.summary import (
    IMAGE_SOURCE_BUILD,
    IMAGE_SOURCE_PULL,
    format_configuration_summary,
    normalize_image_source,
    resolve_install_image_source,
)
from auplc_installer.util import InstallerError


def test_normalize_image_source_pull_and_ghcr_alias() -> None:
    assert normalize_image_source("pull") == IMAGE_SOURCE_PULL
    assert normalize_image_source("ghcr") == IMAGE_SOURCE_PULL


def test_normalize_image_source_build() -> None:
    assert normalize_image_source("build") == IMAGE_SOURCE_BUILD


def test_normalize_image_source_unknown_raises() -> None:
    with pytest.raises(InstallerError):
        normalize_image_source("nope")


def test_resolve_install_image_source_default_is_pull() -> None:
    pull, label = resolve_install_image_source(image_source=None, legacy_pull=False)
    assert pull
    assert label == IMAGE_SOURCE_PULL


def test_resolve_install_image_source_legacy_pull_flag() -> None:
    pull, label = resolve_install_image_source(image_source=None, legacy_pull=True)
    assert pull
    assert label == IMAGE_SOURCE_PULL


def test_resolve_install_image_source_explicit_pull() -> None:
    pull, label = resolve_install_image_source(image_source="pull", legacy_pull=False)
    assert pull
    assert label == IMAGE_SOURCE_PULL


def test_resolve_install_image_source_explicit_ghcr_alias() -> None:
    pull, label = resolve_install_image_source(image_source="ghcr", legacy_pull=False)
    assert pull
    assert label == IMAGE_SOURCE_PULL


def test_resolve_install_image_source_explicit_build() -> None:
    pull, label = resolve_install_image_source(image_source="build", legacy_pull=True)
    assert not pull
    assert label == IMAGE_SOURCE_BUILD


def test_resolve_install_image_source_explicit_build_overrides_legacy_pull() -> None:
    pull, label = resolve_install_image_source(image_source="build", legacy_pull=True)
    assert not pull
    assert label == IMAGE_SOURCE_BUILD


def test_resolve_install_image_source_offline_bundle() -> None:
    pull, label = resolve_install_image_source(
        image_source="pull",
        legacy_pull=False,
        offline_mode=True,
        bundle_dir=Path("/tmp/bundle"),
    )
    assert not pull
    assert "Offline bundle" in label


def test_resolve_install_image_source_unknown_source_raises() -> None:
    with pytest.raises(InstallerError):
        resolve_install_image_source(image_source="nope", legacy_pull=False)


def test_format_configuration_summary_includes_core_fields() -> None:
    state = InstallerState(
        gpu_type="strix-halo",
        use_docker=True,
        image_registry="ghcr.io/example",
        image_tag="develop",
        courses=CourseSelection(picks=list(COURSE_PRESET_ALL)),
    )
    text = format_configuration_summary(state, image_source_label=IMAGE_SOURCE_PULL)
    assert "Configuration summary" in text
    assert "strix-halo" in text
    assert "Docker" in text
    assert "  Image source     : pull" in text
    assert "ghcr.io/example" in text
    assert "develop" in text
    assert "Course-CV" in text


def test_apply_global_flags_gpu_auto_clears_override() -> None:
    state = InstallerState(gpu_type="9070xt")
    parser = _build_parser()
    args = parser.parse_args(["--gpu=auto"])
    _apply_global_flags(state, args)
    assert state.gpu_type == ""


def test_help_lists_only_curated_gpu_hardware_choices() -> None:
    expected_lines = (
        "                       phx        - Radeon 780M (gfx1103)",
        "                       strix      - Radeon 890M (gfx1150)",
        "                       strix-halo - Strix Halo iGPU (gfx1151)",
        "                      9060       - Radeon RX 9060 (gfx1200)",
        "                      9060xt     - Radeon RX 9060 XT (gfx1200)",
        "                      9070       - Radeon RX 9070 (gfx1201)",
        "                      9070xt     - Radeon RX 9070 XT (gfx1201)",
        "                      r9700      - Radeon AI PRO R9700 (gfx1201)",
    )
    help_lines = HELP_TEXT.splitlines()
    for expected_line in expected_lines:
        assert expected_line in help_lines
    for removed_key in ("9600gre", "rdna4", "dgpu", "gfx1152"):
        assert removed_key not in HELP_TEXT


def test_tui_lists_only_curated_gpu_hardware_choices() -> None:
    from auplc_installer.tui import GPU_CHOICES

    assert tuple(choice.value for choice in GPU_CHOICES) == ("", *CURATED_ACCELERATOR_KEYS)
    assert "gfx1152" not in {choice.value for choice in GPU_CHOICES}


def test_apply_global_flags_runtime_containerd() -> None:
    state = InstallerState(use_docker=True)
    parser = _build_parser()
    args = parser.parse_args(["--runtime=containerd"])
    _apply_global_flags(state, args)
    assert not state.use_docker


def test_apply_global_flags_runtime_wins_over_docker_flag() -> None:
    state = InstallerState(use_docker=True)
    parser = _build_parser()
    args = parser.parse_args(["--runtime=containerd", "--docker=1"])
    _apply_global_flags(state, args)
    assert not state.use_docker


def test_apply_global_flags_image_flags() -> None:
    state = InstallerState()
    parser = _build_parser()
    args = parser.parse_args(
        [
            "--image-source=pull",
            "--image-registry=registry.example.com/org",
            "--image-tag=develop",
        ]
    )
    _apply_global_flags(state, args)
    assert state.image_source == "pull"
    assert state.image_registry == "registry.example.com/org"
    assert state.image_tag == "develop"


def test_install_dry_run_prints_summary() -> None:
    state = InstallerState(
        image_source="pull",
        image_tag="develop",
        courses=CourseSelection(picks=list(COURSE_PRESET_ALL)),
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        cmd_install_plan(state, legacy_pull=False)
    out = buf.getvalue()
    assert "Configuration summary" in out
    assert "develop" in out
    assert "  Image source     : pull" in out


def test_install_dry_run_defaults_to_pull() -> None:
    state = InstallerState()
    buf = io.StringIO()
    with redirect_stdout(buf):
        cmd_install_plan(state, legacy_pull=False)
    out = buf.getvalue()
    assert "  Image source     : pull" in out


def test_help_flag_prints_usage() -> None:
    buf = io.StringIO()
    with redirect_stdout(buf):
        main(["--help"])
    out = buf.getvalue()
    assert "Usage: ./auplc-installer" in out
    assert "install --dry-run" in out


@patch("auplc_installer.cli._resolve_source_root")
@patch("auplc_installer.cli.InstallerState.from_environment")
def test_main_install_dry_run(mock_from_env, mock_root) -> None:
    mock_root.return_value = Path("/repo")
    mock_from_env.return_value = InstallerState(image_tag="develop")
    buf = io.StringIO()
    with redirect_stdout(buf):
        main(["install", "--dry-run", "--image-tag=develop"])
    out = buf.getvalue()
    assert "Configuration summary" in out
    assert "develop" in out
    assert "  Image source     : pull" in out


@patch("auplc_installer.cli._resolve_source_root")
@patch("auplc_installer.cli.InstallerState.from_environment")
def test_main_install_dry_run_rejects_unsupported_gpu_override(mock_from_env, mock_root) -> None:
    mock_root.return_value = Path("/repo")
    mock_from_env.return_value = InstallerState()

    with pytest.raises(SystemExit) as exc_info:
        main(["install", "--dry-run", "--gpu=unsupported-gpu"])

    assert exc_info.value.code == 1


@patch("auplc_installer.cli._resolve_source_root")
@patch("auplc_installer.cli.InstallerState.from_environment")
def test_dry_run_without_install_errors(mock_from_env, mock_root) -> None:
    mock_root.return_value = Path("/repo")
    mock_from_env.return_value = InstallerState()
    with pytest.raises(SystemExit) as exc_info:
        main(["detect-gpu", "--dry-run"])
    assert exc_info.value.code == 1
