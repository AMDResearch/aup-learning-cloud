# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Unit tests for rocprofv3 CSV parsing and cell-job persistence."""

import json
import os
import sys
import time
from unittest import mock

import pytest

from jupyterlab_rocm import profiler


KERNEL_CSV = """\
Kernel_Name,Start_Timestamp,End_Timestamp
vec_add,1000,2500
vec_add,3000,4200
matmul,5000,9000
"""

MEMORY_CSV = """\
Direction,Start_Timestamp,End_Timestamp
H2D,100,500
D2H,600,900
H2D,1000,1200
"""


def test_parse_kernel_trace_aggregates_and_sorts(tmp_path):
    path = tmp_path / "kernel_trace.csv"
    path.write_text(KERNEL_CSV)

    kernels = profiler._parse_kernel_trace(str(path))

    assert len(kernels) == 2
    assert kernels[0]["name"] == "matmul"
    assert kernels[0]["calls"] == 1
    assert kernels[0]["total_ns"] == 4000.0
    assert kernels[0]["percent"] == pytest.approx(59.7, abs=0.01)

    vec = next(k for k in kernels if k["name"] == "vec_add")
    assert vec["calls"] == 2
    assert vec["total_ns"] == 2700.0
    assert vec["avg_ns"] == 1350.0
    assert vec["min_ns"] == 1200.0
    assert vec["max_ns"] == 1500.0


def test_parse_kernel_trace_skips_bad_rows(tmp_path):
    path = tmp_path / "kernel_trace.csv"
    path.write_text(
        "Kernel_Name,Start_Timestamp,End_Timestamp\n"
        "good,100,200\n"
        "bad,not_a_number,300\n"
    )

    kernels = profiler._parse_kernel_trace(str(path))

    assert len(kernels) == 1
    assert kernels[0]["name"] == "good"
    assert kernels[0]["total_ns"] == 100.0


def test_parse_memory_copy_trace(tmp_path):
    path = tmp_path / "memory_copy_trace.csv"
    path.write_text(MEMORY_CSV)

    copies = profiler._parse_memory_copy_trace(str(path))

    by_dir = {c["direction"]: c for c in copies}
    assert by_dir["H2D"]["calls"] == 2
    assert by_dir["H2D"]["total_ns"] == 600.0
    assert by_dir["D2H"]["calls"] == 1
    assert by_dir["D2H"]["total_ns"] == 300.0


def test_profile_job_to_dict_truncates_output():
    job = profiler.ProfileJob("script", "/tmp/foo.py", "kernel", {})
    job.stdout = "x" * 10000
    job.stderr = "y" * 10000
    job.kernels = [{"name": "k", "calls": 1, "total_ns": 1.0}]

    data = job.to_dict(include_results=True)

    assert len(data["stdout"]) == 8000
    assert len(data["stderr"]) == 8000
    assert data["kernels"][0]["name"] == "k"

    slim = job.to_dict(include_results=False)
    assert "stdout" not in slim
    assert "kernels" not in slim


def test_attach_blockers_when_torch_loaded():
    with mock.patch.dict(sys.modules, {"torch": object()}):
        message = profiler.attach_blockers()
    assert message is not None
    assert "PyTorch is already loaded" in message


def test_attach_blockers_clear_without_torch():
    modules = {k: v for k, v in sys.modules.items() if k != "torch"}
    with mock.patch.dict(sys.modules, modules, clear=True):
        assert profiler.attach_blockers() is None


def test_attach_status_hints():
    with mock.patch.object(profiler, "rocprof_executable", return_value="/opt/rocm/bin/rocprofv3"):
        with mock.patch.object(profiler, "_read_ptrace_scope", return_value=2):
            with mock.patch.dict(os.environ, {}, clear=True):
                status = profiler.attach_status("/opt/rocm/bin/rocprofv3")

    assert status["supported"] is True
    assert status["ptrace_scope"] == 2
    assert status["tool_attach_env"] is False
    assert "ROCP_TOOL_ATTACH=1" in status["hint"]
    assert "CAP_SYS_PTRACE" in status["hint"]


