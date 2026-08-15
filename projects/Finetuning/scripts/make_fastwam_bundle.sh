#!/usr/bin/env bash
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
#
# ORGANIZER helper: pack the FastWAM LIBERO weights into the split-tar bundle that the course
# image bakes (notebook 3). The FastWAM checkpoint + Wan2.2 base are already BF16 (the production
# precision the fast route runs in), so this only selects + tars them - no conversion needed.
#
# It writes <ASSETS_DIR>/fastwam/fastwam.tar.part-* which the Dockerfile's fastwam-staging stage
# reassembles into /opt/fastwam-assets as:
#   fastwam_release/libero_uncond_2cam224.pt            (bf16 action checkpoint, ~12 GB)
#   fastwam_release/libero_uncond_2cam224_dataset_stats.json
#   diffsynth/...                                        (bf16 Wan2.2 base: T5 + VAE + tokenizer, ~12 GB)
#   data/<dataset>/                                      (LIBERO GT episodes for the imagination cell, ~1.3 GB)
#
# Put the resulting fastwam/ subdir next to base/ libero/ tokenizer/ ... inside mm2_workshop_assets,
# then build exactly as before (ASSETS_SRC=/path/to/mm2_workshop_assets); the build bakes it in.
#
# Usage:
#   scripts/make_fastwam_bundle.sh <FASTWAM_MODELS_DIR> <ASSETS_DIR>
# where FASTWAM_MODELS_DIR is the FastWAM `models/` tree (contains fastwam_release/, diffsynth/,
# data/) and ASSETS_DIR is the mm2_workshop_assets folder to add the fastwam/ subdir to.
# Optional: PART_SIZE (default 4000M), DATASET_NAME (default libero_object_no_noops_lerobot).
set -euo pipefail

SRC="${1:?usage: make_fastwam_bundle.sh <FASTWAM_MODELS_DIR> <ASSETS_DIR>}"
ASSETS_DIR="${2:?usage: make_fastwam_bundle.sh <FASTWAM_MODELS_DIR> <ASSETS_DIR>}"
PART_SIZE="${PART_SIZE:-4000M}"
DATASET_NAME="${DATASET_NAME:-libero_object_no_noops_lerobot}"

REL="$SRC/fastwam_release"
CKPT="$REL/libero_uncond_2cam224.pt"
STATS="$REL/libero_uncond_2cam224_dataset_stats.json"
DIFF="$SRC/diffsynth"
DATA_REL="data/$DATASET_NAME"

echo "packing FastWAM bundle"
echo "  source models = $SRC"
echo "  -> assets     = $ASSETS_DIR/fastwam"
for p in "$CKPT" "$STATS"; do
  [ -f "$p" ] || { echo "ERROR: missing file: $p" >&2; exit 2; }
done
[ -d "$DIFF" ]          || { echo "ERROR: missing dir: $DIFF" >&2; exit 2; }
[ -d "$SRC/$DATA_REL" ] || { echo "ERROR: missing dir: $SRC/$DATA_REL" >&2; exit 2; }

DEST="$ASSETS_DIR/fastwam"
mkdir -p "$DEST"
rm -f "$DEST"/fastwam.tar.part-* 2>/dev/null || true

# Stream a tar of ONLY the LIBERO pieces (no robotwin / rt_checkpoints) straight from SRC into
# ~PART_SIZE splits - no intermediate copy, so it needs no extra disk for a second full tree.
# Drop ModelScope/HF download bookkeeping (.msc/.mv/.locks/.cache), the empty scratch dirs
# (._____temp) and any *.incomplete leftovers: none are needed for direct-path loading, and the
# root-owned .msc lock is not even world-readable. This keeps the baked tree clean + reproducible.
tar -C "$SRC" \
  --exclude='*/._____temp' --exclude='*/.______temp' --exclude='*.incomplete' \
  --exclude='*/.msc' --exclude='*/.mv' --exclude='*/.locks' --exclude='*/.cache' \
  -cf - \
  "fastwam_release/libero_uncond_2cam224.pt" \
  "fastwam_release/libero_uncond_2cam224_dataset_stats.json" \
  "diffsynth" \
  "$DATA_REL" \
  | split -b "$PART_SIZE" -d -a 3 - "$DEST/fastwam.tar.part-"

echo "done. parts:"
ls -lh "$DEST"/fastwam.tar.part-*
echo
echo "sanity: this reassembles to fastwam_release/ diffsynth/ data/ under /opt/fastwam-assets"
echo "  cat $DEST/fastwam.tar.part-* | tar -tf - | head"
