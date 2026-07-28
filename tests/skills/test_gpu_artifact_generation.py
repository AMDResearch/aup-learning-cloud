# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.

"""End-to-end contracts for automatic GPU artifact generation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GEN_CONFIGS = ROOT / "skills" / "deploy-aup-learning-cloud" / "scripts" / "gen_configs.py"


def evidence_host(name: str, *, gpu: bool = False, gid: int = 993, reachable: bool = True) -> dict:
    bdf = "0000:03:00.0" if gpu else ""
    return {
        "host": name,
        "reachable": reachable,
        "lspci": {"rc": 0, "stdout": bdf},
        "sysfs": {"rc": 0, "stdout": bdf},
        "render_group": {"rc": 0, "stdout": f"render:x:{gid}:\n"},
        "groups": {"rc": 0, "stdout": f"render:x:{gid}:\n"},
        "state": {
            "stat_success": True,
            "content_success": True,
            "exists": False,
            "regular": False,
            "symlink": False,
            "content": "",
        },
        "rule": {
            "stat_success": True,
            "content_success": True,
            "exists": False,
            "regular": False,
            "symlink": False,
            "content": "",
        },
        "legacy_rules": {
            key: {
                "stat_success": True,
                "content_success": True,
                "exists": False,
                "regular": False,
                "symlink": False,
                "content": "",
            }
            for key in ("kfd", "amdgpu", "rocm_devices")
        },
    }


def ssh_spec() -> dict:
    return {
        "topology": "ssh-preinstalled",
        "k3s_version": "v1.32.3+k3s1",
        "server": {"name": "server", "ip": "192.168.1.10"},
        "agents": [{"name": "agent", "ip": "192.168.1.11"}],
    }


def write_fake_ansible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, document: dict) -> Path:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_ansible = fake_bin / "ansible-playbook"
    fake_ansible.write_text(
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

arguments = sys.argv[1:]
Path(os.environ["FAKE_ANSIBLE_RECORD"]).write_text(json.dumps(arguments), encoding="utf-8")
environment_record = os.environ.get("FAKE_ANSIBLE_ENV_RECORD")
if environment_record:
    Path(environment_record).write_text(
     json.dumps({key: os.environ.get(key) for key in ("ANSIBLE_CONFIG", "ANSIBLE_HOST_KEY_CHECKING", "ANSIBLE_SSH_ARGS", "ANSIBLE_SSH_COMMON_ARGS", "ANSIBLE_SSH_EXTRA_ARGS", "ANSIBLE_SSH_HOST_KEY_CHECKING", "ANSIBLE_SCP_IF_SSH", "ANSIBLE_SCP_EXTRA_ARGS", "ANSIBLE_SFTP_EXTRA_ARGS")}),
        encoding="utf-8",
    )
output = next(value.split("=", 1)[1] for value in arguments if value.startswith("gpu_access_discovery_output_path="))
Path(output).write_text(os.environ["FAKE_ANSIBLE_EVIDENCE"], encoding="utf-8")
""",
        encoding="utf-8",
    )
    fake_ansible.chmod(0o755)
    record = tmp_path / "ansible-argv.json"
    monkeypatch.setenv("FAKE_ANSIBLE_RECORD", str(record))
    monkeypatch.setenv("FAKE_ANSIBLE_EVIDENCE", json.dumps(document))
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")
    return record


