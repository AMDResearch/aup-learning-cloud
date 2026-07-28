# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

import re
from dataclasses import dataclass
from pathlib import Path

from config_common import DuplicateJsonKeyError, strict_json_loads

MAX_RENDER_GID = 4_294_967_294


@dataclass(frozen=True, slots=True)
class GpuInventory:
    hosts: dict[str, bool]
    render_gid: int | None


@dataclass(frozen=True, slots=True)
class GpuResolution:
    status: str
    hosts: dict[str, bool]
    render_gid: int | None
    pxe_rootfs_enabled: bool | None
    pxe_rootfs_gid: int | None


@dataclass(frozen=True, slots=True)
class PxeGpuPolicy:
    enabled: bool
    render_gid: int | None


def configured_path(repo: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else repo / path


def parse_gpu_gid(value: str) -> int | None | str:
    normalized = value.strip()
    if normalized in {"null", "~"}:
        return None
    if normalized.isascii() and normalized.isdecimal():
        gid = int(normalized)
        if 1 <= gid <= MAX_RENDER_GID:
            return gid
    return "invalid"


def parse_gpu_boolean(value: str) -> bool | None:
    normalized = value.strip()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    return None


def yaml_indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def parse_gpu_inventory(text: str) -> tuple[GpuInventory | None, list[str]]:
    host_values: dict[str, list[str]] = {}
    host_names: list[str] = []
    render_gids: list[str] = []
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
        elif path == ("k3s_cluster", "vars") and key == "auplc_render_gid":
            render_gids.append(value)
        stack.append((indent, key))

    parse_errors: list[str] = []
    if not host_names:
        parse_errors.append("inventory has no generated k3s server or agent hosts")
    if len(set(host_names)) != len(host_names):
        parse_errors.append("inventory has duplicate generated host names")
    hosts: dict[str, bool] = {}
    for host in host_names:
        values = host_values[host]
        if len(values) != 1:
            parse_errors.append(f"inventory host '{host}' must define exactly one auplc_gpu_access_enabled")
            continue
        enabled = parse_gpu_boolean(values[0])
        if enabled is None:
            parse_errors.append(f"inventory host '{host}' has malformed auplc_gpu_access_enabled")
            continue
        hosts[host] = enabled
    if len(render_gids) != 1:
        parse_errors.append("inventory must define exactly one k3s_cluster.vars.auplc_render_gid")
        return None, parse_errors
    render_gid = parse_gpu_gid(render_gids[0])
    if render_gid == "invalid":
        parse_errors.append("inventory has malformed auplc_render_gid")
        return None, parse_errors
    if parse_errors:
        return None, parse_errors
    return GpuInventory(hosts=hosts, render_gid=render_gid), parse_errors


def parse_values_gpu_gid(text: str) -> tuple[int | None, bool, list[str]]:
    render_gids: list[str] = []
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
        if path == ("custom", "gpuAccess") and key == "renderGid":
            render_gids.append(value)
        stack.append((indent, key))
    if not render_gids:
        return None, False, []
    if len(render_gids) != 1:
        return None, True, ["custom.gpuAccess.renderGid is duplicated"]
    render_gid = parse_gpu_gid(render_gids[0])
    if render_gid == "invalid":
        return None, True, ["custom.gpuAccess.renderGid is malformed"]
    return render_gid, True, []


def collect_effective_gpu_gid(repo: Path, values: list[str]) -> tuple[int | None, list[str]]:
    effective_gid: int | None = None
    found = False
    parse_errors: list[str] = []
    for rel in values or ["runtime/values.yaml"]:
        path = configured_path(repo, rel)
        if not path.exists():
            continue
        render_gid, present, file_errors = parse_values_gpu_gid(path.read_text(encoding="utf-8"))
        parse_errors.extend(f"{path}: {error}" for error in file_errors)
        if present and not file_errors:
            effective_gid = render_gid
            found = True
    if not found:
        parse_errors.append("effective values have no custom.gpuAccess.renderGid")
    return effective_gid, parse_errors


def parse_gpu_resolution(text: str, topology: str) -> tuple[GpuResolution | None, list[str]]:
    try:
        document = strict_json_loads(text)
    except DuplicateJsonKeyError as exc:
        return None, [f"GPU resolution manifest is malformed: {exc}"]
    except (TypeError, ValueError) as exc:
        return None, [f"GPU resolution manifest is malformed: {exc}"]
    if type(document) is not dict:
        return None, ["GPU resolution manifest must be a JSON object"]
    expected_keys = {"version", "status", "render_gid", "hosts"}
    if topology == "pxe-diskless":
        expected_keys.add("pxe_rootfs")
    if set(document) != expected_keys:
        return None, ["GPU resolution manifest has an unexpected schema"]
    if type(document["version"]) is not int or document["version"] != 1:
        return None, ["GPU resolution manifest version must be integer 1"]
    status = document["status"]
    if type(status) is not str or status not in {"cpu_only", "gpu_resolved"}:
        return None, ["GPU resolution manifest status must be cpu_only or gpu_resolved"]
    if type(document["hosts"]) is not dict or not document["hosts"]:
        return None, ["GPU resolution manifest hosts must be a non-empty object"]
    if any(
        type(host) is not str or not host or type(enabled) is not bool for host, enabled in document["hosts"].items()
    ):
        return None, ["GPU resolution manifest hosts must map non-empty names to booleans"]
    render_gid = document["render_gid"]
    if render_gid is not None and (type(render_gid) is not int or not 1 <= render_gid <= MAX_RENDER_GID):
        return None, ["GPU resolution manifest render_gid must be an integer or null"]
    if topology == "ssh-preinstalled":
        return GpuResolution(status, document["hosts"], render_gid, None, None), []
    rootfs = document["pxe_rootfs"]
    if type(rootfs) is not dict or set(rootfs) != {"gpu_access_enabled", "render_gid"}:
        return None, ["GPU resolution manifest pxe_rootfs has an unexpected schema"]
    rootfs_enabled = rootfs["gpu_access_enabled"]
    rootfs_gid = rootfs["render_gid"]
    if type(rootfs_enabled) is not bool:
        return None, ["GPU resolution manifest pxe_rootfs.gpu_access_enabled must be boolean"]
    if rootfs_gid is not None and (type(rootfs_gid) is not int or not 1 <= rootfs_gid <= MAX_RENDER_GID):
        return None, ["GPU resolution manifest pxe_rootfs.render_gid must be an integer or null"]
    return GpuResolution(status, document["hosts"], render_gid, rootfs_enabled, rootfs_gid), []


def parse_pxe_gpu_policy(text: str) -> tuple[PxeGpuPolicy | None, list[str]]:
    values: dict[str, list[str]] = {"auplc_render_gid": [], "pxe_gpu_access_enabled": []}
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
    render_gid = parse_gpu_gid(values["auplc_render_gid"][0])
    enabled = parse_gpu_boolean(values["pxe_gpu_access_enabled"][0])
    if render_gid == "invalid":
        parse_errors.append("PXE vars have malformed auplc_render_gid")
    if enabled is None:
        parse_errors.append("PXE vars have malformed pxe_gpu_access_enabled")
    if parse_errors:
        return None, parse_errors
    return PxeGpuPolicy(enabled=enabled, render_gid=render_gid), []
