# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Unit tests for IPython magic display helpers."""

from jupyterlab_rocm import magics, profiler
from jupyterlab_rocm.magics import (
    _error_html,
    _esc,
    _fmt_bytes,
    _fmt_ns,
    _mode_label,
    _render_job,
)
from jupyterlab_rocm.profiler import ProfileJob


class _FakeShell:
    def __init__(self):
        self.user_ns = {}

    def run_cell(self, cell, store_history=False):
        return None


def test_fmt_ns_scales_units():
    assert _fmt_ns(500) == "500 ns"
    assert _fmt_ns(1500) == "1.50 us"
    assert _fmt_ns(2_500_000) == "2.500 ms"
    assert _fmt_ns(3_000_000_000) == "3.000 s"


def test_esc_html():
    assert _esc("<script>&") == "&lt;script&gt;&amp;"
    assert _error_html("bad & gone") == _error_html("bad & gone")
    assert "&amp;" in _error_html("bad & gone")
    assert "Cell Profile:" in _error_html("bad & gone")


def test_render_job_empty_kernels():
    job = ProfileJob("cell", "demo", "kernel", {})
    html = _render_job(job)

    assert "No kernel dispatches" in html
    assert "Cell Profile" in html


def test_render_job_torch_backend():
    job = ProfileJob("cell", "demo", "kernel", {"backend": "torch"})
    html = _render_job(job)

    assert "Cell Profile — torch.profiler" in html


def test_render_job_subprocess_backend():
    job = ProfileJob("cell", "demo", "kernel", {"backend": "rocprofv3-subprocess"})
    html = _render_job(job)

    assert "Cell Profile — rocprofv3 subprocess" in html
    assert "separate process" in html


def test_render_job_with_kernels():
    job = ProfileJob("cell", "demo", "kernel", {})
    job.kernels = [
        {
            "name": "very_long_kernel_name_" * 5,
            "calls": 3,
            "total_ns": 9000.0,
            "avg_ns": 3000.0,
            "percent": 75.0,
        }
    ]
    job.summary = {
        "kernel_count": 1,
        "total_dispatches": 3,
        "total_kernel_ns": 9000.0,
    }

    html = _render_job(job)

    assert "Kernels:" in html
    assert "9.00 us" in html
    assert "\u2026" in html  # truncated kernel name


def test_fmt_bytes_scales_units():
    assert _fmt_bytes(512) == "512 B"
    assert _fmt_bytes(2048) == "2.00 KB"
    assert _fmt_bytes(5 * 1024 * 1024) == "5.00 MB"
    assert _fmt_bytes(-1024) == "-1.00 KB"


def test_mode_label_variants():
    full = ProfileJob("cell", "x", "kernel", {"backend": "torch", "mode": "full"})
    assert _mode_label(full) == "full cell"

    live = ProfileJob(
        "live",
        "x",
        "kernel",
        {"backend": "torch", "mode": "live", "window_s": 2, "warmup_s": 1},
    )
    label = _mode_label(live)
    assert "live capture" in label
    assert "approx" in label


def test_render_job_with_operators():
    job = ProfileJob("cell", "demo", "kernel", {"backend": "torch", "mode": "full"})
    job.operators = [
        {
            "name": "aten::mm",
            "calls": 2,
            "cpu_total_ns": 10000.0,
            "self_cpu_ns": 4000.0,
            "gpu_total_ns": 20000.0,
            "self_gpu_ns": 18000.0,
            "cpu_mem": 0,
            "self_cpu_mem": 1024,
            "gpu_mem": 0,
            "self_gpu_mem": 2048,
            "input_shapes": "[[4, 4], [4, 4]]",
            "stack": None,
            "percent": 90.0,
        }
    ]
    job.summary = {
        "kernel_count": 0,
        "total_dispatches": 0,
        "total_kernel_ns": 0.0,
        "operator_count": 1,
        "self_cpu_total_ns": 4000.0,
        "self_gpu_total_ns": 18000.0,
    }

    html = _render_job(job)

    assert "Operators:" in html
    assert "aten::mm" in html
    assert "Input Shapes" in html  # shapes column rendered
    assert "Self GPU Mem" in html  # memory column rendered
    assert "2.00 KB" in html


def test_magic_routes_full(monkeypatch):
    captured = {}
    monkeypatch.setattr(profiler, "cell_profile_unavailable_reason", lambda c: None)
    monkeypatch.setattr(profiler, "register_cell_job", lambda job: None)

    def fake_run(shell, cell, *, label, preset, options):
        captured["preset"] = preset
        captured["options"] = options
        job = ProfileJob("cell", label, preset, {"backend": "torch", "mode": "full"})
        job.status = "done"
        return job

    monkeypatch.setattr(profiler, "run_cell_profile", fake_run)

    m = magics.RocmMagics(shell=_FakeShell())
    m.rocprofv3("--memory --trace", "import torch")

    assert captured["preset"] == "kernel"
    assert captured["options"]["profile_memory"] is True
    assert captured["options"]["keep_trace"] is True
    assert "window_s" not in captured["options"]


def test_live_watcher_handle_trigger(monkeypatch):
    captured = {}

    def fake_live(**kwargs):
        captured["kwargs"] = kwargs
        job = ProfileJob("live", "live capture", "kernel", {"backend": "torch", "mode": "live"})
        job.status = "done"
        return job

    monkeypatch.setattr(profiler, "profile_live_window", fake_live)
    monkeypatch.setattr(
        profiler, "register_cell_job", lambda job: captured.__setitem__("registered", job)
    )

    magics._handle_live_trigger(
        {
            "window_s": 1.5,
            "warmup_s": 0.5,
            "preset": "kernel",
            "options": {"profile_memory": True},
        }
    )

    assert captured["kwargs"]["window_s"] == 1.5
    assert captured["kwargs"]["warmup_s"] == 0.5
    assert captured["kwargs"]["options"]["profile_memory"] is True
    assert captured["registered"].target_type == "live"


def test_render_job_empty_full_mode_hint():
    job = ProfileJob("cell", "demo", "kernel", {"backend": "torch", "mode": "full"})
    html = _render_job(job)

    assert "No kernel dispatches were captured" in html


def test_render_job_empty_live_hint():
    job = ProfileJob("live", "demo", "kernel", {"backend": "torch", "mode": "live"})
    html = _render_job(job)

    assert "live window captured no GPU work" in html
    assert "live capture" in html  # mode label in the title


