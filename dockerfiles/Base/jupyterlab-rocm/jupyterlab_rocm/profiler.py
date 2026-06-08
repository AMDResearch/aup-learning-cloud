"""Profiling integration for Cell Profile and optional rocprofv3 tooling.

Cell Profile uses ``torch.profiler`` in the live kernel. Helper routines for
``rocprofv3`` CSV parsing remain for deferred subprocess/attach paths.
"""

from __future__ import annotations

import contextlib
import csv
import ctypes
import glob
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

# Trace presets exposed to the frontend. Each maps to a rocprofv3 flag.
TRACE_PRESETS = {
    "runtime": "--runtime-trace",
    "kernel": "--kernel-trace",
    "sys": "--sys-trace",
    "hip": "--hip-trace",
}


class ProfilerBusyError(RuntimeError):
    """Raised when a torch.profiler run is requested while one is already active.

    Only one ``torch.profiler`` can be active per process, so the cell-magic
    path and the live-watcher path share this lock to avoid colliding.
    """


_PROFILER_LOCK = threading.Lock()


@contextlib.contextmanager
def profiler_slot():
    """Acquire the single per-process profiler slot or raise ``ProfilerBusyError``."""
    if not _PROFILER_LOCK.acquire(blocking=False):
        raise ProfilerBusyError(
            "Another profiling run is already active in this kernel. "
            "Wait for it to finish, then try again."
        )
    try:
        yield
    finally:
        _PROFILER_LOCK.release()

def rocprof_executable() -> Optional[str]:
    """Locate the rocprofv3 binary."""
    for candidate in ("rocprofv3", "rocprof"):
        found = shutil.which(candidate)
        if found:
            return found
    for candidate in ("/opt/rocm/bin/rocprofv3", "/usr/bin/rocprofv3"):
        if os.path.exists(candidate):
            return candidate
    return None


def _read_ptrace_scope() -> Optional[int]:
    """Read the Yama ptrace_scope sysctl (None if unavailable)."""
    try:
        with open("/proc/sys/kernel/yama/ptrace_scope") as handle:
            return int(handle.read().strip())
    except (OSError, ValueError):
        return None


def attach_blockers() -> Optional[str]:
    """Return a user-facing reason to skip live attach, or ``None`` if safe to try.

    ``rocprofv3 --attach`` must run before PyTorch initialises the ROCprofiler
    SDK in the kernel. If ``torch`` is already imported, attaching aborts the
    ipykernel process (ROCPROFILER_REGISTER_LIBRARY conflict).
    """
    if "torch" in sys.modules:
        return (
            "PyTorch is already loaded in this kernel. rocprofv3 --attach "
            "conflicts with PyTorch's ROCprofiler library and will crash the "
            "kernel. Restart the kernel, then use Cell Profile without running "
            "any prior import torch cells."
        )
    return None


def attach_status(exe: Optional[str]) -> Dict[str, Any]:
    """Report whether live ``--attach`` profiling is usable in this process.

    ``supported`` means an attach can be *attempted*; the ``hint`` field
    surfaces any remaining configuration steps (e.g. ``ROCP_TOOL_ATTACH``).
    """
    scope = _read_ptrace_scope()
    tool_env = os.environ.get("ROCP_TOOL_ATTACH") == "1"
    supported = exe is not None and scope != 3
    hints: List[str] = []
    if exe is None:
        hints.append("rocprofv3 was not found.")
    if not tool_env:
        hints.append(
            "Set ROCP_TOOL_ATTACH=1 in the kernel environment before starting "
            "the kernel (e.g. via a custom kernelspec)."
        )
    if scope == 2:
        hints.append(
            "yama ptrace_scope=2 requires CAP_SYS_PTRACE "
            "(run the container with --cap-add=SYS_PTRACE)."
        )
    if scope == 3:
        hints.append("yama ptrace_scope=3 disables ptrace; attach is unavailable.")
    return {
        "supported": supported,
        "ptrace_scope": scope,
        "tool_attach_env": tool_env,
        "hint": " ".join(hints) or None,
    }


def get_status() -> Dict[str, Any]:
    exe = rocprof_executable()
    if exe is None:
        return {
            "available": False,
            "error": "rocprofv3 was not found on PATH or in /opt/rocm/bin.",
            "attach": attach_status(exe),
        }
    return {
        "available": True,
        "error": None,
        "executable": exe,
        "presets": list(TRACE_PRESETS),
        "attach": attach_status(exe),
    }


