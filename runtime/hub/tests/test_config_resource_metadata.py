# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import importlib.util
import sys
import types
import warnings
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core"

if "core" not in sys.modules:
    core_module = types.ModuleType("core")
    core_module.__path__ = [str(CORE)]
    sys.modules["core"] = core_module


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


config = load_module("core.config", CORE / "config.py")
ParsedConfig = config.ParsedConfig
ResourceMetadata = config.ResourceMetadata

ProviderFlags = tuple[bool, bool, bool, bool]
AUTH_FLAG_NAMES = ("autoLogin", "dummy", "native", "github")
VALID_CANONICAL_AUTH = (
    ((True, False, False, False), "auto-login"),
    ((False, True, False, False), "dummy"),
    ((False, False, True, False), "local"),
    ((False, False, False, True), "github"),
    ((False, False, True, True), "multi"),
)
INVALID_CANONICAL_AUTH = (
    (False, False, False, False),
    (True, True, False, False),
    (True, False, True, False),
    (True, False, False, True),
    (False, True, True, False),
    (False, True, False, True),
    (True, True, True, False),
    (True, True, False, True),
    (True, False, True, True),
    (False, True, True, True),
    (True, True, True, True),
)


def write_hub_config(tmp_path: Path, contents: str) -> Path:
    config_path = tmp_path / "hub-config.yaml"
    config_path.write_text(contents, encoding="utf-8")
    return config_path


def canonical_auth_yaml(flags: ProviderFlags) -> str:
    lines = ["auth:"]
    lines.extend(f"  {name}: {str(enabled).lower()}" for name, enabled in zip(AUTH_FLAG_NAMES, flags))
    return "\n".join(lines) + "\n"


def assert_auth_configuration_rejected(tmp_path: Path, contents: str, expected_message: str) -> None:
    with pytest.raises(ValueError) as raised:
        config.HubConfig.init(write_hub_config(tmp_path, contents))

    assert raised.value.__class__ is config.AuthConfigurationError
    assert expected_message in str(raised.value)


@pytest.fixture(autouse=True)
def restore_hub_config_singleton(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config.HubConfig, "_instance", None)
    monkeypatch.setattr(config.HubConfig, "_initialized", False)


def test_resource_metadata_default_path_omitted_or_null_stays_none():
    assert ResourceMetadata().defaultPath is None
    assert ResourceMetadata(defaultPath=None).defaultPath is None


@pytest.mark.parametrize(
    ("default_path", "expected_message"),
    [
        ("", "defaultPath cannot be empty"),
        ("   ", "defaultPath cannot be empty"),
        ("workspace/CV", "defaultPath must be an absolute container path"),
        ("/opt/../secret", "defaultPath cannot contain '..' segments"),
        ("/opt/\x00secret", "defaultPath cannot contain NUL bytes"),
    ],
)
def test_resource_metadata_default_path_rejects_invalid_syntax(default_path: str, expected_message: str):
    with pytest.raises(ValidationError, match=expected_message):
        ResourceMetadata(defaultPath=default_path)


@pytest.mark.parametrize(
    ("default_path", "expected_path"),
    [
        ("/", "/"),
        ("/opt/workspace/CV", "/opt/workspace/CV"),
        ("/home/jovyan/", "/home/jovyan"),
        ("//opt/./workspace//CV/", "/opt/workspace/CV"),
        ("  /home/jovyan/  ", "/home/jovyan"),
    ],
)
def test_resource_metadata_default_path_normalizes_valid_paths(default_path: str, expected_path: str):
    metadata = ResourceMetadata(defaultPath=default_path)

    assert metadata.defaultPath == expected_path


def test_code_server_extra_trusted_domains_default_to_empty_list():
    parsed_config = ParsedConfig()

    assert parsed_config.codeServer.extraTrustedDomains == []


def test_code_server_extra_trusted_domains_parse_from_config():
    parsed_config = ParsedConfig.model_validate(
        {"codeServer": {"extraTrustedDomains": ["docs.example.edu", "git.example.edu"]}}
    )

    assert parsed_config.codeServer.extraTrustedDomains == ["docs.example.edu", "git.example.edu"]


def test_legacy_github_mode_preserves_existing_runtime_defaults(tmp_path: Path):
    hub_config = config.HubConfig.init(write_hub_config(tmp_path, "authMode: github\n"))

    assert hub_config.auth_mode == "github"
    assert hub_config.single_node_mode is False
    assert hub_config.quota_enabled is True


def test_absent_auth_forms_preserve_existing_auto_login_compatibility(tmp_path: Path):
    hub_config = config.HubConfig.init(write_hub_config(tmp_path, "resources: {}\n"))

    assert hub_config.auth_mode == "auto-login"


@pytest.mark.parametrize(("flags", "expected_mode"), VALID_CANONICAL_AUTH)
def test_canonical_auth_flags_normalize_to_capabilities_and_neutral_policy(
    tmp_path: Path, flags: ProviderFlags, expected_mode: str
):
    hub_config = config.HubConfig.init(write_hub_config(tmp_path, canonical_auth_yaml(flags)))

    assert hub_config.auth_mode == expected_mode
    assert (hub_config.auth.auto_login, hub_config.auth.dummy, hub_config.auth.native, hub_config.auth.github) == flags
    assert hub_config.single_node_mode is False
    assert hub_config.quota_enabled is True


@pytest.mark.parametrize("flags", INVALID_CANONICAL_AUTH)
def test_canonical_auth_rejects_each_invalid_boolean_combination(tmp_path: Path, flags: ProviderFlags):
    assert_auth_configuration_rejected(tmp_path, canonical_auth_yaml(flags), "native + github")


