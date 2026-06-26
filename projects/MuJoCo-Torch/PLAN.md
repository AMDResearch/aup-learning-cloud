<!-- Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved. -->

# MuJoCo Lab — Embodied AI Track (Plan, two-image edition)

A notebook-based, **non-interactive** course from MuJoCo fundamentals to a
XLeRobot sim-to-sim capstone driven by a π0 VLA policy. Headless on AUP Learning
Cloud (AMD ROCm / Strix Halo gfx1151): offscreen EGL render -> `imageio` mp4 ->
inline `IPython.display.Video`. Outputs under `output/videos` and `output/logs`.

## Two images (two spawn courses)

Frameworks fundamentally conflict in one env (jaxlib vs torch/triton LLVM
double-registration; numpy 2.5 for JAX vs numpy<2.4 for robosuite), so the
course ships as **two images**:

| Image (course) | Stack | numpy | Labs |
|----------------|-------|-------|------|
| **Image 1 — `auplc-mujoco` (JAX/MJX)** | jax-rocm + jaxlib + mjx + brax + playground + mujoco + robot_descriptions. **No torch, no robosuite.** | 2.5 | **A, B, C** (Mujoco01–08) |
| **Image 2 — `auplc-eai` (torch/VLA)** | torch(ROCm) + lerobot + π0 + transformers + gsplat + robosuite + mujoco. **No jax.** | <2.4 | **D, E, F** (Mujoco09–12) |

### Validated feasibility (M0)
- jax-rocm from AMD index `https://repo.amd.com/rocm/whl/gfx1151/` -> `RocmDevice(id=0)`. ✅
- MJX on GPU: 4096 envs x 10 steps in ~33 ms. ✅
- brax 0.14.2 imports. ✅
- `mujoco_playground` import crashed **only when torch/triton was present** (LLVM `spirv-expand-step` double-registration) -> must verify it imports in the torch-free Image 1. ⚠️ (to validate)
- SO-ARM100 via `robot_descriptions` and XLeRobot via sparse-clone both load + render on ROCm/EGL. ✅

---

## Image 1 — `auplc-mujoco` (JAX/MJX): Labs A, B, C

> Repurpose the existing `auplc-mujoco` image to the JAX stack (drop torch /
> robosuite, add jax-rocm + mjx + brax + playground; keep mujoco +
> robot_descriptions). Module A already runs without torch/robosuite.

### Module A — MuJoCo Foundations (done)
- **Mujoco01 — Concepts & MJCF**: mjModel vs mjData, minimal MJCF, `mj_step`, state plots, render. ✅ built
- **Mujoco02 — Rendering, Cameras & Contacts**: `mujoco.Renderer`, named cameras, geom groups (visual vs collision), contact viz. ✅ built
- **Mujoco03 — Control & IK (SO101 + XLeRobot)**: joint control + DLS IK; SO-ARM100 (robot_descriptions) and XLeRobot (sparse-clone), arm-focused camera. ✅ built

### Module B — MJX & large-scale parallel simulation
- **Mujoco04 — From MuJoCo to MJX**: MJX = MuJoCo in JAX (`jit`/`vmap`), mujoco vs mjx API, `vmap` over N envs, throughput 1 vs 4096 envs on GPU.
- **Mujoco05 — Parallel rollouts & domain randomization**: batched random initial states + randomized physics (mass/friction) in MJX; how it narrows the sim-to-real gap.

### Module C — MuJoCo Playground & RL
- **Mujoco06 — RL refresher**: MDP / policy / value / on- vs off-policy, written in JAX (flax/optax) on a small MuJoCo/MJX env (so the image stays torch-free). Training curve.
- **Mujoco07 — MuJoCo Playground intro**: load a Playground locomotion/manipulation env, train with Brax PPO on the GPU, record rollout video.
- **Mujoco08 — Arm manipulation task training**: train a Playground arm grasp/place task to convergence, reward shaping, checkpoint; success-rate curve + video.

---

## Image 2 — `auplc-eai` (torch/VLA): Labs D, E, F

> New image: AMD ROCm PyTorch base + LeRobot + π0 + transformers + gsplat +
> robosuite + mujoco. numpy<2.4. No jax (avoids the LLVM clash).

### Module D — Generalist policies: VLA & π0
- **Mujoco09 — VLA concepts & inference**: vision-language-action basics; run a lightweight VLA (SmolVLA-class) inference: image + instruction -> action sequence; tokenizer / action head / control frequency.
- **Mujoco10 — π0 (pi0) flow-matching policy**: π0 flow-matching action expert vs autoregressive VLA; load π0 pretrained weights (LeRobot) for inference on a simulated grasp; explain flow matching; optional micro fine-tune.

### Module E — Photorealism: 3D Gaussian Splatting
- **Mujoco11 — 3DGS + MuJoCo hybrid rendering**: offline port of MuJoCo-GS-Web's physics + 3DGS hybrid (correct occlusion); load a pretrained 3DGS scene, offscreen rasterize (gsplat), composite with MuJoCo depth. Feasibility-check gsplat on ROCm first; fall back to a precomputed image sequence to teach the concept if needed.

### Module F — Capstone: XLeRobot Sim-to-Sim with π0
- **Mujoco12 — XLeRobot sim-to-sim (π0)**: load XLeRobot MuJoCo model; define a household task; run a **π0 VLA policy** (torch) controlling XLeRobot in MuJoCo; observe the sim-to-sim gap and make minimal obs/action-space + coordinate adjustments; record a demo (optionally with a 3DGS background from Module E).
  - F is torch/π0-only (does **not** consume Module C's brax/jax policies).

---

## Platform integration

- Image 1: keep course key `Course-MuJoCo` -> `auplc-mujoco`, but change
  `dockerfiles/Courses/MuJoCo/Dockerfile` to the JAX stack (jax-rocm + mjx +
  brax + playground + mujoco + robot_descriptions; remove torch/robosuite).
- Image 2: add a new course (e.g. `Course-EAI` -> `auplc-eai`) wired like any
  course: `dockerfiles/Courses/EAI/`, `dockerfiles/Makefile`,
  `.github/build-config.json`, `auplc_installer/catalog.py`,
  `auplc_installer/overlay.py`, `runtime/values*.yaml`.
- Notebooks: `projects/MuJoCo/` -> Mujoco01–08; new `projects/EAI/` (or
  `projects/MuJoCoVLA/`) -> Mujoco09–12.

## Conventions
- Headless EGL render -> `imageio` mp4 -> inline `Video(...)`; outputs under
  `output/videos` / `output/logs`.
- Each notebook self-contained: concept markdown -> env/feasibility check ->
  minimal runnable example -> output/visualization.
- AMD copyright header markdown cell at the top of each notebook.

## Phasing
1. Build Image 1 `auplc-mujoco` (JAX stack); verify `mujoco_playground` imports torch-free; confirm Module A still runs there.
2. Write & validate Module B (Mujoco04–05) on GPU MJX.
3. Write & validate Module C (Mujoco06–08) with Brax PPO + Playground.
4. Build Image 2 `auplc-eai` (torch/VLA); validate lerobot/π0 + gsplat + robosuite co-resolve under numpy<2.4.
5. Write Module D (Mujoco09–10), E (Mujoco11), F (Mujoco12, π0).

## Open items
- Verify `mujoco_playground` import in a torch-free JAX image (gates Module C).
- Verify Image 2 dependency resolution (lerobot/π0/gsplat/robosuite under numpy<2.4).
- Pick the Image 2 course name/key and notebook project dir.
