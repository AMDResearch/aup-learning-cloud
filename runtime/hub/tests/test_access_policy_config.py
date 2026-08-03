import importlib.util
import sys
import types
import warnings
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "core" / "config.py"
AUTH_FLAGS = ("autoLogin", "dummy", "native", "github")
CANONICAL_PROVIDERS = (
    (True, False, False, False),
    (False, True, False, False),
    (False, False, True, False),
    (False, False, False, True),
    (False, False, True, True),
)
LEGACY_POLICIES = {
    "auto-login": "all",
    "dummy": "all",
    "local": "all",
    "github": "group-mapped",
    "multi": "group-mapped",
}


@pytest.fixture
def config_module(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("task7_access_policy_config", CONFIG)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def write_config(tmp_path: Path, data: dict[str, object]) -> Path:
    path = tmp_path / "hub-config.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def canonical_auth(flags: tuple[bool, bool, bool, bool]) -> dict[str, dict[str, bool]]:
    return {"auth": dict(zip(AUTH_FLAGS, flags, strict=True))}


@pytest.mark.parametrize("providers", CANONICAL_PROVIDERS)
def test_canonical_providers_default_to_group_mapped_access(
    config_module: types.ModuleType, tmp_path: Path, providers: tuple[bool, bool, bool, bool]
) -> None:
    hub_config = config_module.HubConfig.init(write_config(tmp_path, canonical_auth(providers)))

    assert hub_config.resources.effective_access_policy == "group-mapped"


def test_absent_auth_forms_default_to_group_mapped_access(config_module: types.ModuleType, tmp_path: Path) -> None:
    hub_config = config_module.HubConfig.init(write_config(tmp_path, {"resources": {}}))

    assert hub_config.resources.effective_access_policy == "group-mapped"


@pytest.mark.parametrize(("auth_mode", "expected_policy"), LEGACY_POLICIES.items())
def test_legacy_modes_preserve_implicit_resource_access_policy(
    config_module: types.ModuleType, tmp_path: Path, auth_mode: str, expected_policy: str
) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        hub_config = config_module.HubConfig.init(write_config(tmp_path, {"authMode": auth_mode}))

    assert hub_config.resources.effective_access_policy == expected_policy


@pytest.mark.parametrize("providers", CANONICAL_PROVIDERS)
@pytest.mark.parametrize("access_policy", ("all", "group-mapped"))
def test_explicit_policy_is_independent_of_canonical_provider_and_runtime_policy(
    config_module: types.ModuleType,
    tmp_path: Path,
    providers: tuple[bool, bool, bool, bool],
    access_policy: str,
) -> None:
    raw_config: dict[str, object] = canonical_auth(providers)
    raw_config.update(
        {
            "singleNodeMode": True,
            "quota": {"enabled": False},
            "resources": {"accessPolicy": access_policy},
        }
    )

    hub_config = config_module.HubConfig.init(write_config(tmp_path, raw_config))

    assert hub_config.resources.effective_access_policy == access_policy
    assert hub_config.single_node_mode is True
    assert hub_config.quota_enabled is False


@pytest.mark.parametrize("access_policy", ("all", "group-mapped"))
@pytest.mark.parametrize("auth_mode", tuple(LEGACY_POLICIES))
def test_explicit_policy_overrides_legacy_implicit_policy(
    config_module: types.ModuleType, tmp_path: Path, auth_mode: str, access_policy: str
) -> None:
    raw_config = {"authMode": auth_mode, "resources": {"accessPolicy": access_policy}}

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        hub_config = config_module.HubConfig.init(write_config(tmp_path, raw_config))

    assert hub_config.resources.effective_access_policy == access_policy


@pytest.mark.parametrize("invalid_policy", ("unknown", None, True, 1, ["all"]))
def test_direct_parser_rejects_invalid_explicit_access_policy(
    config_module: types.ModuleType, tmp_path: Path, invalid_policy: object
) -> None:
    raw_config = {"resources": {"accessPolicy": invalid_policy}}

    with pytest.raises(ValidationError):
        config_module.HubConfig.init(write_config(tmp_path, raw_config))
