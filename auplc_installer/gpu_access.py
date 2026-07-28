# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

"""Single-node AMD GPU device-access reconciler."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from auplc_installer.util import InstallerError, run, run_capture

GPU_ACCESS_RULES_PATH = Path("/etc/udev/rules.d/70-auplc-gpu-access.rules")
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
UDEV_MANAGED_MARKER = "# Managed by auplc-installer: AMD GPU device access."
CANONICAL_UDEV_RULES = (
    f"{UDEV_MANAGED_MARKER}\n"
    'KERNEL=="kfd", OWNER="root", GROUP="render", MODE="0666"\n'
    'SUBSYSTEM=="drm", KERNEL=="renderD*", DRIVERS=="amdgpu", OWNER="root", GROUP="render", MODE="0666"\n'
    'SUBSYSTEM=="drm", KERNEL=="card*", DRIVERS=="amdgpu", OWNER="root", GROUP="video", MODE="0666"\n'
)
_FSYNC_PATH_SCRIPT = (
    "import os\n"
    "import sys\n"
    "fd = os.open(sys.argv[1], os.O_RDONLY)\n"
    "try:\n"
    "    os.fsync(fd)\n"
    "finally:\n"
    "    os.close(fd)\n"
)
_VERIFY_DEVICE_ACCESS_SCRIPT = (
    "import grp, pathlib, stat\n"
    "drm = pathlib.Path('/sys/class/drm')\n"
    "devices = [(pathlib.Path('/dev/kfd'), 'render', 0o666)]\n"
    "render_nodes = []\n"
    "for node in drm.glob('renderD*'):\n"
    "    driver = node / 'device' / 'driver'\n"
    "    if driver.exists() and driver.resolve().name == 'amdgpu':\n"
    "        render_nodes.append(pathlib.Path('/dev/dri') / node.name)\n"
    "if not render_nodes: raise SystemExit('no AMD renderD device found')\n"
    "devices.extend((path, 'render', 0o666) for path in render_nodes)\n"
    "card_nodes = []\n"
    "for node in drm.glob('card*'):\n"
    "    driver = node / 'device' / 'driver'\n"
    "    if driver.exists() and driver.resolve().name == 'amdgpu':\n"
    "        card_nodes.append(pathlib.Path('/dev/dri') / node.name)\n"
    "if not card_nodes: raise SystemExit('no AMD card device found')\n"
    "devices.extend((path, 'video', 0o666) for path in card_nodes)\n"
    "for path, expected_group, expected_mode in devices:\n"
    "    data = path.lstat()\n"
    "    try:\n"
    "        group_name = grp.getgrgid(data.st_gid).gr_name\n"
    "    except KeyError:\n"
    "        raise SystemExit(f'unknown GPU device group: {path}')\n"
    "    if not stat.S_ISCHR(data.st_mode) or data.st_uid != 0 or group_name != expected_group or stat.S_IMODE(data.st_mode) != expected_mode:\n"
    "        raise SystemExit(f'bad GPU device access: {path}')\n"
)


class GpuAccessHost(Protocol):
    """Privileged host-operation seam for GPU access provisioning."""

    def read_text(self, path: Path) -> str | None:
        """Return a privileged file's text, or ``None`` when it is absent."""

    def write_udev_rule(self, path: Path, text: str) -> None:
        """Write a managed udev rule after reconciliation has authorized it."""

    def reload_udev_rules(self) -> None:
        """Reload host udev rules."""

    def trigger_udev(self) -> None:
        """Apply reloaded udev rules to current devices."""

    def settle_udev(self) -> None:
        """Wait until triggered udev events finish before inode verification."""

    def remove_udev_rule(self, path: Path) -> None:
        """Remove an explicitly recognized legacy udev rule."""

    def verify_device_access(self) -> None:
        """Verify the relevant GPU device inodes use the host access contract."""

    def is_symlink(self, path: Path) -> bool:
        """Return whether ``path`` is a symlink without following it."""

    def is_regular_file(self, path: Path) -> bool:
        """Return whether an existing ``path`` is a regular file."""

    def path_exists(self, path: Path) -> bool:
        """Return whether ``path`` exists after a separate symlink check."""

    def is_directory(self, path: Path) -> bool:
        """Return whether an existing ``path`` is a directory."""


