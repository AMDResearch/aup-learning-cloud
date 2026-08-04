import asyncio
import importlib.util
import sys
import types
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIRSTUSE = ROOT / "core" / "authenticators" / "firstuse.py"


class _FakeLog:
    def __init__(self) -> None:
        self.warnings = []

    def warning(self, *args) -> None:
        self.warnings.append(args)

    def info(self, *_args) -> None:
        pass


class _HubUserQuery:
    def __init__(self, result, queried_names) -> None:
        self._result = result
        self._queried_names = queried_names

    def filter_by(self, *, name):
        self._queried_names.append(name)
        return self

    def first(self):
        return self._result


class _HubDatabase:
    def __init__(self, result) -> None:
        self._result = result
        self.queried_names = []

    def query(self, _model):
        return _HubUserQuery(self._result, self.queried_names)


class _RaisingHubDatabase:
    def query(self, _model):
        raise RuntimeError("database unavailable")


class _UnexpectedHubDatabase:
    def query(self, _model):
        raise AssertionError("unexpected Hub database query")


def _install_core_packages(module_patch: pytest.MonkeyPatch) -> None:
    core = types.ModuleType("core")
    core.__path__ = [str(ROOT / "core")]
    authenticators = types.ModuleType("core.authenticators")
    authenticators.__path__ = [str(ROOT / "core" / "authenticators")]
    core.authenticators = authenticators
    module_patch.setitem(sys.modules, "core", core)
    module_patch.setitem(sys.modules, "core.authenticators", authenticators)


@contextmanager
def _loaded_firstuse_authenticator(monkeypatch: pytest.MonkeyPatch) -> Iterator[type]:
    with monkeypatch.context() as module_patch:
        _install_core_packages(module_patch)
        bcrypt = types.ModuleType("bcrypt")
        bcrypt.gensalt = lambda: b"salt"
        bcrypt.hashpw = lambda password, _salt: b"hash:" + password
        bcrypt.checkpw_calls = []

        def checkpw(password, password_hash):
            bcrypt.checkpw_calls.append((password, password_hash))
            return password_hash == b"hash:" + password

        bcrypt.checkpw = checkpw

        class FakeFirstUseAuthenticator:
            def __init__(self) -> None:
                self.log = _FakeLog()

        firstuseauthenticator = types.ModuleType("firstuseauthenticator")
        firstuseauthenticator.FirstUseAuthenticator = FakeFirstUseAuthenticator
        models = types.ModuleType("core.authenticators.models")
        models.UserPassword = type("UserPassword", (), {})
        database = types.ModuleType("core.database")
        database.get_session = lambda: None
        database.session_scope = lambda: None
        jupyterhub = types.ModuleType("jupyterhub")
        orm = types.ModuleType("jupyterhub.orm")
        orm.User = type("User", (), {})
        jupyterhub.orm = orm
        for fake_module in (bcrypt, firstuseauthenticator, models, database, jupyterhub, orm):
            module_patch.setitem(sys.modules, fake_module.__name__, fake_module)

        spec = importlib.util.spec_from_file_location("core.authenticators.firstuse", FIRSTUSE)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        module_patch.setitem(sys.modules, "core.authenticators.firstuse", module)
        spec.loader.exec_module(module)
        yield module.CustomFirstUseAuthenticator


def test_firstuse_module_cleanup_survives_a_forced_test_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    module_names = (
        "core",
        "core.authenticators",
        "core.authenticators.firstuse",
        "core.authenticators.models",
        "core.database",
        "bcrypt",
        "firstuseauthenticator",
        "jupyterhub",
        "jupyterhub.orm",
    )
    missing = object()
    original_modules = {name: sys.modules.get(name, missing) for name in module_names}

    with pytest.raises(AssertionError, match="forced cleanup probe"), _loaded_firstuse_authenticator(monkeypatch):
        raise AssertionError("forced cleanup probe")

    for name, original_module in original_modules.items():
        if original_module is missing:
            assert name not in sys.modules
        else:
            assert sys.modules[name] is original_module


def test_precreated_user_sets_password_after_one_normalized_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    with _loaded_firstuse_authenticator(monkeypatch) as authenticator_type:
        authenticator = authenticator_type()
        hub_db = _HubDatabase(object())
        authenticator.db = hub_db
        calls = []
        authenticator.normalize_username = lambda username: calls.append(("normalize", username)) or "learner"
        authenticator.user_has_password = lambda username: calls.append(("has_password", username)) or False
        authenticator._validate_password = lambda password: calls.append(("validate", password)) or True
        authenticator.set_password = lambda username, password, force_change: calls.append(
            ("set_password", username, password, force_change)
        )

        authenticated = asyncio.run(authenticator.authenticate(None, {"username": "LEARNER", "password": "Password1!"}))

        assert authenticated == "learner"
        assert authenticator.create_users is False
        assert hub_db.queried_names == ["learner"]
        assert calls == [
            ("normalize", "LEARNER"),
            ("has_password", "learner"),
            ("validate", "Password1!"),
            ("set_password", "learner", "Password1!", False),
        ]


