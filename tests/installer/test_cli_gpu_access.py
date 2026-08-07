# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

"""GPU access sequencing tests for installer command orchestration."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from auplc_installer import cli
from auplc_installer.gpu_hardware import GpuHardware
from auplc_installer.helm import RuntimePaths
from auplc_installer.state import InstallerState


@pytest.mark.parametrize(("hardware", "expected_provision_count"), [(GpuHardware.GPU, 1), (GpuHardware.CPU, 0)])
def test_full_install_gates_gpu_access_without_passing_it_to_the_overlay(
    monkeypatch, hardware: GpuHardware, expected_provision_count: int
) -> None:
    events: list[str] = []
    state = InstallerState()
    paths = RuntimePaths(chart_path=Path("chart"), values_path=Path("values.yaml"), overlay_path=Path("overlay.yaml"))

    def fake_overlay(*args: object, **kwargs: object) -> Path:
        assert "render_gid" not in kwargs
        return paths.overlay_path

    monkeypatch.setattr(state, "runtime_paths", lambda: paths)
    monkeypatch.setattr(cli, "classify_gpu_hardware", lambda: hardware)
    monkeypatch.setattr(cli, "detect_and_configure_gpu", lambda *args, **kwargs: events.append("detect"))
    monkeypatch.setattr(cli, "provision_gpu_access", lambda **kwargs: events.append("provision"))
    monkeypatch.setattr(cli, "generate_values_overlay", fake_overlay)
    monkeypatch.setattr(cli, "install_tools", lambda **kwargs: events.append("tools"))
    monkeypatch.setattr(cli, "install_k3s_single_node", lambda **kwargs: events.append("k3s"))
    monkeypatch.setattr(cli, "pull_custom_images", lambda **kwargs: events.append("custom-images"))
    monkeypatch.setattr(cli, "pull_external_images", lambda **kwargs: events.append("external-images"))
    monkeypatch.setattr(cli, "deploy_rocm_gpu_device_plugin", lambda **kwargs: events.append("device-plugin"))
    monkeypatch.setattr(cli, "refine_gpu_config_from_node_labels", lambda *args, **kwargs: events.append("refine"))
    monkeypatch.setattr(cli, "deploy_runtime", lambda *args, **kwargs: events.append("runtime"))
    monkeypatch.setattr(cli, "_print_success_banner", lambda **_kwargs: events.append("success"))

    cli._cmd_install_inner(state, pull=True)

    assert events.count("provision") == expected_provision_count
    if expected_provision_count:
        assert events.index("provision") < events.index("device-plugin")


@pytest.mark.parametrize(("hardware", "expected_provision_count"), [(GpuHardware.GPU, 1), (GpuHardware.CPU, 0)])
def test_runtime_upgrade_gates_host_access_without_provisioning_helm_values(
    monkeypatch, hardware: GpuHardware, expected_provision_count: int
) -> None:
    events: list[str] = []
    state = InstallerState()
    paths = RuntimePaths(chart_path=Path("chart"), values_path=Path("values.yaml"), overlay_path=Path("overlay.yaml"))

    def fake_overlay(*args: object, **kwargs: object) -> Path:
        assert "render_gid" not in kwargs
        return paths.overlay_path

    monkeypatch.setattr(state, "runtime_paths", lambda: paths)
    monkeypatch.setattr(cli, "classify_gpu_hardware", lambda: hardware)
    monkeypatch.setattr(cli, "provision_gpu_access", lambda **kwargs: events.append("provision"))
    monkeypatch.setattr(cli, "detect_and_configure_gpu", lambda *args, **kwargs: events.append("detect"))
    monkeypatch.setattr(cli, "refine_gpu_config_from_node_labels", lambda *args, **kwargs: events.append("refine"))
    monkeypatch.setattr(cli, "_preserve_courses_for_upgrade", lambda *args, **kwargs: events.append("preserve-courses"))
    monkeypatch.setattr(cli, "generate_values_overlay", fake_overlay)
    monkeypatch.setattr(cli, "upgrade_runtime", lambda *args, **kwargs: events.append("upgrade-runtime"))

    cli.cmd_rt_upgrade(state)

    assert events.count("provision") == expected_provision_count


@pytest.mark.parametrize(
    ("reinstall", "delegate_name"),
    [(cli.cmd_dev_reinstall, "cmd_dev_deploy"), (cli.cmd_rt_reinstall, "cmd_rt_install")],
)
@pytest.mark.parametrize(("hardware", "expected_provision_count"), [(GpuHardware.GPU, 1), (GpuHardware.CPU, 0)])
def test_reinstall_gates_host_access_before_removing_runtime(
    monkeypatch,
    reinstall: Callable[[InstallerState], None],
    delegate_name: str,
    hardware: GpuHardware,
    expected_provision_count: int,
) -> None:
    events: list[str] = []
    state = InstallerState()

    monkeypatch.setattr(cli, "classify_gpu_hardware", lambda: hardware)
    monkeypatch.setattr(cli, "provision_gpu_access", lambda **kwargs: events.append("provision"))
    monkeypatch.setattr(cli, "remove_runtime", lambda: events.append("remove-runtime"))
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: events.append("sleep"))
    monkeypatch.setattr(cli, delegate_name, lambda current_state: events.append("delegate"))

    reinstall(state)

    assert events.count("provision") == expected_provision_count
    assert events.index("remove-runtime") < events.index("delegate")
    if expected_provision_count:
        assert events.index("provision") < events.index("remove-runtime")


def test_unknown_hardware_blocks_full_install_before_gpu_access_mutation(monkeypatch) -> None:
    state = InstallerState()

    monkeypatch.setattr(cli, "classify_gpu_hardware", lambda: GpuHardware.UNKNOWN)
    monkeypatch.setattr(cli, "detect_and_configure_gpu", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        cli, "provision_gpu_access", lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not provision"))
    )

    with pytest.raises(RuntimeError, match="hardware"):
        cli._cmd_install_inner(state, pull=True)


@pytest.mark.parametrize(
    ("reinstall", "delegate_name"),
    [(cli.cmd_dev_reinstall, "cmd_dev_deploy"), (cli.cmd_rt_reinstall, "cmd_rt_install")],
)
def test_unknown_hardware_blocks_reinstall_before_runtime_removal(
    monkeypatch, reinstall: Callable[[InstallerState], None], delegate_name: str
) -> None:
    events: list[str] = []
    state = InstallerState()

    monkeypatch.setattr(cli, "classify_gpu_hardware", lambda: GpuHardware.UNKNOWN)
    monkeypatch.setattr(
        cli, "provision_gpu_access", lambda **kwargs: (_ for _ in ()).throw(AssertionError("must not provision"))
    )
    monkeypatch.setattr(cli, "remove_runtime", lambda: events.append("remove-runtime"))
    monkeypatch.setattr(cli, delegate_name, lambda current_state: events.append("delegate"))

    with pytest.raises(RuntimeError, match="hardware"):
        reinstall(state)

    assert "remove-runtime" not in events
    assert "delegate" not in events


def test_gpu_hardware_gate_passes_offline_bundle_context_to_package_provisioning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Given: a local GPU installation running from an offline bundle.
    bundle = tmp_path / "bundle"
    package_calls: list[dict[str, object]] = []
    monkeypatch.setattr(cli, "classify_gpu_hardware", lambda: GpuHardware.GPU)
    monkeypatch.setattr(cli, "provision_gpu_access", lambda **kwargs: package_calls.append(kwargs))

    # When: the CLI's local-hardware gate provisions GPU access.
    cli._provision_gpu_access_for_local_hardware(offline_mode=True, bundle_dir=bundle)

    # Then: package provisioning receives the bundle context unchanged.
    assert package_calls == [{"offline_mode": True, "bundle_dir": bundle}]
