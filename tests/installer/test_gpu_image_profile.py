# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

"""Image-profile contracts for installer GPU resolution."""

from __future__ import annotations

import pytest

from auplc_installer.gpu import GpuConfig, append_product, sku_for_product_name
from auplc_installer.rocm_profiles import resolve_profile
from auplc_installer.util import InstallerError


@pytest.mark.parametrize(
    ("product_name", "accelerator_key", "image_profile"),
    [
        ("AMD_Radeon_780M_Graphics", "phx", "gfx1103"),
        ("AMD_Radeon_890M_Graphics", "strix", "gfx1150"),
        ("AMD_Radeon_8060S_Graphics", "strix-halo", "gfx1151"),
        ("AMD_Radeon_RX_9060", "9060", "gfx1200"),
        ("AMD_Radeon_RX_9060_XT", "9060xt", "gfx1200"),
        ("AMD_Radeon_RX_9070", "9070", "gfx1201"),
        ("AMD_Radeon_RX_9070_XT", "9070xt", "gfx1201"),
        ("AMD_Radeon_AI_PRO_R9700", "r9700", "gfx1201"),
    ],
)
def test_curated_product_resolves_catalog_image_profile(
    product_name: str,
    accelerator_key: str,
    image_profile: str,
) -> None:
    row = sku_for_product_name(product_name)

    assert row.accelerator_key == accelerator_key
    assert row.image_profile == resolve_profile(image_profile).profile


def test_unknown_product_fails_instead_of_synthesising_an_image_route() -> None:
    with pytest.raises(InstallerError, match="Unsupported AMD GPU product 'AMD_Mystery_GPU'"):
        sku_for_product_name("AMD_Mystery_GPU")


def test_config_tracks_profiles_without_a_gpu_target_alias() -> None:
    cfg = GpuConfig()
    append_product(cfg, "AMD_Radeon_8060S_Graphics")
    append_product(cfg, "AMD_Radeon_RX_9070_XT")

    assert cfg.image_profile == "gfx1151"
    assert not cfg.homogeneous_profile
    assert not hasattr(cfg, "gpu_target")
