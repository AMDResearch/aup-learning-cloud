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
#
# --------------------------------------------------------------------------
# auplc-vllm — vLLM + AITER flash-attention on top of auplc-base.
#
# Builds vLLM, ROCm/flash-attention (main_perf), and AITER from source against
# the apt-installed ROCm 7.12 SDK and the PyTorch wheel already shipped in
# auplc-base (no torch swap, no prebuilt wheels). Targets the Strix Halo
# iGPU (gfx1151 / RDNA 3.5) by default; override GPU_TARGET to retarget.
#
# gfx1151 (RDNA 3.5) is not a first-class target in vLLM, AITER, or
# ROCm/flash-attention HEAD as of 2026-05; the gaps are closed by three
# small scripts shipped alongside this Dockerfile:
#   * patch_aiter_headers.py     — RDNA scalar fallbacks for two AITER
#                                  csrc headers that emit CDNA-only ISA
#                                  (v_pk_mul_f32, v_cvt_pk_fp8_f32,
#                                   row_bcast:15/:31 DPP, …).
#   * patch_flash_attn_setup.py  — strips flash-attention's setup.py
#                                  in-tree AITER rebuild step.
#   * patch_strix.py             — vLLM gfx1x enablement: stub amdsmi,
#                                  add on_gfx1x() to feature gates,
#                                  fix PatternMatcher duplicates, lift
#                                  the Triton-MoE compute-cap ceiling,
#                                  proxy torch.cuda.mem_get_info around
#                                  the APU GTT clamp (ROCM-21812).
# Each block is documented at its declaration site; delete blocks as
# upstream support lands.
# --------------------------------------------------------------------------

ARG BASE_IMAGE=ghcr.io/amdresearch/auplc-base:latest
FROM ${BASE_IMAGE}

SHELL ["/bin/bash", "-c"]

# auplc-base ends as USER jovyan. Switch to root for system installs;
# pip-as-jovyan silently lands in ~/.local and gets masked by the PVC mount
# at runtime.
USER root

# GPU target — must match what auplc-base was built with. Defaults to Strix
# Halo (gfx1151). The Dev / runtime ROCm apt packages are pinned per-GPU.
ARG GPU_TARGET=gfx1151
ARG ROCM_VERSION=7.12.0

# Pin the upstream sources we build against. Override at build time for a
# different vLLM / flash-attention / AITER cut.
ARG VLLM_REPO=https://github.com/vllm-project/vllm.git
ARG VLLM_REF=
ARG FLASH_ATTN_REPO=https://github.com/ROCm/flash-attention.git
ARG FLASH_ATTN_REF=main_perf

# Build parallelism — vLLM HIP compile is RAM-hungry. Override on a beefier
# host: --build-arg MAX_JOBS=8.
ARG MAX_JOBS=4

# --------------------------------------------------------------------------
# 1) ROCm dev + build toolchain. auplc-base ships the runtime metapackage
#    (amdrocm7.12-<GPU>) but not all dev headers / cmake configs the vLLM,
#    AITER, and flash-attention HIP sources need. Install the matching
#    -dev packages from the same AMD apt repo that auplc-base already
#    configured.
# --------------------------------------------------------------------------
RUN ROCM_MAJ_MIN="${ROCM_VERSION%.*}" && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        ninja-build \
        cmake \
        pkg-config \
        libnuma-dev \
        libelf-dev \
        libdrm-dev \
        zlib1g-dev \
        libssl-dev \
        amdrocm-runtime-dev${ROCM_MAJ_MIN} \
        amdrocm-llvm-dev${ROCM_MAJ_MIN} \
        amdrocm-core-dev${ROCM_MAJ_MIN}-${GPU_TARGET} \
        amdrocm-core-sdk${ROCM_MAJ_MIN}-${GPU_TARGET} \
        amdrocm-hipblas-common-dev${ROCM_MAJ_MIN}-${GPU_TARGET} \
        amdrocm-blas-dev${ROCM_MAJ_MIN}-${GPU_TARGET} \
        amdrocm-rand-dev${ROCM_MAJ_MIN}-${GPU_TARGET} \
        amdrocm-fft-dev${ROCM_MAJ_MIN}-${GPU_TARGET} \
        amdrocm-sparse-dev${ROCM_MAJ_MIN}-${GPU_TARGET} \
        amdrocm-solver-dev${ROCM_MAJ_MIN}-${GPU_TARGET} \
        amdrocm-dnn-dev${ROCM_MAJ_MIN}-${GPU_TARGET} \
        amdrocm-rccl-dev${ROCM_MAJ_MIN}-${GPU_TARGET} \
        amdrocm-ccl-dev${ROCM_MAJ_MIN}-${GPU_TARGET} && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# ROCm 7.12 packaging gap: amdrocm-solver-dev ships
