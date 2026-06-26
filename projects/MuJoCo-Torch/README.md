<!-- Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved. -->

# MuJoCo (PyTorch) Course

Content for the **MuJoCo (PyTorch)** course (image `auplc-mujoco-torch`:
PyTorch ROCm + mujoco + robosuite + gymnasium + robot_descriptions). The
companion JAX/MJX course (Module A–C foundations) lives in `../MuJoCo-MJX`.

## Labs (all validated end-to-end on gfx1151 / ROCm)

- `Torch01_Robosuite_Intro` — what robosuite is; create a Lift/Panda task,
  inspect dict observations and the 7-D end-effector action, render reliably,
  roll out a random policy.
- `Torch02_Controllers_and_Cameras` — operational-space (BASIC) controller and
  named cameras; **script a full reach–grasp–lift pick** (cube lifted ≈0.24 m,
  task reward 1.0).
- `Torch03_Gymnasium_and_Reward` — wrap a task with `GymWrapper` (the Gymnasium
  5-tuple API), and visualize the dense (shaped) reward signal over a reach.
- `Torch04_Behavior_Cloning` — collect demonstrations from the scripted expert
  and train a PyTorch MLP on the GPU to imitate it; the learned policy reaches
  the cube (final distance ≈0.04 m).

## Rendering note (important for this ROCm/EGL stack)

robosuite's built-in camera-observation renderer emits **intermittently
corrupted frames** on gfx1151/EGL. All notebooks therefore render through a
`make_renderer` / `grab_frame` helper that drives `mujoco.Renderer` directly on
`env.sim.model._model` / `env.sim.data._data` and shows only the visual geom
group (group 1). This path is stable across runs and avoids the green/blue
collision-shape overlay.

Each notebook is self-contained: concept markdown → runnable code → inline
`Video(...)`. Outputs are written under `output/videos`.

## Scope note vs. `PLAN.md`

`PLAN.md` sketches an aspirational Module D–F (π0 / VLA, 3D Gaussian Splatting,
XLeRobot sim-to-sim). Those require packages **not installed in the current
`auplc-mujoco-torch` image** (lerobot, π0, transformers, gsplat) whose ROCm /
gfx1151 support is unverified. To meet the "must run" bar, the implemented
course (Torch 01–04) is built on the stack the image actually ships
(robosuite + gymnasium + PyTorch) and is fully tested. Extending toward the
π0/3DGS plan would first need Dockerfile additions and ROCm feasibility R&D.
