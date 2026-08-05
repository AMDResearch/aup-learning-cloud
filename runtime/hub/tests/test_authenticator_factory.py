import importlib
import importlib.util
import sys
import types
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import anyio
import pytest

ROOT = Path(__file__).resolve().parents[1]
AUTHENTICATORS = ROOT / "core" / "authenticators" / "__init__.py"
CONFIG = ROOT / "core" / "config.py"


def _install_core_packages(module_patch: pytest.MonkeyPatch) -> types.ModuleType:
    core = types.ModuleType("core")
    core.__path__ = [str(ROOT / "core")]
    authenticators = types.ModuleType("core.authenticators")
    authenticators.__path__ = [str(ROOT / "core" / "authenticators")]
    module_patch.setitem(sys.modules, "core", core)
    module_patch.setitem(sys.modules, "core.authenticators", authenticators)
    core.authenticators = authenticators
    return core


@contextmanager
def _loaded_factory(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[types.ModuleType, types.ModuleType]]:
    with monkeypatch.context() as module_patch:
        core = _install_core_packages(module_patch)
        config_spec = importlib.util.spec_from_file_location("core.config", CONFIG)
        assert config_spec is not None and config_spec.loader is not None
        config = importlib.util.module_from_spec(config_spec)
        module_patch.setitem(sys.modules, "core.config", config)
        core.config = config
        config_spec.loader.exec_module(config)

        auto_login = types.ModuleType("core.authenticators.auto_login")
        auto_login.AutoLoginAuthenticator = type("AutoLoginAuthenticator", (), {})
        firstuse = types.ModuleType("core.authenticators.firstuse")
        firstuse.CustomFirstUseAuthenticator = type("CustomFirstUseAuthenticator", (), {"prefix": ""})
        github_app = types.ModuleType("core.authenticators.github_app")
        github_app.CustomGitHubOAuthenticator = type("CustomGitHubOAuthenticator", (), {"prefix": "github:"})
        github_app.GITHUB_USERNAME_PREFIX = "github:"
        jwt = types.ModuleType("core.authenticators.jwt")
        jwt.RemoteLabAuthenticator = type("RemoteLabAuthenticator", (), {})
        multi = types.ModuleType("core.authenticators.multi")
        multi.CustomMultiAuthenticator = type("CustomMultiAuthenticator", (), {})
        for fake_module in (auto_login, firstuse, github_app, jwt, multi):
            module_patch.setitem(sys.modules, fake_module.__name__, fake_module)

        spec = importlib.util.spec_from_file_location("core.authenticators", AUTHENTICATORS)
        assert spec is not None and spec.loader is not None
        authenticator_factory = importlib.util.module_from_spec(spec)
        module_patch.setitem(sys.modules, "core.authenticators", authenticator_factory)
        core.authenticators = authenticator_factory
        spec.loader.exec_module(authenticator_factory)
        yield authenticator_factory, config


def test_factory_preserves_identity_prefix_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    with _loaded_factory(monkeypatch) as (factory, _config):
        assert factory.GITHUB_USERNAME_PREFIX == "github:"
        assert factory.CustomGitHubOAuthenticator.prefix == "github:"
        assert factory.CustomFirstUseAuthenticator.prefix == ""
        assert "CustomLocalAuthenticator" not in factory.__all__


@pytest.mark.parametrize(
    ("capabilities", "expected_name", "expected_allow_all"),
    [
        ((True, False, False, False), "AutoLoginAuthenticator", (("Authenticator", True),)),
        ((False, True, False, False), "dummy", (("Authenticator", True),)),
        ((False, False, True, False), "CustomFirstUseAuthenticator", (("Authenticator", True),)),
        ((False, False, False, True), "CustomGitHubOAuthenticator", (("GitHubOAuthenticator", False),)),
        (
            (False, False, True, True),
            "CustomMultiAuthenticator",
            (("GitHubOAuthenticator", False), ("MultiAuthenticator", True)),
        ),
    ],
)
def test_factory_configures_authenticator_for_canonical_capabilities(
    monkeypatch: pytest.MonkeyPatch,
    capabilities: tuple[bool, bool, bool, bool],
    expected_name: str,
    expected_allow_all: tuple[tuple[str, bool], ...],
) -> None:
    with _loaded_factory(monkeypatch) as (factory, config):
        c = types.SimpleNamespace(
            JupyterHub=types.SimpleNamespace(),
            Authenticator=types.SimpleNamespace(),
            GitHubOAuthenticator=types.SimpleNamespace(),
            MultiAuthenticator=types.SimpleNamespace(),
        )
        factory.configure_authenticator(c, config.AuthCapabilities(*capabilities))

        selected = c.JupyterHub.authenticator_class
        assert selected == "dummy" if expected_name == "dummy" else selected.__name__ == expected_name
        for authenticator_name, allow_all in expected_allow_all:
            assert getattr(c, authenticator_name).allow_all is allow_all
        if capabilities == (False, False, True, True):
            assert c.MultiAuthenticator.authenticators == [
                {"authenticator_class": factory.CustomGitHubOAuthenticator, "url_prefix": "/github"},
                {
                    "authenticator_class": factory.CustomFirstUseAuthenticator,
                    "url_prefix": "/native",
                    "config": {"prefix": "", "allow_all": True},
                },
            ]


