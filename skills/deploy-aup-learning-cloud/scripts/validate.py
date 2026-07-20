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
  * (optional) the chart does not render: a `helm template` dry-run.

This intentionally uses regex/line scanning rather than a YAML parser so it
runs on a bare operator machine with stdlib only. It is a linter, not a schema
validator: it reports what it can prove wrong, and says so when it cannot
inspect something.

Usage:
    validate.py --repo ~/aup-learning-cloud --topology pxe-diskless
    validate.py --repo ~/aup-learning-cloud \
        --topology ssh-preinstalled \
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


def yaml_scalar(value: str) -> str:
    return value.strip().strip('"').strip("'")


def yaml_optional_scalar(value: str) -> str:
    scalar_value = yaml_scalar(value)
    return "" if scalar_value in {"", "null", "~"} else scalar_value


def yaml_indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def parse_inline_list(value: str) -> list[str]:
    items = value.strip()[1:-1].strip()
    if not items:
        return []
    return [yaml_scalar(item) for item in items.split(",") if yaml_scalar(item)]


def is_relevant_flow_path(path: tuple[str, ...]) -> bool:
    return path == ("custom",) or path[:2] in {("custom", "accelerators"), ("custom", "resources")}


def unsupported_yaml_syntax(value: str) -> bool:
    return value.startswith(("&", "*", "!", "|", ">"))


def parse_values_file(text: str) -> tuple[dict[str, str | None], dict[str, list[str]], list[str]]:
    """Extract the deploy-relevant mappings from a fixed-shape values YAML file.

    The helpers deliberately remain stdlib-only. This scanner handles the
    mapping/list shapes used by values overlays, rather than pretending to be a
    general YAML parser.
    """
    accelerators: dict[str, str | None] = {}
    metadata: dict[str, list[str]] = {}
    parse_errors: list[str] = []
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

        if stripped.startswith("- "):
            if len(path) == 5 and path[:3] == ("custom", "resources", "metadata") and path[-1] == "acceleratorKeys":
                metadata.setdefault(path[3], []).append(yaml_scalar(stripped[2:]))
            continue

        product_label_match = re.fullmatch(
            r"(?:[\"']amd\.com/gpu\.product-name[\"']|amd\.com/gpu\.product-name):\s*(.*)", stripped
        )
        if product_label_match:
            if len(path) == 4 and path[:2] == ("custom", "accelerators") and path[-1] == "nodeSelector":
                value = product_label_match.group(1).strip()
                if unsupported_yaml_syntax(value):
                    parse_errors.append(
                        f"unsupported YAML syntax at custom.accelerators.{path[2]}.nodeSelector.amd.com/gpu.product-name"
                    )
                else:
                    accelerators[path[2]] = yaml_optional_scalar(value)
            continue

        mapping_match = re.fullmatch(r"(.+?):(?:\s*(.*))?", stripped)
        if not mapping_match:
            continue
        key = mapping_match.group(1).strip("\"'")
        value = (mapping_match.group(2) or "").strip()
        candidate_path = path + (key,)
        if value.startswith("{") and value != "{}" and is_relevant_flow_path(candidate_path):
            parse_errors.append(f"unsupported non-empty flow-style mapping at {'.'.join(candidate_path)}")
        if unsupported_yaml_syntax(value) and is_relevant_flow_path(candidate_path):
            parse_errors.append(f"unsupported YAML syntax at {'.'.join(candidate_path)}")
        if path == ("custom", "accelerators"):
            accelerators.setdefault(key, None)
        if len(path) == 4 and path[:3] == ("custom", "resources", "metadata") and key == "acceleratorKeys":
            resource_key = path[3]
            if unsupported_yaml_syntax(value):
                parse_errors.append(f"unsupported YAML syntax at {'.'.join(candidate_path)}")
            elif value.startswith("[") and value.endswith("]"):
                metadata[resource_key] = parse_inline_list(value)
            elif not value or value in {"null", "~"}:
                metadata[resource_key] = []
            else:
                parse_errors.append(f"acceleratorKeys must be a list at {'.'.join(candidate_path)}")
        stack.append((indent, key))
    return accelerators, metadata, parse_errors


def collect_effective_values(repo: Path, values: list[str]) -> tuple[dict[str, str], dict[str, list[str]], list[str]]:
    paths = values or ["runtime/values.yaml"]
    accelerators: dict[str, str] = {}
    metadata: dict[str, list[str]] = {}
    parse_errors: list[str] = []
    for rel in paths:
        p = (repo / rel) if not Path(rel).is_absolute() else Path(rel)
        if p.exists():
            parsed_accelerators, parsed_metadata, file_errors = parse_values_file(p.read_text(encoding="utf-8"))
            for key, selector in parsed_accelerators.items():
                if selector is not None or key not in accelerators:
                    accelerators[key] = selector
            metadata.update(parsed_metadata)
            parse_errors.extend(file_errors)
        else:
            fail(f"values file not found: {rel}")
    return accelerators, metadata, parse_errors


def check_accelerator_labels(
    accelerators: dict[str, str], metadata: dict[str, list[str]], cluster: dict | None
) -> None:
    active_keys = sorted({key for keys in metadata.values() for key in keys})
    if not active_keys:
        warn("no acceleratorKeys found in effective custom.resources.metadata")
        return
    declared: list[str] = []
    for key in active_keys:
        if key not in accelerators:
            fail(f"active accelerator '{key}' is not defined under custom.accelerators")
        elif not accelerators[key]:
            fail(f"active accelerator '{key}' has no amd.com/gpu.product-name nodeSelector")
        else:
            declared.append(accelerators[key])
    if not declared:
        return
    if cluster is None:
        warn(
            "no --cluster snapshot; cannot confirm nodeSelector labels match real "
            f"nodes. Declared: {', '.join(declared)}"
        )
        return
    real = set(cluster.get("gpu_product_names", []))
    if not real:
        fail("cluster snapshot has no GPU product labels for active accelerators")
        return
    for d in declared:
        if d in real:
            ok(f"nodeSelector '{d}' matches a real node label")
        else:
            fail(f"nodeSelector '{d}' matches no node label. Real labels: {', '.join(sorted(real))}")


def check_helm(repo: Path, values: list[str]) -> None:
    if not shutil.which("helm"):
        warn("helm not on PATH; skipped chart dry-run")
        return
    chart = repo / CHART
    if not chart.exists():
        warn(f"chart not found at {CHART}; skipped dry-run")
        return
    cmd = ["helm", "template", "jupyterhub", str(chart)]
    for rel in values or ["runtime/values.yaml"]:
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

    if args.topology == "pxe-diskless":
        check_pxe_vars(repo, args.pxe_vars)
        check_version_sync(repo, args.pxe_vars)
    else:
        ok("skipped PXE checks for ssh-preinstalled topology")
    accelerators, metadata, parse_errors = collect_effective_values(repo, args.values)
    for message in parse_errors:
        fail(message)
    check_accelerator_labels(accelerators, metadata, cluster)
    if args.helm_dry_run:
        check_helm(repo, args.values)

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
