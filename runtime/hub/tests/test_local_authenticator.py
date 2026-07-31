import asyncio
import importlib.util
import sys
import types
from contextlib import contextmanager
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LOCAL_AUTHENTICATOR = ROOT / "core" / "authenticators" / "local.py"
AUTHENTICATORS = ROOT / "core" / "authenticators" / "__init__.py"
SETUP = ROOT / "core" / "setup.py"


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
        assert (
            asyncio.run(authenticator.authenticate(None, {"username": username, "password": "correct-password"}))
            is None
        )


def test_local_authenticator_validate_username_matches_login_policy() -> None:
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

    assert authenticator.validate_username("existing")
    for username in ("EXISTING", "existing:admin", 'existing"', "existing\n", "a" * 65):
        assert not authenticator.validate_username(username)


def test_bootstrap_admin_password_preserves_a_password_changed_after_first_start(monkeypatch) -> None:
    bcrypt = types.ModuleType("bcrypt")
    bcrypt.gensalt = lambda: b"salt"
    bcrypt.hashpw = lambda password, _salt: b"hash:" + password
    bcrypt.checkpw = lambda password, password_hash: password_hash == b"hash:" + password

    class FakeUserPassword:
        def __init__(self, username, password_hash, force_change):
            self.username = username
            self.password_hash = password_hash
            self.force_change = force_change

    class FakeQuery:
        def __init__(self, rows):
            self.rows = rows
            self.username = ""

        def filter_by(self, *, username):
            self.username = username
            return self

        def first(self):
            return next((row for row in self.rows if row.username == self.username), None)

    class FakeSession:
        def __init__(self):
            self.rows = []

        def query(self, _model):
            return FakeQuery(self.rows)

        def add(self, row):
            self.rows.append(row)

    session = FakeSession()
    models = types.ModuleType("core.authenticators.models")
    models.UserPassword = FakeUserPassword
    database = types.ModuleType("core.database")

    @contextmanager
    def session_scope():
        yield session

    database.session_scope = session_scope
    monkeypatch.setitem(sys.modules, "bcrypt", bcrypt)
    monkeypatch.setitem(sys.modules, "core.authenticators.models", models)
    monkeypatch.setitem(sys.modules, "core.database", database)
    spec = importlib.util.spec_from_file_location("core.setup", SETUP)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    module._bootstrap_admin_password("operator", "InitialPassword1!")
    session.rows[0].password_hash = bcrypt.hashpw(b"ChangedPassword1!", bcrypt.gensalt())
    module._bootstrap_admin_password("operator", "InitialPassword1!")

    assert bcrypt.checkpw(b"ChangedPassword1!", session.rows[0].password_hash)
    assert not bcrypt.checkpw(b"InitialPassword1!", session.rows[0].password_hash)


def test_api_token_is_assigned_to_the_configured_administrator(monkeypatch) -> None:
    bcrypt = types.ModuleType("bcrypt")
    monkeypatch.setitem(sys.modules, "bcrypt", bcrypt)
    spec = importlib.util.spec_from_file_location("core.setup", SETUP)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = types.SimpleNamespace(JupyterHub=types.SimpleNamespace())

    module._configure_api_token(config, "token", "operator")

    assert config.JupyterHub.api_tokens == {"token": "operator"}


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
