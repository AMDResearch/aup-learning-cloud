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
`Dockerfile.rocm` tracks the current course-image baseline: ROCm 10.0.0 Core SDK
from AMD's Ubuntu 24.04 apt repository, plus ROCm-enabled PyTorch wheels.

### Supported Targets

| GPU_TARGET    | Arch     | GPUs                            | ROCm 10 ISAs (apt + `torch[device-*]`) |
|---------------|----------|---------------------------------|----------------------------------------|
| gfx110x       | RDNA 3   | gfx1100/1101/1102/1103          | gfx1100 gfx1101 gfx1102 gfx1103        |
| gfx1150       | RDNA 3.5 | Strix (Radeon 890M)             | gfx1150                                |
| gfx1151       | RDNA 3.5 | Strix Halo (Radeon 8060S)      | gfx1151                                |
| gfx1152       | RDNA 3.5 | Ryzen AI 300-series iGPU        | gfx1152                                |
| gfx1153       | RDNA 3.5 | Ryzen AI 300/400-series iGPU     | gfx1153                                |
| gfx120x       | RDNA 4   | gfx1200/gfx1201 (RX 9x, R9700)  | gfx1200 gfx1201                        |

The `GPU_TARGET` value is the image-tag suffix. ROCm 10 does not ship
`gfx110x` / `gfx120x` apt or wheel buckets, so those family tags expand to
the concrete ISAs above. Specific targets such as `gfx1151` stay 1:1.
CI passes `PYTORCH_DEVICES` and `ROCM_SDK_TARGET` as space-separated ISA
lists (see `.github/build-config.json`).

The pip extra index is <https://stable.repo.amd.com/rocm/whl-next/>.
The baseline PyTorch stack follows AMD's ROCm 10.0.0 wheel set:
`torch==2.13.0+rocm10.0.0`, `torchvision==0.28.0+rocm10.0.0`, and
`torchaudio==2.11.0.2+rocm10.0.0`.

### Build

```bash
# Default target (gfx1151 = Strix Halo)
docker build -t ghcr.io/amdresearch/auplc-base:latest --file Dockerfile.rocm .

# Specific target
docker build --build-arg GPU_TARGET=gfx120x \
  --build-arg ROCM_SDK_TARGET=gfx1201 \
  --build-arg PYTORCH_DEVICES=gfx1201 \
  -t ghcr.io/amdresearch/auplc-base:latest-gfx120x --file Dockerfile.rocm .

# Using make (from dockerfiles/ directory)
make base-rocm                         # default target
make base-rocm GPU_TARGET=gfx120x      # RDNA 4 desktop GPUs
make base-rocm GPU_TARGET=gfx110x      # RDNA 3 desktop GPUs
make base-rocm GPU_TARGET=gfx1152      # Ryzen AI 300-series iGPU
make base-rocm GPU_TARGET=gfx1153      # Ryzen AI 300/400-series iGPU
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
