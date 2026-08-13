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
    && ln -sf /ryzers/notebooks/tests/test_molmoact2.sh /ryzers/test_molmoact2.sh
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

FROM base AS with-assets
USER root
COPY --from=assets-staging /opt/auplc-hf  /opt/auplc-hf
COPY --from=assets-staging /opt/auplc-ref /opt/auplc-ref
RUN chown -R jovyan:100 /opt/auplc-hf /opt/auplc-ref
ENV HF_HOME=/opt/auplc-hf \
    HF_LEROBOT_HOME=/opt/auplc-hf/lerobot \
    REFERENCE_POLICY=/opt/auplc-ref/pretrained_model
USER jovyan
WORKDIR /ryzers/notebooks

FROM ${FINAL} AS final
