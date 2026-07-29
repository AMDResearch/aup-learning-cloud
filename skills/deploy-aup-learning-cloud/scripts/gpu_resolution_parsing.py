# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

import re
from dataclasses import dataclass
from pathlib import Path

from config_common import DuplicateJsonKeyError, strict_json_loads
from gpu_resolution_manifest import MANIFEST_VERSION


@dataclass(frozen=True, slots=True)
class GpuInventory:
    hosts: dict[str, bool]


@dataclass(frozen=True, slots=True)
class GpuInventoryHostScalars:
    hosts: dict[str, str]


@dataclass(frozen=True, slots=True)
class GpuResolution:
    status: str
    hosts: dict[str, bool]
    pxe_rootfs_enabled: bool | None


@dataclass(frozen=True, slots=True)
class PxeGpuPolicy:
    enabled: bool


def configured_path(repo: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else repo / path


def parse_gpu_boolean(value: str) -> bool | None:
    normalized = value.strip()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    return None


def yaml_indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def scan_gpu_inventory_host_scalars(text: str) -> tuple[GpuInventoryHostScalars | None, list[str]]:
    host_values: dict[str, list[str]] = {}
    host_names: list[str] = []
    stack: list[tuple[int, str]] = []

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = yaml_indent(line)
        stripped = line.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        path = tuple(key for _, key in stack)
        mapping_match = re.fullmatch(r"(.+?):(?:\s*(.*))?", stripped)
        if not mapping_match:
            continue
        key = mapping_match.group(1).strip("\"'")
        value = (mapping_match.group(2) or "").strip()
        if len(path) == 4 and path[:4] in {
            ("k3s_cluster", "children", "server", "hosts"),
            ("k3s_cluster", "children", "agent", "hosts"),
        }:
            host_names.append(key)
            host_values.setdefault(key, [])
        elif (
            len(path) == 5
            and path[:4]
            in {
                ("k3s_cluster", "children", "server", "hosts"),
                ("k3s_cluster", "children", "agent", "hosts"),
            }
            and key == "auplc_gpu_access_enabled"
        ):
            host_values.setdefault(path[4], []).append(value)
        stack.append((indent, key))

    parse_errors: list[str] = []
    if not host_names:
        parse_errors.append("inventory has no generated k3s server or agent hosts")
    if len(set(host_names)) != len(host_names):
        parse_errors.append("inventory has duplicate generated host names")
    hosts: dict[str, str] = {}
    for host in host_names:
        values = host_values[host]
        if len(values) != 1:
            parse_errors.append(f"inventory host '{host}' must define exactly one auplc_gpu_access_enabled")
            continue
        hosts[host] = values[0]
    if parse_errors:
        return None, parse_errors
    return GpuInventoryHostScalars(hosts=hosts), []


def validate_direct_gpu_inventory(text: str) -> list[str]:
    host_scalars, parse_errors = scan_gpu_inventory_host_scalars(text)
    if host_scalars is None:
        return parse_errors
    for host, value in host_scalars.hosts.items():
        if value not in {"auto", "true", "false"}:
            parse_errors.append(f"inventory host '{host}' has malformed auplc_gpu_access_enabled")
    return parse_errors


def parse_gpu_inventory(text: str) -> tuple[GpuInventory | None, list[str]]:
    host_scalars, parse_errors = scan_gpu_inventory_host_scalars(text)
    if host_scalars is None:
        return None, parse_errors
    hosts: dict[str, bool] = {}
    for host, value in host_scalars.hosts.items():
        enabled = parse_gpu_boolean(value)
        if enabled is None:
            parse_errors.append(f"inventory host '{host}' has malformed auplc_gpu_access_enabled")
            continue
        hosts[host] = enabled
    if parse_errors:
        return None, parse_errors
    return GpuInventory(hosts=hosts), []


def parse_gpu_resolution(text: str, topology: str) -> tuple[GpuResolution | None, list[str]]:
    try:
        document = strict_json_loads(text)
    except DuplicateJsonKeyError as exc:
        return None, [f"GPU resolution manifest is malformed: {exc}"]
    except (TypeError, ValueError) as exc:
        return None, [f"GPU resolution manifest is malformed: {exc}"]
    if type(document) is not dict:
        return None, ["GPU resolution manifest must be a JSON object"]
    expected_keys = {"version", "status", "hosts"}
    if topology == "pxe-diskless":
        expected_keys.add("pxe_rootfs")
    if set(document) != expected_keys:
        return None, ["GPU resolution manifest has an unexpected schema"]
    if type(document["version"]) is not int or document["version"] != MANIFEST_VERSION:
        return None, [f"GPU resolution manifest version must be integer {MANIFEST_VERSION}"]
    status = document["status"]
    if type(status) is not str or status not in {"cpu_only", "gpu_resolved"}:
        return None, ["GPU resolution manifest status must be cpu_only or gpu_resolved"]
    if type(document["hosts"]) is not dict or not document["hosts"]:
        return None, ["GPU resolution manifest hosts must be a non-empty object"]
    if any(
        type(host) is not str or not host or type(enabled) is not bool for host, enabled in document["hosts"].items()
    ):
        return None, ["GPU resolution manifest hosts must map non-empty names to booleans"]
    if topology == "ssh-preinstalled":
        return GpuResolution(status, document["hosts"], None), []
    rootfs = document["pxe_rootfs"]
    if type(rootfs) is not dict or set(rootfs) != {"gpu_access_enabled"}:
        return None, ["GPU resolution manifest pxe_rootfs has an unexpected schema"]
    rootfs_enabled = rootfs["gpu_access_enabled"]
    if type(rootfs_enabled) is not bool:
        return None, ["GPU resolution manifest pxe_rootfs.gpu_access_enabled must be boolean"]
    return GpuResolution(status, document["hosts"], rootfs_enabled), []


def parse_pxe_gpu_policy(text: str) -> tuple[PxeGpuPolicy | None, list[str]]:
    values: dict[str, list[str]] = {"pxe_gpu_access_enabled": []}
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip() or yaml_indent(line) != 0:
            continue
        mapping_match = re.fullmatch(r"(.+?):(?:\s*(.*))?", line.strip())
        if not mapping_match:
            continue
        key = mapping_match.group(1).strip("\"'")
        if key in values:
            values[key].append((mapping_match.group(2) or "").strip())
    parse_errors: list[str] = []
    for key, occurrences in values.items():
        if len(occurrences) != 1:
            parse_errors.append(f"PXE vars must define exactly one {key}")
    if parse_errors:
        return None, parse_errors
    enabled = parse_gpu_boolean(values["pxe_gpu_access_enabled"][0])
    if enabled is None:
        parse_errors.append("PXE vars have malformed pxe_gpu_access_enabled")
    if parse_errors:
        return None, parse_errors
    return PxeGpuPolicy(enabled=enabled), []
