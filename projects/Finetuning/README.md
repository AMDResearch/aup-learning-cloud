<!-- Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved. -->

# ROSCon 2026: Fine-tuning a Robot Policy (MolmoAct2 + LIBERO)

Fine-tune a real-robot vision-language-action model (**MolmoAct2**) on a new skill in the **LIBERO**
simulator with a short **LoRA** run, then drive the fine-tuned policy live in the simulator. It runs
in the browser on a single AMD **Strix Halo** machine as a JupyterHub course image.

---

## Build the image

Two steps: **copy the assets, then run the build.**

### 1. Copy the workshop assets zip into this folder

```bash
cp /path/to/mm2_workshop_assets.zip  projects/Finetuning/
```

### 2. Run the build

From the repo root:

```bash
make -C dockerfiles finetuning GPU_TARGET=gfx1151
```

The build unpacks the assets, rebuilds the fine-tuned checkpoint, and bakes everything — plus the two
notebooks and helper scripts — into a self-contained image
`ghcr.io/amdresearch/auplc-finetuning:latest` (also tagged `:latest-gfx1151`).

---

## Deploy and hand out to attendees

Deploy the JupyterHub server with the image you just built:

```bash
sudo ./auplc-installer install --gpu=strix-halo
```

---

## Developer check (optional): run a notebook headless against the built image

Verify a build end-to-end with no network and no mounts, exactly what an attendee gets:

```bash
docker run --rm --network=host --ipc=host --shm-size 16G \
  --device=/dev/kfd --device=/dev/dri --security-opt seccomp=unconfined \
  --group-add video --group-add render \
  --tmpfs /home/jovyan:mode=0777 \
  -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
  --entrypoint bash ghcr.io/amdresearch/auplc-finetuning:latest-gfx1151 -lc '
    mkdir -p /home/jovyan/outputs
    /opt/train-venv/bin/python -m ipykernel install --user --name tv >/dev/null 2>&1
    jupyter nbconvert --to notebook --execute --ExecutePreprocessor.kernel_name=tv \
      --ExecutePreprocessor.timeout=-1 --output /home/jovyan/outputs/nb1.ipynb \
      finetune_molmoact2_libero.ipynb'
```

A healthy run shows the closed-loop LIBERO evaluation reporting success.
