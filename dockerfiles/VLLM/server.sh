#!/usr/bin/env bash
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
#
# vLLM OpenAI-compatible API server, in-image launcher tuned for benchmark
# runs on Strix Halo (gfx1151). Pairs with /usr/local/bin/bench.
#
# Designed to be run *inside* the auplc-vllm container, e.g.:
#
#   # foreground (CMD-style):
#   docker run --rm --device=/dev/kfd --device=/dev/dri \
#       -p 8000:8000 -e MODEL=Qwen/Qwen3-4B \
#       ghcr.io/amdresearch/auplc-vllm:latest server
#
#   # detached + bench against it:
#   docker run -d --name vllm --device=/dev/kfd --device=/dev/dri \
#       -p 8000:8000 -e MODEL=Qwen/Qwen3-4B \
#       ghcr.io/amdresearch/auplc-vllm:latest server
#   docker exec vllm bench
#
# Differences vs. start-vllm-server.sh: bench-friendly defaults
# (Qwen3-4B, MAX_MODEL_LEN=2048, GPU_MEM_UTIL=0.90, --no-enable-log-requests)
# and a stable name pair (`server` / `bench`).
#
# All knobs are env-driven so the script is `docker exec`-friendly. Any
# positional / flag args after the script name are forwarded verbatim to
# vllm.entrypoints.openai.api_server, so you can mix env + extra flags.
set -euo pipefail

: "${MODEL:=Qwen/Qwen3-4B}"
: "${DTYPE:=bfloat16}"
: "${MAX_MODEL_LEN:=2048}"
: "${GPU_MEM_UTIL:=0.90}"
: "${PORT:=8000}"
: "${HOST:=0.0.0.0}"
: "${TENSOR_PARALLEL_SIZE:=1}"
# Pass-through extras. Defaults: trust HF custom code, suppress per-request
# log spam (it pollutes bench client output and adds non-trivial overhead).
: "${EXTRA_ARGS:=--trust-remote-code --no-enable-log-requests}"

# Strix Halo runtime knobs are baked into the image ENV; re-export defensively
# in case the operator overrode them on `docker run`.
export FLASH_ATTENTION_TRITON_AMD_ENABLE="${FLASH_ATTENTION_TRITON_AMD_ENABLE:-TRUE}"

echo "[server] model=${MODEL} dtype=${DTYPE} max_len=${MAX_MODEL_LEN} gpu_util=${GPU_MEM_UTIL}"
echo "[server] host=${HOST} port=${PORT} tp=${TENSOR_PARALLEL_SIZE}"
echo "[server] extra_args=${EXTRA_ARGS}"

# shellcheck disable=SC2086  # intentional word-splitting of EXTRA_ARGS
exec python3 -m vllm.entrypoints.openai.api_server \
    --model "${MODEL}" \
    --dtype "${DTYPE}" \
    --max-model-len "${MAX_MODEL_LEN}" \
    --gpu-memory-utilization "${GPU_MEM_UTIL}" \
    --tensor-parallel-size "${TENSOR_PARALLEL_SIZE}" \
    --host "${HOST}" \
    --port "${PORT}" \
    ${EXTRA_ARGS} \
    "$@"
