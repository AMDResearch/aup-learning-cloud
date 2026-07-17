#!/usr/bin/env bash
# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
#
# Read-only verification that AUP Learning Cloud monitoring is wired up:
# checks the ServiceMonitor, metrics token secret, Grafana dashboard ConfigMap,
# and metrics NetworkPolicy, then port-forwards Prometheus and confirms the
# Hub target is UP. Makes no cluster changes.
#
# Usage:
#   scripts/verify_monitoring.sh
#
# Environment (optional):
#   MON_NS   monitoring namespace   (default: monitoring)
#   HUB_NS   jupyterhub namespace   (default: jupyterhub)
#   PROM_SVC Prometheus service     (default: monitoring-kube-prometheus-prometheus)

set -uo pipefail

MON_NS="${MON_NS:-monitoring}"
HUB_NS="${HUB_NS:-jupyterhub}"
PROM_SVC="${PROM_SVC:-monitoring-kube-prometheus-prometheus}"

rc=0
pass() { printf '  [OK]   %s\n' "$1"; }
warn() { printf '  [WARN] %s\n' "$1"; rc=1; }

echo "Checking monitoring objects (mon ns=$MON_NS, hub ns=$HUB_NS)..."

if kubectl -n "$MON_NS" get servicemonitor hub-metrics >/dev/null 2>&1; then
  pass "ServiceMonitor hub-metrics present"
else
  warn "ServiceMonitor hub-metrics missing (serviceMonitor.enabled?)"
fi

if kubectl -n "$MON_NS" get secret 2>/dev/null | grep -q 'metrics-token'; then
  pass "metrics token secret present"
else
  warn "metrics token secret missing (authorization.secret.create?)"
fi

if kubectl -n "$MON_NS" get configmap grafana-dashboard-aup-hub >/dev/null 2>&1; then
  pass "Grafana dashboard ConfigMap present"
else
  warn "Grafana dashboard ConfigMap missing (grafana.dashboard.enabled?)"
fi

if kubectl -n "$HUB_NS" get networkpolicy hub-metrics >/dev/null 2>&1; then
  pass "metrics NetworkPolicy present"
else
  warn "metrics NetworkPolicy missing (hubMetrics.enabled?)"
fi

echo "Checking the live Prometheus target..."
if ! kubectl -n "$MON_NS" get svc "$PROM_SVC" >/dev/null 2>&1; then
  warn "Prometheus service '$PROM_SVC' not found; set PROM_SVC to your service name"
  echo "Done (with warnings)."; exit "$rc"
fi

kubectl -n "$MON_NS" port-forward "svc/$PROM_SVC" 9090:9090 >/dev/null 2>&1 &
pf_pid=$!
trap 'kill "$pf_pid" 2>/dev/null' EXIT
sleep 3

result="$(curl -fsS 'http://127.0.0.1:9090/api/v1/query?query=up%7Bjob%3D%22hub%22%7D' 2>/dev/null)"
case "$result" in
  *'"job":"hub"'*'"1"'*) pass "Prometheus reports hub target UP" ;;
  *'"job":"hub"'*)       warn "hub target found but not UP (value != 1)" ;;
  *)                     warn "hub target not found in Prometheus (label/selector mismatch?)" ;;
esac

echo "Done."
exit "$rc"
