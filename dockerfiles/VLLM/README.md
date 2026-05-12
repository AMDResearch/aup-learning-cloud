<!-- Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved. -->
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

# AUP Learning Cloud vLLM Base Image

`Dockerfile` builds **`ghcr.io/amdresearch/auplc-vllm`** — a vLLM-enabled
JupyterHub singleuser image. It layers on top of `auplc-base` (Ubuntu 24.04
+ ROCm 7.12 + ROCm PyTorch) and adds:

| Component        | How                                                            | Source                                              |
| ---------------- | -------------------------------------------------------------- | --------------------------------------------------- |
| ROCm dev headers | apt (`amdrocm-*-dev<ver>-<gpu>` + math libs)                   | Same AMD apt repo `auplc-base` already configured   |
| AITER            | built from source against the apt-installed ROCm SDK           | `ROCm/flash-attention/third_party/aiter` (submodule) |
| flash-attention  | python wrapper, `--no-deps`, AITER rebuild stripped            | `ROCm/flash-attention` @ `main_perf`                |
| vLLM             | wheel build, gfx1151 enablement patches applied to a fresh     | `vllm-project/vllm` (HEAD by default)               |
|                  | `git clone` (see `patch_strix.py`)                             |                                                     |
| Ray              | `pip3 install "ray>=2.55"`                                     | PyPI                                                |

gfx1151 (RDNA 3.5 / Strix Halo) is not a first-class target in vLLM, AITER,
or `ROCm/flash-attention` HEAD as of 2026-05. The image closes those gaps
with three local patch scripts:

| Script                       | Closes which upstream gap                                                                                                                 |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `patch_aiter_headers.py`     | Two AITER `csrc/include/` headers (`ck_tile/vec_convert.h`, `hip_reduce.h`) emit CDNA-only ISA — provide RDNA scalar / `ds_swizzle` fallbacks |
| `patch_flash_attn_setup.py`  | `ROCm/flash-attention`'s `setup.py` reruns the in-tree AITER build inside `pip install` — strip it, we have AITER already                  |
| `patch_strix.py`             | vLLM: stub `amdsmi` (broken on APU), add `on_gfx1x()` to AITER feature gates, opt out of AITER fused-MoE / FP8 linear, lift Triton-MoE `(11,0)` cap to `(12,0)`, proxy `torch.cuda.mem_get_info` past the ROCM-21812 APU GTT clamp |

Each block inside `patch_strix.py` is annotated with the upstream gap it
addresses. When upstream lands real support, delete the corresponding
block — the script is idempotent and sentinel-guarded, so leftover blocks
turn into harmless no-ops first, then become removable.

## Supported GPU targets

Same matrix as `Base/Dockerfile.rocm` — the value of `GPU_TARGET` is used
both as the apt suffix (`amdrocm7.12-<GPU_TARGET>`) and as the kernel
target (`AMDGPU_TARGETS`):

| GPU_TARGET | Arch     | GPUs                                           |
| ---------- | -------- | ---------------------------------------------- |
| gfx110x    | RDNA 3   | gfx1100/1101/1102/1103 (dGPU)                  |
| gfx1150    | RDNA 3.5 | Strix (Radeon 890M)                            |
| gfx1151    | RDNA 3.5 | Strix Halo (Radeon 8060S) — **default**        |
| gfx1152    | RDNA 3.5 |                                                |
| gfx120x    | RDNA 4   | gfx1201 (RX 9070 XT, R9700, RX 9600 GRE, …)    |

The Strix Halo patches are only verified on `gfx1151` today. The build
*will* compile for the other RDNA targets, but you may want to broaden the
`#ifdef`s in `patch_aiter_headers.py::VEC_CONVERT` / `HIP_REDUCE`.

## Build

```bash
# Default — Strix Halo, vLLM @ HEAD, flash-attention @ main_perf
make vllm                              # from dockerfiles/

# Override the upstream base image (e.g. a per-GPU tag)
make vllm GPU_BASE_IMAGE=ghcr.io/amdresearch/auplc-base:latest-gfx120x \
          GPU_TARGET=gfx120x

# Pin to a specific vLLM commit for reproducible builds
make vllm VLLM_REF=v0.10.0

# Or call the build helper directly
cd dockerfiles/VLLM && ./build.sh
```

Build-time arguments (all overridable via `--build-arg` or the `build.sh`
env vars):

