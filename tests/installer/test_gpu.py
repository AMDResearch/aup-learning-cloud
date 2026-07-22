# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

from __future__ import annotations

import pytest

from auplc_installer.gpu import (
    CURATED_ACCELERATOR_KEYS,
    GpuConfig,
    append_product,
    detect_and_configure_gpu,
    normalise_gpu_type_key,
    refine_gpu_config_from_node_labels,
    resolve_gpu_config,
    sku_for_product_name,
)
from auplc_installer.util import InstallerError


def test_supported_accelerators_are_exactly_curated() -> None:
    assert CURATED_ACCELERATOR_KEYS == ("phx", "strix", "strix-halo", "9060", "9060xt", "9070", "9070xt", "r9700")


@pytest.mark.parametrize(
    "product",
    ["AMD_Radeon_RX_9600_GRE", "AMD_Radeon_RX_9600_GRE_Graphics", "AMD_Radeon_RX_9600GRE"],
)
def test_unsupported_9600gre_products_fail(product: str) -> None:
    with pytest.raises(InstallerError, match="Unsupported AMD GPU product"):
        sku_for_product_name(product)


@pytest.mark.parametrize("value", ["gfx1100", "gfx110x", "gfx120x", "rdna4", "dgpu", "9600gre"])
def test_removed_profiles_and_fallbacks_fail(value: str) -> None:
    with pytest.raises(InstallerError):
        resolve_gpu_config(value)


@pytest.mark.parametrize(
    ("value", "accelerator_key", "image_profile"),
    [
        ("gfx1103", "phx", "gfx1103"),
        ("gfx1150", "strix", "gfx1150"),
        ("gfx1151", "strix-halo", "gfx1151"),
    ],
)
def test_unique_detected_gfx_resolves_to_runtime_profile(value: str, accelerator_key: str, image_profile: str) -> None:
    row = resolve_gpu_config(value)
    assert (row.accelerator_key, row.image_profile) == (accelerator_key, image_profile)


def test_build_only_profile_is_not_a_runtime_accelerator() -> None:
    with pytest.raises(InstallerError, match="valid build-only image profile"):
        resolve_gpu_config("gfx1152")


def test_phx_and_strix_preserve_exact_runtime_policy() -> None:
    phx = sku_for_product_name("AMD_Radeon_780M_Graphics")
    strix = sku_for_product_name("AMD_Radeon_890M_Graphics")

    assert (phx.accelerator_key, phx.image_profile, phx.accelerator_env, phx.quota_rate) == (
        "phx",
        "gfx1103",
        "",
        2,
    )
    assert (strix.accelerator_key, strix.image_profile, strix.accelerator_env, strix.quota_rate) == (
        "strix",
        "gfx1150",
        "",
        2,
    )


def test_ambiguous_detected_gfx_requires_accelerator() -> None:
    with pytest.raises(InstallerError, match="multiple accelerators"):
        resolve_gpu_config("gfx1200")


def test_mixed_profiles_are_not_homogeneous() -> None:
    cfg = GpuConfig()
    append_product(cfg, "AMD_Radeon_8060S_Graphics")
    append_product(cfg, "AMD_Radeon_RX_9070_XT")
    assert not cfg.homogeneous_profile
    assert cfg.image_profile == "gfx1151"


def test_gpu_input_normalization() -> None:
    assert normalise_gpu_type_key(" GFX-1151 ") == "gfx1151"


def test_online_provisional_profile_is_replaced_by_authoritative_labeller(monkeypatch) -> None:
    cfg = GpuConfig()
    monkeypatch.setattr("auplc_installer.gpu.detect_gpu_product_names", lambda: [])
    monkeypatch.setattr("auplc_installer.gpu.detect_gpu_gfx_target", lambda: None)

    detect_and_configure_gpu(cfg)
    assert cfg.image_profile == "gfx1151"
    monkeypatch.setattr(
        "auplc_installer.gpu._read_gpu_product_names_from_node_labels",
        lambda: ["AMD_Radeon_RX_9060"],
    )

    refine_gpu_config_from_node_labels(cfg)
    assert (cfg.accelerator_key, cfg.image_profile) == ("9060", "gfx1200")


def test_explicit_offline_pin_rejects_mismatched_host_detection(monkeypatch) -> None:
    cfg = GpuConfig(fallback_accelerator_key="strix-halo", pinned_image_profile="gfx1151")
    monkeypatch.setattr("auplc_installer.gpu.detect_gpu_product_names", lambda: ["AMD_Radeon_RX_9070"])

    with pytest.raises(InstallerError, match="Offline bundle profile pin"):
        detect_and_configure_gpu(cfg)


def test_explicit_offline_pin_rejects_mixed_host_profiles(monkeypatch) -> None:
    cfg = GpuConfig(fallback_accelerator_key="9060", pinned_image_profile="gfx1200")
    monkeypatch.setattr(
        "auplc_installer.gpu.detect_gpu_product_names",
        lambda: ["AMD_Radeon_RX_9060", "AMD_Radeon_RX_9070"],
    )
    monkeypatch.setattr("auplc_installer.gpu.detect_gpu_gfx_target", lambda: None)

    with pytest.raises(InstallerError, match="Offline bundle profile pin gfx1200"):
        detect_and_configure_gpu(cfg)


@pytest.mark.parametrize(
    ("fallback_key", "profile", "raw_target"),
    [("9060", "gfx1200", "gfx1200"), ("9070", "gfx1201", "gfx1201")],
)
def test_explicit_offline_pin_accepts_matching_raw_target_with_fallback(
    monkeypatch, fallback_key: str, profile: str, raw_target: str
) -> None:
    cfg = GpuConfig(fallback_accelerator_key=fallback_key, pinned_image_profile=profile)
    monkeypatch.setattr("auplc_installer.gpu.detect_gpu_product_names", lambda: [])
    monkeypatch.setattr("auplc_installer.gpu.detect_gpu_gfx_target", lambda: raw_target)

    detect_and_configure_gpu(cfg)

    assert (cfg.accelerator_key, cfg.image_profile) == (fallback_key, profile)
    assert cfg.offline_pin_validated


def test_explicit_offline_pin_rejects_mismatched_raw_target(monkeypatch) -> None:
    cfg = GpuConfig(fallback_accelerator_key="9060", pinned_image_profile="gfx1200")
    monkeypatch.setattr("auplc_installer.gpu.detect_gpu_product_names", lambda: [])
    monkeypatch.setattr("auplc_installer.gpu.detect_gpu_gfx_target", lambda: "gfx1201")

    with pytest.raises(InstallerError, match="Offline bundle profile pin gfx1200"):
        detect_and_configure_gpu(cfg)


def test_explicit_offline_pin_rejects_mismatched_labeller_sku(monkeypatch) -> None:
    cfg = GpuConfig(fallback_accelerator_key="strix-halo", pinned_image_profile="gfx1151", offline_pin_validated=True)
    append_product(cfg, "AMD_Radeon_8060S_Graphics")
    monkeypatch.setattr(
        "auplc_installer.gpu._read_gpu_product_names_from_node_labels",
        lambda: ["AMD_Radeon_RX_9070"],
    )

    with pytest.raises(InstallerError, match="Offline bundle profile pin gfx1151"):
        refine_gpu_config_from_node_labels(cfg)
