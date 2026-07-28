#!/usr/bin/env python3
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
"""Pre-flight validation for an AUP Learning Cloud deploy.

Catches the mistakes that otherwise surface only after a long playbook or a
failed spawn:

  * required PXE vars empty (PXE topology only: interface / subnet /
    controller_ip / dns / k3s_server_ips / at least one authorized key);
  * the k3s server version and the PXE agent rootfs version disagree (PXE
    topology only; agents must not be newer than the server);
  * nodeSelectors for the accelerators actually referenced by effective
    custom.resources.metadata.*.acceleratorKeys, checked against
    detect_cluster.sh output when supplied;
   * direct inventory GPU access booleans are valid, or generated inventory,
     GPU-resolution manifest, and PXE rootfs policy agree when both artifacts
     are supplied;
  * (optional) the chart does not render: a `helm template` dry-run.

This intentionally uses regex/line scanning rather than a YAML parser so it
runs on a bare operator machine with stdlib only. It is a linter, not a schema
validator: it reports what it can prove wrong, and says so when it cannot
inspect something.

Usage:
    validate.py --repo ~/aup-learning-cloud \
        --topology ssh-preinstalled \
        --inventory generated/inventory.yml \
        --gpu-resolution generated/gpu-access-resolution.json \
        --values runtime/values.yaml --values runtime/values-basic-example.yaml \
        --cluster cluster.json --helm-dry-run

Exit codes: 0 if every check passed (warnings allowed); 1 if any check failed;
2 on a usage error.
"""

import argparse
import json
import re
import sys
from pathlib import Path

from config_common import DuplicateJsonKeyError, strict_json_loads
from gpu_resolution_validation import (
    GpuArtifactValidationRequest,
    check_accelerator_labels,
    check_gpu_artifacts,
    check_gpu_inventory,
)
from helm_validation import HelmValidationReporter, check_helm
from values_resolution_parsing import collect_effective_values

PXE_PLAYBOOK = "deploy/ansible/playbooks/pb-pxe-controller.yml"
INVENTORY = "deploy/ansible/inventory.yml"

errors: list[str] = []
warnings: list[str] = []
passed: list[str] = []


def ok(msg: str) -> None:
    passed.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


def fail(msg: str) -> None:
    errors.append(msg)


def scalar(text: str, key: str) -> str | None:
    """First `key: value` scalar in `text` (ignores list/empty values)."""
    m = re.search(rf"^\s*{re.escape(key)}\s*:\s*(.+?)\s*$", text, re.MULTILINE)
    if not m:
        return None
    val = m.group(1).strip().strip('"').strip("'")
    return val or None


def key_occurrences(text: str, key: str) -> int:
    return len(re.findall(rf"^\s*{re.escape(key)}\s*:", text, re.MULTILINE))


def list_nonempty(text: str, key: str) -> bool:
    """True if `key:` is a YAML list with at least one item, or an inline
    non-empty flow list (``[...]`` with content)."""
    # Inline flow list: key: ["a", "b"] or key: []
    m = re.search(rf"^\s*{re.escape(key)}\s*:\s*\[(.*?)\]\s*$", text, re.MULTILINE)
    if m:
        return bool(m.group(1).strip())
    # Block list: key:\n  - item
    m = re.search(rf"^(\s*){re.escape(key)}\s*:\s*$", text, re.MULTILINE)
    if not m:
        return False
    indent = len(m.group(1))
    tail = text[m.end() :].splitlines()
    for line in tail:
        if not line.strip():
            continue
        cur_indent = len(line) - len(line.lstrip())
        if cur_indent <= indent:
            break
        if line.lstrip().startswith("- "):
            return True
    return False


def pxe_vars_path(repo: Path, configured_path: str | None) -> Path:
    return Path(configured_path).expanduser() if configured_path else repo / PXE_PLAYBOOK


def check_pxe_vars(repo: Path, configured_path: str | None = None) -> None:
    pb = pxe_vars_path(repo, configured_path)
    if not pb.exists():
        fail(f"PXE vars file not found: {pb}")
        return
    text = pb.read_text(encoding="utf-8")
    required_scalars = {
        "pxe_network_interface": "service-machine NIC",
        "pxe_subnet": "node subnet CIDR",
        "pxe_controller_ip": "service host IP",
        "pxe_dns_servers": "rootfs DNS servers",
    }
    safety_keys = [*required_scalars, "pxe_k3s_server_ips", "pxe_rootfs_authorized_keys", "pxe_k3s_version"]
    for key in safety_keys:
        if key_occurrences(text, key) > 1:
            fail(f"duplicate PXE key '{key}' in {pb}")
    for key, what in required_scalars.items():
        if scalar(text, key):
            ok(f"PXE var {key} is set")
        else:
            fail(f"PXE var {key} ({what}) is empty -- the playbook asserts on this")
    if list_nonempty(text, "pxe_k3s_server_ips"):
        ok("PXE var pxe_k3s_server_ips has at least one IP")
    else:
        fail("PXE var pxe_k3s_server_ips is empty")
    if list_nonempty(text, "pxe_rootfs_authorized_keys"):
        ok("PXE var pxe_rootfs_authorized_keys has at least one key")
    else:
        fail("PXE var pxe_rootfs_authorized_keys is empty (rootfs would be unreachable)")


