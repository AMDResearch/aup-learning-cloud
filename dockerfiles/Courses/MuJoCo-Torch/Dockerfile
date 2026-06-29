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

# Use a verified ROCm PyTorch image as base
ARG BASE_IMAGE=ghcr.io/amdresearch/auplc-base:latest
FROM ${BASE_IMAGE}

USER root
# Vulkan backend and GUI
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget git ca-certificates locales \
    ffmpeg \
    libgl1 libglx-mesa0 libgl1-mesa-dri libegl1 libgbm1 libglib2.0-0 \
    libvulkan1 mesa-vulkan-drivers vulkan-tools \
 && rm -rf /var/lib/apt/lists/*

RUN ln -sf /opt/rocm/lib/llvm/bin/ld.lld /usr/local/bin/ld.lld

# IMPORTANT: must remain under USER root here. pip install as jovyan silently
# falls back to ~/.local/, which gets masked by the PVC mount at runtime.

# Course packages not already in auplc-base (torch / numpy / jupyter ship there).
# The MuJoCo simulation core is pinned; the rest track compatible releases.
RUN pip3 install --no-cache-dir \
    "mujoco==3.9.0" \
    "gymnasium==1.3.0" \
    "robosuite==1.5.2" \
    robosuite_models \
    robot_descriptions \
    h5py \
    imageio \
    imageio-ffmpeg

# LeRobot (VLA policies) + the transformers version it requires (>=5.3.0,<6).
RUN pip3 install --no-cache-dir "lerobot[smolvla,pi]==0.5.0" \
 && pip3 install --no-cache-dir "transformers==5.3.0"

# XLeRobot MuJoCo assets, baked for offline use at runtime.
RUN git clone --depth 1 https://github.com/Vector-Wangel/XLeRobot.git /opt/xlerobot \
 && chmod -R a+rX /opt/xlerobot

# Bake the SmolVLA weights (+ SmolVLM2 backbone) so the labs run offline.
# HF_HOME is owned by jovyan so runtime downloads cache alongside the baked weights.
ENV HF_HOME=/opt/hf
RUN mkdir -p /opt/hf \
 && python3 -c "from huggingface_hub import snapshot_download; \
snapshot_download('lerobot/smolvla_base'); \
snapshot_download('HuggingFaceTB/SmolVLM2-500M-Video-Instruct')" \
 && chown -R jovyan:1000 /opt/hf

# Copy related rocm notebooks into the docker
RUN mkdir -p /opt/workspace/MuJoCo-Torch
COPY ./course_data /opt/workspace/MuJoCo-Torch

# Bake any locally-trained SmolVLA checkpoints (empty if none were produced).
COPY ./ckpt_data /opt/checkpoints

USER root
RUN chown -R jovyan:1000 /opt/workspace /opt/checkpoints
USER jovyan
