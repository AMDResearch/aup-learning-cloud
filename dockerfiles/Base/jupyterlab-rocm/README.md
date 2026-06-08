# jupyterlab-rocm

A JupyterLab 4 extension for monitoring AMD ROCm GPU usage and running
[`rocprofv3`](https://rocm.docs.amd.com/projects/rocprofiler-sdk/en/latest/how-to/using-rocprofv3.html)
profiling, without leaving JupyterLab.

It has two parts:

- A **GPU Monitor** that streams live metrics (GFX utilization, VRAM, power,
  temperature, clocks, processes) over a WebSocket, collected through the
  [`amdsmi`](https://rocm.docs.amd.com/projects/amdsmi/en/latest/) Python
  library.
- **Cell Profile** — profile a single PyTorch GPU notebook cell with
  `torch.profiler` in the live kernel (via the notebook toolbar button or
  `%%rocprofv3`), rendering the hottest kernels inline and in the sidebar.

## Architecture

```
JupyterLab frontend (TypeScript + React)
  ├── GPU Monitor  ──WebSocket──►  /jupyterlab-rocm/stream
  └── Cell Profile ──kernel exec─►  %%rocprofv3 (torch.profiler in kernel)
                                        │
jupyter_server extension (Tornado)      │   ┌─ cell job JSON files ─┐
  ├── metrics.py   ── amdsmi ──────────► AMD GPU                    │
  └── /profile/cell  reads ◄────────────────────────────────────────┘
                                        │
IPython kernel
  └── magics.py    ── torch.profiler wraps run_cell ──► AMD GPU
```

## Requirements

- Linux with the `amdgpu` kernel driver loaded, ROCm installed.
- Python >= 3.9, JupyterLab >= 4.
- `amdsmi` Python package (ships with ROCm). It is **not** installed as a hard
  dependency because it is normally provided by the system ROCm tree.
- PyTorch with ROCm/CUDA support (for Cell Profile).
- The server process must be able to access `/dev/kfd` and `/dev/dri` (add your
  user to the `render` and `video` groups).

## Installation

Install `amdsmi` from your ROCm tree (the source is read-only under
`/opt/rocm`, so build from a writable copy if needed):

```bash
# Option A: install directly
pip install /opt/rocm/share/amd_smi

# Option B: if /opt/rocm is read-only
cp -r /opt/rocm/share/amd_smi /tmp/amd_smi && pip install /tmp/amd_smi
```

Then install the extension:

```bash
pip install jupyterlab_rocm
```

## Development install

```bash
# Frontend deps + build
jlpm install
jlpm build

# Editable install of the Python package (builds the labextension)
pip install -e .

# Link the labextension for live rebuilds and enable the server extension
jupyter labextension develop . --overwrite
jupyter server extension enable jupyterlab_rocm

# Rebuild on change
jlpm watch
```

Verify it is wired up:

```bash
jupyter server extension list      # should list jupyterlab_rocm
jupyter labextension list          # should list jupyterlab-rocm
```

## Usage

1. Open JupyterLab and launch **ROCm GPU Monitor** from the Launcher or the
   command palette.
2. The **GPU Monitor** tab shows live charts per GPU. Adjust the sampling
   interval in the toolbar.
3. The **Cell Profile** tab lists recent cell profiling results.

## Cell Profile (`%%rocprofv3`)

Profile a single PyTorch GPU cell in the live kernel so variables from earlier
cells are preserved. Results appear inline under the cell and in the **Cell
Profile** sidebar tab.

```python
%load_ext jupyterlab_rocm
```

```python
%%rocprofv3 --kernel-trace
import torch
x = torch.randn(4096, 4096, device="cuda")
y = x @ x
torch.cuda.synchronize()
```

Options: `--preset {runtime,kernel,sys,hip}` (or the `--kernel-trace` /
`--hip-trace` / `--sys-trace` / `--runtime-trace` shortcuts), `--label`,
`--shapes` / `--memory` / `--stack` (extra `torch.profiler` detail), and
`--trace` (keep the chrome trace for download).

You can also click **Cell Profile** in the notebook toolbar to profile the
active PyTorch GPU cell without typing the magic; results appear under the cell
and in the sidebar. To profile a long-running cell without re-running it, use
the **Live capture** mode in the sidebar instead.

## Notes on unsupported metrics

`amdsmi` raises errors or returns `"N/A"` for metrics a given ASIC does not
expose (this is common on integrated/APU parts). The backend guards every
field individually and reports missing values as `null`, shown as `N/A` in the
UI, instead of failing the whole sample.

## API endpoints

All endpoints are namespaced under `/jupyterlab-rocm` and require Jupyter
authentication.

| Method | Path | Description |
| --- | --- | --- |
| GET | `/gpus` | Static device info + amdsmi/rocprof availability |
| GET | `/metrics` | One-shot metrics sample (polling fallback) |
| WS | `/stream?interval=<ms>` | Live metrics stream |
| GET | `/profile/cell` | List Cell Profile jobs |

## License

BSD-3-Clause.
