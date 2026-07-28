# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

from __future__ import annotations

import contextlib
import tempfile
from pathlib import Path
from typing import Protocol

from auplc_installer.util import InstallerError, run, run_capture, verify_sha256

AMD_GPU_UDEV_PACKAGE_NAME = "amdgpu-insecure-instinct-udev-rules"
AMD_GPU_UDEV_PACKAGE_VERSION = "30.30.4.0-2341068.24.04"
AMD_GPU_UDEV_PACKAGE_FILENAME = "amdgpu-insecure-instinct-udev-rules_30.30.4.0-2341068.24.04_all.deb"
AMD_GPU_UDEV_PACKAGE_URL = (
    "https://repo.radeon.com/amdgpu/30.30.4/ubuntu/pool/main/a/amdgpu-insecure-instinct-udev-rules/"
    f"{AMD_GPU_UDEV_PACKAGE_FILENAME}"
)
AMD_GPU_UDEV_PACKAGE_SHA256 = "4be865985c7a13114c45925e77bc0b411b9fd47d5040ed35df44b9c411766162"
AMD_GPU_UDEV_PACKAGE_RULES_PATH = Path("/etc/udev/rules.d/70-amdgpu.rules")
AMD_GPU_UDEV_PACKAGE_RULES = (
    'KERNEL=="kfd", GROUP="render", MODE="0666"\nSUBSYSTEM=="drm", KERNEL=="renderD*", GROUP="render", MODE="0666"\n'
)

LEGACY_KFD_RULES_PATH = Path("/etc/udev/rules.d/70-kfd.rules")
LEGACY_AMDGPU_RULES_PATH = Path("/etc/udev/rules.d/70-amdgpu.rules")
LEGACY_ROCM_DEVICES_RULES_PATH = Path("/etc/udev/rules.d/70-rocm-devices.rules")
LEGACY_KFD_RULES = 'KERNEL=="kfd", MODE="0666"\nSUBSYSTEM=="drm", KERNEL=="renderD*", MODE="0666"\n'
LEGACY_AMDGPU_RULES = (
    "# ROCm device permissions\n"
    "# Grant render group access to AMD GPU devices\n"
    "# Reference: https://rocm.docs.amd.com/projects/install-on-linux/en/latest/install/prerequisites.html#using-udev-rules\n"
    'KERNEL=="kfd", GROUP="render", MODE="0660"\n'
    'SUBSYSTEM=="drm", KERNEL=="renderD*", GROUP="render", MODE="0660"\n'
)
LEGACY_AMDGPU_PXE_RULES = 'KERNEL=="kfd", MODE="0666"\nKERNEL=="renderD[0-9]*", MODE="0666"\n'
LEGACY_ROCM_DEVICES_RULES = (
    "# ROCm device permissions\n"
    "# Ensure /dev/kfd and /dev/dri/renderD* are accessible by render group\n"
    'SUBSYSTEM=="kfd", GROUP="render", MODE="0660"\n'
    'SUBSYSTEM=="drm", KERNEL=="renderD*", GROUP="render", MODE="0660"\n'
)
LEGACY_RULE_CONTENTS: dict[Path, frozenset[str]] = {
    LEGACY_KFD_RULES_PATH: frozenset((LEGACY_KFD_RULES,)),
    LEGACY_AMDGPU_RULES_PATH: frozenset((LEGACY_AMDGPU_RULES, LEGACY_AMDGPU_PXE_RULES)),
    LEGACY_ROCM_DEVICES_RULES_PATH: frozenset((LEGACY_ROCM_DEVICES_RULES,)),
}


class GpuAccessHost(Protocol):
    def read_text(self, path: Path) -> str | None: ...

    def remove_udev_rule(self, path: Path) -> None: ...

    def installed_package_version(self) -> str | None: ...

    def package_owns_rule(self, path: Path) -> bool: ...

    def install_package(self, deb: Path) -> None: ...

    def reload_udev_rules(self) -> None: ...

    def trigger_udev(self) -> None: ...

    def settle_udev(self) -> None: ...

    def is_symlink(self, path: Path) -> bool: ...

    def is_regular_file(self, path: Path) -> bool: ...

    def path_exists(self, path: Path) -> bool: ...

    def is_directory(self, path: Path) -> bool: ...


class SystemGpuAccessHost:
    def read_text(self, path: Path) -> str | None:
        exists = run(["test", "-e", str(path)], sudo=True, check=False)
        if exists.returncode != 0:
            return None
        result = run_capture(["cat", str(path)], sudo=True)
        return result.stdout or ""

    def remove_udev_rule(self, path: Path) -> None:
        run(["rm", "-f", str(path)], sudo=True)

    def installed_package_version(self) -> str | None:
        result = run_capture(
            ["dpkg-query", "--show", "--showformat=${Status}\t${Version}", AMD_GPU_UDEV_PACKAGE_NAME],
            sudo=True,
            check=False,
        )
        if result.returncode != 0:
            return None
        status, separator, version = (result.stdout or "").strip().partition("\t")
        if status != "install ok installed" or not separator or not version:
            return None
        return version

    def package_owns_rule(self, path: Path) -> bool:
        result = run_capture(
            ["dpkg-query", "--listfiles", AMD_GPU_UDEV_PACKAGE_NAME],
            sudo=True,
            check=False,
        )
        return result.returncode == 0 and str(path) in (result.stdout or "").splitlines()

    def install_package(self, deb: Path) -> None:
        run(["dpkg", "--force-confnew", "--install", str(deb)], sudo=True)

    def reload_udev_rules(self) -> None:
        run(["udevadm", "control", "--reload-rules"], sudo=True)

    def trigger_udev(self) -> None:
        run(["udevadm", "trigger"], sudo=True)

    def settle_udev(self) -> None:
        run(["udevadm", "settle"], sudo=True)

    def is_symlink(self, path: Path) -> bool:
        return run(["test", "-L", str(path)], sudo=True, check=False).returncode == 0

    def is_regular_file(self, path: Path) -> bool:
        return run(["test", "-f", str(path)], sudo=True, check=False).returncode == 0

    def path_exists(self, path: Path) -> bool:
        return run(["test", "-e", str(path)], sudo=True, check=False).returncode == 0

    def is_directory(self, path: Path) -> bool:
        return run(["test", "-d", str(path)], sudo=True, check=False).returncode == 0


