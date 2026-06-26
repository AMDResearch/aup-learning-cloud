<!-- Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved. -->

# MuJoCo MJX Course

Content for the **MuJoCo MJX** course (image `auplc-mujoco-mjx`, JAX/MJX stack:
jax-rocm + mjx + brax + playground + mujoco + robot_descriptions, no
torch/robosuite). See `../MuJoCo-Torch/PLAN.md` for the full two-image plan.

Labs (Image 1):
- Stage 1 — MuJoCo Foundations (MJX01–03)
  - `MJX01_Concepts_and_MJCF` — mjModel/mjData, MJCF, simulation, rendering
  - `MJX02_Rendering_Cameras_Contacts` — Renderer, cameras, geom groups, contacts
  - `MJX03_Control_and_IK` — joint control + DLS IK on SO-101 and XLeRobot
- Stage 2 — MJX & large-scale parallel simulation (MJX04–05)
  - `MJX04_From_MuJoCo_to_MJX` — jit/vmap batching, CPU vs GPU throughput
  - `MJX05_Parallel_Rollouts_and_Domain_Randomization` — batched rollouts + DR
- Stage 3 — MuJoCo Playground & RL (MJX06–09)
  - `MJX06_RL_Refresher` — MDP/PPO fundamentals
  - `MJX07_Playground_PPO_Control` — Playground PPO on `CartpoleBalance`
  - `MJX08_Playground_PointMass` — Playground PPO on `PointMass`
  - `MJX09_Playground_PandaPickCube` — stabilised PPO on the Franka Panda arm

All RL notebooks use MuJoCo Playground on top of MJX/Brax. On this gfx1151 ROCm
stack they run with `impl="jax"`, `num_envs=512`, and highest matmul precision;
MJX09 additionally lowers the learning rate and clips gradients to avoid NaNs.

Note: Stage 1 is pure MuJoCo (no RL framework needed), so it runs natively on
this JAX image, which installs `mujoco` + `robot_descriptions`.
