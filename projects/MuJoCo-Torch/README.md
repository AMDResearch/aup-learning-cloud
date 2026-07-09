<!-- Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved. -->

# MuJoCo (PyTorch) Course

Content for the **MuJoCo (PyTorch)** course (image `auplc-mujoco-torch`:
PyTorch ROCm + mujoco + robosuite + gymnasium + lerobot). It goes from robosuite
fundamentals and classical control, through the Gymnasium API and behavior
cloning, up to fine-tuning a vision-language-action (VLA) foundation model, and
finally reinforcement learning from scratch (PPO) and cross-domain transfer
(QAvatar) — all running on AMD ROCm / Strix Halo (gfx1151). The companion JAX/MJX
course (foundations) lives in `../MuJoCo-MJX`.

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
  one needs ~10k–20k steps. A **fully-trained checkpoint**
  (`sonya-tw/mt05-smolvla-lift`, baked into the image's HF cache) is loaded in an
  appendix to show the polished result (final distance ≈0.02–0.04 m, on par with the
  MT04 expert).

### Reinforcement learning from scratch (PPO)

- `MT06_RL_PPO` — implement **Proximal Policy Optimization (PPO)** end to end (Gaussian
  actor + value networks, on-policy rollout buffer, Generalized Advantage Estimation,
  clipped-surrogate update) on `2leg_cheetah` (Gymnasium `HalfCheetah-v5`) — no
  demonstrations, no pretrained weights. Following the MT05 pattern, the in-notebook
  training is a **short 50k-step demo** (curves only; still undertrained), and the
  running-gait rollout loads a **fully-trained (baked) 300k-step checkpoint**
  (`cdrl_assets/checkpoints/ppo_cheetah/`). `2leg_cheetah` is wrapped to end the episode
  if the torso flips past ~90° (HalfCheetah doesn't penalize flipping, so PPO otherwise
  learns a high-reward but broken-looking on-its-back gait). An appendix reproduces that
  checkpoint from scratch. Sets up the transfer question answered by MT07. Uses the
  shared RL utilities in `cdrl_code/`.

### Cross-domain reinforcement learning (QAvatar)

- `MT07_Cross_Domain_RL` — transfer a policy across *different* domains with
  **QAvatar**, which reuses a frozen source-domain critic through learned RealNVP
  flows + a decoder, and compares it against a from-scratch **SAC** baseline. Two
  transfer settings: **Part A** locomotion `4leg_ant → 5leg_ant` (MuJoCo) and
  **Part B** manipulation `Door Panda → Door UR5e` (robosuite). Following the MT05
  pattern, the in-notebook training is a **short demo** (mechanics + partial curves);
  the side-by-side rollouts load **fully-trained (baked) checkpoints** (Part A at 300k,
  Part B at 500k steps) where QAvatar clearly outperforms the from-scratch SAC baseline.
  The CDRL implementation ships in `cdrl_code/` and the pretrained weights in
  `cdrl_assets/`, both baked into the image.

## Rendering note (important for this ROCm/EGL stack)

robosuite's built-in camera-observation renderer emits **intermittently corrupted
frames** on gfx1151/EGL. The **robosuite** notebooks (MT01–MT05, and MT07 Part B)
therefore render through a direct `mujoco.Renderer` on `env.sim.model._model` /
`env.sim.data._data` (a `make_renderer` / `grab_frame` helper in MT01–MT05, and the
`_make_rs_renderer` / `_rs_frame` helpers in MT07) showing only the visual geom group
(group 1) — stable across runs and free of the green/blue collision-shape overlay.
The pure-**MuJoCo Gymnasium** environments (MT06's HalfCheetah and MT07 Part A's Ant)
are unaffected and use the standard gym `rgb_array` renderer. Outputs are written
under `output/videos`.

## Models & dependencies

The Dockerfile installs `lerobot==0.5.0` + `transformers==5.3.0` (lerobot 0.5.0
requires transformers ≥5.3.0,<6) on top of `auplc-base`'s ROCm PyTorch. All model
weights MT05 needs are **baked into the image at build time** (into the HF cache at
`HF_HOME=/opt/hf`), so the notebook runs without the ~2.8 GB first-run download and
works offline: `lerobot/smolvla_base`, its SmolVLM2 backbone
(`HuggingFaceTB/SmolVLM2-500M-Video-Instruct`), and the fully-trained checkpoint
[`sonya-tw/mt05-smolvla-lift`](https://huggingface.co/sonya-tw/mt05-smolvla-lift).
The runtime cells still call `snapshot_download` / `from_pretrained`, but these
resolve from the baked cache; network is only needed if you swap in other models.

MT06 (PPO) and MT07 (Cross-Domain RL) add no extra pip dependencies — they run on the
existing torch + mujoco + gymnasium + robosuite stack. The shared RL implementation
(`cdrl_code/`, including the `core/flow` RealNVP modules and the on-policy `PPOBuffer`)
and the pretrained weights (`cdrl_assets/`) live inside `projects/MuJoCo-Torch/` and are
baked into the image by the standard `COPY ./course_data` step. This includes MT07's
source/target QAvatar+SAC checkpoints and MT06's fully-trained PPO checkpoint
(`cdrl_assets/checkpoints/ppo_cheetah/steps_300000.pt`) used for its rollout.

> Note: AMD flash-attention is still experimental on this stack; the models fall
> back to PyTorch SDPA automatically (optionally enable with
> `TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1`). The MIOpen db warning is harmless.