# /opt/rocm/lib/cmake/hipsolver/hipsolver-targets-release.cmake which references
# libhipsolver_fortran.so.1.0, but no deb actually installs that file. torch
# pulls hipsolver in via Caffe2Config.cmake on every HIP build (vLLM, AITER,
# flash-attn), so CMake configure fails with:
#   The imported target "roc::hipsolver_fortran" references the file
#   "/opt/rocm/.../lib/libhipsolver_fortran.so.1.0" but this file does not exist.
# vLLM doesn't actually call into hipsolver's Fortran ABI, so symlinking the
# C-ABI lib to the missing fortran filename satisfies the file-existence check
# without affecting runtime behaviour. Drop this when AMD ships a real
# libhipsolver_fortran.so.1.0 in the apt repo.
RUN ROCM_MAJ_MIN="${ROCM_VERSION%.*}" && \
    for libdir in "/opt/rocm/lib" "/opt/rocm/core-${ROCM_MAJ_MIN}/lib"; do \
        if [ -f "${libdir}/libhipsolver.so.1.0" ] && [ ! -e "${libdir}/libhipsolver_fortran.so.1.0" ]; then \
            ln -s libhipsolver.so.1.0 "${libdir}/libhipsolver_fortran.so.1.0" && \
            ln -s libhipsolver.so.1.0 "${libdir}/libhipsolver_fortran.so.1" && \
            ln -s libhipsolver.so.1.0 "${libdir}/libhipsolver_fortran.so"; \
        fi; \
    done

# Python build-time deps. Pinned setuptools<80 because AITER / flash-attention
# still use the legacy setup.py codepath that 80+ removed.
#
# --ignore-installed is required because pip / wheel / setuptools ship from
# Debian (python3-pip, python3-wheel, python3-setuptools) under
# /usr/lib/python3/dist-packages without a RECORD file, so pip refuses to
# uninstall them during --upgrade. Letting the newer versions shadow the
# distro-provided ones in /usr/local/lib/python3.12/dist-packages is the
# canonical workaround.
RUN pip3 install --no-cache-dir --upgrade --ignore-installed \
        "pip" \
        "wheel" \
        "packaging" \
        "setuptools<80.0.0" \
        "setuptools-scm>=8" \
        "scikit-build-core" \
        "cmake" \
        "ninja" \
        "pybind11" \
        "numba" \
        "scipy"

# --------------------------------------------------------------------------
# 2) Compile env. ROCm clang is at /opt/rocm/lib/llvm/bin/clang(++) inside
#    the apt layout (auplc-base symlinks /opt/rocm/{bin,lib,include} →
#    /opt/rocm/core-<ver>/{bin,lib,include}). Force it as the host compiler
#    so vLLM/AITER/flash-attn extensions match the PyTorch wheel ABI.
# --------------------------------------------------------------------------
ENV ROCM_PATH=/opt/rocm \
    HIP_PATH=/opt/rocm \
    HIP_PLATFORM=amd \
    HIP_DEVICE_LIB_PATH=/opt/rocm/lib/llvm/amdgcn/bitcode \
    CC=/opt/rocm/lib/llvm/bin/clang \
    CXX=/opt/rocm/lib/llvm/bin/clang++ \
    PYTORCH_ROCM_ARCH=${GPU_TARGET} \
    HIP_ARCHITECTURES=${GPU_TARGET} \
    AMDGPU_TARGETS=${GPU_TARGET} \
    GPU_TARGETS=${GPU_TARGET} \
    HCC_AMDGPU_TARGET=${GPU_TARGET} \
    VLLM_TARGET_DEVICE=rocm \
    FLASH_ATTENTION_TRITON_AMD_ENABLE=TRUE \
    LD_LIBRARY_PATH=/opt/rocm/lib:/opt/rocm/lib64

