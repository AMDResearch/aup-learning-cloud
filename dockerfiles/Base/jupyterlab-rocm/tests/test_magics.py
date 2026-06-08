# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Unit tests for IPython magic display helpers."""

from jupyterlab_rocm.magics import _error_html, _esc, _fmt_ns, _render_job
from jupyterlab_rocm.profiler import ProfileJob


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