| Arg                | Default                                          | Purpose                                                   |
| ------------------ | ------------------------------------------------ | --------------------------------------------------------- |
| `BASE_IMAGE`       | `ghcr.io/amdresearch/auplc-base:latest`          | Parent image                                              |
| `GPU_TARGET`       | `gfx1151`                                        | Strix Halo iGPU                                           |
| `ROCM_VERSION`     | `7.12.0`                                         | Matches auplc-base's apt repo                             |
| `VLLM_REPO`        | upstream vllm-project                            |                                                            |
| `VLLM_REF`         | empty (=HEAD)                                    | Pin a specific commit/tag                                 |
| `FLASH_ATTN_REPO`  | `ROCm/flash-attention`                           |                                                            |
| `FLASH_ATTN_REF`   | `main_perf`                                      | The Triton AMD backend lives on this branch                |
| `MAX_JOBS`         | `4`                                              | HIP compile is RAM-hungry; raise on beefier hosts          |

> **Expect a long build.** Compiling AITER + vLLM HIP sources on a Strix
> Halo class machine takes ~45-90 minutes at `MAX_JOBS=4`, on top of the
> apt-install of the ROCm dev packages (~3-5 GB extra layer). The Dockerfile
> strips `.so` symbols and clears `__pycache__` at each stage to keep the
> final image around `~12 GB` rather than `>20 GB`.

## Run

### Standalone OpenAI-compatible API server

```bash
docker run --rm -it \
    --device=/dev/kfd --device=/dev/dri \
    --group-add video --group-add render \
    --ipc=host --security-opt seccomp=unconfined \
    -p 8000:8000 \
    -e MODEL=Qwen/Qwen2.5-7B-Instruct \
    -e MAX_MODEL_LEN=8192 \
    -e GPU_MEM_UTIL=0.85 \
    -v "${HOME}/.cache/huggingface:/home/jovyan/.cache/huggingface" \
    ghcr.io/amdresearch/auplc-vllm:latest \
    start-vllm-server
```

Then point any OpenAI client at `http://localhost:8000/v1`.

`start-vllm-server` honours `MODEL`, `DTYPE`, `MAX_MODEL_LEN`, `GPU_MEM_UTIL`,
`PORT`, `HOST`, `TENSOR_PARALLEL_SIZE`, and `EXTRA_ARGS` (passthrough);
trailing CLI args go straight to `python -m vllm.entrypoints.openai.api_server`.

### As a JupyterHub singleuser image

The default `CMD` is still `auplc-base`'s `/entrypoint.sh` (jupyter singleuser
on `:8888`), so this image is a drop-in profile entry. Register it in
`runtime/values.yaml` exactly like the other course images:

```yaml
custom:
  resources:
    images:
      vllm: "ghcr.io/amdresearch/auplc-vllm:latest"
```

…and inside the notebook:

```python
import os
os.environ.setdefault("VLLM_USE_TRITON_FLASH_ATTN", "1")
from vllm import LLM, SamplingParams

llm = LLM(model="Qwen/Qwen2.5-0.5B-Instruct", dtype="bfloat16",
          gpu_memory_utilization=0.5, max_model_len=2048)
print(llm.generate(["Hello!"], SamplingParams(max_tokens=32))[0].outputs[0].text)
```

## Layout

```
dockerfiles/VLLM/
├── Dockerfile                  # the recipe
├── build.sh                    # thin wrapper that the Makefile calls
├── start-vllm-server.sh        # OpenAI-compat server launcher (lands in $PATH)
├── patch_strix.py              # applied to vllm src before the wheel build
├── patch_aiter_headers.py      # applied post pip-install of AITER
├── patch_flash_attn_setup.py   # strips AITER subprocess.run from flash-attn setup.py
└── README.md                   # this file
```

## Build-time smoke test

The penultimate `RUN` in the Dockerfile imports `torch`, `triton`, `aiter`,
`flash_attn`, `vllm`, and `ray`, printing their versions. If any import
fails the build aborts — this catches torch/libtorch ABI drift or a busted
JIT path *before* the image is tagged. Real kernel launches happen at
container start, when `/dev/kfd` is mounted in.

## Maintaining the patch set

The three `patch_*.py` scripts are the only thing keeping gfx1151 on the
critical path. Every time the pinned `VLLM_REF` / `FLASH_ATTN_REF` is
bumped, do a sentinel grep against the new HEAD:

* If a `patch_strix.py` block's `if "<sentinel>" in txt:` no longer matches,
  upstream either fixed the gap or refactored around it — delete that block.
* If `csrc/include/ck_tile/vec_convert.h` or `csrc/include/hip_reduce.h` in
  AITER gain a `defined(__gfx115x__)` guard, drop `patch_aiter_headers.py`.
* If `ROCm/flash-attention` setup.py drops the `pip install third_party/aiter`
  subprocess (or gains a `--skip-aiter` flag), drop
  `patch_flash_attn_setup.py`.
