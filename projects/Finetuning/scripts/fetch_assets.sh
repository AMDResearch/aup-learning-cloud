#!/usr/bin/env bash
# Copyright(C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
#
# WORKSHOP USER script -- runs INSIDE your notebook server, needs NO sudo and NO kubectl.
#
# Makes the workshop's large inputs (BF16 base checkpoint + LIBERO dataset + fine-tuned checkpoint)
# available to the notebooks WITHOUT downloading anything. Your instructor pre-stages the assets once
# on the machine and mounts them read-only into your server; this wires them into the caches the
# notebooks read. It runs automatically when your server starts, and is safe to re-run by hand.
#
# It handles the two layouts the instructor may have staged:
#   (1) UNPACKED read-only shared tree (recommended, ZERO-COPY) at $ASSETS_SRC:
#         hf_hub/<models--...|datasets--...>/     checkpoints/reference/pretrained_model/
#       -> we SYMLINK these into your cache. Nothing is copied; startup is instant.
#   (2) the split-tar bundle (base/ libero/ tokenizer/ droid_dataset/ ft_checkpoint/):
#       -> we extract it into your cache and rebuild the fine-tuned checkpoint from base + delta.
#
# Everything lands where the notebooks look:
#   $HF_HOME/hub                                              (models--*, datasets--*)
#   $REFERENCE_POLICY (checkpoints/reference/pretrained_model)   the fine-tuned policy
#
# Usage:
#   scripts/fetch_assets.sh                 # auto-detects the mounted source
#   ASSETS_SRC=/path/to/assets scripts/fetch_assets.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${PY:-/opt/train-venv/bin/python}"
HF_HOME="${HF_HOME:-$HOME/.cache/huggingface}"
HUB="$HF_HOME/hub"
REFERENCE_POLICY="${REFERENCE_POLICY:-$HOME/checkpoints/reference/pretrained_model}"
REF_PARENT="$(dirname "$REFERENCE_POLICY")"

# Resolve the source. Explicit ASSETS_SRC wins; otherwise probe the usual mount points, preferring
# the UNPACKED read-only tree (zero-copy) over the split-tar bundle.
ASSETS_SRC="${ASSETS_SRC:-${1:-}}"
if [ -z "$ASSETS_SRC" ]; then
  for cand in \
    /opt/auplc-assets/assets \
    /opt/auplc-assets/mm2_workshop_assets \
    /mnt/workshop-assets/assets \
    /mnt/workshop-assets/mm2_workshop_assets \
    /mnt/workshop-assets \
    "$HOME/mm2_workshop_assets" \
    "$HOME/mm2_asset_bundle"; do
    if [ -d "$cand" ]; then ASSETS_SRC="$cand"; break; fi
  done
fi

if [ -z "$ASSETS_SRC" ] || [ ! -d "$ASSETS_SRC" ]; then
  cat >&2 <<EOF
No workshop assets found.
  Set ASSETS_SRC to where your instructor mounted them, e.g.:
    ASSETS_SRC=/opt/auplc-assets/assets scripts/fetch_assets.sh
  (If assets are not staged, the notebooks will download from Hugging Face at run time
   instead -- that needs network access and takes a while.)
EOF
  exit 2
fi

echo "fetching workshop assets"
echo "  source           = $ASSETS_SRC"
echo "  HF_HOME          = $HF_HOME"
echo "  REFERENCE_POLICY = $REFERENCE_POLICY"
mkdir -p "$HUB" "$REF_PARENT"

_have() {  # dir non-empty (follows symlinks)?
  [ -d "$1" ] && [ -n "$(ls -A "$1" 2>/dev/null || true)" ]
}

_stage_ref_from() {  # <src pretrained_model dir>
  local src="$1"
  if [ -f "$REFERENCE_POLICY/model.safetensors" ] || { [ -L "$REFERENCE_POLICY" ] && [ -f "$REFERENCE_POLICY/model.safetensors" ]; }; then
    echo "  -> fine-tuned checkpoint: already present, skipping"; return 0
  fi
  if [ -f "$src/model.safetensors" ]; then
    # Full checkpoint already reconstructed on the shared store -> zero-copy symlink.
    rm -rf "$REFERENCE_POLICY" 2>/dev/null || true
    ln -sfn "$src" "$REFERENCE_POLICY"
    echo "  -> linked fine-tuned checkpoint (zero-copy)"
  else
    # Only a delta present -> copy locally (writable) and rebuild the full checkpoint.
    echo "  -> fine-tuned checkpoint is a delta; copying + rebuilding locally"
    mkdir -p "$REFERENCE_POLICY"; cp -a "$src/." "$REFERENCE_POLICY/"
    "$PY" "$HERE/reconstruct_reference.py" \
      --delta "$REFERENCE_POLICY" --out "$REFERENCE_POLICY" --hf-home "$HF_HOME"
  fi
}

