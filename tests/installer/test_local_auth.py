import json
from pathlib import Path

from auplc_installer.cli import _preserve_access_settings_for_upgrade
from auplc_installer.gpu import GpuConfig, append_product
from auplc_installer.overlay import generate_values_overlay, try_load_access_settings_from_overlay
from auplc_installer.state import InstallerState
from auplc_installer.tui import _flow_select_access


def test_overlay_emits_local_auth_and_round_trips_generated_headers(tmp_path: Path) -> None:
    cfg = GpuConfig()
    append_product(cfg, "AMD_Radeon_8060S_Graphics")
    overlay = tmp_path / "values.local.yaml"

    generate_values_overlay(
        cfg,
        image_registry="ghcr.io/amdresearch",
        image_tag="latest",
        courses=InstallerState().courses,
        access_mode="local",
        admin_username="operator",
        offline_mode=False,
        overlay_path=overlay,
    )

    settings = try_load_access_settings_from_overlay(overlay)
    rendered = json.loads(json.dumps(__import__("yaml").safe_load(overlay.read_text())))
    assert settings == ("local", "operator")
    assert rendered["custom"]["authMode"] == "local"
    assert rendered["custom"]["adminUser"] == {
        "enabled": True,
        "username": "operator",
        "existingSecret": "jupyterhub-admin-credentials",
    }


def test_bare_upgrade_restores_local_access_settings(tmp_path: Path) -> None:
    cfg = GpuConfig()
    append_product(cfg, "AMD_Radeon_8060S_Graphics")
    overlay = tmp_path / "values.local.yaml"
    generate_values_overlay(
        cfg,
        image_registry="ghcr.io/amdresearch",
        image_tag="latest",
        courses=InstallerState().courses,
        access_mode="local",
        admin_username="operator",
        offline_mode=False,
        overlay_path=overlay,
    )

    state = InstallerState()
    _preserve_access_settings_for_upgrade(state, overlay)

    assert state.access_mode == "local"
    assert state.admin_username == "operator"


def test_cli_defaults_to_personal_but_tui_defaults_to_local(monkeypatch) -> None:
    state = InstallerState()
    selections = iter(["local"])
    names = iter(["admin"])
    monkeypatch.setattr("auplc_installer.tui._ask_select", lambda *_args, **_kwargs: next(selections))
    monkeypatch.setattr("auplc_installer.tui._ask_text", lambda *_args, **_kwargs: next(names))

    _flow_select_access(state)

    assert InstallerState().access_mode == ""
    assert state.access_mode == "local"
    assert state.admin_username == "admin"
