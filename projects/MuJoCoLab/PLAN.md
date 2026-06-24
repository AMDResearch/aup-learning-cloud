<!-- Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved. -->

# MuJoCo Lab — Embodied AI Track (Plan)

A notebook-based, **non-interactive** course that takes a learner from MuJoCo
fundamentals all the way to a XLeRobot sim-to-sim task. Everything runs headless
on the AUP Learning Cloud (AMD ROCm / Strix Halo gfx1151), using offscreen EGL
rendering + `imageio` mp4 output + inline `IPython.display.Video`, mirroring the
existing `RL0X_` course.

- **Notebook prefix:** `EAI01_ … EAI13_`
- **Course image:** `auplc-mjlab` (new course, wired like the RL course)
- **No GUI / teleop / browser interaction** — VR/keyboard demos from the source
  projects are converted to scripted, offscreen-rendered, recorded form.

## Sources surveyed

| Source | Role in this course |
|--------|---------------------|
| google-deepmind/mujoco | Physics engine + Python bindings + `mujoco.Renderer` (the base for everything). |
| MuJoCo Playground | MJX-based RL (single-GPU, minutes-scale training) for arms/locomotion. |
| XLeRobot | $660 dual-arm mobile robot; `simulation/` MuJoCo model + RL env = capstone target. |
| MuJoCo-GS-Web | MuJoCo (WASM) + 3D Gaussian Splatting hybrid rendering; SO101/Panda/XLeRobot IK. We port the **3DGS + physics compositing concept** to offline notebooks. |

---

## Recommended structure — 13 notebooks, 6 modules

### Module A — MuJoCo Foundations

**EAI01 — MuJoCo concepts & MJCF models**
- `mjModel` (static, compiled from MJCF) vs `mjData` (dynamic: `qpos/qvel/ctrl/xpos`).
- Load a built-in model, parse a minimal MJCF (body/joint/geom/actuator),
  `mj_step` / `mj_forward`, timestep, gravity, DOF.
- Output: state-vs-time plots + a minimal scene mp4.

**EAI02 — Rendering, cameras & contacts**
- `mujoco.Renderer`, named vs free cameras, `MjvOption` geom groups
  (visual vs collision — the "green Panda" lesson), contact-force viz, segmentation.
- Output: multi-camera video, contact visualization.

**EAI03a — SO101 single-arm control & IK (intro)**
- Platform: SO-101, 6-DOF single arm (used by XLeRobot; SO101 in MuJoCo-GS-Web).
- Model source: SO-Arm101 MJCF (MuJoCo Menagerie / LeRobot) or XLeRobot `simulation/` URDF→MJCF.
- Joint-space control (`ctrl` / PD), **analytical 2-link IK** (end-effector x,y → joint angles),
  scripted trajectory tracking (rectangle/circle), gripper open/close.
- Output: end-effector trajectory-tracking video + tracking-error curves.

**EAI03b — XLeRobot dual-arm + base control & IK (advanced)**
- Platform: XLeRobot — 2 (base) + 10 (dual 5-DOF arms) + 2 (grippers) + 2 (head).
- Model source: XLeRobot repo `simulation/` (URDF/MJCF).
- **Numerical IK (Damped Least Squares)** via Jacobian for 6-DOF pose control,
  redundancy + damping/stability, dual-arm coordination, optional base + arm combo.
- Output: dual-arm pose-tracking video + IK residual/convergence curves.

### Module B — MJX & large-scale parallel simulation
> Highest ROCm dependency risk: MJX runs on **JAX**. `jax-rocm` works but is
> version-sensitive; may need a dedicated image or CPU fallback for small demos.

**EAI04 — From MuJoCo to MJX**
- MJX = MuJoCo rewritten in JAX (`jit`/`vmap`, batched on GPU).
- mujoco vs mjx API mapping, `jax.vmap` over N envs, throughput comparison (1 vs 4096 envs).
- Output: throughput bar chart, batched rollout data.

**EAI05 — Parallel rollouts & domain randomization**
- Parallel random initial states + randomized physics (mass/friction) in MJX.
- How randomization narrows the sim-to-real gap.
- Output: trajectory-distribution visualization.

### Module C — MuJoCo Playground & RL

**EAI06 — RL refresher (bridges the existing RL0X course)**
- Unify vocabulary (MDP, policy, value, on/off-policy, SAC/PPO) using gymnasium + a MuJoCo env.
- Output: training curves.

**EAI07 — MuJoCo Playground intro**
- Load a Playground manipulation/locomotion env, train with built-in Brax PPO on a single GPU, record rollout.
- Output: trained policy + evaluation video.

**EAI08 — Arm manipulation task training**
- Train a Playground arm grasp/place task to convergence (XLeRobot-relevant), reward shaping, checkpoint.
- Output: success-rate curve + successful-episode video.

### Module D — Generalist policies: VLA & π0
> Large models, heavy deps. Inference-first (+ micro fine-tune if resources allow).
> Prefer the PyTorch(ROCm) route (LeRobot) over JAX to reduce AMD risk.

