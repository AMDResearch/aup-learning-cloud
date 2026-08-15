# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

ARG BASE_IMAGE=ghcr.io/amdresearch/auplc-base:latest
# Selects the final stage: "without-assets" (default, code-only image for CI/registry) or
# "with-assets" (workshop image with the dataset/model baked in). build.sh sets this to
# with-assets and overrides the "assets" context below when ASSETS_SRC is provided.
ARG FINAL=without-assets

# Optional pre-staged assets context. Empty by default; overridden at build time with
# `--build-context assets=<prestaged assets dir>`. Only read by the with-assets stage, so the
# default (no assets) build never touches it.
FROM scratch AS assets

FROM ${BASE_IMAGE} AS base

USER root
SHELL ["/bin/bash", "-c"]

ARG MOLMOACT2_COMMIT=cdf4b7728e0545366bf3366639fd86477ef59d04
ARG LEROBOT_COMMIT=a4f15bf347dee7eb8a8c5f4a70a37f476b091113

ENV DEBIAN_FRONTEND=noninteractive \
    HF_HUB_DISABLE_TELEMETRY=1 \
    HF_HUB_DISABLE_XET=1 \
    HF_HUB_ENABLE_HF_TRANSFER=0 \
    TOKENIZERS_PARALLELISM=false \
    TORCH_BLAS_PREFER_HIPBLASLT=0 \
    TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      cmake \
      git \
      libegl-dev \
      libgles-dev \
      libglib2.0-0t64 \
      libglew-dev \
      libosmesa6-dev \
      python3-venv \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/allenai/molmoact2 /opt/molmoact2 \
    && git -C /opt/molmoact2 checkout "${MOLMOACT2_COMMIT}" \
    && mkdir -p /opt/lerobot-allenai \
    && git -C /opt/lerobot-allenai init \
    && git -C /opt/lerobot-allenai remote add origin https://github.com/allenai/lerobot.git \
    && git -C /opt/lerobot-allenai fetch --depth 1 origin "${LEROBOT_COMMIT}" \
    && git -C /opt/lerobot-allenai checkout --detach FETCH_HEAD

# Keep the ROCm torch supplied by auplc-base while installing the MolmoAct2
# training and headless LIBERO stacks in the environment used by Jupyter.
RUN python3 -m venv --system-site-packages /opt/train-venv \
    && python3 -c "from importlib.metadata import version; \
print('torch==' + version('torch')); \
print('torchvision==' + version('torchvision')); \
print('torchaudio==' + version('torchaudio'))" > /opt/torch-constraints.txt \
    && PIP_CONSTRAINT=/opt/torch-constraints.txt /opt/train-venv/bin/pip install --no-cache-dir \
      "/opt/lerobot-allenai[libero,molmoact2,training]" \
      "accelerate>=1.0" \
      "av>=12" \
      "einops>=0.7" \
      "fastapi>=0.116" \
      "hf-transfer>=0.1.8" \
      "huggingface-hub[cli]>=0.36" \
      "imageio[ffmpeg]>=2.34" \
      "json-numpy>=2.1.0" \
      "matplotlib>=3.8" \
      "pyarrow>=17" \
      "safetensors>=0.4" \
      "sentencepiece>=0.2" \
      "uvicorn[standard]>=0.35" \
    && /opt/train-venv/bin/pip install --no-cache-dir --ignore-installed --no-deps opencv-python \
    && /opt/train-venv/bin/python -c \
      "import torch, lerobot, transformers, robosuite, mujoco; assert torch.version.hip; assert lerobot.__version__ == '0.5.2'; print('MolmoAct2 training environment OK:', torch.__version__, transformers.__version__, lerobot.__version__)" \
    && rm -f /tmp/robosuite.log

# Seed LIBERO non-interactively and bake its simulator assets outside HOME.
# JupyterHub mounts a persistent volume over /home/jovyan, so image content
# stored there would be hidden and the first eval would prompt or redownload.
RUN mkdir -p /opt/libero-config \
    && printf 'N\n' | LIBERO_CONFIG_PATH=/opt/libero-config \
      /opt/train-venv/bin/python -c "import libero.libero" \
    && LIBERO_CONFIG_PATH=/opt/libero-config \
      /opt/train-venv/bin/python -c \
      "from libero.libero import get_libero_path; from libero.libero.utils.download_utils import download_assets_from_huggingface as download; download(get_libero_path('assets'))" \
    && rm -f /tmp/robosuite.log

