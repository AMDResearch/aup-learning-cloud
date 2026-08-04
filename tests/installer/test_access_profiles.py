from __future__ import annotations

import itertools
from pathlib import Path

import pytest
import yaml

from auplc_installer.catalog import COURSE_CATALOG, NONE_SENTINEL, CourseSelection
from auplc_installer.cli import _preserve_access_settings_for_upgrade
from auplc_installer.gpu import GpuConfig, append_product
from auplc_installer.overlay import GPU_RESOURCE_KEYS, emit_overlay, try_load_access_settings_from_overlay
from auplc_installer.state import InstallerState


def _gpu_config() -> GpuConfig:
    config = GpuConfig()
    append_product(config, "AMD_Radeon_8060S_Graphics")
    return config


def _render(*, courses: CourseSelection, access_mode: str = "personal") -> str:
    return emit_overlay(
        _gpu_config(),
        image_registry="ghcr.io/amdresearch",
        image_tag="latest",
        courses=courses,
        access_mode=access_mode,
        admin_username="operator",
    )


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueKeyLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[str, object]:
    mapping: dict[str, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        assert isinstance(key, str)
        assert key not in mapping, f"duplicate YAML key: {key}"
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


def _load_unique(text: str) -> dict[str, object]:
    rendered = yaml.load(text, Loader=_UniqueKeyLoader)
    assert isinstance(rendered, dict)
    return rendered


def _all_course_selections() -> list[CourseSelection]:
    keys = tuple(course.key for course in COURSE_CATALOG)
    selections = [CourseSelection.default(), CourseSelection(picks=[NONE_SENTINEL])]
    selections.extend(
        CourseSelection(picks=list(picks))
        for count in range(1, len(keys) + 1)
        for picks in itertools.combinations(keys, count)
    )
    return selections


def test_personal_profile_emits_minimal_canonical_provider() -> None:
    rendered = _load_unique(_render(courses=CourseSelection.default()))
    custom = rendered["custom"]
    assert isinstance(custom, dict)

    assert custom["auth"] == {"autoLogin": True}
    assert "authMode" not in custom
    assert custom["runtimeLimitEnabled"] is False
    assert custom["quota"] == {"enabled": False}
    assert custom["adminUser"] == {"enabled": False}


def test_local_profile_emits_minimal_native_provider() -> None:
    rendered = _load_unique(_render(courses=CourseSelection.default(), access_mode="local"))
    custom = rendered["custom"]
    assert isinstance(custom, dict)

    assert custom["auth"] == {"native": True}
    assert "authMode" not in custom
    assert custom["runtimeLimitEnabled"] is False
    assert custom["quota"] == {"enabled": False}
    assert custom["adminUser"] == {
        "enabled": True,
        "username": "operator",
        "existingSecret": "jupyterhub-admin-credentials",
    }


@pytest.mark.parametrize("courses", _all_course_selections())
@pytest.mark.parametrize("access_mode", ("personal", "local"))
def test_profile_resources_are_emitted_only_for_selected_courses(courses: CourseSelection, access_mode: str) -> None:
    text = _render(courses=courses, access_mode=access_mode)
    rendered = _load_unique(text)
    custom = rendered["custom"]
    assert isinstance(custom, dict)
    if not any(courses.is_selected(resource) for resource in GPU_RESOURCE_KEYS):
        assert "resources" not in custom
    else:
        resources = custom["resources"]
        assert isinstance(resources, dict)
        assert text.count("\n  resources:\n") == 1


def test_upgrade_preserves_canonical_local_profile_and_admin_username(tmp_path: Path) -> None:
    overlay = tmp_path / "values.local.yaml"
    overlay.write_text(_render(courses=CourseSelection.default(), access_mode="local"), encoding="utf-8")
    state = InstallerState()

    _preserve_access_settings_for_upgrade(state, overlay)

    assert (state.access_mode, state.admin_username) == ("local", "operator")
    assert try_load_access_settings_from_overlay(overlay) == ("local", "operator")


def test_upgrade_migrates_legacy_personal_profile_with_headers(tmp_path: Path) -> None:
    overlay = tmp_path / "values.local.yaml"
    overlay.write_text(
        "# Access mode   : personal\n# Admin username: admin\ncustom:\n  authMode: auto-login\n",
        encoding="utf-8",
    )
    state = InstallerState()

    _preserve_access_settings_for_upgrade(state, overlay)

    assert (state.access_mode, state.admin_username) == ("personal", "admin")
    migrated = _load_unique(_render(courses=CourseSelection.default(), access_mode=state.access_mode))
    custom = migrated["custom"]
    assert isinstance(custom, dict)
    assert custom["auth"] == {"autoLogin": True}
    assert "authMode" not in custom


def test_upgrade_migrates_legacy_local_profile_with_headers(tmp_path: Path) -> None:
    overlay = tmp_path / "values.local.yaml"
    overlay.write_text(
        '# Access mode   : local\n# Admin username: operator\ncustom:\n  authMode: "local"\n',
        encoding="utf-8",
    )
    state = InstallerState()

    _preserve_access_settings_for_upgrade(state, overlay)

    migrated = _load_unique(_render(courses=CourseSelection.default(), access_mode=state.access_mode))
    custom = migrated["custom"]
    assert isinstance(custom, dict)
    assert custom["auth"] == {"native": True}
    assert "authMode" not in custom
