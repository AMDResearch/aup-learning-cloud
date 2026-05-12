#!/usr/bin/env bash
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# ---------------------------------------------------------------------------
# Build the auplc-vllm image. Mirrors the Courses/<X>/build.sh convention:
# honours BASE_IMAGE / GPU_TARGET / MAX_JOBS / VLLM_REF / FLASH_ATTN_REF as
# environment variables so the parent Makefile can drive it.
# ---------------------------------------------------------------------------

set -euo pipefail

BASE_IMAGE="${BASE_IMAGE:-ghcr.io/amdresearch/auplc-base:latest}"
GPU_TARGET="${GPU_TARGET:-gfx1151}"
ROCM_VERSION="${ROCM_VERSION:-7.12.0}"
MAX_JOBS="${MAX_JOBS:-4}"
VLLM_REF="${VLLM_REF:-}"
FLASH_ATTN_REF="${FLASH_ATTN_REF:-main_perf}"
IMAGE_TAG="${IMAGE_TAG:-ghcr.io/amdresearch/auplc-vllm:latest}"

build_args=(
    --build-arg "BASE_IMAGE=${BASE_IMAGE}"
    --build-arg "GPU_TARGET=${GPU_TARGET}"
    --build-arg "ROCM_VERSION=${ROCM_VERSION}"
    --build-arg "MAX_JOBS=${MAX_JOBS}"
    --build-arg "FLASH_ATTN_REF=${FLASH_ATTN_REF}"
)
if [ -n "${VLLM_REF}" ]; then
    build_args+=(--build-arg "VLLM_REF=${VLLM_REF}")
fi

echo "-------------------------------------------"
echo "Building auplc-vllm:"
echo "  BASE_IMAGE      = ${BASE_IMAGE}"
echo "  GPU_TARGET      = ${GPU_TARGET}"
echo "  ROCM_VERSION    = ${ROCM_VERSION}"
echo "  MAX_JOBS        = ${MAX_JOBS}"
echo "  VLLM_REF        = ${VLLM_REF:-<HEAD>}"
echo "  FLASH_ATTN_REF  = ${FLASH_ATTN_REF}"
echo "  IMAGE_TAG       = ${IMAGE_TAG}"
echo "-------------------------------------------"

docker build "${build_args[@]}" -t "${IMAGE_TAG}" .
docker tag "${IMAGE_TAG}" "${IMAGE_TAG}-${GPU_TARGET}"
