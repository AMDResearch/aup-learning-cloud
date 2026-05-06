# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Tests for :mod:`auplc_installer.gpu` detection and SKU resolution."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from auplc_installer import gpu
from auplc_installer.gpu import (
    _GFX_FALLBACK,
    GPU_CURATED_SKU_KEYS,
    PRODUCT_NAME_TO_SKU,
    GpuConfig,
    SkuEntry,
    append_product,
    is_curated_sku,
    normalise_product_name,
    resolve_gpu_config,
    sku_for_product_name,
)
from auplc_installer.util import InstallerError


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class GpuMemoryFormattingTests(unittest.TestCase):
    def test_format_gpu_memory_uses_gib(self) -> None:
        self.assertEqual(gpu.format_gpu_memory(64 * 1024**3), "64 GiB")
        self.assertEqual(gpu.format_gpu_memory(1536 * 1024**2), "1.5 GiB")
        self.assertEqual(gpu.format_gpu_memory(None), "")

    def test_build_gpu_description_omits_missing_parts(self) -> None:
        self.assertEqual(
            gpu.build_gpu_description(
                "gfx1151",
                vram_bytes=64 * 1024**3,
                visible_vram_bytes=None,
                gtt_bytes=31 * 1024**3,
            ),
            "gfx1151 | VRAM 64 GiB | GTT 31 GiB",
        )


class DriverInventoryTests(unittest.TestCase):
    def test_driver_inventory_reads_sysfs_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            drm_root = Path(tmp) / "drm"
            device = drm_root / "card0" / "device"
            _write(device / "vendor", "0x1002\n")
            _write(device / "product_name", "AMD Radeon 8060S Graphics\n")
            _write(device / "mem_info_vram_total", str(64 * 1024**3))
            _write(device / "mem_info_vis_vram_total", str(64 * 1024**3))
            _write(device / "mem_info_gtt_total", str(31 * 1024**3))

            with (
                patch.object(gpu, "SYS_DRM_ROOT", drm_root),
                patch.object(gpu, "detect_rocminfo_gpu_marketing_names", return_value=[]),
                patch.object(gpu, "detect_gpu_gfx_family", return_value="gfx1151"),
            ):
                entries = gpu.detect_driver_gpu_inventory()

        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry.accel_key, "strix-halo")
        self.assertEqual(entry.product_name, "AMD_Radeon_8060S_Graphics")
        self.assertEqual(entry.display_name, "AMD Radeon 8060S Graphics")
        self.assertEqual(entry.description, "gfx1151 | VRAM 64 GiB | Visible VRAM 64 GiB | GTT 31 GiB")

    def test_driver_inventory_uses_gfx_display_when_product_name_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            drm_root = Path(tmp) / "drm"
            device = drm_root / "card0" / "device"
            _write(device / "vendor", "0x1002\n")
            _write(device / "mem_info_vram_total", str(64 * 1024**3))
            _write(device / "mem_info_vis_vram_total", str(64 * 1024**3))
            _write(device / "mem_info_gtt_total", str(31 * 1024**3))

            with (
                patch.object(gpu, "SYS_DRM_ROOT", drm_root),
                patch.object(gpu, "detect_rocminfo_gpu_marketing_names", return_value=[]),
                patch.object(gpu, "detect_gpu_gfx_family", return_value="gfx1151"),
            ):
                entries = gpu.detect_driver_gpu_inventory()

        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry.accel_key, "strix-halo")
        self.assertEqual(entry.product_name, "")
        self.assertEqual(entry.display_name, "AMD Radeon 8060S (Strix Halo iGPU)")
        self.assertEqual(entry.description, "gfx1151 | VRAM 64 GiB | Visible VRAM 64 GiB | GTT 31 GiB")


