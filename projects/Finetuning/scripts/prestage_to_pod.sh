#!/usr/bin/env bash
# Copyright(C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Load the offline asset bundle (base checkpoint + LIBERO dataset + fine-tuned checkpoint) from a
# persistent host location DIRECTLY into a running JupyterHub single-user pod, placing everything
# at the paths the notebooks expect:
#   - HF cache          -> /home/jovyan/.cache/huggingface/hub   (models--*, datasets--*)
#   - fine-tuned policy -> /home/jovyan/checkpoints/reference/pretrained_model   (= REFERENCE_POLICY)
#
# The bundle is the split-tar folder produced for OneDrive (base/ libero/ tokenizer/ droid_dataset/
# ft_checkpoint/). Parts are streamed straight into the pod via `kubectl exec ... tar -x`, so files
# are written AS the pod user (correct ownership) and never re-downloaded from the Hub. Idempotent
# at the item level: tar overwrites, so re-running is safe.
#
# Usage:
#   ./prestage_to_pod.sh <BUNDLE_DIR>
# Env overrides:
#   NAMESPACE (default: jupyterhub)   NB_USER (default: student)   POD (default: jupyter-$NB_USER)
#   CONTAINER (default: notebook)
set -euo pipefail

BUNDLE="${1:-${BUNDLE_DIR:-}}"
NS="${NAMESPACE:-jupyterhub}"
NB_USER="${NB_USER:-student}"
POD="${POD:-jupyter-$NB_USER}"
CONTAINER="${CONTAINER:-notebook}"

HUB="/home/jovyan/.cache/huggingface/hub"
REF_PARENT="/home/jovyan/checkpoints/reference"

if [ -z "$BUNDLE" ] || [ ! -d "$BUNDLE" ]; then
  echo "ERROR: bundle dir not found. Usage: $0 <BUNDLE_DIR>" >&2
  exit 2
fi

kx() { kubectl exec -i -n "$NS" "$POD" -c "$CONTAINER" -- "$@"; }

echo "prestaging bundle: $BUNDLE"
echo "  -> pod $NS/$POD ($CONTAINER)"
kubectl get pod -n "$NS" "$POD" >/dev/null   # fail fast if the pod is not running
kx bash -lc "mkdir -p '$HUB' '$REF_PARENT'"

extract() {  # <dest-in-pod> <file...>   (concatenated then untarred inside the pod)
  local dest="$1"; shift
  echo "  loading $(basename "$1" | sed 's/\..*//') -> $dest"
  cat "$@" | kx tar -C "$dest" -xf -
}

# HF cache items (models + datasets) -> hub
extract "$HUB" "$BUNDLE"/base/base.tar.part-*
extract "$HUB" "$BUNDLE"/libero/libero.tar.part-*
extract "$HUB" "$BUNDLE"/tokenizer/tokenizer.tar
if ls "$BUNDLE"/droid_dataset/droid_dataset.tar.part-* >/dev/null 2>&1; then
  extract "$HUB" "$BUNDLE"/droid_dataset/droid_dataset.tar.part-*
fi
# fine-tuned checkpoint -> checkpoints/reference/pretrained_model
# It ships as a small delta (LoRA adapter + trained action-expert); rebuild the full checkpoint
# inside the pod from the BF16 base we just streamed into the HF cache.
extract "$REF_PARENT" "$BUNDLE"/ft_checkpoint/ft.tar.part-*
echo "  rebuilding full fine-tuned checkpoint in pod (BF16 base + delta)"
kx bash -lc '/opt/train-venv/bin/python /ryzers/notebooks/scripts/reconstruct_reference.py \
  --delta /home/jovyan/checkpoints/reference/pretrained_model \
  --out   /home/jovyan/checkpoints/reference/pretrained_model \
  --hf-home /home/jovyan/.cache/huggingface'

# LeRobot (Step-4 fine-tune) resolves datasets under $HF_LEROBOT_HOME/{repo_id}, NOT the HF hub
# cache. Link the hub-cached LIBERO dataset there inside the pod so offline training reuses the same
# blobs rather than re-downloading 33 GB.
kx bash -lc '
  HF_HOME=/home/jovyan/.cache/huggingface
  LEROBOT_HOME="${HF_LEROBOT_HOME:-$HF_HOME/lerobot}"
  snap="$(ls -d "$HF_HOME"/hub/datasets--allenai--MolmoAct2-LIBERO-Dataset/snapshots/*/ 2>/dev/null | head -1)"
  if [ -n "$snap" ]; then
    mkdir -p "$LEROBOT_HOME/allenai"
    ln -sfn "${snap%/}" "$LEROBOT_HOME/allenai/MolmoAct2-LIBERO-Dataset"
    echo "  LeRobot dataset link: $LEROBOT_HOME/allenai/MolmoAct2-LIBERO-Dataset"
  fi
'

echo "=== verify (sizes in pod) ==="
kx bash -lc "
  du -sh '$HUB'/models--allenai--MolmoAct2-DROID 2>/dev/null
  du -sh '$HUB'/datasets--allenai--MolmoAct2-LIBERO-Dataset 2>/dev/null
  du -sh '$HUB'/datasets--allenai--MolmoAct2-DROID-Dataset 2>/dev/null
  du -sh '$REF_PARENT'/pretrained_model 2>/dev/null
  test -f '$REF_PARENT'/pretrained_model/config.json && echo 'reference checkpoint: config.json present' || echo 'WARN: reference config.json missing'
"
echo "prestage complete. The notebooks will now find everything cached (no Hub download)."
