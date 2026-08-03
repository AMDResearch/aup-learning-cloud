# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

ARG BASE_IMAGE=ghcr.io/amdresearch/auplc-base:latest
FROM ${BASE_IMAGE}

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
COPY ./course_data /ryzers/notebooks
RUN chown -R jovyan:100 \
      /home/jovyan/.cache \
      /home/jovyan/checkpoints \
      /home/jovyan/outputs \
      /ryzers

ENV HOME=/home/jovyan \
    PATH="/opt/train-venv/bin:${PATH}" \
    HF_HOME=/home/jovyan/.cache/huggingface \
    LIBERO_CONFIG_PATH=/opt/libero-config \
    DROID_SERVER_DIR=/opt/molmoact2/examples/droid \
    OUT_DIR=/home/jovyan/outputs \
    CHECKPOINTS_DIR=/home/jovyan/checkpoints \
    REFERENCE_POLICY=/home/jovyan/checkpoints/reference/pretrained_model \
    MUJOCO_GL=egl \
    PYOPENGL_PLATFORM=egl

USER jovyan
WORKDIR /ryzers/notebooks