# ============================================================================================
# FastWAM (Wan2.2-TI2V-5B world-action model) inference layer -- powers notebook 3.
# Installed into an ISOLATED /opt/fastwam-venv so the pinned MolmoAct2 train-venv above is never
# disturbed. The FastWAM LIBERO path reuses the upstream `sim_libero` harness (vendored from
# ClockWorkKid/Ryzers@benchmark), which needs the numpy-1.26.4 LIBERO sim stack -- deliberately
# separate from the train-venv's numpy 2.x. FastWAM itself is cloned from its open-source upstream
# at build; only the CUDA torch pins are stripped so it runs on auplc-base's ROCm torch. Weights
# are NOT fetched here (baked from the local asset store in the with-assets stage / mounted at
# runtime). Placed before the notebook COPY so this heavy layer stays cached across notebook edits.
# The fastwam venv is created from the BASE interpreter (/usr/bin/python3, the auplc-base ROCm
# torch), NOT from train-venv, to keep a single, clean site-packages chain.
# ============================================================================================
ARG FASTWAM_COMMIT=45d8e1458921d83f8ad6cf9ce993d371208dabd0

RUN apt-get update && apt-get install -y --no-install-recommends \
      fonts-dejavu-core \
      libglu1-mesa \
    && rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/yuantianyuan01/FastWAM /repos/fastwam \
    && git -C /repos/fastwam checkout "${FASTWAM_COMMIT}" \
    && git clone --depth 1 https://github.com/Lifelong-Robot-Learning/LIBERO /opt/LIBERO

# Vendored AMD ryzers glue (sim_libero harness + FastWAM LIBERO policy adapter + kv-cache patch
# + strip helper + upstream-pin provenance). Source only; no binaries.
COPY fastwam/ /opt/fastwam-src/

# Exact planning-path caches (bit-identical output, ~1.45x faster on gfx1151): memoize the
# UMT5-XXL text encode across a replan episode and cache the action cross-attention K/V. Shipped
# as a reviewable diff vs the pinned upstream; default-on at runtime (FASTWAM_TEXT_KV_CACHE=0
# restores upstream behavior for parity checks).
RUN git -C /repos/fastwam apply --verbose /opt/fastwam-src/patches/fastwam_kv_cache.patch

# Isolated venv: reuse auplc-base's ROCm torch (constraint-pinned so it is never replaced) while
# installing the LIBERO sim stack (numpy 1.26.4) + FastWAM. Mirrors the simulation/libero +
# wam/fastwam ryzer recipe so the direct port stays faithful. numpy 1.26.4 is installed first,
# then the constraint is frozen from it so no transitive dep downgrades numpy or swaps the torch.
RUN /usr/bin/python3 -m venv --system-site-packages /opt/fastwam-venv \
    && /opt/fastwam-venv/bin/pip install --no-cache-dir "numpy==1.26.4" \
    && /opt/fastwam-venv/bin/python /opt/fastwam-src/strip_cuda_torch.py /repos/fastwam/pyproject.toml \
    && /opt/fastwam-venv/bin/pip freeze | grep -iE "^(torch|torchvision|torchcodec|numpy)==" > /opt/fastwam-constraints.txt \
    && PIP_CONSTRAINT=/opt/fastwam-constraints.txt /opt/fastwam-venv/bin/pip install --no-cache-dir \
        "robosuite==1.4.0" "bddl==1.0.1" "mujoco==3.3.2" easydict thop \
        "future==1.0.0" "cloudpickle==3.1.2" "gym==0.25.2" termcolor \
        "imageio>=2.34" "imageio-ffmpeg>=0.5" "pillow>=10" \
    && PIP_CONSTRAINT=/opt/fastwam-constraints.txt /opt/fastwam-venv/bin/pip install --no-cache-dir --no-deps -e /opt/LIBERO \
    && PIP_CONSTRAINT=/opt/fastwam-constraints.txt /opt/fastwam-venv/bin/pip install --no-cache-dir -e /repos/fastwam \
    && PIP_CONSTRAINT=/opt/fastwam-constraints.txt /opt/fastwam-venv/bin/pip install --no-cache-dir \
        "hf-transfer>=0.1.8" "sentencepiece>=0.2" "pyarrow>=17" "av>=12" "matplotlib>=3.8" \
    && /opt/fastwam-venv/bin/pip install --no-cache-dir --ignore-installed --no-deps opencv-python-headless

