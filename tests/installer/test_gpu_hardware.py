# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

"""Tests for local AMD GPU hardware classification from PCI sysfs evidence."""

from __future__ import annotations

from pathlib import Path

from auplc_installer.gpu_hardware import GpuHardware, classify_gpu_hardware


def test_classify_gpu_hardware_returns_gpu_for_amd_display_controller(tmp_path: Path) -> None:
    pci_devices = tmp_path / "devices"
    device = pci_devices / "0000:03:00.0"
    device.mkdir(parents=True)
    (device / "vendor").write_text("0x1002\n", encoding="ascii")
    (device / "class").write_text("0x030200\n", encoding="ascii")

    hardware = classify_gpu_hardware(pci_devices)

    assert hardware is GpuHardware.GPU


def test_classify_gpu_hardware_returns_cpu_for_complete_scan_without_amd_display(tmp_path: Path) -> None:
    pci_devices = tmp_path / "devices"
    intel_display = pci_devices / "0000:00:02.0"
    intel_display.mkdir(parents=True)
    (intel_display / "vendor").write_text("0x8086\n", encoding="ascii")
    (intel_display / "class").write_text("0x030000\n", encoding="ascii")
    amd_audio = pci_devices / "0000:03:00.1"
    amd_audio.mkdir()
    (amd_audio / "vendor").write_text("0x1002\n", encoding="ascii")
    (amd_audio / "class").write_text("0x040300\n", encoding="ascii")

    hardware = classify_gpu_hardware(pci_devices)

    assert hardware is GpuHardware.CPU


def test_classify_gpu_hardware_returns_unknown_when_pci_root_is_missing(tmp_path: Path) -> None:
    hardware = classify_gpu_hardware(tmp_path / "missing")

    assert hardware is GpuHardware.UNKNOWN


def test_classify_gpu_hardware_returns_unknown_when_pci_root_is_empty(tmp_path: Path) -> None:
    pci_devices = tmp_path / "devices"
    pci_devices.mkdir()

    hardware = classify_gpu_hardware(pci_devices)

    assert hardware is GpuHardware.UNKNOWN


def test_classify_gpu_hardware_returns_unknown_for_incomplete_pci_evidence(tmp_path: Path) -> None:
    pci_devices = tmp_path / "devices"
    missing_vendor = pci_devices / "0000:00:02.0"
    missing_vendor.mkdir(parents=True)
    (missing_vendor / "class").write_text("0x030000\n", encoding="ascii")

    hardware = classify_gpu_hardware(pci_devices)

    assert hardware is GpuHardware.UNKNOWN


def test_classify_gpu_hardware_prefers_positive_amd_evidence_over_incomplete_sibling(tmp_path: Path) -> None:
    pci_devices = tmp_path / "devices"
    incomplete_device = pci_devices / "0000:00:02.0"
    incomplete_device.mkdir(parents=True)
    (incomplete_device / "vendor").write_text("0x8086\n", encoding="ascii")
    gpu_device = pci_devices / "0000:03:00.0"
    gpu_device.mkdir()
    (gpu_device / "vendor").write_text("0x1002\n", encoding="ascii")
    (gpu_device / "class").write_text("0x038000\n", encoding="ascii")

    hardware = classify_gpu_hardware(pci_devices)

    assert hardware is GpuHardware.GPU
