# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from auplc_installer import gpu_access
from auplc_installer.gpu_access import (
    AMD_GPU_UDEV_PACKAGE_FILENAME,
    AMD_GPU_UDEV_PACKAGE_RULES,
    AMD_GPU_UDEV_PACKAGE_RULES_PATH,
    AMD_GPU_UDEV_PACKAGE_VERSION,
    LEGACY_KFD_RULES,
    LEGACY_KFD_RULES_PATH,
    provision_gpu_access,
)
from auplc_installer.util import InstallerError
from tests.installer.test_gpu_access import FakeGpuAccessHost


def _offline_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "bundle"
    deb = bundle / "packages" / AMD_GPU_UDEV_PACKAGE_FILENAME
    deb.parent.mkdir(parents=True)
    deb.write_bytes(b"package")
    return bundle


def test_wrong_installed_version_downloads_and_converges_to_the_pinned_package(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a different installed package version and an online downloader.
    host = FakeGpuAccessHost(
        files={AMD_GPU_UDEV_PACKAGE_RULES_PATH: 'KERNEL=="kfd", MODE="0660"\n'},
        installed_version="30.30.4.0-older",
    )
    downloads: list[list[str]] = []

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        downloads.append(command)
        Path(command[-1]).write_bytes(b"package")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(gpu_access, "run", fake_run)
    monkeypatch.setattr(gpu_access, "verify_sha256", lambda *args: None)

    # When: GPU access is provisioned.
    provision_gpu_access(host)

    # Then: the pinned deb is acquired and the installed rule converges to its exact content.
    assert downloads[0][2] == gpu_access.AMD_GPU_UDEV_PACKAGE_URL
    assert host.installed_version == AMD_GPU_UDEV_PACKAGE_VERSION
    assert host.files[AMD_GPU_UDEV_PACKAGE_RULES_PATH] == AMD_GPU_UDEV_PACKAGE_RULES


def test_exact_installed_package_skips_network_then_removes_separate_legacy_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: an exact package rule plus a separately shipped legacy KFD rule.
    host = FakeGpuAccessHost(
        files={
            AMD_GPU_UDEV_PACKAGE_RULES_PATH: AMD_GPU_UDEV_PACKAGE_RULES,
            LEGACY_KFD_RULES_PATH: LEGACY_KFD_RULES,
        },
        installed_version=AMD_GPU_UDEV_PACKAGE_VERSION,
    )
    monkeypatch.setattr(gpu_access, "run", lambda *args, **kwargs: pytest.fail("must not download"))

    # When: provisioning checks an otherwise already-correct installation.
    provision_gpu_access(host)

    # Then: it removes only the separate legacy file and applies its removal to live udev state.
    assert LEGACY_KFD_RULES_PATH not in host.files
    assert not any(call.startswith("install-package:") for call in host.calls)
    assert host.calls[-3:] == ["reload-udev", "trigger-udev", "settle-udev"]


def test_acquires_and_verifies_the_offline_deb_before_deleting_legacy_rules(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: a first installation from a verified offline bundle and a legacy KFD rule.
    bundle = _offline_bundle(tmp_path)
    host = FakeGpuAccessHost(files={LEGACY_KFD_RULES_PATH: LEGACY_KFD_RULES})
    monkeypatch.setattr(gpu_access, "verify_sha256", lambda *args: host.calls.append("verify-deb"))

    # When: the package is installed.
    provision_gpu_access(host, offline_mode=True, bundle_dir=bundle)

    # Then: package installation completes before the separate legacy rule is deleted.
    install_index = next(index for index, call in enumerate(host.calls) if call.startswith("install-package:"))
    removal_index = host.calls.index(f"remove-rule:{LEGACY_KFD_RULES_PATH}")
    assert host.calls.index("verify-deb") < install_index < removal_index


def test_failed_installation_keeps_legacy_rules_intact(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Given: a first offline installation whose package install fails.
    bundle = _offline_bundle(tmp_path)
    host = FakeGpuAccessHost(files={LEGACY_KFD_RULES_PATH: LEGACY_KFD_RULES})
    monkeypatch.setattr(gpu_access, "verify_sha256", lambda *args: None)

    def fail_install(deb: Path) -> None:
        host.calls.append(f"install-package:{deb}")
        raise InstallerError("dpkg failed")

    monkeypatch.setattr(host, "install_package", fail_install)

    # When: package installation fails.
    with pytest.raises(InstallerError, match="dpkg failed"):
        provision_gpu_access(host, offline_mode=True, bundle_dir=bundle)

    # Then: the legacy rule remains and no udev refresh occurs.
    assert host.files[LEGACY_KFD_RULES_PATH] == LEGACY_KFD_RULES
    assert "reload-udev" not in host.calls


@pytest.mark.parametrize("installed_version", ["30.30.4.0-older", None])
def test_package_owned_differing_conffile_converges(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, installed_version: str | None
) -> None:
    # Given: a wrong-version or partial package state that owns a differing conffile.
    host = FakeGpuAccessHost(
        files={AMD_GPU_UDEV_PACKAGE_RULES_PATH: 'KERNEL=="kfd", MODE="0600"\n'},
        installed_version=installed_version,
        package_owns_rule=True,
    )
    monkeypatch.setattr(gpu_access, "verify_sha256", lambda *args: None)

    # When: the pinned package is installed from an offline bundle.
    provision_gpu_access(host, offline_mode=True, bundle_dir=_offline_bundle(tmp_path))

    # Then: forced installation converges to the exact package rule without legacy deletion.
    assert host.files[AMD_GPU_UDEV_PACKAGE_RULES_PATH] == AMD_GPU_UDEV_PACKAGE_RULES
    assert not any(call.startswith("remove-rule:") for call in host.calls)


def test_unknown_unowned_amdgpu_rule_fails_closed() -> None:
    # Given: an unowned, unrecognized rule at the AMD package path.
    host = FakeGpuAccessHost(
        files={AMD_GPU_UDEV_PACKAGE_RULES_PATH: 'KERNEL=="kfd", MODE="0600"\n'},
        package_owns_rule=False,
    )

    # When: provisioning admits legacy rules.
    with pytest.raises(InstallerError, match="unexpected legacy"):
        provision_gpu_access(host)

    # Then: no package installation or rule deletion is attempted.
    assert not any(call.startswith(("install-package:", "remove-rule:")) for call in host.calls)