# Place the sim harness + adapter where the demos expect them; register the import paths + the
# torch.load compat shim in the fastwam venv only (self-contained .pth adds /opt/sim itself; the
# fastwam_paths.pth adds the upstream repo + adapters so experiments.libero + the policy resolve).
RUN mkdir -p /opt/sim /opt/fastwam-adapters \
    && cp -r /opt/fastwam-src/sim_libero /opt/sim/sim_libero \
    && cp /opt/fastwam-src/adapters/fastwam_libero_policy.py /opt/fastwam-adapters/ \
    && SP="$(/opt/fastwam-venv/bin/python -c 'import sysconfig;print(sysconfig.get_paths()["purelib"])')" \
    && cp /opt/fastwam-src/sim_libero_compat.pth "$SP/" \
    && printf '/opt/LIBERO\n/repos/fastwam\n/repos/fastwam/experiments/libero\n/opt/fastwam-adapters\n' > "$SP/fastwam_paths.pth"

# Seed the upstream LIBERO config for the fastwam venv OUTSIDE HOME, on its OWN config path so it
# never clashes with the MolmoAct2 train-venv's LIBERO (which lives in a different site-packages).
# bddl + robosuite meshes ship in the repo (no dataset download for eval/interactive). Verify the
# whole fastwam stack imports on auplc-base's ROCm torch (no GPU needed at build).
RUN mkdir -p /opt/libero-config-fastwam \
    && printf 'N\n' | LIBERO_CONFIG_PATH=/opt/libero-config-fastwam \
       /opt/fastwam-venv/bin/python -c \
       "import mujoco, robosuite; from libero.libero import benchmark; from libero.libero.envs import OffScreenRenderEnv; import sim_libero; from sim_libero.policy import load_policy; print('sim_libero + LIBERO import OK, mujoco', mujoco.__version__)" \
    && LIBERO_CONFIG_PATH=/opt/libero-config-fastwam /opt/fastwam-venv/bin/python -c \
       "import torch; assert torch.version.hip, 'torch is not a ROCm build: '+torch.__version__; import fastwam; from fastwam.runtime import create_fastwam; print('FastWAM import OK on torch', torch.__version__, 'hip', torch.version.hip)" \
    && rm -f /tmp/robosuite.log

RUN mkdir -p \
      /home/jovyan/.cache/huggingface \
      /home/jovyan/checkpoints \
      /home/jovyan/outputs \
      /ryzers/notebooks
# Proxy the interactive LIBERO sim server (notebook Section 6) through each JupyterHub
# user's existing notebook route, so no extra port must be exposed (same pattern the
# LocalInference course uses for its Streamlit UI). Installed into the system python that
# runs the single-user Jupyter server.
RUN /usr/bin/python3 -m pip install --no-cache-dir --break-system-packages \
      jupyter-server-proxy

