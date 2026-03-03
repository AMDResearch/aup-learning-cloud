# AUP Learning Cloud Base Images

## GPU Base Image (`Dockerfile.rocm`)

Multi-target ROCm GPU base image. Set `GPU_TARGET` to build for any supported architecture.

### Supported Targets

| GPU_TARGET    | Arch     | GPUs                            |
|---------------|----------|---------------------------------|
| gfx110X-all   | RDNA 3   | gfx1100/1101/1102/1103 (dGPU)   |
| gfx1150       | RDNA 3.5 | Strix (Radeon 890M)             |
| gfx1151       | RDNA 3.5 | Strix Halo (Radeon 8060S)       |
| gfx1152       | RDNA 3.5 |                                 |
| gfx120X-all   | RDNA 4   | gfx1201 (dGPU)                  |

### Build

```bash
# Default target (gfx110X-all)
docker build -t ghcr.io/amdresearch/auplc-base:latest --file Dockerfile.rocm .

# Specific target
docker build --build-arg GPU_TARGET=gfx1151 \
  -t ghcr.io/amdresearch/auplc-base:latest-gfx1151 --file Dockerfile.rocm .

# Using make (from dockerfiles/ directory)
make base-rocm                          # default target
make base-rocm GPU_TARGET=gfx1151      # specific target
```

### Override URLs

For edge cases, override the derived URLs directly:

```bash
docker build \
  --build-arg ROCM_TARBALL_URL=https://custom.url/rocm.tar.gz \
  --build-arg PYTORCH_INDEX_URL=https://custom.url/whl/ \
  --file Dockerfile.rocm .
```

## CPU Base Image (`Dockerfile.cpu`)

```bash
docker build -t ghcr.io/amdresearch/auplc-default:latest --file Dockerfile.cpu .
```
