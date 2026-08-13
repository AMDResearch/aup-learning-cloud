#!/usr/bin/env bash
# Copyright(C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Stage workshop assets from a local resources directory into the Hugging Face cache and the
# fine-tuned-checkpoint location, so the notebooks do NOT re-download anything from the Hub.
#
# The workshop hosts three large items on local storage (e.g. copied from OneDrive):
#   - base checkpoint   allenai/MolmoAct2-DROID          (HF model cache)
#   - dataset           allenai/MolmoAct2-LIBERO-Dataset (HF dataset cache)
#   - fine-tuned policy our LoRA checkpoint              (REFERENCE_POLICY)
# plus small helpers (the FAST tokenizer, and optionally the DROID-Dataset used by the Step-3
# open-loop check). This script copies whatever is present; it is idempotent (skips items that
# already exist) and preserves the HF cache symlink layout.
#
# Expected ASSETS_DIR layout:
#   <ASSETS_DIR>/hf_hub/<models--...|datasets--...>/   -> copied into $HF_HOME/hub/
#   <ASSETS_DIR>/checkpoints/reference/pretrained_model -> copied into $REFERENCE_POLICY
#
# Usage:
#   ASSETS_DIR=/path/to/assets ./stage_assets.sh
#   ./stage_assets.sh /path/to/assets
# Optional overrides: HF_HOME, REFERENCE_POLICY.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${PY:-/opt/train-venv/bin/python}"
ASSETS_DIR="${1:-${ASSETS_DIR:-}}"
HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
REFERENCE_POLICY="${REFERENCE_POLICY:-$HOME/checkpoints/reference/pretrained_model}"

if [ -z "$ASSETS_DIR" ]; then
  echo "ERROR: ASSETS_DIR not set (pass as \$1 or env). Nothing to stage." >&2
  exit 2
fi
if [ ! -d "$ASSETS_DIR" ]; then
  echo "ERROR: ASSETS_DIR not found: $ASSETS_DIR" >&2
  exit 2
fi

echo "staging assets from: $ASSETS_DIR"
echo "  HF_HOME          = $HF_HOME"
echo "  REFERENCE_POLICY = $REFERENCE_POLICY"

_copy() {  # src dst
  local src="$1" dst="$2"
  [ -e "$src" ] || return 0
  if [ -d "$dst" ] && [ -n "$(ls -A "$dst" 2>/dev/null || true)" ]; then
    echo "  skip (exists) $dst"
    return 0
  fi
  mkdir -p "$(dirname "$dst")"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a "$src/" "$dst/"
  else
    cp -a "$src/." "$dst/"
  fi
  echo "  staged        $dst"
}

# 1) Hugging Face hub cache (models + datasets) -> $HF_HOME/hub
if [ -d "$ASSETS_DIR/hf_hub" ]; then
  mkdir -p "$HF_HOME/hub"
  for d in "$ASSETS_DIR"/hf_hub/*/; do
    [ -d "$d" ] || continue
    _copy "${d%/}" "$HF_HOME/hub/$(basename "$d")"
  done
else
  echo "  (no hf_hub/ in ASSETS_DIR - skipping HF cache staging)"
fi

# 2) Fine-tuned reference checkpoint -> $REFERENCE_POLICY
# It ships as a small "delta" (LoRA adapter + trained action-expert) plus a map of the frozen
# tensors it dropped; rebuild the full checkpoint from the BF16 base staged in step 1.
if [ -d "$ASSETS_DIR/checkpoints/reference/pretrained_model" ]; then
  _copy "$ASSETS_DIR/checkpoints/reference/pretrained_model" "$REFERENCE_POLICY"
  if [ ! -f "$REFERENCE_POLICY/model.safetensors" ]; then
    echo "  rebuilding full fine-tuned checkpoint from BF16 base + delta"
    "$PY" "$HERE/reconstruct_reference.py" \
      --delta "$REFERENCE_POLICY" --out "$REFERENCE_POLICY" --hf-home "$HF_HOME"
  fi
else
  echo "  (no checkpoints/reference/pretrained_model in ASSETS_DIR - skipping)"
fi

# 3) LeRobot (Step-4 fine-tune) resolves datasets under $HF_LEROBOT_HOME/{repo_id}, NOT the standard
# HF hub cache. Link the hub-cached LIBERO dataset there so offline training reuses the same blobs
# instead of re-downloading 33 GB.
LEROBOT_HOME="${HF_LEROBOT_HOME:-$HF_HOME/lerobot}"
_snap="$(ls -d "$HF_HOME"/hub/datasets--allenai--MolmoAct2-LIBERO-Dataset/snapshots/*/ 2>/dev/null | head -1)"
if [ -n "$_snap" ]; then
  mkdir -p "$LEROBOT_HOME/allenai"
  ln -sfn "${_snap%/}" "$LEROBOT_HOME/allenai/MolmoAct2-LIBERO-Dataset"
  echo "  LeRobot dataset link: $LEROBOT_HOME/allenai/MolmoAct2-LIBERO-Dataset"
fi

echo "asset staging complete."