def test_attach_status_unavailable_when_ptrace_scope_3():
    with mock.patch.object(profiler, "_read_ptrace_scope", return_value=3):
        status = profiler.attach_status("/opt/rocm/bin/rocprofv3")

    assert status["supported"] is False
    assert "ptrace_scope=3" in status["hint"]


def test_cell_looks_like_torch_gpu():
    assert profiler.cell_looks_like_torch_gpu("import torch\nx = torch.randn(4, device='cuda')")
    assert profiler.cell_looks_like_torch_gpu("import torch\nx = torch.ones(4).cuda()")
    assert not profiler.cell_looks_like_torch_gpu("print('hello')")
    assert not profiler.cell_looks_like_torch_gpu("import numpy as np\nnp.dot(a, b)")


def test_cell_profile_unavailable_reason():
    assert profiler.cell_profile_unavailable_reason("print('hello')") is not None
    assert "PyTorch GPU" in profiler.cell_profile_unavailable_reason("print('hello')")

    cell = "import torch\nx = torch.randn(4, device='cuda')"
    with mock.patch.object(profiler, "torch_cuda_available", return_value=False):
        reason = profiler.cell_profile_unavailable_reason(cell)
        assert reason is not None
        assert "ROCm/CUDA" in reason

    with mock.patch.object(profiler, "torch_cuda_available", return_value=True):
        assert profiler.cell_profile_unavailable_reason(cell) is None


def test_detect_cell_backend_routes_torch_when_cuda_available():
    cell = "import torch\nx = torch.randn(4, device='cuda')"
    with mock.patch.object(profiler, "cell_looks_like_torch_gpu", return_value=True):
        with mock.patch.object(profiler, "torch_cuda_available", return_value=True):
            assert profiler.detect_cell_backend(cell) == "torch"
    with mock.patch.object(profiler, "cell_looks_like_torch_gpu", return_value=True):
        with mock.patch.object(profiler, "torch_cuda_available", return_value=False):
            assert profiler.detect_cell_backend(cell) == "rocprofv3"


def test_parse_torch_kernel_events():
    trace = {
        "traceEvents": [
            {"cat": "kernel", "ph": "X", "name": "gemm_a", "dur": 10.0},
            {"cat": "kernel", "ph": "X", "name": "gemm_a", "dur": 5.0},
            {"cat": "cpu_op", "ph": "X", "name": "ignored", "dur": 100.0},
        ]
    }
    kernels = profiler._parse_torch_kernel_events(trace)

    assert len(kernels) == 1
    assert kernels[0]["name"] == "gemm_a"
    assert kernels[0]["calls"] == 2
    assert kernels[0]["total_ns"] == 15000.0
    assert kernels[0]["avg_ns"] == 7500.0