# ------------------------------------------------- (1) unpacked read-only tree (zero-copy) -------
if [ -d "$ASSETS_SRC/hf_hub" ]; then
  echo "  detected unpacked tree -- linking (zero-copy, nothing is copied)"
  for d in "$ASSETS_SRC"/hf_hub/*/; do
    [ -d "$d" ] || continue
    name="$(basename "${d%/}")"
    if _have "$HUB/$name"; then echo "  -> $name: present, skipping"; else
      ln -sfn "${d%/}" "$HUB/$name"; echo "  -> linked $name"
    fi
  done
  [ -d "$ASSETS_SRC/checkpoints/reference/pretrained_model" ] && \
    _stage_ref_from "$ASSETS_SRC/checkpoints/reference/pretrained_model"

# ------------------------------------------------------------------- (2) split-tar bundle -------
elif ls "$ASSETS_SRC"/base/base.tar.part-* >/dev/null 2>&1; then
  echo "  detected split-tar bundle -- extracting into your cache"
  _untar_hub() {  # <expected-cache-dirname> <parts...>
    local name="$1"; shift
    if _have "$HUB/$name"; then echo "  -> $name: already present, skipping"; return 0; fi
    echo "  -> $name (into HF cache)"; cat "$@" | tar -C "$HUB" -xf -
  }
  _untar_hub models--allenai--MolmoAct2-DROID            "$ASSETS_SRC"/base/base.tar.part-*
  _untar_hub datasets--allenai--MolmoAct2-LIBERO-Dataset "$ASSETS_SRC"/libero/libero.tar.part-*
  echo "  -> tokenizer (into HF cache)"; tar -C "$HUB" -xf "$ASSETS_SRC"/tokenizer/tokenizer.tar
  if ls "$ASSETS_SRC"/droid_dataset/droid_dataset.tar.part-* >/dev/null 2>&1; then
    _untar_hub datasets--allenai--MolmoAct2-DROID-Dataset "$ASSETS_SRC"/droid_dataset/droid_dataset.tar.part-*
  fi
  if [ -f "$REFERENCE_POLICY/model.safetensors" ]; then
    echo "  -> fine-tuned checkpoint: already built, skipping"
  else
    echo "  -> fine-tuned checkpoint delta (-> $REF_PARENT)"
    cat "$ASSETS_SRC"/ft_checkpoint/ft.tar.part-* | tar -C "$REF_PARENT" -xf -
    echo "  -> rebuilding full fine-tuned checkpoint from BF16 base + delta"
    "$PY" "$HERE/reconstruct_reference.py" \
      --delta "$REFERENCE_POLICY" --out "$REFERENCE_POLICY" --hf-home "$HF_HOME"
  fi

else
  echo "ERROR: $ASSETS_SRC has neither hf_hub/ nor base/base.tar.part-* -- unknown layout." >&2
  exit 2
fi

# LeRobot (Step-4 fine-tune) resolves datasets under $HF_LEROBOT_HOME/{repo_id}, NOT the HF hub
# cache. Expose the hub-cached LIBERO dataset there via a symlink so offline training reads the same
# blobs instead of re-downloading 33 GB.
LEROBOT_HOME="${HF_LEROBOT_HOME:-$HF_HOME/lerobot}"
_link_lerobot_dataset() {  # <hub-cache-dirname> <repo_id>
  local hubname="$1" repo="$2" snap
  snap="$(ls -d "$HUB/$hubname"/snapshots/*/ 2>/dev/null | head -1)"
  [ -n "$snap" ] || { echo "  WARN: no snapshot for $hubname; LeRobot link skipped"; return 0; }
  mkdir -p "$LEROBOT_HOME/$(dirname "$repo")"
  ln -sfn "${snap%/}" "$LEROBOT_HOME/$repo"
  echo "  -> LeRobot dataset link: $LEROBOT_HOME/$repo"
}
_link_lerobot_dataset datasets--allenai--MolmoAct2-LIBERO-Dataset allenai/MolmoAct2-LIBERO-Dataset

echo "=== verify ==="
ls -ld "$HUB"/models--allenai--MolmoAct2-DROID            2>/dev/null || true
ls -ld "$HUB"/datasets--allenai--MolmoAct2-LIBERO-Dataset 2>/dev/null || true
ls -ld "$REFERENCE_POLICY"                                2>/dev/null || true
if [ -f "$REFERENCE_POLICY/config.json" ]; then
  echo "fine-tuned checkpoint: config.json present"
else
  echo "WARN: $REFERENCE_POLICY/config.json missing"
fi
echo "done -- open the notebooks and Run All; downloads are skipped (assets already staged)."
