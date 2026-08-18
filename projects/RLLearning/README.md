<!-- Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved. -->

# ROSCon 2026: RL Learning

PandaPickCube inference demo for ROSCon. Open [`hands-on.ipynb`](hands-on.ipynb) to restore a trained Brax PPO policy, roll out one episode, and render `panda_pick_cube.mp4`.

## Contents

| File | Purpose |
|------|---------|
| `hands-on.ipynb` | Main inference notebook |
| `headless_gl.py` | Headless MuJoCo rendering via pixi-installed Mesa |
| `pixi.toml` | Mesa/OpenGL dependencies for section 1.5 |
| `scripts/render_trajectory.py` | Re-render a saved rollout without rerunning inference |
| `PandaPickCube-20260817-150103.zip` | Brax PPO checkpoint archive (extracted in the Docker image) |

The checkpoint extracts to `PandaPickCube-20260817-150103/checkpoints/` (latest step: `000045875200`).

## Run locally

1. Python 3.11 or 3.12, [pixi](https://pixi.sh) on `PATH`, and `git` for Franka assets.
2. Unzip the checkpoint: `unzip PandaPickCube-20260817-150103.zip`
3. Open `hands-on.ipynb` from this directory and run the cells in order.

## Docker image

Environment setup lives in [`dockerfiles/Courses/RLLearning/Dockerfile`](../../dockerfiles/Courses/RLLearning/Dockerfile).

From a sparse checkout that includes `dockerfiles/Courses/RLLearning` and `dockerfiles/Makefile`:

```bash
make -C dockerfiles rl-learning GPU_TARGET=gfx1151
```

Course notebooks are staged at `/ryzers/notebooks` in the image.