def test_profile_cell_subprocess_parses_csv(tmp_path, monkeypatch):
    outdir = tmp_path / "out"
    outdir.mkdir()
    (outdir / "results_kernel_trace.csv").write_text(KERNEL_CSV)

    def fake_run(command, **kwargs):
        return mock.Mock(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(profiler, "rocprof_executable", lambda: "/opt/rocm/bin/rocprofv3")
    monkeypatch.setattr(profiler.subprocess, "run", fake_run)
    monkeypatch.setattr(profiler.glob, "glob", lambda pattern, **kw: [str(outdir / "results_kernel_trace.csv")])

    job = profiler.profile_cell_subprocess("print('hi')", preset="kernel", label="demo")

    assert job.status == "done"
    assert job.extra["backend"] == "rocprofv3-subprocess"
    assert len(job.kernels) == 2
    assert job.kernels[0]["name"] == "matmul"


def test_register_and_list_cell_jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(profiler, "cell_jobs_dir", lambda: str(tmp_path))

    job = profiler.ProfileJob("cell", "test cell", "kernel", {})
    job.status = "done"
    job.kernels = [{"name": "foo", "calls": 1, "total_ns": 100.0}]
    job.summary = {"kernel_count": 1, "total_kernel_ns": 100.0, "total_dispatches": 1}

    profiler.register_cell_job(job)

    jobs = profiler.list_cell_jobs()
    assert len(jobs) == 1
    assert jobs[0]["id"] == job.id
    assert jobs[0]["kernels"][0]["name"] == "foo"

    stored = json.loads((tmp_path / f"{job.id}.json").read_text())
    assert stored["target"] == "test cell"


# ---------------------------------------------------------------------------
# key_averages (operator-level) parsing
# ---------------------------------------------------------------------------


class _FakeEvt:
    """Stand-in for a torch ``FunctionEventAvg`` row."""

    def __init__(
        self,
        key,
        count,
        cpu_total,
        self_cpu,
        dev_total,
        self_dev,
        *,
        cpu_mem=0,
        self_cpu_mem=0,
        dev_mem=0,
        self_dev_mem=0,
        input_shapes=None,
        stack=None,
    ):
        self.key = key
        self.count = count
        self.cpu_time_total = cpu_total
        self.self_cpu_time_total = self_cpu
        self.device_time_total = dev_total
        self.self_device_time_total = self_dev
        self.cpu_memory_usage = cpu_mem
        self.self_cpu_memory_usage = self_cpu_mem
        self.device_memory_usage = dev_mem
        self.self_device_memory_usage = self_dev_mem
        self.input_shapes = input_shapes
        self.stack = stack


class _FakeProf:
    def __init__(self, events):
        self._events = events

    def key_averages(self):
        return self._events


def test_summarize_key_averages_converts_and_sorts():
    events = [
        _FakeEvt("aten::mm", 2, cpu_total=10, self_cpu=4, dev_total=20, self_dev=18),
        _FakeEvt("aten::add", 5, cpu_total=6, self_cpu=6, dev_total=4, self_dev=2),
    ]
    ops = profiler._summarize_key_averages(_FakeProf(events))

    assert ops[0]["name"] == "aten::mm"  # highest self device time
    assert ops[0]["calls"] == 2
    # microseconds -> nanoseconds
    assert ops[0]["self_gpu_ns"] == 18000.0
    assert ops[0]["cpu_total_ns"] == 10000.0
    # percent computed against self device total (18 / 20 = 90%)
    assert ops[0]["percent"] == 90.0


def test_summarize_key_averages_falls_back_to_cpu_when_no_gpu():
    events = [
        _FakeEvt("aten::add", 1, cpu_total=8, self_cpu=8, dev_total=0, self_dev=0),
        _FakeEvt("aten::mul", 1, cpu_total=2, self_cpu=2, dev_total=0, self_dev=0),
    ]
    ops = profiler._summarize_key_averages(_FakeProf(events))

    assert ops[0]["name"] == "aten::add"
    assert ops[0]["percent"] == 80.0  # 8 / 10 self cpu


def test_evt_attr_prefers_legacy_cuda_name():
    evt = type("E", (), {"cuda_time_total": 7})()
    assert profiler._evt_attr(evt, "device_time_total", "cuda_time_total") == 7


def test_apply_operator_summary():
    job = profiler.ProfileJob("cell", "x", "kernel", {})
    job.operators = [
        {"self_cpu_ns": 1000.0, "self_gpu_ns": 2000.0},
        {"self_cpu_ns": 500.0, "self_gpu_ns": 0.0},
    ]
    profiler._apply_kernel_summary(job)
    profiler._apply_operator_summary(job)

    assert job.summary["operator_count"] == 2
    assert job.summary["self_cpu_total_ns"] == 1500.0
    assert job.summary["self_gpu_total_ns"] == 2000.0


# ---------------------------------------------------------------------------
# Trace persistence / job-file filtering
# ---------------------------------------------------------------------------


def test_is_job_file_excludes_trace():
    assert profiler._is_job_file("abc123.json")
    assert not profiler._is_job_file("abc123.trace.json")
    assert not profiler._is_job_file("notes.txt")


def test_store_trace_moves_file(tmp_path, monkeypatch):
    monkeypatch.setattr(profiler, "cell_jobs_dir", lambda: str(tmp_path))
    job = profiler.ProfileJob("cell", "x", "kernel", {})
    src = tmp_path / "src.json"
    src.write_text("{}")

    profiler._store_trace(job, str(src))

    assert job.extra["trace_available"] is True
    assert os.path.isfile(profiler.trace_path_for(job.id))
    assert not src.exists()


def test_list_cell_jobs_ignores_trace_files(tmp_path, monkeypatch):
    monkeypatch.setattr(profiler, "cell_jobs_dir", lambda: str(tmp_path))
    job = profiler.ProfileJob("cell", "x", "kernel", {})
    job.status = "done"
    profiler.register_cell_job(job)
    (tmp_path / f"{job.id}.trace.json").write_text('{"traceEvents": []}')

    jobs = profiler.list_cell_jobs()

    assert len(jobs) == 1
    assert jobs[0]["id"] == job.id


# ---------------------------------------------------------------------------
# Mode dispatch + windowed profiling (with a fake torch)
# ---------------------------------------------------------------------------


def _install_fake_torch(monkeypatch, events, cuda=False):
    import types

    sync_calls = {"count": 0}

    def _synchronize(*args, **kwargs):
        sync_calls["count"] += 1

    torch_mod = types.ModuleType("torch")
    torch_mod.cuda = types.SimpleNamespace(
        is_available=lambda: cuda, synchronize=_synchronize
    )

    prof_mod = types.ModuleType("torch.profiler")

    class ProfilerActivity:
        CPU = "CPU"
        CUDA = "CUDA"

    class FakeProfile:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.started = False
            self.stopped = False
            self._schedule = kwargs.get("schedule")
            self._on_ready = kwargs.get("on_trace_ready")
            self._steps = 0

        def __enter__(self):
            self.start()
            return self

        def __exit__(self, *exc):
            self.stop()
            return False

        def start(self):
            self.started = True

        def stop(self):
            self.stopped = True

        def key_averages(self):
            return events

        def export_chrome_trace(self, path):
            with open(path, "w") as handle:
                json.dump(
                    {
                        "traceEvents": [
                            {"cat": "kernel", "ph": "X", "name": "k", "dur": 1.0}
                        ]
                    },
                    handle,
                )

        def step(self):
            self._steps += 1
            if self._schedule and self._on_ready:
                cycle_len = (
                    self._schedule.get("wait", 0)
                    + self._schedule.get("warmup", 0)
                    + self._schedule.get("active", 1)
                )
                if cycle_len > 0 and self._steps % cycle_len == 0:
                    self._on_ready(self)

    def schedule(**kwargs):
        return kwargs

    prof_mod.ProfilerActivity = ProfilerActivity
    prof_mod.profile = FakeProfile
    prof_mod.schedule = schedule

    monkeypatch.setitem(sys.modules, "torch", torch_mod)
    monkeypatch.setitem(sys.modules, "torch.profiler", prof_mod)
    return sync_calls


class _FakeShell:
    def __init__(self):
        self.user_ns = {}

    def run_cell(self, cell, store_history=False):
        return None


def test_run_cell_profile_full(monkeypatch):
    events = [_FakeEvt("aten::mm", 1, 10, 10, 20, 20)]
    _install_fake_torch(monkeypatch, events)
    shell = _FakeShell()

    job = profiler.run_cell_profile(
        shell, "x", label="demo", options={"profile_memory": True}
    )

    assert job.status == "done"
    assert job.extra["mode"] == "full"
    assert job.extra["backend"] == "torch"
    assert job.operators and job.operators[0]["name"] == "aten::mm"
    assert job.kernels  # parsed from the fake chrome trace


def test_run_cell_profile_busy(monkeypatch):
    events = [_FakeEvt("aten::mm", 1, 10, 10, 20, 20)]
    _install_fake_torch(monkeypatch, events)
    with profiler.profiler_slot():
        job = profiler.run_cell_profile(_FakeShell(), "x", label="demo")
    assert job.status == "error"
    assert "already active" in (job.error or "")


def test_profiler_slot_mutual_exclusion():
    with profiler.profiler_slot():
        with pytest.raises(profiler.ProfilerBusyError):
            with profiler.profiler_slot():
                pass
    # Released afterwards: can acquire again.
    with profiler.profiler_slot():
        pass


def test_profile_live_window(monkeypatch):
    events = [_FakeEvt("aten::mm", 1, 10, 10, 20, 20)]
    _install_fake_torch(monkeypatch, events, cuda=True)

    job = profiler.profile_live_window(window_s=0.02, warmup_s=0.0)

    assert job.status == "done"
    assert job.target_type == "live"
    assert job.extra["mode"] == "live"
    assert job.extra["approx"] is True
    assert job.extra["stop_after_window"] is False
    assert job.operators and job.operators[0]["name"] == "aten::mm"


def test_profile_live_window_busy(monkeypatch):
    events = [_FakeEvt("aten::mm", 1, 10, 10, 20, 20)]
    _install_fake_torch(monkeypatch, events)
    with profiler.profiler_slot():
        job = profiler.profile_live_window(window_s=0.02)
    assert job.status == "error"
    assert "already active" in (job.error or "")


def test_live_trigger_claim_is_atomic(tmp_path, monkeypatch):
    monkeypatch.setattr(profiler, "cell_jobs_dir", lambda: str(tmp_path))

    profiler.write_live_trigger("k1", {"window_s": 1.0})

    first = profiler.claim_live_trigger("k1")
    second = profiler.claim_live_trigger("k1")

    assert first == {"window_s": 1.0}
    assert second is None  # already claimed


def test_live_trigger_any_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(profiler, "cell_jobs_dir", lambda: str(tmp_path))

    profiler.write_live_trigger(None, {"window_s": 2.0})

    # A kernel with a specific id still picks up the "any" trigger.
    claimed = profiler.claim_live_trigger("kX")
    assert claimed == {"window_s": 2.0}


def test_live_heartbeat_and_armed(tmp_path, monkeypatch):
    monkeypatch.setattr(profiler, "cell_jobs_dir", lambda: str(tmp_path))

    assert profiler.live_armed("k1") is False
    profiler.live_heartbeat("k1")
    assert profiler.live_armed("k1") is True
    assert profiler.live_armed(None) is True  # also written under "any"
    assert profiler.live_armed("k1", max_age=-1.0) is False  # stale


def test_live_busy_lifecycle(tmp_path, monkeypatch):
    monkeypatch.setattr(profiler, "cell_jobs_dir", lambda: str(tmp_path))

    assert profiler.live_busy("k1") is False
    profiler.set_live_busy("k1", time.time() + 60)
    assert profiler.live_busy("k1") is True
    assert profiler.live_busy(None) is True  # also written under "any"
    profiler.clear_live_busy("k1")
    assert profiler.live_busy("k1") is False


def test_live_busy_expires(tmp_path, monkeypatch):
    monkeypatch.setattr(profiler, "cell_jobs_dir", lambda: str(tmp_path))
    profiler.set_live_busy("k1", time.time() - 1)  # already expired
    assert profiler.live_busy("k1") is False


def test_current_kernel_id_fallback(monkeypatch):
    monkeypatch.setitem(sys.modules, "ipykernel.connect", None)
    # With a broken import path the helper must not raise.
    assert profiler.current_kernel_id() is None or isinstance(
        profiler.current_kernel_id(), str
    )


