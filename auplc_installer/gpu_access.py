# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

"""Single-node AMD GPU device-access source of truth.

The host's existing ``render`` group is authoritative. Its numeric GID is
persisted here so installer reruns and runtime-only commands cannot silently
select a different permission model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from auplc_installer.util import InstallerError, run, run_capture

GPU_ACCESS_STATE_VERSION = 1
MAX_RENDER_GID = (2**32) - 2
GPU_ACCESS_STATE_PATH = Path("/var/lib/auplc/gpu-access.json")
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
    'KERNEL=="kfd", OWNER="root", GROUP="render", MODE="0660"\n'
    'SUBSYSTEM=="drm", KERNEL=="renderD*", DRIVERS=="amdgpu", OWNER="root", GROUP="render", MODE="0660"\n'
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
    "import os, pathlib, stat, sys\n"
    "gid = int(sys.argv[1])\n"
    "paths = [pathlib.Path('/dev/kfd')]\n"
    "for node in pathlib.Path('/sys/class/drm').glob('renderD*'):\n"
    "    driver = node / 'device' / 'driver'\n"
    "    if driver.exists() and driver.resolve().name == 'amdgpu': paths.append(pathlib.Path('/dev/dri') / node.name)\n"
    "if len(paths) == 1: raise SystemExit('no AMD renderD device found')\n"
    "for path in paths:\n"
    "    data = path.lstat()\n"
    "    if not stat.S_ISCHR(data.st_mode) or data.st_uid != 0 or data.st_gid != gid or stat.S_IMODE(data.st_mode) != 0o660: raise SystemExit(f'bad GPU device access: {path}')\n"
)


@dataclass(frozen=True)
class GpuAccessState:
    """Versioned, immutable record of the host render-group GID."""

    render_gid: int
    version: int = GPU_ACCESS_STATE_VERSION

    def __post_init__(self) -> None:
        if self.version != GPU_ACCESS_STATE_VERSION:
            raise InstallerError(f"Unsupported GPU access state version: {self.version!r}")
        _validate_render_gid(self.render_gid)


class GpuAccessHost(Protocol):
    """Privileged host-operation seam for GPU access provisioning."""

    def get_group_entry(self, group_name: str) -> str:
        """Return the NSS group record for ``group_name``."""

    def read_text(self, path: Path) -> str | None:
        """Return a privileged file's text, or ``None`` when it is absent."""

    def write_state_atomically(self, path: Path, text: str) -> None:
        """Atomically replace a state file with same-directory persistence."""

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

    def verify_device_access(self, render_gid: int) -> None:
        """Verify the relevant GPU device inodes use the requested access contract."""

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

    def get_group_entry(self, group_name: str) -> str:
        result = run_capture(["getent", "group", group_name], check=False)
        if result.returncode != 0:
            return ""
        return result.stdout or ""

    def read_text(self, path: Path) -> str | None:
        exists = run(["test", "-e", str(path)], sudo=True, check=False)
        if exists.returncode != 0:
            return None
        result = run_capture(["cat", str(path)], sudo=True)
        return result.stdout or ""

    def write_state_atomically(self, path: Path, text: str) -> None:
        """Durably replace state with a same-directory temporary file."""
        self._write_text_atomically(path, text)

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
            raise InstallerError(f"Could not create temporary GPU access state beside {path}")

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

    def verify_device_access(self, render_gid: int) -> None:
        run(["python3", "-c", _VERIFY_DEVICE_ACCESS_SCRIPT, str(render_gid)], sudo=True)

    def is_symlink(self, path: Path) -> bool:
        return run(["test", "-L", str(path)], sudo=True, check=False).returncode == 0

    def is_regular_file(self, path: Path) -> bool:
        return run(["test", "-f", str(path)], sudo=True, check=False).returncode == 0

    def path_exists(self, path: Path) -> bool:
        return run(["test", "-e", str(path)], sudo=True, check=False).returncode == 0

    def is_directory(self, path: Path) -> bool:
        return run(["test", "-d", str(path)], sudo=True, check=False).returncode == 0


