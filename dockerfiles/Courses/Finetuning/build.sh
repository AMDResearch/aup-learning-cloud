#!/usr/bin/env bash
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

set -euo pipefail

# Hardcoded workshop asset bundle location: drop mm2_workshop_assets.zip into projects/Finetuning/
# (next to the notebooks) and it gets baked into the image. Nothing to configure.
PROJECT_DIR="../../../projects/Finetuning"
ASSETS_ZIP="${PROJECT_DIR}/mm2_workshop_assets.zip"

WORK_ASSETS=""
cleanup() {
  rm -rf course_data
  [ -n "${WORK_ASSETS:-}" ] && rm -rf "${WORK_ASSETS}"
  return 0
}
trap cleanup EXIT

# Stage the course notebooks + helper scripts into the build context, EXCLUDING the large asset
# bundle so it is never baked into /ryzers/notebooks.
rm -rf course_data
mkdir -p course_data
cp -r "$PROJECT_DIR"/. course_data/
rm -rf course_data/mm2_workshop_assets course_data/mm2_workshop_assets.zip

# Bake the workshop assets if the bundle is present; otherwise build a code-only image (CI/registry).
BUILD_EXTRA=()
if [ -f "${ASSETS_ZIP}" ]; then
  echo "unpacking mm2_workshop_assets.zip (one-time; the bundle is large, this can take a while)..."
  # Unpack OUTSIDE the docker build context (extracting here would bloat the context sent to the
  # daemon). /var/tmp is disk-backed and typically large enough for the ~16 GB bundle.
  WORK_ASSETS="$(mktemp -d "${TMPDIR:-/var/tmp}/auplc-ft-assets.XXXXXX")"
  unzip -q "${ASSETS_ZIP}" -d "${WORK_ASSETS}"
  echo "baking workshop assets into the image from: ${WORK_ASSETS}/mm2_workshop_assets"
  BUILD_EXTRA+=(--build-context "assets=${WORK_ASSETS}/mm2_workshop_assets" --build-arg "FINAL=with-assets")
else
  echo "no mm2_workshop_assets.zip in projects/Finetuning/ -> building code-only image (assets NOT baked in)."
fi

DOCKER_BUILDKIT=1 docker build ${BASE_IMAGE:+--build-arg BASE_IMAGE="$BASE_IMAGE"} \
  ${BUILD_EXTRA[@]+"${BUILD_EXTRA[@]}"} \
  -t ghcr.io/amdresearch/auplc-finetuning:latest .
