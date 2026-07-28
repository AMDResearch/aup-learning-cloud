# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.

"""Public CLI tests for direct SSH inventory validation."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VALIDATE = ROOT / "skills" / "deploy-aup-learning-cloud" / "scripts" / "validate.py"


def run_validate(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(VALIDATE), *args], capture_output=True, text=True, check=False)


def write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def valid_inventory() -> str:
    return """k3s_cluster:
  children:
    server:
      hosts:
        server:
          auplc_gpu_access_enabled: true
    agent:
      hosts:
        agent:
          auplc_gpu_access_enabled: false
"""


def test_validator_accepts_direct_inventory_without_resolution_manifest(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    inventory = write(repo / "inventory.yml", valid_inventory())
    values = write(repo / "values.yaml", "custom:\n  resources:\n    metadata: {}\n")

    result = run_validate(
        "--repo", str(repo), "--topology", "ssh-preinstalled", "--inventory", str(inventory), "--values", str(values)
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "GPU access inventory is valid" in result.stdout


@pytest.mark.parametrize(
    ("inventory_content", "expected_error"),
    [
        (valid_inventory().replace("          auplc_gpu_access_enabled: true\n", ""), "must define exactly one"),
        (valid_inventory().replace("auplc_gpu_access_enabled: true", "auplc_gpu_access_enabled: yes"), "malformed"),
        (
            valid_inventory().replace(
                "          auplc_gpu_access_enabled: true\n",
                "          auplc_gpu_access_enabled: true\n          auplc_gpu_access_enabled: false\n",
            ),
            "must define exactly one",
        ),
    ],
)
def test_validator_rejects_invalid_direct_inventory(
    tmp_path: Path, inventory_content: str, expected_error: str
) -> None:
    repo = tmp_path / "checkout"
    inventory = write(repo / "inventory.yml", inventory_content)
    values = write(repo / "values.yaml", "custom:\n  resources:\n    metadata: {}\n")

    result = run_validate(
        "--repo", str(repo), "--topology", "ssh-preinstalled", "--inventory", str(inventory), "--values", str(values)
    )

    assert result.returncode == 1
    assert expected_error in result.stdout


def test_validator_reports_direct_inventory_not_found(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    values = write(repo / "values.yaml", "custom:\n  resources:\n    metadata: {}\n")

    result = run_validate(
        "--repo", str(repo), "--topology", "ssh-preinstalled", "--inventory", "missing.yml", "--values", str(values)
    )

    assert result.returncode == 1
    assert "inventory not found" in result.stdout
    assert "generated inventory not found" not in result.stdout


def test_validator_rejects_gpu_resolution_without_inventory(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    values = write(repo / "values.yaml", "custom:\n  resources:\n    metadata: {}\n")
    resolution = write(repo / "resolution.json", "{}\n")

    result = run_validate(
        "--repo",
        str(repo),
        "--topology",
        "ssh-preinstalled",
        "--gpu-resolution",
        str(resolution),
        "--values",
        str(values),
    )

    assert result.returncode == 1
    assert "--gpu-resolution requires --inventory" in result.stdout
