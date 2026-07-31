import json
from pathlib import Path

import pytest

from auplc_installer import tui
from auplc_installer.cli import (
    _preserve_access_settings_for_upgrade,
    _resolve_access_settings,
    cmd_dev_reinstall,
    cmd_rt_reinstall,
)
from auplc_installer.gpu import GpuConfig, append_product
from auplc_installer.helm import RuntimePaths
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


@pytest.mark.parametrize("username", ["Admin", "admin:name", 'admin"name', "admin\nname", "-admin"])
def test_local_admin_username_rejects_unsafe_values(username: str) -> None:
    state = InstallerState(access_mode="local", admin_username=username)

    with pytest.raises(Exception, match="lowercase ASCII"):
        _resolve_access_settings(state)


def test_explicit_local_upgrade_without_username_preserves_previous_username(tmp_path: Path) -> None:
    overlay = tmp_path / "values.local.yaml"
    overlay.write_text("# Access mode   : local\n# Admin username: operator\n", encoding="utf-8")
    state = InstallerState(access_mode="local")

    _preserve_access_settings_for_upgrade(state, overlay)

    assert _resolve_access_settings(state) == ("local", "operator")


def test_upgrade_rejects_unmanaged_advanced_auth_overlay(tmp_path: Path) -> None:
    overlay = tmp_path / "values.local.yaml"
    overlay.write_text("custom:\n  authMode: github\n", encoding="utf-8")

    with pytest.raises(Exception, match="operator-managed Helm values"):
        _preserve_access_settings_for_upgrade(InstallerState(), overlay)


@pytest.mark.parametrize(
    "auth_mode",
    ['"github"', "'multi' # operator-managed", '"dummy"'],
)
def test_upgrade_rejects_quoted_or_commented_advanced_auth_overlay(tmp_path: Path, auth_mode: str) -> None:
    overlay = tmp_path / "values.local.yaml"
    overlay.write_text(
        f"# Access mode   : local\n# Admin username: operator\ncustom:\n  authMode: {auth_mode}\n",
        encoding="utf-8",
    )

    with pytest.raises(Exception, match="operator-managed Helm values"):
        _preserve_access_settings_for_upgrade(InstallerState(), overlay)


@pytest.mark.parametrize(
    ("menu", "action", "command"),
    [
        ("dev", "deploy", "cmd_dev_deploy"),
        ("dev", "reinstall", "cmd_dev_reinstall"),
        ("rt", "install", "cmd_rt_install"),
        ("rt", "reinstall", "cmd_rt_reinstall"),
    ],
)
def test_tui_runtime_deploy_and_reinstall_prompt_for_access_mode(
    monkeypatch, menu: str, action: str, command: str
) -> None:
    selected_access = []
    monkeypatch.setattr("auplc_installer.tui._ask_select", lambda *_args, **_kwargs: action)
    monkeypatch.setattr("auplc_installer.tui._ask_confirm", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("auplc_installer.tui._flow_select_envs", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("auplc_installer.tui._flow_select_access", lambda state: selected_access.append(state))
    monkeypatch.setattr(f"auplc_installer.cli.{command}", lambda _state: None)

    if menu == "dev":
        tui._flow_dev(InstallerState())
    else:
        tui._flow_rt(InstallerState())

    assert len(selected_access) == 1


@pytest.mark.parametrize(
    ("reinstall", "install"),
    [
        (cmd_dev_reinstall, "auplc_installer.cli.cmd_dev_deploy"),
        (cmd_rt_reinstall, "auplc_installer.cli.cmd_rt_install"),
    ],
)
def test_reinstall_preserves_local_access_before_removing_release(
    monkeypatch, tmp_path: Path, reinstall, install: str
) -> None:
    overlay = tmp_path / "values.local.yaml"
    overlay.write_text("# Access mode   : local\n# Admin username: operator\n", encoding="utf-8")
    state = InstallerState()
    monkeypatch.setattr(state, "runtime_paths", lambda: RuntimePaths(Path("chart"), Path("values"), overlay))
    observed = []
    monkeypatch.setattr("auplc_installer.cli._provision_gpu_access_for_local_hardware", lambda **_kwargs: None)
    monkeypatch.setattr("auplc_installer.cli.remove_runtime", lambda: observed.append("removed"))
    monkeypatch.setattr("auplc_installer.cli.time.sleep", lambda _seconds: None)
    monkeypatch.setattr(
        install, lambda current_state: observed.append((current_state.access_mode, current_state.admin_username))
    )

    reinstall(state)

    assert observed == ["removed", ("local", "operator")]


def test_local_overlay_retains_single_node_runtime_behavior(tmp_path: Path) -> None:
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
        overlay_path=overlay,
    )

    rendered = __import__("yaml").safe_load(overlay.read_text())
    assert rendered["custom"]["singleNodeMode"] is True
