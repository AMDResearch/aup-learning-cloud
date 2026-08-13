#!/usr/bin/env bash
# Copyright(C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
#
# ORGANIZER one-time pre-stage. Run ONCE, before the workshop. Unpacks the split OneDrive bundle
# into a single READ-ONLY shared tree and rebuilds the full fine-tuned checkpoint ONCE, so every
# attendee's server can LINK to it with zero copying (no per-attendee download, no sudo at runtime).
#
# Because it needs the training Python (torch/safetensors) and writes under /opt, run it INSIDE the
# course image as root, e.g.:
#   sudo mkdir -p /opt/auplc-assets/assets
#   docker run --rm --user 0:0 -v /opt/auplc-assets:/opt/auplc-assets \
#     --entrypoint bash ghcr.io/amdresearch/auplc-finetuning:latest \
#     /ryzers/notebooks/scripts/prestage_shared.sh \
#       /opt/auplc-assets/mm2_workshop_assets /opt/auplc-assets/assets
#
# Result layout (world-readable):
#   <ASSETS_DIR>/hf_hub/<models--...|datasets--...>/
#   <ASSETS_DIR>/checkpoints/reference/pretrained_model/   (FULL, reconstructed model.safetensors)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${PY:-/opt/train-venv/bin/python}"
command -v "$PY" >/dev/null 2>&1 || PY="python3"

BUNDLE="${1:?usage: prestage_shared.sh <BUNDLE_DIR> [ASSETS_DIR]}"
ASSETS_DIR="${2:-$(dirname "$BUNDLE")/assets}"
[ -d "$BUNDLE" ] || { echo "ERROR: bundle dir not found: $BUNDLE" >&2; exit 2; }

echo "pre-staging shared read-only assets"
echo "  bundle     = $BUNDLE"
echo "  assets dir = $ASSETS_DIR"

# 1) Unpack the split-tar bundle into hf_hub/ + checkpoints/reference/pretrained_model (delta).
"$HERE/unpack_bundle.sh" "$BUNDLE" "$ASSETS_DIR"

# 2) Rebuild the FULL fine-tuned checkpoint ONCE from the BF16 base + delta, in place.
REF="$ASSETS_DIR/checkpoints/reference/pretrained_model"
if [ -f "$REF/model.safetensors" ]; then
  echo "  reference checkpoint already reconstructed, skipping"
else
  echo "  rebuilding full fine-tuned checkpoint (BF16 base + delta) ..."
  "$PY" "$HERE/reconstruct_reference.py" --delta "$REF" --out "$REF" --hub "$ASSETS_DIR/hf_hub"
fi

# 3) Make the whole tree world-readable so attendee pods (non-root) can read it.
chmod -R a+rX "$ASSETS_DIR"

echo "done. Shared assets ready at: $ASSETS_DIR"
echo "The installer mounts $(dirname "$ASSETS_DIR") read-only into every server; attendees do nothing."
