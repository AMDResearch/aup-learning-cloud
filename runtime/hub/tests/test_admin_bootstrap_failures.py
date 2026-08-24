import importlib.util
import sys
import types
from contextlib import contextmanager
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "core" / "setup.py"


@pytest.mark.parametrize("failure", ("query", "hash", "add", "commit"))
def test_bootstrap_failure_never_prints_password_success(monkeypatch: pytest.MonkeyPatch, capsys, failure: str) -> None:
    class FakeUserPassword:
        def __init__(self, **kwargs) -> None:
            self.__dict__.update(kwargs)

    class FakeQuery:
        def filter_by(self, **_kwargs):
            return self

        def first(self):
            if failure == "query":
                raise OSError("query failed")
            return None

    class FakeSession:
        def query(self, _model):
            return FakeQuery()

        def add(self, _row) -> None:
            if failure == "add":
                raise OSError("add failed")

    @contextmanager
    def session_scope():
        yield FakeSession()
        if failure == "commit":
            raise OSError("commit failed")

    bcrypt = types.ModuleType("bcrypt")
    bcrypt.gensalt = lambda: b"salt"
    bcrypt.hashpw = lambda _password, _salt: (
        (_ for _ in ()).throw(OSError("hash failed")) if failure == "hash" else b"hash"
    )
    models = types.ModuleType("core.authenticators.models")
    models.UserPassword = FakeUserPassword
    database = types.ModuleType("core.database")
    database.session_scope = session_scope
    monkeypatch.setitem(sys.modules, "bcrypt", bcrypt)
    monkeypatch.setitem(sys.modules, "core.authenticators.models", models)
    monkeypatch.setitem(sys.modules, "core.database", database)
    spec = importlib.util.spec_from_file_location("core.setup", SETUP)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with pytest.raises(OSError):
        module._bootstrap_admin_password("operator", "Password1!")

    assert "Admin 'operator' password" not in capsys.readouterr().out


def test_existing_password_commit_failure_never_prints_success(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    class FakeUserPassword:
        username = "operator"

    class FakeQuery:
        def filter_by(self, **_kwargs):
            return self

        def first(self):
            return FakeUserPassword()

    class FakeSession:
        def query(self, _model):
            return FakeQuery()

    @contextmanager
    def session_scope():
        yield FakeSession()
        raise OSError("commit failed")

    bcrypt = types.ModuleType("bcrypt")
    bcrypt.hashpw = lambda *_args: (_ for _ in ()).throw(AssertionError("existing rows must not hash"))
    models = types.ModuleType("core.authenticators.models")
    models.UserPassword = FakeUserPassword
    database = types.ModuleType("core.database")
    database.session_scope = session_scope
    monkeypatch.setitem(sys.modules, "bcrypt", bcrypt)
    monkeypatch.setitem(sys.modules, "core.authenticators.models", models)
    monkeypatch.setitem(sys.modules, "core.database", database)
    spec = importlib.util.spec_from_file_location("core.setup", SETUP)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with pytest.raises(OSError, match="commit failed"):
        module._bootstrap_admin_password("operator", "Password1!")

    assert "Admin 'operator' password" not in capsys.readouterr().out