**EAI09 — VLA concepts & inference**
- Vision-Language-Action: image + language instruction → actions.
- Run a lightweight VLA (e.g. SmolVLA-class) inference: image + instruction → action sequence;
  explain tokenizer / action head / control frequency.
- Output: image+instruction → action visualization.

**EAI10 — π0 (pi0) flow-matching policy**
- π0 flow-matching action expert vs autoregressive VLA.
- Load π0 pretrained weights for inference on a simulated grasp; explain flow matching;
  optional micro-scale fine-tune on a few demos.
- Output: π0 controlling an arm on a simple task (video).

### Module E — Photorealism: 3D Gaussian Splatting

**EAI11 — 3DGS + MuJoCo hybrid rendering**
- Offline notebook port of MuJoCo-GS-Web's physics + 3DGS hybrid (correct occlusion).
- Load a pretrained 3DGS scene (`.ply`/`.spz`), offscreen rasterize (gsplat-class),
  composite with MuJoCo depth so sim objects occlude the background correctly.
- Output: photorealistic-background + physics-robot composited video.
- ⚠️ 3DGS rasterizer on ROCm is the biggest unknown — feasibility-check first; fall back
  to "render a precomputed image sequence" to teach the concept if needed.

### Module F — Capstone: XLeRobot Sim-to-Sim

**EAI12 — XLeRobot sim-to-sim task**
- Load XLeRobot MuJoCo model (dual arm + mobile base).
- Define a household task (e.g. place a cube into a basket).
- **Sim-to-sim**: take a policy from Module C (Playground/standard MuJoCo) or the VLA from
  Module D, run it in XLeRobot's MuJoCo env, observe the gap, and make minimal adjustments
  (obs/action-space alignment, coordinate/unit conversion).
- Record a demo with a 3DGS background (Module E).
- Output: XLeRobot attempting the task (video) + sim-to-sim gap analysis.

> EAI13 reserved as an overflow/capstone-part-2 slot (e.g. split task setup from
> the sim-to-sim transfer if EAI12 grows too large).

---

## Environment / image strategy

Do **not** cram everything into the existing RL image. Plan for layered envs
(each a validated course image, wired like the RL course):

| Layer | Modules | Key deps | ROCm risk |
|-------|---------|----------|-----------|
| Base MuJoCo | A, C(gymnasium), F | mujoco, robosuite, gymnasium, torch, imageio | ✅ proven |
| JAX line | B, C(Playground) | jax-rocm, mjx, playground, brax | ⚠️ JAX version-sensitive |
| VLA line | D | lerobot, transformers, π0 weights | ⚠️ large models, ROCm-compat builds |
| 3DGS | E | gsplat / rasterizer + viewer | ⚠️⚠️ rasterizer ROCm support unknown |

ROCm feasibility order (safe → risky):
`A ✅ → C(gymnasium) ✅ → B/C(MJX/Playground) ⚠️ → D ⚠️ → E ⚠️⚠️`

Each high-risk module starts with an "environment feasibility" cell.

## Platform integration (mirror the RL course)

When a module's image is ready, wire it like `Course-RL`:
- `dockerfiles/Courses/MJLab/` (Dockerfile + build.sh)
- `dockerfiles/Makefile` (target + `courses` aggregate + `.PHONY`)
- `.github/build-config.json` (courses list)
- `auplc_installer/catalog.py` (COURSE_CATALOG + BASE_TEAM_MAPPING)
- `auplc_installer/overlay.py` (`_RESOURCE_IMAGE_BASE`)
- `runtime/values.yaml` + `runtime/values-multi-nodes.yaml.example`
  (images / requirements / metadata / teams)

## Conventions (same as RL course)

- Headless EGL offscreen render → `imageio` mp4 → inline `Video(...)`.
- Outputs under `output/videos` and `output/logs`.
- Each notebook self-contained: concept markdown → env check → minimal runnable example → output/visualization.
- AMD copyright header markdown cell at the top of each notebook.

## Phasing / milestones

1. **M0 — Model + env feasibility**: verify SO101 & XLeRobot MJCF load and render
   correctly on ROCm/EGL (geom-group fix as needed); verify jax-rocm and gsplat
   minimal examples.
2. **M1 — Module A** (EAI01, EAI02, EAI03a, EAI03b) on the base image.
3. **M2 — Module C** (EAI06–08) — RL/Playground.
4. **M3 — Module B** (EAI04–05) — MJX (after JAX feasibility).
5. **M4 — Module D** (EAI09–10) — VLA/π0.
6. **M5 — Module E** (EAI11) — 3DGS.
7. **M6 — Capstone** (EAI12) — XLeRobot sim-to-sim.

## Open questions

1. EAI03: replace Panda entirely with SO101/XLeRobot, or keep Panda as a reference?
2. XLeRobot model: use the repo `simulation/` version or the MuJoCo-GS-Web version?
3. Course image split: one big `auplc-mjlab` vs multiple per-layer images?
