# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

"""Tests for AMD's packaged single-node GPU udev policy."""

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
    LEGACY_AMDGPU_RULES,
    LEGACY_AMDGPU_RULES_PATH,
    SystemGpuAccessHost,
    provision_gpu_access,
)
from auplc_installer.util import InstallerError


class FakeGpuAccessHost:
    def __init__(
        self,
        *,
        files: dict[Path, str] | None = None,
        installed_version: str | None = None,
        package_owns_rule: bool | None = None,
    ) -> None:
        self.files = dict(files or {})
        self.installed_version = installed_version
        self._package_owns_rule = installed_version is not None if package_owns_rule is None else package_owns_rule
        self.calls: list[str] = []
        self.symlinks: set[Path] = set()
        self.nonregular_files: set[Path] = set()
        self.directories = {Path("/"), Path("/etc"), Path("/etc/udev"), Path("/etc/udev/rules.d")}

    def read_text(self, path: Path) -> str | None:
        self.calls.append(f"read:{path}")
        return self.files.get(path)

    def remove_udev_rule(self, path: Path) -> None:
        self.calls.append(f"remove-rule:{path}")
        self.files.pop(path, None)

    def installed_package_version(self) -> str | None:
        self.calls.append("installed-version")
        return self.installed_version

    def package_owns_rule(self, path: Path) -> bool:
        self.calls.append(f"owns-rule:{path}")
        return self._package_owns_rule

    def install_package(self, deb: Path) -> None:
        self.calls.append(f"install-package:{deb}")
        self.installed_version = AMD_GPU_UDEV_PACKAGE_VERSION
        self._package_owns_rule = True
        self.files[AMD_GPU_UDEV_PACKAGE_RULES_PATH] = AMD_GPU_UDEV_PACKAGE_RULES

    def reload_udev_rules(self) -> None:
        self.calls.append("reload-udev")

    def trigger_udev(self) -> None:
        self.calls.append("trigger-udev")

    def settle_udev(self) -> None:
        self.calls.append("settle-udev")

    def is_symlink(self, path: Path) -> bool:
        return path in self.symlinks

    def is_regular_file(self, path: Path) -> bool:
        return path in self.files

    def path_exists(self, path: Path) -> bool:
        return path in self.files or path in self.symlinks or path in self.nonregular_files or path in self.directories

    def is_directory(self, path: Path) -> bool:
        return path in self.directories


def test_offline_install_replaces_legacy_rule_at_the_package_owned_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: an offline bundle and a legacy rule from an earlier shipped installer.
    bundle = tmp_path / "bundle"
    deb = bundle / "packages" / AMD_GPU_UDEV_PACKAGE_FILENAME
    deb.parent.mkdir(parents=True)
    deb.write_bytes(b"package")
    host = FakeGpuAccessHost(files={LEGACY_AMDGPU_RULES_PATH: LEGACY_AMDGPU_RULES})
    verified: list[tuple[Path, str]] = []
    monkeypatch.setattr(gpu_access, "verify_sha256", lambda path, checksum: verified.append((Path(path), checksum)))

    # When: GPU access is provisioned from the bundle.
    provision_gpu_access(host, offline_mode=True, bundle_dir=bundle)

    # Then: package installation replaces the path without deleting the package-owned rule afterward.
    assert not any(call == f"remove-rule:{LEGACY_AMDGPU_RULES_PATH}" for call in host.calls)
    assert host.files == {AMD_GPU_UDEV_PACKAGE_RULES_PATH: AMD_GPU_UDEV_PACKAGE_RULES}
    assert verified == [(deb, gpu_access.AMD_GPU_UDEV_PACKAGE_SHA256)]