def test_generator_forces_repository_host_key_checking_over_disabled_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_fake_ansible(
        tmp_path, monkeypatch, {"version": 2, "hosts": [evidence_host("server"), evidence_host("agent")]}
    )
    environment_record = tmp_path / "ansible-environment.json"
    monkeypatch.setenv("FAKE_ANSIBLE_ENV_RECORD", str(environment_record))
    monkeypatch.setenv("ANSIBLE_CONFIG", str(tmp_path / "disabled-ansible.cfg"))
    monkeypatch.setenv("ANSIBLE_HOST_KEY_CHECKING", "False")
    monkeypatch.setenv("ANSIBLE_SSH_ARGS", "-o StrictHostKeyChecking=no")
    monkeypatch.setenv("ANSIBLE_SSH_COMMON_ARGS", "-o UserKnownHostsFile=/dev/null")
    monkeypatch.setenv("ANSIBLE_SSH_HOST_KEY_CHECKING", "False")
    monkeypatch.setenv("ANSIBLE_SSH_EXTRA_ARGS", "-o StrictHostKeyChecking=no")
    monkeypatch.setenv("ANSIBLE_SCP_IF_SSH", "True")
    monkeypatch.setenv("ANSIBLE_SCP_EXTRA_ARGS", "-o UserKnownHostsFile=/dev/null")
    monkeypatch.setenv("ANSIBLE_SFTP_EXTRA_ARGS", "-o StrictHostKeyChecking=no")
    spec_path = write_json(tmp_path / "spec.json", ssh_spec())

    result = run_generator(spec_path, tmp_path / "generated")

    assert result.returncode == 0, result.stderr
    assert json.loads(environment_record.read_text(encoding="utf-8")) == {
        "ANSIBLE_CONFIG": str(ROOT / "deploy" / "ansible" / "ansible.cfg"),
        "ANSIBLE_HOST_KEY_CHECKING": "True",
        "ANSIBLE_SSH_ARGS": "-o StrictHostKeyChecking=yes",
        "ANSIBLE_SSH_COMMON_ARGS": None,
        "ANSIBLE_SSH_EXTRA_ARGS": None,
        "ANSIBLE_SSH_HOST_KEY_CHECKING": "True",
        "ANSIBLE_SCP_IF_SSH": None,
        "ANSIBLE_SCP_EXTRA_ARGS": None,
        "ANSIBLE_SFTP_EXTRA_ARGS": None,
    }


def test_generator_surfaces_redacted_bounded_ansible_failure_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_ansible = fake_bin / "ansible-playbook"
    fake_ansible.write_text(
        "#!/bin/sh\nprintf '%s\\n' 'fatal: [server]: UNREACHABLE! token=do-not-disclose' >&2\nexit 2\n",
        encoding="utf-8",
    )
    fake_ansible.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")
    spec_path = write_json(tmp_path / "spec.json", ssh_spec())

    result = run_generator(spec_path, tmp_path / "generated")

    assert result.returncode == 1
    assert "exit code 2" in result.stderr
    assert "fatal: [server]: UNREACHABLE!" in result.stderr
    assert "do-not-disclose" not in result.stderr
    assert "token=<redacted>" in result.stderr


def run_generator(spec_path: Path, out_dir: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GEN_CONFIGS), "--spec", str(spec_path), "--out-dir", str(out_dir), *extra],
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )


def write_json(path: Path, document: dict) -> Path:
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_generator_discovers_mixed_ssh_targets_and_publishes_resolved_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = write_fake_ansible(
        tmp_path,
        monkeypatch,
        {"version": 2, "hosts": [evidence_host("server", gpu=True), evidence_host("agent")]},
    )
    spec_path = write_json(tmp_path / "spec.json", ssh_spec())
    out_dir = tmp_path / "generated"

    result = run_generator(spec_path, out_dir)

    assert result.returncode == 0, result.stderr
    inventory = (out_dir / "inventory.yml").read_text(encoding="utf-8")
    assert "auplc_render_gid: 993" in inventory
    assert inventory.count("auplc_gpu_access_enabled: true") == 1
    assert inventory.count("auplc_gpu_access_enabled: false") == 1
    assert "renderGid: 993" in (out_dir / "values-basic-example.yaml").read_text(encoding="utf-8")
    assert json.loads((out_dir / "gpu-access-resolution.json").read_text(encoding="utf-8")) == {
        "version": 1,
        "status": "gpu_resolved",
        "render_gid": 993,
        "hosts": {"agent": False, "server": True},
    }
    discovery_inventory = out_dir / ".gpu-access-discovery.inventory.yml"
    discovery_evidence = out_dir / ".gpu-access-discovery-evidence.json"
    assert discovery_inventory.stat().st_mode & 0o777 == 0o600
    assert discovery_evidence.stat().st_mode & 0o777 == 0o600
    assert json.loads(record.read_text(encoding="utf-8")) == [
        "-i",
        str(discovery_inventory),
        str(ROOT / "deploy" / "ansible" / "playbooks" / "pb-gpu-access-discovery.yml"),
        "-e",
        f"gpu_access_discovery_output_path={discovery_evidence}",
    ]


