#!/usr/bin/env python3
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
"""Orchestrate transactional PXE configuration finalization."""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

import pxe_finalization_support as _support
from artifact_store import preflight_destinations, publish_artifacts
from config_rendering import ResolvedGpuPolicy, render_inventory, render_pxe_vars, render_values
from gpu_access_resolution import (
    FleetResolution,
    FleetStatus,
    HostStatus,
    resolution_manifest,
)
from gpu_access_resolution import HostResolution as HostResolution
from gpu_resolution_manifest import build_pxe_resolution_manifest
from pxe_finalization_support import MAX_RENDER_GID as MAX_RENDER_GID
from pxe_finalization_support import (
    VERSION,
    Artifact,
    JsonDocument,
)
from pxe_finalization_support import FinalizationError as FinalizationError
from pxe_finalization_support import PxePaths as PxePaths
from pxe_finalization_support import paths as paths

_artifact_attestations = _support.artifact_attestations
_completion = _support.completion
_controller_resolution = _support.controller_resolution
_exclusive_lock = _support.exclusive_lock
_final_resolution = _support.final_resolution
_generation_paths = _support.generation_paths
_read_artifact_attestation = _support.read_artifact_attestation
_read_document = _support.read_document
_spec_sha256 = _support.spec_sha256
_target = _support.target
_valid_gid = _support.valid_gid
_validate = _support.validate
_verify_canonical_artifacts = _support.verify_canonical_artifacts


def stage_pending(spec: JsonDocument, token: str, controller: FleetResolution, out_dir: Path, force: bool) -> PxePaths:
    pending = paths(out_dir)
    if controller.status is FleetStatus.BLOCKED:
        raise FinalizationError(f"GPU discovery is blocked: {controller.reason}")
    pending.lock.parent.mkdir(parents=True, exist_ok=True)
    with _exclusive_lock(pending.lock):
        context: JsonDocument = {
            "version": VERSION,
            "generation": secrets.token_urlsafe(32),
            "spec_sha256": _spec_sha256(spec),
            "topology": "pxe-diskless",
            "spec": spec,
            "token": token,
            "controller": resolution_manifest(controller),
        }
        bootstrap = render_pxe_vars(spec, _controller_policy(controller, True), str(pending.context))
        bootstrap += "\n".join(
            [
                f"pxe_finalizer_handoff: {_yaml_quote(str(pending.handoff))}",
                f"pxe_finalizer_generation: {_yaml_quote(context['generation'])}",
                f"pxe_finalizer_spec_sha256: {_yaml_quote(context['spec_sha256'])}",
                f"pxe_finalizer_script: {_yaml_quote(str(Path(__file__).with_name('gen_configs.py').resolve()))}",
                "",
            ]
        )
        artifacts: list[Artifact] = [
            (pending.bootstrap_inventory, _render_bootstrap_inventory(spec), 0o600, True),
            (pending.bootstrap_vars, bootstrap, 0o600, True),
            (pending.context, json.dumps(context, sort_keys=True) + "\n", 0o600, True),
        ]
        if not force:
            preflight_destinations(_generation_paths(pending), False)
        publish_artifacts(artifacts, force, _generation_paths(pending))
    return pending


def publish_disabled_rootfs(
    spec: JsonDocument, token: str, controller: FleetResolution, out_dir: Path, force: bool
) -> None:
    pending = paths(out_dir)
    if controller.status is FleetStatus.BLOCKED:
        raise FinalizationError(f"GPU discovery is blocked: {controller.reason}")
    pending.lock.parent.mkdir(parents=True, exist_ok=True)
    with _exclusive_lock(pending.lock):
        policy = _controller_policy(controller, False)
        artifacts: list[Artifact] = [
            (pending.inventory, render_inventory(spec, token, controller), 0o600, True),
            (pending.pxe_vars, render_pxe_vars(spec, policy), 0o600, True),
            (pending.values, render_values(spec, controller), 0o644, False),
            (pending.manifest, _manifest(controller, False, None), 0o644, False),
        ]
        if not force:
            preflight_destinations(_generation_paths(pending), False)
        publish_artifacts(artifacts, force, _generation_paths(pending))


def finalize(out_dir: Path, context_path: Path, handoff_path: Path) -> None:
    pending = paths(out_dir)
    if context_path.resolve() != pending.context or handoff_path.resolve() != pending.handoff:
        raise FinalizationError("PXE finalizer context and handoff paths must be the generated private paths")
    pending.lock.parent.mkdir(parents=True, exist_ok=True)
    with _exclusive_lock(pending.lock):
        context = _read_document(pending.context, "PXE finalizer context")
        handoff = _read_document(pending.handoff, "PXE finalizer handoff")
        spec, controller, rootfs_gid = _validate(context, handoff)
        resolution = _final_resolution(controller, rootfs_gid)
        policy = _controller_policy(resolution, True)
        artifacts: list[Artifact] = [
            (pending.inventory, render_inventory(spec, context["token"], resolution), 0o600, True),
            (pending.pxe_vars, render_pxe_vars(spec, policy), 0o600, True),
            (pending.values, render_values(spec, resolution), 0o644, False),
            (pending.manifest, _manifest(resolution, True, rootfs_gid), 0o644, False),
        ]
        completion = _completion(context, handoff, _artifact_attestations(artifacts))
        if os.path.lexists(pending.completion):
            if _read_document(pending.completion, "PXE finalizer completion") != completion:
                raise FinalizationError("PXE finalizer completion does not match the supplied handoff")
            _verify_canonical_artifacts(pending, completion["artifacts"])
            return
        published: list[Artifact] = [
            *artifacts,
            (pending.completion, json.dumps(completion, sort_keys=True) + "\n", 0o600, True),
        ]
        preflight_destinations([path for path, _, _, _ in published], False)
        publish_artifacts(published, False)


def _controller_policy(resolution: FleetResolution, rootfs_enabled: bool) -> ResolvedGpuPolicy:
    return ResolvedGpuPolicy(
        host_gpu_enabled={host.target.name: host.status is HostStatus.GPU for host in resolution.hosts},
        render_gid=resolution.render_gid,
        pxe_gpu_enabled=rootfs_enabled,
    )


def _manifest(resolution: FleetResolution, rootfs_enabled: bool, rootfs_gid: int | None) -> str:
    base = resolution_manifest(resolution)
    document = build_pxe_resolution_manifest(
        version=base["version"],
        status=base["status"],
        render_gid=base["render_gid"],
        hosts=base["hosts"],
        gpu_access_enabled=rootfs_enabled,
        pxe_render_gid=rootfs_gid,
    )
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def _render_bootstrap_inventory(spec: JsonDocument) -> str:
    server = spec["server"]
    return "\n".join(
        [
            "pxe_controller:",
            "  hosts:",
            f"    {server['name']}:",
            f"      ansible_host: {server['ip']}",
            "  vars:",
            "    ansible_port: 22",
            "    ansible_user: root",
            "",
        ]
    )


def _yaml_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
