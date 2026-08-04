import importlib.util
import itertools
import json
import subprocess
import sys
import warnings
from collections.abc import Mapping
from pathlib import Path

import pytest
import yaml

from scripts.generate_values_schema import remove_descriptions

ROOT = Path(__file__).resolve().parents[2]
CHART = "runtime/chart"
AUTH_KEYS = ("autoLogin", "dummy", "native", "github")
LEGACY_MODES = ("auto-login", "dummy", "github", "local", "multi")
VALID_COMBINATIONS = {
    (True, False, False, False),
    (False, True, False, False),
    (False, False, True, False),
    (False, False, False, True),
    (False, False, True, True),
}
ALL_COMBINATIONS = tuple(itertools.product((False, True), repeat=len(AUTH_KEYS)))
INVALID_COMBINATIONS = tuple(case for case in ALL_COMBINATIONS if case not in VALID_COMBINATIONS)


def render(*settings: str, string_settings: tuple[str, ...] = ()) -> subprocess.CompletedProcess[str]:
    command = ["helm", "template", "jupyterhub", CHART]
    for setting in settings:
        command.extend(("--set", setting))
    for setting in string_settings:
        command.extend(("--set-string", setting))
    return subprocess.run(command, cwd=ROOT, check=False, capture_output=True, text=True)


def auth_settings(combination: tuple[bool, bool, bool, bool]) -> tuple[str, ...]:
    return tuple(
        f"custom.auth.{key}={str(enabled).lower()}" for key, enabled in zip(AUTH_KEYS, combination, strict=True)
    )


def rendered_documents(output: str) -> list[Mapping[str, object]]:
    return [document for document in yaml.safe_load_all(output) if isinstance(document, dict)]


def document_by_kind(documents: list[Mapping[str, object]], kind: str) -> Mapping[str, object]:
    return next(document for document in documents if document.get("kind") == kind)


@pytest.mark.parametrize("combination", sorted(VALID_COMBINATIONS))
def test_chart_accepts_canonical_auth_truth_table(
    combination: tuple[bool, bool, bool, bool],
) -> None:
    result = render(*auth_settings(combination))

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("combination", INVALID_COMBINATIONS)
def test_chart_rejects_invalid_canonical_auth_combinations(
    combination: tuple[bool, bool, bool, bool],
) -> None:
    result = render(*auth_settings(combination))

    assert result.returncode != 0
    assert "values don't meet the specifications" in result.stderr


@pytest.mark.parametrize("auth_mode", LEGACY_MODES)
def test_chart_accepts_legacy_auth_modes(auth_mode: str) -> None:
    result = render(f"custom.authMode={auth_mode}")

    assert result.returncode == 0, result.stderr


def test_chart_accepts_absent_auth_forms_without_injecting_a_default() -> None:
    result = render()

    assert result.returncode == 0, result.stderr
    config_map = document_by_kind(rendered_documents(result.stdout), "ConfigMap")
    custom = yaml.safe_load(config_map["data"]["hub-config.yaml"])
    assert "auth" not in custom
    assert "authMode" not in custom