class SystemGpuAccessHost:
    """Production host adapter using the installer's sudo-aware command helpers."""

    def read_text(self, path: Path) -> str | None:
        exists = run(["test", "-e", str(path)], sudo=True, check=False)
        if exists.returncode != 0:
            return None
        result = run_capture(["cat", str(path)], sudo=True)
        return result.stdout or ""

    def write_udev_rule(self, path: Path, text: str) -> None:
        self._write_text_atomically(path, text)

    def _write_text_atomically(self, path: Path, text: str) -> None:
        """Durably replace ``path`` after atomically renaming a temporary file."""
        _validate_parent_chain(self, path.parent)
        run(["mkdir", "-p", str(path.parent)], sudo=True)
        temporary_result = run_capture(
            ["mktemp", str(path.parent / f".{path.name}.XXXXXX")],
            sudo=True,
        )
        temporary_path = (temporary_result.stdout or "").strip()
        if not temporary_path:
            raise InstallerError(f"Could not create temporary GPU access rule beside {path}")

        try:
            run(["tee", temporary_path], sudo=True, input_text=text)
            run(["chmod", "0644", temporary_path], sudo=True)
            self._fsync_path(temporary_path)
            run(["mv", "-f", temporary_path, str(path)], sudo=True)
            self._fsync_path(str(path.parent))
        except BaseException:
            run(["rm", "-f", temporary_path], sudo=True, check=False)
            raise

    def _fsync_path(self, path: str) -> None:
        run(["python3", "-c", _FSYNC_PATH_SCRIPT, path], sudo=True)

    def reload_udev_rules(self) -> None:
        run(["udevadm", "control", "--reload-rules"], sudo=True)

    def trigger_udev(self) -> None:
        run(["udevadm", "trigger"], sudo=True)

    def settle_udev(self) -> None:
        run(["udevadm", "settle"], sudo=True)

    def remove_udev_rule(self, path: Path) -> None:
        run(["rm", "-f", str(path)], sudo=True)

    def verify_device_access(self) -> None:
        run(["python3", "-c", _VERIFY_DEVICE_ACCESS_SCRIPT], sudo=True)

    def is_symlink(self, path: Path) -> bool:
        return run(["test", "-L", str(path)], sudo=True, check=False).returncode == 0

    def is_regular_file(self, path: Path) -> bool:
        return run(["test", "-f", str(path)], sudo=True, check=False).returncode == 0

    def path_exists(self, path: Path) -> bool:
        return run(["test", "-e", str(path)], sudo=True, check=False).returncode == 0

    def is_directory(self, path: Path) -> bool:
        return run(["test", "-d", str(path)], sudo=True, check=False).returncode == 0


def render_udev_rules() -> str:
    """Return the canonical AMD GPU host-device udev rules."""
    return CANONICAL_UDEV_RULES


def provision_gpu_access(host: GpuAccessHost | None = None) -> None:
    """Reconcile and verify the canonical AMD GPU host-device policy."""
    active_host = host if host is not None else SystemGpuAccessHost()
    _validate_parent_chain(active_host, GPU_ACCESS_RULES_PATH.parent)
    legacy_paths = _legacy_rules_to_remove(active_host)
    existing_rule = _read_regular_text(active_host, GPU_ACCESS_RULES_PATH)

    for path in legacy_paths:
        active_host.remove_udev_rule(path)
    if _should_rewrite_udev_rule(existing_rule):
        active_host.write_udev_rule(GPU_ACCESS_RULES_PATH, render_udev_rules())
    active_host.reload_udev_rules()
    active_host.trigger_udev()
    active_host.settle_udev()
    active_host.verify_device_access()


def _read_regular_text(host: GpuAccessHost, path: Path) -> str | None:
    if host.is_symlink(path):
        raise InstallerError(f"Refusing symlinked GPU access file: {path}")
    if not host.path_exists(path):
        return None
    if not host.is_regular_file(path):
        raise InstallerError(f"Refusing non-regular GPU access file: {path}")
    return host.read_text(path)


def _validate_parent_chain(host: GpuAccessHost, parent: Path) -> None:
    components = [*reversed(parent.parents), parent]
    for index, component in enumerate(components):
        if host.is_symlink(component):
            raise InstallerError(f"Refusing symlinked GPU access directory: {component}")
        if not host.path_exists(component):
            if index != len(components) - 1:
                raise InstallerError(f"Missing parent GPU access directory: {component}")
            return
        if not host.is_directory(component):
            raise InstallerError(f"Refusing non-directory GPU access parent: {component}")


def _legacy_rules_to_remove(host: GpuAccessHost) -> list[Path]:
    removals: list[Path] = []
    for path, expected_contents in LEGACY_RULE_CONTENTS.items():
        content = _read_regular_text(host, path)
        if content is None:
            continue
        if content not in expected_contents:
            raise InstallerError(f"Refusing to remove unexpected legacy GPU udev rule: {path}")
        removals.append(path)
    return removals


def _should_rewrite_udev_rule(existing_rule: str | None) -> bool:
    if existing_rule is None:
        return True
    if existing_rule == render_udev_rules():
        return False
    if existing_rule.split("\n", maxsplit=1)[0] != UDEV_MANAGED_MARKER:
        raise InstallerError(f"Refusing to overwrite unmanaged GPU udev rule: {GPU_ACCESS_RULES_PATH}")
    raise InstallerError(f"Refusing to overwrite unrecognized managed GPU udev rule: {GPU_ACCESS_RULES_PATH}")
