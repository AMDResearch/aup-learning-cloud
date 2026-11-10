# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
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

ARG BASE_IMAGE=ghcr.io/amdresearch/auplc-base:latest
FROM ${BASE_IMAGE}

ARG HIP_TUTORIAL_REPO=https://github.com/AMDResearch/introduction_to_hip
ARG HIP_TUTORIAL_SHA=470d709cc74c0a68679804af29946f7135c903aa
ARG HIP_OFFLOAD_ARCHS="gfx1100,gfx1101,gfx1102,gfx1103,gfx1150,gfx1151,gfx1152,gfx1200,gfx1201"

USER root

RUN git init -q /tmp/introduction_to_hip && \
    cd /tmp/introduction_to_hip && \
    git remote add origin "${HIP_TUTORIAL_REPO}" && \
    git fetch -q --depth 1 origin "${HIP_TUTORIAL_SHA}" && \
    git checkout -q FETCH_HEAD && \
    mkdir -p /opt/workspace/HIP-Tutorial /usr/share/doc/introduction_to_hip && \
    cp -a examples exercises /opt/workspace/HIP-Tutorial/ && \
    cp LICENSE.md /usr/share/doc/introduction_to_hip/ && \
    rm -rf /tmp/introduction_to_hip

RUN find /opt/workspace/HIP-Tutorial -name submit.sh -delete
RUN find /opt/workspace/HIP-Tutorial -name Makefile -exec sed -i "s/gfx90a/${HIP_OFFLOAD_ARCHS}/" {} +

# Copy the tutorial notebook(s)
COPY ./course_data /opt/workspace/HIP-Tutorial

RUN chown -R jovyan:1000 /opt/workspace
USER jovyan
WORKDIR /opt/workspace/HIP-Tutorial