def serialize_gpu_access_state(state: GpuAccessState) -> str:
    """Return the canonical on-disk JSON representation for ``state``."""
    return (
        json.dumps(
            {"renderGid": state.render_gid, "version": state.version},
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    )


def parse_gpu_access_state(text: str) -> GpuAccessState:
    """Parse strict versioned GPU access state, failing closed on bad input."""
    try:
        payload = json.loads(text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise InstallerError("Malformed GPU access state") from exc

    if not isinstance(payload, dict) or set(payload) != {"renderGid", "version"}:
        raise InstallerError("Malformed GPU access state")

    version = payload["version"]
    render_gid = payload["renderGid"]
    if type(version) is not int or version != GPU_ACCESS_STATE_VERSION:
        raise InstallerError("Unsupported GPU access state version")
    _validate_render_gid(render_gid)
    return GpuAccessState(render_gid=render_gid, version=version)


def resolve_render_gid(getent_output: str) -> int:
    """Parse the numeric GID from one ``getent group render`` record."""
    if not isinstance(getent_output, str):
        raise InstallerError("Could not resolve the host render group")

    lines = getent_output.splitlines()
    if len(lines) != 1:
        raise InstallerError("Could not resolve the host render group")

    fields = lines[0].split(":")
    if len(fields) != 4 or fields[0] != "render":
        raise InstallerError("Could not resolve the host render group")

    raw_gid = fields[2]
    if not raw_gid.isascii() or not raw_gid.isdecimal():
        raise InstallerError("Could not resolve the host render group")

    render_gid = int(raw_gid)
    _validate_render_gid(render_gid)
    return render_gid


def render_udev_rules() -> str:
    """Return the canonical, least-privilege AMD GPU udev rules."""
    return CANONICAL_UDEV_RULES


def provision_gpu_access(host: GpuAccessHost | None = None) -> GpuAccessState:
    """Create or reuse immutable state and reconcile the managed udev rule.

    When state is absent, adopt the current host ``render`` GID only after the
    udev rule has been applied and verified. Existing state must match the host
    group before any mutation occurs.
    """
    return _reconcile_gpu_access(host if host is not None else SystemGpuAccessHost())


def load_existing_gpu_access(host: GpuAccessHost | None = None) -> GpuAccessState:
    """Reconcile runtime GPU access, adopting missing state for pre-change installs.

    Runtime, upgrade, and reinstall paths reuse persisted state when present.
    For an installation created before GPU access state existed, this performs a
    one-time host ``render`` GID adoption after udev verification. A persisted
    GID that differs from the current host group remains a hard failure.
    """
    return _reconcile_gpu_access(host if host is not None else SystemGpuAccessHost())


def _reconcile_gpu_access(host: GpuAccessHost) -> GpuAccessState:
    _validate_parent_chain(host, GPU_ACCESS_STATE_PATH.parent)
    _validate_parent_chain(host, GPU_ACCESS_RULES_PATH.parent)
    state_text = _read_regular_text(host, GPU_ACCESS_STATE_PATH)
    host_gid = resolve_render_gid(host.get_group_entry("render"))

    if state_text is None:
        state = GpuAccessState(render_gid=host_gid)
        persist_state = True
    else:
        state = parse_gpu_access_state(state_text)
        if state.render_gid != host_gid:
            raise InstallerError(
                f"Persisted render GID does not match the current host render group ({state.render_gid} != {host_gid})"
            )
        persist_state = False

    legacy_paths = _legacy_rules_to_remove(host)
    existing_rule = _read_regular_text(host, GPU_ACCESS_RULES_PATH)
    rewrite_rule = _should_rewrite_udev_rule(existing_rule)

    for path in legacy_paths:
        host.remove_udev_rule(path)
    if rewrite_rule:
        host.write_udev_rule(GPU_ACCESS_RULES_PATH, render_udev_rules())
    host.reload_udev_rules()
    host.trigger_udev()
    host.settle_udev()
    host.verify_device_access(state.render_gid)
    if persist_state:
        host.write_state_atomically(GPU_ACCESS_STATE_PATH, serialize_gpu_access_state(state))

    return state


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
    return True


def _validate_render_gid(render_gid: object) -> None:
    if type(render_gid) is not int or not 1 <= render_gid <= MAX_RENDER_GID:
        raise InstallerError(f"Invalid render group GID: {render_gid!r}")
