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
import unittest
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


class OverlayDefaultSelectionTests(unittest.TestCase):
    def test_default_selection_round_trips_valid_yaml(self) -> None:
        text, parsed = _render(_strix_halo_cfg(), courses=CourseSelection.default())
        self.assertIsInstance(parsed, dict)
        self.assertIn("custom", parsed)
        # default selection must NOT emit teams.mapping
        self.assertNotIn("teams", parsed["custom"])

    def test_resource_images_use_primary_tag(self) -> None:
        _, parsed = _render(_strix_halo_cfg(), courses=CourseSelection.default())
        images = parsed["custom"]["resources"]["images"]
        self.assertEqual(images["gpu"], "ghcr.io/amdresearch/auplc-base:v1.0-gfx1151")
        self.assertEqual(images["Course-CV"], "ghcr.io/amdresearch/auplc-cv:v1.0-gfx1151")
        self.assertEqual(images["Course-PhySim"], "ghcr.io/amdresearch/auplc-physim:v1.0-gfx1151")

    def test_curated_sku_with_product_name_emits_node_selector(self) -> None:
        _, parsed = _render(_strix_halo_cfg(), courses=CourseSelection.default())
        accelerators = parsed["custom"]["accelerators"]
        self.assertIn("strix-halo", accelerators)
        self.assertEqual(
            accelerators["strix-halo"]["nodeSelector"]["amd.com/gpu.product-name"],
            "AMD_Radeon_8060S_Graphics",
        )

    def test_curated_sku_with_driver_metadata_emits_display_description(self) -> None:
        cfg = GpuConfig()
        cfg.append(
            SkuEntry(
                accel_key="strix-halo",
                product_name="",
                gpu_target="gfx1151",
                accel_env="",
                quota_rate=3,
                display_name="AMD Radeon 8060S (Strix Halo iGPU)",
                description="gfx1151 | VRAM 64 GiB | Visible VRAM 64 GiB | GTT 31 GiB",
            )
        )
        _, parsed = _render(cfg, courses=CourseSelection.default())
        accel = parsed["custom"]["accelerators"]["strix-halo"]
        self.assertEqual(accel["displayName"], "AMD Radeon 8060S (Strix Halo iGPU)")
        self.assertEqual(accel["description"], "gfx1151 | VRAM 64 GiB | Visible VRAM 64 GiB | GTT 31 GiB")
        self.assertEqual(accel["quotaRate"], 3)


class OverlayBasicSelectionTests(unittest.TestCase):
    def test_basic_emits_filtered_teams_mapping(self) -> None:
        _, parsed = _render(
            _strix_halo_cfg(),
            courses=CourseSelection(picks=list(COURSE_PRESET_BASIC)),
        )
        mapping = parsed["custom"]["teams"]["mapping"]
        # The 'gpu' team's full base list is the four GPU courses; with the
        # basic preset (cpu+gpu) none of those overlap, so it must be empty.
        self.assertEqual(mapping["gpu"], [])
        # The 'cpu' team's only base entry IS 'cpu', so it survives.
        self.assertEqual(mapping["cpu"], ["cpu"])

    def test_basic_omits_unselected_resource_images(self) -> None:
        _, parsed = _render(
            _strix_halo_cfg(),
            courses=CourseSelection(picks=list(COURSE_PRESET_BASIC)),
        )
        images = parsed["custom"]["resources"]["images"]
        self.assertIn("gpu", images)  # 'gpu' is selected via the basic preset
        self.assertNotIn("Course-CV", images)
        self.assertNotIn("Course-LLM", images)


class OverlayNoneSelectionTests(unittest.TestCase):
    def test_none_results_in_empty_teams_and_no_resources(self) -> None:
        _, parsed = _render(
            _strix_halo_cfg(),
            courses=CourseSelection(picks=[NONE_SENTINEL]),
        )
        custom = parsed["custom"]
        # Every team filtered to empty list since no course is picked
        for team_courses in custom["teams"]["mapping"].values():
            self.assertEqual(team_courses, [])
        # No GPU resources should be emitted
        self.assertNotIn("resources", custom)


class OverlayOfflineModeTests(unittest.TestCase):
    def test_offline_mode_injects_hub_image_override(self) -> None:
        _, parsed = _render(
            _strix_halo_cfg(),
            courses=CourseSelection.default(),
            offline_mode=True,
        )
        self.assertIn("hub", parsed)
        self.assertEqual(parsed["hub"]["image"]["name"], "ghcr.io/amdresearch/auplc-hub")
        self.assertEqual(parsed["hub"]["image"]["tag"], "v1.0")
        self.assertEqual(parsed["hub"]["image"]["pullPolicy"], "IfNotPresent")

    def test_online_mode_omits_hub_image_override(self) -> None:
        _, parsed = _render(
            _strix_halo_cfg(),
            courses=CourseSelection.default(),
            offline_mode=False,
        )
        self.assertNotIn("hub", parsed)