def test_runtime_values_keep_auth_absent_and_resolve_to_compatibility_auto_login(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = subprocess.run(
        ["helm", "template", "jupyterhub", CHART, "-f", "runtime/values.yaml"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    config_map = document_by_kind(rendered_documents(result.stdout), "ConfigMap")
    rendered_config = config_map["data"]["hub-config.yaml"]
    custom = yaml.safe_load(rendered_config)
    assert "auth" not in custom
    assert "authMode" not in custom
    assert "runtimeLimitEnabled" not in custom

    config_path = tmp_path / "hub-config.yaml"
    config_path.write_text(rendered_config, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("runtime_values_config", ROOT / "runtime/hub/core/config.py")
    assert spec is not None
    assert spec.loader is not None
    config_module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, config_module)
    spec.loader.exec_module(config_module)
    hub_config = config_module.HubConfig.init(config_path)

    assert (
        hub_config.auth.auto_login,
        hub_config.auth.dummy,
        hub_config.auth.native,
        hub_config.auth.github,
    ) == (True, False, False, False)
    assert not hasattr(hub_config, "auth_mode")
    assert hub_config.runtime_limit_enabled is True
    assert hub_config.quota_enabled is True


def test_multi_node_example_emits_canonical_auth_and_runtime_policy() -> None:
    values = yaml.safe_load((ROOT / "runtime/values-multi-nodes.yaml.example").read_text(encoding="utf-8"))
    custom = values["custom"]

    assert custom["auth"] == {"native": True, "github": True}
    assert "authMode" not in custom
    assert custom["runtimeLimitEnabled"] is True
    assert custom["quota"]["enabled"] is True


@pytest.mark.parametrize(
    ("runtime_limit_enabled", "quota_enabled"),
    [(True, True), (True, False), (False, False)],
)
def test_chart_accepts_each_valid_quota_runtime_combination(runtime_limit_enabled: bool, quota_enabled: bool) -> None:
    result = render(
        f"custom.runtimeLimitEnabled={str(runtime_limit_enabled).lower()}",
        f"custom.quota.enabled={str(quota_enabled).lower()}",
    )

    assert result.returncode == 0, result.stderr


def test_chart_rejects_enabled_quota_with_unlimited_runtime() -> None:
    result = render("custom.runtimeLimitEnabled=false", "custom.quota.enabled=true")

    assert result.returncode != 0
    assert "values don't meet the specifications" in result.stderr


@pytest.mark.parametrize("quota_enabled", ("false", "yes"))
def test_chart_rejects_string_quota_enabled_values(quota_enabled: str) -> None:
    result = render(string_settings=(f"custom.quota.enabled={quota_enabled}",))

    assert result.returncode != 0
    assert "got string, want null or boolean" in result.stderr


def test_chart_rejects_integer_quota_enabled_value() -> None:
    result = render("custom.quota.enabled=1")

    assert result.returncode != 0
    assert "got number, want null or boolean" in result.stderr


def test_chart_rejects_array_quota_enabled_value() -> None:
    result = subprocess.run(
        ["helm", "template", "jupyterhub", CHART, "--set-json", "custom.quota.enabled=[]"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "got array, want null or boolean" in result.stderr


def test_chart_rejects_legacy_local_enabled_quota_without_runtime_limit() -> None:
    result = render("custom.authMode=local", "custom.quota.enabled=true")

    assert result.returncode != 0
    assert "values don't meet the specifications" in result.stderr


def test_chart_accepts_legacy_local_enabled_quota_with_explicit_runtime_limit() -> None:
    result = render(
        "custom.authMode=local",
        "custom.runtimeLimitEnabled=true",
        "custom.quota.enabled=true",
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "legacy_case",
    [
        ("local", False, False),
        ("multi", True, True),
    ],
)
def test_legacy_auth_overlay_preserves_runtime_defaults_after_shared_values_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, legacy_case: tuple[str, bool, bool]
) -> None:
    auth_mode, expected_runtime_limit, expected_quota = legacy_case
    overlay = tmp_path / "legacy-auth.yaml"
    overlay.write_text(f"custom:\n  authMode: {auth_mode}\n", encoding="utf-8")
    result = subprocess.run(
        [
            "helm",
            "template",
            "jupyterhub",
            CHART,
            "-f",
            "runtime/values.yaml",
            "-f",
            str(overlay),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    config_map = document_by_kind(rendered_documents(result.stdout), "ConfigMap")
    rendered_config = config_map["data"]["hub-config.yaml"]
    custom = yaml.safe_load(rendered_config)
    assert custom["authMode"] == auth_mode
    assert "auth" not in custom
    assert "runtimeLimitEnabled" not in custom

    config_path = tmp_path / "hub-config.yaml"
    config_path.write_text(rendered_config, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("legacy_chart_contract_config", ROOT / "runtime/hub/core/config.py")
    assert spec is not None
    assert spec.loader is not None
    config_module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, config_module)
    spec.loader.exec_module(config_module)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        hub_config = config_module.HubConfig.init(config_path)

    assert hub_config.runtime_limit_enabled is expected_runtime_limit
    assert hub_config.quota_enabled is expected_quota


def test_null_legacy_mode_renders_as_compatibility_absent_without_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = subprocess.run(
        ["helm", "template", "jupyterhub", CHART, "--set-json", "custom.authMode=null"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    config_map = document_by_kind(rendered_documents(result.stdout), "ConfigMap")
    rendered_config = config_map["data"]["hub-config.yaml"]
    custom = yaml.safe_load(rendered_config)
    assert "authMode" in custom
    assert custom["authMode"] is None
    assert "auth" not in custom

    config_path = tmp_path / "hub-config.yaml"
    config_path.write_text(rendered_config, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("chart_contract_config", ROOT / "runtime/hub/core/config.py")
    assert spec is not None
    assert spec.loader is not None
    config_module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, config_module)
    spec.loader.exec_module(config_module)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        hub_config = config_module.HubConfig.init(config_path)

    assert (
        hub_config.auth.auto_login,
        hub_config.auth.dummy,
        hub_config.auth.native,
        hub_config.auth.github,
    ) == (True, False, False, False)
    assert not hasattr(hub_config, "auth_mode")
    assert not [warning for warning in caught if issubclass(warning.category, DeprecationWarning)]


def test_chart_accepts_minimal_native_set_override() -> None:
    result = render("custom.auth.native=true")

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("auth_mode", LEGACY_MODES)
@pytest.mark.parametrize("auth_key", AUTH_KEYS)
def test_chart_rejects_mixed_legacy_and_canonical_auth(auth_mode: str, auth_key: str) -> None:
    result = render(f"custom.authMode={auth_mode}", f"custom.auth.{auth_key}=true")

    assert result.returncode != 0
    assert "values don't meet the specifications" in result.stderr


@pytest.mark.parametrize("auth_key", AUTH_KEYS)
def test_chart_rejects_null_legacy_mode_with_canonical_auth(auth_key: str) -> None:
    result = subprocess.run(
        [
            "helm",
            "template",
            "jupyterhub",
            CHART,
            "--set-json",
            "custom.authMode=null",
            "--set",
            f"custom.auth.{auth_key}=true",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "at '/custom': 'not' failed" in result.stderr


def test_chart_rejects_empty_canonical_auth_object() -> None:
    result = subprocess.run(
        ["helm", "template", "jupyterhub", CHART, "--set-json", "custom.auth={}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "values don't meet the specifications" in result.stderr


@pytest.mark.parametrize("auth_key", AUTH_KEYS)
def test_chart_rejects_non_boolean_canonical_auth_values(auth_key: str) -> None:
    result = render(string_settings=(f"custom.auth.{auth_key}=true",))

    assert result.returncode != 0
    assert f"at '/custom/auth/{auth_key}': got string, want boolean" in result.stderr


def test_chart_rejects_unknown_canonical_auth_key() -> None:
    result = render("custom.auth.native=true", "custom.auth.password=true")

    assert result.returncode != 0
    assert "additional properties 'password' not allowed" in result.stderr


@pytest.mark.parametrize(
    "provider_settings",
    [
        ("custom.auth.autoLogin=true",),
        ("custom.auth.dummy=true",),
        ("custom.auth.github=true",),
        (),
        ("custom.authMode=auto-login",),
        ("custom.authMode=dummy",),
        ("custom.authMode=github",),
    ],
)
def test_chart_rejects_admin_bootstrap_without_native(
    provider_settings: tuple[str, ...],
) -> None:
    result = render(
        *provider_settings,
        "custom.adminUser.enabled=true",
        "custom.adminUser.username=operator",
    )

    assert result.returncode != 0
    assert "values don't meet the specifications" in result.stderr


@pytest.mark.parametrize(
    "provider_settings",
    [
        ("custom.auth.native=true",),
        ("custom.auth.native=true", "custom.auth.github=true"),
        ("custom.authMode=local",),
        ("custom.authMode=multi",),
    ],
)
@pytest.mark.parametrize("existing_secret", ["", "external-admin-credentials"])
def test_native_admin_bootstrap_renders_generated_or_external_secret(
    provider_settings: tuple[str, ...], existing_secret: str
) -> None:
    settings = [
        *provider_settings,
        "custom.adminUser.enabled=true",
        "custom.adminUser.username=operator",
    ]
    if existing_secret:
        settings.append(f"custom.adminUser.existingSecret={existing_secret}")

    result = render(*settings)

    assert result.returncode == 0, result.stderr
    documents = rendered_documents(result.stdout)
    deployment = document_by_kind(documents, "Deployment")
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    environment = {entry["name"]: entry for entry in container["env"]}
    selected_secret = existing_secret or "jupyterhub-admin-credentials"
    assert environment["JUPYTERHUB_ADMIN_USERNAME"]["value"] == "operator"
    assert environment["JUPYTERHUB_ADMIN_PASSWORD"]["valueFrom"]["secretKeyRef"] == {
        "name": selected_secret,
        "key": "admin-password",
    }
    expected_token_ref = {"name": selected_secret, "key": "api-token"}
    if existing_secret:
        expected_token_ref["optional"] = True
    assert environment["JUPYTERHUB_API_TOKEN"]["valueFrom"]["secretKeyRef"] == expected_token_ref
    admin_secrets = [
        document
        for document in documents
        if document.get("kind") == "Secret"
        and document.get("metadata", {}).get("name") == "jupyterhub-admin-credentials"
    ]
    assert bool(admin_secrets) is not bool(existing_secret)
    if admin_secrets:
        assert set(admin_secrets[0]["data"]) == {"admin-username", "admin-password", "api-token"}


@pytest.mark.parametrize(
    "provider_settings",
    [("custom.auth.native=true",), ("custom.authMode=local",), ("custom.authMode=multi",)],
)
def test_native_admin_bootstrap_rejects_uppercase_username(
    provider_settings: tuple[str, ...],
) -> None:
    result = render(
        *provider_settings,
        "custom.adminUser.enabled=true",
        "custom.adminUser.username=Operator",
    )

    assert result.returncode != 0
    assert "does not match pattern" in result.stderr


def test_generated_values_schema_matches_yaml_source() -> None:
    yaml_schema = yaml.safe_load((ROOT / "runtime/chart/values.schema.yaml").read_text())
    json_schema = json.loads((ROOT / "runtime/chart/values.schema.json").read_text())

    assert json_schema == remove_descriptions(yaml_schema)