def test_generator_publishes_null_render_gid_for_all_cpu_ssh_targets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_fake_ansible(
        tmp_path,
        monkeypatch,
        {"version": 2, "hosts": [evidence_host("server"), evidence_host("agent")]},
    )
    spec_path = write_json(tmp_path / "spec.json", ssh_spec())
    out_dir = tmp_path / "generated"

    result = run_generator(spec_path, out_dir)

    assert result.returncode == 0, result.stderr
    inventory = (out_dir / "inventory.yml").read_text(encoding="utf-8")
    assert "auplc_render_gid: null" in inventory
    assert inventory.count("auplc_gpu_access_enabled: false") == 2
    assert "renderGid: null" in (out_dir / "values-basic-example.yaml").read_text(encoding="utf-8")
    manifest = json.loads((out_dir / "gpu-access-resolution.json").read_text(encoding="utf-8"))
    assert manifest == {
        "version": 1,
        "status": "cpu_only",
        "render_gid": None,
        "hosts": {"agent": False, "server": False},
    }


@pytest.mark.parametrize("failure", ["missing", "nonzero"])
def test_generator_does_not_publish_when_ansible_is_unavailable_or_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    spec_path = write_json(tmp_path / "spec.json", ssh_spec())
    out_dir = tmp_path / "generated"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    if failure == "nonzero":
        fake_ansible = fake_bin / "ansible-playbook"
        fake_ansible.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        fake_ansible.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake_bin))

    result = run_generator(spec_path, out_dir)

    assert result.returncode == 1
    assert not (out_dir / "inventory.yml").exists()
    assert not (out_dir / "values-basic-example.yaml").exists()
    assert not (out_dir / "gpu-access-resolution.json").exists()


@pytest.mark.parametrize(
    "document",
    [
        {"version": 2, "hosts": [evidence_host("server", reachable=False), evidence_host("agent")]},
        {
            "version": 2,
            "hosts": [evidence_host("server", gpu=True, gid=993), evidence_host("agent", gpu=True, gid=994)],
        },
    ],
    ids=["unknown", "gid-disagreement"],
)
def test_generator_keeps_canonical_artifacts_unchanged_when_discovery_blocks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, document: dict
) -> None:
    write_fake_ansible(tmp_path, monkeypatch, document)
    spec_path = write_json(tmp_path / "spec.json", ssh_spec())
    out_dir = tmp_path / "generated"
    out_dir.mkdir()
    inventory = out_dir / "inventory.yml"
    values = out_dir / "values-basic-example.yaml"
    manifest = out_dir / "gpu-access-resolution.json"
    inventory.write_text("previous inventory\n", encoding="utf-8")
    values.write_text("previous values\n", encoding="utf-8")
    manifest.write_text("previous manifest\n", encoding="utf-8")

    result = run_generator(spec_path, out_dir, "--force")

    assert result.returncode == 1
    assert inventory.read_text(encoding="utf-8") == "previous inventory\n"
    assert values.read_text(encoding="utf-8") == "previous values\n"
    assert manifest.read_text(encoding="utf-8") == "previous manifest\n"


@pytest.mark.parametrize(
    "field",
    ["render_gid", "gpu_access"],
)
def test_generator_rejects_removed_public_gpu_fields_before_running_discovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    record = write_fake_ansible(tmp_path, monkeypatch, {"version": 2, "hosts": []})
    spec = ssh_spec()
    spec[field] = 993 if field == "render_gid" else {"hosts": []}
    spec_path = write_json(tmp_path / "spec.json", spec)

    result = run_generator(spec_path, tmp_path / "generated")

    assert result.returncode == 1
    assert f"spec.{field} is no longer accepted" in result.stderr
    assert not record.exists()
