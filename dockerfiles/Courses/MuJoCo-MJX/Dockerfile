# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# =============================================================================
# MuJoCo MJX course image (Image 1): JAX / MJX / Brax / MuJoCo Playground on AMD ROCm.
#
# Built on auplc-base, but PyTorch is removed. PyTorch's bundled triton LLVM
# clashes with jaxlib's bundled LLVM (and ROCm's ld.lld): importing
# `mujoco_playground` would otherwise abort with
#   'spirv-expand-step registered more than once'.
# With torch/triton gone and the XLA flags below set, jax-rocm + MJX + Brax +
# MuJoCo Playground all import and run on the GPU.
# =============================================================================

ARG BASE_IMAGE=ghcr.io/amdresearch/auplc-base:latest
FROM ${BASE_IMAGE}

USER root
# Vulkan backend and GUI (offscreen EGL rendering for MuJoCo)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget git ca-certificates locales \
    ffmpeg \
    libgl1 libglx-mesa0 libgl1-mesa-dri libegl1 libgbm1 libglib2.0-0 \
    libvulkan1 mesa-vulkan-drivers vulkan-tools \
 && rm -rf /var/lib/apt/lists/*

RUN ln -sf /opt/rocm/lib/llvm/bin/ld.lld /usr/local/bin/ld.lld

# Remove PyTorch/triton: its bundled LLVM duplicates jaxlib's and breaks the
# mujoco_playground import on this ROCm stack. This image is JAX-only.
RUN pip3 uninstall -y torch torchvision torchaudio triton pytorch-triton-rocm || true

# JAX for AMD ROCm (from AMD's ROCm wheel index).
RUN pip3 install --no-cache-dir \
    --extra-index-url https://repo.amd.com/rocm/whl/gfx1151/ \
    jax jaxlib jax-rocm7-plugin jax-rocm7-pjrt

# MuJoCo + MJX + Brax + MuJoCo Playground + helpers.
RUN pip3 install --no-cache-dir \
    mujoco \
    mujoco-mjx \
    brax \
    playground \
    robot_descriptions \
    imageio \
    imageio-ffmpeg

# Pre-download the MuJoCo Menagerie (Panda + other robot assets) at build time
# as root, so the PandaPickCube manipulation task works for the non-root jovyan
# user at runtime without needing network or write access to dist-packages.
RUN python3 -c "from mujoco_playground._src import mjx_env; mjx_env.ensure_menagerie_exists()" \
 && chmod -R a+rX /usr/local/lib/python3.12/dist-packages/mujoco_playground/external_deps

# JAX/XLA + MuJoCo runtime settings for ROCm (per AMD's ROCm-JAX-MuJoCo guide).
ENV XLA_FLAGS="--xla_gpu_enable_command_buffer="
ENV XLA_PYTHON_CLIENT_PREALLOCATE=false
ENV MUJOCO_GL=egl

RUN mkdir -p /opt/workspace/MuJoCo-MJX
COPY ./course_data /opt/workspace/MuJoCo-MJX

USER root
RUN chown -R jovyan:1000 /opt/workspace
USER jovyan
