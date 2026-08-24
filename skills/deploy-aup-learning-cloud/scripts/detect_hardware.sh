#!/usr/bin/env bash
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
#
# detect_hardware.sh -- inspect the service machine and emit a JSON snapshot of
# the network and AMD GPU facts the deploy skill needs to fill in PXE / inventory
# variables. Read-only: it never changes the host.
#
# Usage:
#   ./detect_hardware.sh                 # auto-detect the default-route NIC
#   ./detect_hardware.sh --nic enp1s0    # force a specific NIC
#   ./detect_hardware.sh -h | --help
#
# Output (stdout) is a single JSON object:
#   {
#     "nic": "enp1s0",
#     "ip": "192.168.0.140",
#     "subnet_cidr": "192.168.0.0/24",
#     "gateway": "192.168.0.1",
#     "dns_servers": "8.8.8.8,8.8.4.4",
#     "gpus": [ {"pci":"c5:00.0","vendor":"1002","description":"...","kernel_driver":"amdgpu"} ],
#     "warnings": [ "..." ]
#   }
#
# Exit codes: 0 always (partial detection is reported via empty fields +
# warnings so the agent can decide what to ask the operator). Hard tooling
# failures (no python3) exit 2.
#
# Dependencies: bash, iproute2 (ip), pciutils (lspci), python3 (stdlib only).
# python3 is used purely to serialise JSON safely (lspci descriptions contain
# brackets, quotes, commas). No third-party packages.

set -uo pipefail

NIC=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --nic) NIC="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,40p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "detect_hardware: unknown arg $1" >&2; exit 2 ;;
  esac
done

command -v python3 >/dev/null 2>&1 || { echo "detect_hardware: python3 is required" >&2; exit 2; }

warnings=()

# --- NIC: default to the interface owning the default route ---------------
if [[ -z "$NIC" ]]; then
  NIC="$(ip -o route show default 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="dev"){print $(i+1); exit}}')"
fi
[[ -z "$NIC" ]] && warnings+=("no default-route NIC found; pass --nic explicitly")

# --- IPv4 address + CIDR on that NIC --------------------------------------
IP=""; CIDR=""
if [[ -n "$NIC" ]]; then
  # e.g. "192.168.0.140/24"
  addr="$(ip -o -f inet addr show "$NIC" 2>/dev/null | awk '{print $4; exit}')"
  if [[ -n "$addr" ]]; then
    IP="${addr%/*}"
    prefix="${addr#*/}"
    # Network address for the CIDR (zero the host bits) via python ipaddress.
    CIDR="$(python3 - "$addr" <<'PY' 2>/dev/null
import ipaddress, sys
net = ipaddress.ip_interface(sys.argv[1]).network
print(net.with_prefixlen)
PY
)"
  fi
fi
[[ -z "$IP" ]] && warnings+=("no IPv4 address on NIC '$NIC'")

# --- Default gateway ------------------------------------------------------
GATEWAY="$(ip -o route show default 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="via"){print $(i+1); exit}}')"
[[ -z "$GATEWAY" ]] && warnings+=("no default gateway found")

# --- DNS servers ----------------------------------------------------------
# Prefer systemd-resolved when present; fall back to /etc/resolv.conf.
DNS=""
if command -v resolvectl >/dev/null 2>&1; then
  DNS="$(resolvectl dns 2>/dev/null | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}' | sort -u | paste -sd, -)"
fi
if [[ -z "$DNS" && -r /etc/resolv.conf ]]; then
  DNS="$(awk '/^nameserver/{print $2}' /etc/resolv.conf | grep -E '^([0-9]{1,3}\.){3}[0-9]{1,3}$' | paste -sd, -)"
fi
[[ -z "$DNS" ]] && warnings+=("no DNS servers detected; defaulting suggestion is 8.8.8.8,8.8.4.4")

# --- AMD GPUs via lspci ---------------------------------------------------
# AMD/ATI PCI vendor id is 1002. We hand the full `lspci -D -nnk` dump to
# python3 (below) and parse device blocks there: mawk (Ubuntu's default awk)
# does not support {n} interval regexes, so block parsing in python is far more
# portable. We record the bound kernel driver (amdgpu = the in-kernel driver is
# loaded, which the PXE rootfs needs for GPU scheduling).
LSPCI_RAW=""
if command -v lspci >/dev/null 2>&1; then
  LSPCI_RAW="$(lspci -D -nnk 2>/dev/null)"
else
  warnings+=("lspci not found (install pciutils); GPU detection skipped")
fi

# Hand everything to python3 for safe JSON assembly.
export DH_NIC="$NIC" DH_IP="$IP" DH_CIDR="$CIDR" DH_GW="$GATEWAY" DH_DNS="$DNS"
export DH_LSPCI="$LSPCI_RAW"
DH_WARNINGS="$(printf '%s\n' "${warnings[@]:-}")"
export DH_WARNINGS

python3 <<'PY'
import json, os, re

# PCI classes we treat as a GPU/accelerator: VGA (0300), 3D (0302),
# Display (0380), Processing accelerator (1200).
GPU_CLASSES = ("0300", "0302", "0380", "1200")

def amd_gpus(raw):
    out = []
    cur = None
    for line in (raw or "").splitlines():
        # Device header lines start at column 0 with a PCI address.
        if re.match(r"^[0-9a-fA-F]{4}:", line):
            if cur:
                out.append(cur)
            cur = None
            m = re.match(
                r"^(\S+)\s+.*?\[(?P<cls>[0-9a-f]{4})\]:\s+(?P<desc>.*?)\s*"
                r"\[(?P<vendor>[0-9a-f]{4}):(?P<dev>[0-9a-f]{4})\]",
                line)
            if not m:
                continue
            if m.group("vendor") != "1002" or m.group("cls") not in GPU_CLASSES:
                continue
            cur = {
                "pci": m.group(1),
                "vendor": "1002",
                "device_id": m.group("dev"),
                "description": m.group("desc").strip(),
                "kernel_driver": "",
            }
        elif cur is not None:
            dm = re.search(r"Kernel driver in use:\s*(\S+)", line)
            if dm:
                cur["kernel_driver"] = dm.group(1)
    if cur:
        out.append(cur)
    return out

warnings = [w for w in (os.environ.get("DH_WARNINGS", "").splitlines()) if w.strip()]
print(json.dumps({
    "nic": os.environ.get("DH_NIC", ""),
    "ip": os.environ.get("DH_IP", ""),
    "subnet_cidr": os.environ.get("DH_CIDR", ""),
    "gateway": os.environ.get("DH_GW", ""),
    "dns_servers": os.environ.get("DH_DNS", ""),
    "gpus": amd_gpus(os.environ.get("DH_LSPCI", "")),
    "warnings": warnings,
}, indent=2))
PY
