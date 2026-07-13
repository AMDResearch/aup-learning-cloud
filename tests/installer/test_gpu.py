# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Tests for :mod:`auplc_installer.gpu` SKU resolution.

Avoids hitting the host (no rocminfo, no ``/sys/class/drm`` reads); instead
exercises the curated/fallback tables and the dataclasses that the rest of
the installer reads from.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from auplc_installer.gpu import (
    _GFX_FALLBACK,
    GPU_CURATED_SKU_KEYS,
    PRODUCT_NAME_TO_SKU,
    GpuConfig,
    SkuEntry,
    _rocminfo_gpu_agent_records,
    append_product,
    detect_and_configure_gpu,
    detect_gpu_gfx_family,
    detect_gpu_product_names,
    is_curated_sku,
    normalise_gpu_type_key,
    normalise_product_name,
    refine_gpu_config_from_node_labels,
    resolve_gpu_config,
    sku_for_detected_product,
    sku_for_product_name,
)
from auplc_installer.util import InstallerError

ROCMINFO_WITH_STRIX_CPU_AND_GPU = """
Agent 1
Name:                    AMD Ryzen AI 9 HX 370 w/ Radeon 890M
Marketing Name:          AMD Ryzen AI 9 HX 370 w/ Radeon 890M
Device Type:             CPU
ISA Info:
Agent 2
Name:                    gfx1150
Marketing Name:          AMD Radeon Graphics
Device Type:             GPU
ISA Info:
ISA 1
Name:                    amdgcn-amd-amdhsa--gfx1150
ISA 2
Name:                    amdgcn-amd-amdhsa--gfx11-generic
"""

_PRODUCT_FOR_KEY = {
    "phx": "AMD_Radeon_780M_Graphics",
    "strix": "AMD_Radeon_890M_Graphics",
    "strix-halo": "AMD_Radeon_8060S_Graphics",
    "9070xt": "AMD_Radeon_RX_9070_XT",
    "r9700": "AMD_Radeon_AI_PRO_R9700",
    "9600gre": "AMD_Radeon_RX_9600_GRE",
}


def _sku_entry(key: str, target: str = "gfx1151") -> SkuEntry:
    return SkuEntry(
        accel_key=key,
        product_name="",
        gpu_target=target,
        accel_env="",
        quota_rate=4,
        display_name="",
    )


def test_normalise_product_name_collapses_internal_whitespace() -> None:
    assert normalise_product_name("AMD Radeon  890M Graphics") == "AMD_Radeon_890M_Graphics"


def test_normalise_product_name_strips_special_chars_keeping_dot_dash_underscore() -> None:
    # Whitespace becomes "_" first, then non-[A-Za-z0-9._-] chars are
    # dropped — so the space between "Foo" and "(Bar)" survives as "_".
    assert normalise_product_name("Foo (Bar)/Baz!") == "Foo_BarBaz"
    assert normalise_product_name("v1.2-rc3") == "v1.2-rc3"


def test_normalise_product_name_strips_outer_underscores() -> None:
    assert normalise_product_name("  Foo Bar  ") == "Foo_Bar"


def test_normalise_product_name_empty_input_yields_empty() -> None:
    assert normalise_product_name("") == ""
    assert normalise_product_name("   ") == ""


def test_normalise_product_name_normalises_ryzen_ai_890m_marketing_name() -> None:
    assert normalise_product_name("AMD Ryzen AI 9 HX 370 w/ Radeon 890M") == "AMD_Ryzen_AI_9_HX_370_w_Radeon_890M"


def test_rocminfo_records_ignore_cpu_marketing_name_and_keep_gpu_gfx_target() -> None:
    assert _rocminfo_gpu_agent_records(ROCMINFO_WITH_STRIX_CPU_AND_GPU) == [("AMD Radeon Graphics", ["gfx1150"])]


@patch("auplc_installer.gpu.command_exists", return_value=True)
@patch("auplc_installer.gpu.run_capture", return_value=SimpleNamespace(stdout=ROCMINFO_WITH_STRIX_CPU_AND_GPU))
def test_detect_gpu_product_names_reads_gpu_agent_marketing_only(*_: object) -> None:
    assert detect_gpu_product_names() == ["AMD_Radeon_Graphics"]


@patch("auplc_installer.gpu.command_exists", return_value=True)
@patch("auplc_installer.gpu.run_capture", return_value=SimpleNamespace(stdout=ROCMINFO_WITH_STRIX_CPU_AND_GPU))
def test_detect_gpu_gfx_family_prefers_gpu_agent_target(*_: object) -> None:
    assert detect_gpu_gfx_family() == "gfx1150"


def test_known_product_name_resolves_to_curated_row() -> None:
    row = sku_for_product_name("AMD_Radeon_8060S_Graphics")
    assert row[0] == "strix-halo"
    assert row[1] == "gfx1151"


def test_unknown_product_name_synthesises_row() -> None:
    row = sku_for_product_name("AMD_Mystery_GPU")
    # Default fallback: gfx120x, no HSA env, quotaRate 4
    assert row[1] == "gfx120x"
    assert row[2] == ""
    assert row[3] == 4
    # Synthesised key sanitised to a valid kebab-cased token
    assert row[0] == "amd-mystery-gpu"
    assert row[4] == "AMD Mystery GPU"


@pytest.mark.parametrize("key", GPU_CURATED_SKU_KEYS)
def test_is_curated_sku(key: str) -> None:
    assert is_curated_sku(key)