# --------------------------------------------------------------------------
# 3) Build & install AITER. The wheel ships csrc headers + .co code objects
#    — kernels are JIT-built at first import — so the RDNA-fallback header
#    patches (patch_aiter_headers.py) MUST be re-applied AFTER pip install,
#    against the installed aiter_meta/csrc/include/ tree.
#
#    optCompilerConfig.gfx1151.json is a curated drop-in replacement for
#    aiter/jit/optCompilerConfig.json. It removes ~37 modules that cannot
#    build on RDNA 3.5 (HSA-asm blobs, FAV3, fp4 / CK FlatMM-18, MLA,
#    HipKittens, gradlib, TP-only all-reduce …) so a stray
#    @compile_ops("module_<...>") fail-fasts with a clear "module not in
#    config" warning instead of letting hipcc emit an opaque CDNA-ISA
#    error 30s into the JIT step. Each kept module also gets
#    `-DCK_TILE_RDNA3_NO_PK_FP8=1 -DAITER_RDNA_NO_DPP_BCAST=1` pinned in
#    flags_extra_hip so the patched headers' fallback paths fire even
#    when PyTorch invokes clang++ directly and skips hipcc's hardware-
#    detection wrappers.
# --------------------------------------------------------------------------
WORKDIR /opt
RUN git clone --depth 1 -b "${FLASH_ATTN_REF}" "${FLASH_ATTN_REPO}" /opt/flash-attention && \
    cd /opt/flash-attention && \
    git submodule update --init third_party/aiter && \
    cd third_party/aiter && \
    git submodule update --init 3rdparty/composable_kernel

COPY patch_aiter_headers.py        /tmp/patch_aiter_headers.py
COPY patch_flash_attn_setup.py     /tmp/patch_flash_attn_setup.py
COPY optCompilerConfig.gfx1151.json /tmp/optCompilerConfig.gfx1151.json

RUN set -eo pipefail; \
    cd /opt/flash-attention/third_party/aiter && \
    export CK_DIR="$(pwd)/3rdparty/composable_kernel" && \
    PREBUILD_KERNELS=1 \
    python3 /tmp/patch_aiter_headers.py && \
    rm -f /tmp/patch_aiter_headers.py && \
    MAX_JOBS="${MAX_JOBS}" pip3 wheel --no-build-isolation --no-deps -w /tmp/dist -v . && \
    pip3 install --force-reinstall /tmp/dist/amd_aiter*.whl && \
    rm -rf /tmp/dist && \
    AITER_DIR="$(python3 -c 'import aiter, os; print(os.path.dirname(aiter.__file__))')" && \
    cp -f /tmp/optCompilerConfig.gfx1151.json "${AITER_DIR}/jit/optCompilerConfig.json" && \
    rm -f /tmp/optCompilerConfig.gfx1151.json && \
    echo "[gfx1151] installed curated optCompilerConfig.json -> ${AITER_DIR}/jit/" && \
    { find /usr/local/lib /usr/lib -type f -name "*.so" 2>/dev/null | xargs -r strip -s 2>/dev/null || true; } && \
    rm -rf /root/.cache/pip

# --------------------------------------------------------------------------
# 4) Build & install ROCm flash-attention (Triton AMD backend). The python
#    wrapper around the AITER kernels. Upstream setup.py rebuilds AITER as
#    a subprocess — strip that out, we already installed it above.
# --------------------------------------------------------------------------
RUN python3 /tmp/patch_flash_attn_setup.py /opt/flash-attention/setup.py && \
    rm -f /tmp/patch_flash_attn_setup.py && \
    cd /opt/flash-attention && \
    pip3 install --no-cache-dir --no-build-isolation --no-deps . && \
    cd /opt && rm -rf /opt/flash-attention && \
    rm -rf /root/.cache/pip

# --------------------------------------------------------------------------
# 5) Build & install vLLM. patch_strix.py applies the gfx1151 enablement
#    workarounds against a fresh vllm-project/vllm clone (amdsmi stubs,
#    on_gfx1x() in feature gates, AITER fused MoE / FP8 linear opt-out,
#    PatternMatcher skip_duplicates, Triton-MoE compute-cap ceiling, GTT
#    memory-info proxy). Each block is documented in patch_strix.py.
# --------------------------------------------------------------------------
RUN git clone "${VLLM_REPO}" /opt/vllm && \
    cd /opt/vllm && \
    if [ -n "${VLLM_REF}" ]; then \
        git fetch --depth 1 origin "${VLLM_REF}" && git checkout "${VLLM_REF}"; \
    fi

