# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Tests for :mod:`auplc_installer.manifest`.

manifest.json is what flips a tarball into "this is an air-gapped bundle";
making sure read/write stays a faithful round-trip protects offline users
who can't easily roll back a broken bundle.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from auplc_installer.gpu import (
    GpuConfig,
    append_product,
    detect_and_configure_gpu,
    refine_gpu_config_from_node_labels,
)
from auplc_installer.manifest import BundleManifest, detect_offline_bundle
from auplc_installer.pack import pack_write_manifest
from auplc_installer.state import InstallerState
from auplc_installer.util import InstallerError


def _sample_manifest() -> BundleManifest:
    return BundleManifest(
        format_version="2",
        build_date="2026-04-29T06:00:00Z",
        image_profile="gfx1151",
        accelerator_key="strix-halo",
        accelerator_env="",
        image_registry="ghcr.io/amdresearch",
        image_tag="v1.0",
        k3s_version="v1.32.3+k3s1",
        helm_version="v3.17.2",
        k9s_version="v0.32.7",
    )


def _manifest_for(*, accelerator_key: str, image_profile: str) -> BundleManifest:
    manifest = _sample_manifest()
    manifest.accelerator_key = accelerator_key
    manifest.image_profile = image_profile
    return manifest


def test_write_then_from_path_recovers_every_field() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "manifest.json"
        original = _sample_manifest()
        original.write(path)
        loaded = BundleManifest.from_path(path)
        assert loaded == original


