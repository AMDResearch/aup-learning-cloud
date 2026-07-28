# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

"""GPU access sequencing tests for installer command orchestration."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
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
    stages: list[tuple[str, int, int]] = []
    state = InstallerState()
    paths = RuntimePaths(chart_path=Path("chart"), values_path=Path("values.yaml"), overlay_path=Path("overlay.yaml"))

    @contextmanager
    def fake_stage(label: str, *, idx: int, total: int):
        stages.append((label, idx, total))
        yield

    def fake_overlay(*args: object, **kwargs: object) -> Path:
        assert "render_gid" not in kwargs
        events.append("overlay")
        return paths.overlay_path

    monkeypatch.setattr(state, "runtime_paths", lambda: paths)
    monkeypatch.setattr(cli, "stage", fake_stage)
    monkeypatch.setattr(cli, "classify_gpu_hardware", lambda: hardware)
    monkeypatch.setattr(cli, "detect_and_configure_gpu", lambda *args, **kwargs: events.append("detect"))
    monkeypatch.setattr(cli, "provision_gpu_access", lambda: events.append("provision"))
    monkeypatch.setattr(cli, "generate_values_overlay", fake_overlay)
    monkeypatch.setattr(cli, "install_tools", lambda **kwargs: events.append("tools"))
    monkeypatch.setattr(cli, "install_k3s_single_node", lambda **kwargs: events.append("k3s"))
    monkeypatch.setattr(cli, "pull_custom_images", lambda **kwargs: events.append("custom-images"))
    monkeypatch.setattr(cli, "pull_external_images", lambda **kwargs: events.append("external-images"))
    monkeypatch.setattr(cli, "deploy_rocm_gpu_device_plugin", lambda **kwargs: events.append("device-plugin"))
    monkeypatch.setattr(cli, "refine_gpu_config_from_node_labels", lambda *args, **kwargs: events.append("refine"))
    monkeypatch.setattr(cli, "deploy_runtime", lambda *args, **kwargs: events.append("runtime"))
    monkeypatch.setattr(cli, "_print_success_banner", lambda: events.append("success"))

    cli._cmd_install_inner(state, pull=True)

    assert events.count("provision") == expected_provision_count
    if expected_provision_count:
        assert events.index("provision") < events.index("device-plugin")
    assert events.count("overlay") == 2
    assert stages == [
        ("Detecting GPU", 1, 9),
        ("Provisioning GPU device access", 2, 9),
        ("Generating values overlay (initial)", 3, 9),
        ("Installing helm + k9s", 4, 9),
        ("Installing K3s (single-node)", 5, 9),
        ("Pulling custom + external images", 6, 9),
        ("Deploying ROCm GPU device plugin + node labeller", 7, 9),
        ("Refreshing values overlay from node labels", 8, 9),
        ("Deploying JupyterHub runtime (helm install + wait)", 9, 9),
    ]


@pytest.mark.parametrize(("hardware", "expected_provision_count"), [(GpuHardware.GPU, 1), (GpuHardware.CPU, 0)])
def test_runtime_upgrade_gates_host_access_without_provisioning_helm_values(
    monkeypatch, hardware: GpuHardware, expected_provision_count: int
) -> None:
    events: list[str] = []
    state = InstallerState()
    paths = RuntimePaths(chart_path=Path("chart"), values_path=Path("values.yaml"), overlay_path=Path("overlay.yaml"))

    def fake_overlay(*args: object, **kwargs: object) -> Path:
        assert "render_gid" not in kwargs
        events.append("overlay")
        return paths.overlay_path

    monkeypatch.setattr(state, "runtime_paths", lambda: paths)
    monkeypatch.setattr(cli, "classify_gpu_hardware", lambda: hardware)
    monkeypatch.setattr(cli, "provision_gpu_access", lambda: events.append("provision"))
    monkeypatch.setattr(cli, "detect_and_configure_gpu", lambda *args, **kwargs: events.append("detect"))
    monkeypatch.setattr(cli, "refine_gpu_config_from_node_labels", lambda *args, **kwargs: events.append("refine"))
    monkeypatch.setattr(cli, "_preserve_courses_for_upgrade", lambda *args, **kwargs: events.append("preserve-courses"))
    monkeypatch.setattr(cli, "generate_values_overlay", fake_overlay)
    monkeypatch.setattr(cli, "upgrade_runtime", lambda *args, **kwargs: events.append("upgrade-runtime"))

    cli.cmd_rt_upgrade(state)

    assert events.count("provision") == expected_provision_count
    assert events[-5:] == ["detect", "refine", "preserve-courses", "overlay", "upgrade-runtime"]


@pytest.mark.parametrize(
    ("command", "expected_events"),
    [
        (cli.cmd_dev_deploy, ("detect", "refine", "overlay", "deploy-runtime")),
        (cli.cmd_dev_upgrade, ("detect", "refine", "preserve-courses", "overlay", "upgrade-runtime")),
        (cli.cmd_rt_install, ("detect", "refine", "overlay", "deploy-runtime")),
        (cli.cmd_rt_upgrade, ("detect", "refine", "preserve-courses", "overlay", "upgrade-runtime")),
    ],
)
def test_cpu_hardware_skips_host_access_and_preserves_runtime_flow(
    monkeypatch, command: Callable[[InstallerState], None], expected_events: tuple[str, ...]
) -> None:
    events: list[str] = []
    state = InstallerState()
    paths = RuntimePaths(chart_path=Path("chart"), values_path=Path("values.yaml"), overlay_path=Path("overlay.yaml"))

    monkeypatch.setattr(state, "runtime_paths", lambda: paths)
    monkeypatch.setattr(cli, "classify_gpu_hardware", lambda: GpuHardware.CPU)
    monkeypatch.setattr(
        cli, "provision_gpu_access", lambda: (_ for _ in ()).throw(AssertionError("must not provision"))
    )
    monkeypatch.setattr(cli, "detect_and_configure_gpu", lambda *args, **kwargs: events.append("detect"))
    monkeypatch.setattr(cli, "refine_gpu_config_from_node_labels", lambda *args, **kwargs: events.append("refine"))
    monkeypatch.setattr(cli, "_preserve_courses_for_upgrade", lambda *args, **kwargs: events.append("preserve-courses"))
    monkeypatch.setattr(
        cli,
        "generate_values_overlay",
        lambda *args, **kwargs: events.append("overlay") or paths.overlay_path,
    )
    monkeypatch.setattr(cli, "deploy_runtime", lambda *args, **kwargs: events.append("deploy-runtime"))
    monkeypatch.setattr(cli, "upgrade_runtime", lambda *args, **kwargs: events.append("upgrade-runtime"))

    command(state)

    assert events == list(expected_events)


@pytest.mark.parametrize(
    ("reinstall", "delegate_name"),
    [(cli.cmd_dev_reinstall, "cmd_dev_deploy"), (cli.cmd_rt_reinstall, "cmd_rt_install")],
)
@pytest.mark.parametrize(
    ("hardware", "expected_access_events"), [(GpuHardware.GPU, ["provision"]), (GpuHardware.CPU, [])]
)
def test_reinstall_gates_host_access_before_removing_runtime(
    monkeypatch,
    reinstall: Callable[[InstallerState], None],
    delegate_name: str,
    hardware: GpuHardware,
    expected_access_events: list[str],
) -> None:
    events: list[str] = []
    state = InstallerState()

    monkeypatch.setattr(cli, "classify_gpu_hardware", lambda: hardware)
    monkeypatch.setattr(cli, "provision_gpu_access", lambda: events.append("provision"))
    monkeypatch.setattr(cli, "remove_runtime", lambda: events.append("remove-runtime"))
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: events.append("sleep"))
    monkeypatch.setattr(cli, delegate_name, lambda current_state: events.append("delegate"))

    reinstall(state)

    assert events == [*expected_access_events, "remove-runtime", "sleep", "delegate"]


def test_unknown_hardware_blocks_full_install_before_gpu_access_mutation(monkeypatch) -> None:
    events: list[str] = []
    state = InstallerState()

    monkeypatch.setattr(cli, "classify_gpu_hardware", lambda: GpuHardware.UNKNOWN)
    monkeypatch.setattr(cli, "detect_and_configure_gpu", lambda *args, **kwargs: events.append("detect"))
    monkeypatch.setattr(
        cli, "provision_gpu_access", lambda: (_ for _ in ()).throw(AssertionError("must not provision"))
    )

    with pytest.raises(RuntimeError, match="hardware"):
        cli._cmd_install_inner(state, pull=True)

    assert events == ["detect"]


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
        cli, "provision_gpu_access", lambda: (_ for _ in ()).throw(AssertionError("must not provision"))
    )
    monkeypatch.setattr(cli, "remove_runtime", lambda: events.append("remove-runtime"))
    monkeypatch.setattr(cli, delegate_name, lambda current_state: events.append("delegate"))

    with pytest.raises(RuntimeError, match="hardware"):
        reinstall(state)

    assert events == []


def test_cli_exposes_no_render_gid_reconciliation_api() -> None:
    assert not hasattr(cli, "_render_gid_for_local_hardware")
    assert not hasattr(cli, "load_existing_gpu_access")
