# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Tests for :mod:`auplc_installer.catalog`.

Covers the user-facing CLI selection grammar (``--courses=…`` /
``AUPLC_COURSES``) and the helper methods on :class:`CourseSelection` that
the rest of the installer relies on for image filtering and team-mapping
overrides.
"""

from __future__ import annotations

import pytest

from auplc_installer.catalog import (
    COURSE_KEYS_ALL,
    COURSE_PRESET_ALL,
    COURSE_PRESET_BASIC,
    NONE_SENTINEL,
    CourseSelection,
    parse_selection_spec,
)
from auplc_installer.util import InstallerError


def test_empty_string_is_default() -> None:
    assert parse_selection_spec("").is_default()


def test_all_keyword_picks_every_course() -> None:
    sel = parse_selection_spec("all")
    assert sel.picks == list(COURSE_PRESET_ALL)
    assert not sel.is_default()  # explicit selection, not the default sentinel


def test_basic_keyword_picks_cpu_gpu_and_code_server() -> None:
    assert parse_selection_spec("basic").picks == list(COURSE_PRESET_BASIC)


def test_none_keyword_uses_sentinel() -> None:
    sel = parse_selection_spec("none")
    assert sel.is_none()
    assert sel.picks == [NONE_SENTINEL]


@pytest.mark.parametrize("spec", ["ALL", "All", "Basic", "NONE"])
def test_keyword_is_case_insensitive(spec: str) -> None:
    parse_selection_spec(spec)


def test_explicit_keys_round_trip() -> None:
    sel = parse_selection_spec("cpu,gpu,Course-CV")
    assert sel.picks == ["cpu", "gpu", "Course-CV"]


def test_tolerates_whitespace_and_blank_entries() -> None:
    sel = parse_selection_spec("  cpu , ,Course-CV ")
    assert sel.picks == ["cpu", "Course-CV"]


def test_unknown_key_raises() -> None:
    with pytest.raises(InstallerError):
        parse_selection_spec("not-a-real-course")


def test_unknown_key_message_lists_valid_keys() -> None:
    with pytest.raises(InstallerError) as exc_info:
        parse_selection_spec("nope")
    msg = str(exc_info.value)
    assert "nope" in msg
    for key in COURSE_KEYS_ALL:
        assert key in msg


def test_default_returns_all_keys() -> None:
    sel = CourseSelection.default()
    assert sel.effective_keys() == list(COURSE_KEYS_ALL)
    assert sel.is_selected("cpu")
    assert sel.is_selected("Course-LLM")


def test_none_selects_no_keys() -> None:
    sel = CourseSelection(picks=[NONE_SENTINEL])
    assert sel.effective_keys() == []
    assert not sel.is_selected("cpu")


def test_explicit_picks_preserves_order() -> None:
    sel = CourseSelection(picks=["Course-LLM", "cpu"])
    assert sel.effective_keys() == ["Course-LLM", "cpu"]


def test_gpu_image_basenames_only_returns_gpu_required() -> None:
    sel = CourseSelection(picks=["cpu", "gpu", "code-gpu", "Course-CV"])
    # cpu/code-cpu are plain-tagged; gpu/code-gpu/Course-CV are GPU-tagged
    assert sel.gpu_image_basenames() == [
        "auplc-base",
        "auplc-code-gpu",
        "auplc-cv",
    ]
    assert sel.plain_image_basenames() == ["auplc-default"]


def test_make_targets_includes_every_selected_course() -> None:
    sel = CourseSelection(picks=["cpu", "code-cpu", "Course-DL"])
    assert sel.make_targets() == ["base-cpu", "code-cpu", "dl"]


def test_description_default() -> None:
    assert CourseSelection.default().description() == "all (default)"


def test_description_none() -> None:
    assert CourseSelection(picks=[NONE_SENTINEL]).description() == "none"


def test_description_custom() -> None:
    sel = CourseSelection(picks=["cpu", "Course-CV"])
    assert sel.description() == "cpu, Course-CV"
