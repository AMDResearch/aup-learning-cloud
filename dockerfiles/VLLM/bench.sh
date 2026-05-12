#!/usr/bin/env bash
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
#
# vLLM benchmark client (in-image), pairs with /usr/local/bin/server.
#
# Designed to be run *inside* the auplc-vllm container, e.g.:
#
#   # against the server in the same container:
#   docker exec <ctr> bench
#
#   # offline throughput mode (no server needed):
#   docker run --rm --device=/dev/kfd --device=/dev/dri \
#       -e MODE=throughput -e MODEL=Qwen/Qwen3-4B \
#       -e RESULT_DIR=/results -v $PWD/results:/results \
#       ghcr.io/amdresearch/auplc-vllm:latest bench
#
# Results land in ${RESULT_DIR} (default: ${HOME}/results, always writable
# for the running user). Override RESULT_DIR to mount-bind into a host path.
#
# Modes:
#   serve      (default) — `vllm bench serve` against ${BASE_URL}; emits
#              the full TTFT/TPOT/ITL SLA report. Will poll /v1/models for
#              up to MAX_WAIT seconds before starting.
#   throughput          — `vllm bench throughput` (offline, no server).
#                          Only emits aggregate requests/s & tokens/s.
#
# All knobs are env-driven; any extra positional/flag args are forwarded to
# the underlying `vllm bench …` invocation.
set -euo pipefail

: "${MODE:=serve}"                       # serve | throughput
: "${MODEL:=Qwen/Qwen3-4B}"
: "${BASE_URL:=http://127.0.0.1:8000}"   # serve mode only
: "${INPUT_LEN:=1024}"
: "${OUTPUT_LEN:=512}"
: "${NUM_PROMPTS:=500}"
: "${REQUEST_RATE:=inf}"                 # serve mode: inf = closed-loop
: "${MAX_CONCURRENCY:=}"                 # empty = unbounded
: "${PERCENTILE_METRICS:=ttft,tpot,itl}"
: "${METRIC_PERCENTILES:=50,90,99}"
# throughput-only knobs (ignored in serve mode)
: "${DTYPE:=bfloat16}"
: "${MAX_MODEL_LEN:=2048}"
: "${GPU_MEM_UTIL:=0.90}"
# I/O
# Default lands inside the user's HOME (always writable) instead of /results
# (which is root-owned and unwritable for jovyan / uid 1000). Operators who
# rely on `-v $PWD/results:/results` can still override with RESULT_DIR=/results.
: "${RESULT_DIR:=${HOME:-/tmp}/results}"
: "${RESULT_FILENAME:=qwen3-4b-${MODE}-$(date +%Y%m%d-%H%M%S).json}"
# server-readiness
: "${WAIT_FOR_SERVER:=1}"                # serve mode only
: "${MAX_WAIT:=600}"

mkdir -p "${RESULT_DIR}"

echo "[bench] mode=${MODE} model=${MODEL} in=${INPUT_LEN} out=${OUTPUT_LEN} N=${NUM_PROMPTS}"
if [[ "${MODE}" == "serve" ]]; then
    echo "[bench] base_url=${BASE_URL} rate=${REQUEST_RATE} concurrency=${MAX_CONCURRENCY:-unbounded}"
fi
echo "[bench] result -> ${RESULT_DIR}/${RESULT_FILENAME}"
echo "--- vllm version ---"
python3 -c "import vllm; print(vllm.__version__)"

# Optional --max-concurrency for serve mode.
EXTRA_BENCH_ARGS=()
if [[ "${MODE}" == "serve" && -n "${MAX_CONCURRENCY}" ]]; then
    EXTRA_BENCH_ARGS+=(--max-concurrency "${MAX_CONCURRENCY}")
fi

case "${MODE}" in
    throughput)
        exec vllm bench throughput \
            --model "${MODEL}" \
            --dtype "${DTYPE}" \
            --dataset-name random \
            --random-input-len "${INPUT_LEN}" \
            --random-output-len "${OUTPUT_LEN}" \
            --random-prefix-len 0 \
            --num-prompts "${NUM_PROMPTS}" \
            --max-model-len "${MAX_MODEL_LEN}" \
            --gpu-memory-utilization "${GPU_MEM_UTIL}" \
            --trust-remote-code \
            --output-json "${RESULT_DIR}/${RESULT_FILENAME}" \
            "$@"
        ;;
    serve)
        if [[ "${WAIT_FOR_SERVER}" == "1" ]]; then
            echo "[bench] waiting up to ${MAX_WAIT}s for ${BASE_URL}/v1/models ..."
            deadline=$(( $(date +%s) + MAX_WAIT ))
            ready=0
            while (( $(date +%s) < deadline )); do
                if curl -fsS "${BASE_URL}/v1/models" >/dev/null 2>&1; then
                    ready=1
                    break
                fi
                sleep 3
            done
            if (( ready == 0 )); then
                echo "[bench] ERROR: ${BASE_URL}/v1/models did not respond within ${MAX_WAIT}s" >&2
                exit 4
            fi
            echo "[bench] server is up; starting benchmark"
        fi
        exec vllm bench serve \
            --backend vllm \
            --base-url "${BASE_URL}" \
            --model "${MODEL}" \
            --dataset-name random \
            --random-input-len "${INPUT_LEN}" \
            --random-output-len "${OUTPUT_LEN}" \
            --random-prefix-len 0 \
            --num-prompts "${NUM_PROMPTS}" \
            --request-rate "${REQUEST_RATE}" \
            --percentile-metrics "${PERCENTILE_METRICS}" \
            --metric-percentiles "${METRIC_PERCENTILES}" \
            --save-result \
            --result-dir "${RESULT_DIR}" \
            --result-filename "${RESULT_FILENAME}" \
            "${EXTRA_BENCH_ARGS[@]}" \
            "$@"
        ;;
    *)
        echo "[bench] ERROR: unknown MODE=${MODE} (expected: serve | throughput)" >&2
        exit 2
        ;;
esac
