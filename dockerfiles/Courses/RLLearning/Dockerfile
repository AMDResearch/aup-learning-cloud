# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

ARG BASE_IMAGE=ghcr.io/amdresearch/auplc-base:latest
FROM ${BASE_IMAGE}

ARG PLAYGROUND_COMMIT=cf88ae6e9c38654199d85c5c976795a7dc350571

USER root
SHELL ["/bin/bash", "-c"]

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
      git \
      libegl-dev \
      libgl1-mesa-dri \
      libglew-dev \
      libgles-dev \
      libosmesa6-dev \
      unzip \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /ryzers/notebooks

# The build script stages projects/RLLearning as course_data.
COPY ./course_data /ryzers/notebooks

WORKDIR /ryzers/notebooks
RUN unzip -q PandaPickCube-20260817-150103.zip \
    && unzip -q PandaPickCube-20260807-131132.zip \
    && chown -R jovyan:100 /ryzers

# Install course packages system-wide as root (see LLM Dockerfile for rationale).
RUN pip3 install --no-cache-dir \
      "mujoco==3.10.0" \
      "mujoco-mjx==3.10.0" \
      "jax==0.10.0" \
      "jaxlib==0.10.0" \
      "brax==0.14.2" \
      "flax" \
      "orbax-checkpoint>=0.11.22" \
      "etils" \
      "ml-collections" \
      "mediapy" \
      "imageio" \
      "imageio-ffmpeg" \
      "absl-py" \
      "lxml" \
      "tqdm" \
    && pip3 install --no-cache-dir --no-deps \
      "git+https://github.com/google-deepmind/mujoco_playground.git@${PLAYGROUND_COMMIT}"

RUN python3 -c "import brax, jax, mujoco; from mujoco_playground import registry; print('PandaPickCube inference env OK')"

# Pre-download MuJoCo Menagerie as root; runtime user cannot write under site-packages.
RUN python3 -c "\
from mujoco_playground import registry; \
env = registry.load('PandaPickCube', config_overrides={'impl': 'jax'}); \
print('PandaPickCube env loaded, obs=', env.observation_size, 'act=', env.action_size)"

USER jovyan
WORKDIR /ryzers/notebooks
