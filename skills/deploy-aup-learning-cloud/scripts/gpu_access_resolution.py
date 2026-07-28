# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

"""Parse read-only host evidence and resolve a safe fleet GPU-access policy."""

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Final

from config_common import DuplicateJsonKeyError, strict_json_loads
from gpu_resolution_manifest import ResolutionManifest, build_resolution_manifest

EVIDENCE_VERSION: Final = 2
MAX_RENDER_GID: Final = 4_294_967_294
CANONICAL_RULE: Final = (
    "# Managed by auplc-installer: AMD GPU device access.\n"
    'KERNEL=="kfd", OWNER="root", GROUP="render", MODE="0660"\n'
    'SUBSYSTEM=="drm", KERNEL=="renderD*", DRIVERS=="amdgpu", OWNER="root", GROUP="render", MODE="0660"\n'
)
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
class FileEvidence:
    stat_success: bool
    content_success: bool
    exists: bool
    regular: bool
    symlink: bool
    content: str


@dataclass(frozen=True, slots=True)
class LegacyRuleEvidence:
    kfd: FileEvidence
    amdgpu: FileEvidence
    rocm_devices: FileEvidence


@dataclass(frozen=True, slots=True)
class HostEvidence:
    target: InventoryTarget
    reachable: bool
    lspci: CommandEvidence
    sysfs: CommandEvidence
    render_group: CommandEvidence
    groups: CommandEvidence
    state: FileEvidence
    rule: FileEvidence
    legacy_rules: LegacyRuleEvidence


@dataclass(frozen=True, slots=True)
class HostResolution:
    target: InventoryTarget
    status: HostStatus
    render_gid: int | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class FleetResolution:
    status: FleetStatus
    hosts: tuple[HostResolution, ...]
    render_gid: int | None
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
        return FleetResolution(FleetStatus.CPU_ONLY, resolutions, None, None)
    gids = {host.render_gid for host in gpu_hosts}
    if len(gids) != 1:
        return _blocked(resolutions, "GPU render GIDs disagree")
    return FleetResolution(FleetStatus.GPU_RESOLVED, resolutions, next(iter(gids)), None)


def resolution_manifest(resolution: FleetResolution) -> ResolutionManifest:
    """Build the public serialized manifest for a resolved fleet."""
    return build_resolution_manifest(
        version=1,
        status=resolution.status.value,
        render_gid=resolution.render_gid,
        hosts={host.target.name: host.status is HostStatus.GPU for host in resolution.hosts},
    )


def _parse_host(raw, field: str) -> HostEvidence:
    _require_mapping(raw, field)
    required = {"host", "reachable", "lspci", "sysfs", "render_group", "groups", "state", "rule", "legacy_rules"}
    if set(raw) != required or type(raw["host"]) is not str or not raw["host"]:
        raise EvidenceParseError(field=field)
    if type(raw["reachable"]) is not bool:
        raise EvidenceParseError(field=f"{field}.reachable")
    return HostEvidence(
        target=InventoryTarget(name=raw["host"]),
        reachable=raw["reachable"],
        lspci=_parse_command(raw["lspci"], f"{field}.lspci"),
        sysfs=_parse_command(raw["sysfs"], f"{field}.sysfs"),
        render_group=_parse_command(raw["render_group"], f"{field}.render_group"),
        groups=_parse_command(raw["groups"], f"{field}.groups"),
        state=_parse_file(raw["state"], f"{field}.state"),
        rule=_parse_file(raw["rule"], f"{field}.rule"),
        legacy_rules=_parse_legacy_rules(raw["legacy_rules"], f"{field}.legacy_rules"),
    )


def _parse_command(raw, field: str) -> CommandEvidence:
    _require_mapping(raw, field)
    if set(raw) != {"rc", "stdout"} or type(raw["rc"]) is not int or type(raw["stdout"]) is not str:
        raise EvidenceParseError(field=field)
    return CommandEvidence(rc=raw["rc"], stdout=raw["stdout"])


def _parse_file(raw, field: str) -> FileEvidence:
    _require_mapping(raw, field)
    required = {"stat_success", "content_success", "exists", "regular", "symlink", "content"}
    if set(raw) != required or any(
        type(raw[key]) is not bool for key in ("stat_success", "content_success", "exists", "regular", "symlink")
    ):
        raise EvidenceParseError(field=field)
    if type(raw["content"]) is not str:
        raise EvidenceParseError(field=f"{field}.content")
    return FileEvidence(**raw)


def _parse_legacy_rules(raw, field: str) -> LegacyRuleEvidence:
    _require_mapping(raw, field)
    if set(raw) != {"kfd", "amdgpu", "rocm_devices"}:
        raise EvidenceParseError(field=field)
    return LegacyRuleEvidence(
        kfd=_parse_file(raw["kfd"], f"{field}.kfd"),
        amdgpu=_parse_file(raw["amdgpu"], f"{field}.amdgpu"),
        rocm_devices=_parse_file(raw["rocm_devices"], f"{field}.rocm_devices"),
    )