class OverlayUncuratedSkuTests(unittest.TestCase):
    """Synthesised SKU should still produce a complete, helm-mergeable stanza."""

    def test_uncurated_sku_emits_full_stanza_with_quota(self) -> None:
        cfg = GpuConfig()
        append_product(cfg, "AMD_Some_Future_GPU")
        _, parsed = _render(cfg, courses=CourseSelection.default())
        accel = parsed["custom"]["accelerators"]["amd-some-future-gpu"]
        self.assertEqual(accel["quotaRate"], 4)
        self.assertIn("displayName", accel)
        self.assertIn("description", accel)
        self.assertEqual(accel["description"], "Auto-detected (gfx120x)")
        self.assertEqual(
            accel["nodeSelector"]["amd.com/gpu.product-name"],
            "AMD_Some_Future_GPU",
        )

    def test_uncurated_sku_uses_live_driver_description_when_present(self) -> None:
        cfg = GpuConfig()
        cfg.append(
            SkuEntry(
                accel_key="amd-future",
                product_name="AMD_Future_GPU",
                gpu_target="gfx120x",
                accel_env="",
                quota_rate=4,
                display_name="AMD Future GPU",
                description="gfx1201 | VRAM 48 GiB | GTT 64 GiB",
            )
        )
        _, parsed = _render(cfg, courses=CourseSelection.default())
        accel = parsed["custom"]["accelerators"]["amd-future"]
        self.assertEqual(accel["description"], "gfx1201 | VRAM 48 GiB | GTT 64 GiB")


class OverlayMixedTargetsTests(unittest.TestCase):
    """When SKUs straddle gfx families we must emit acceleratorOverrides."""

    def _mixed_config(self) -> GpuConfig:
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

    def test_mixed_targets_emit_accelerator_overrides(self) -> None:
        _, parsed = _render(self._mixed_config(), courses=CourseSelection.default())
        gpu_metadata = parsed["custom"]["resources"]["metadata"]["gpu"]
        self.assertIn("acceleratorOverrides", gpu_metadata)
        overrides = gpu_metadata["acceleratorOverrides"]
        self.assertIn("r9700", overrides)
        self.assertEqual(
            overrides["r9700"]["image"],
            "ghcr.io/amdresearch/auplc-base:v1.0-gfx120x",
        )

    def test_mixed_targets_acceleratorkeys_lists_every_sku(self) -> None:
        _, parsed = _render(self._mixed_config(), courses=CourseSelection.default())
        keys = parsed["custom"]["resources"]["metadata"]["gpu"]["acceleratorKeys"]
        self.assertEqual(set(keys), {"strix-halo", "r9700"})


class OverlayHsaOverrideTests(unittest.TestCase):
    def test_phx_emits_hsa_override_env(self) -> None:
        cfg = GpuConfig()
        append_product(cfg, "AMD_Radeon_780M_Graphics")  # phx, sets HSA_OVERRIDE
        _, parsed = _render(cfg, courses=CourseSelection.default())
        env = parsed["custom"]["accelerators"]["phx"]["env"]
        self.assertEqual(env["HSA_OVERRIDE_GFX_VERSION"], "11.0.0")


class OverlayFallbackPathTests(unittest.TestCase):
    """Curated key reached via the gfx-family fallback (no product_name).

    Mirrors the 'rocminfo missing AND no /sys/.../product_name' case: the
    overlay must NOT emit an accelerator stanza for a curated SKU when
    there is no product name to pin a nodeSelector to (helm falls back to
    runtime/values.yaml's hard-coded selector).
    """

    def test_fallback_path_skips_accelerator_stanza_for_curated_sku(self) -> None:
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
        self.assertNotIn("accelerators", parsed["custom"])


class TryLoadCoursesFromOverlayTests(unittest.TestCase):
    """Round-trip CourseSelection through emit → write → re-read.

    Guards the contract that ``rt upgrade`` relies on: a bare upgrade
    must inherit whatever course selection the previous install wrote
    into the overlay header.
    """

    def _write_and_read_back(self, courses: CourseSelection) -> CourseSelection | None:
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

    def test_default_round_trips(self) -> None:
        loaded = self._write_and_read_back(CourseSelection.default())
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertTrue(loaded.is_default())

    def test_basic_preset_round_trips(self) -> None:
        original = CourseSelection(picks=list(COURSE_PRESET_BASIC))
        loaded = self._write_and_read_back(original)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.picks, original.picks)

    def test_none_sentinel_round_trips(self) -> None:
        loaded = self._write_and_read_back(CourseSelection(picks=[NONE_SENTINEL]))
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertTrue(loaded.is_none())

    def test_custom_subset_round_trips(self) -> None:
        original = CourseSelection(picks=["cpu", "Course-CV"])
        loaded = self._write_and_read_back(original)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.picks, ["cpu", "Course-CV"])

    def test_missing_file_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(try_load_courses_from_overlay(Path(tmp) / "nope.yaml"))

    def test_overlay_without_header_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "values.local.yaml"
            path.write_text("custom: {}\n", encoding="utf-8")
            self.assertIsNone(try_load_courses_from_overlay(path))

    def test_unparseable_spec_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "values.local.yaml"
            path.write_text(
                "# Course selection : not-a-real-key, also-fake\ncustom: {}\n",
                encoding="utf-8",
            )
            self.assertIsNone(try_load_courses_from_overlay(path))


if __name__ == "__main__":
    unittest.main()