def test_write_emits_4_space_indent() -> None:
    """Bash version layout is contractual for human-diff readability."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "manifest.json"
        _sample_manifest().write(path)
        text = path.read_text(encoding="utf-8")
        # Every continuation line should start with at least 4 spaces of indent
        for line in text.splitlines()[1:-1]:
            if line.strip():
                assert line.startswith("    "), f"bad indent: {line!r}"


def test_write_appends_trailing_newline() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "manifest.json"
        _sample_manifest().write(path)
        assert path.read_text(encoding="utf-8").endswith("}\n")


def test_write_rejects_non_v2_manifest() -> None:
    with tempfile.TemporaryDirectory() as tmp, pytest.raises(InstallerError, match="format_version '2'"):
        BundleManifest(format_version="1").write(Path(tmp) / "manifest.json")


def test_pack_write_manifest_round_trips_gpu_config() -> None:
    cfg = GpuConfig()
    append_product(cfg, "AMD_Radeon_8060S_Graphics")
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp)
        pack_write_manifest(
            staging,
            cfg=cfg,
            image_registry="ghcr.io/amdresearch",
            image_tag="v1.0",
        )
        loaded = BundleManifest.from_path(staging / "manifest.json")
        assert loaded.format_version == "2"
        assert loaded.image_profile == cfg.image_profile == "gfx1151"
        assert loaded.accelerator_key == cfg.accelerator_key == "strix-halo"
        assert loaded.image_tag == "v1.0"


def test_from_path_rejects_legacy_manifest_format() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "manifest.json"
        path.write_text(json.dumps({"format_version": "1"}), encoding="utf-8")
        with pytest.raises(InstallerError, match="format_version '2'"):
            BundleManifest.from_path(path)


def test_detect_offline_bundle_returns_none_when_manifest_absent() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert detect_offline_bundle(tmp) is None


def test_detect_offline_bundle_returns_parsed_manifest_when_present() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "manifest.json").write_text(
            json.dumps(
                {
                    "format_version": "2",
                    "image_profile": "gfx1151",
                    "accelerator_key": "strix-halo",
                    "accelerator_env": "",
                    "image_registry": "ghcr.io/amdresearch",
                    "image_tag": "v1.0",
                }
            ),
            encoding="utf-8",
        )
        m = detect_offline_bundle(tmp)
        assert m is not None
        assert m.image_profile == "gfx1151"
        assert m.image_tag == "v1.0"


def test_offline_state_records_explicit_manifest_pin_without_seeding_skus(monkeypatch, tmp_path: Path) -> None:
    _sample_manifest().write(tmp_path / "manifest.json")
    monkeypatch.setenv("IMAGE_REGISTRY", "ghcr.io/ignored")
    monkeypatch.setenv("IMAGE_TAG", "ignored")

    state = InstallerState.from_environment(script_dir=tmp_path)

    assert state.offline_mode
    assert not state.use_docker
    assert state.image_registry == "ghcr.io/amdresearch"
    assert state.image_tag == "v1.0"
    assert state.gpu.skus == []
    assert state.gpu.fallback_accelerator_key == "strix-halo"
    assert state.gpu.pinned_image_profile == "gfx1151"
    assert not state.gpu.offline_pin_validated


def test_offline_state_rejects_manifest_accelerator_profile_mismatch(tmp_path: Path) -> None:
    manifest = _sample_manifest()
    manifest.accelerator_key = "9060"
    manifest.write(tmp_path / "manifest.json")

    with pytest.raises(InstallerError, match="does not match its pinned image profile"):
        InstallerState.from_environment(script_dir=tmp_path)


def test_offline_state_rejects_noncanonical_manifest_accelerator_key(tmp_path: Path) -> None:
    manifest = _sample_manifest()
    manifest.accelerator_key = "gfx1151"
    manifest.write(tmp_path / "manifest.json")

    with pytest.raises(InstallerError, match="canonical accelerator key"):
        InstallerState.from_environment(script_dir=tmp_path)


def test_offline_manifest_pin_validates_matching_host_and_labeller(monkeypatch, tmp_path: Path) -> None:
    _sample_manifest().write(tmp_path / "manifest.json")
    state = InstallerState.from_environment(script_dir=tmp_path)
    monkeypatch.setattr(
        "auplc_installer.gpu.detect_gpu_product_names",
        lambda: ["AMD_Radeon_8060S_Graphics"],
    )

    detect_and_configure_gpu(state.gpu)
    assert state.gpu.offline_pin_validated
    monkeypatch.setattr(
        "auplc_installer.gpu._read_gpu_product_names_from_node_labels",
        lambda: ["AMD_Radeon_8060S_Graphics"],
    )

    refine_gpu_config_from_node_labels(state.gpu)
    assert (state.gpu.accelerator_key, state.gpu.image_profile) == ("strix-halo", "gfx1151")


def test_offline_manifest_pin_rejects_mismatched_host(monkeypatch, tmp_path: Path) -> None:
    _sample_manifest().write(tmp_path / "manifest.json")
    state = InstallerState.from_environment(script_dir=tmp_path)
    monkeypatch.setattr(
        "auplc_installer.gpu.detect_gpu_product_names",
        lambda: ["AMD_Radeon_RX_9060"],
    )

    with pytest.raises(InstallerError, match="Offline bundle profile pin"):
        detect_and_configure_gpu(state.gpu)


def test_offline_gfx1200_bundle_replaces_fallback_with_profile_compatible_labeller_accelerator(
    monkeypatch, tmp_path: Path
) -> None:
    _manifest_for(accelerator_key="9060", image_profile="gfx1200").write(tmp_path / "manifest.json")
    state = InstallerState.from_environment(script_dir=tmp_path)
    monkeypatch.setattr("auplc_installer.gpu.detect_gpu_product_names", lambda: [])
    monkeypatch.setattr("auplc_installer.gpu.detect_gpu_gfx_target", lambda: None)

    detect_and_configure_gpu(state.gpu)
    assert not state.gpu.offline_pin_validated
    assert state.gpu.accelerator_key == "9060"
    monkeypatch.setattr(
        "auplc_installer.gpu._read_gpu_product_names_from_node_labels",
        lambda: ["AMD_Radeon_RX_9060_XT"],
    )

    refine_gpu_config_from_node_labels(state.gpu)

    assert state.gpu.offline_pin_validated
    assert (state.gpu.accelerator_key, state.gpu.image_profile) == ("9060xt", "gfx1200")


def test_offline_gfx1201_bundle_accepts_profile_compatible_labeller_accelerator(monkeypatch, tmp_path: Path) -> None:
    _manifest_for(accelerator_key="9070xt", image_profile="gfx1201").write(tmp_path / "manifest.json")
    state = InstallerState.from_environment(script_dir=tmp_path)
    monkeypatch.setattr("auplc_installer.gpu.detect_gpu_product_names", lambda: [])
    monkeypatch.setattr("auplc_installer.gpu.detect_gpu_gfx_target", lambda: None)

    detect_and_configure_gpu(state.gpu)
    assert not state.gpu.offline_pin_validated
    assert state.gpu.accelerator_key == "9070xt"
    monkeypatch.setattr(
        "auplc_installer.gpu._read_gpu_product_names_from_node_labels",
        lambda: ["AMD_Radeon_AI_PRO_R9700"],
    )

    refine_gpu_config_from_node_labels(state.gpu)

    assert state.gpu.offline_pin_validated
    assert (state.gpu.accelerator_key, state.gpu.image_profile) == ("r9700", "gfx1201")


def test_offline_manifest_pin_rejects_mismatched_labeller(monkeypatch, tmp_path: Path) -> None:
    _sample_manifest().write(tmp_path / "manifest.json")
    state = InstallerState.from_environment(script_dir=tmp_path)
    monkeypatch.setattr(
        "auplc_installer.gpu.detect_gpu_product_names",
        lambda: ["AMD_Radeon_8060S_Graphics"],
    )
    detect_and_configure_gpu(state.gpu)
    monkeypatch.setattr(
        "auplc_installer.gpu._read_gpu_product_names_from_node_labels",
        lambda: ["AMD_Radeon_RX_9060"],
    )

    with pytest.raises(InstallerError, match="Offline bundle profile pin gfx1151"):
        refine_gpu_config_from_node_labels(state.gpu)


def test_offline_manifest_pin_without_host_facts_fails_when_labeller_is_unavailable(
    monkeypatch, tmp_path: Path
) -> None:
    _sample_manifest().write(tmp_path / "manifest.json")
    state = InstallerState.from_environment(script_dir=tmp_path)
    monkeypatch.setattr("auplc_installer.gpu.detect_gpu_product_names", lambda: [])
    monkeypatch.setattr("auplc_installer.gpu.detect_gpu_gfx_target", lambda: None)

    detect_and_configure_gpu(state.gpu)
    assert (state.gpu.accelerator_key, state.gpu.image_profile) == ("strix-halo", "gfx1151")
    assert not state.gpu.offline_pin_validated
    monkeypatch.setattr("auplc_installer.gpu._read_gpu_product_names_from_node_labels", lambda: [])

    with pytest.raises(InstallerError, match="could not be validated"):
        refine_gpu_config_from_node_labels(state.gpu)