COPY ./course_data /ryzers/notebooks
# Make the shipped shell scripts executable and expose the env-check scripts at the
# /ryzers/test_*.sh paths the README documents (same convention as the other courses).
RUN chmod +x /ryzers/notebooks/tests/*.sh /ryzers/notebooks/scripts/*.sh \
    && ln -sf /ryzers/notebooks/tests/test_torch.sh     /ryzers/test_torch.sh \
    && ln -sf /ryzers/notebooks/tests/test_molmoact2.sh /ryzers/test_molmoact2.sh \
    && ln -sf /ryzers/notebooks/tests/test_fastwam.sh   /ryzers/test_fastwam.sh
RUN chown -R jovyan:100 \
      /home/jovyan/.cache \
      /home/jovyan/checkpoints \
      /home/jovyan/outputs \
      /ryzers

ENV HOME=/home/jovyan \
    PATH="/opt/train-venv/bin:${PATH}" \
    HF_HOME=/home/jovyan/.cache/huggingface \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HF_DATASETS_OFFLINE=1 \
    LIBERO_CONFIG_PATH=/opt/libero-config \
    DROID_SERVER_DIR=/opt/molmoact2/examples/droid \
    OUT_DIR=/home/jovyan/outputs \
    CHECKPOINTS_DIR=/home/jovyan/checkpoints \
    REFERENCE_POLICY=/home/jovyan/checkpoints/reference/pretrained_model \
    MUJOCO_GL=egl \
    PYOPENGL_PLATFORM=egl

# FastWAM (notebook 3) runtime knobs. The weight/data paths resolve to the baked assets in the
# with-assets image; in a code-only image they can be overridden or mounted at runtime. The fastwam
# venv uses its OWN LIBERO config path (never the train-venv's), and the exact planning-path caches
# are on by default. DIFFSYNTH_MODEL_BASE_PATH is where the upstream loader looks for the Wan2.2
# base (T5 + VAE + tokenizer) instead of downloading it.
ENV FASTWAM_REPO=/repos/fastwam \
    FASTWAM_VENV=/opt/fastwam-venv \
    LIBERO_CONFIG_PATH_FASTWAM=/opt/libero-config-fastwam \
    DIFFSYNTH_MODEL_BASE_PATH=/opt/fastwam-assets/diffsynth \
    FASTWAM_RELEASE_DIR=/opt/fastwam-assets/fastwam_release \
    FASTWAM_DATA_DIR=/opt/fastwam-assets/data \
    FASTWAM_TEXT_KV_CACHE=1

USER jovyan
WORKDIR /ryzers/notebooks

# ---------------------------------------------------------------------------------------------
# Distribution variants. The default final stage is the code-only image (no assets), which keeps
# CI/registry builds and non-workshop use working unchanged. When build.sh passes
# `--build-arg FINAL=with-assets` together with `--build-context assets=<RAW workshop bundle>`,
# the build is FULLY SELF-CONTAINED: a staging stage unpacks the bundle and reconstructs the
# fine-tuned checkpoint in-build, and the final stage bakes the result in with the HF cache
# pointed at it (no host pre-stage, no shared mount). The cache lives under /opt (NOT /home/jovyan)
# because a persistent volume mounts over /home/jovyan at runtime and would hide anything under HOME.
# ---------------------------------------------------------------------------------------------
FROM base AS without-assets

# Self-contained pre-stage: unpack the raw split-tar workshop bundle and rebuild the fine-tuned
# checkpoint entirely INSIDE the build, using the image's own train-venv. Only the bundle subdirs
# we need are copied (the optional ~33 GB libero_full_backup/ is skipped; with BuildKit its bytes
# are never transferred). This stage is discarded except for the staged /opt trees copied below.
# The reused scripts/fetch_assets.sh untars base/libero/tokenizer/droid into the HF cache and
# reconstructs the reference checkpoint from the BF16 base + delta.
FROM base AS assets-staging
USER root
COPY --from=assets base/          /staging/bundle/base/
COPY --from=assets libero/        /staging/bundle/libero/
COPY --from=assets tokenizer/     /staging/bundle/tokenizer/
COPY --from=assets droid_dataset/ /staging/bundle/droid_dataset/
COPY --from=assets ft_checkpoint/ /staging/bundle/ft_checkpoint/
RUN set -euo pipefail; \
    HF_HOME=/opt/auplc-hf \
    HF_LEROBOT_HOME=/opt/auplc-hf/lerobot \
    REFERENCE_POLICY=/opt/auplc-ref/pretrained_model \
    ASSETS_SRC=/staging/bundle \
    bash /ryzers/notebooks/scripts/fetch_assets.sh; \
    test -f /opt/auplc-ref/pretrained_model/model.safetensors; \
    rm -rf /staging

# FastWAM weight pre-stage: unpack the split-tar FastWAM bundle (bf16 release checkpoint +
# dataset stats, the bf16 Wan2.2 base = T5 / VAE / tokenizer, and the small LIBERO episode set
# used by the video-imagination cell) into /opt/fastwam-assets. Kept OUTSIDE /home/jovyan so it
# survives the runtime PVC mount, exactly like the MolmoAct2 caches above. The weights are already
# bf16 (production precision); the bundle is passed via the same BuildKit `assets` context and is
# never committed to git.
FROM base AS fastwam-staging
USER root
COPY --from=assets fastwam/ /staging/fastwam/
RUN set -euo pipefail; \
    mkdir -p /opt/fastwam-assets; \
    cat /staging/fastwam/fastwam.tar.part-* | tar -C /opt/fastwam-assets -xf -; \
    test -f /opt/fastwam-assets/fastwam_release/libero_uncond_2cam224.pt; \
    test -f /opt/fastwam-assets/fastwam_release/libero_uncond_2cam224_dataset_stats.json; \
    test -d /opt/fastwam-assets/diffsynth; \
    rm -rf /staging

FROM base AS with-assets
USER root
COPY --from=assets-staging  /opt/auplc-hf       /opt/auplc-hf
COPY --from=assets-staging  /opt/auplc-ref      /opt/auplc-ref
RUN chown -R jovyan:100 /opt/auplc-hf /opt/auplc-ref
# FastWAM weights are large (~25 GB) and read-only at runtime, so bake them root-owned (world
# readable) WITHOUT a chown -R -- a recursive chown would double the layer size in the overlay.
COPY --from=fastwam-staging /opt/fastwam-assets /opt/fastwam-assets
ENV HF_HOME=/opt/auplc-hf \
    HF_LEROBOT_HOME=/opt/auplc-hf/lerobot \
    REFERENCE_POLICY=/opt/auplc-ref/pretrained_model
USER jovyan
WORKDIR /ryzers/notebooks

FROM ${FINAL} AS final
