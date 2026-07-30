# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Tests for :mod:`auplc_installer.overlay`.

The overlay text is the contract between the installer and Helm: any
formatting drift can break ``helm install``. These tests assert two things:

  1. The output is valid YAML for every selection / mode combination we
     ship (so we never emit something Helm won't merge).
  2. Specific structural pieces (``custom.accelerators``, ``custom.resources``,
     ``custom.teams.mapping``, offline ``hub.image``) appear / disappear in
     the right scenarios.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import yaml

from auplc_installer.catalog import (
    COURSE_PRESET_BASIC,
    NONE_SENTINEL,
    CourseSelection,
)
from auplc_installer.gpu import GpuConfig, SkuEntry, append_product
from auplc_installer.overlay import (
    emit_overlay,
    generate_values_overlay,
    try_load_courses_from_overlay,
)


def _strix_halo_cfg() -> GpuConfig:
    cfg = GpuConfig()
    append_product(cfg, "AMD_Radeon_8060S_Graphics")
    return cfg


def _render(
    cfg: GpuConfig,
    *,
    courses: CourseSelection,
    offline_mode: bool = False,
    image_tag: str = "v1.0",
) -> tuple[str, dict]:
    text = emit_overlay(
        cfg,
        image_registry="ghcr.io/amdresearch",
        image_tag=image_tag,
        courses=courses,
        offline_mode=offline_mode,
    )
    return text, yaml.safe_load(text)


def _mixed_config() -> GpuConfig:
    cfg = GpuConfig()
    # primary: strix-halo / gfx1151
    cfg.append(
        SkuEntry(
            accel_key="strix-halo",
            product_name="AMD_Radeon_8060S_Graphics",
            gpu_target="gfx1151",
            accel_env="",
            quota_rate=3,
            display_name="",
        )
    )
    # secondary: r9700 / gfx120x  (different family → triggers overrides)
    cfg.append(
        SkuEntry(
            accel_key="r9700",
            product_name="AMD_Radeon_AI_PRO_R9700",
            gpu_target="gfx120x",
            accel_env="",
            quota_rate=4,
            display_name="",
        )
    )
    return cfg


def _write_and_read_back(courses: CourseSelection) -> CourseSelection | None:
    cfg = _strix_halo_cfg()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "values.local.yaml"
        generate_values_overlay(
            cfg,
            image_registry="ghcr.io/amdresearch",
            image_tag="v1.0",
            courses=courses,
            offline_mode=False,
            overlay_path=path,
        )
        return try_load_courses_from_overlay(path)


def test_default_selection_round_trips_valid_yaml() -> None:
    text, parsed = _render(_strix_halo_cfg(), courses=CourseSelection.default())
    assert isinstance(parsed, dict)
    assert "custom" in parsed
    # default selection must NOT emit teams.mapping
    assert "teams" not in parsed["custom"]


def test_resource_images_use_primary_tag() -> None:
    _, parsed = _render(_strix_halo_cfg(), courses=CourseSelection.default())
    images = parsed["custom"]["resources"]["images"]
    assert images["gpu"] == "ghcr.io/amdresearch/auplc-base:v1.0-gfx1151"
    assert images["code-gpu"] == "ghcr.io/amdresearch/auplc-code-gpu:v1.0-gfx1151"
    assert images["Course-CV"] == "ghcr.io/amdresearch/auplc-cv:v1.0-gfx1151"
    assert images["Course-PhySim"] == "ghcr.io/amdresearch/auplc-physim:v1.0-gfx1151"
    assert images["Course-Finetuning"] == "ghcr.io/amdresearch/auplc-finetuning:v1.0-gfx1151"
    assert images["Course-LocalInference"] == "ghcr.io/amdresearch/auplc-localinference:v1.0-gfx1151"


def test_curated_sku_with_product_name_emits_node_selector() -> None:
    _, parsed = _render(_strix_halo_cfg(), courses=CourseSelection.default())
    accelerators = parsed["custom"]["accelerators"]
    assert "strix-halo" in accelerators
    assert accelerators["strix-halo"]["nodeSelector"]["amd.com/gpu.product-name"] == "AMD_Radeon_8060S_Graphics"


def test_basic_emits_filtered_teams_mapping() -> None:
    _, parsed = _render(
        _strix_halo_cfg(),
        courses=CourseSelection(picks=list(COURSE_PRESET_BASIC)),
    )
    mapping = parsed["custom"]["teams"]["mapping"]
    assert mapping["cpu"] == ["cpu", "code-cpu"]
    assert mapping["gpu"] == ["code-gpu"]


def test_basic_omits_unselected_resource_images() -> None:
    _, parsed = _render(
        _strix_halo_cfg(),
        courses=CourseSelection(picks=list(COURSE_PRESET_BASIC)),
    )
    images = parsed["custom"]["resources"]["images"]
    assert "gpu" in images
    assert "code-gpu" in images
    assert "Course-CV" not in images
    assert "Course-LLM" not in images


def test_none_results_in_empty_teams_and_no_resources() -> None:
    _, parsed = _render(
        _strix_halo_cfg(),
        courses=CourseSelection(picks=[NONE_SENTINEL]),
    )
    custom = parsed["custom"]
    # Every team filtered to empty list since no course is picked
    for team_courses in custom["teams"]["mapping"].values():
        assert team_courses == []
    # No GPU resources should be emitted
    assert "resources" not in custom


def test_offline_mode_injects_hub_image_override() -> None:
    _, parsed = _render(
        _strix_halo_cfg(),
        courses=CourseSelection.default(),
        offline_mode=True,
    )
    assert "hub" in parsed
    assert parsed["hub"]["image"]["name"] == "ghcr.io/amdresearch/auplc-hub"
    assert parsed["hub"]["image"]["tag"] == "v1.0"
    assert parsed["hub"]["image"]["pullPolicy"] == "IfNotPresent"


def test_online_mode_omits_hub_image_override() -> None:
    _, parsed = _render(
        _strix_halo_cfg(),
        courses=CourseSelection.default(),
        offline_mode=False,
    )
    assert "hub" not in parsed


def test_uncurated_sku_emits_full_stanza_with_quota() -> None:
    cfg = GpuConfig()
    append_product(cfg, "AMD_Some_Future_GPU")
    _, parsed = _render(cfg, courses=CourseSelection.default())
    accel = parsed["custom"]["accelerators"]["amd-some-future-gpu"]
    assert accel["quotaRate"] == 4
    assert "displayName" in accel
    assert "description" in accel
    assert accel["nodeSelector"]["amd.com/gpu.product-name"] == "AMD_Some_Future_GPU"


def test_mixed_targets_emit_accelerator_overrides() -> None:
    _, parsed = _render(_mixed_config(), courses=CourseSelection.default())
    gpu_metadata = parsed["custom"]["resources"]["metadata"]["gpu"]
    assert "acceleratorOverrides" in gpu_metadata
    overrides = gpu_metadata["acceleratorOverrides"]
    assert "r9700" in overrides
    assert overrides["r9700"]["image"] == "ghcr.io/amdresearch/auplc-base:v1.0-gfx120x"


def test_mixed_targets_acceleratorkeys_lists_every_sku() -> None:
    _, parsed = _render(_mixed_config(), courses=CourseSelection.default())
    keys = parsed["custom"]["resources"]["metadata"]["gpu"]["acceleratorKeys"]
    assert set(keys) == {"strix-halo", "r9700"}


def test_phx_emits_hsa_override_env() -> None:
    cfg = GpuConfig()
    append_product(cfg, "AMD_Radeon_780M_Graphics")  # phx, sets HSA_OVERRIDE
    _, parsed = _render(cfg, courses=CourseSelection.default())
    env = parsed["custom"]["accelerators"]["phx"]["env"]
    assert env["HSA_OVERRIDE_GFX_VERSION"] == "11.0.0"


def test_fallback_path_skips_accelerator_stanza_for_curated_sku() -> None:
    cfg = GpuConfig()
    cfg.append(
        SkuEntry(
            accel_key="strix",
            product_name="",  # fallback path
            gpu_target="gfx1150",
            accel_env="",
            quota_rate=2,
            display_name="",
        )
    )
    _, parsed = _render(cfg, courses=CourseSelection.default())
    assert "accelerators" not in parsed["custom"]


def test_env_selection_header_round_trips() -> None:
    loaded = _write_and_read_back(CourseSelection.default())
    assert loaded is not None
    assert loaded.is_default()


def test_legacy_course_selection_header_still_loads() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "values.local.yaml"
        path.write_text("# Course selection : cpu, gpu\ncustom: {}\n", encoding="utf-8")
        loaded = try_load_courses_from_overlay(path)
        assert loaded is not None
        assert loaded.picks == ["cpu", "gpu"]


def test_basic_preset_round_trips() -> None:
    original = CourseSelection(picks=list(COURSE_PRESET_BASIC))
    loaded = _write_and_read_back(original)
    assert loaded is not None
    assert loaded.picks == original.picks


def test_none_sentinel_round_trips() -> None:
    loaded = _write_and_read_back(CourseSelection(picks=[NONE_SENTINEL]))
    assert loaded is not None
    assert loaded.is_none()


def test_custom_subset_round_trips() -> None:
    original = CourseSelection(picks=["cpu", "Course-CV"])
    loaded = _write_and_read_back(original)
    assert loaded is not None
    assert loaded.picks == ["cpu", "Course-CV"]


def test_missing_file_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert try_load_courses_from_overlay(Path(tmp) / "nope.yaml") is None


def test_overlay_without_header_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "values.local.yaml"
        path.write_text("custom: {}\n", encoding="utf-8")
        assert try_load_courses_from_overlay(path) is None


def test_unparseable_spec_returns_none() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "values.local.yaml"
        path.write_text(
            "# Course selection : not-a-real-key, also-fake\ncustom: {}\n",
            encoding="utf-8",
        )
        assert try_load_courses_from_overlay(path) is None
