#!/usr/bin/env bash
# Host-side orchestration around the in-image `server` + `bench` scripts.
#
# All real benchmark logic lives in /usr/local/bin/{server,bench} inside the
# auplc-vllm image (sources at dockerfiles/VLLM/{server,bench}.sh). This
# wrapper only:
#   1. boots the container with `server` (detached) — or skips it for
#      MODE=throughput where bench runs offline in its own container.
#   2. waits up to MAX_WAIT seconds for /v1/models to answer 200 (so we
#      benchmark a steady-state engine, not the cold-start path).
#   3. `docker exec`s `bench` against the in-container server, so client
#      and server share the exact same vLLM build and talk over loopback.
#   4. tears the container down + dumps server log to ./results/.
#
# Usage (env-driven knobs identical to the in-image scripts):
#   ./run_qwen3_4b_throughput.sh                       # default: serve
#   MODE=throughput  ./run_qwen3_4b_throughput.sh      # offline throughput
#   NUM_PROMPTS=200  ./run_qwen3_4b_throughput.sh
#   REQUEST_RATE=4 NUM_PROMPTS=200 ./run_qwen3_4b_throughput.sh
set -euo pipefail

: "${IMAGE:=ghcr.io/amdresearch/auplc-vllm:latest}"
: "${MODEL:=Qwen/Qwen3-4B}"
: "${MODE:=serve}"                       # serve | throughput
: "${INPUT_LEN:=1024}"
: "${OUTPUT_LEN:=512}"
: "${NUM_PROMPTS:=500}"
: "${REQUEST_RATE:=inf}"
: "${MAX_CONCURRENCY:=}"
: "${MAX_MODEL_LEN:=2048}"
: "${DTYPE:=bfloat16}"
: "${GPU_MEM_UTIL:=0.90}"
: "${HOST_PORT:=8000}"
: "${MAX_WAIT:=600}"
: "${HF_CACHE:=${HOME}/.cache/huggingface}"
: "${OUT_DIR:=$(cd "$(dirname "$0")" && pwd)/results}"

mkdir -p "${OUT_DIR}" "${HF_CACHE}"
STAMP="$(date +%Y%m%d-%H%M%S)"
TAG="qwen3-4b-${MODE}-${STAMP}"
LOG="${OUT_DIR}/${TAG}.log"
SERVER_LOG="${OUT_DIR}/${TAG}.server.log"
JSON_NAME="${TAG}.json"
CTR_NAME="auplc-vllm-bench-${STAMP}-$$"

# Knobs forwarded into the container — `server` and `bench` both read these.
COMMON_ENV=(
    -e HF_HOME=/root/.cache/huggingface
    -e HUGGINGFACE_HUB_CACHE=/root/.cache/huggingface/hub
    -e FLASH_ATTENTION_TRITON_AMD_ENABLE=TRUE
    -e HIP_VISIBLE_DEVICES=0
    -e HSA_OVERRIDE_GFX_VERSION=11.5.1
    -e MODEL="${MODEL}"
    -e DTYPE="${DTYPE}"
    -e MAX_MODEL_LEN="${MAX_MODEL_LEN}"
    -e GPU_MEM_UTIL="${GPU_MEM_UTIL}"
    -e INPUT_LEN="${INPUT_LEN}"
    -e OUTPUT_LEN="${OUTPUT_LEN}"
    -e NUM_PROMPTS="${NUM_PROMPTS}"
    -e REQUEST_RATE="${REQUEST_RATE}"
    -e MAX_CONCURRENCY="${MAX_CONCURRENCY}"
    -e RESULT_DIR=/results
    -e RESULT_FILENAME="${JSON_NAME}"
)
COMMON_DOCKER=(
    --device=/dev/kfd --device=/dev/dri
    --group-add=render --group-add=video
    --security-opt seccomp=unconfined --cap-add=SYS_PTRACE
    --ipc=host --shm-size=8g --user 0:0
    -v "${HF_CACHE}:/root/.cache/huggingface"
    -v "${OUT_DIR}:/results"
)

