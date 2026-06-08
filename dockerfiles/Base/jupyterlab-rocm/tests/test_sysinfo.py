# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Unit tests for amd-smi CLI wrapper."""

import json
from unittest import mock

from jupyterlab_rocm import sysinfo


def test_run_json_parses_stdout_despite_nonzero_exit():
    proc = mock.Mock(returncode=1, stdout='{"gpu_data": []}', stderr="warning")
    with mock.patch("jupyterlab_rocm.sysinfo.subprocess.run", return_value=proc):
        data, err = sysinfo._run_json("/usr/bin/amd-smi", ["static", "--json"])

    assert err is None
    assert data == {"gpu_data": []}


def test_run_json_reports_empty_stdout():
    proc = mock.Mock(returncode=2, stdout="", stderr="not found")
    with mock.patch("jupyterlab_rocm.sysinfo.subprocess.run", return_value=proc):
        data, err = sysinfo._run_json("/usr/bin/amd-smi", ["list", "--json"])

    assert data is None
    assert err == "not found"


def test_static_info_when_executable_missing():
    with mock.patch("jupyterlab_rocm.sysinfo.amd_smi_executable", return_value=None):
        result = sysinfo.static_info()

    assert result["available"] is False
    assert "not found" in result["error"].lower()
    assert result["list"] == []
    assert result["static"] == []


def test_static_info_normalises_dict_and_list_shapes():
    listing = [{"gpu": 0, "bdf": "0000:03:00.0"}]
    static_dict = {"gpu_data": [{"market_name": "Radeon"}]}
    static_list = [{"market_name": "APU"}]

    with mock.patch("jupyterlab_rocm.sysinfo.amd_smi_executable", return_value="/usr/bin/amd-smi"):
        with mock.patch(
            "jupyterlab_rocm.sysinfo._run_json",
            side_effect=[(listing, None), (static_dict, None)],
        ):
            result = sysinfo.static_info()

    assert result["available"] is True
    assert result["list"] == listing
    assert result["static"] == static_dict["gpu_data"]

    with mock.patch("jupyterlab_rocm.sysinfo.amd_smi_executable", return_value="/usr/bin/amd-smi"):
        with mock.patch(
            "jupyterlab_rocm.sysinfo._run_json",
            side_effect=[(listing, None), (static_list, None)],
        ):
            result = sysinfo.static_info()

    assert result["static"] == static_list
