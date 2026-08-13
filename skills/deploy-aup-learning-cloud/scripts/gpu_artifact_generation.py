#!/usr/bin/env python3
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
"""Discover live GPU facts and prepare publication-safe resolved artifacts."""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from artifact_store import publish_artifacts
from config_common import yaml_quote
from config_generation import HEADER_HASH
from gpu_access_resolution import (
    EvidenceParseError,
    FleetResolution,
    FleetStatus,
    InventoryTarget,
    parse_fleet_evidence,
    resolution_manifest,
    resolve_fleet,
)
from gpu_resolution_manifest import build_pxe_resolution_manifest

DISCOVERY_TIMEOUT_BASE_SECONDS = 30
DISCOVERY_TIMEOUT_PER_TARGET_SECONDS = 15
DISCOVERY_TIMEOUT_MAX_SECONDS = 300
DISCOVERY_DIAGNOSTIC_MAX_CHARS = 1200


def assert_never(value: FleetStatus) -> NoReturn:
    raise AssertionError(f"unexpected fleet status: {value}")


@dataclass(frozen=True, slots=True)
class DiscoveryFailure(Exception):
    reason: str

    def __str__(self) -> str:
        return self.reason


@dataclass(frozen=True, slots=True)
class DiscoveryPaths:
    inventory: Path
    evidence: Path


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    resolution: FleetResolution


def canonical_paths(out_dir: Path) -> tuple[Path, Path, Path]:
    return (
        out_dir / "inventory.yml",
        out_dir / "values-basic-example.yaml",
        out_dir / "gpu-access-resolution.json",
    )


def discover_gpu_policy(spec: dict, out_dir: Path) -> DiscoveryResult:
    targets = live_targets(spec)
    paths = stage_private_discovery(spec, out_dir)
    run_discovery(paths, len(targets))
    try:
        evidence = parse_fleet_evidence(read_regular_file(paths.evidence))
    except EvidenceParseError as error:
        raise DiscoveryFailure("GPU discovery evidence is malformed") from error
    resolution = resolve_fleet(targets, evidence)
    match resolution.status:
        case FleetStatus.BLOCKED:
            raise DiscoveryFailure(f"GPU discovery is blocked: {resolution.reason}")
        case FleetStatus.GPU_RESOLVED | FleetStatus.CPU_ONLY:
            pass
        case unreachable:
            assert_never(unreachable)
    return DiscoveryResult(resolution=resolution)


def live_targets(spec: dict) -> tuple[InventoryTarget, ...]:
    names = [spec["server"]["name"]]
    if spec["topology"] == "ssh-preinstalled":
        names.extend(agent["name"] for agent in spec.get("agents", []))
    if len(names) != len(set(names)):
        raise DiscoveryFailure("live target names must be unique")
    return tuple(InventoryTarget(name=name) for name in names)


def stage_private_discovery(spec: dict, out_dir: Path) -> DiscoveryPaths:
    resolved_out_dir = out_dir.resolve()
    paths = DiscoveryPaths(
        inventory=resolved_out_dir / ".gpu-access-discovery.inventory.yml",
        evidence=resolved_out_dir / ".gpu-access-discovery-evidence.json",
    )
    publish_artifacts(
        [
            (paths.inventory, render_discovery_inventory(spec), 0o600, False),
            (paths.evidence, "", 0o600, False),
        ],
        force=True,
    )
    return paths


def render_discovery_inventory(spec: dict) -> str:
    server = spec["server"]
    lines = [
        HEADER_HASH,
        "k3s_cluster:",
        "  children:",
        "    server:",
        "      hosts:",
        f"        {server['name']}:",
        f"          ansible_host: {yaml_quote(server['ip'])}",
        "    agent:",
    ]
    if spec["topology"] == "ssh-preinstalled" and spec.get("agents"):
        lines.append("      hosts:")
        for agent in spec["agents"]:
            lines += [f"        {agent['name']}:", f"          ansible_host: {yaml_quote(agent['ip'])}"]
    else:
        lines.append("      hosts: {}")
    lines += ["  vars:", "    ansible_port: 22", "    ansible_user: root"]
    return "\n".join(lines) + "\n"


