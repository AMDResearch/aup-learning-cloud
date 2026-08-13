# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

"""Parse read-only host evidence and resolve a safe fleet GPU-access policy."""

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Final

from config_common import DuplicateJsonKeyError, strict_json_loads
from gpu_resolution_manifest import ResolutionManifest, build_resolution_manifest

EVIDENCE_VERSION: Final = 1
BDF_PATTERN: Final = re.compile(r"[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]")


class HostStatus(str, Enum):
    """Classify one inventory host from mutually corroborated discovery probes."""

    GPU = "gpu"
    CPU = "cpu"
    UNKNOWN = "unknown"


class FleetStatus(str, Enum):
    """Describe whether fleet evidence yields a publication-safe GPU policy."""

    GPU_RESOLVED = "gpu_resolved"
    CPU_ONLY = "cpu_only"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class EvidenceParseError(ValueError):
    """Raised when discovery JSON does not match the fixed evidence schema."""

    field: str

    def __str__(self) -> str:
        return f"Malformed GPU-access discovery evidence at {self.field}"


@dataclass(frozen=True, slots=True)
class InventoryTarget:
    name: str


@dataclass(frozen=True, slots=True)
class CommandEvidence:
    rc: int
    stdout: str


@dataclass(frozen=True, slots=True)
class HostEvidence:
    target: InventoryTarget
    reachable: bool
    lspci: CommandEvidence
    sysfs: CommandEvidence


@dataclass(frozen=True, slots=True)
class HostResolution:
    target: InventoryTarget
    status: HostStatus
    reason: str | None


@dataclass(frozen=True, slots=True)
class FleetResolution:
    status: FleetStatus
    hosts: tuple[HostResolution, ...]
    reason: str | None


def parse_fleet_evidence(raw: str) -> tuple[HostEvidence, ...]:
    """Parse the exact JSON emitted by the GPU-access discovery playbook."""
    try:
        document = strict_json_loads(raw)
    except DuplicateJsonKeyError as error:
        raise EvidenceParseError(field=str(error)) from error
    except (TypeError, json.JSONDecodeError) as error:
        raise EvidenceParseError(field="document") from error
    _require_mapping(document, "document")
    if set(document) != {"version", "hosts"}:
        raise EvidenceParseError(field="document")
    if type(document["version"]) is not int or document["version"] != EVIDENCE_VERSION:
        raise EvidenceParseError(field="version")
    if type(document["hosts"]) is not list:
        raise EvidenceParseError(field="hosts")
    return tuple(_parse_host(item, f"hosts[{index}]") for index, item in enumerate(document["hosts"]))


def resolve_fleet(expected_targets: tuple[InventoryTarget, ...], evidence: tuple[HostEvidence, ...]) -> FleetResolution:
    """Resolve a fleet only when complete evidence proves one safe policy."""
    resolutions = tuple(_resolve_host(host) for host in evidence)
    expected_names = tuple(target.name for target in expected_targets)
    actual_names = tuple(host.target.name for host in evidence)
    if len(set(expected_names)) != len(expected_names) or len(set(actual_names)) != len(actual_names):
        return _blocked(resolutions, "duplicate host")
    if set(expected_names) != set(actual_names):
        return _blocked(resolutions, "incomplete host coverage")
    if any(host.status is HostStatus.UNKNOWN for host in resolutions):
        return _blocked(resolutions, "unknown host evidence")
    gpu_hosts = tuple(host for host in resolutions if host.status is HostStatus.GPU)
    if not gpu_hosts:
        return FleetResolution(FleetStatus.CPU_ONLY, resolutions, None)
    return FleetResolution(FleetStatus.GPU_RESOLVED, resolutions, None)


def resolution_manifest(resolution: FleetResolution) -> ResolutionManifest:
    """Build the public serialized manifest for a resolved fleet."""
    return build_resolution_manifest(
        status=resolution.status.value,
        hosts={host.target.name: host.status is HostStatus.GPU for host in resolution.hosts},
    )


def _parse_host(raw, field: str) -> HostEvidence:
    _require_mapping(raw, field)
    required = {"host", "reachable", "lspci", "sysfs"}
    if set(raw) != required or type(raw["host"]) is not str or not raw["host"]:
        raise EvidenceParseError(field=field)
    if type(raw["reachable"]) is not bool:
        raise EvidenceParseError(field=f"{field}.reachable")
    return HostEvidence(
        target=InventoryTarget(name=raw["host"]),
        reachable=raw["reachable"],
        lspci=_parse_command(raw["lspci"], f"{field}.lspci"),
        sysfs=_parse_command(raw["sysfs"], f"{field}.sysfs"),
    )


def _parse_command(raw, field: str) -> CommandEvidence:
    _require_mapping(raw, field)
    if set(raw) != {"rc", "stdout"} or type(raw["rc"]) is not int or type(raw["stdout"]) is not str:
        raise EvidenceParseError(field=field)
    return CommandEvidence(rc=raw["rc"], stdout=raw["stdout"])


def _require_mapping(value, field: str) -> None:
    if type(value) is not dict:
        raise EvidenceParseError(field=field)


def _resolve_host(evidence: HostEvidence) -> HostResolution:
    if not evidence.reachable or evidence.lspci.rc != 0 or evidence.sysfs.rc != 0:
        return _unknown(evidence, "GPU discovery probe failed")
    lspci_bdfs = _bdfs(evidence.lspci.stdout)
    sysfs_bdfs = _bdfs(evidence.sysfs.stdout)
    if lspci_bdfs is None or sysfs_bdfs is None or lspci_bdfs != sysfs_bdfs:
        return _unknown(evidence, "AMD GPU BDF probes disagree")
    if not lspci_bdfs:
        return HostResolution(evidence.target, HostStatus.CPU, None)
    return HostResolution(evidence.target, HostStatus.GPU, None)


def _bdfs(stdout: str) -> frozenset[str] | None:
    bdfs = frozenset(line.split(maxsplit=1)[0] for line in stdout.splitlines())
    if all(BDF_PATTERN.fullmatch(bdf) for bdf in bdfs):
        return bdfs
    return None


def _unknown(evidence: HostEvidence, reason: str) -> HostResolution:
    return HostResolution(evidence.target, HostStatus.UNKNOWN, reason)


def _blocked(hosts: tuple[HostResolution, ...], reason: str) -> FleetResolution:
    return FleetResolution(FleetStatus.BLOCKED, hosts, reason)
