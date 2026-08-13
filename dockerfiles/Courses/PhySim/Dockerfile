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

ARG BASE_IMAGE=ghcr.io/amdresearch/auplc-base:latest
FROM ${BASE_IMAGE}

ARG GENESIS_WORLD_VERSION=1.3.1

ENV ROCM_PYTHON_LIB=/opt/rocm-python/lib
ENV LD_LIBRARY_PATH="${ROCM_PYTHON_LIB}:${LD_LIBRARY_PATH}"

USER root
RUN SDK_LIB=$(python3 -c "import _rocm_sdk_core, os; print(os.path.join(os.path.dirname(_rocm_sdk_core.__file__), 'lib'))") && \
    mkdir -p /opt/rocm-python && \
    ln -s "${SDK_LIB}" "${ROCM_PYTHON_LIB}" && \
    ln -sf libamdhip64.so.7 "${SDK_LIB}/libamdhip64.so" && \
    ln -sf /opt/rocm/lib/llvm/bin/ld.lld /usr/local/bin/ld.lld

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 libglx-mesa0 libgl1-mesa-dri libegl1 libgbm1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir \
    "numpy>=1.26.4,<2.4" \
    "genesis-world==${GENESIS_WORLD_VERSION}"

COPY --chown=jovyan:1000 ./course_data /opt/workspace/PhySim

USER jovyan
WORKDIR /opt/workspace/PhySim
