#!/usr/bin/env python3
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
"""Typed security and verification support for PXE finalization."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypeAlias, TypedDict

from config_common import DuplicateJsonKeyError, strict_json_loads
from gpu_access_resolution import FleetResolution, FleetStatus, HostResolution, HostStatus, InventoryTarget

VERSION: Final = 1
MAX_RENDER_GID: Final = 4_294_967_294

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonDocument: TypeAlias = dict[str, JsonValue]
Artifact: TypeAlias = tuple[Path, str, int, bool]


class ArtifactAttestation(TypedDict):
    sha256: str
    mode: int
    owner_uid: int


ArtifactAttestations: TypeAlias = dict[str, ArtifactAttestation]


@dataclass(frozen=True, slots=True)
class FinalizationError(Exception):
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class PxePaths:
    bootstrap_inventory: Path
    bootstrap_vars: Path
    context: Path
    handoff: Path
    completion: Path
    lock: Path
    inventory: Path
    pxe_vars: Path
    values: Path
    manifest: Path


def paths(out_dir: Path) -> PxePaths:
    root = out_dir.resolve()
    return PxePaths(
        bootstrap_inventory=root / ".pxe-bootstrap.inventory.yml",
        bootstrap_vars=root / ".pxe-bootstrap.vars.yml",
        context=root / ".pxe-finalizer-context.json",
        handoff=root / ".pxe-finalizer-handoff.json",
        completion=root / ".pxe-finalizer-completion.json",
        lock=root / ".pxe-finalizer.lock",
        inventory=root / "inventory.yml",
        pxe_vars=root / "pb-pxe-controller.vars.yml",
        values=root / "values-basic-example.yaml",
        manifest=root / "gpu-access-resolution.json",
    )


def spec_sha256(spec: JsonDocument) -> str:
    encoded = json.dumps(spec, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def valid_gid(value: JsonValue) -> bool:
    return type(value) is int and 1 <= value <= MAX_RENDER_GID


def read_document(path: Path, label: str) -> JsonDocument:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        with os.fdopen(descriptor, encoding="utf-8") as source:
            mode = os.fstat(source.fileno()).st_mode
            if not stat.S_ISREG(mode):
                raise FinalizationError(f"{label} must be a regular file")
            document = strict_json_loads(source.read())
    except FinalizationError:
        raise
    except (DuplicateJsonKeyError, FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as error:
        raise FinalizationError(f"{label} cannot be read") from error
    if type(document) is not dict:
        raise FinalizationError(f"{label} must be a JSON object")
    return document


def validate(context: JsonDocument, handoff: JsonDocument) -> tuple[JsonDocument, FleetResolution, int]:
    required_context = {"version", "generation", "spec_sha256", "topology", "spec", "token", "controller"}
    required_handoff = {"version", "generation", "spec_sha256", "topology", "pxe_gpu_access_enabled", "render_gid"}
    if set(context) != required_context or set(handoff) != required_handoff:
        raise FinalizationError("PXE finalizer context or handoff has an unexpected schema")
    if type(context["version"]) is not int or type(handoff["version"]) is not int:
        raise FinalizationError("PXE finalizer context or handoff version is invalid")
    if context["version"] != VERSION or handoff["version"] != VERSION:
        raise FinalizationError("PXE finalizer context or handoff version is unsupported")
    if context["topology"] != "pxe-diskless" or handoff["topology"] != "pxe-diskless":
        raise FinalizationError("PXE finalizer topology is invalid")
    generation = context["generation"]
    if type(generation) is not str or not generation or handoff["generation"] != generation:
        raise FinalizationError("PXE finalizer generation does not match")
    spec = context["spec"]
    if type(spec) is not dict or spec_sha256(spec) != context["spec_sha256"]:
        raise FinalizationError("PXE finalizer context spec does not match its digest")
    if handoff["spec_sha256"] != context["spec_sha256"] or spec.get("topology") != "pxe-diskless":
        raise FinalizationError("PXE finalizer handoff does not match its pending spec")
    if "render_gid" in spec or "gpu_access" in spec:
        raise FinalizationError("PXE finalizer context contains removed public GPU policy fields")
    if type(context["token"]) is not str or not context["token"]:
        raise FinalizationError("PXE finalizer context token is invalid")
    pxe = spec.get("pxe")
    if type(pxe) is not dict or pxe.get("diskless_agents_have_amd_gpus") is not True:
        raise FinalizationError("PXE finalizer context is not for GPU-enabled diskless agents")
    rootfs_gid = handoff["render_gid"]
    if handoff["pxe_gpu_access_enabled"] is not True or not valid_gid(rootfs_gid):
        raise FinalizationError("PXE finalizer handoff has no valid resolved rootfs GID")
    controller = controller_resolution(spec, context["controller"])
    if controller.render_gid is not None and controller.render_gid != rootfs_gid:
        raise FinalizationError("PXE rootfs render GID disagrees with the GPU-enabled controller")
    return spec, controller, rootfs_gid


def controller_resolution(spec: JsonDocument, raw: JsonValue) -> FleetResolution:
    if type(raw) is not dict or set(raw) != {"version", "status", "render_gid", "hosts"}:
        raise FinalizationError("PXE finalizer context controller evidence is invalid")
    server = spec.get("server")
    name = server.get("name") if type(server) is dict else None
    hosts = raw["hosts"]
    if type(name) is not str or type(hosts) is not dict or set(hosts) != {name} or type(hosts[name]) is not bool:
        raise FinalizationError("PXE finalizer context controller host is invalid")
    enabled = hosts[name]
    gid = raw["render_gid"]
    if enabled and not valid_gid(gid):
        raise FinalizationError("PXE finalizer context controller GID is invalid")
    if not enabled and gid is not None:
        raise FinalizationError("CPU-only PXE controller must not publish a render GID")
    status = HostStatus.GPU if enabled else HostStatus.CPU
    fleet_status = FleetStatus.GPU_RESOLVED if enabled else FleetStatus.CPU_ONLY
    if type(raw["version"]) is not int or raw["version"] != VERSION or raw["status"] != fleet_status.value:
        raise FinalizationError("PXE finalizer context controller status is invalid")
    host = HostResolution(target=target(name), status=status, render_gid=gid, reason=None)
    return FleetResolution(fleet_status, (host,), gid, None)


def target(name: str) -> InventoryTarget:
    return InventoryTarget(name=name)


def final_resolution(controller: FleetResolution, rootfs_gid: int) -> FleetResolution:
    return FleetResolution(FleetStatus.GPU_RESOLVED, controller.hosts, rootfs_gid, None)


def generation_paths(pending: PxePaths) -> tuple[Path, ...]:
    return (
        pending.bootstrap_inventory,
        pending.bootstrap_vars,
        pending.context,
        pending.handoff,
        pending.completion,
        pending.inventory,
        pending.pxe_vars,
        pending.values,
        pending.manifest,
    )


def artifact_attestations(artifacts: list[Artifact]) -> ArtifactAttestations:
    return {
        path.name: {"sha256": hashlib.sha256(content.encode()).hexdigest(), "mode": mode, "owner_uid": os.geteuid()}
        for path, content, mode, _ in artifacts
    }


def verify_canonical_artifacts(pending: PxePaths, expected: JsonValue) -> None:
    canonical = (pending.inventory, pending.pxe_vars, pending.values, pending.manifest)
    if type(expected) is not dict or set(expected) != {path.name for path in canonical}:
        raise FinalizationError("PXE finalizer completion artifacts are invalid")
    for path in canonical:
        attestation = expected[path.name]
        if (
            type(attestation) is not dict
            or set(attestation) != {"sha256", "mode", "owner_uid"}
            or type(attestation["sha256"]) is not str
            or type(attestation["mode"]) is not int
            or type(attestation["owner_uid"]) is not int
            or read_artifact_attestation(path) != attestation
        ):
            raise FinalizationError(f"PXE finalizer canonical artifact is missing or corrupted: {path.name}")


def read_artifact_attestation(path: Path) -> ArtifactAttestation:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        with os.fdopen(descriptor, "rb") as source:
            artifact_stat = os.fstat(source.fileno())
            if not stat.S_ISREG(artifact_stat.st_mode):
                raise FinalizationError("PXE finalizer canonical artifact must be a regular file")
            digest = hashlib.sha256()
            while chunk := source.read(65_536):
                digest.update(chunk)
            return {
                "sha256": digest.hexdigest(),
                "mode": stat.S_IMODE(artifact_stat.st_mode),
                "owner_uid": artifact_stat.st_uid,
            }
    except FinalizationError:
        raise
    except (FileNotFoundError, OSError) as error:
        raise FinalizationError("PXE finalizer canonical artifact cannot be read") from error


def completion(context: JsonDocument, handoff: JsonDocument, artifacts: ArtifactAttestations) -> JsonDocument:
    return {
        **{
            key: handoff[key]
            for key in ("version", "generation", "spec_sha256", "topology", "pxe_gpu_access_enabled", "render_gid")
        },
        "artifacts": artifacts,
    }


@contextmanager
def exclusive_lock(path: Path) -> Iterator[None]:
    descriptor = -1
    locked = False
    try:
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600)
        lock_stat = os.fstat(descriptor)
        if not stat.S_ISREG(lock_stat.st_mode):
            raise FinalizationError("PXE finalizer lock must be a regular file")
        if lock_stat.st_uid != os.geteuid() or stat.S_IMODE(lock_stat.st_mode) != 0o600:
            raise FinalizationError("PXE finalizer lock has unsafe owner or mode")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        locked = True
        yield
    except OSError as error:
        raise FinalizationError("PXE finalizer lock cannot be opened") from error
    finally:
        if locked:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        if descriptor >= 0:
            os.close(descriptor)
