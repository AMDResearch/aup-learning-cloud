#!/usr/bin/env bash
set -euo pipefail

IMAGE_FLAVOR="${IMAGE_FLAVOR:-cpu}"

case "${IMAGE_FLAVOR}" in
  cpu)
    BASE_IMAGE="${BASE_IMAGE:-ghcr.io/amdresearch/auplc-default:latest}"
    IMAGE_TAG="${IMAGE_TAG:-ghcr.io/amdresearch/auplc-code-cpu:latest}"
    ;;
  gpu)
    BASE_IMAGE="${BASE_IMAGE:-ghcr.io/amdresearch/auplc-base:latest}"
    IMAGE_TAG="${IMAGE_TAG:-ghcr.io/amdresearch/auplc-code-gpu:latest}"
    ;;
  *)
    printf 'Unsupported IMAGE_FLAVOR: %s\n' "${IMAGE_FLAVOR}" >&2
    exit 2
    ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
NODE_IMAGE="${NODE_IMAGE:-docker.io/library/node:22-bookworm-slim}"
NPM_REGISTRY="${NPM_REGISTRY:-}"
PNPM_VERSION="${PNPM_VERSION:-10.27.0}"
CODE_GLOBAL_NPM_PACKAGES="${CODE_GLOBAL_NPM_PACKAGES:-typescript tsx vite eslint prettier}"

docker build \
  -f "${ROOT_DIR}/dockerfiles/Code/Dockerfile" \
  --build-arg "NODE_IMAGE=${NODE_IMAGE}" \
  --build-arg "BASE_IMAGE=${BASE_IMAGE}" \
  --build-arg "IMAGE_FLAVOR=${IMAGE_FLAVOR}" \
  --build-arg "NPM_REGISTRY=${NPM_REGISTRY}" \
  --build-arg "PNPM_VERSION=${PNPM_VERSION}" \
  --build-arg "CODE_GLOBAL_NPM_PACKAGES=${CODE_GLOBAL_NPM_PACKAGES}" \
  -t "${IMAGE_TAG}" \
  "${ROOT_DIR}"