COPY patch_strix.py /tmp/patch_strix.py
RUN cd /opt/vllm && \
    cp /tmp/patch_strix.py ./patch_strix.py && \
    python3 ./patch_strix.py && \
    rm -f /tmp/patch_strix.py

RUN set -eo pipefail; \
    cd /opt/vllm && \
    export CMAKE_PREFIX_PATH="${ROCM_PATH}${CMAKE_PREFIX_PATH:+:${CMAKE_PREFIX_PATH}}" && \
    export CMAKE_ARGS="-DROCM_PATH=${ROCM_PATH} -DHIP_PATH=${ROCM_PATH} -DAMDGPU_TARGETS=${GPU_TARGET} -DHIP_ARCHITECTURES=${GPU_TARGET} -DCMAKE_HIP_COMPILER=${CXX}" && \
    export NVCC_THREADS=1 && \
    MAX_JOBS="${MAX_JOBS}" pip3 wheel --no-build-isolation --no-deps -w /tmp/dist -v . && \
    pip3 install --no-cache-dir /tmp/dist/vllm-*.whl && \
    cd /opt && rm -rf /opt/vllm /tmp/dist /opt/-.o && \
    { find /usr/local/lib /usr/lib -type f -name "*.so" 2>/dev/null | xargs -r strip -s 2>/dev/null || true; } && \
    rm -rf /root/.cache/pip

# Ray for offline TP / multi-process scheduling.
RUN pip3 install --no-cache-dir "ray>=2.55" && rm -rf /root/.cache/pip

# torch_c_dlpack_ext is a CUDA-only optimization wheel pulled in transitively
# by xgrammar -> apache-tvm-ffi. Its prebuilt .so set ships only
# libtorch_c_dlpack_addon_torch{29,28,...}-{cuda,cpu}.so — no ROCm variant —
# and the cuda one links against libtorch_cuda.so, which the ROCm PyTorch
# wheel does not provide (it ships libtorch_hip.so). At import time
# torch_c_dlpack_ext/core.py does ctypes.CDLL(...) at module top level on
# the cuda .so, raising OSError. tvm_ffi's loader only catches ImportError /
# AttributeError around `import torch_c_dlpack_ext`, so the OSError escapes
# and detonates every consumer of xgrammar — including `vllm bench`,
# `vllm serve`, and any import of vllm.entrypoints.openai.api_server.
# Drop the wheel entirely (it can never run on ROCm) and additionally set
# TVM_FFI_DISABLE_TORCH_C_DLPACK=1 to short-circuit tvm_ffi's optional
# loader so it doesn't even attempt the JIT-build fallback at first import.
RUN pip3 uninstall -y torch_c_dlpack_ext || true

# --------------------------------------------------------------------------
# 6) Strix Halo runtime knobs. VLLM_USE_TRITON_FLASH_ATTN=1 +
#    FLASH_ATTENTION_TRITON_AMD_ENABLE=TRUE forces vLLM down the AITER /
#    Triton attention path — the only one that works on gfx1151 today.
# --------------------------------------------------------------------------
ENV FLASH_ATTENTION_TRITON_AMD_ENABLE=TRUE \
    HIP_FORCE_DEV_KERNARG=1 \
    ROCBLAS_USE_HIPBLASLT=1 \
    TORCH_ROCM_AOTRITON_ENABLE_EXPERIMENTAL=1 \
    RAY_EXPERIMENTAL_NOSET_ROCR_VISIBLE_DEVICES=1 \
    TVM_FFI_DISABLE_TORCH_C_DLPACK=1

# Build-time smoke: fail fast on torch / vllm ABI mismatch BEFORE the image
# gets tagged. Requires no GPU — only validates the import graph.
#
# NOTE: flash_attn cannot be `import`-ed inside `docker build`, because its
# import chain reaches aiter.ops.triton._triton_kernels.flash_attn_triton_amd
# .fwd_prefill, which at MODULE TOP LEVEL calls
# `triton.runtime.driver.active.get_current_target().arch`. Triton's driver
# auto-detection needs /dev/kfd + /dev/dri/* visible, which the BuildKit
# sandbox does not expose, so it raises
# `RuntimeError: 0 active drivers ([])`. The same import works fine at
# container runtime once GPUs are passed through. For that package we only
# verify the wheel is installed & discoverable via importlib.metadata, which
# is enough to catch a missing / unbuilt flash-attn without booting Triton.
RUN python3 - <<'PY'
import importlib
import importlib.metadata as md

