#!/usr/bin/env python3
# Copyright(C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Rebuild the full fine-tuned LeRobot checkpoint (model.safetensors) from the two SPLIT pieces the
# workshop bundle ships:
#   * the BF16 DROID base            (HF hub cache: models--allenai--MolmoAct2-DROID)
#   * the small fine-tune "delta"    (delta.safetensors + base_fill.json + config/processors)
#
# The delta stores only the tensors that actually changed during fine-tuning (the LoRA adapter and
# the trained action-expert); every frozen tensor was dropped and is restored here from the BF16
# base (they are bit-identical to the base cast to BF16, which is verified at build time). The
# result is byte-for-tensor identical to the original merged checkpoint, so the existing loaders
# (`lerobot-eval --policy.path=...` and the interactive server) work unchanged.
#
# Staging scripts call this after extracting the bundle; it is idempotent (skips if already built).
import argparse, glob, json, os, shutil, sys


def _find_base_snapshot(hub, repo_dirname):
    repo = os.path.join(hub, repo_dirname)
    snaps = sorted(glob.glob(os.path.join(repo, "snapshots", "*", "")))
    if not snaps:
        sys.exit(f"reconstruct: base checkpoint not found under {repo}/snapshots/*/ "
                 f"(did the base bundle extract into the HF cache?)")
    return snaps[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delta", required=True, help="dir with delta.safetensors + base_fill.json + config/processors")
    ap.add_argument("--out", required=True, help="output pretrained_model dir the loaders read")
    ap.add_argument("--hf-home", default=os.environ.get("HF_HOME", os.path.expanduser("~/.cache/huggingface")))
    ap.add_argument("--hub", default=None, help="explicit HF hub dir (holds models--*/); defaults to <hf-home>/hub")
    args = ap.parse_args()

    hub = args.hub or os.path.join(args.hf_home, "hub")

    out_model = os.path.join(args.out, "model.safetensors")
    if os.path.exists(out_model) and os.path.getsize(out_model) > 1_000_000_000:
        print(f"reconstruct: {out_model} already present -> skipping")
        return

    import torch
    from safetensors import safe_open
    from safetensors.torch import save_file

    fill = json.load(open(os.path.join(args.delta, "base_fill.json")))
    base_snap = _find_base_snapshot(hub, fill.get("base_repo", "models--allenai--MolmoAct2-DROID"))

    # index the BF16 base shards: base_key -> shard file
    base_key2file = {}
    for f in sorted(glob.glob(os.path.join(base_snap, "*.safetensors"))):
        with safe_open(f, framework="pt") as h:
            for k in h.keys():
                base_key2file[k] = f

    os.makedirs(args.out, exist_ok=True)
    print(f"reconstruct: base={base_snap}")
    print(f"reconstruct: delta={args.delta}  ->  out={out_model}")

    state = {}
    delta_path = os.path.join(args.delta, "delta.safetensors")
    with safe_open(delta_path, framework="pt") as h:
        meta = h.metadata() or {"format": "pt"}
        for k in h.keys():
            state[k] = h.get_tensor(k)
    kept = len(state)

    open_handles = {}
    def _get(bk):
        f = base_key2file[bk]
        if f not in open_handles:
            open_handles[f] = safe_open(f, framework="pt")
        return open_handles[f].get_tensor(bk)

    for ft_key, base_key in fill["fill"].items():
        if base_key not in base_key2file:
            sys.exit(f"reconstruct: base tensor '{base_key}' missing for '{ft_key}'")
        state[ft_key] = _get(base_key).to(torch.bfloat16)

    print(f"reconstruct: {kept} delta tensors + {len(fill['fill'])} from base = {len(state)} total")
    os.makedirs(args.out, exist_ok=True)
    save_file(state, out_model, metadata=meta)

    # copy the small companion files (config, train_config, processors, normalizers)
    for f in os.listdir(args.delta):
        if f in ("delta.safetensors", "base_fill.json"):
            continue
        src = os.path.join(args.delta, f)
        dst = os.path.join(args.out, f)
        if os.path.isfile(src) and os.path.abspath(src) != os.path.abspath(dst):
            shutil.copy2(src, dst)
    # the delta pieces are no longer needed once model.safetensors exists -> drop them so the
    # checkpoint dir matches a normal LeRobot checkpoint (saves ~2.5 GB on the pod)
    for f in ("delta.safetensors", "base_fill.json"):
        p = os.path.join(args.out, f)
        if os.path.exists(p):
            os.remove(p)
    print(f"reconstruct: wrote {out_model} ({os.path.getsize(out_model)/1e9:.2f} GB) and companion files")


if __name__ == "__main__":
    main()
