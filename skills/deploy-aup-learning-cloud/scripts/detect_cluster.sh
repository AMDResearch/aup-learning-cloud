#!/usr/bin/env bash
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
#
# detect_cluster.sh -- after k3s is up, emit a JSON snapshot of the cluster the
# deploy skill needs to align custom.accelerators.*.nodeSelector with the REAL
# amd.com/gpu.* labels, confirm storage, and check the ROCm device plugin +
# labeller are running. Read-only: it only runs `kubectl get`.
#
# Usage:
#   ./detect_cluster.sh                          # uses current KUBECONFIG
#   KUBECONFIG=~/.kube/config ./detect_cluster.sh
#   ./detect_cluster.sh --kubeconfig /path/to/k3s.yaml
#   ./detect_cluster.sh -h | --help
#
# Output (stdout) is a single JSON object:
#   {
#     "nodes": [
#       {"name":"aipc1","ready":true,"roles":["control-plane"],
#        "internal_ip":"192.168.0.140","gpu_product_names":["AMD_Radeon_8060S_Graphics"],
#        "gpu_allocatable":"1","gpu_labels":{...}}
#     ],
#     "gpu_product_names": ["AMD_Radeon_8060S_Graphics"],
#     "storage_classes": [{"name":"local-path","default":true}],
#     "amdgpu_device_plugin": true,
#     "amdgpu_labeller": true,
#     "warnings": ["..."]
#   }
#
# Exit codes: 0 on success (including "cluster reachable but nothing labelled
# yet"); 2 if kubectl/python3 missing or the API server is unreachable.
#
# Dependencies: bash, kubectl, python3 (stdlib only -- parses `kubectl -o json`).

set -uo pipefail

KCFG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --kubeconfig) KCFG="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "detect_cluster: unknown arg $1" >&2; exit 2 ;;
  esac
done

command -v kubectl >/dev/null 2>&1 || { echo "detect_cluster: kubectl is required" >&2; exit 2; }
command -v python3 >/dev/null 2>&1 || { echo "detect_cluster: python3 is required" >&2; exit 2; }
[[ -n "$KCFG" ]] && export KUBECONFIG="$KCFG"

kc() { kubectl "$@" 2>/dev/null; }

# Fail fast (exit 2) if we cannot reach the API server at all -- this is the
# single most common "ran too early / wrong kubeconfig" case.
if ! kc version --request-timeout=10s >/dev/null; then
  echo "detect_cluster: cannot reach the Kubernetes API server. Check KUBECONFIG / that k3s is up." >&2
  exit 2
fi

NODES_JSON="$(kc get nodes -o json || echo '{}')"
SC_JSON="$(kc get storageclass -o json || echo '{}')"
# The device plugin + labeller are DaemonSets; their names/namespaces can vary,
# so we scan all daemonsets and match on the amdgpu substring.
DS_JSON="$(kc get ds -A -o json || echo '{}')"

export DC_NODES="$NODES_JSON" DC_SC="$SC_JSON" DC_DS="$DS_JSON"

python3 <<'PY'
import json, os

def load(name):
    try:
        return json.loads(os.environ.get(name, "") or "{}")
    except json.JSONDecodeError:
        return {}

nodes_raw = load("DC_NODES").get("items", [])
sc_raw = load("DC_SC").get("items", [])
ds_raw = load("DC_DS").get("items", [])

warnings = []
nodes = []
all_products = set()
for n in nodes_raw:
    meta = n.get("metadata", {})
    name = meta.get("name", "")
    labels = meta.get("labels", {}) or {}
    status = n.get("status", {})
    ready = False
    for c in status.get("conditions", []) or []:
        if c.get("type") == "Ready":
            ready = (c.get("status") == "True")
    roles = sorted(
        k.split("/", 1)[1] or "node"
        for k in labels
        if k.startswith("node-role.kubernetes.io/")
    )
    internal_ip = ""
    for a in status.get("addresses", []) or []:
        if a.get("type") == "InternalIP":
            internal_ip = a.get("address", "")
    gpu_labels = {k: v for k, v in labels.items() if k.startswith("amd.com/gpu")}
    products = [v for k, v in gpu_labels.items() if k == "amd.com/gpu.product-name"]
    all_products.update(products)
    alloc = (status.get("allocatable", {}) or {}).get("amd.com/gpu", "0")
    nodes.append({
        "name": name,
        "ready": ready,
        "roles": roles,
        "internal_ip": internal_ip,
        "gpu_product_names": products,
        "gpu_allocatable": alloc,
        "gpu_labels": gpu_labels,
    })

storage_classes = []
for sc in sc_raw:
    meta = sc.get("metadata", {})
    ann = meta.get("annotations", {}) or {}
    is_default = ann.get("storageclass.kubernetes.io/is-default-class") == "true"
    storage_classes.append({"name": meta.get("name", ""), "default": is_default})

def has_ds(substr):
    for ds in ds_raw:
        if substr in ds.get("metadata", {}).get("name", "").lower():
            return True
    return False

device_plugin = has_ds("device-plugin") or has_ds("amdgpu-dp") or (
    any("amdgpu" in ds.get("metadata", {}).get("name", "").lower()
        and "label" not in ds.get("metadata", {}).get("name", "").lower()
        for ds in ds_raw)
)
labeller = has_ds("labeller") or has_ds("labeler") or has_ds("amdgpu-labeller")

if not nodes:
    warnings.append("no nodes returned; cluster may still be initialising")
if not all_products:
    warnings.append("no amd.com/gpu.product-name labels yet; install the ROCm device plugin + labeller, then re-run")
if not device_plugin:
    warnings.append("AMD GPU device plugin DaemonSet not detected")
if not labeller:
    warnings.append("ROCm node labeller DaemonSet not detected")

print(json.dumps({
    "nodes": nodes,
    "gpu_product_names": sorted(all_products),
    "storage_classes": storage_classes,
    "amdgpu_device_plugin": bool(device_plugin),
    "amdgpu_labeller": bool(labeller),
    "warnings": warnings,
}, indent=2))
PY
