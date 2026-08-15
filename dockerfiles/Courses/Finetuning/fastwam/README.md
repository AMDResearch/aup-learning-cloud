### FastWAM

This package runs [FastWAM](https://github.com/yuantianyuan01/FastWAM) — a Wan2.2-TI2V-5B
world-action model (T5 text encoder + Wan VAE + video/action DiT) — on AMD Ryzen AI Max+
395 (Strix Halo, `gfx1151`) under ROCm 7.2.2. Direct PyTorch port: upstream code runs on
the base image's ROCm torch; only the CUDA torch pins are stripped.

It is a **slim policy/model layer that ships no simulator**, and the reference consumer of
the simulator packages' `Policy` seam. It composes on:

- the plain ROCm base &rarr; non-sim demos (smoke / latency / open-loop / videogen);
- the `simulation/libero` base &rarr; closed-loop + interactive LIBERO;
- the `simulation/robotwin` base &rarr; closed-loop + interactive RoboTwin 2.0.

The same policy layer composes on all three because the FastWAM install is pinned to the
base image's torch + numpy (so a plain base's numpy 2.x and a sim base's numpy 1.26.4 both
work). Weights/datasets are fetched by the scripts below; sim assets come from the sim base.

### Build

```sh
# Standalone (non-sim demos + model sign-of-life):
ryzers build fastwam --name fastwam
ryzers run --name fastwam                 # test.py: ROCm torch + GPU + deps sign-of-life

# Chain on a simulator base for closed-loop / interactive rollouts:
ryzers build libero   fastwam --name fastwam-libero
ryzers build robotwin fastwam --name fastwam-robotwin
```

Artifacts are written to `workspace/*/outputs`. For faster/gated HF downloads set
`HF_TOKEN`. The ~12 GB Wan2.2 base is fetched automatically on the first model run.

```sh
ryzers run --name fastwam /ryzers/scripts/download_checkpoints.sh    # LIBERO + RoboTwin ckpts
ryzers run --name fastwam /ryzers/scripts/download_datasets.sh       # open-loop / video data
```

The chain drives a sim base's model-agnostic `Policy` seam via a runtime adapter
(`adapters/fastwam_{libero,robotwin}_policy.py`, selected by `POLICY_FACTORY`); these
adapters double as the worked reference for wiring any VLA/WAM into the sim bases (see each
`simulation/*` README). The RoboTwin closed-loop instead runs RoboTwin's own
`script/eval_policy.py` against `experiments/robotwin/fastwam_policy`
(`EVALUATION.robotwin_root=/opt/RoboTwin`).

### Demos

| Demo | Base | What it does |
|---|---|---|
| `demos/demo_smoke.sh` | plain | Load checkpoint, one `infer_action`; cold/steady latency + VRAM. |
| `demos/demo_latency.sh` | plain | Per-part latency (T5 / VAE / world prefill / plan) + SDPA backends. |
| `demos/demo_openloop.sh` | plain | Replay GT observations, overlay predicted vs GT action chunks + MAE. |
| `demos/demo_videogen.sh` | plain | Imagine future frames from the first observation; GT-vs-imagined clips. |
| `demos/demo_closedloop_libero.sh` | `libero` | Closed-loop LIBERO rollouts (MuJoCo/EGL) + success rate. |
| `demos/demo_interactive_libero.sh` / `_rt.sh` | `libero` | Interactive LIBERO over HTTP/MJPEG. |
| `demos/demo_closedloop_robotwin.sh` | `robotwin` | Closed-loop RoboTwin 2.0 rollouts (SAPIEN Vulkan RT) + success rate. |
| `demos/demo_interactive_robotwin.sh` / `_rt.sh` | `robotwin` | Interactive RoboTwin over HTTP/MJPEG. |

```sh
ryzers run --name fastwam        /ryzers/demos/demo_smoke.sh
ryzers run --name fastwam-libero /ryzers/demos/demo_closedloop_libero.sh
TASKS="click_bell lift_pot" NUM_EPISODES=10 \
  ryzers run --name fastwam-robotwin /ryzers/demos/demo_closedloop_robotwin.sh
ryzers run --name fastwam-robotwin /ryzers/demos/demo_interactive_robotwin.sh   # http://localhost:8082
```

### Open-loop replay

Predicted action chunks track ground truth over 100 episodes: mean normalized MAE
**0.0222** (LIBERO) / **0.0208** (RoboTwin), action inference ~1.5 s.

<p align="center">
  <img src="assets/d1_libero_per_dim_mae.png" alt="open-loop per-dim MAE, LIBERO" width="700">
  <br><em>Per-dimension normalized MAE (LIBERO).</em>
</p>
<p align="center">
  <img src="assets/d1_libero_ep00.png" alt="open-loop GT-vs-pred overlay, LIBERO episode 0" width="700">
  <br><em>GT (solid) vs predicted (dashed) action chunks, LIBERO episode 0.</em>
</p>

### Video imagination

Joint path imagines the future video + actions (GT left, imagined right). Steady-state
joint latency ~18.6 s (LIBERO) / ~21.9 s (RoboTwin) for a 33-frame clip at 20 denoise
steps (the first call pays a one-time ROCm warmup).

<p align="center">
  <img src="assets/d2_libero.gif" alt="GT vs imagined, LIBERO" width="600">
  <br><em>Ground truth vs imagined future (LIBERO).</em>
</p>
<p align="center">
  <img src="assets/d2_robotwin.gif" alt="GT vs imagined, RoboTwin" width="600">
  <br><em>Ground truth vs imagined future (RoboTwin).</em>
</p>

### Closed-loop LIBERO

`libero_object` suite, 10 tasks × 20 trials: **199/200 (99.5%)** success, rendered headless
via EGL. With `VISUALIZE_FUTURE=true` the slow path also renders the model's imagined future
alongside the real rollout (GT left, imagined right; PSNR ~27.3 dB).

<p align="center">
  <img src="assets/d3_libero.gif" alt="closed-loop LIBERO rollout" width="400">
  <img src="assets/d4_slow.gif" alt="closed-loop slow path, GT vs imagined" width="400">
  <br><em>Closed-loop rollout (left) and slow-path GT-vs-imagined (right).</em>
</p>

### Useful knobs

- Non-sim: `DATASET=libero|robotwin` (open-loop/videogen/latency), `NUM_STEPS`, `SEED`.
- Closed-loop LIBERO: `SUITE`, `NUM_TASKS`, `NUM_TRIALS`, `VISUALIZE_FUTURE`.
- Closed-loop RoboTwin: `TASKS`, `TASK_CONFIG`, `NUM_EPISODES`.
- Interactive: `PORT`, `CKPT`, `DATASET_STATS`, `REPLAN_STEPS`, `NUM_INFERENCE_STEPS`.
- `HF_TOKEN` for faster/gated downloads.

### References

- Upstream: https://github.com/yuantianyuan01/FastWAM (pinned in `docs/UPSTREAM_PIN.commit.txt`)
- Model: https://huggingface.co/yuanty/fastwam
- Datasets: https://huggingface.co/datasets/yuanty/LIBERO-fastwam · https://huggingface.co/datasets/yuanty/robotwin2.0-fastwam

Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
SPDX-License-Identifier: MIT
