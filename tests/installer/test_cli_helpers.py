# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Tests for small ``cli.py`` pure helpers.

Specifically the upgrade-time course-preservation helper, which is the
glue that lets a bare ``./auplc-installer rt upgrade`` (or the TUI's
``rt → upgrade`` path) inherit the previously installed selection
instead of silently widening to "all" because no ``--courses=`` flag
was passed.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from auplc_installer.catalog import (
    COURSE_PRESET_BASIC,
    NONE_SENTINEL,
    CourseSelection,
)
from auplc_installer.cli import _preserve_courses_for_upgrade
from auplc_installer.gpu import GpuConfig, append_product
from auplc_installer.overlay import generate_values_overlay
from auplc_installer.state import InstallerState


def _make_state_with_courses(courses: CourseSelection) -> InstallerState:
    state = InstallerState()
    state.courses = courses
    return state


def _write_overlay(path: Path, courses: CourseSelection) -> None:
    cfg = GpuConfig()
    append_product(cfg, "AMD_Radeon_8060S_Graphics")
    generate_values_overlay(
        cfg,
        image_registry="ghcr.io/amdresearch",
        image_tag="v1.0",
        courses=courses,
        offline_mode=False,
        overlay_path=path,
    )


def test_default_courses_inherits_previous_basic() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        overlay = Path(tmp) / "values.local.yaml"
        _write_overlay(overlay, CourseSelection(picks=list(COURSE_PRESET_BASIC)))

        state = _make_state_with_courses(CourseSelection.default())
        _preserve_courses_for_upgrade(state, overlay)
        assert state.courses.picks == list(COURSE_PRESET_BASIC)


def test_default_courses_inherits_previous_none_sentinel() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        overlay = Path(tmp) / "values.local.yaml"
        _write_overlay(overlay, CourseSelection(picks=[NONE_SENTINEL]))

        state = _make_state_with_courses(CourseSelection.default())
        _preserve_courses_for_upgrade(state, overlay)
        assert state.courses.is_none()


def test_explicit_selection_is_not_overwritten() -> None:
    """User-passed --courses=basic must beat whatever the file says."""
    with tempfile.TemporaryDirectory() as tmp:
        overlay = Path(tmp) / "values.local.yaml"
        _write_overlay(overlay, CourseSelection(picks=["cpu"]))

        explicit = CourseSelection(picks=list(COURSE_PRESET_BASIC))
        state = _make_state_with_courses(explicit)
        _preserve_courses_for_upgrade(state, overlay)
        assert state.courses.picks == list(COURSE_PRESET_BASIC)


def test_missing_overlay_keeps_default() -> None:
    """No prior overlay => upgrade falls back to the historical 'all' default."""
    with tempfile.TemporaryDirectory() as tmp:
        overlay = Path(tmp) / "values.local.yaml"  # never created

        state = _make_state_with_courses(CourseSelection.default())
        _preserve_courses_for_upgrade(state, overlay)
        assert state.courses.is_default()
