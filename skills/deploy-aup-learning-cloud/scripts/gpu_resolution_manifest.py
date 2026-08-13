# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

"""Typed GPU-resolution manifest schemas and primitive builders."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, TypedDict

MANIFEST_VERSION: Final = 1


class ResolutionManifest(TypedDict):
    """Serialized fleet GPU-resolution evidence."""

    version: int
    status: str
    hosts: dict[str, bool]


class PxeRootfsManifest(TypedDict):
    """Serialized GPU policy applied to the PXE root filesystem."""

    gpu_access_enabled: bool


class PxeResolutionManifest(ResolutionManifest):
    """Serialized fleet resolution with its PXE rootfs policy."""

    pxe_rootfs: PxeRootfsManifest


def build_resolution_manifest(
    *,
    status: str,
    hosts: Mapping[str, bool],
) -> ResolutionManifest:
    """Build a deterministic ordinary dictionary for fleet resolution."""
    return {
        "version": MANIFEST_VERSION,
        "status": status,
        "hosts": {name: hosts[name] for name in sorted(hosts)},
    }


def build_pxe_resolution_manifest(
    resolution: ResolutionManifest,
    *,
    gpu_access_enabled: bool,
) -> PxeResolutionManifest:
    """Build a PXE manifest without mutating a base fleet manifest."""
    return {
        **resolution,
        "pxe_rootfs": {
            "gpu_access_enabled": gpu_access_enabled,
        },
    }
