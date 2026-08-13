#!/usr/bin/env bash
# Copyright(C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Reassemble the split OneDrive asset bundle (base/ libero/ tokenizer/ droid_dataset/ ft_checkpoint/)
# into a single ASSETS_DIR layout that stage_assets.sh (or the notebooks' ASSETS_DIR support) expect:
#
#   <ASSETS_DIR>/hf_hub/<models--...|datasets--...>/         (base is the BF16 DROID checkpoint)
#   <ASSETS_DIR>/checkpoints/reference/pretrained_model/     (fine-tune DELTA: adapter + action-expert)
#
# The reference here is only the small fine-tune delta; stage_assets.sh rebuilds the full checkpoint
# from the BF16 base + delta when it stages into the pod. Use this when you want the assets on a host
# directory (e.g. to mount into the pod). To load straight into a running pod, use prestage_to_pod.sh.
#
# Usage:
#   ./unpack_bundle.sh <BUNDLE_DIR> [ASSETS_DIR]    # default ASSETS_DIR=<BUNDLE_DIR>/assets
set -euo pipefail

BUNDLE="${1:?usage: unpack_bundle.sh <BUNDLE_DIR> [ASSETS_DIR]}"
ASSETS_DIR="${2:-$BUNDLE/assets}"
[ -d "$BUNDLE" ] || { echo "ERROR: bundle dir not found: $BUNDLE" >&2; exit 2; }

mkdir -p "$ASSETS_DIR/hf_hub" "$ASSETS_DIR/checkpoints/reference"
echo "unpacking $BUNDLE -> $ASSETS_DIR"

cat "$BUNDLE"/base/base.tar.part-*     | tar -C "$ASSETS_DIR/hf_hub" -xf -
cat "$BUNDLE"/libero/libero.tar.part-* | tar -C "$ASSETS_DIR/hf_hub" -xf -
tar -C "$ASSETS_DIR/hf_hub" -xf "$BUNDLE"/tokenizer/tokenizer.tar
if ls "$BUNDLE"/droid_dataset/droid_dataset.tar.part-* >/dev/null 2>&1; then
  cat "$BUNDLE"/droid_dataset/droid_dataset.tar.part-* | tar -C "$ASSETS_DIR/hf_hub" -xf -
fi
cat "$BUNDLE"/ft_checkpoint/ft.tar.part-* | tar -C "$ASSETS_DIR/checkpoints/reference" -xf -

echo "done -> $ASSETS_DIR"
echo "next: ASSETS_DIR=$ASSETS_DIR <repo>/projects/Finetuning/scripts/stage_assets.sh"