@pytest.mark.parametrize(
    ("legacy_mode", "expected_flags", "expected_single_node", "expected_quota"),
    [
        ("auto-login", (True, False, False, False), True, False),
        ("dummy", (False, True, False, False), False, False),
        ("github", (False, False, False, True), False, True),
        ("local", (False, False, True, False), True, False),
        ("multi", (False, False, True, True), False, True),
    ],
)
def test_explicit_legacy_modes_map_to_capabilities_and_preserve_policy_defaults(
    tmp_path: Path, legacy_mode: str, expected_flags: ProviderFlags, expected_single_node: bool, expected_quota: bool
):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        hub_config = config.HubConfig.init(write_hub_config(tmp_path, f"authMode: {legacy_mode}\n"))

    assert hub_config.auth_mode == legacy_mode
    assert (
        hub_config.auth.auto_login,
        hub_config.auth.dummy,
        hub_config.auth.native,
        hub_config.auth.github,
    ) == expected_flags
    assert hub_config.single_node_mode is expected_single_node
    assert hub_config.quota_enabled is expected_quota


def test_legacy_auth_emits_one_actionable_deprecation_warning_per_initialization(tmp_path: Path):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        hub_config = config.HubConfig.init(write_hub_config(tmp_path, "authMode: local\n"))
        _ = hub_config.auth
        _ = hub_config.auth

    legacy_warnings = [warning for warning in caught if issubclass(warning.category, DeprecationWarning)]
    assert len(legacy_warnings) == 1
    assert "authMode" in str(legacy_warnings[0].message)
    assert "auth" in str(legacy_warnings[0].message)


def test_absent_auth_forms_use_compatibility_auto_login_with_neutral_defaults(tmp_path: Path):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        hub_config = config.HubConfig.init(write_hub_config(tmp_path, "resources: {}\n"))

    assert not [warning for warning in caught if issubclass(warning.category, DeprecationWarning)]
    assert hub_config.auth_mode == "auto-login"
    assert (hub_config.auth.auto_login, hub_config.auth.dummy, hub_config.auth.native, hub_config.auth.github) == (
        True,
        False,
        False,
        False,
    )
    assert hub_config.single_node_mode is False
    assert hub_config.quota_enabled is True


def test_mixed_legacy_and_canonical_auth_forms_are_rejected(tmp_path: Path):
    assert_auth_configuration_rejected(tmp_path, "authMode: local\nauth: {}\n", "both authMode and auth")


@pytest.mark.parametrize(
    "contents",
    [
        "auth: []\n",
        'auth:\n  autoLogin: "true"\n',
        "auth:\n  native: 1\n",
        "auth:\n  autoLogin: true\n  ldap: false\n",
    ],
)
def test_malformed_canonical_auth_is_rejected_before_hub_setup(tmp_path: Path, contents: str):
    assert_auth_configuration_rejected(tmp_path, contents, "auth")


@pytest.mark.parametrize(
    ("contents", "expected_single_node", "expected_quota"),
    [
        ("auth:\n  native: true\nsingleNodeMode: true\nquota:\n  enabled: false\n", True, False),
        ("authMode: local\nsingleNodeMode: false\nquota:\n  enabled: true\n", False, True),
    ],
)
def test_explicit_runtime_policy_values_override_auth_compatibility_defaults(
    tmp_path: Path, contents: str, expected_single_node: bool, expected_quota: bool
):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        hub_config = config.HubConfig.init(write_hub_config(tmp_path, contents))

    assert hub_config.single_node_mode is expected_single_node
    assert hub_config.quota_enabled is expected_quota


def test_hub_config_singleton_is_reset_before_each_case():
    assert config.HubConfig.is_initialized() is False
    with pytest.raises(RuntimeError):
        config.HubConfig.get()


@pytest.mark.parametrize("contents", ["[]\n", "false\n", "0\n", '""\n'])
def test_falsey_non_mapping_yaml_roots_are_rejected(tmp_path: Path, contents: str):
    assert_auth_configuration_rejected(tmp_path, contents, "YAML mapping")


def test_null_legacy_mode_is_absent_compatibility_without_warning(tmp_path: Path):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        hub_config = config.HubConfig.init(write_hub_config(tmp_path, "authMode: null\n"))

    assert hub_config.auth_mode == "auto-login"
    assert not [warning for warning in caught if issubclass(warning.category, DeprecationWarning)]


def test_null_legacy_mode_with_canonical_auth_is_rejected(tmp_path: Path):
    assert_auth_configuration_rejected(tmp_path, "authMode: null\nauth:\n  native: true\n", "both authMode and auth")


def test_failed_initializations_preserve_or_recover_singleton_state(tmp_path: Path):
    with pytest.raises(ValidationError, match="Input should be a valid dictionary"):
        config.HubConfig.init(write_hub_config(tmp_path, "quota: invalid\n"))
    assert config.HubConfig._instance is None
    assert config.HubConfig._initialized is False
    with pytest.raises(RuntimeError):
        config.HubConfig.get()

    valid = config.HubConfig.init(write_hub_config(tmp_path, "auth:\n  native: true\n"))
    with pytest.raises(ValidationError, match="Input should be a valid dictionary"):
        config.HubConfig.init(write_hub_config(tmp_path, "auth:\n  github: true\nquota: invalid\n"))
    assert config.HubConfig.get() is valid
    assert valid.auth.native is True
