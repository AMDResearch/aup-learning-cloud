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

from auplc_installer.manifest import BundleManifest, detect_offline_bundle


def _sample_manifest() -> BundleManifest:
    return BundleManifest(
        format_version="1",
        build_date="2026-04-29T06:00:00Z",
        gpu_target="gfx1151",
        accel_key="strix-halo",
        accel_env="",
        image_registry="ghcr.io/amdresearch",
        image_tag="v1.0",
        k3s_version="v1.32.3+k3s1",
        helm_version="v3.17.2",
        k9s_version="v0.32.7",
    )


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


def test_from_path_tolerates_missing_optional_fields() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "manifest.json"
        path.write_text(json.dumps({"format_version": "1"}), encoding="utf-8")
        m = BundleManifest.from_path(path)
        assert m.format_version == "1"
        assert m.gpu_target == ""
        assert m.image_registry == ""


def test_detect_offline_bundle_returns_none_when_manifest_absent() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert detect_offline_bundle(tmp) is None


def test_detect_offline_bundle_returns_parsed_manifest_when_present() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "manifest.json").write_text(
            json.dumps(
                {
                    "format_version": "1",
                    "gpu_target": "gfx1151",
                    "image_registry": "ghcr.io/amdresearch",
                    "image_tag": "v1.0",
                }
            ),
            encoding="utf-8",
        )
        m = detect_offline_bundle(tmp)
        assert m is not None
        assert m.gpu_target == "gfx1151"
        assert m.image_tag == "v1.0"
