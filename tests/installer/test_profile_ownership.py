from __future__ import annotations

from pathlib import Path

import pytest

from auplc_installer.catalog import CourseSelection
from auplc_installer.cli import _preserve_access_settings_for_upgrade
from auplc_installer.gpu import GpuConfig, append_product
from auplc_installer.overlay import emit_overlay, generate_values_overlay
from auplc_installer.state import InstallerState
from auplc_installer.util import InstallerError


def _overlay(access_mode: str = "local") -> str:
    config = GpuConfig()
    append_product(config, "AMD_Radeon_8060S_Graphics")
    return emit_overlay(
        config,
        image_registry="ghcr.io/amdresearch",
        image_tag="latest",
        courses=CourseSelection.default(),
        access_mode=access_mode,
        admin_username="operator",
    )


def test_upgrade_may_overwrite_user_modified_body_when_headers_are_recoverable(tmp_path: Path) -> None:
    overlay = tmp_path / "values.local.yaml"
    overlay.write_text(
        "# Access mode   : local\n# Admin username: operator\ncustom:\n  auth:\n    github: true\n",
        encoding="utf-8",
    )
    state = InstallerState()

    _preserve_access_settings_for_upgrade(state, overlay)
    config = GpuConfig()
    append_product(config, "AMD_Radeon_8060S_Graphics")
    generate_values_overlay(
        config,
        image_registry="ghcr.io/amdresearch",
        image_tag="latest",
        courses=CourseSelection.default(),
        access_mode=state.access_mode,
        admin_username=state.admin_username,
        overlay_path=overlay,
    )

    assert (state.access_mode, state.admin_username) == ("local", "operator")
    assert "    native: true\n" in overlay.read_text(encoding="utf-8")
    assert "    github: true\n" not in overlay.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "text",
    (
        "custom:\n  auth:\n    github: true\n",
        "# Access mode   : local\ncustom:\n  auth:\n    native: true\n",
        "# Access mode   : local\n# Access mode   : personal\n# Admin username: operator\ncustom: {}\n",
        "# Access mode   : github\n# Admin username: operator\ncustom: {}\n",
        "# Access mode   : local\n# Admin username: Admin\ncustom: {}\n",
    ),
)
def test_upgrade_skips_profile_recovery_when_headers_are_unusable(tmp_path: Path, text: str) -> None:
    overlay = tmp_path / "values.local.yaml"
    overlay.write_text(text, encoding="utf-8")
    state = InstallerState()

    _preserve_access_settings_for_upgrade(state, overlay)

    assert (state.access_mode, state.admin_username) == ("", "")


def test_upgrade_ignores_auth_like_values_under_hub(tmp_path: Path) -> None:
    state = InstallerState()
    overlay = tmp_path / "values.local.yaml"
    overlay.write_text(_overlay("personal") + "hub:\n  authMode: ignored\n", encoding="utf-8")

    _preserve_access_settings_for_upgrade(state, overlay)

    assert (state.access_mode, state.admin_username) == ("personal", "admin")


@pytest.mark.parametrize("username", ("Admin", "admin:name", 'admin"name', "admin\nname", "admin name", "a" * 65))
def test_personal_profile_rejects_unsafe_admin_username(username: str) -> None:
    with pytest.raises(InstallerError, match="lowercase ASCII"):
        _overlay("personal") if username == "operator" else emit_overlay(
            GpuConfig(),
            image_registry="ghcr.io/amdresearch",
            image_tag="latest",
            courses=CourseSelection.default(),
            admin_username=username,
        )


def test_personal_profile_canonicalizes_safe_admin_username_to_admin() -> None:
    config = GpuConfig()
    append_product(config, "AMD_Radeon_8060S_Graphics")

    rendered = emit_overlay(
        config,
        image_registry="ghcr.io/amdresearch",
        image_tag="latest",
        courses=CourseSelection.default(),
        admin_username="operator",
    )

    assert "# Admin username: admin\n" in rendered
