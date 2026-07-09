<!-- Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved. -->
<!--
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
-->

# AUP Learning Cloud Base Images

## GPU Base Image (`Dockerfile.rocm`)

Multi-target ROCm GPU base image. Set `GPU_TARGET` to build for any supported architecture.
`Dockerfile.rocm` tracks the current course-image baseline: ROCm 7.13.0 Core SDK
from AMD's Ubuntu 24.04 apt repository, plus ROCm-enabled PyTorch wheels.

### Supported Targets

| GPU_TARGET    | Arch     | GPUs                            | Pip wheel path (derived) |
|---------------|----------|---------------------------------|--------------------------|
| gfx110x       | RDNA 3   | gfx1100/1101/1102/1103 (dGPU)   | gfx110X-all              |
| gfx1150       | RDNA 3.5 | Strix (Radeon 890M)             | gfx1150                  |
| gfx1151       | RDNA 3.5 | Strix Halo (Radeon 8060S)       | gfx1151                  |
| gfx1152       | RDNA 3.5 | Ryzen AI 300-series iGPU        | gfx1152                  |
| gfx120x       | RDNA 4   | gfx1201 (dGPU: RX 9070 XT, R9700, RX 9600 GRE, …) | gfx120X-all |

The `GPU_TARGET` value selects the PyTorch wheel bucket and becomes the
image-tag suffix. The ROCm SDK is installed from the matching arch-specific
`amdrocm-core-sdk7.13-<ROCM_SDK_TARGET>` apt package to avoid pulling every
supported architecture into each image. Generic image buckets use the matching
generic SDK target, for example `gfx110x` and `gfx120x`.

The pip wheel index at <https://repo.amd.com/rocm/whl/> uses the "long"
`gfxNNNX-all` path for the generic RDNA 3 / RDNA 4 buckets; `Dockerfile.rocm`
maps short → long automatically. CI passes `PYTORCH_WHL_TARGET` and
`ROCM_SDK_TARGET` explicitly (see `.github/build-config.json`).

The baseline PyTorch stack follows AMD's ROCm 7.13.0 wheel set while keeping
the existing course-facing framework versions: `torch==2.9.1+rocm7.13.0`,
`torchvision==0.24.0+rocm7.13.0`, and `torchaudio==2.9.0+rocm7.13.0`.

### Build

```bash
# Default target (gfx1151 = Strix Halo)
docker build -t ghcr.io/amdresearch/auplc-base:latest --file Dockerfile.rocm .

# Specific target
docker build --build-arg GPU_TARGET=gfx120x \
  --build-arg ROCM_SDK_TARGET=gfx1201 \
  -t ghcr.io/amdresearch/auplc-base:latest-gfx120x --file Dockerfile.rocm .

# Using make (from dockerfiles/ directory)
make base-rocm                         # default target
make base-rocm GPU_TARGET=gfx120x      # RDNA 4 desktop GPUs
make base-rocm GPU_TARGET=gfx110x      # RDNA 3 desktop GPUs
make base-rocm GPU_TARGET=gfx1152      # Ryzen AI 300-series iGPU
```

### Override PyTorch Wheel URL

For edge cases, override the derived PyTorch wheel URL directly:

```bash
docker build \
  --build-arg PYTORCH_INDEX_URL=https://custom.url/whl/ \
  --file Dockerfile.rocm .
```

## CPU Base Image (`Dockerfile.cpu`)

```bash
docker build -t ghcr.io/amdresearch/auplc-default:latest --file Dockerfile.cpu .
```

## Resource Path Contract

Resource metadata in `runtime/values.yaml` can set `defaultPath` for the
initial landing path inside the container. It controls where JupyterLab or
code-server opens first. It is not a security boundary, an access boundary, or a
runtime guarantee that the directory exists.

The Hub chooses the target path in this order:

1. Custom Repo clone path, when the user supplies a repository.
2. Resource `defaultPath`, when configured.
3. The image or single-user application default, normally the image `WORKDIR`.

For official images, keep `custom.resources.metadata.<resource>.defaultPath` in
sync with the image `WORKDIR`. Check the local image contracts with:

```bash
make -C dockerfiles verify-resource-contracts
```

That verifier checks the official image contract. Runtime spawning still does
not check path existence for arbitrary or custom images. If an environment
points at a custom image, make sure the configured `defaultPath` exists in that
image, or omit `defaultPath` to let the image `WORKDIR` control the initial
folder.

## Generic Code Images

The base images remain the foundation for notebook and coding environments. Generic code-server images are built separately from `dockerfiles/Code/`:

```bash
# From the repository root
make -C dockerfiles code-cpu
make -C dockerfiles code-gpu GPU_TARGET=gfx1151
make -C dockerfiles code
```

`auplc-code-cpu` inherits from `auplc-default`, and `auplc-code-gpu` inherits from `auplc-base`. These are generic development images, not per-course VS Code variants. See `dockerfiles/Code/README.md` for the code-server runtime, security, and extension notes.
