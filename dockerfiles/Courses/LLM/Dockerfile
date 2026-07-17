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

# IMPORTANT: base image ends with USER jovyan. pip install as jovyan silently
# falls back to ~/.local/, which gets masked by the PVC mount at runtime.
# Always switch to root before pip install to ensure system-wide installation.
USER root

# Install course-specific packages system-wide
RUN pip3 install --no-cache-dir \
    transformers \    
    datasets>=2.14.0 \
    tokenizers>=0.15.0 \
    accelerate>=0.25.0 \
    evaluate>=0.4.0 \
    # Parameter-efficient fine-tuning for L8 and L10
    peft>=0.7.0 \
    # Text processing and NLP utilities
    sentencepiece>=0.1.99 \
    protobuf>=3.20.0 \
    # Visualization
    seaborn>=0.11.0 \
    plotly>=5.0.0 \
    kaleido>=0.2.1 \
    # Graph visualization for L3 neural network fundamentals
    torchviz>=0.0.2 \
    graphviz>=0.20.1 \
    # Image processing
    Pillow>=8.3.0 \
    imageio>=2.9.0 \
    # Additional dependencies for advanced features
    requests>=2.28.0 \
    typing-extensions>=4.4.0

USER root

# Copy related rocm notebooks into the docker
COPY ./course_data /opt/workspace/LLM

# Datasets and pretrained weights are loaded at runtime via Hugging Face Hub
# (e.g. load_dataset, from_pretrained) into the default HF cache — not baked into the image.

RUN chown -R jovyan:1000 /opt/workspace
USER jovyan
WORKDIR /opt/workspace/LLM
