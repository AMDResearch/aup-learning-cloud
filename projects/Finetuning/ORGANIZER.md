<!-- Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved. -->

# Fine-tuning course - organizer & developer guide

This guide sets up the MolmoAct2 fine-tuning workshop on one AMD **Strix Halo** machine, end to end:
build the course image, deploy the JupyterHub server, put the large files in place, and hand each
attendee a web address. When you are done, an attendee just opens that address, logs in, runs one
command, and clicks **Run All** - with no downloading at the venue.

> **Just attending?** You do not need this file - follow **[README.md](README.md)** instead.

Every step below says **where to run it**. Do them in order. You need a Strix Halo box running
**Ubuntu 24.04** where you have `sudo` (admin) rights, and about **150 GB free** disk (the baked
course image is ~50 GB; the pre-staged `assets/` tree and a saved image tar need room too).

---

## Step 1 - Prepare the machine (once per box)

**Run this on: the Strix Halo box (a terminal, with sudo).**

Install the prerequisites from the repository's top-level `README.md` "Quick Start": the OEM kernel
for Ryzen AI APUs, Docker set up for non-root use, `build-essential`, and the installer's terminal
UI dependencies. Then confirm Docker works without sudo:

```bash
docker run --rm hello-world
```

If that prints a success message, the machine is ready.

## Step 2 - Get the course code

**Run this on: the Strix Halo box.**

```bash
git clone <your-fork-url>/aup-learning-cloud.git
cd aup-learning-cloud
git checkout roscon26
```

Everything in the rest of this guide is run from inside this `aup-learning-cloud` folder.

## Step 3 - Put the workshop files on the machine

**Run this on: any machine that can reach both your file store and the Strix Halo box.**

The large inputs ship as one folder called `mm2_workshop_assets` (about **16 GB** with the default
LIBERO subset), split into ~4 GB pieces so it copies easily. It is hosted on your team's shared
drive (for this workshop, OneDrive). Its layout is:

```
mm2_workshop_assets/
  base/           the base MolmoAct2-DROID checkpoint, stored in BF16          (~11 GB)
  libero/         the LIBERO training dataset (default: ~1 GB task-diverse subset;
                  set USE_FULL_LIBERO=1 in the notebook to fetch the full ~33 GB set)
  tokenizer/      a small tokenizer the model needs
  droid_dataset/  a small real-robot dataset used by notebook 1, Step 3         (~1.4 GB)
  ft_checkpoint/  the fine-tune "delta": the LoRA adapter + trained parts       (~2.4 GB)
  reconstruct_reference.py  unpack_bundle.sh  README.txt
```

Copy that whole folder onto the Strix Halo box, for example:

```bash
scp -r /path/to/mm2_workshop_assets  <user>@<strix-halo-address>:/opt/auplc-assets/mm2_workshop_assets
```

> **Why is `ft_checkpoint/` so small, and what is the "delta"?** The fine-tuned policy is just the
> frozen base model plus a small set of weights that changed during fine-tuning. Instead of shipping
> the whole base model twice, we ship the base once (in BF16, the precision everyone runs in) and
> only the small delta. The full fine-tuned checkpoint is rebuilt automatically from base + delta in
> Step 4 - you do not do anything extra.

## Step 4 - Build the self-contained course image

**Run this on: the Strix Halo box, inside the `aup-learning-cloud` folder.**

One command builds a FULLY self-contained image: the Docker build itself unpacks the raw workshop
bundle, rebuilds the full fine-tuned checkpoint, and bakes everything - together with the two
notebooks and their helper scripts - into a single container image. Point `ASSETS_SRC` at the raw
bundle from Step 3:

```bash
make -C dockerfiles finetuning GPU_TARGET=gfx1151 ASSETS_SRC=/path/to/mm2_workshop_assets
```

There is no separate pre-stage step - the build's staging stage runs the unpack + checkpoint
reconstruction internally (using the image's own Python), so this works on a fresh machine. Only
the bundle subdirs it needs are read (`base/ libero/ tokenizer/ droid_dataset/ ft_checkpoint/`); an
optional `libero_full_backup/` is ignored.

The result is a local image `ghcr.io/amdresearch/auplc-finetuning:latest` (and `:latest-gfx1151`)
that carries its own HF cache under `/opt/auplc-hf` and reference checkpoint under `/opt/auplc-ref` -
no shared mount, no per-attendee download. When you only change a notebook or script later, rebuild
in place with the same command (BuildKit reuses the cached asset layers, so it does not re-unpack) -
do not create a second image.

> `make finetuning-baked` is kept as a back-compat alias and now simply runs `make finetuning`.

> **Build a code-only image** (no assets, e.g. for CI) with `ASSETS_SRC= make -C dockerfiles
> finetuning GPU_TARGET=gfx1151`. The assets are passed to the build as a BuildKit named context, so
> they are never copied into the git tree.

## Step 5 - Distribute the image to the other nodes (multi-node only)

**Run this on: the Strix Halo box.** Skip this on a single machine.

Because the assets are inside the image, distributing the workshop to a cluster is just distributing
the image - like a `docker pull`. Save it once and load it on each node (or push to a registry every
node can reach):

```bash
docker save ghcr.io/amdresearch/auplc-finetuning:latest-gfx1151 | gzip > auplc-finetuning.tar.gz
# then on each node:
gunzip -c auplc-finetuning.tar.gz | docker load
```

## Step 6 - Deploy the JupyterHub server

**Run this on: the Strix Halo box, inside the `aup-learning-cloud` folder.**

```bash
sudo ./auplc-installer install --gpu=strix-halo
```

This installs a small single-node Kubernetes (k3s) and the JupyterHub server on top of it, using the
image you just built. Wait until it finishes and reports the pods are ready. When it is done it
prints the **web address of the server** - it looks like `http://<this-machine's-address>:30890/`.
**Write that address down; it is what you give attendees in Step 7.**

The course "Fine-tuning on GPUs" is already registered, so it shows up on the login page
automatically. Each attendee who logs in gets their own private notebook server with its own GPU
slice and a writable home folder. The assets are already in the image, so attendees just open the
notebooks and click **Run All** - nothing is downloaded or linked at the venue.

> **Already have another JupyterHub running on this same box?** Two servers cannot share the same
> name. On a fresh box this never happens. If it does (a shared dev box), the simplest fix is to
> deploy on a machine that does not already run one - that keeps this command exactly as written,
> with nothing to configure.

## Step 7 - Give attendees the address

Send each attendee:

- the web address from Step 6 (`http://<this-machine's-address>:30890/`), and
- their username and password.

They then follow **[README.md](README.md)**. Done.

---

## Developer check: reproduce the whole thing offline before you ship

**Run this on: a Strix Halo box, after Step 4 (the build) above.**

To verify a change end to end without any network, run a notebook headless directly against the
baked image - no mount and no staging step, exactly what an attendee gets. The assets are already in
the image at `/opt/auplc-hf` (HF cache) and `/opt/auplc-ref` (reference checkpoint):

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

A healthy run shows the closed-loop LIBERO evaluation reporting success. Model weights and large
videos stay on the machine (never re-hosted).

> **Testing against an external asset tree instead of the baked cache?** The code-only image plus
> `scripts/fetch_assets.sh` still supports the old mount-and-link workflow; point `ASSETS_SRC` at a
> mounted `assets/` tree and run `fetch_assets.sh` before nbconvert.