@pytest.mark.parametrize(
    ("submitted_password", "expected_result"),
    [("Password1!", "learner"), ("wrong-password", None)],
)
def test_existing_user_authentication_checks_normalized_username(
    monkeypatch: pytest.MonkeyPatch, submitted_password: str, expected_result: str | None
) -> None:
    with _loaded_firstuse_authenticator(monkeypatch) as authenticator_type:
        authenticator = authenticator_type()
        hub_db = _HubDatabase(object())
        authenticator.db = hub_db
        calls = []
        authenticator.normalize_username = lambda username: calls.append(("normalize", username)) or "learner"
        authenticator.user_has_password = lambda username: calls.append(("has_password", username)) or True
        authenticator.check_password = lambda username, password: (
            calls.append(("check_password", username, password)) or (password == "Password1!")
        )

        authenticated = asyncio.run(
            authenticator.authenticate(None, {"username": "LEARNER", "password": submitted_password})
        )

        assert authenticated == expected_result
        assert hub_db.queried_names == ["learner"]
        assert calls == [
            ("normalize", "LEARNER"),
            ("has_password", "learner"),
            ("check_password", "learner", submitted_password),
        ]
        assert sys.modules["bcrypt"].checkpw_calls == []


def test_missing_child_and_parent_database_rejects_without_password_side_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _loaded_firstuse_authenticator(monkeypatch) as authenticator_type:
        authenticator = authenticator_type()
        authenticator.db = None
        authenticator.parent = types.SimpleNamespace(db=None)
        authenticator.user_has_password = lambda _username: False
        authenticator._validate_password = lambda _password: True
        password_changes = []
        authenticator.set_password = lambda *args: password_changes.append(args)

        authenticated = asyncio.run(authenticator.authenticate(None, {"username": "learner", "password": "Password1!"}))

        assert authenticated is None
        assert password_changes == []
        assert authenticator.log.warnings
        assert sys.modules["bcrypt"].checkpw_calls == []


def test_missing_parent_database_rejects_without_password_side_effect(monkeypatch: pytest.MonkeyPatch) -> None:
    with _loaded_firstuse_authenticator(monkeypatch) as authenticator_type:
        authenticator = authenticator_type()
        authenticator.db = None
        authenticator.parent = types.SimpleNamespace()
        password_changes = []
        authenticator.set_password = lambda *args: password_changes.append(args)

        authenticated = asyncio.run(authenticator.authenticate(None, {"username": "learner", "password": "Password1!"}))

        assert authenticated is None
        assert password_changes == []
        assert authenticator.log.warnings
        assert sys.modules["bcrypt"].checkpw_calls == []


@pytest.mark.parametrize("query_result", [None, False], ids=["none", "falsey"])
def test_unknown_user_query_result_rejects_without_password_side_effect(
    monkeypatch: pytest.MonkeyPatch, query_result
) -> None:
    with _loaded_firstuse_authenticator(monkeypatch) as authenticator_type:
        authenticator = authenticator_type()
        authenticator.db = _HubDatabase(query_result)
        password_changes = []
        authenticator.set_password = lambda *args: password_changes.append(args)

        authenticated = asyncio.run(authenticator.authenticate(None, {"username": "learner", "password": "Password1!"}))

        assert authenticated is None
        assert password_changes == []
        assert sys.modules["bcrypt"].checkpw_calls == [(b"Password1!", authenticator_type.DUMMY_PASSWORD_HASH)]


def test_database_query_error_propagates_without_password_side_effect(monkeypatch: pytest.MonkeyPatch) -> None:
    with _loaded_firstuse_authenticator(monkeypatch) as authenticator_type:
        authenticator = authenticator_type()
        authenticator.db = _RaisingHubDatabase()
        password_changes = []
        authenticator.set_password = lambda *args: password_changes.append(args)

        with pytest.raises(RuntimeError, match="database unavailable"):
            asyncio.run(authenticator.authenticate(None, {"username": "learner", "password": "Password1!"}))

        assert password_changes == []
        assert sys.modules["bcrypt"].checkpw_calls == []


def test_parent_database_fallback_supports_multiauth_child(monkeypatch: pytest.MonkeyPatch) -> None:
    with _loaded_firstuse_authenticator(monkeypatch) as authenticator_type:
        authenticator = authenticator_type()
        parent_db = _HubDatabase(object())
        authenticator.db = None
        authenticator.parent = types.SimpleNamespace(db=parent_db)

        assert authenticator._user_exists("learner") is True
        assert parent_db.queried_names == ["learner"]


def test_child_database_takes_precedence_over_parent_database(monkeypatch: pytest.MonkeyPatch) -> None:
    with _loaded_firstuse_authenticator(monkeypatch) as authenticator_type:
        authenticator = authenticator_type()
        child_db = _HubDatabase(object())
        authenticator.db = child_db
        authenticator.parent = types.SimpleNamespace(db=_UnexpectedHubDatabase())

        assert authenticator._user_exists("learner") is True
        assert child_db.queried_names == ["learner"]


def test_weak_first_use_password_rejects_without_password_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    with _loaded_firstuse_authenticator(monkeypatch) as authenticator_type:
        authenticator = authenticator_type()
        authenticator.db = _HubDatabase(object())
        authenticator.user_has_password = lambda _username: False
        password_changes = []
        authenticator.set_password = lambda *args: password_changes.append(args)

        authenticated = asyncio.run(authenticator.authenticate(None, {"username": "learner", "password": "weak"}))

        assert authenticated is None
        assert password_changes == []
