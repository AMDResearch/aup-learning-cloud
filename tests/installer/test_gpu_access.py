# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

"""Tests for the single-node AMD GPU access source of truth."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from auplc_installer import gpu_access
from auplc_installer.gpu_access import (
    GPU_ACCESS_RULES_PATH,
    GPU_ACCESS_STATE_PATH,
    LEGACY_AMDGPU_PXE_RULES,
    LEGACY_AMDGPU_RULES,
    LEGACY_AMDGPU_RULES_PATH,
    LEGACY_KFD_RULES,
    LEGACY_KFD_RULES_PATH,
    LEGACY_ROCM_DEVICES_RULES,
    LEGACY_ROCM_DEVICES_RULES_PATH,
    MAX_RENDER_GID,
    GpuAccessState,
    SystemGpuAccessHost,
    load_existing_gpu_access,
    parse_gpu_access_state,
    provision_gpu_access,
    render_udev_rules,
    resolve_render_gid,
    serialize_gpu_access_state,
)
from auplc_installer.util import InstallerError


class FakeGpuAccessHost:
    """In-memory adapter for the installer host-operation seam."""

    def __init__(self, *, getent_output: str, files: dict[Path, str] | None = None) -> None:
        self.getent_output = getent_output
        self.files = dict(files or {})
        self.calls: list[str] = []
        self.symlinks: set[Path] = set()
        self.nonregular_files: set[Path] = set()
        self.directories = {
            Path("/"),
            Path("/etc"),
            Path("/etc/udev"),
            Path("/etc/udev/rules.d"),
            Path("/var"),
            Path("/var/lib"),
            Path("/var/lib/auplc"),
        }

    def get_group_entry(self, group_name: str) -> str:
        self.calls.append(f"get-group:{group_name}")
        return self.getent_output

    def read_text(self, path: Path) -> str | None:
        self.calls.append(f"read:{path}")
        return self.files.get(path)

    def write_state_atomically(self, path: Path, text: str) -> None:
        self.calls.append(f"write-state:{path}")
        self.files[path] = text

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

    def verify_device_access(self, render_gid: int) -> None:
        self.calls.append(f"verify-devices:{render_gid}")

    def is_symlink(self, path: Path) -> bool:
        return path in self.symlinks

    def is_regular_file(self, path: Path) -> bool:
        return path in self.files

    def path_exists(self, path: Path) -> bool:
        return path in self.files or path in self.symlinks or path in self.nonregular_files or path in self.directories

    def is_directory(self, path: Path) -> bool:
        return path in self.directories


def test_gpu_access_state_round_trips_as_versioned_json() -> None:
    state = GpuAccessState(render_gid=993)

    serialized = serialize_gpu_access_state(state)

    assert serialized == '{"renderGid":993,"version":1}\n'
    assert parse_gpu_access_state(serialized) == state


@pytest.mark.parametrize(
    "state_text",
    [
        "not json",
        '{"renderGid":993,"version":2}',
        '{"renderGid":0,"version":1}',
        f'{{"renderGid":{MAX_RENDER_GID + 1},"version":1}}',
        '{"renderGid":true,"version":1}',
        '{"renderGid":993,"unexpected":true,"version":1}',
    ],
)
def test_parse_gpu_access_state_rejects_malformed_or_unsupported_state(state_text: str) -> None:
    with pytest.raises(RuntimeError):
        parse_gpu_access_state(state_text)


def test_resolve_render_gid_reads_the_numeric_getent_field() -> None:
    assert resolve_render_gid("render:x:993:student\n") == 993


@pytest.mark.parametrize(
    "getent_output",
    [
        "",
        "video:x:44:student\n",
        "render:x:0:student\n",
        "render:x:not-a-number:student\n",
        f"render:x:{MAX_RENDER_GID + 1}:student\n",
        "render:x:993:student\nrender:x:994:student\n",
    ],
)
def test_resolve_render_gid_rejects_missing_or_invalid_group_records(getent_output: str) -> None:
    with pytest.raises(RuntimeError):
        resolve_render_gid(getent_output)


def test_render_udev_rules_is_the_canonical_least_privilege_policy() -> None:
    rules = render_udev_rules()

    assert rules == (
        "# Managed by auplc-installer: AMD GPU device access.\n"
        'KERNEL=="kfd", OWNER="root", GROUP="render", MODE="0660"\n'
        'SUBSYSTEM=="drm", KERNEL=="renderD*", DRIVERS=="amdgpu", OWNER="root", GROUP="render", MODE="0660"\n'
    )
    assert "card" not in rules
    assert "0666" not in rules
    assert "chmod" not in rules


def test_device_verification_uses_lstat_and_requires_character_devices() -> None:
    assert "path.lstat()" in gpu_access._VERIFY_DEVICE_ACCESS_SCRIPT
    assert "stat.S_ISCHR(data.st_mode)" in gpu_access._VERIFY_DEVICE_ACCESS_SCRIPT


@pytest.mark.parametrize("unsafe_parent", [Path("/etc/udev"), Path("/etc/udev/rules.d"), Path("/var/lib/auplc")])
def test_symlinked_gpu_access_parent_fails_before_any_file_read_or_write(unsafe_parent: Path) -> None:
    host = FakeGpuAccessHost(getent_output="render:x:993:student\n")
    host.symlinks.add(unsafe_parent)

    with pytest.raises(InstallerError, match="symlinked GPU access directory"):
        provision_gpu_access(host)

    assert not any(call.startswith(("read:", "write-", "remove-rule:")) for call in host.calls)


def test_nonregular_canonical_rule_fails_before_reading_or_writing_it() -> None:
    host = FakeGpuAccessHost(getent_output="render:x:993:student\n")
    host.nonregular_files.add(GPU_ACCESS_RULES_PATH)

    with pytest.raises(InstallerError, match="non-regular GPU access file"):
        provision_gpu_access(host)

    assert f"read:{GPU_ACCESS_RULES_PATH}" not in host.calls
    assert f"write-rule:{GPU_ACCESS_RULES_PATH}" not in host.calls


def test_provision_adopts_host_render_gid_and_installs_canonical_rule() -> None:
    host = FakeGpuAccessHost(getent_output="render:x:993:student\n")

    state = provision_gpu_access(host)

    assert state == GpuAccessState(render_gid=993)
    assert host.files[GPU_ACCESS_STATE_PATH] == '{"renderGid":993,"version":1}\n'
    assert host.files[GPU_ACCESS_RULES_PATH] == render_udev_rules()
    assert host.calls[-4:] == [
        "trigger-udev",
        "settle-udev",
        "verify-devices:993",
        f"write-state:{GPU_ACCESS_STATE_PATH}",
    ]


def test_provision_migrates_exact_legacy_rules_then_verifies_before_persisting_state() -> None:
    host = FakeGpuAccessHost(
        getent_output="render:x:993:student\n",
        files={
            LEGACY_KFD_RULES_PATH: ('KERNEL=="kfd", MODE="0666"\nSUBSYSTEM=="drm", KERNEL=="renderD*", MODE="0666"\n'),
            LEGACY_AMDGPU_RULES_PATH: (
                "# ROCm device permissions\n"
                "# Grant render group access to AMD GPU devices\n"
                "# Reference: https://rocm.docs.amd.com/projects/install-on-linux/en/latest/install/prerequisites.html#using-udev-rules\n"
                'KERNEL=="kfd", GROUP="render", MODE="0660"\n'
                'SUBSYSTEM=="drm", KERNEL=="renderD*", GROUP="render", MODE="0660"\n'
            ),
        },
    )

    state = provision_gpu_access(host)

    assert state == GpuAccessState(render_gid=993)
    assert LEGACY_KFD_RULES == ('KERNEL=="kfd", MODE="0666"\nSUBSYSTEM=="drm", KERNEL=="renderD*", MODE="0666"\n')
    assert LEGACY_AMDGPU_RULES == (
        "# ROCm device permissions\n"
        "# Grant render group access to AMD GPU devices\n"
        "# Reference: https://rocm.docs.amd.com/projects/install-on-linux/en/latest/install/prerequisites.html#using-udev-rules\n"
        'KERNEL=="kfd", GROUP="render", MODE="0660"\n'
        'SUBSYSTEM=="drm", KERNEL=="renderD*", GROUP="render", MODE="0660"\n'
    )
    assert LEGACY_KFD_RULES_PATH not in host.files
    assert LEGACY_AMDGPU_RULES_PATH not in host.files
    assert host.calls.index(f"remove-rule:{LEGACY_KFD_RULES_PATH}") < host.calls.index(
        f"write-rule:{GPU_ACCESS_RULES_PATH}"
    )
    assert host.calls[-3:] == ["settle-udev", "verify-devices:993", f"write-state:{GPU_ACCESS_STATE_PATH}"]


def test_provision_migrates_exact_legacy_rocm_devices_rule() -> None:
    host = FakeGpuAccessHost(
        getent_output="render:x:993:student\n",
        files={
            LEGACY_ROCM_DEVICES_RULES_PATH: (
                "# ROCm device permissions\n"
                "# Ensure /dev/kfd and /dev/dri/renderD* are accessible by render group\n"
                'SUBSYSTEM=="kfd", GROUP="render", MODE="0660"\n'
                'SUBSYSTEM=="drm", KERNEL=="renderD*", GROUP="render", MODE="0660"\n'
            ),
        },
    )

    state = provision_gpu_access(host)

    assert state == GpuAccessState(render_gid=993)
    assert LEGACY_ROCM_DEVICES_RULES == (
        "# ROCm device permissions\n"
        "# Ensure /dev/kfd and /dev/dri/renderD* are accessible by render group\n"
        'SUBSYSTEM=="kfd", GROUP="render", MODE="0660"\n'
        'SUBSYSTEM=="drm", KERNEL=="renderD*", GROUP="render", MODE="0660"\n'
    )
    assert LEGACY_ROCM_DEVICES_RULES_PATH not in host.files


def test_provision_migrates_exact_legacy_pxe_rule_at_amdgpu_path() -> None:
    host = FakeGpuAccessHost(
        getent_output="render:x:993:student\n",
        files={
            LEGACY_AMDGPU_RULES_PATH: ('KERNEL=="kfd", MODE="0666"\nKERNEL=="renderD[0-9]*", MODE="0666"\n'),
        },
    )

    state = provision_gpu_access(host)

    assert state == GpuAccessState(render_gid=993)
    assert LEGACY_AMDGPU_PXE_RULES == ('KERNEL=="kfd", MODE="0666"\nKERNEL=="renderD[0-9]*", MODE="0666"\n')
    assert LEGACY_AMDGPU_RULES_PATH not in host.files


def test_near_legacy_pxe_rule_fails_closed_without_removal() -> None:
    near_variant = 'KERNEL=="kfd", MODE="0666"\nKERNEL=="renderD*", MODE="0666"\n'
    host = FakeGpuAccessHost(getent_output="render:x:993:student\n", files={LEGACY_AMDGPU_RULES_PATH: near_variant})

    with pytest.raises(InstallerError, match="unexpected legacy"):
        provision_gpu_access(host)

    assert host.files[LEGACY_AMDGPU_RULES_PATH] == near_variant


def test_modified_legacy_rocm_devices_rule_fails_closed_without_removal() -> None:
    modified = (
        "# ROCm device permissions\n"
        "# Ensure /dev/kfd and /dev/dri/renderD* are accessible by render group\n"
        'SUBSYSTEM=="kfd", GROUP="render", MODE="0666"\n'
        'SUBSYSTEM=="drm", KERNEL=="renderD*", GROUP="render", MODE="0660"\n'
    )
    host = FakeGpuAccessHost(getent_output="render:x:993:student\n", files={LEGACY_ROCM_DEVICES_RULES_PATH: modified})

    with pytest.raises(InstallerError, match="unexpected legacy"):
        provision_gpu_access(host)

    assert host.files[LEGACY_ROCM_DEVICES_RULES_PATH] == modified


def test_provision_reapplies_and_verifies_matching_immutable_state() -> None:
    host = FakeGpuAccessHost(
        getent_output="render:x:993:student\n",
        files={
            GPU_ACCESS_STATE_PATH: '{"renderGid":993,"version":1}\n',
            GPU_ACCESS_RULES_PATH: render_udev_rules(),
        },
    )

    state = provision_gpu_access(host)

    assert state == GpuAccessState(render_gid=993)
    assert not any(call.startswith("write-") for call in host.calls)
    assert host.calls[-4:] == ["reload-udev", "trigger-udev", "settle-udev", "verify-devices:993"]


def test_provision_fails_before_mutation_when_persisted_gid_differs_from_host() -> None:
    host = FakeGpuAccessHost(
        getent_output="render:x:994:student\n",
        files={GPU_ACCESS_STATE_PATH: '{"renderGid":993,"version":1}\n'},
    )

    with pytest.raises(RuntimeError, match="does not match"):
        provision_gpu_access(host)

    assert not any(call.startswith("write-") for call in host.calls)
    assert "reload-udev" not in host.calls
    assert "trigger-udev" not in host.calls


def test_provision_fails_before_writing_state_when_rule_is_unmanaged() -> None:
    host = FakeGpuAccessHost(
        getent_output="render:x:993:student\n",
        files={GPU_ACCESS_RULES_PATH: 'KERNEL=="kfd", MODE="0666"\n'},
    )

    with pytest.raises(RuntimeError, match="unmanaged"):
        provision_gpu_access(host)

    assert GPU_ACCESS_STATE_PATH not in host.files
    assert not any(call.startswith("write-") for call in host.calls)


def test_load_existing_gpu_access_adopts_missing_state_after_verification() -> None:
    host = FakeGpuAccessHost(getent_output="render:x:993:student\n")

    state = load_existing_gpu_access(host)

    assert state == GpuAccessState(render_gid=993)
    assert host.files[GPU_ACCESS_STATE_PATH] == '{"renderGid":993,"version":1}\n'
    assert host.calls[-3:] == ["settle-udev", "verify-devices:993", f"write-state:{GPU_ACCESS_STATE_PATH}"]


def test_managed_rule_is_reconciled_and_reloaded_when_content_changes() -> None:
    host = FakeGpuAccessHost(
        getent_output="render:x:993:student\n",
        files={
            GPU_ACCESS_STATE_PATH: '{"renderGid":993,"version":1}\n',
            GPU_ACCESS_RULES_PATH: "# Managed by auplc-installer: AMD GPU device access.\nold rule\n",
        },
    )

    state = load_existing_gpu_access(host)

    assert state == GpuAccessState(render_gid=993)
    assert host.files[GPU_ACCESS_RULES_PATH] == render_udev_rules()
    assert host.calls[-5:] == [
        f"write-rule:{GPU_ACCESS_RULES_PATH}",
        "reload-udev",
        "trigger-udev",
        "settle-udev",
        "verify-devices:993",
    ]


def test_system_adapter_persists_state_with_a_same_directory_temporary_file(monkeypatch) -> None:
    commands: list[list[str]] = []
    capture_commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        commands.append(command)
        if command[:2] == ["test", "-L"]:
            return SimpleNamespace(returncode=1)
        return SimpleNamespace(returncode=0)

    def fake_run_capture(command: list[str], **kwargs: object) -> SimpleNamespace:
        capture_commands.append(command)
        return SimpleNamespace(stdout="/var/lib/auplc/.gpu-access.json.temporary\n")

    monkeypatch.setattr(gpu_access, "run", fake_run)
    monkeypatch.setattr(gpu_access, "run_capture", fake_run_capture)

    SystemGpuAccessHost().write_state_atomically(GPU_ACCESS_STATE_PATH, "state\n")

    assert capture_commands == [["mktemp", "/var/lib/auplc/.gpu-access.json.XXXXXX"]]
    assert [command for command in commands if command[0] != "test"] == [
        ["mkdir", "-p", "/var/lib/auplc"],
        ["tee", "/var/lib/auplc/.gpu-access.json.temporary"],
        ["chmod", "0644", "/var/lib/auplc/.gpu-access.json.temporary"],
        ["python3", "-c", gpu_access._FSYNC_PATH_SCRIPT, "/var/lib/auplc/.gpu-access.json.temporary"],
        ["mv", "-f", "/var/lib/auplc/.gpu-access.json.temporary", "/var/lib/auplc/gpu-access.json"],
        ["python3", "-c", gpu_access._FSYNC_PATH_SCRIPT, "/var/lib/auplc"],
    ]


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


def test_system_adapter_removes_temporary_file_when_durable_write_fails(monkeypatch) -> None:
    commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        commands.append(command)
        if command[:2] == ["test", "-L"]:
            return SimpleNamespace(returncode=1)
        if command == ["python3", "-c", gpu_access._FSYNC_PATH_SCRIPT, "/var/lib/auplc/.gpu-access.json.temporary"]:
            raise InstallerError("fsync failed")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(gpu_access, "run", fake_run)
    monkeypatch.setattr(
        gpu_access,
        "run_capture",
        lambda command, **kwargs: SimpleNamespace(stdout="/var/lib/auplc/.gpu-access.json.temporary\n"),
    )

    with pytest.raises(InstallerError, match="fsync failed"):
        SystemGpuAccessHost().write_state_atomically(GPU_ACCESS_STATE_PATH, "state\n")

    assert [command for command in commands if command[0] != "test"] == [
        ["mkdir", "-p", "/var/lib/auplc"],
        ["tee", "/var/lib/auplc/.gpu-access.json.temporary"],
        ["chmod", "0644", "/var/lib/auplc/.gpu-access.json.temporary"],
        ["python3", "-c", gpu_access._FSYNC_PATH_SCRIPT, "/var/lib/auplc/.gpu-access.json.temporary"],
        ["rm", "-f", "/var/lib/auplc/.gpu-access.json.temporary"],
    ]


@pytest.mark.parametrize(
    ("failing_method", "expected_calls"),
    [
        (
            "write_udev_rule",
            [
                "get-group:render",
                f"write-rule:{GPU_ACCESS_RULES_PATH}",
            ],
        ),
        (
            "reload_udev_rules",
            [
                "get-group:render",
                f"write-rule:{GPU_ACCESS_RULES_PATH}",
                "reload-udev",
            ],
        ),
        (
            "trigger_udev",
            [
                "get-group:render",
                f"write-rule:{GPU_ACCESS_RULES_PATH}",
                "reload-udev",
                "trigger-udev",
            ],
        ),
    ],
)
def test_first_install_does_not_persist_state_until_udev_reconciliation_succeeds(
    monkeypatch,
    failing_method: str,
    expected_calls: list[str],
) -> None:
    host = FakeGpuAccessHost(getent_output="render:x:993:student\n")
    original_method = getattr(host, failing_method)

    def fail_after_recording(*args: object) -> None:
        original_method(*args)
        raise InstallerError(f"{failing_method} failed")

    monkeypatch.setattr(host, failing_method, fail_after_recording)

    with pytest.raises(InstallerError, match=f"{failing_method} failed"):
        provision_gpu_access(host)

    assert host.calls[-len(expected_calls) :] == expected_calls
    assert GPU_ACCESS_STATE_PATH not in host.files


def test_failed_udev_reconciliation_never_rewrites_existing_state(monkeypatch) -> None:
    original_state = '{"renderGid":993,"version":1}\n'
    host = FakeGpuAccessHost(
        getent_output="render:x:993:student\n",
        files={
            GPU_ACCESS_STATE_PATH: original_state,
            GPU_ACCESS_RULES_PATH: "# Managed by auplc-installer: AMD GPU device access.\nold rule\n",
        },
    )

    def fail_reload() -> None:
        host.calls.append("reload-udev")
        raise InstallerError("reload failed")

    monkeypatch.setattr(host, "reload_udev_rules", fail_reload)

    with pytest.raises(InstallerError, match="reload failed"):
        provision_gpu_access(host)

    assert host.files[GPU_ACCESS_STATE_PATH] == original_state
    assert not any(call.startswith("write-state:") for call in host.calls)
    assert "trigger-udev" not in host.calls


def test_failed_reload_is_retried_and_only_persists_state_after_a_later_success(monkeypatch) -> None:
    host = FakeGpuAccessHost(getent_output="render:x:993:student\n")

    def fail_reload() -> None:
        host.calls.append("reload-udev")
        raise InstallerError("reload failed")

    monkeypatch.setattr(host, "reload_udev_rules", fail_reload)
    with pytest.raises(InstallerError, match="reload failed"):
        provision_gpu_access(host)
    assert GPU_ACCESS_STATE_PATH not in host.files

    monkeypatch.setattr(host, "reload_udev_rules", FakeGpuAccessHost.reload_udev_rules.__get__(host))
    state = provision_gpu_access(host)

    assert state == GpuAccessState(render_gid=993)
    assert host.calls[-2:] == ["verify-devices:993", f"write-state:{GPU_ACCESS_STATE_PATH}"]


def test_failed_settle_is_retried_and_only_persists_state_after_a_later_success(monkeypatch) -> None:
    host = FakeGpuAccessHost(getent_output="render:x:993:student\n")

    def fail_settle() -> None:
        host.calls.append("settle-udev")
        raise InstallerError("settle failed")

    monkeypatch.setattr(host, "settle_udev", fail_settle)
    with pytest.raises(InstallerError, match="settle failed"):
        provision_gpu_access(host)
    assert GPU_ACCESS_STATE_PATH not in host.files
    assert "verify-devices:993" not in host.calls

    monkeypatch.setattr(host, "settle_udev", FakeGpuAccessHost.settle_udev.__get__(host))
    state = provision_gpu_access(host)

    assert state == GpuAccessState(render_gid=993)
    assert host.calls[-3:] == ["settle-udev", "verify-devices:993", f"write-state:{GPU_ACCESS_STATE_PATH}"]


def test_failed_inode_verification_does_not_adopt_state(monkeypatch) -> None:
    host = FakeGpuAccessHost(getent_output="render:x:993:student\n")

    def fail_verification(render_gid: int) -> None:
        host.calls.append(f"verify-devices:{render_gid}")
        raise InstallerError("device ownership mismatch")

    monkeypatch.setattr(host, "verify_device_access", fail_verification)

    with pytest.raises(InstallerError, match="ownership mismatch"):
        provision_gpu_access(host)

    assert host.calls[-1] == "verify-devices:993"
    assert GPU_ACCESS_STATE_PATH not in host.files


@pytest.mark.parametrize("path", [LEGACY_KFD_RULES_PATH, LEGACY_AMDGPU_RULES_PATH, GPU_ACCESS_RULES_PATH])
def test_symlinked_gpu_access_files_fail_closed_before_mutation(path: Path) -> None:
    host = FakeGpuAccessHost(getent_output="render:x:993:student\n")
    host.symlinks.add(path)

    with pytest.raises(InstallerError, match="symlinked"):
        provision_gpu_access(host)

    assert GPU_ACCESS_STATE_PATH not in host.files


@pytest.mark.parametrize(
    ("path", "content"),
    [
        (LEGACY_KFD_RULES_PATH, 'KERNEL=="kfd", MODE="0666"\n'),
        (LEGACY_AMDGPU_RULES_PATH, 'KERNEL=="kfd", GROUP="render", MODE="0660"\n'),
    ],
)
def test_one_line_legacy_variants_fail_closed_without_removal(path: Path, content: str) -> None:
    host = FakeGpuAccessHost(
        getent_output="render:x:993:student\n",
        files={path: content},
    )

    with pytest.raises(InstallerError, match="unexpected legacy"):
        provision_gpu_access(host)

    assert host.files[path] == content
    assert GPU_ACCESS_STATE_PATH not in host.files