class DetectAndConfigureGpuTests(unittest.TestCase):
    def test_override_wins_over_driver_inventory(self) -> None:
        cfg = GpuConfig()
        driver_entry = SkuEntry(
            accel_key="strix-halo",
            product_name="AMD_Radeon_8060S_Graphics",
            gpu_target="gfx1151",
            accel_env="",
            quota_rate=3,
            display_name="AMD Radeon 8060S Graphics",
            description="gfx1151 | VRAM 64 GiB",
        )

        with (
            patch.object(gpu, "detect_driver_gpu_inventory", return_value=[driver_entry]),
            patch.object(gpu, "detect_gpu_product_names") as product_names,
            patch.object(gpu, "detect_gpu_gfx_family") as gfx_family,
        ):
            gpu.detect_and_configure_gpu(cfg, gpu_type_override="phx")

        self.assertEqual(cfg.accel_key, "phx")
        self.assertEqual(cfg.gpu_target, "gfx110x")
        self.assertEqual(cfg.accel_env, "11.0.0")
        product_names.assert_not_called()
        gfx_family.assert_not_called()

    def test_no_detection_requires_explicit_gpu_type(self) -> None:
        cfg = GpuConfig()
        with (
            patch.object(gpu, "detect_driver_gpu_inventory", return_value=[]),
            patch.object(gpu, "detect_gpu_product_names", return_value=[]),
            patch.object(gpu, "detect_gpu_gfx_family", return_value=None),
            self.assertRaises(InstallerError),
        ):
            gpu.detect_and_configure_gpu(cfg)

    def test_manifest_pinned_target_survives_missing_host_detection(self) -> None:
        cfg = GpuConfig(accel_key="strix-halo", gpu_target="gfx1151", accel_env="")
        with (
            patch.object(gpu, "detect_driver_gpu_inventory", return_value=[]),
            patch.object(gpu, "detect_gpu_product_names", return_value=[]),
            patch.object(gpu, "detect_gpu_gfx_family", return_value=None),
        ):
            gpu.detect_and_configure_gpu(cfg)

        self.assertEqual(cfg.accel_key, "strix-halo")
        self.assertEqual(cfg.gpu_target, "gfx1151")
        self.assertEqual(len(cfg.skus), 1)


class NormaliseProductNameTests(unittest.TestCase):
    def test_collapses_internal_whitespace(self) -> None:
        self.assertEqual(normalise_product_name("AMD Radeon  890M Graphics"), "AMD_Radeon_890M_Graphics")

    def test_strips_special_chars_keeping_dot_dash_underscore(self) -> None:
        # Whitespace becomes "_" first, then non-[A-Za-z0-9._-] chars are
        # dropped — so the space between "Foo" and "(Bar)" survives as "_".
        self.assertEqual(normalise_product_name("Foo (Bar)/Baz!"), "Foo_BarBaz")
        self.assertEqual(normalise_product_name("v1.2-rc3"), "v1.2-rc3")

    def test_strips_outer_underscores(self) -> None:
        self.assertEqual(normalise_product_name("  Foo Bar  "), "Foo_Bar")

    def test_empty_input_yields_empty(self) -> None:
        self.assertEqual(normalise_product_name(""), "")
        self.assertEqual(normalise_product_name("   "), "")


class CuratedSkuLookupTests(unittest.TestCase):
    def test_known_product_name_resolves_to_curated_row(self) -> None:
        row = sku_for_product_name("AMD_Radeon_8060S_Graphics")
        self.assertEqual(row[0], "strix-halo")
        self.assertEqual(row[1], "gfx1151")

    def test_unknown_product_name_synthesises_row(self) -> None:
        row = sku_for_product_name("AMD_Mystery_GPU")
        # Default fallback: gfx120x, no HSA env, quotaRate 4
        self.assertEqual(row[1], "gfx120x")
        self.assertEqual(row[2], "")
        self.assertEqual(row[3], 4)
        # Synthesised key sanitised to a valid kebab-cased token
        self.assertEqual(row[0], "amd-mystery-gpu")
        self.assertEqual(row[4], "AMD Mystery GPU")

    def test_is_curated_sku(self) -> None:
        for key in GPU_CURATED_SKU_KEYS:
            with self.subTest(key=key):
                self.assertTrue(is_curated_sku(key))
        self.assertFalse(is_curated_sku("9600gre"))


