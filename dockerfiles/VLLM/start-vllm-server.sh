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
# OpenAI-compatible vLLM API server launcher for the auplc-vllm image.
#
# Usage inside the container:
#
#   start-vllm-server                                      # uses MODEL env (default Qwen 2.5 0.5B)
#   MODEL=Qwen/Qwen2.5-7B-Instruct start-vllm-server       # pick a model
#   start-vllm-server --model Qwen/Qwen2.5-7B-Instruct ... # any vllm.entrypoints flags
#
# Common env knobs (defaults in parens):
#   MODEL                  HF repo or local path (Qwen/Qwen2.5-0.5B-Instruct)
#   DTYPE                  bfloat16 | float16 | auto (bfloat16)
#   MAX_MODEL_LEN          context length (4096)
#   GPU_MEM_UTIL           gpu_memory_utilization (0.85)
#   PORT / HOST            8000 / 0.0.0.0
#   TENSOR_PARALLEL_SIZE   TP degree (1)
#   EXTRA_ARGS             passthrough to vllm.entrypoints.openai.api_server
# ---------------------------------------------------------------------------

set -euo pipefail

: "${MODEL:=Qwen/Qwen2.5-0.5B-Instruct}"
: "${DTYPE:=bfloat16}"
: "${MAX_MODEL_LEN:=4096}"
: "${GPU_MEM_UTIL:=0.85}"
: "${PORT:=8000}"
: "${HOST:=0.0.0.0}"
: "${TENSOR_PARALLEL_SIZE:=1}"
: "${EXTRA_ARGS:=}"

# Strix Halo defaults are baked into the image ENV; re-export defensively in
# case the operator overrode them on `docker run`.
export VLLM_USE_TRITON_FLASH_ATTN="${VLLM_USE_TRITON_FLASH_ATTN:-1}"
export FLASH_ATTENTION_TRITON_AMD_ENABLE="${FLASH_ATTENTION_TRITON_AMD_ENABLE:-TRUE}"

echo "[start-vllm-server] model=${MODEL} dtype=${DTYPE} max_len=${MAX_MODEL_LEN}"
echo "[start-vllm-server] host=${HOST} port=${PORT} tp=${TENSOR_PARALLEL_SIZE}"

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
