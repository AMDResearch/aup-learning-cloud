# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from auplc_installer.cli import _cmd_install_inner
from auplc_installer.gpu import append_product
from auplc_installer.state import InstallerState


def _recording_stage(events: list[str]):
    @contextmanager
    def record(label: str, **_: object):
        events.append(f"stage:{label}")
        yield

    return record


def _configure_online_install(monkeypatch, state: InstallerState, events: list[object]) -> None:
    monkeypatch.setattr("auplc_installer.cli.stage", _recording_stage(events))
    monkeypatch.setattr(
        "auplc_installer.cli.detect_and_configure_gpu",
        lambda cfg, **_: (events.append("detect"), append_product(cfg, "AMD_Radeon_8060S_Graphics")),
    )
    monkeypatch.setattr("auplc_installer.cli.install_tools", lambda **_: events.append("tools"))
    monkeypatch.setattr("auplc_installer.cli.install_k3s_single_node", lambda **_: events.append("k3s"))
    monkeypatch.setattr("auplc_installer.cli.deploy_rocm_gpu_device_plugin", lambda **_: events.append("plugin"))

    def refine(cfg) -> None:
        events.append("refine")
        cfg.reset()
        append_product(cfg, "AMD_Radeon_RX_9060_XT")

    monkeypatch.setattr("auplc_installer.cli.refine_gpu_config_from_node_labels", refine)
    monkeypatch.setattr(
        "auplc_installer.cli.generate_values_overlay",
        lambda cfg, **_: events.append(("overlay", cfg.accelerator_key, cfg.image_profile)),
    )
    monkeypatch.setattr(
        "auplc_installer.cli.pull_custom_images",
        lambda *, cfg, **_: events.append(("custom-images", cfg.accelerator_key, cfg.image_profile)),
    )
    monkeypatch.setattr("auplc_installer.cli.pull_external_images", lambda **_: events.append("external-images"))
    monkeypatch.setattr("auplc_installer.cli.local_image_build", lambda *_args, **_: events.append("build-images"))
    monkeypatch.setattr("auplc_installer.cli.deploy_runtime", lambda *_args, **_: events.append("runtime"))
    monkeypatch.setattr("auplc_installer.cli._print_success_banner", lambda: None)


def test_online_image_acquisition_uses_labeller_refined_profile(monkeypatch) -> None:
    state = InstallerState()
    events: list[object] = []
    _configure_online_install(monkeypatch, state, events)

    _cmd_install_inner(state, pull=True)

    final_overlay = ("overlay", "9060xt", "gfx1200")
    acquired_images = ("custom-images", "9060xt", "gfx1200")
    assert events.index("k3s") < events.index("plugin") < events.index("refine")
    assert events.index(final_overlay) < events.index(acquired_images) < events.index("external-images")
    assert events.index("external-images") < events.index("runtime")


def test_offline_install_imports_bundle_before_labeller_validation(monkeypatch, tmp_path: Path) -> None:
    state = InstallerState(offline_mode=True, bundle_dir=tmp_path)
    events: list[object] = []
    _configure_online_install(monkeypatch, state, events)
    monkeypatch.setattr("auplc_installer.cli.load_offline_images", lambda *_args: events.append("offline-images"))

    _cmd_install_inner(state, pull=True)

    assert events.index("k3s") < events.index("offline-images") < events.index("plugin") < events.index("refine")
    assert events.index("refine") < events.index("runtime")
    assert not any(event in {"custom-images", "external-images", "build-images"} for event in events)