class ProfileJob:
    """State container for a single profiling run."""

    def __init__(self, target_type: str, target: str, preset: str, extra: Dict[str, Any]):
        self.id = uuid.uuid4().hex
        self.target_type = target_type
        self.target = target
        self.preset = preset
        self.extra = extra
        self.status = "queued"  # queued | running | done | error
        self.error: Optional[str] = None
        self.returncode: Optional[int] = None
        self.stdout: str = ""
        self.stderr: str = ""
        self.command: List[str] = []
        self.created = time.time()
        self.finished: Optional[float] = None
        self.kernels: List[Dict[str, Any]] = []
        self.operators: List[Dict[str, Any]] = []
        self.memory_copies: List[Dict[str, Any]] = []
        self.summary: Dict[str, Any] = {}

    def to_dict(self, include_results: bool = True) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "id": self.id,
            "target_type": self.target_type,
            "target": self.target,
            "preset": self.preset,
            "extra": dict(self.extra),
            "status": self.status,
            "error": self.error,
            "returncode": self.returncode,
            "command": " ".join(shlex.quote(c) for c in self.command),
            "created": self.created,
            "finished": self.finished,
        }
        if include_results:
            data.update(
                {
                    "stdout": self.stdout[-8000:],
                    "stderr": self.stderr[-8000:],
                    "kernels": self.kernels,
                    "operators": self.operators,
                    "memory_copies": self.memory_copies,
                    "summary": self.summary,
                }
            )
        return data


