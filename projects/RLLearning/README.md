<!-- Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved. -->

# ROSCon 2026: RL Learning

PandaPickCube inference demo for ROSCon. Open [`hands-on.ipynb`](hands-on.ipynb) to restore a trained Brax PPO policy, roll out one episode, and render `panda_pick_cube.mp4`.

## Contents

| File | Purpose |
|------|---------|
| `hands-on.ipynb` | Main inference notebook |
| `headless_gl.py` | Headless MuJoCo rendering via system Mesa/OSMesa |
| `scripts/render_trajectory.py` | Re-render a saved rollout without rerunning inference |
| `PandaPickCube-20260817-150103.zip` | Brax PPO checkpoint archive (extracted in the Docker image; notebook default) |
| `PandaPickCube-20260807-131132.zip` | Alternate Brax PPO checkpoint archive (also extracted in the Docker image) |

`PandaPickCube-20260817-150103` extracts to `checkpoints/` with latest step `000045875200`. `PandaPickCube-20260807-131132` extracts to `checkpoints/` with latest step `000024576000`.

## Docker image

All dependencies are installed in [`dockerfiles/Courses/RLLearning/Dockerfile`](../../dockerfiles/Courses/RLLearning/Dockerfile): Python packages, headless GL libraries, and the extracted checkpoint.

From a sparse checkout that includes `dockerfiles/Courses/RLLearning` and `dockerfiles/Makefile`:

```bash
make -C dockerfiles rl-learning GPU_TARGET=gfx1151
```

Course notebooks are staged at `/ryzers/notebooks` in the image. Open `hands-on.ipynb` there and run the cells in order — no `%pip` or pixi steps in the notebook.
