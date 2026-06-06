# jupyterlab-rocm

A JupyterLab 4 extension for monitoring AMD ROCm GPU usage and running
[`rocprofv3`](https://rocm.docs.amd.com/projects/rocprofiler-sdk/en/latest/how-to/using-rocprofv3.html)
profiling, without leaving JupyterLab.

It has two parts:

- A **GPU Monitor** that streams live metrics (GFX utilization, VRAM, power,
  temperature, clocks, processes) over a WebSocket, collected through the
  [`amdsmi`](https://rocm.docs.amd.com/projects/amdsmi/en/latest/) Python
  library.
- A **Profiler** that runs `rocprofv3` against the current notebook, a Python
  script, or a custom command, then parses the kernel trace and shows a sorted
  table and a bar chart of the hottest kernels.
- A **`%%rocprofv3` cell magic** that profiles a single notebook cell by
  attaching `rocprofv3` to the *live* kernel (so variables from earlier cells
  are preserved), rendering the hottest kernels inline and in the sidebar.

## Architecture

```
JupyterLab frontend (TypeScript + React)
  ├── GPU Monitor  ──WebSocket──►  /jupyterlab-rocm/stream
  ├── Profiler     ──REST───────►  /jupyterlab-rocm/profile
  └── Profile cell ──kernel exec─►  %%rocprofv3 (in the IPython kernel)
                                        │
jupyter_server extension (Tornado)      │   ┌─ cell job JSON files ─┐
  ├── metrics.py   ── amdsmi ──────────► AMD GPU                    │
  ├── profiler.py  ── rocprofv3 ───────► AMD GPU                    │
  └── /profile/cell  reads ◄────────────────────────────────────────┘
                                        │
IPython kernel
  └── magics.py    ── rocprofv3 --attach <kernel pid> ──► AMD GPU
```

## Requirements

- Linux with the `amdgpu` kernel driver loaded, ROCm installed.
- Python >= 3.9, JupyterLab >= 4.
- `amdsmi` Python package (ships with ROCm). It is **not** installed as a hard
  dependency because it is normally provided by the system ROCm tree.
- `rocprofv3` on `PATH` or in `/opt/rocm/bin` (only needed for the profiler).
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
3. The **Profiler** tab lets you pick a target (use *Use current notebook* to
   profile the active notebook), choose a trace preset (`runtime`, `kernel`,
   `sys`, `hip`), optionally filter kernels by regex, and run `rocprofv3`. When
   it finishes, the hottest kernels are shown as a table and bar chart.

## Cell-level profiling (`%%rocprofv3`)

Profile a single cell while keeping the variables defined in earlier cells.
`rocprofv3` attaches to the running kernel with `--attach <pid>`, the cell runs
in the live kernel, then the profiler detaches and shows the results inline and
in the **Profiler** tab's *Cell profiling* section.

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
`--hip-trace` / `--sys-trace` / `--runtime-trace` shortcuts), `--include` /
`--exclude` kernel regexes, `--label`, and `--ready-timeout`.

You can also click **Profile cell** in the notebook toolbar to profile the
active cell without typing the magic; results appear in the sidebar.

### Live-attach environment requirements

`--attach` uses `ptrace`, so the environment must allow it **and** the kernel
must be started with `ROCP_TOOL_ATTACH=1`:

- **`ROCP_TOOL_ATTACH=1`** must be set *before the kernel starts* (it is read
  during ROCm runtime initialization). Set it in your shell before launching
  JupyterLab, or via a dedicated kernelspec so it is scoped to GPU profiling:

  ```json
  // ~/.local/share/jupyter/kernels/python3-rocmattach/kernel.json
  {
    "argv": ["python", "-m", "ipykernel_launcher", "-f", "{connection_file}"],
    "display_name": "Python 3 (ROCm attach)",
    "language": "python",
    "env": { "ROCP_TOOL_ATTACH": "1" }
  }
  ```

- **Yama `ptrace_scope`**: with the default `1`, the extension calls
  `prctl(PR_SET_PTRACER, PR_SET_PTRACER_ANY)` from the kernel so the `rocprofv3`
  child can attach. `ptrace_scope=2` additionally needs `CAP_SYS_PTRACE`;
  `ptrace_scope=3` disables attach entirely.

- **Containers**: add the ptrace capability, e.g. `docker run --cap-add=SYS_PTRACE ...`.

The *Cell profiling* section shows a hint whenever any of these prerequisites
is missing (reported by `GET /profile/cell`).

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
| GET | `/profile` | List profiling jobs + rocprof status |
| POST | `/profile` | Start a profiling job |
| GET | `/profile/cell` | List `%%rocprofv3` cell jobs + attach status |
| GET | `/profile/{id}` | Job status and parsed results |

## License

BSD-3-Clause.
