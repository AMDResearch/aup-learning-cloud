# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Read and write offline-bundle ``manifest.json``."""

from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class BundleManifest:
    """Pinned configuration for an offline bundle.

    Mirrors the JSON the bash version writes in ``pack_write_manifest`` and
    parses in ``detect_offline_bundle``. Field names match exactly so old
    bundles remain readable by the new installer.
    """

    format_version: str = "1"
    build_date: str = ""
    gpu_target: str = ""
    accel_key: str = ""
    accel_env: str = ""
    image_registry: str = ""
    image_tag: str = ""
    k3s_version: str = ""
    helm_version: str = ""
    k9s_version: str = ""

    @classmethod
    def from_path(cls, path: str | Path) -> BundleManifest:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls(
            format_version=str(data.get("format_version", "1")),
            build_date=str(data.get("build_date", "")),
            gpu_target=str(data.get("gpu_target", "")),
            accel_key=str(data.get("accel_key", "")),
            accel_env=str(data.get("accel_env", "")),
            image_registry=str(data.get("image_registry", "")),
            image_tag=str(data.get("image_tag", "")),
            k3s_version=str(data.get("k3s_version", "")),
            helm_version=str(data.get("helm_version", "")),
            k9s_version=str(data.get("k9s_version", "")),
        )

    def write(self, path: str | Path) -> None:
        out = {
            "format_version": self.format_version,
            "build_date": self.build_date or _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "gpu_target": self.gpu_target,
            "accel_key": self.accel_key,
            "accel_env": self.accel_env,
            "image_registry": self.image_registry,
            "image_tag": self.image_tag,
            "k3s_version": self.k3s_version,
            "helm_version": self.helm_version,
            "k9s_version": self.k9s_version,
        }
        # Preserve the bash version's pretty-printed "4-space indent, no
        # trailing newline before the closing brace" layout for byte-for-byte
        # compatibility when humans diff bundle metadata.
        Path(path).write_text(json.dumps(out, indent=4) + "\n", encoding="utf-8")


def detect_offline_bundle(script_dir: str | Path) -> BundleManifest | None:
    """Return the parsed manifest when ``script_dir/manifest.json`` exists, else None.

    Matches bash ``detect_offline_bundle``: presence of ``manifest.json`` in
    the same directory as the installer script flips the runner into offline
    mode.
    """
    p = Path(script_dir) / "manifest.json"
    if not p.is_file():
        return None
    return BundleManifest.from_path(p)
