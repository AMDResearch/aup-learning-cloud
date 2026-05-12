#!/usr/bin/env bash
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
#
# Interactive CLI chat client for the in-image vLLM OpenAI-compatible server.
# Pairs with /usr/local/bin/server (and /usr/local/bin/bench).
#
# Designed to be run *inside* the auplc-vllm container, e.g.:
#
#   # interactive REPL against the server in the same container:
#   docker exec -it <ctr> chat
#
#   # one-shot prompt (non-interactive, also great in pipelines):
#   docker exec <ctr> chat "List three differences between RDNA and CDNA."
#   echo "Translate to Klingon: hello world" | docker exec -i <ctr> chat
#
#   # against a server elsewhere (e.g. host network or a different pod):
#   docker exec -e BASE_URL=http://10.0.0.5:8000 -it <ctr> chat
#
#   # with a system prompt + custom model:
#   docker exec -e SYSTEM_PROMPT="You are a terse RDNA-3 ISA expert." \
#               -e MODEL=Qwen/Qwen3-4B -it <ctr> chat
#
# Modes:
#   REPL (default)   — multi-turn conversation, Ctrl-D / Ctrl-C to exit.
#   One-shot         — pass a prompt as positional args OR pipe via stdin;
#                      script auto-detects, sends it once, prints the
#                      streamed answer, then exits.
#
# All knobs are env-driven; any extra flags are forwarded verbatim to
# `vllm chat` (e.g. --api-key, --url override).
set -euo pipefail

: "${MODEL:=}"                              # empty -> auto-pick first /v1/models
: "${BASE_URL:=http://127.0.0.1:8000}"      # server (no /v1 suffix; we add it)
: "${SYSTEM_PROMPT:=}"                      # empty -> no system message
: "${API_KEY:=EMPTY}"                       # vLLM accepts anything by default
# server-readiness (same semantics as bench.sh)
: "${WAIT_FOR_SERVER:=1}"
: "${MAX_WAIT:=600}"

URL="${BASE_URL%/}/v1"

# ---------------------------------------------------------------------------
# Wait for the server. Skip if WAIT_FOR_SERVER=0.
# ---------------------------------------------------------------------------
if [[ "${WAIT_FOR_SERVER}" == "1" ]]; then
    if ! curl -fsS "${BASE_URL}/v1/models" >/dev/null 2>&1; then
        echo "[chat] waiting up to ${MAX_WAIT}s for ${BASE_URL}/v1/models ..." >&2
        deadline=$(( $(date +%s) + MAX_WAIT ))
        ready=0
        while (( $(date +%s) < deadline )); do
            if curl -fsS "${BASE_URL}/v1/models" >/dev/null 2>&1; then
                ready=1
                break
            fi
            sleep 2
        done
        if (( ready == 0 )); then
            echo "[chat] ERROR: ${BASE_URL}/v1/models did not respond within ${MAX_WAIT}s" >&2
            echo "[chat] hint: is \`server\` running in this container?" >&2
            exit 4
        fi
    fi
fi

# ---------------------------------------------------------------------------
# Detect one-shot mode:
#   * positional args present  -> join into a single prompt
#   * stdin is a pipe / file   -> read it
#   * else                     -> interactive REPL
# ---------------------------------------------------------------------------
QUICK=""
EXTRA_ARGS=()
if (( $# > 0 )); then
    # If the first arg starts with `-`, treat the entire $@ as flag pass-through
    # to `vllm chat` (e.g. `chat --api-key foo`). Otherwise treat $@ as the prompt.
    if [[ "$1" == -* ]]; then
        EXTRA_ARGS=("$@")
    else
        QUICK="$*"
    fi
elif [[ ! -t 0 ]]; then
    QUICK="$(cat)"
fi

# ---------------------------------------------------------------------------
# Compose `vllm chat` invocation.
# ---------------------------------------------------------------------------
ARGS=(--url "${URL}" --api-key "${API_KEY}")
[[ -n "${MODEL}" ]]         && ARGS+=(--model-name "${MODEL}")
[[ -n "${SYSTEM_PROMPT}" ]] && ARGS+=(--system-prompt "${SYSTEM_PROMPT}")
[[ -n "${QUICK}" ]]         && ARGS+=(-q "${QUICK}")

if [[ -z "${QUICK}" ]]; then
    echo "[chat] ${URL} (model: ${MODEL:-<auto>}) — Ctrl-D to exit" >&2
fi

exec vllm chat "${ARGS[@]}" "${EXTRA_ARGS[@]}"
