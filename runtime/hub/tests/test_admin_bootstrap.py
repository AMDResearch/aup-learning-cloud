import importlib.util
import inspect
import sys
import types
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "core" / "setup.py"


def test_bootstrap_admin_password_preserves_existing_hash(monkeypatch) -> None:
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
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    module._bootstrap_admin_password("operator", "InitialPassword1!")
    session.rows[0].password_hash = bcrypt.hashpw(b"ChangedPassword1!", bcrypt.gensalt())
    module._bootstrap_admin_password("operator", "InitialPassword1!")

    assert "require_match" not in inspect.signature(module._bootstrap_admin_password).parameters
    assert bcrypt.checkpw(b"ChangedPassword1!", session.rows[0].password_hash)
    assert not bcrypt.checkpw(b"InitialPassword1!", session.rows[0].password_hash)


def test_bootstrap_admin_password_does_not_compare_same_secret_on_restart(monkeypatch) -> None:
    bcrypt = types.ModuleType("bcrypt")
    bcrypt.gensalt = lambda: b"salt"
    bcrypt.hashpw = lambda password, _salt: b"hash:" + password
    bcrypt.checkpw = lambda *_args: (_ for _ in ()).throw(AssertionError("bootstrap must not compare password hashes"))

    class FakeUserPassword:
        def __init__(self, username, password_hash, force_change):
            self.username = username
            self.password_hash = password_hash
            self.force_change = force_change

    class FakeQuery:
        def __init__(self, rows):
            self.rows = rows

        def filter_by(self, *, username):
            self.username = username
            return self

        def first(self):
            return next((row for row in self.rows if row.username == self.username), None)

    session = types.SimpleNamespace(rows=[])
    session.query = lambda _model: FakeQuery(session.rows)
    session.add = session.rows.append
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
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    module._bootstrap_admin_password("operator", "InitialPassword1!")
    module._bootstrap_admin_password("operator", "InitialPassword1!")

    assert len(session.rows) == 1
    assert session.rows[0].password_hash == b"hash:InitialPassword1!"


def test_api_token_is_assigned_to_the_configured_administrator(monkeypatch) -> None:
    bcrypt = types.ModuleType("bcrypt")
    monkeypatch.setitem(sys.modules, "bcrypt", bcrypt)
    spec = importlib.util.spec_from_file_location("core.setup", SETUP)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    config = types.SimpleNamespace(JupyterHub=types.SimpleNamespace())

    module._configure_api_token(config, "token", "operator")

    assert config.JupyterHub.api_tokens == {"token": "operator"}
