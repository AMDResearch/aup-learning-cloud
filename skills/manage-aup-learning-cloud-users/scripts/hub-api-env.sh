# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
#
# Derive the JupyterHub API environment for AUP Learning Cloud user-management
# scripts and probe reachability. SOURCE this file (do not execute) so the
# exports persist in your shell:
#
#   source scripts/hub-api-env.sh
#   HUB_URL="https://hub.example.com" source scripts/hub-api-env.sh
#
# Environment inputs (all optional):
#   HUB_URL        Hub base URL          (default: http://localhost:30890)
#   HUB_NAMESPACE  Kubernetes namespace  (default: jupyterhub)
#
# Exports on success: JUPYTERHUB_URL, JUPYTERHUB_TOKEN

_auplc_ns="${HUB_NAMESPACE:-jupyterhub}"
_auplc_url="${HUB_URL:-http://localhost:30890}"

_auplc_token="$(kubectl -n "$_auplc_ns" get secret jupyterhub-admin-credentials \
  -o jsonpath='{.data.api-token}' 2>/dev/null | base64 -d 2>/dev/null)"

if [ -z "$_auplc_token" ]; then
  echo "hub-api-env: could not read api-token from secret 'jupyterhub-admin-credentials'" >&2
  echo "  - is custom.adminUser.enabled: true and the Hub deployed?" >&2
  echo "  - is your kube context/namespace ('$_auplc_ns') correct?" >&2
  # This file is meant to be sourced; `return` exits the caller's shell. The
  # `exit 1` fallback only runs if the file is executed directly.
  # shellcheck disable=SC2317
  return 1 2>/dev/null || exit 1
fi

export JUPYTERHUB_URL="$_auplc_url"
export JUPYTERHUB_TOKEN="$_auplc_token"

# Probe the API (non-fatal: token may still be valid behind an auth proxy).
if command -v curl >/dev/null 2>&1; then
  _auplc_code="$(printf 'header = "Authorization: token %s"\n' "$JUPYTERHUB_TOKEN" | \
    curl --config - -s -o /dev/null -w '%{http_code}' \
      "${JUPYTERHUB_URL%/}/hub/api/" 2>/dev/null)"
  case "$_auplc_code" in
    200) echo "hub-api-env: OK — $JUPYTERHUB_URL/hub/api/ reachable (200)" ;;
    *)   echo "hub-api-env: WARNING — $JUPYTERHUB_URL/hub/api/ returned '$_auplc_code'; check HUB_URL/network" >&2 ;;
  esac
fi

echo "hub-api-env: exported JUPYTERHUB_URL=$JUPYTERHUB_URL and JUPYTERHUB_TOKEN (hidden)"

unset _auplc_ns _auplc_url _auplc_token _auplc_code