echo "[bench] image=${IMAGE}"
echo "[bench] model=${MODEL}  mode=${MODE}  in=${INPUT_LEN}  out=${OUTPUT_LEN}  N=${NUM_PROMPTS}"
echo "[bench] log        -> ${LOG}"
echo "[bench] server log -> ${SERVER_LOG}"
echo "[bench] json       -> ${OUT_DIR}/${JSON_NAME}"

rocm-smi --showproductname --showmeminfo vram 2>/dev/null || true

cleanup() {
    if docker ps -a --format '{{.Names}}' | grep -qx "${CTR_NAME}"; then
        echo "[bench] tearing down container ${CTR_NAME}"
        docker logs "${CTR_NAME}" >"${SERVER_LOG}" 2>&1 || true
        docker rm -f "${CTR_NAME}" >/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

# ----------------------------------------------------------------------------
# offline throughput: one container, runs `bench` in MODE=throughput, exits.
# ----------------------------------------------------------------------------
if [[ "${MODE}" == "throughput" ]]; then
    docker run --rm \
        --name "${CTR_NAME}" \
        "${COMMON_DOCKER[@]}" \
        "${COMMON_ENV[@]}" \
        -e MODE=throughput \
        "${IMAGE}" \
        bench 2>&1 | tee "${LOG}"

    echo
    echo "[bench] === summary (offline throughput) ==="
    grep -E "Throughput|requests/s|tokens/s|Total num" "${LOG}" || true
    echo "[bench] full log: ${LOG}"
    echo "[bench] json    : ${OUT_DIR}/${JSON_NAME}"
    exit 0
fi

# ----------------------------------------------------------------------------
# online serve: detached `server` + `docker exec bench`.
# ----------------------------------------------------------------------------
echo "[bench] booting in-image \`server\` in container ${CTR_NAME}"
docker run -d \
    --name "${CTR_NAME}" \
    "${COMMON_DOCKER[@]}" \
    -p "${HOST_PORT}:8000" \
    "${COMMON_ENV[@]}" \
    "${IMAGE}" \
    server >/dev/null

echo "[bench] waiting up to ${MAX_WAIT}s for /v1/models on host:${HOST_PORT} ..."
deadline=$(( $(date +%s) + MAX_WAIT ))
ready=0
while (( $(date +%s) < deadline )); do
    if ! docker ps --format '{{.Names}}' | grep -qx "${CTR_NAME}"; then
        echo "[bench] ERROR: server container exited before becoming ready" >&2
        docker logs --tail 80 "${CTR_NAME}" >&2 || true
        exit 3
    fi
    if curl -fsS "http://127.0.0.1:${HOST_PORT}/v1/models" >/dev/null 2>&1; then
        ready=1
        break
    fi
    sleep 3
done
if (( ready == 0 )); then
    echo "[bench] ERROR: server did not come up within ${MAX_WAIT}s" >&2
    docker logs --tail 120 "${CTR_NAME}" >&2 || true
    exit 4
fi
echo "[bench] server is up; running in-image \`bench\`"

# bench runs inside the same container -> talks to the server over loopback,
# uses the exact same vLLM build, and writes JSON to the bind-mounted /results.
# WAIT_FOR_SERVER=0 because we already polled from the host above.
docker exec \
    -e MODE=serve \
    -e BASE_URL=http://127.0.0.1:8000 \
    -e WAIT_FOR_SERVER=0 \
    "${CTR_NAME}" \
    bench 2>&1 | tee "${LOG}"

echo
echo "[bench] === summary (online serve) ==="
sed -n '/Serving Benchmark Result/,/^=\{20,\}/p' "${LOG}" || true
echo "[bench] full log : ${LOG}"
echo "[bench] server   : ${SERVER_LOG}"
echo "[bench] json     : ${OUT_DIR}/${JSON_NAME}"
