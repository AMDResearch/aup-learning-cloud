#!/usr/bin/env python3
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
"""Pre-flight validation for an AUP Learning Cloud deploy.

Catches the mistakes that otherwise surface only after a long playbook or a
failed spawn:

  * required PXE vars empty (interface / subnet / controller_ip / dns /
    k3s_server_ips / at least one authorized key);
  * the k3s server version and the PXE agent rootfs version disagree
    (agents must not be newer than the server);
  * a custom.accelerators.*.nodeSelector that names a GPU product label no
    node actually reports (the #1 cause of GPU notebooks stuck Pending) --
    checked against detect_cluster.sh output when supplied;
  * (optional) the chart does not render: a `helm template` dry-run.

This intentionally uses regex/line scanning rather than a YAML parser so it
runs on a bare operator machine with stdlib only. It is a linter, not a schema
validator: it reports what it can prove wrong, and says so when it cannot
inspect something.

Usage:
    validate.py --repo ~/aup-learning-cloud
    validate.py --repo ~/aup-learning-cloud \
        --values runtime/values.yaml --values runtime/values-basic-example.yaml \
        --cluster cluster.json --helm-dry-run

Exit codes: 0 if every check passed (warnings allowed); 1 if any check failed;
2 on a usage error.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

PXE_PLAYBOOK = "deploy/ansible/playbooks/pb-pxe-controller.yml"
INVENTORY = "deploy/ansible/inventory.yml"
CHART = "runtime/chart"

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
    tail = text[m.end():].splitlines()
    for line in tail:
        if not line.strip():
            continue
        cur_indent = len(line) - len(line.lstrip())
        if cur_indent <= indent:
            break
        if line.lstrip().startswith("- "):
            return True
    return False


def check_pxe_vars(repo: Path) -> None:
    pb = repo / PXE_PLAYBOOK
    if not pb.exists():
        warn(f"{PXE_PLAYBOOK} not found; skipping PXE checks (SSH topology?)")
        return
    text = pb.read_text(encoding="utf-8")
    required_scalars = {
        "pxe_network_interface": "service-machine NIC",
        "pxe_subnet": "node subnet CIDR",
        "pxe_controller_ip": "service host IP",
        "pxe_dns_servers": "rootfs DNS servers",
    }
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


def check_version_sync(repo: Path) -> None:
    inv = repo / INVENTORY
    pb = repo / PXE_PLAYBOOK
    if not inv.exists():
        warn(f"{INVENTORY} not found; skipping k3s version sync check")
        return
    server_ver = scalar(inv.read_text(encoding="utf-8"), "k3s_version")
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
        fail(f"version mismatch: inventory k3s_version={server_ver} but "
             f"pxe_k3s_version={agent_ver}. Agents must not be newer than the server.")


def collect_values_text(repo: Path, values: list[str]) -> str:
    paths = values or ["runtime/values.yaml"]
    chunks = []
    for rel in paths:
        p = (repo / rel) if not Path(rel).is_absolute() else Path(rel)
        if p.exists():
            chunks.append(p.read_text(encoding="utf-8"))
        else:
            warn(f"values file not found: {rel}")
    return "\n".join(chunks)


def check_accelerator_labels(values_text: str, cluster: dict | None) -> None:
    declared = sorted(set(re.findall(
        r"amd\.com/gpu\.product-name\s*:\s*[\"']?([A-Za-z0-9_]+)[\"']?", values_text)))
    if not declared:
        warn("no amd.com/gpu.product-name nodeSelector found in the values overlay")
        return
    if cluster is None:
        warn("no --cluster snapshot; cannot confirm nodeSelector labels match real "
             f"nodes. Declared: {', '.join(declared)}")
        return
    real = set(cluster.get("gpu_product_names", []))
    if not real:
        warn("cluster snapshot reports no GPU product labels yet (device plugin / "
             "labeller not ready?)")
        return
    for d in declared:
        if d in real:
            ok(f"nodeSelector '{d}' matches a real node label")
        else:
            fail(f"nodeSelector '{d}' matches no node label. Real labels: "
                 f"{', '.join(sorted(real))}")


def check_helm(repo: Path, values: list[str]) -> None:
    if not shutil.which("helm"):
        warn("helm not on PATH; skipped chart dry-run")
        return
    chart = repo / CHART
    if not chart.exists():
        warn(f"chart not found at {CHART}; skipped dry-run")
        return
    cmd = ["helm", "template", "jupyterhub", str(chart)]
    for rel in (values or ["runtime/values.yaml"]):
        p = (repo / rel) if not Path(rel).is_absolute() else Path(rel)
        if p.exists():
            cmd += ["-f", str(p)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode == 0:
        ok("helm template rendered the chart successfully")
    else:
        tail = (proc.stderr or proc.stdout).strip().splitlines()[-5:]
        fail("helm template failed:\n        " + "\n        ".join(tail))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, help="path to the aup-learning-cloud checkout")
    ap.add_argument("--values", action="append", default=[],
                    help="values file (repeatable); defaults to runtime/values.yaml")
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
            cluster = json.loads(Path(args.cluster).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"validate: cannot read --cluster: {exc}", file=sys.stderr)
            return 2

    check_pxe_vars(repo)
    check_version_sync(repo)
    values_text = collect_values_text(repo, args.values)
    check_accelerator_labels(values_text, cluster)
    if args.helm_dry_run:
        check_helm(repo, args.values)

    if args.json:
        print(json.dumps({"passed": passed, "warnings": warnings, "errors": errors,
                          "status": "ok" if not errors else "error"}, indent=2))
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
