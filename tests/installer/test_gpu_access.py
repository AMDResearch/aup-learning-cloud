# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

"""Tests for the single-node AMD GPU host device-access reconciler."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from auplc_installer import gpu_access
from auplc_installer.gpu_access import (
    GPU_ACCESS_RULES_PATH,
    LEGACY_AMDGPU_PXE_RULES,
    LEGACY_AMDGPU_RULES,
    LEGACY_AMDGPU_RULES_PATH,
    LEGACY_KFD_RULES,
    LEGACY_KFD_RULES_PATH,
    LEGACY_ROCM_DEVICES_RULES,
    LEGACY_ROCM_DEVICES_RULES_PATH,
    SystemGpuAccessHost,
    provision_gpu_access,
    render_udev_rules,
)
from auplc_installer.util import InstallerError


class FakeGpuAccessHost:
    """In-memory adapter for the installer host-operation seam."""

    def __init__(self, *, files: dict[Path, str] | None = None) -> None:
        self.files = dict(files or {})
        self.calls: list[str] = []
        self.symlinks: set[Path] = set()
        self.nonregular_files: set[Path] = set()
        self.directories = {Path("/"), Path("/etc"), Path("/etc/udev"), Path("/etc/udev/rules.d")}

    def read_text(self, path: Path) -> str | None:
        self.calls.append(f"read:{path}")
        return self.files.get(path)

    def write_udev_rule(self, path: Path, text: str) -> None:
        self.calls.append(f"write-rule:{path}")
        self.files[path] = text

    def remove_udev_rule(self, path: Path) -> None:
        self.calls.append(f"remove-rule:{path}")
        self.files.pop(path, None)

    def reload_udev_rules(self) -> None:
        self.calls.append("reload-udev")

    def trigger_udev(self) -> None:
        self.calls.append("trigger-udev")

    def settle_udev(self) -> None:
        self.calls.append("settle-udev")

    def verify_device_access(self) -> None:
        self.calls.append("verify-devices")

    def is_symlink(self, path: Path) -> bool:
        return path in self.symlinks

    def is_regular_file(self, path: Path) -> bool:
        return path in self.files

    def path_exists(self, path: Path) -> bool:
        return path in self.files or path in self.symlinks or path in self.nonregular_files or path in self.directories

    def is_directory(self, path: Path) -> bool:
        return path in self.directories


def test_render_udev_rules_is_the_canonical_host_device_policy() -> None:
    rules = render_udev_rules()

    assert rules == (
        "# Managed by auplc-installer: AMD GPU device access.\n"
        'KERNEL=="kfd", OWNER="root", GROUP="render", MODE="0666"\n'
        'SUBSYSTEM=="drm", KERNEL=="renderD*", DRIVERS=="amdgpu", OWNER="root", GROUP="render", MODE="0666"\n'
        'SUBSYSTEM=="drm", KERNEL=="card*", DRIVERS=="amdgpu", OWNER="root", GROUP="video", MODE="0666"\n'
    )
    assert "chmod" not in rules


def test_device_verification_checks_kfd_and_amd_render_and_card_nodes_without_a_render_gid() -> None:
    script = gpu_access._VERIFY_DEVICE_ACCESS_SCRIPT

    assert "path.lstat()" in script
    assert "stat.S_ISCHR(data.st_mode)" in script
    assert "glob('renderD*')" in script
    assert "glob('card*')" in script
    assert "'render', 0o666" in script
    assert "'video', 0o666" in script
    assert "render_gid" not in script
    assert "sys.argv[1]" not in script


@pytest.mark.parametrize("unsafe_parent", [Path("/etc/udev"), Path("/etc/udev/rules.d")])
def test_symlinked_gpu_access_parent_fails_before_any_file_read_or_write(unsafe_parent: Path) -> None:
    host = FakeGpuAccessHost()
    host.symlinks.add(unsafe_parent)

    with pytest.raises(InstallerError, match="symlinked GPU access directory"):
        provision_gpu_access(host)

    assert not any(call.startswith(("read:", "write-", "remove-rule:")) for call in host.calls)


def test_nonregular_canonical_rule_fails_before_reading_or_writing_it() -> None:
    host = FakeGpuAccessHost()
    host.nonregular_files.add(GPU_ACCESS_RULES_PATH)

    with pytest.raises(InstallerError, match="non-regular GPU access file"):
        provision_gpu_access(host)

    assert f"read:{GPU_ACCESS_RULES_PATH}" not in host.calls
    assert f"write-rule:{GPU_ACCESS_RULES_PATH}" not in host.calls


def test_provision_reconciles_the_canonical_rule_without_group_lookup_or_state() -> None:
    host = FakeGpuAccessHost()

    result = provision_gpu_access(host)

    assert result is None
    assert host.files == {GPU_ACCESS_RULES_PATH: render_udev_rules()}
    assert host.calls[-4:] == ["reload-udev", "trigger-udev", "settle-udev", "verify-devices"]
    assert not any("group" in call or "state" in call for call in host.calls)


@pytest.mark.parametrize(
    ("path", "content"),
    [
        (LEGACY_KFD_RULES_PATH, LEGACY_KFD_RULES),
        (LEGACY_AMDGPU_RULES_PATH, LEGACY_AMDGPU_RULES),
        (LEGACY_AMDGPU_RULES_PATH, LEGACY_AMDGPU_PXE_RULES),
        (LEGACY_ROCM_DEVICES_RULES_PATH, LEGACY_ROCM_DEVICES_RULES),
    ],
)
def test_provision_removes_only_exact_legacy_rules_before_verifying(path: Path, content: str) -> None:
    host = FakeGpuAccessHost(files={path: content})

    provision_gpu_access(host)

    assert path not in host.files
    assert host.files[GPU_ACCESS_RULES_PATH] == render_udev_rules()
    assert host.calls.index(f"remove-rule:{path}") < host.calls.index(f"write-rule:{GPU_ACCESS_RULES_PATH}")
    assert host.calls[-4:] == ["reload-udev", "trigger-udev", "settle-udev", "verify-devices"]


@pytest.mark.parametrize(
    ("path", "content"),
    [
        (LEGACY_AMDGPU_RULES_PATH, 'KERNEL=="kfd", MODE="0666"\nKERNEL=="renderD*", MODE="0666"\n'),
        (
            LEGACY_ROCM_DEVICES_RULES_PATH,
            "# ROCm device permissions\n"
            "# Ensure /dev/kfd and /dev/dri/renderD* are accessible by render group\n"
            'SUBSYSTEM=="kfd", GROUP="render", MODE="0666"\n'
            'SUBSYSTEM=="drm", KERNEL=="renderD*", GROUP="render", MODE="0660"\n',
        ),
    ],
)
def test_near_legacy_rule_fails_closed_without_removal(path: Path, content: str) -> None:
    host = FakeGpuAccessHost(files={path: content})

    with pytest.raises(InstallerError, match="unexpected legacy"):
        provision_gpu_access(host)

    assert host.files[path] == content


def test_matching_managed_rule_is_reapplied_and_verified_without_rewriting() -> None:
    host = FakeGpuAccessHost(files={GPU_ACCESS_RULES_PATH: render_udev_rules()})

    provision_gpu_access(host)

    assert not any(call.startswith("write-") for call in host.calls)
    assert host.calls[-4:] == ["reload-udev", "trigger-udev", "settle-udev", "verify-devices"]


@pytest.mark.parametrize(
    "unexpected_rule",
    [
        f"{gpu_access.UDEV_MANAGED_MARKER}\n"
        'KERNEL=="kfd", OWNER="root", GROUP="render", MODE="0660"\n'
        'SUBSYSTEM=="drm", KERNEL=="renderD*", DRIVERS=="amdgpu", OWNER="root", GROUP="render", MODE="0660"\n',
        f'{gpu_access.UDEV_MANAGED_MARKER}\nKERNEL=="kfd", MODE="0666"\n',
    ],
)
def test_noncanonical_managed_rule_fails_closed_before_mutation(unexpected_rule: str) -> None:
    host = FakeGpuAccessHost(files={GPU_ACCESS_RULES_PATH: unexpected_rule})

    with pytest.raises(InstallerError, match="unrecognized managed"):
        provision_gpu_access(host)

    assert host.files[GPU_ACCESS_RULES_PATH] == unexpected_rule
    assert not any(call.startswith(("write-", "remove-rule:")) for call in host.calls)
    assert "reload-udev" not in host.calls


def test_unmanaged_rule_fails_before_any_mutation() -> None:
    host = FakeGpuAccessHost(files={GPU_ACCESS_RULES_PATH: 'KERNEL=="kfd", MODE="0666"\n'})

    with pytest.raises(InstallerError, match="unmanaged"):
        provision_gpu_access(host)

    assert not any(call.startswith(("write-", "remove-rule:")) for call in host.calls)
    assert "reload-udev" not in host.calls


def test_system_adapter_persists_udev_rule_with_durable_atomic_replacement(monkeypatch) -> None:
    commands: list[list[str]] = []
    capture_commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        commands.append(command)
        if command[:2] == ["test", "-L"]:
            return SimpleNamespace(returncode=1)
        return SimpleNamespace(returncode=0)

    def fake_run_capture(command: list[str], **kwargs: object) -> SimpleNamespace:
        capture_commands.append(command)
        return SimpleNamespace(stdout="/etc/udev/rules.d/.70-auplc-gpu-access.rules.temporary\n")

    monkeypatch.setattr(gpu_access, "run", fake_run)
    monkeypatch.setattr(gpu_access, "run_capture", fake_run_capture)

    SystemGpuAccessHost().write_udev_rule(GPU_ACCESS_RULES_PATH, "rule\n")

    assert capture_commands == [["mktemp", "/etc/udev/rules.d/.70-auplc-gpu-access.rules.XXXXXX"]]
    assert [command for command in commands if command[0] != "test"] == [
        ["mkdir", "-p", "/etc/udev/rules.d"],
        ["tee", "/etc/udev/rules.d/.70-auplc-gpu-access.rules.temporary"],
        ["chmod", "0644", "/etc/udev/rules.d/.70-auplc-gpu-access.rules.temporary"],
        ["python3", "-c", gpu_access._FSYNC_PATH_SCRIPT, "/etc/udev/rules.d/.70-auplc-gpu-access.rules.temporary"],
        [
            "mv",
            "-f",
            "/etc/udev/rules.d/.70-auplc-gpu-access.rules.temporary",
            "/etc/udev/rules.d/70-auplc-gpu-access.rules",
        ],
        ["python3", "-c", gpu_access._FSYNC_PATH_SCRIPT, "/etc/udev/rules.d"],
    ]


def test_system_adapter_removes_temporary_rule_when_durable_write_fails(monkeypatch) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        commands.append(command)
        if command[:2] == ["test", "-L"]:
            return SimpleNamespace(returncode=1)
        if command == [
            "python3",
            "-c",
            gpu_access._FSYNC_PATH_SCRIPT,
            "/etc/udev/rules.d/.70-auplc-gpu-access.rules.temporary",
        ]:
            raise InstallerError("fsync failed")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(gpu_access, "run", fake_run)
    monkeypatch.setattr(
        gpu_access,
        "run_capture",
        lambda command, **kwargs: SimpleNamespace(stdout="/etc/udev/rules.d/.70-auplc-gpu-access.rules.temporary\n"),
    )

    with pytest.raises(InstallerError, match="fsync failed"):
        SystemGpuAccessHost().write_udev_rule(GPU_ACCESS_RULES_PATH, "rule\n")

    assert [command for command in commands if command[0] != "test"] == [
        ["mkdir", "-p", "/etc/udev/rules.d"],
        ["tee", "/etc/udev/rules.d/.70-auplc-gpu-access.rules.temporary"],
        ["chmod", "0644", "/etc/udev/rules.d/.70-auplc-gpu-access.rules.temporary"],
        ["python3", "-c", gpu_access._FSYNC_PATH_SCRIPT, "/etc/udev/rules.d/.70-auplc-gpu-access.rules.temporary"],
        ["rm", "-f", "/etc/udev/rules.d/.70-auplc-gpu-access.rules.temporary"],
    ]


@pytest.mark.parametrize("failing_method", ["write_udev_rule", "reload_udev_rules", "trigger_udev", "settle_udev"])
def test_reconciliation_stops_when_udev_mutation_fails(monkeypatch, failing_method: str) -> None:
    host = FakeGpuAccessHost()
    original_method = getattr(host, failing_method)

    def fail_after_recording(*args: object) -> None:
        original_method(*args)
        raise InstallerError(f"{failing_method} failed")

    monkeypatch.setattr(host, failing_method, fail_after_recording)

    with pytest.raises(InstallerError, match=f"{failing_method} failed"):
        provision_gpu_access(host)

    assert "verify-devices" not in host.calls


def test_failed_inode_verification_leaves_the_reconciled_rule_in_place(monkeypatch) -> None:
    host = FakeGpuAccessHost()

    def fail_verification() -> None:
        host.calls.append("verify-devices")
        raise InstallerError("device ownership mismatch")

    monkeypatch.setattr(host, "verify_device_access", fail_verification)

    with pytest.raises(InstallerError, match="ownership mismatch"):
        provision_gpu_access(host)

    assert host.files[GPU_ACCESS_RULES_PATH] == render_udev_rules()
    assert host.calls[-1] == "verify-devices"


@pytest.mark.parametrize("path", [LEGACY_KFD_RULES_PATH, LEGACY_AMDGPU_RULES_PATH, GPU_ACCESS_RULES_PATH])
def test_symlinked_gpu_access_files_fail_closed_before_mutation(path: Path) -> None:
    host = FakeGpuAccessHost()
    host.symlinks.add(path)

    with pytest.raises(InstallerError, match="symlinked"):
        provision_gpu_access(host)

    assert not any(call.startswith(("write-", "remove-rule:")) for call in host.calls)
