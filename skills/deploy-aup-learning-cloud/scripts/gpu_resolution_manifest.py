# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

"""Typed GPU-resolution manifest schemas and primitive builders."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypedDict


class ResolutionManifest(TypedDict):
    """Serialized fleet GPU-resolution evidence."""

    version: int
    status: str
    render_gid: int | None
    hosts: dict[str, bool]


class PxeRootfsManifest(TypedDict):
    """Serialized GPU policy applied to the PXE root filesystem."""

    gpu_access_enabled: bool
    render_gid: int | None


class PxeResolutionManifest(ResolutionManifest):
    """Serialized fleet resolution with its PXE rootfs policy."""

    pxe_rootfs: PxeRootfsManifest


def build_resolution_manifest(
    *,
    version: int,
    status: str,
    render_gid: int | None,
    hosts: Mapping[str, bool],
) -> ResolutionManifest:
    """Build a deterministic ordinary dictionary for fleet resolution."""
    return {
        "version": version,
        "status": status,
        "render_gid": render_gid,
        "hosts": {name: hosts[name] for name in sorted(hosts)},
    }


def build_pxe_resolution_manifest(
    *,
    version: int,
    status: str,
    render_gid: int | None,
    hosts: Mapping[str, bool],
    gpu_access_enabled: bool,
    pxe_render_gid: int | None,
) -> PxeResolutionManifest:
    """Build a PXE manifest without mutating a base fleet manifest."""
    return {
        "version": version,
        "status": status,
        "render_gid": render_gid,
        "hosts": {name: hosts[name] for name in sorted(hosts)},
        "pxe_rootfs": {
            "gpu_access_enabled": gpu_access_enabled,
            "render_gid": pxe_render_gid,
        },
    }
