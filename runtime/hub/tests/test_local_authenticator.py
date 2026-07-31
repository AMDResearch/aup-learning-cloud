import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LOCAL_AUTHENTICATOR = ROOT / "core" / "authenticators" / "local.py"
AUTHENTICATORS = ROOT / "core" / "authenticators" / "__init__.py"


class FakeFirstUseAuthenticator:
    def normalize_username(self, username):
        return username.lower()

    def _user_exists(self, username):
        return username == "existing"

    def check_password(self, username, password):
        return username == "existing" and password == "correct-password"


def test_local_authenticator_rejects_first_use_and_accepts_existing_password() -> None:
    core = types.ModuleType("core")
    authenticators = types.ModuleType("core.authenticators")
    firstuse = types.ModuleType("core.authenticators.firstuse")
    firstuse.CustomFirstUseAuthenticator = FakeFirstUseAuthenticator
    sys.modules.update(
        {
            "core": core,
            "core.authenticators": authenticators,
            "core.authenticators.firstuse": firstuse,
        }
    )
    spec = importlib.util.spec_from_file_location("core.authenticators.local", LOCAL_AUTHENTICATOR)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    authenticator = module.CustomLocalAuthenticator()

    assert (
        asyncio.run(authenticator.authenticate(None, {"username": "existing", "password": "correct-password"}))
        == "existing"
    )
    assert asyncio.run(authenticator.authenticate(None, {"username": "existing", "password": "wrong-password"})) is None
    assert asyncio.run(authenticator.authenticate(None, {"username": "new", "password": "valid-password"})) is None


def test_local_authenticator_rejects_noncanonical_usernames() -> None:
    core = types.ModuleType("core")
    authenticators = types.ModuleType("core.authenticators")
    firstuse = types.ModuleType("core.authenticators.firstuse")
    firstuse.CustomFirstUseAuthenticator = FakeFirstUseAuthenticator
    sys.modules.update(
        {
            "core": core,
            "core.authenticators": authenticators,
            "core.authenticators.firstuse": firstuse,
        }
    )
    spec = importlib.util.spec_from_file_location("core.authenticators.local", LOCAL_AUTHENTICATOR)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    authenticator = module.CustomLocalAuthenticator()

    for username in ("EXISTING", "existing:admin", 'existing"', "existing\n"):
        assert asyncio.run(authenticator.authenticate(None, {"username": username, "password": "correct-password"})) is None


def test_authenticator_factory_rejects_unknown_mode() -> None:
    core = types.ModuleType("core")
    authenticators = types.ModuleType("core.authenticators")
    sys.modules.update({"core": core, "core.authenticators": authenticators})
    for name, attribute in (
        ("auto_login", "AutoLoginAuthenticator"),
        ("firstuse", "CustomFirstUseAuthenticator"),
        ("github_app", "GITHUB_USERNAME_PREFIX"),
        ("jwt", "RemoteLabAuthenticator"),
        ("local", "CustomLocalAuthenticator"),
        ("multi", "CustomMultiAuthenticator"),
    ):
        module = types.ModuleType(f"core.authenticators.{name}")
        setattr(module, attribute, type(attribute, (), {}) if attribute != "GITHUB_USERNAME_PREFIX" else "github:")
        if name == "github_app":
            module.CustomGitHubOAuthenticator = type("CustomGitHubOAuthenticator", (), {})
        sys.modules[module.__name__] = module

    spec = importlib.util.spec_from_file_location("core.authenticators", AUTHENTICATORS)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with pytest.raises(ValueError, match="Unknown authentication mode"):
        module.create_authenticator("unexpected")