def _parse_kernel_trace(path: str) -> List[Dict[str, Any]]:
    """Aggregate kernel dispatch rows by kernel name."""
    agg: Dict[str, Dict[str, float]] = {}
    with open(path, newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            name = row.get("Kernel_Name") or row.get("Name") or "<unknown>"
            try:
                start = float(row.get("Start_Timestamp", "") or 0)
                end = float(row.get("End_Timestamp", "") or 0)
            except ValueError:
                continue
            duration = max(end - start, 0.0)
            entry = agg.setdefault(
                name,
                {"calls": 0, "total_ns": 0.0, "min_ns": duration, "max_ns": duration},
            )
            entry["calls"] += 1
            entry["total_ns"] += duration
            entry["min_ns"] = min(entry["min_ns"], duration)
            entry["max_ns"] = max(entry["max_ns"], duration)

    return _summarize_kernels(agg)


def _summarize_kernels(agg: Dict[str, Dict[str, float]]) -> List[Dict[str, Any]]:
    """Turn per-kernel aggregates into sorted result rows with percentages."""
    grand_total = sum(e["total_ns"] for e in agg.values()) or 1.0
    kernels: List[Dict[str, Any]] = []
    for name, entry in agg.items():
        calls = int(entry["calls"])
        total = entry["total_ns"]
        kernels.append(
            {
                "name": name,
                "calls": calls,
                "total_ns": total,
                "avg_ns": total / calls if calls else 0.0,
                "min_ns": entry["min_ns"],
                "max_ns": entry["max_ns"],
                "percent": round(total / grand_total * 100.0, 2),
            }
        )
    kernels.sort(key=lambda k: k["total_ns"], reverse=True)
    return kernels


def _apply_kernel_summary(job: ProfileJob) -> None:
    total_ns = sum(k["total_ns"] for k in job.kernels)
    job.summary = {
        "kernel_count": len(job.kernels),
        "total_kernel_ns": total_ns,
        "total_dispatches": sum(k["calls"] for k in job.kernels),
    }


def _apply_operator_summary(job: ProfileJob) -> None:
    """Augment ``job.summary`` with operator-level (key_averages) totals."""
    ops = job.operators
    job.summary.update(
        {
            "operator_count": len(ops),
            "self_cpu_total_ns": sum(o.get("self_cpu_ns", 0.0) for o in ops),
            "self_gpu_total_ns": sum(o.get("self_gpu_ns", 0.0) for o in ops),
        }
    )


def _parse_memory_copy_trace(path: str) -> List[Dict[str, Any]]:
    agg: Dict[str, Dict[str, float]] = {}
    with open(path, newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            direction = row.get("Direction") or row.get("Operation") or "<copy>"
            try:
                start = float(row.get("Start_Timestamp", "") or 0)
                end = float(row.get("End_Timestamp", "") or 0)
            except ValueError:
                continue
            duration = max(end - start, 0.0)
            entry = agg.setdefault(direction, {"calls": 0, "total_ns": 0.0})
            entry["calls"] += 1
            entry["total_ns"] += duration
    return [
        {
            "direction": direction,
            "calls": int(entry["calls"]),
            "total_ns": entry["total_ns"],
        }
        for direction, entry in agg.items()
    ]


def _collect_outputs(job: ProfileJob, outdir: str) -> None:
    """Find rocprofv3 CSV outputs (recursively) and parse them."""
    kernel_files = glob.glob(os.path.join(outdir, "**", "*kernel_trace.csv"), recursive=True)
    if kernel_files:
        job.kernels = _parse_kernel_trace(kernel_files[0])
    copy_files = glob.glob(os.path.join(outdir, "**", "*memory_copy_trace.csv"), recursive=True)
    if copy_files:
        job.memory_copies = _parse_memory_copy_trace(copy_files[0])

    _apply_kernel_summary(job)


# ---------------------------------------------------------------------------
# Cell Profile (torch.profiler in the live kernel)
# ---------------------------------------------------------------------------

_TORCH_GPU_CELL_RE = re.compile(
    r"""
    (?:^|\n)\s*(?:import\s+torch|from\s+torch\b)
    |torch\.cuda\b
    |device\s*=\s*['\"]cuda['\"]
    |\.cuda\s*\(
    |\.to\s*\(\s*['\"]cuda['\"]
    """,
    re.IGNORECASE | re.VERBOSE,
)


def cell_looks_like_torch_gpu(cell_source: str) -> bool:
    """Heuristic: does the cell source use PyTorch on a CUDA/ROCm device?"""
    return bool(_TORCH_GPU_CELL_RE.search(cell_source))


def torch_cuda_available() -> bool:
    try:
        import torch  # type: ignore

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def cell_profile_unavailable_reason(cell_source: str) -> Optional[str]:
    """Return a user-facing reason Cell Profile cannot run, or ``None`` if supported."""
    if not cell_looks_like_torch_gpu(cell_source):
        return (
            "Cell Profile supports PyTorch GPU cells only "
            '(import torch and use device="cuda" or .cuda()).'
        )
    if not torch_cuda_available():
        return (
            "PyTorch does not see a ROCm/CUDA device in this kernel. "
            "Run a GPU check cell first."
        )
    return None


def detect_cell_backend(cell_source: str) -> str:
    """Pick the profiling backend for a notebook cell.

    Cell Profile uses ``"torch"`` when the cell looks like PyTorch GPU code and
    a ROCm/CUDA device is available. The ``"rocprofv3"`` subprocess path is
    reserved for a future release and is not invoked by the UI today.
    """
    if cell_profile_unavailable_reason(cell_source) is None:
        return "torch"
    return "rocprofv3"


def _parse_torch_kernel_events(trace_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Aggregate Chrome trace kernel events (``cat == "kernel"``) by name."""
    agg: Dict[str, Dict[str, float]] = {}
    for event in trace_data.get("traceEvents", []):
        if event.get("cat") != "kernel" or event.get("ph") != "X":
            continue
        name = str(event.get("name") or "<unknown>")
        # Chrome trace ``dur`` is in microseconds.
        duration_ns = float(event.get("dur", 0) or 0) * 1000.0
        if duration_ns <= 0:
            continue
        entry = agg.setdefault(
            name,
            {"calls": 0, "total_ns": 0.0, "min_ns": duration_ns, "max_ns": duration_ns},
        )
        entry["calls"] += 1
        entry["total_ns"] += duration_ns
        entry["min_ns"] = min(entry["min_ns"], duration_ns)
        entry["max_ns"] = max(entry["max_ns"], duration_ns)
    return _summarize_kernels(agg)


def _evt_attr(evt: Any, *names: str, default: Any = 0) -> Any:
    """Return the first present, non-None attribute from ``names``.

    ``key_averages`` event objects renamed several CUDA fields to ``device``
    across torch versions (e.g. ``cuda_time_total`` -> ``device_time_total``),
    so we probe both spellings.
    """
    for name in names:
        if hasattr(evt, name):
            try:
                value = getattr(evt, name)
            except Exception:
                continue
            if value is not None:
                return value
    return default


def _summarize_key_averages(prof: Any, row_limit: int = 100) -> List[Dict[str, Any]]:
    """Aggregate ``prof.key_averages()`` into operator-level result rows.

    Times are converted from microseconds (torch's unit) to nanoseconds so the
    frontend can reuse its existing ``*_ns`` formatting. Memory is in bytes.
    """
    try:
        events = prof.key_averages()
    except Exception:
        return []

    operators: List[Dict[str, Any]] = []
    for evt in events:
        shapes = getattr(evt, "input_shapes", None)
        stack = getattr(evt, "stack", None)
        operators.append(
            {
                "name": str(_evt_attr(evt, "key", default="") or "<unknown>"),
                "calls": int(_evt_attr(evt, "count", default=0) or 0),
                "cpu_total_ns": float(_evt_attr(evt, "cpu_time_total")) * 1000.0,
                "self_cpu_ns": float(_evt_attr(evt, "self_cpu_time_total")) * 1000.0,
                "gpu_total_ns": float(
                    _evt_attr(evt, "device_time_total", "cuda_time_total")
                )
                * 1000.0,
                "self_gpu_ns": float(
                    _evt_attr(evt, "self_device_time_total", "self_cuda_time_total")
                )
                * 1000.0,
                "cpu_mem": int(_evt_attr(evt, "cpu_memory_usage")),
                "self_cpu_mem": int(_evt_attr(evt, "self_cpu_memory_usage")),
                "gpu_mem": int(
                    _evt_attr(evt, "device_memory_usage", "cuda_memory_usage")
                ),
                "self_gpu_mem": int(
                    _evt_attr(evt, "self_device_memory_usage", "self_cuda_memory_usage")
                ),
                "input_shapes": str(shapes) if shapes else None,
                "stack": [str(s) for s in stack] if stack else None,
            }
        )

    has_gpu = any(o["self_gpu_ns"] > 0 for o in operators)
    metric = "self_gpu_ns" if has_gpu else "self_cpu_ns"
    grand_total = sum(o[metric] for o in operators) or 1.0
    for o in operators:
        o["percent"] = round(o[metric] / grand_total * 100.0, 2)
    operators.sort(key=lambda o: o[metric], reverse=True)
    return operators[:row_limit]


def _kernels_from_prof(prof: Any) -> tuple:
    """Export a chrome trace from ``prof`` and parse GPU kernel events.

    Returns ``(kernels, trace_path)``. ``trace_path`` is left on disk so the
    caller can either keep it (for download) or delete it.
    """
    trace_path: Optional[str] = None
    kernels: List[Dict[str, Any]] = []
    try:
        fd, trace_path = tempfile.mkstemp(suffix=".json", prefix="rocm_torch_trace_")
        os.close(fd)
        prof.export_chrome_trace(trace_path)
        with open(trace_path) as handle:
            kernels = _parse_torch_kernel_events(json.load(handle))
    except Exception:
        if trace_path:
            try:
                os.remove(trace_path)
            except OSError:
                pass
            trace_path = None
    return kernels, trace_path


def trace_path_for(job_id: str) -> str:
    """Filesystem path of the persisted chrome trace for a cell job."""
    return os.path.join(cell_jobs_dir(), f"{job_id}.trace.json")


def _store_trace(job: ProfileJob, src: Optional[str]) -> None:
    """Persist the chrome trace next to the job JSON for later download."""
    if not src:
        return
    dst = trace_path_for(job.id)
    try:
        shutil.move(src, dst)
        job.extra["trace_available"] = True
    except OSError:
        try:
            os.remove(src)
        except OSError:
            pass


def _discard_trace(src: Optional[str]) -> None:
    if not src:
        return
    try:
        os.remove(src)
    except OSError:
        pass


def _torch_activities() -> List[Any]:
    import torch  # type: ignore
    from torch.profiler import ProfilerActivity  # type: ignore

    activities = [ProfilerActivity.CPU]
    if torch.cuda.is_available():
        activities.append(ProfilerActivity.CUDA)
    return activities


def _finalize_torch_job(
    job: ProfileJob,
    prof: Any,
    *,
    keep_trace: bool,
    kernels: Optional[List[Dict[str, Any]]] = None,
    trace_path: Optional[str] = None,
    operators: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Compute operators/kernels/summary for a finished torch profile."""
    job.operators = operators if operators is not None else _summarize_key_averages(prof)
    if kernels is None:
        kernels, trace_path = _kernels_from_prof(prof)
    job.kernels = kernels
    if keep_trace:
        _store_trace(job, trace_path)
    else:
        _discard_trace(trace_path)
    _apply_kernel_summary(job)
    _apply_operator_summary(job)


def _run_cell_quietly(shell: Any, cell: str) -> None:
    import io

    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
        io.StringIO()
    ):
        shell.run_cell(cell, store_history=False)


def profile_cell_torch(
    shell: Any,
    cell: str,
    label: str,
    preset: str = "kernel",
    *,
    record_shapes: bool = False,
    profile_memory: bool = False,
    with_stack: bool = False,
    keep_trace: bool = False,
) -> ProfileJob:
    """Profile an entire cell in the live kernel using ``torch.profiler``."""
    import torch  # type: ignore
    from torch.profiler import profile  # type: ignore

    job = ProfileJob("cell", label, preset, {"backend": "torch", "mode": "full"})
    job.status = "running"
    try:
        with profile(
            activities=_torch_activities(),
            record_shapes=record_shapes,
            profile_memory=profile_memory,
            with_stack=with_stack,
        ) as prof:
            _run_cell_quietly(shell, cell)
            if torch.cuda.is_available():
                torch.cuda.synchronize()
        _finalize_torch_job(job, prof, keep_trace=keep_trace)
        job.status = "done"
    except Exception as exc:
        job.status = "error"
        job.error = f"{type(exc).__name__}: {exc}"
    finally:
        job.finished = time.time()
    return job


def run_cell_profile(
    shell: Any,
    cell: str,
    *,
    label: str = "notebook cell",
    preset: str = "kernel",
    options: Optional[Dict[str, Any]] = None,
) -> ProfileJob:
    """Profile a whole notebook cell with ``torch.profiler`` in the live kernel.

    Held under :func:`profiler_slot` so it cannot run concurrently with a live
    capture (only one ``torch.profiler`` per process).
    """
    options = options or {}
    try:
        with profiler_slot():
            return profile_cell_torch(
                shell,
                cell,
                label,
                preset,
                record_shapes=bool(options.get("record_shapes", False)),
                profile_memory=bool(options.get("profile_memory", False)),
                with_stack=bool(options.get("with_stack", False)),
                keep_trace=bool(options.get("keep_trace", False)),
            )
    except ProfilerBusyError as exc:
        job = ProfileJob("cell", label, preset, {"backend": "torch", "mode": "full"})
        job.status = "error"
        job.error = str(exc)
        job.finished = time.time()
        return job


def _build_rocprof_command(
    exe: str,
    preset: str,
    outdir: str,
    target_cmd: List[str],
    extra: Dict[str, Any],
) -> List[str]:
    flag = TRACE_PRESETS.get(preset, TRACE_PRESETS["kernel"])
    command = [exe, flag, "--output-format", "csv", "-d", outdir]
    include = extra.get("kernel_include_regex")
    exclude = extra.get("kernel_exclude_regex")
    if include:
        command += ["--kernel-include-regex", str(include)]
    if exclude:
        command += ["--kernel-exclude-regex", str(exclude)]
    command += ["--", *target_cmd]
    return command


def profile_cell_subprocess(
    cell: str,
    preset: str = "kernel",
    extra: Optional[Dict[str, Any]] = None,
    label: str = "notebook cell",
) -> ProfileJob:
    """Profile a cell in a fresh Python subprocess under ``rocprofv3``.

    Deferred: Cell Profile does not call this path yet. Kept for tests and a
    future non-PyTorch backend.
    """
    merged_extra = dict(extra or {})
    merged_extra["backend"] = "rocprofv3-subprocess"
    job = ProfileJob("cell", label, preset, merged_extra)
    job.status = "running"
    workdir = tempfile.mkdtemp(prefix="rocm_cell_")
    outdir = os.path.join(workdir, "out")
    os.makedirs(outdir, exist_ok=True)
    script_path = os.path.join(workdir, "profiled_cell.py")
    try:
        exe = rocprof_executable()
        if exe is None:
            raise RuntimeError("rocprofv3 executable not found.")

        with open(script_path, "w") as handle:
            handle.write(cell)
            if not cell.endswith("\n"):
                handle.write("\n")

        command = _build_rocprof_command(
            exe, preset, outdir, [sys.executable, script_path], merged_extra
        )
        job.command = command
        timeout = float(merged_extra.get("timeout", 120))
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            cwd=workdir,
            timeout=timeout,
        )
        job.returncode = proc.returncode
        job.stdout = proc.stdout
        job.stderr = proc.stderr
        _collect_outputs(job, outdir)

        if proc.returncode != 0 and not job.kernels:
            job.status = "error"
            job.error = f"rocprofv3 exited with code {proc.returncode}."
        else:
            job.status = "done"
    except subprocess.TimeoutExpired:
        job.status = "error"
        job.error = "Profiling timed out."
    except Exception as exc:
        job.status = "error"
        job.error = f"{type(exc).__name__}: {exc}"
    finally:
        job.finished = time.time()
        shutil.rmtree(workdir, ignore_errors=True)
    return job


# ---------------------------------------------------------------------------
# Live-attach (cell-level) profiling
# ---------------------------------------------------------------------------

# prctl(2) options. PR_SET_PTRACER lets us declare which process may ptrace us;
# PR_SET_PTRACER_ANY ((unsigned long) -1) permits any same-user process, which
# is required so the rocprofv3 child can attach to its parent kernel under
# Yama ptrace_scope=1.
_PR_SET_PTRACER = 0x59616D61


def _allow_ptrace_any() -> None:
    """Permit any same-user process to ptrace this process (best effort)."""
    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.prctl.argtypes = [
            ctypes.c_int,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_ulong,
        ]
        libc.prctl.restype = ctypes.c_int
        # PR_SET_PTRACER_ANY is (unsigned long) -1.
        libc.prctl(_PR_SET_PTRACER, ctypes.c_ulong(-1).value, 0, 0, 0)
    except Exception:
        # Non-Linux, missing libc, or insufficient privileges; attach may still
        # work if ptrace_scope is 0 or the tracer is already permitted.
        pass


_READY_RE = re.compile(r"attach|instrument|ready|profil", re.IGNORECASE)


class AttachSession:
    """Drives a ``rocprofv3 --attach <pid>`` run around a single cell.

    Usage::

        session = AttachSession(os.getpid(), preset="kernel")
        session.start()
        # ... run the cell in the live kernel ...
        job = session.stop()
    """

    def __init__(
        self,
        pid: int,
        preset: str = "kernel",
        extra: Optional[Dict[str, Any]] = None,
        label: str = "notebook cell",
    ):
        self.pid = pid
        self.preset = preset if preset in TRACE_PRESETS else "kernel"
        self.extra = extra or {}
        self.label = label
        self.workdir: Optional[str] = None
        self.outdir: Optional[str] = None
        self.proc: Optional[subprocess.Popen] = None
        self._stdout_lines: List[str] = []
        self._stderr_lines: List[str] = []
        self._readers: List[threading.Thread] = []
        self.job = ProfileJob("cell", label, self.preset, self.extra)

    def _drain(self, stream, sink: List[str]) -> None:
        try:
            for line in stream:
                sink.append(line)
        except Exception:
            pass

    def start(self, ready_timeout: float = 10.0) -> None:
        exe = rocprof_executable()
        if exe is None:
            raise RuntimeError("rocprofv3 executable not found.")

        _allow_ptrace_any()
        self.workdir = tempfile.mkdtemp(prefix="rocm_cell_")
        self.outdir = os.path.join(self.workdir, "out")
        os.makedirs(self.outdir, exist_ok=True)

        flag = TRACE_PRESETS.get(self.preset, TRACE_PRESETS["kernel"])
        command = [
            exe,
            "--attach",
            str(self.pid),
            flag,
            "--output-format",
            "csv",
            "-d",
            self.outdir,
        ]
        include = self.extra.get("kernel_include_regex")
        exclude = self.extra.get("kernel_exclude_regex")
        if include:
            command += ["--kernel-include-regex", str(include)]
        if exclude:
            command += ["--kernel-exclude-regex", str(exclude)]
        self.job.command = command

        self.proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=self.workdir,
        )
        self.job.status = "running"

        for stream, sink in (
            (self.proc.stdout, self._stdout_lines),
            (self.proc.stderr, self._stderr_lines),
        ):
            thread = threading.Thread(
                target=self._drain, args=(stream, sink), daemon=True
            )
            thread.start()
            self._readers.append(thread)

        self._wait_ready(ready_timeout)

    def _wait_ready(self, timeout: float) -> None:
        """Block until rocprofv3 looks attached, it exits, or we time out."""
        deadline = time.time() + max(timeout, 0.0)
        while time.time() < deadline:
            if self.proc is not None and self.proc.poll() is not None:
                return  # exited prematurely; stop() will report it
            if any(_READY_RE.search(line) for line in self._stderr_lines):
                time.sleep(0.2)  # brief settle once instrumentation is armed
                return
            time.sleep(0.1)

    def stop(self, settle: float = 0.3) -> ProfileJob:
        if self.proc is None:
            self.job.status = "error"
            self.job.error = "rocprofv3 attach was never started."
            return self.job

        time.sleep(max(settle, 0.0))
        # Detach: rocprofv3 detaches on newline (Enter) and flushes its output.
        try:
            if self.proc.stdin:
                self.proc.stdin.write("\n")
                self.proc.stdin.flush()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                self.proc.send_signal(signal.SIGINT)
                self.proc.wait(timeout=10)
            except (subprocess.TimeoutExpired, Exception):
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.proc.kill()

        for thread in self._readers:
            thread.join(timeout=2)

        self.job.returncode = self.proc.returncode
        self.job.stdout = "".join(self._stdout_lines)
        self.job.stderr = "".join(self._stderr_lines)
        if self.outdir:
            _collect_outputs(self.job, self.outdir)
        self.job.finished = time.time()

        if self.job.kernels:
            self.job.status = "done"
        elif self.job.returncode in (0, None, -signal.SIGINT):
            self.job.status = "done"
        else:
            self.job.status = "error"
            if not self.job.error:
                self.job.error = (
                    f"rocprofv3 attach exited with code {self.job.returncode}."
                )

        if self.workdir:
            shutil.rmtree(self.workdir, ignore_errors=True)
        return self.job


# ---------------------------------------------------------------------------
# Cross-process cell-job store (kernel writes, server reads)
# ---------------------------------------------------------------------------
#
# The cell magic runs inside the IPython *kernel* process while the sidebar
# talks to the *server* extension process. They share the filesystem but not
# memory, so completed cell jobs are persisted as JSON files in a shared dir.


def cell_jobs_dir() -> str:
    base = os.environ.get("JUPYTER_RUNTIME_DIR") or tempfile.gettempdir()
    path = os.path.join(base, "jupyterlab_rocm_cell_jobs")
    os.makedirs(path, exist_ok=True)
    return path


def _is_job_file(name: str) -> bool:
    """True for ``{id}.json`` job files, excluding ``{id}.trace.json`` traces."""
    return name.endswith(".json") and not name.endswith(".trace.json")


def _prune_cell_jobs(directory: str, max_keep: int) -> None:
    try:
        files = [
            os.path.join(directory, name)
            for name in os.listdir(directory)
            if _is_job_file(name)
        ]
    except OSError:
        return
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    for stale in files[max_keep:]:
        try:
            os.remove(stale)
        except OSError:
            pass
        # Remove the companion trace, if any.
        job_id = os.path.basename(stale)[: -len(".json")]
        try:
            os.remove(trace_path_for(job_id))
        except OSError:
            pass


def register_cell_job(job: ProfileJob, max_keep: int = 30) -> None:
    """Persist a finished cell job so the server extension can serve it."""
    directory = cell_jobs_dir()
    path = os.path.join(directory, f"{job.id}.json")
    try:
        with open(path, "w") as handle:
            json.dump(job.to_dict(include_results=True), handle)
    except OSError:
        return
    _prune_cell_jobs(directory, max_keep)


def list_cell_jobs(limit: int = 20) -> List[Dict[str, Any]]:
    directory = cell_jobs_dir()
    jobs: List[Dict[str, Any]] = []
    try:
        names = [name for name in os.listdir(directory) if _is_job_file(name)]
    except OSError:
        names = []
    for name in names:
        try:
            with open(os.path.join(directory, name)) as handle:
                jobs.append(json.load(handle))
        except (OSError, ValueError):
            continue
    jobs.sort(key=lambda j: j.get("created", 0), reverse=True)
    return jobs[:limit]


# ---------------------------------------------------------------------------
# Live capture (profile a cell that is already running)
# ---------------------------------------------------------------------------
#
# The kernel is single-threaded for cell execution, so a busy training cell
# cannot accept a new ``%%rocprofv3``. Instead a background watcher thread
# (armed when the extension loads) polls a trigger file written by the server
# extension and runs ``torch.profiler`` for a short window. Because kineto is
# process-wide, it captures the work the main thread is doing.


def current_kernel_id() -> Optional[str]:
    """Best-effort current ipykernel id, parsed from the connection file."""
    try:
        from ipykernel.connect import get_connection_file  # type: ignore

        path = get_connection_file()
    except Exception:
        return None
    match = re.match(r"kernel-(.+)\.json$", os.path.basename(path or ""))
    return match.group(1) if match else None


def live_dir() -> str:
    path = os.path.join(cell_jobs_dir(), "live")
    os.makedirs(path, exist_ok=True)
    return path


def _trigger_name(kernel_id: Optional[str]) -> str:
    return f"trigger-{kernel_id or 'any'}.json"


def write_live_trigger(kernel_id: Optional[str], payload: Dict[str, Any]) -> str:
    """Atomically publish a live-capture request for ``kernel_id`` (or any)."""
    directory = live_dir()
    path = os.path.join(directory, _trigger_name(kernel_id))
    tmp = f"{path}.{uuid.uuid4().hex}.tmp"
    with open(tmp, "w") as handle:
        json.dump(payload, handle)
    os.replace(tmp, path)
    return path


def claim_live_trigger(kernel_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """Atomically claim a pending trigger for this kernel; return its payload.

    Tries the kernel-specific trigger first, then the ``any`` trigger. The
    ``os.rename`` makes the claim atomic so concurrent watchers never run the
    same request twice.
    """
    directory = live_dir()
    names = [_trigger_name(kernel_id)] if kernel_id else []
    names.append(_trigger_name(None))
    for name in names:
        src = os.path.join(directory, name)
        dst = os.path.join(directory, f"claim-{uuid.uuid4().hex}.json")
        try:
            os.rename(src, dst)
        except OSError:
            continue
        payload: Optional[Dict[str, Any]] = None
        try:
            with open(dst) as handle:
                payload = json.load(handle)
        except (OSError, ValueError):
            payload = None
        finally:
            try:
                os.remove(dst)
            except OSError:
                pass
        return payload
    return None


def live_heartbeat(kernel_id: Optional[str]) -> None:
    """Mark this kernel's watcher as alive (also under the shared ``any`` key)."""
    directory = live_dir()
    keys = {"any"}
    if kernel_id:
        keys.add(kernel_id)
    stamp = str(time.time())
    for key in keys:
        try:
            with open(os.path.join(directory, f"heartbeat-{key}"), "w") as handle:
                handle.write(stamp)
        except OSError:
            pass


def live_armed(kernel_id: Optional[str], max_age: float = 6.0) -> bool:
    """True if a watcher heartbeat for ``kernel_id`` (or any) is recent."""
    directory = live_dir()
    names = [f"heartbeat-{kernel_id}"] if kernel_id else []
    names.append("heartbeat-any")
    now = time.time()
    for name in names:
        try:
            if now - os.path.getmtime(os.path.join(directory, name)) <= max_age:
                return True
        except OSError:
            continue
    return False


def set_live_busy(kernel_id: Optional[str], expiry: float) -> None:
    """Mark a live capture as in-progress until ``expiry`` (epoch seconds)."""
    directory = live_dir()
    keys = {"any"}
    if kernel_id:
        keys.add(kernel_id)
    for key in keys:
        try:
            with open(os.path.join(directory, f"busy-{key}"), "w") as handle:
                handle.write(str(expiry))
        except OSError:
            pass


def clear_live_busy(kernel_id: Optional[str]) -> None:
    directory = live_dir()
    keys = {"any"}
    if kernel_id:
        keys.add(kernel_id)
    for key in keys:
        try:
            os.remove(os.path.join(directory, f"busy-{key}"))
        except OSError:
            pass


def live_busy(kernel_id: Optional[str]) -> bool:
    """True if a live capture is currently running for this kernel.

    Uses a stored expiry so a crashed capture cannot wedge the UI forever.
    """
    directory = live_dir()
    name = f"busy-{kernel_id}" if kernel_id else "busy-any"
    try:
        with open(os.path.join(directory, name)) as handle:
            expiry = float(handle.read().strip() or 0)
    except (OSError, ValueError):
        return False
    return time.time() < expiry


def profile_live_window(
    *,
    window_s: float = 2.0,
    warmup_s: float = 0.0,
    preset: str = "kernel",
    options: Optional[Dict[str, Any]] = None,
    label: str = "live capture",
) -> ProfileJob:
    """Profile whatever the kernel is doing for a fixed wall-clock window.

    Unlike :func:`profile_cell_torch_timed` this does not run a cell; the
    workload is the already-running code on the main thread. Held under
    :func:`profiler_slot` to stay mutually exclusive with the cell-magic path.
    """
    options = options or {}
    try:
        with profiler_slot():
            return _profile_live_window_locked(
                window_s=window_s,
                warmup_s=warmup_s,
                preset=preset,
                options=options,
                label=label,
            )
    except ProfilerBusyError as exc:
        job = ProfileJob("live", label, preset, {"backend": "torch", "mode": "live"})
        job.status = "error"
        job.error = str(exc)
        job.finished = time.time()
        return job


def _profile_live_window_locked(
    *,
    window_s: float,
    warmup_s: float,
    preset: str,
    options: Dict[str, Any],
    label: str,
) -> ProfileJob:
    import torch  # type: ignore
    from torch.profiler import profile  # type: ignore

    job = ProfileJob(
        "live",
        label,
        preset,
        {
            "backend": "torch",
            "mode": "live",
            "window_s": window_s,
            "warmup_s": warmup_s,
            "approx": True,
            "stop_after_window": False,
        },
    )
    job.status = "running"
    keep_trace = bool(options.get("keep_trace", False))
    try:
        if warmup_s > 0:
            time.sleep(warmup_s)
        prof = profile(
            activities=_torch_activities(),
            record_shapes=bool(options.get("record_shapes", False)),
            profile_memory=bool(options.get("profile_memory", False)),
            with_stack=bool(options.get("with_stack", False)),
        )
        prof.start()
        try:
            time.sleep(max(window_s, 0.0))
            if torch.cuda.is_available():
                try:
                    torch.cuda.synchronize()
                except Exception:
                    pass
        finally:
            prof.stop()
        _finalize_torch_job(job, prof, keep_trace=keep_trace)
        job.status = "done"
    except Exception as exc:
        job.status = "error"
        job.error = f"{type(exc).__name__}: {exc}"
    finally:
        job.finished = time.time()
    return job