def test_is_curated_sku_true_for_9600gre() -> None:
    assert is_curated_sku("9600gre")


def test_is_curated_sku_false_for_unknown() -> None:
    assert not is_curated_sku("totally-unknown")


def test_resolve_gpu_config_known_short_name() -> None:
    accel_key, gpu_target, env, _, _ = resolve_gpu_config("strix-halo")
    assert (accel_key, gpu_target, env) == ("strix-halo", "gfx1151", "")


def test_resolve_gpu_config_known_gfx_alias() -> None:
    accel_key, gpu_target, _, _, _ = resolve_gpu_config("gfx1151")
    assert (accel_key, gpu_target) == ("strix-halo", "gfx1151")


def test_resolve_gpu_config_hyphenated_gfx_alias() -> None:
    accel_key, gpu_target, _, _, _ = resolve_gpu_config("gfx-1150")
    assert (accel_key, gpu_target) == ("strix", "gfx1150")


def test_normalise_gpu_type_key() -> None:
    assert normalise_gpu_type_key(" GFX-1150 ") == "gfx1150"
    assert normalise_gpu_type_key("strix_halo") == "strix-halo"


def test_resolve_gpu_config_unsupported_input_raises() -> None:
    with pytest.raises(InstallerError):
        resolve_gpu_config("totally-not-a-gpu")


def test_unknown_product_uses_detected_gfx_family_before_generic_fallback() -> None:
    row = sku_for_detected_product("AMD_Radeon_Graphics", "gfx1150")
    assert row[0] == "strix"
    assert row[1] == "gfx1150"


def test_unknown_product_without_gfx_family_keeps_generic_fallback() -> None:
    row = sku_for_detected_product("AMD_Radeon_Graphics")
    assert row[1] == "gfx120x"


@patch("auplc_installer.gpu.detect_gpu_gfx_family", return_value="gfx1150")
@patch("auplc_installer.gpu.detect_gpu_product_names", return_value=["AMD_Radeon_Graphics"])
def test_detect_and_configure_uses_gfx_for_generic_single_product_name(*_: object) -> None:
    cfg = GpuConfig()
    detect_and_configure_gpu(cfg)
    assert cfg.accel_key == "strix"
    assert cfg.gpu_target == "gfx1150"
    assert cfg.gpu_product_name == "AMD_Radeon_Graphics"


@patch("auplc_installer.gpu._read_gpu_product_names_from_node_labels", return_value=["AMD_Radeon_Graphics"])
def test_refinement_preserves_existing_gfx_for_generic_product_name(*_: object) -> None:
    cfg = GpuConfig()
    cfg.append(
        SkuEntry(
            accel_key="strix",
            product_name="AMD_Radeon_Graphics",
            gpu_target="gfx1150",
            accel_env="",
            quota_rate=2,
            display_name="",
        )
    )
    refine_gpu_config_from_node_labels(cfg)
    assert cfg.accel_key == "strix"
    assert cfg.gpu_target == "gfx1150"


@pytest.mark.parametrize("short_key,product_name", list(_PRODUCT_FOR_KEY.items()))
def test_fallback_quota_rate_matches_curated(short_key: str, product_name: str) -> None:
    """Same physical GPU should map to the same quotaRate on both paths."""
    fallback_rate = _GFX_FALLBACK[short_key][3]
    curated_rate = PRODUCT_NAME_TO_SKU[product_name][3]
    assert fallback_rate == curated_rate, (
        f"_GFX_FALLBACK[{short_key!r}] quota_rate diverges from PRODUCT_NAME_TO_SKU[{product_name!r}]"
    )


def test_gpu_config_append_dedups_by_accel_key() -> None:
    cfg = GpuConfig()
    cfg.append(_sku_entry("strix-halo"))
    cfg.append(_sku_entry("strix-halo"))  # duplicate
    assert len(cfg.skus) == 1


def test_gpu_config_first_entry_drives_primary_scalars() -> None:
    cfg = GpuConfig()
    cfg.append(_sku_entry("strix-halo", target="gfx1151"))
    cfg.append(_sku_entry("9070xt", target="gfx1201"))
    assert cfg.accel_key == "strix-halo"
    assert cfg.gpu_target == "gfx1151"


def test_gpu_config_homogeneous_target_true_for_single_sku() -> None:
    cfg = GpuConfig()
    cfg.append(_sku_entry("strix-halo"))
    assert cfg.homogeneous_target


def test_gpu_config_homogeneous_target_false_for_mixed_gfx() -> None:
    cfg = GpuConfig()
    cfg.append(_sku_entry("strix-halo", target="gfx1151"))
    cfg.append(_sku_entry("9070xt", target="gfx1201"))
    assert not cfg.homogeneous_target


def test_append_product_uses_curated_table_when_known() -> None:
    cfg = GpuConfig()
    append_product(cfg, "AMD_Radeon_8060S_Graphics")
    assert cfg.accel_key == "strix-halo"
    assert cfg.gpu_target == "gfx1151"
    assert cfg.skus[0].product_name == "AMD_Radeon_8060S_Graphics"


def test_append_product_synthesises_row_when_unknown() -> None:
    cfg = GpuConfig()
    append_product(cfg, "AMD_Some_Future_GPU")
    assert cfg.accel_key == "amd-some-future-gpu"
    assert cfg.gpu_target == "gfx120x"


def test_append_product_ignores_empty_string() -> None:
    cfg = GpuConfig()
    append_product(cfg, "")
    assert cfg.skus == []
