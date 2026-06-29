<!-- Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved. -->

# MuJoCo (PyTorch) Course

Content for the **MuJoCo (PyTorch)** course (image `auplc-mujoco-torch`:
PyTorch ROCm + mujoco + robosuite + gymnasium + lerobot). It goes from robosuite
fundamentals and classical control, through the Gymnasium API and behavior
cloning, up to fine-tuning a vision-language-action (VLA) foundation model — all
running on AMD ROCm / Strix Halo (gfx1151). The companion JAX/MJX course
(foundations) lives in `../MuJoCo-MJX`.

Each notebook is self-contained and follows the same format (Lab Description /
Recommended Hardware / Software Environment / Goals → concept markdown + runnable
code → inline `Video(...)` / plots → Conclusions / License), and is validated
end-to-end with `jupyter nbconvert --execute` on gfx1151 / ROCm.

## Labs

### Foundations & imitation learning (robosuite)

- `MT01_Robosuite_Intro` — what robosuite is; create a Lift/Panda task, inspect the
  dict observations and the 7-D end-effector action, render reliably, and roll out a
  random policy.
- `MT02_Controllers_and_Cameras` — the operational-space (BASIC) controller and
  named cameras; **script a full reach–grasp–lift pick** (cube lifted ≈0.24 m, task
  reward ≈1.0).
- `MT03_Gymnasium_and_Reward` — wrap a task with `GymWrapper` (the Gymnasium 5-tuple
  API) and visualize the dense (shaped) reward signal over a scripted reach.
- `MT04_Behavior_Cloning` — collect demonstrations from the scripted expert and train
  a PyTorch MLP on the GPU to imitate it; the learned policy reaches the cube (final
  distance ≈0.04 m).

### Vision-language-action fine-tuning

- `MT05_VLA_SmolVLA_Finetune` — take the *same* MT04 scripted-expert demos, record
  image + state + instruction into a **`LeRobotDataset`**, and **fine-tune the
  pretrained SmolVLA** (450M VLA) on the GPU. Contrasts the zero-shot vs. fine-tuned
  policy. The in-notebook fine-tune is **deliberately short** (a few hundred steps):
  the loss falls and the rollout improves, but it is not a finished policy — a usable
  one needs ~10k–20k steps. A **fully-trained checkpoint** baked into the image
  (`/opt/checkpoints/mt05_smolvla_lift`) is loaded in an appendix to show the polished
  result (final distance ≈0.02–0.04 m, on par with the MT04 expert).

## Rendering note (important for this ROCm/EGL stack)

robosuite's built-in camera-observation renderer emits **intermittently corrupted
frames** on gfx1151/EGL. All notebooks therefore render through a `make_renderer` /
`grab_frame` helper that drives `mujoco.Renderer` directly on
`env.sim.model._model` / `env.sim.data._data` and shows only the visual geom group
(group 1) — stable across runs and free of the green/blue collision-shape overlay.
Outputs are written under `output/videos`.

## Models & dependencies

The Dockerfile installs `lerobot==0.5.0` + `transformers==5.3.0` (lerobot 0.5.0
requires transformers ≥5.3.0,<6) on top of `auplc-base`'s ROCm PyTorch. The model
weights are **downloaded at runtime from the public Hugging Face Hub (no token):**
MT05 fetches `lerobot/smolvla_base` + its SmolVLM2 backbone (~2.8 GB, first run only,
then cached under `HF_HOME=/opt/hf`), and the appendix fetches the fully-trained
checkpoint [`sonya-tw/mt05-smolvla-lift`](https://huggingface.co/sonya-tw/mt05-smolvla-lift).
First-run cells therefore need network access.

> Note: AMD flash-attention is still experimental on this stack; the models fall
> back to PyTorch SDPA automatically (optionally enable with
> `TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1`). The MIOpen db warning is harmless.