class ResolveGpuConfigTests(unittest.TestCase):
    def test_known_short_name(self) -> None:
        accel_key, gpu_target, env, _, _ = resolve_gpu_config("strix-halo")
        self.assertEqual((accel_key, gpu_target, env), ("strix-halo", "gfx1151", ""))

    def test_known_gfx_alias(self) -> None:
        accel_key, gpu_target, _, _, _ = resolve_gpu_config("gfx1151")
        self.assertEqual((accel_key, gpu_target), ("strix-halo", "gfx1151"))

    def test_unsupported_input_raises(self) -> None:
        with self.assertRaises(InstallerError):
            resolve_gpu_config("totally-not-a-gpu")


class FallbackQuotaRateAlignmentTests(unittest.TestCase):
    """Regression guard against the Tier-1 bug we just fixed.

    Same physical GPU should map to the same quotaRate whether the user
    landed on the curated path (PRODUCT_NAME_TO_SKU) or the gfx-family
    fallback (_GFX_FALLBACK).
    """

    PRODUCT_FOR_KEY = {
        "phx": "AMD_Radeon_780M_Graphics",
        "strix": "AMD_Radeon_890M_Graphics",
        "strix-halo": "AMD_Radeon_8060S_Graphics",
        "9070xt": "AMD_Radeon_RX_9070_XT",
        "r9700": "AMD_Radeon_AI_PRO_R9700",
        "9600gre": "AMD_Radeon_RX_9600_GRE",
    }

    def test_fallback_quota_rate_matches_curated(self) -> None:
        for short_key, product_name in self.PRODUCT_FOR_KEY.items():
            with self.subTest(key=short_key):
                fallback_rate = _GFX_FALLBACK[short_key][3]
                curated_rate = PRODUCT_NAME_TO_SKU[product_name][3]
                self.assertEqual(
                    fallback_rate,
                    curated_rate,
                    f"_GFX_FALLBACK[{short_key!r}] quota_rate diverges from PRODUCT_NAME_TO_SKU[{product_name!r}]",
                )


class GpuConfigTests(unittest.TestCase):
    def _entry(self, key: str, target: str = "gfx1151") -> SkuEntry:
        return SkuEntry(
            accel_key=key,
            product_name="",
            gpu_target=target,
            accel_env="",
            quota_rate=4,
            display_name="",
        )

    def test_append_dedups_by_accel_key(self) -> None:
        cfg = GpuConfig()
        cfg.append(self._entry("strix-halo"))
        cfg.append(self._entry("strix-halo"))  # duplicate
        self.assertEqual(len(cfg.skus), 1)

    def test_first_entry_drives_primary_scalars(self) -> None:
        cfg = GpuConfig()
        cfg.append(self._entry("strix-halo", target="gfx1151"))
        cfg.append(self._entry("9070xt", target="gfx1201"))
        self.assertEqual(cfg.accel_key, "strix-halo")
        self.assertEqual(cfg.gpu_target, "gfx1151")

    def test_homogeneous_target_true_for_single_sku(self) -> None:
        cfg = GpuConfig()
        cfg.append(self._entry("strix-halo"))
        self.assertTrue(cfg.homogeneous_target)

    def test_homogeneous_target_false_for_mixed_gfx(self) -> None:
        cfg = GpuConfig()
        cfg.append(self._entry("strix-halo", target="gfx1151"))
        cfg.append(self._entry("9070xt", target="gfx1201"))
        self.assertFalse(cfg.homogeneous_target)

    def test_append_product_uses_curated_table_when_known(self) -> None:
        cfg = GpuConfig()
        append_product(cfg, "AMD_Radeon_8060S_Graphics")
        self.assertEqual(cfg.accel_key, "strix-halo")
        self.assertEqual(cfg.gpu_target, "gfx1151")
        self.assertEqual(cfg.skus[0].product_name, "AMD_Radeon_8060S_Graphics")

    def test_append_product_synthesises_row_when_unknown(self) -> None:
        cfg = GpuConfig()
        append_product(cfg, "AMD_Some_Future_GPU")
        self.assertEqual(cfg.accel_key, "amd-some-future-gpu")
        self.assertEqual(cfg.gpu_target, "gfx120x")

    def test_append_product_ignores_empty_string(self) -> None:
        cfg = GpuConfig()
        append_product(cfg, "")
        self.assertEqual(cfg.skus, [])


if __name__ == "__main__":
    unittest.main()