def test_factory_keeps_multi_github_allow_all_available_for_later_operator_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _loaded_factory(monkeypatch) as (factory, config):
        c = types.SimpleNamespace(
            JupyterHub=types.SimpleNamespace(),
            Authenticator=types.SimpleNamespace(),
            GitHubOAuthenticator=types.SimpleNamespace(),
            MultiAuthenticator=types.SimpleNamespace(),
        )
        factory.configure_authenticator(c, config.AuthCapabilities(False, False, True, True))

        c.GitHubOAuthenticator.allow_all = True

        assert c.GitHubOAuthenticator.allow_all is True
        assert "config" not in c.MultiAuthenticator.authenticators[0]


def test_factory_multi_github_child_enforces_org_policy_until_class_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "tests"))
    support_module = importlib.import_module("github_authenticator_support")
    loaded_authenticators = support_module.loaded_authenticators
    with _loaded_factory(monkeypatch) as (factory, config), loaded_authenticators(monkeypatch) as modules:
        c = types.SimpleNamespace(
            JupyterHub=types.SimpleNamespace(),
            Authenticator=types.SimpleNamespace(),
            GitHubOAuthenticator=types.SimpleNamespace(),
            MultiAuthenticator=types.SimpleNamespace(),
        )
        factory.configure_authenticator(c, config.AuthCapabilities(False, False, True, True))
        github_child = c.MultiAuthenticator.authenticators[0]
        authenticator = modules.github.CustomGitHubOAuthenticator()
        authenticator.allow_all = c.GitHubOAuthenticator.allow_all
        authenticator.allowed_organizations = {"auplc"}
        authenticator.organization_members = {"auplc": {"octo"}}

        member = anyio.run(authenticator.authenticate, None, {"login": "octo"})
        outsider = anyio.run(authenticator.authenticate, None, {"login": "outside"})

        c.GitHubOAuthenticator.allow_all = True
        authenticator.allow_all = c.GitHubOAuthenticator.allow_all
        overridden_outsider = anyio.run(authenticator.authenticate, None, {"login": "outside"})

        assert github_child == {"authenticator_class": factory.CustomGitHubOAuthenticator, "url_prefix": "/github"}
        assert member["name"] == "octo"
        assert outsider is None
        assert overridden_outsider["name"] == "outside"


@pytest.mark.parametrize(
    "capabilities",
    [
        (False, False, False, False),
        (True, False, True, False),
        (False, True, False, True),
        (True, True, False, False),
    ],
)
def test_factory_rejects_invalid_capabilities_before_authenticator_construction(
    monkeypatch: pytest.MonkeyPatch, capabilities: tuple[bool, bool, bool, bool]
) -> None:
    with _loaded_factory(monkeypatch) as (factory, config), pytest.raises(config.AuthConfigurationError):
        factory.configure_authenticator(types.SimpleNamespace(), config.AuthCapabilities(*capabilities))


@pytest.mark.parametrize(
    "malformed_auth",
    (None, 1, True, (), object(), "auto-login", "dummy", "local", "github", "multi", "unexpected"),
)
def test_factory_rejects_malformed_runtime_inputs(monkeypatch: pytest.MonkeyPatch, malformed_auth) -> None:
    with _loaded_factory(monkeypatch) as (factory, config), pytest.raises(config.AuthConfigurationError):
        factory.configure_authenticator(types.SimpleNamespace(), malformed_auth)


def test_factory_module_cleanup_survives_a_forced_test_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    module_names = (
        "core",
        "core.config",
        "core.authenticators",
        "core.authenticators.auto_login",
        "core.authenticators.firstuse",
        "core.authenticators.github_app",
        "core.authenticators.jwt",
        "core.authenticators.multi",
    )
    missing = object()
    original_modules = {name: sys.modules.get(name, missing) for name in module_names}

    with pytest.raises(AssertionError, match="forced cleanup probe"), _loaded_factory(monkeypatch):
        raise AssertionError("forced cleanup probe")

    for name, original_module in original_modules.items():
        if original_module is missing:
            assert name not in sys.modules
        else:
            assert sys.modules[name] is original_module