# Packages whose top-level import is safe without a GPU.
for m in ("torch", "triton", "aiter", "vllm", "ray"):
    mod = importlib.import_module(m)
    print(f"  {m:10s} : {getattr(mod, '__version__', '?')}")

# Packages whose top-level import eagerly touches the Triton driver —
# verify presence via package metadata only at build time.
for m in ("flash_attn",):
    print(f"  {m:10s} : {md.version(m)} (metadata-only; import deferred to runtime)")

# Exercise the CLI / OpenAI server import graph. `import vllm` alone does
# NOT walk into vllm.entrypoints.* / vllm.v1.structured_output.* /
# xgrammar / tvm_ffi, so a broken xgrammar (e.g. CUDA-only torch_c_dlpack_ext
# OSError on ROCm) will silently pass `import vllm` and only blow up the
# first time a user runs `vllm bench` or `vllm serve`. Walk the same chain
# the CLI does, at build time, so this regression class fails the build.
for m in (
    "vllm.entrypoints.cli.main",
    "vllm.entrypoints.openai.api_server",
    "vllm.v1.structured_output.backend_xgrammar",
):
    importlib.import_module(m)
    print(f"  {m} : OK")
PY

# --------------------------------------------------------------------------
# 7) OpenAI-compat server + benchmark + chat helpers. JupyterHub entrypoint
#    from auplc-base stays as the default CMD. Override the container command
#    to:
#      * `start-vllm-server`  — general-purpose server (Qwen 0.5B default,
#                               max_len=4096), backwards compat.
#      * `server`             — bench-tuned vLLM API server (Qwen3-4B
#                               default, max_len=2048, no per-request
#                               logging). Pairs with `bench` and `chat`.
#      * `bench`              — `vllm bench serve` (default) or `bench
#                               throughput`. Polls /v1/models before
#                               starting in serve mode. Writes JSON to
#                               /results.
#      * `chat`               — interactive CLI chat client wrapping
#                               `vllm chat`. Polls /v1/models, then
#                               drops into a multi-turn REPL. Also
#                               supports one-shot via positional arg or
#                               stdin pipe.
#    Typical usage:
#      docker run -d --name vllm ... ghcr.io/.../auplc-vllm:latest server
#      docker exec      vllm bench
#      docker exec -it  vllm chat
#      docker exec      vllm chat "Summarise RDNA 3.5 in two bullets."
# --------------------------------------------------------------------------
COPY --chown=jovyan:1000 start-vllm-server.sh /usr/local/bin/start-vllm-server
COPY --chown=jovyan:1000 server.sh            /usr/local/bin/server
COPY --chown=jovyan:1000 bench.sh             /usr/local/bin/bench
COPY --chown=jovyan:1000 chat.sh              /usr/local/bin/chat
RUN chmod +x /usr/local/bin/start-vllm-server \
             /usr/local/bin/server \
             /usr/local/bin/bench \
             /usr/local/bin/chat

# Drop the same helpers + an intro notebook into the JupyterLab landing dir
# (/opt/workspace) so users see them immediately when the spawn lands. We
# create the directory explicitly because the WORKDIR step below would
# create it as root-owned if we tried to COPY into a missing path first.
RUN install -d -o jovyan -g 1000 /opt/workspace
COPY --chown=jovyan:1000 server.sh                       /opt/workspace/server.sh
COPY --chown=jovyan:1000 bench.sh                        /opt/workspace/bench.sh
COPY --chown=jovyan:1000 chat.sh                         /opt/workspace/chat.sh
COPY --chown=jovyan:1000 Welcome-vLLM-on-Strix-Halo.ipynb /opt/workspace/Welcome-vLLM-on-Strix-Halo.ipynb
RUN chmod +x /opt/workspace/server.sh /opt/workspace/bench.sh /opt/workspace/chat.sh

EXPOSE 8000 8888

USER 1000
WORKDIR /opt/workspace

CMD ["/bin/bash", "/entrypoint.sh"]