def check_version_sync(repo: Path, configured_path: str | None = None) -> None:
    inv = repo / INVENTORY
    pb = pxe_vars_path(repo, configured_path)
    if not inv.exists():
        warn(f"{INVENTORY} not found; skipping k3s version sync check")
        return
    inventory_text = inv.read_text(encoding="utf-8")
    if key_occurrences(inventory_text, "k3s_version") > 1:
        fail(f"duplicate inventory key 'k3s_version' in {inv}")
        return
    server_ver = scalar(inventory_text, "k3s_version")
    if not server_ver:
        warn("k3s_version not found in inventory.yml")
        return
    if not pb.exists():
        ok(f"k3s server version is {server_ver} (no PXE playbook to cross-check)")
        return
    agent_ver = scalar(pb.read_text(encoding="utf-8"), "pxe_k3s_version")
    if not agent_ver:
        warn("pxe_k3s_version not found in the PXE playbook")
        return
    if agent_ver == server_ver:
        ok(f"k3s_version == pxe_k3s_version ({server_ver})")
    else:
        fail(
            f"version mismatch: inventory k3s_version={server_ver} but "
            f"pxe_k3s_version={agent_ver}. Agents must not be newer than the server."
        )


def main(argv=None) -> int:
    global errors, passed, warnings
    errors = []
    warnings = []
    passed = []
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, help="path to the aup-learning-cloud checkout")
    ap.add_argument(
        "--topology",
        choices=("pxe-diskless", "ssh-preinstalled"),
        default="pxe-diskless",
        help="deployment topology (default: pxe-diskless)",
    )
    ap.add_argument(
        "--values", action="append", default=[], help="values file (repeatable); defaults to runtime/values.yaml"
    )
    ap.add_argument(
        "--pxe-vars",
        help="PXE vars file to validate instead of deploy/ansible/playbooks/pb-pxe-controller.yml",
    )
    ap.add_argument("--inventory", help="inventory.yml to validate directly or cross-check with GPU resolution")
    ap.add_argument(
        "--gpu-resolution", help="generated gpu-access-resolution.json; requires --inventory for consistency checks"
    )
    ap.add_argument("--cluster", help="detect_cluster.sh JSON output to match labels against")
    ap.add_argument("--helm-dry-run", action="store_true", help="also run `helm template`")
    ap.add_argument("--json", action="store_true", help="emit a JSON report instead of text")
    args = ap.parse_args(argv)

    repo = Path(args.repo).expanduser()
    if not repo.exists():
        print(f"validate: repo not found: {repo}", file=sys.stderr)
        return 2

    cluster = None
    if args.cluster:
        try:
            cluster = strict_json_loads(Path(args.cluster).read_text(encoding="utf-8"))
        except (DuplicateJsonKeyError, OSError, json.JSONDecodeError) as exc:
            print(f"validate: cannot read --cluster: {exc}", file=sys.stderr)
            return 2

    if args.topology == "pxe-diskless":
        check_pxe_vars(repo, args.pxe_vars)
        check_version_sync(repo, args.pxe_vars)
    else:
        ok("skipped PXE checks for ssh-preinstalled topology")
    values_result = collect_effective_values(repo, args.values)
    for message in values_result.missing_files:
        fail(message)
    for message in values_result.parse_errors:
        fail(message)
    accelerator_result = check_accelerator_labels(values_result.accelerators, values_result.metadata, cluster)
    for message in accelerator_result.errors:
        fail(message)
    for message in accelerator_result.warnings:
        warn(message)
    for message in accelerator_result.passed:
        ok(message)
    if args.gpu_resolution and not args.inventory:
        fail("--gpu-resolution requires --inventory")
    elif args.inventory and not args.gpu_resolution:
        inventory_result = check_gpu_inventory(repo, args.inventory)
        for message in inventory_result.errors:
            fail(message)
        for message in inventory_result.passed:
            ok(message)
    elif args.inventory and args.gpu_resolution:
        artifact_result = check_gpu_artifacts(
            GpuArtifactValidationRequest(
                repo=repo,
                inventory_path=args.inventory,
                resolution_path=args.gpu_resolution,
                topology=args.topology,
                pxe_vars_path=pxe_vars_path(repo, args.pxe_vars),
                has_prior_errors=bool(errors),
            )
        )
        for message in artifact_result.errors:
            fail(message)
        for message in artifact_result.passed:
            ok(message)
    if args.helm_dry_run:
        check_helm(repo, args.values, HelmValidationReporter(ok=ok, warn=warn, fail=fail))

    if args.json:
        print(
            json.dumps(
                {"passed": passed, "warnings": warnings, "errors": errors, "status": "ok" if not errors else "error"},
                indent=2,
            )
        )
    else:
        for m in passed:
            print(f"[ OK ] {m}")
        for m in warnings:
            print(f"[WARN] {m}")
        for m in errors:
            print(f"[FAIL] {m}")
        print(f"\n{len(passed)} ok, {len(warnings)} warning(s), {len(errors)} error(s)")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