def provision_gpu_access(
    host: GpuAccessHost | None = None,
    *,
    offline_mode: bool = False,
    bundle_dir: Path | None = None,
) -> None:
    active_host = host if host is not None else SystemGpuAccessHost()
    _validate_parent_chain(active_host, AMD_GPU_UDEV_PACKAGE_RULES_PATH.parent)
    installed_version = active_host.installed_package_version()
    legacy_paths = _legacy_rules_to_remove(active_host)
    if installed_version == AMD_GPU_UDEV_PACKAGE_VERSION:
        _verify_installed_package(active_host, installed_version)
    else:
        _install_package(active_host, offline_mode=offline_mode, bundle_dir=bundle_dir)
        installed_version = active_host.installed_package_version()
        if installed_version is None:
            raise InstallerError(f"{AMD_GPU_UDEV_PACKAGE_NAME} was not installed")
        _verify_installed_package(active_host, installed_version)
    _remove_separate_legacy_rules(active_host, legacy_paths)


def _install_package(active_host: GpuAccessHost, *, offline_mode: bool, bundle_dir: Path | None) -> None:
    if offline_mode:
        if bundle_dir is None:
            raise InstallerError("Offline GPU udev package installation requires a bundle directory")
        deb = bundle_dir / "packages" / AMD_GPU_UDEV_PACKAGE_FILENAME
        if not deb.is_file():
            raise InstallerError(f"Offline GPU udev package is missing: {deb}")
        verify_sha256(deb, AMD_GPU_UDEV_PACKAGE_SHA256)
        active_host.install_package(deb)
        return

    with tempfile.NamedTemporaryFile(prefix="auplc-amdgpu-udev-", suffix=".deb", delete=False) as temporary:
        deb = Path(temporary.name)
    try:
        run(["wget", "-q", AMD_GPU_UDEV_PACKAGE_URL, "-O", str(deb)])
        verify_sha256(deb, AMD_GPU_UDEV_PACKAGE_SHA256)
        active_host.install_package(deb)
    finally:
        with contextlib.suppress(OSError):
            deb.unlink()


def _verify_installed_package(active_host: GpuAccessHost, installed_version: str) -> None:
    if installed_version != AMD_GPU_UDEV_PACKAGE_VERSION:
        raise InstallerError(
            f"{AMD_GPU_UDEV_PACKAGE_NAME} has version {installed_version}, expected {AMD_GPU_UDEV_PACKAGE_VERSION}"
        )
    if not active_host.package_owns_rule(AMD_GPU_UDEV_PACKAGE_RULES_PATH):
        raise InstallerError(f"{AMD_GPU_UDEV_PACKAGE_NAME} does not own {AMD_GPU_UDEV_PACKAGE_RULES_PATH}")
    rule = _read_regular_text(active_host, AMD_GPU_UDEV_PACKAGE_RULES_PATH)
    if rule != AMD_GPU_UDEV_PACKAGE_RULES:
        raise InstallerError(f"{AMD_GPU_UDEV_PACKAGE_NAME} rule does not match the pinned package policy")


def _read_regular_text(host: GpuAccessHost, path: Path) -> str | None:
    if host.is_symlink(path):
        raise InstallerError(f"Refusing symlinked GPU udev rule: {path}")
    if not host.path_exists(path):
        return None
    if not host.is_regular_file(path):
        raise InstallerError(f"Refusing non-regular GPU udev rule: {path}")
    return host.read_text(path)


def _validate_parent_chain(host: GpuAccessHost, parent: Path) -> None:
    components = [*reversed(parent.parents), parent]
    for index, component in enumerate(components):
        if host.is_symlink(component):
            raise InstallerError(f"Refusing symlinked GPU udev directory: {component}")
        if not host.path_exists(component):
            if index != len(components) - 1:
                raise InstallerError(f"Missing parent GPU udev directory: {component}")
            return
        if not host.is_directory(component):
            raise InstallerError(f"Refusing non-directory GPU udev parent: {component}")


def _legacy_rules_to_remove(host: GpuAccessHost) -> list[Path]:
    removals: list[Path] = []
    for path, expected_contents in LEGACY_RULE_CONTENTS.items():
        content = _read_regular_text(host, path)
        if content is None:
            continue
        if path == AMD_GPU_UDEV_PACKAGE_RULES_PATH and host.package_owns_rule(path):
            continue
        if content not in expected_contents:
            raise InstallerError(f"Refusing to remove unexpected legacy GPU udev rule: {path}")
        removals.append(path)
    return removals


def _remove_separate_legacy_rules(host: GpuAccessHost, paths: list[Path]) -> None:
    removed = False
    for path in paths:
        if path == AMD_GPU_UDEV_PACKAGE_RULES_PATH:
            continue
        host.remove_udev_rule(path)
        removed = True
    if removed:
        host.reload_udev_rules()
        host.trigger_udev()
        host.settle_udev()
