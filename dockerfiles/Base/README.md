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

Multi-profile ROCm GPU base image. `Dockerfile.rocm` is standalone when built
from the repository root: pass an optional `AUP_IMAGE_PROFILE` directly to
`docker build`, or omit it to use the canonical catalog default (`gfx1151`). It
tracks ROCm 7.14.0 TheRock Core SDK packages from AMD's multi-architecture
Ubuntu 24.04 repository and matching ROCm-enabled PyTorch wheels.

### Profiles and Targets

An **image profile** is the user-facing build and image-tag selection. A
**target** is the concrete GPU architecture selected by that profile. The
catalog currently defines one target per profile, but consumers must pass a
profile and let the resolver select artifacts and tag suffixes.

| AUP_IMAGE_PROFILE | Current resolved target | Image tag suffix |
|-------------------|-------------------------|------------------|
| gfx1103 | gfx1103 | gfx1103 |
| gfx1150 | gfx1150 | gfx1150 |
| gfx1151 | gfx1151 | gfx1151 |
| gfx1152 | gfx1152 | gfx1152 |
| gfx1200 | gfx1200 | gfx1200 |
| gfx1201 | gfx1201 | gfx1201 |

All six profiles are buildable through the catalog. `gfx1152` is build-only:
it has no runtime accelerator or ROCm labeller product mapping. Runtime bundles
are produced for `gfx1103`, `gfx1150`, `gfx1151`, `gfx1200`, and `gfx1201`.

`auplc_installer/data/rocm-profiles.yaml` is the stable canonical catalog for
one active rolling TheRock/ROCm baseline. Replace it atomically after
qualification with its artifact facts and provenance evidence; it is not a
runtime ROCm version selector.
`dockerfiles/Base/rocm-targets.py` resolves a profile to its complete
BuildPlan: the APT signing key and source, Core SDK package, wheel index, exact
Torch and TorchVision requirements, and TorchAudio requirement. The Dockerfile
copies the catalog, resolver module, and CLI into the image build context, so
raw repository-root Docker builds remain self-resolving. Do not construct
package names or wheel extras in Docker, Make, or CI.

### Build

```bash
# From the repository root: default image profile (gfx1151)
docker build -f dockerfiles/Base/Dockerfile.rocm \
  -t ghcr.io/amdresearch/auplc-base:latest .

# Specific image profile
docker build -f dockerfiles/Base/Dockerfile.rocm \
  --build-arg AUP_IMAGE_PROFILE=gfx1200 \
  -t ghcr.io/amdresearch/auplc-base:latest-gfx1200 .

# Using make (from dockerfiles/ directory)
make base-rocm                                      # catalog default
make base-rocm AUP_IMAGE_PROFILE=gfx1200
make code-gpu AUP_IMAGE_PROFILE=gfx1201
make courses AUP_IMAGE_PROFILE=gfx1200
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
make -C dockerfiles code-gpu AUP_IMAGE_PROFILE=gfx1151
make -C dockerfiles code
```

`auplc-code-cpu` inherits from `auplc-default`, and `auplc-code-gpu` inherits from `auplc-base`. These are generic development images, not per-course VS Code variants. See `dockerfiles/Code/README.md` for the code-server runtime, security, and extension notes.
