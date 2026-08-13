# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

"""Read-only local AMD GPU hardware classification from Linux PCI sysfs."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Final

PCI_DEVICES_ROOT: Final = Path("/sys/bus/pci/devices")
AMD_PCI_VENDOR: Final = "0x1002"
DISPLAY_CLASS_PREFIX: Final = "0x03"
_HEX_DIGITS: Final = frozenset("0123456789abcdef")


class GpuHardware(Enum):
    """The local host's AMD display-hardware eligibility."""

    GPU = "gpu"
    CPU = "cpu"
    UNKNOWN = "unknown"


def classify_gpu_hardware(pci_devices_root: Path = PCI_DEVICES_ROOT) -> GpuHardware:
    """Classify local hardware using complete PCI vendor and class evidence."""
    try:
        devices = tuple(pci_devices_root.iterdir())
    except OSError:
        return GpuHardware.UNKNOWN

    if not devices:
        return GpuHardware.UNKNOWN

    scan_is_complete = True
    for device in devices:
        vendor = _read_pci_attribute(device / "vendor")
        pci_class = _read_pci_attribute(device / "class")
        if vendor is None or pci_class is None or not _has_valid_pci_attributes(vendor, pci_class):
            scan_is_complete = False
            continue
        if vendor == AMD_PCI_VENDOR and pci_class.startswith(DISPLAY_CLASS_PREFIX):
            return GpuHardware.GPU

    return GpuHardware.CPU if scan_is_complete else GpuHardware.UNKNOWN


def _read_pci_attribute(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="ascii").strip().lower()
    except (OSError, UnicodeDecodeError):
        return None
    return value or None


def _has_valid_pci_attributes(vendor: str, pci_class: str) -> bool:
    return _is_pci_hex(vendor, digits=4) and _is_pci_hex(pci_class, digits=6)


def _is_pci_hex(value: str, *, digits: int) -> bool:
    return (
        len(value) == digits + 2 and value.startswith("0x") and all(character in _HEX_DIGITS for character in value[2:])
    )
