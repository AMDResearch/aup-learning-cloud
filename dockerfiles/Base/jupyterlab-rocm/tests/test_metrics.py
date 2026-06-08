# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Unit tests for metrics normalisation helpers (no GPU hardware required)."""

import json
from unittest import mock

from jupyterlab_rocm.metrics import (
    _fresh_processes_by_gpu,
    _cu_percent,
    _memory_bytes,
    _microseconds,
    _normalise,
    _normalise_metric,
    _processes,
)


def test_normalise_na_strings():
    assert _normalise("N/A") is None
    assert _normalise("n/a") is None
    assert _normalise("NA") is None
    assert _normalise("") is None
    assert _normalise("  ") is None


def test_normalise_passthrough():
    assert _normalise(42) == 42
    assert _normalise("Radeon RX 7900 XTX") == "Radeon RX 7900 XTX"
    assert _normalise(0) == 0


def test_normalise_metric_uint_sentinels():
    assert _normalise_metric(0xFFFF) is None
    assert _normalise_metric(0xFFFFFFFF) is None
    assert _normalise_metric(0xFFFFFFFFFFFFFFFF) is None


def test_normalise_metric_preserves_bool():
    assert _normalise_metric(True) is True
    assert _normalise_metric(False) is False


def test_normalise_metric_valid_values():
    assert _normalise_metric(150) == 150
    assert _normalise_metric("N/A") is None
    assert _normalise_metric(65534) == 65534


def test_cu_percent():
    assert _cu_percent(32, 128) == 25.0
    assert _cu_percent(None, 128) is None
    assert _cu_percent(32, None) is None
    assert _cu_percent("N/A", 128) is None


def test_memory_bytes_and_microseconds():
    assert _memory_bytes(1048576) == 1048576
    assert _memory_bytes("N/A") is None
    assert _memory_bytes("0.0 B") == 0
    assert _memory_bytes("1.5 MiB") == 1572864
    assert _microseconds(500) == 500
    assert _microseconds("2 ms") == 2000
    assert _microseconds(0xFFFFFFFFFFFFFFFF) is None


def test_processes_keeps_driver_visible_pids():
    driver_pid = 2**31 - 1
    raw = [
        {
            "pid": driver_pid,
            "name": "python",
            "memory_usage": {"gtt_mem": 0, "vram_mem": 0},
            "mem": 200,
            "cu_occupancy": "N/A",
            "sdma_usage": 0,
        },
    ]
    with mock.patch("jupyterlab_rocm.metrics.amdsmi") as amdsmi_mod:
        amdsmi_mod.amdsmi_get_gpu_process_list.return_value = raw
        with mock.patch(
            "jupyterlab_rocm.metrics._compute_units", return_value=None
        ):
            procs = _processes(object())
    assert len(procs) == 1
    assert procs[0]["pid"] == driver_pid


def test_fresh_processes_by_gpu_parses_empty_process_list():
    payload = [
        {
            "gpu": 0,
            "processes": [],
        }
    ]
    with mock.patch("jupyterlab_rocm.metrics.subprocess.run") as run:
        run.return_value.stdout = json.dumps(payload)
        assert _fresh_processes_by_gpu() == {0: []}


def test_fresh_processes_by_gpu_parses_process_rows():
    payload = [
        {
            "gpu": 0,
            "processes": [
                {
                    "name": "N/A",
                    "pid": 4021392,
                    "memory_usage": {
                        "gtt_mem": "0.0 B",
                        "vram_mem": "0.0 B",
                    },
                    "mem_usage": "0.0 B",
                    "cu_occupancy": "N/A",
                    "sdma_usage": "0 us",
                }
            ],
        }
    ]
    with mock.patch("jupyterlab_rocm.metrics.subprocess.run") as run:
        run.return_value.stdout = json.dumps(payload)
        assert _fresh_processes_by_gpu() == {
            0: [
                {
                    "pid": 4021392,
                    "name": None,
                    "gtt_mem": 0,
                    "vram_mem": 0,
                    "mem_usage": 0,
                    "cu_percent": None,
                    "sdma_us": 0,
                }
            ]
        }