def test_online_install_downloads_to_a_temporary_deb_then_removes_it(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: no installed package and a downloader that materializes its destination.
    host = FakeGpuAccessHost()
    downloads: list[list[str]] = []
    verified: list[Path] = []

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        downloads.append(command)
        Path(command[-1]).write_bytes(b"package")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(gpu_access, "run", fake_run)
    monkeypatch.setattr(gpu_access, "verify_sha256", lambda path, _: verified.append(Path(path)))

    # When: GPU access is provisioned online.
    provision_gpu_access(host, offline_mode=False, bundle_dir=None)

    # Then: the exact Radeon URL is downloaded, verified, installed, and cleaned up.
    downloaded_path = Path(downloads[0][-1])
    assert downloads[0][2] == gpu_access.AMD_GPU_UDEV_PACKAGE_URL
    assert verified == [downloaded_path]
    assert not downloaded_path.exists()
    assert host.installed_version == AMD_GPU_UDEV_PACKAGE_VERSION
    assert host.files[AMD_GPU_UDEV_PACKAGE_RULES_PATH] == AMD_GPU_UDEV_PACKAGE_RULES


def test_installed_package_requires_the_pinned_version_and_its_exact_rule() -> None:
    # Given: the package is already present with the expected package-owned rule.
    host = FakeGpuAccessHost(
        files={AMD_GPU_UDEV_PACKAGE_RULES_PATH: AMD_GPU_UDEV_PACKAGE_RULES},
        installed_version=AMD_GPU_UDEV_PACKAGE_VERSION,
    )

    # When: provisioning is repeated.
    provision_gpu_access(host)

    # Then: no download, install, legacy removal, or device probe is performed.
    assert not any(call.startswith(("install-package:", "remove-rule:")) for call in host.calls)
    assert not any(call in {"reload-udev", "trigger-udev", "settle-udev"} for call in host.calls)


@pytest.mark.parametrize(
    ("installed_version", "package_owns_rule", "rule"),
    [
        (AMD_GPU_UDEV_PACKAGE_VERSION, False, AMD_GPU_UDEV_PACKAGE_RULES),
        (AMD_GPU_UDEV_PACKAGE_VERSION, True, 'KERNEL=="kfd", MODE="0660"\n'),
    ],
)
def test_installed_package_fails_closed_when_its_version_or_rule_contract_is_wrong(
    installed_version: str, package_owns_rule: bool, rule: str
) -> None:
    # Given: an installed package that does not satisfy the pinned package contract.
    host = FakeGpuAccessHost(
        files={AMD_GPU_UDEV_PACKAGE_RULES_PATH: rule},
        installed_version=installed_version,
        package_owns_rule=package_owns_rule,
    )

    # When: provisioning checks the installed package.
    with pytest.raises(InstallerError):
        provision_gpu_access(host)

    # Then: it fails before installing or mutating any udev rule.
    assert not any(call.startswith(("install-package:", "remove-rule:")) for call in host.calls)


def test_symlinked_legacy_rule_fails_closed_before_installation(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: a legacy-rule path replaced by a symlink.
    host = FakeGpuAccessHost()
    host.symlinks.add(LEGACY_AMDGPU_RULES_PATH)
    monkeypatch.setattr(gpu_access, "run", lambda *args, **kwargs: pytest.fail("must not download"))

    # When: first-time provisioning inspects legacy rules.
    with pytest.raises(InstallerError, match="symlinked GPU udev rule"):
        provision_gpu_access(host)

    # Then: no package installation is attempted.
    assert not any(call.startswith("install-package:") for call in host.calls)


def test_official_rule_matches_the_extracted_deb_policy_not_the_old_pxe_shape() -> None:
    # Given: the exact package verification constant.
    rules = AMD_GPU_UDEV_PACKAGE_RULES

    # When: its policy is inspected.
    # Then: it matches the extracted package rule rather than the former two-line PXE shape.
    assert rules == (
        'KERNEL=="kfd", GROUP="render", MODE="0666"\n'
        'SUBSYSTEM=="drm", KERNEL=="renderD*", GROUP="render", MODE="0666"\n'
    )
    assert "card" not in rules


def test_system_adapter_uses_dpkg_for_the_package_install(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: the production host adapter and a recorded command runner.
    commands: list[list[str]] = []
    monkeypatch.setattr(
        gpu_access,
        "run",
        lambda command, **_: commands.append(command) or SimpleNamespace(returncode=0),
    )

    # When: it installs the verified package artifact.
    SystemGpuAccessHost().install_package(Path("/tmp/package.deb"))

    # Then: installation is delegated to dpkg with sudo awareness.
    assert commands == [["dpkg", "--force-confnew", "--install", "/tmp/package.deb"]]