def _require_mapping(value, field: str) -> None:
    if type(value) is not dict:
        raise EvidenceParseError(field=field)


def _resolve_host(evidence: HostEvidence) -> HostResolution:
    if not evidence.reachable or evidence.lspci.rc != 0 or evidence.sysfs.rc != 0:
        return _unknown(evidence, "GPU discovery probe failed")
    if not _file_probes_succeeded(evidence):
        return _unknown(evidence, "GPU access file probe failed")
    lspci_bdfs = _bdfs(evidence.lspci.stdout)
    sysfs_bdfs = _bdfs(evidence.sysfs.stdout)
    if lspci_bdfs is None or sysfs_bdfs is None or lspci_bdfs != sysfs_bdfs:
        return _unknown(evidence, "AMD GPU BDF probes disagree")
    if not lspci_bdfs:
        if evidence.state.exists or evidence.rule.exists or _legacy_rule_exists(evidence.legacy_rules):
            return _unknown(evidence, "CPU host retains GPU access contract")
        return HostResolution(evidence.target, HostStatus.CPU, None, None)
    render_gid = _render_gid(evidence)
    if render_gid is None or not _safe_gpu_files(evidence, render_gid):
        return _unknown(evidence, "GPU access contract is unsafe")
    return HostResolution(evidence.target, HostStatus.GPU, render_gid, None)


def _bdfs(stdout: str) -> frozenset[str] | None:
    bdfs = frozenset(line.split(maxsplit=1)[0] for line in stdout.splitlines())
    if all(BDF_PATTERN.fullmatch(bdf) for bdf in bdfs):
        return bdfs
    return None


def _render_gid(evidence: HostEvidence) -> int | None:
    if evidence.render_group.rc != 0 or evidence.groups.rc != 0:
        return None
    record = _group_record(evidence.render_group.stdout)
    if record is None or record[0] != "render":
        return None
    gid = record[1]
    groups = tuple(_group_record(line) for line in evidence.groups.stdout.splitlines())
    if not groups or any(group is None for group in groups):
        return None
    if sum(group[0] == "render" and group[1] == gid for group in groups) != 1:
        return None
    if any(group[0] != "render" and group[1] == gid for group in groups):
        return None
    return gid


def _group_record(record: str) -> tuple[str, int] | None:
    fields = record.split(":")
    if len(fields) != 4 or not fields[0] or not fields[2].isascii() or not fields[2].isdecimal():
        return None
    gid = int(fields[2])
    if 1 <= gid <= MAX_RENDER_GID:
        return fields[0], gid
    return None


def _safe_gpu_files(evidence: HostEvidence, render_gid: int) -> bool:
    if not _safe_file(evidence.state) or not _safe_file(evidence.rule):
        return False
    if evidence.state.exists and _state_gid(evidence.state.content) != render_gid:
        return False
    return not evidence.rule.exists or evidence.rule.content == CANONICAL_RULE


def _safe_file(evidence: FileEvidence) -> bool:
    if not evidence.stat_success or not evidence.content_success:
        return False
    if evidence.exists:
        return evidence.regular and not evidence.symlink
    return not evidence.regular and not evidence.symlink and not evidence.content


def _file_probes_succeeded(evidence: HostEvidence) -> bool:
    return all(
        file_evidence.stat_success and file_evidence.content_success
        for file_evidence in (
            evidence.state,
            evidence.rule,
            evidence.legacy_rules.kfd,
            evidence.legacy_rules.amdgpu,
            evidence.legacy_rules.rocm_devices,
        )
    )


def _legacy_rule_exists(evidence: LegacyRuleEvidence) -> bool:
    return any(file_evidence.exists for file_evidence in (evidence.kfd, evidence.amdgpu, evidence.rocm_devices))


def _state_gid(raw: str) -> int | None:
    try:
        state = strict_json_loads(raw)
    except (DuplicateJsonKeyError, TypeError, json.JSONDecodeError):
        return None
    if type(state) is not dict or set(state) != {"renderGid", "version"}:
        return None
    gid = state["renderGid"]
    if type(gid) is not int or type(state["version"]) is not int or state["version"] != 1:
        return None
    return gid if 1 <= gid <= MAX_RENDER_GID else None


def _unknown(evidence: HostEvidence, reason: str) -> HostResolution:
    return HostResolution(evidence.target, HostStatus.UNKNOWN, None, reason)


def _blocked(hosts: tuple[HostResolution, ...], reason: str) -> FleetResolution:
    return FleetResolution(FleetStatus.BLOCKED, hosts, None, reason)
