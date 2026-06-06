"""rocprofv3 profiling integration.

Runs ``rocprofv3`` against a notebook or Python script in a background thread,
parses the resulting ``*_kernel_trace.csv`` file and aggregates per-kernel
statistics for display in the JupyterLab frontend.
"""

from __future__ import annotations

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

_JOBS: Dict[str, "ProfileJob"] = {}
_JOBS_LOCK = threading.Lock()


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
        self.memory_copies: List[Dict[str, Any]] = []
        self.summary: Dict[str, Any] = {}

    def to_dict(self, include_results: bool = True) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "id": self.id,
            "target_type": self.target_type,
            "target": self.target,
            "preset": self.preset,
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
                    "memory_copies": self.memory_copies,
                    "summary": self.summary,
                }
            )
        return data


def _resolve_target_command(job: ProfileJob, workdir: str) -> List[str]:
    """Build the command to be profiled (everything after ``--``)."""
    if job.target_type == "notebook":
        if not os.path.exists(job.target):
            raise FileNotFoundError(f"Notebook not found: {job.target}")
        script_path = os.path.join(workdir, "profiled_notebook.py")
        convert = subprocess.run(
            [
                sys.executable,
                "-m",
                "jupyter",
                "nbconvert",
                "--to",
                "script",
                "--output",
                "profiled_notebook",
                "--output-dir",
                workdir,
                job.target,
            ],
            capture_output=True,
            text=True,
        )
        if convert.returncode != 0:
            raise RuntimeError(
                "nbconvert failed:\n" + convert.stdout + "\n" + convert.stderr
            )
        if not os.path.exists(script_path):
            # nbconvert may keep the original extension casing; fall back to glob.
            matches = glob.glob(os.path.join(workdir, "profiled_notebook*.py"))
            if not matches:
                raise RuntimeError("nbconvert did not produce a Python script.")
            script_path = matches[0]
        return [sys.executable, script_path]

    if job.target_type == "script":
        if not os.path.exists(job.target):
            raise FileNotFoundError(f"Script not found: {job.target}")
        return [sys.executable, job.target]

    if job.target_type == "command":
        return shlex.split(job.target)

    raise ValueError(f"Unknown target_type: {job.target_type}")


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

    total_ns = sum(k["total_ns"] for k in job.kernels)
    job.summary = {
        "kernel_count": len(job.kernels),
        "total_kernel_ns": total_ns,
        "total_dispatches": sum(k["calls"] for k in job.kernels),
    }


def _run_job(job: ProfileJob) -> None:
    job.status = "running"
    exe = rocprof_executable()
    workdir = tempfile.mkdtemp(prefix="rocm_profile_")
    outdir = os.path.join(workdir, "out")
    os.makedirs(outdir, exist_ok=True)
    try:
        if exe is None:
            raise RuntimeError("rocprofv3 executable not found.")

        target_cmd = _resolve_target_command(job, workdir)
        flag = TRACE_PRESETS.get(job.preset, TRACE_PRESETS["runtime"])

        command = [exe, flag, "--output-format", "csv", "-d", outdir]
        include = job.extra.get("kernel_include_regex")
        exclude = job.extra.get("kernel_exclude_regex")
        if include:
            command += ["--kernel-include-regex", str(include)]
        if exclude:
            command += ["--kernel-exclude-regex", str(exclude)]
        command += ["--", *target_cmd]
        job.command = command

        timeout = float(job.extra.get("timeout", 600))
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


def start_profile(
    target_type: str,
    target: str,
    preset: str = "runtime",
    extra: Optional[Dict[str, Any]] = None,
) -> ProfileJob:
    job = ProfileJob(target_type, target, preset, extra or {})
    with _JOBS_LOCK:
        _JOBS[job.id] = job
    thread = threading.Thread(target=_run_job, args=(job,), daemon=True)
    thread.start()
    return job


def get_job(job_id: str) -> Optional[ProfileJob]:
    with _JOBS_LOCK:
        return _JOBS.get(job_id)


def list_jobs() -> List[Dict[str, Any]]:
    with _JOBS_LOCK:
        jobs = list(_JOBS.values())
    jobs.sort(key=lambda j: j.created, reverse=True)
    return [j.to_dict(include_results=False) for j in jobs]


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


def _prune_cell_jobs(directory: str, max_keep: int) -> None:
    try:
        files = [
            os.path.join(directory, name)
            for name in os.listdir(directory)
            if name.endswith(".json")
        ]
    except OSError:
        return
    files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    for stale in files[max_keep:]:
        try:
            os.remove(stale)
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
        names = [name for name in os.listdir(directory) if name.endswith(".json")]
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
