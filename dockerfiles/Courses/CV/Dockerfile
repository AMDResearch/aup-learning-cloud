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

# OpenCV (pulled in by ultralytics) needs libGL / glib at import time
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Course dependencies: ultralytics + lap (CV03 detection, CV06 ByteTrack tracking),
# segment-anything + pycocotools (CV05), kagglehub (CV04 CamVid download).
# Pin the base image's torch stack so these packages cannot replace the ROCm wheels.
RUN pip3 freeze | grep -iE '^(torch|torchvision|torchaudio|numpy)==' > /tmp/base-pins.txt && \
    pip3 install --no-cache-dir -c /tmp/base-pins.txt \
    ultralytics \
    lap \
    segment-anything \
    pycocotools \
    kagglehub \
    && rm /tmp/base-pins.txt

# Copy related rocm notebooks into the docker
RUN mkdir -p /opt/workspace/CV
COPY ./course_data /opt/workspace/CV

RUN chown -R jovyan:1000 /opt/workspace
USER jovyan
WORKDIR /opt/workspace/CV
