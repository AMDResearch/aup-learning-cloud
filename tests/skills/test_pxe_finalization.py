# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.

"""End-to-end contracts for immediate PXE GPU policy generation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GEN_CONFIGS = ROOT / "skills" / "deploy-aup-learning-cloud" / "scripts" / "gen_configs.py"


def pxe_spec(gpu_agents: bool) -> dict:
    return {
        "topology": "pxe-diskless",
        "k3s_version": "v1.32.3+k3s1",
        "server": {"name": "controller", "ip": "192.168.1.10"},
        "agents": [{"name": "diskless-agent", "ip": "192.168.1.11"}],
        "network": {"interface": "enp1s0", "subnet": "192.168.1.0/24"},
        "pxe": {
            "authorized_keys": ["ssh-ed25519 AAAA test@example"],
            "rootfs_password": "do-not-print-this-secret",
            "diskless_agents_have_amd_gpus": gpu_agents,
        },
    }


def write_json(path: Path, document: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def write_fake_ansible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, controller_gpu: bool = False) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_ansible = fake_bin / "ansible-playbook"
    bdf = "0000:03:00.0" if controller_gpu else ""
    fake_ansible.write_text(
        f"""#!/usr/bin/env python3
import json
import sys
from pathlib import Path

output = next(value.split('=', 1)[1] for value in sys.argv if value.startswith('gpu_access_discovery_output_path='))
Path(output).write_text(json.dumps({{
    'version': 1,
    'hosts': [{{
        'host': 'controller', 'reachable': True,
        'lspci': {{'rc': 0, 'stdout': {bdf!r}}},
        'sysfs': {{'rc': 0, 'stdout': {bdf!r}}},
    }}],
}}), encoding='utf-8')
""",
        encoding="utf-8",
    )
    fake_ansible.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")


def run_generator(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GEN_CONFIGS), *arguments],
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )


def canonical_artifacts(out_dir: Path) -> tuple[Path, ...]:
    return (
        out_dir / "inventory.yml",
        out_dir / "pb-pxe-controller.vars.yml",
        out_dir / "values-basic-example.yaml",
        out_dir / "gpu-access-resolution.json",
    )


def test_pxe_gpu_agents_publish_immediate_boolean_only_rootfs_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_fake_ansible(tmp_path, monkeypatch)
    out_dir = tmp_path / "generated"

    result = run_generator("--spec", str(write_json(tmp_path / "spec.json", pxe_spec(True))), "--out-dir", str(out_dir))

    assert result.returncode == 0, result.stderr
    inventory = (out_dir / "inventory.yml").read_text(encoding="utf-8")
    values = (out_dir / "values-basic-example.yaml").read_text(encoding="utf-8")
    manifest = json.loads((out_dir / "gpu-access-resolution.json").read_text(encoding="utf-8"))
    pxe_vars = (out_dir / "pb-pxe-controller.vars.yml").read_text(encoding="utf-8")
    assert "auplc_render_gid" not in inventory
    assert "auplc_gpu_access_enabled: auto" not in inventory
    assert "gpuAccess" not in values
    assert "pxe_gpu_access_enabled: true" in pxe_vars
    assert "pxe_gpu_access_enabled: auto" not in pxe_vars
    assert manifest == {
        "version": 1,
        "status": "cpu_only",
        "hosts": {"controller": False},
        "pxe_rootfs": {"gpu_access_enabled": True},
    }
    assert not list(out_dir.glob(".pxe-finalizer-*"))
    assert "do-not-print-this-secret" not in result.stdout + result.stderr


def test_pxe_cpu_agents_publish_a_disabled_rootfs_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_fake_ansible(tmp_path, monkeypatch)
    out_dir = tmp_path / "generated"

    result = run_generator(
        "--spec", str(write_json(tmp_path / "spec.json", pxe_spec(False))), "--out-dir", str(out_dir)
    )

    assert result.returncode == 0, result.stderr
    pxe_vars = (out_dir / "pb-pxe-controller.vars.yml").read_text(encoding="utf-8")
    manifest = json.loads((out_dir / "gpu-access-resolution.json").read_text(encoding="utf-8"))
    assert "pxe_gpu_access_enabled: false" in pxe_vars
    assert "pxe_gpu_access_enabled: auto" not in pxe_vars
    assert "auplc_render_gid" not in pxe_vars
    assert manifest["pxe_rootfs"] == {"gpu_access_enabled": False}


def test_pxe_gpu_controller_and_rootfs_publish_independent_booleans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_fake_ansible(tmp_path, monkeypatch, controller_gpu=True)
    out_dir = tmp_path / "generated"

    result = run_generator("--spec", str(write_json(tmp_path / "spec.json", pxe_spec(True))), "--out-dir", str(out_dir))

    assert result.returncode == 0, result.stderr
    inventory = (out_dir / "inventory.yml").read_text(encoding="utf-8")
    manifest = json.loads((out_dir / "gpu-access-resolution.json").read_text(encoding="utf-8"))
    assert "auplc_gpu_access_enabled: true" in inventory
    assert "auplc_gpu_access_enabled: auto" not in inventory
    pxe_vars = (out_dir / "pb-pxe-controller.vars.yml").read_text(encoding="utf-8")
    assert "pxe_gpu_access_enabled: auto" not in pxe_vars
    assert manifest["status"] == "gpu_resolved"
    assert manifest["pxe_rootfs"] == {"gpu_access_enabled": True}


def test_pxe_generator_refuses_existing_canonical_artifacts_without_force(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_fake_ansible(tmp_path, monkeypatch)
    out_dir = tmp_path / "generated"
    out_dir.mkdir()
    existing = out_dir / "values-basic-example.yaml"
    existing.write_text("existing\n", encoding="utf-8")

    result = run_generator("--spec", str(write_json(tmp_path / "spec.json", pxe_spec(True))), "--out-dir", str(out_dir))

    assert result.returncode == 1
    assert "refusing to overwrite existing" in result.stderr
    assert existing.read_text(encoding="utf-8") == "existing\n"
    assert all(not path.exists() for path in canonical_artifacts(out_dir) if path != existing)


def test_pxe_generator_does_not_publish_when_controller_discovery_is_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_ansible = fake_bin / "ansible-playbook"
    fake_ansible.write_text(
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path

output = next(value.split('=', 1)[1] for value in sys.argv if value.startswith('gpu_access_discovery_output_path='))
Path(output).write_text(json.dumps({'version': 1, 'hosts': [{'host': 'controller', 'reachable': False, 'lspci': {'rc': 0, 'stdout': ''}, 'sysfs': {'rc': 0, 'stdout': ''}}]}), encoding='utf-8')
""",
        encoding="utf-8",
    )
    fake_ansible.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")
    out_dir = tmp_path / "generated"

    result = run_generator("--spec", str(write_json(tmp_path / "spec.json", pxe_spec(True))), "--out-dir", str(out_dir))

    assert result.returncode == 1
    assert all(not path.exists() for path in canonical_artifacts(out_dir))
