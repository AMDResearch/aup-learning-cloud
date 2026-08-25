<!-- Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved. -->

# ROSCon 2026: RL Learning

PandaPickCube inference demo for ROSCon. Open [`hands-on.ipynb`](hands-on.ipynb) to roll out three Brax PPO checkpoints (weak → improving → strong) and render comparison videos.

## Contents

| File | Purpose |
|------|---------|
| `hands-on.ipynb` | Main inference notebook (checkpoint progression demo) |
| `headless_gl.py` | Headless MuJoCo rendering via system Mesa/OSMesa |
| `scripts/render_trajectory.py` | Re-render a saved rollout without rerunning inference |
| `scripts/render_checkpoint_once.py` | One-off rollout + render for a single checkpoint |
| `PandaPickCube-20260807-131132.zip` | Early-training checkpoints (demo uses `000008192000`) |
| `PandaPickCube-20260817-150103.zip` | Mid/final checkpoints (demo uses `000006553600`, `000045875200`) |

## Checkpoint progression

The notebook runs three stages in **demo order** (picked by rollout quality, not step count alone):

| Stage | Step folder | Video output |
|-------|-------------|--------------|
| Early (weak) | `131132` → `000008192000` (8.2M) | `panda_pick_cube_early.mp4` |
| Mid (improving) | `150103` → `000006553600` (6.5M) | `panda_pick_cube_mid.mp4` |
| Final (strong) | `150103` → `000045875200` (45.9M) | `panda_pick_cube.mp4` |

## Docker image

All dependencies are installed in [`dockerfiles/Courses/RLLearning/Dockerfile`](../../dockerfiles/Courses/RLLearning/Dockerfile): Python packages, headless GL libraries, and both checkpoint archives extracted at build time.

From a sparse checkout that includes `dockerfiles/Courses/RLLearning` and `dockerfiles/Makefile`:

```bash
make -C dockerfiles rl-learning GPU_TARGET=gfx1151
```

## Notebook Instructions

Course notebooks are staged at `/ryzers/notebooks` in the image. Open `hands-on.ipynb` there and run the cells in order — no `%pip` or pixi steps in the notebook.

**What you will show the audience**

- The simulation stack already baked into the course image (MuJoCo Playground, JAX/MJX, Brax).
- Three saved checkpoints from different points in training — early, mid, and final.
- One rollout per checkpoint, rendered to video, so behavior and reward visibly improve.

**What this notebook does not do**

- It does not train a policy. All weights are pre-baked in the Docker image.
- CPU JAX is enough. We run deterministic inference only.

**Run the cells in order**

1. Verify imports and the render backend
2. Confirm checkpoint paths on disk
3. Load the `PandaPickCube` environment
4. Define the Brax PPO loader
5. Prepare rollout helpers, then run **4a → 4b → 4c** (one cell per video)
6. Summary table and closing notes

Use the RLLearning course Docker image. It installs Python packages, headless GL libraries, and both checkpoint archives before you open the notebook.