def discovery_timeout_seconds(target_count: int) -> int:
    configured = os.environ.get("AUPLC_GPU_DISCOVERY_TIMEOUT_SECONDS")
    if configured is not None:
        try:
            timeout = int(configured)
        except ValueError as error:
            raise DiscoveryFailure("AUPLC_GPU_DISCOVERY_TIMEOUT_SECONDS must be an integer") from error
        if not DISCOVERY_TIMEOUT_BASE_SECONDS <= timeout <= DISCOVERY_TIMEOUT_MAX_SECONDS:
            raise DiscoveryFailure(
                f"AUPLC_GPU_DISCOVERY_TIMEOUT_SECONDS must be between {DISCOVERY_TIMEOUT_BASE_SECONDS} and "
                f"{DISCOVERY_TIMEOUT_MAX_SECONDS}"
            )
        return timeout
    return min(
        DISCOVERY_TIMEOUT_MAX_SECONDS,
        DISCOVERY_TIMEOUT_BASE_SECONDS + (DISCOVERY_TIMEOUT_PER_TARGET_SECONDS * target_count),
    )


def _bounded_diagnostic(*values: str | bytes | None) -> str:
    text = "\n".join(value.decode(errors="replace") if isinstance(value, bytes) else value or "" for value in values)
    text = re.sub(r"(?i)\b(token|password|secret|private[_-]?key)\s*[:=]\s*\S+", r"\1=<redacted>", text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    summary = " | ".join(lines[-8:])
    return summary[-DISCOVERY_DIAGNOSTIC_MAX_CHARS:] or "no Ansible diagnostics"


def run_discovery(paths: DiscoveryPaths, target_count: int) -> None:
    playbook = Path(__file__).resolve().parents[3] / "deploy" / "ansible" / "playbooks" / "pb-gpu-access-discovery.yml"
    argv = [
        "ansible-playbook",
        "-i",
        str(paths.inventory),
        str(playbook),
        "-e",
        f"gpu_access_discovery_output_path={paths.evidence}",
    ]
    environment = os.environ.copy()
    environment["ANSIBLE_CONFIG"] = str(playbook.parents[1] / "ansible.cfg")
    environment["ANSIBLE_HOST_KEY_CHECKING"] = "True"
    environment["ANSIBLE_SSH_HOST_KEY_CHECKING"] = "True"
    environment["ANSIBLE_SSH_ARGS"] = "-o StrictHostKeyChecking=yes"
    for key in (
        "ANSIBLE_SSH_COMMON_ARGS",
        "ANSIBLE_SSH_EXTRA_ARGS",
        "ANSIBLE_SCP_IF_SSH",
        "ANSIBLE_SCP_EXTRA_ARGS",
        "ANSIBLE_SFTP_EXTRA_ARGS",
    ):
        environment.pop(key, None)
    timeout = discovery_timeout_seconds(target_count)
    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            check=False,
            cwd=playbook.parents[1],
            env=environment,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as error:
        raise DiscoveryFailure("ansible-playbook is required for GPU discovery") from error
    except subprocess.TimeoutExpired as error:
        diagnostic = _bounded_diagnostic(error.stderr, error.stdout)
        raise DiscoveryFailure(f"GPU discovery playbook timed out after {timeout}s: {diagnostic}") from error
    if result.returncode != 0:
        diagnostic = _bounded_diagnostic(result.stderr, result.stdout)
        raise DiscoveryFailure(f"GPU discovery playbook failed with exit code {result.returncode}: {diagnostic}")


def read_regular_file(path: Path) -> str:
    try:
        mode = os.lstat(path).st_mode
    except FileNotFoundError as error:
        raise DiscoveryFailure("GPU discovery evidence was not written") from error
    if not stat.S_ISREG(mode):
        raise DiscoveryFailure("GPU discovery evidence must be a regular file")
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise DiscoveryFailure("GPU discovery evidence could not be read") from error


def manifest_content(result: DiscoveryResult, pxe_gpu_access_enabled: bool | None = None) -> str:
    base = resolution_manifest(result.resolution)
    document = (
        base
        if pxe_gpu_access_enabled is None
        else build_pxe_resolution_manifest(
            base,
            gpu_access_enabled=pxe_gpu_access_enabled,
        )
    )
    return json.dumps(document, indent=2, sort_keys=True) + "\n"
