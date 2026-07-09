# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from auplc_installer import rocm


def _mock_rocm_commands(monkeypatch, exists: list[bool]):
    commands: list[list[str]] = []
    waits: list[list[str]] = []
    verifications: list[tuple[str, str]] = []
    removed: list[str] = []
    exists_iter = iter(exists)

    def fake_run(cmd, **kwargs):
        commands.append(list(cmd))
        return SimpleNamespace(returncode=0)

    def fake_wait(cmd, **kwargs):
        waits.append(list(cmd))
        return 0

    monkeypatch.setattr(rocm, "_exists_daemonset", lambda name: next(exists_iter))
    monkeypatch.setattr(rocm, "run", fake_run)
    monkeypatch.setattr(rocm, "run_streaming", fake_wait)
    monkeypatch.setattr(rocm, "verify_sha256", lambda path, expected: verifications.append((str(path), expected)))
    monkeypatch.setattr(rocm.os, "remove", lambda path: removed.append(path))

    return commands, waits, verifications, removed


def _patched_daemonsets(commands: list[list[str]]) -> list[str]:
    return [cmd[3] for cmd in commands if cmd[:3] == ["kubectl", "patch", "ds"]]


def test_image_pull_policy_patch_uses_add(monkeypatch) -> None:
    commands: list[list[str]] = []
    monkeypatch.setattr(rocm, "run", lambda cmd: commands.append(list(cmd)))

    rocm._patch_image_pull_policy("amdgpu-device-plugin-daemonset")

    assert commands == [
        [
            "kubectl",
            "patch",
            "ds",
            "amdgpu-device-plugin-daemonset",
            "-n",
            "kube-system",
            "--type=json",
            "-p",
            '[{"op":"add","path":"/spec/template/spec/containers/0/imagePullPolicy","value":"IfNotPresent"}]',
        ]
    ]


def test_existing_rocm_daemonsets_are_reconciled(monkeypatch) -> None:
    commands, waits, verifications, removed = _mock_rocm_commands(monkeypatch, [True, True])

    rocm.deploy_rocm_gpu_device_plugin(offline_mode=False, bundle_dir=None)

    assert not any(cmd[:3] == ["kubectl", "create", "-f"] for cmd in commands)
    assert not any(cmd and cmd[0] == "wget" for cmd in commands)
    assert _patched_daemonsets(commands) == [
        "amdgpu-device-plugin-daemonset",
        "amdgpu-labeller-daemonset",
    ]
    assert [cmd[-2] for cmd in waits] == [
        "ds/amdgpu-device-plugin-daemonset",
        "ds/amdgpu-labeller-daemonset",
    ]
    assert verifications == []
    assert removed == []


def test_online_rocm_daemonset_creation_is_reconciled(monkeypatch) -> None:
    commands, waits, verifications, removed = _mock_rocm_commands(monkeypatch, [False, False])

    rocm.deploy_rocm_gpu_device_plugin(offline_mode=False, bundle_dir=None)

    assert [cmd for cmd in commands if cmd and cmd[0] == "wget"] == [
        [
            "wget",
            f"https://raw.githubusercontent.com/ROCm/k8s-device-plugin/{rocm.ROCM_DEVICE_PLUGIN_COMMIT}/k8s-ds-amdgpu-dp.yaml",
            "-O",
            "/tmp/k8s-ds-amdgpu-dp.yaml",
        ],
        [
            "wget",
            f"https://raw.githubusercontent.com/ROCm/k8s-device-plugin/{rocm.ROCM_DEVICE_PLUGIN_COMMIT}/k8s-ds-amdgpu-labeller.yaml",
            "-O",
            "/tmp/k8s-ds-amdgpu-labeller.yaml",
        ],
    ]
    assert [cmd for cmd in commands if cmd[:3] == ["kubectl", "create", "-f"]] == [
        ["kubectl", "create", "-f", "/tmp/k8s-ds-amdgpu-dp.yaml"],
        ["kubectl", "create", "-f", "/tmp/k8s-ds-amdgpu-labeller.yaml"],
    ]
    assert _patched_daemonsets(commands) == [
        "amdgpu-device-plugin-daemonset",
        "amdgpu-labeller-daemonset",
    ]
    assert [cmd[-2] for cmd in waits] == [
        "ds/amdgpu-device-plugin-daemonset",
        "ds/amdgpu-labeller-daemonset",
    ]
    assert verifications == [
        ("/tmp/k8s-ds-amdgpu-dp.yaml", rocm.ROCM_DEVICE_PLUGIN_SHA256),
        ("/tmp/k8s-ds-amdgpu-labeller.yaml", rocm.ROCM_LABELLER_SHA256),
    ]
    assert removed == ["/tmp/k8s-ds-amdgpu-dp.yaml", "/tmp/k8s-ds-amdgpu-labeller.yaml"]


def test_offline_rocm_daemonset_creation_is_reconciled(monkeypatch, tmp_path: Path) -> None:
    commands, waits, verifications, removed = _mock_rocm_commands(monkeypatch, [False, False])

    rocm.deploy_rocm_gpu_device_plugin(offline_mode=True, bundle_dir=tmp_path)

    assert not any(cmd and cmd[0] == "wget" for cmd in commands)
    assert [cmd for cmd in commands if cmd[:3] == ["kubectl", "create", "-f"]] == [
        ["kubectl", "create", "-f", str(tmp_path / "manifests/k8s-ds-amdgpu-dp.yaml")],
        ["kubectl", "create", "-f", str(tmp_path / "manifests/k8s-ds-amdgpu-labeller.yaml")],
    ]
    assert _patched_daemonsets(commands) == [
        "amdgpu-device-plugin-daemonset",
        "amdgpu-labeller-daemonset",
    ]
    assert [cmd[-2] for cmd in waits] == [
        "ds/amdgpu-device-plugin-daemonset",
        "ds/amdgpu-labeller-daemonset",
    ]
    assert verifications == []
    assert removed == []
