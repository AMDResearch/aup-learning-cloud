# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Unit tests for metrics normalisation helpers (no GPU hardware required)."""

from jupyterlab_rocm.metrics import _normalise, _normalise_metric


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
