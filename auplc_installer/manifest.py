# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Read and write offline-bundle ``manifest.json``."""

from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass
from pathlib import Path

from auplc_installer.rocm_profiles import CatalogError, resolve_profile
from auplc_installer.util import InstallerError


@dataclass
class BundleManifest:
    """Pinned configuration for an offline bundle.

    Format v2 is intentionally incompatible with legacy target-based bundles.
    """

    format_version: str = "2"
    build_date: str = ""
    image_profile: str = ""
    accelerator_key: str = ""
    accelerator_env: str = ""
    image_registry: str = ""
    image_tag: str = ""
    k3s_version: str = ""
    helm_version: str = ""
    k9s_version: str = ""

    @classmethod
    def from_path(cls, path: str | Path) -> BundleManifest:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or data.get("format_version") != "2":
            raise InstallerError("Unsupported offline manifest format; expected format_version '2'")
        required = ("image_profile", "accelerator_key", "accelerator_env", "image_registry", "image_tag")
        missing = [field for field in required if not isinstance(data.get(field), str)]
        if missing:
            raise InstallerError(f"Offline manifest is missing required field '{missing[0]}'")
        try:
            image_profile = resolve_profile(data["image_profile"]).profile
        except CatalogError as error:
            raise InstallerError(f"Offline manifest has unsupported image_profile: {data['image_profile']}") from error
        return cls(
            format_version="2",
            build_date=str(data.get("build_date", "")),
            image_profile=image_profile,
            accelerator_key=data["accelerator_key"],
            accelerator_env=data["accelerator_env"],
            image_registry=data["image_registry"],
            image_tag=data["image_tag"],
            k3s_version=str(data.get("k3s_version", "")),
            helm_version=str(data.get("helm_version", "")),
            k9s_version=str(data.get("k9s_version", "")),
        )

    def write(self, path: str | Path) -> None:
        if self.format_version != "2":
            raise InstallerError("Unsupported offline manifest format; expected format_version '2'")
        out = {
            "format_version": self.format_version,
            "build_date": self.build_date or _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "image_profile": resolve_profile(self.image_profile).profile,
            "accelerator_key": self.accelerator_key,
            "accelerator_env": self.accelerator_env,
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
