# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Unit tests for rocprofv3 CSV parsing and cell-job persistence."""

import json
import os
import sys
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
