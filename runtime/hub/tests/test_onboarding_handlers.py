import asyncio
import importlib.util
import json
import sys
import types
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core"
AUTHENTICATORS = CORE / "authenticators"

if "jupyterhub.apihandlers" not in sys.modules:
    jupyterhub_module = types.ModuleType("jupyterhub")
    apihandlers_module = types.ModuleType("jupyterhub.apihandlers")
    handlers_module = types.ModuleType("jupyterhub.handlers")
    apihandlers_module.APIHandler = type("APIHandler", (), {})
    handlers_module.BaseHandler = type("BaseHandler", (), {})
    sys.modules["jupyterhub"] = jupyterhub_module
    sys.modules["jupyterhub.apihandlers"] = apihandlers_module
    sys.modules["jupyterhub.handlers"] = handlers_module

if "multiauthenticator" not in sys.modules:
    multiauthenticator_module = types.ModuleType("multiauthenticator")
    multiauthenticator_module.MultiAuthenticator = type("MultiAuthenticator", (), {})
    sys.modules["multiauthenticator"] = multiauthenticator_module

if "core" not in sys.modules:
    core_module = types.ModuleType("core")
    core_module.__path__ = [str(CORE)]
    sys.modules["core"] = core_module

if "core.authenticators" not in sys.modules:
    auth_module = types.ModuleType("core.authenticators")
    auth_module.__path__ = [str(AUTHENTICATORS)]
    auth_module.CustomFirstUseAuthenticator = type("CustomFirstUseAuthenticator", (), {})
    sys.modules["core.authenticators"] = auth_module

if "sqlalchemy" not in sys.modules:
    sqlalchemy_module = types.ModuleType("sqlalchemy")

    class _SQLAType:
        def __init__(self, *args, **kwargs):
            pass

    class _Func:
        @staticmethod
        def now():
            return None

    sqlalchemy_module.Boolean = _SQLAType
    sqlalchemy_module.DateTime = _SQLAType
    sqlalchemy_module.Integer = _SQLAType
    sqlalchemy_module.LargeBinary = _SQLAType
    sqlalchemy_module.String = _SQLAType
    sqlalchemy_module.func = _Func()
    sys.modules["sqlalchemy"] = sqlalchemy_module

if "sqlalchemy.orm" in sys.modules:
    sqlalchemy_orm_module = sys.modules["sqlalchemy.orm"]
else:
    sqlalchemy_orm_module = types.ModuleType("sqlalchemy.orm")
    sys.modules["sqlalchemy.orm"] = sqlalchemy_orm_module


class Mapped:
    def __class_getitem__(cls, _item):
        return cls


def mapped_column(*args, **kwargs):
    return None


if not hasattr(sqlalchemy_orm_module, "Mapped"):
    sqlalchemy_orm_module.Mapped = Mapped
if not hasattr(sqlalchemy_orm_module, "mapped_column"):
    sqlalchemy_orm_module.mapped_column = mapped_column
if not hasattr(sqlalchemy_orm_module, "Session"):
    sqlalchemy_orm_module.Session = type("Session", (), {})

if "core.database" not in sys.modules:
    database_module = types.ModuleType("core.database")

    class Base:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    @contextmanager
    def session_scope():
        raise AssertionError("session_scope must be patched in onboarding tests")

    database_module.Base = Base
    database_module.session_scope = session_scope
    sys.modules["core.database"] = database_module

if "core.quota" not in sys.modules:
    quota_module = types.ModuleType("core.quota")
    quota_module.BatchQuotaRequest = type("BatchQuotaRequest", (), {})
    quota_module.QuotaAction = type("QuotaAction", (), {})
    quota_module.QuotaModifyRequest = type("QuotaModifyRequest", (), {})
    quota_module.QuotaRefreshRequest = type("QuotaRefreshRequest", (), {})
    quota_module.get_quota_manager = lambda: None
    sys.modules["core.quota"] = quota_module

if "core.stats_handlers" not in sys.modules:
    stats_module = types.ModuleType("core.stats_handlers")
    for name in [
        "StatsActiveSSEHandler",
        "StatsDistributionHandler",
        "StatsHourlyHandler",
        "StatsMyUsageHandler",
        "StatsOverviewHandler",
        "StatsUsageHandler",
        "StatsUserHandler",
    ]:
        setattr(stats_module, name, type(name, (), {}))
    sys.modules["core.stats_handlers"] = stats_module


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


models = load_module("core.authenticators.models", AUTHENTICATORS / "models.py")
handlers = load_module("core.handlers", CORE / "handlers.py")
database = sys.modules["core.database"]

UserOnboardingState = models.UserOnboardingState
DismissMyOnboardingHandler = handlers.DismissMyOnboardingHandler
GetMyOnboardingHandler = handlers.GetMyOnboardingHandler


class DummyUser:
    def __init__(self, name: str):
        self.name = name


class FakeQuery:
    def __init__(self, rows):
        self._rows = rows
        self._filtered = rows

    def filter_by(self, **kwargs):
        self._filtered = [
            row for row in self._rows if all(getattr(row, key, None) == value for key, value in kwargs.items())
        ]
        return self

    def first(self):
        return self._filtered[0] if self._filtered else None

    def one_or_none(self):
        return self.first()


class FakeDb:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.commits = 0

    def query(self, _model):
        return FakeQuery(self.rows)

    def add(self, obj):
        self.rows.append(obj)

    def flush(self):
        pass

    def commit(self):
        self.commits += 1


class DetachedAwareState:
    def __init__(self, username: str, dismissed_at):
        self.username = username
        self._dismissed_at = dismissed_at
        self.detached = False

    @property
    def dismissed_at(self):
        if self.detached:
            raise RuntimeError("detached instance access")
        return self._dismissed_at

    @dismissed_at.setter
    def dismissed_at(self, value):
        self._dismissed_at = value


def fake_session_scope(db):
    @contextmanager
    def _scope():
        yield db
        for row in getattr(db, "rows", []):
            if hasattr(row, "detached"):
                row.detached = True
        db.commit()

    return _scope


def make_handler(handler_cls, username: str):
    handler = object.__new__(handler_cls)
    handler.current_user = DummyUser(username)
    captured = {}
    handler.set_header = lambda key, value: captured.setdefault("headers", {}).__setitem__(key, value)
    handler.finish = lambda payload: captured.setdefault("body", payload)
    return handler, captured


def test_get_my_onboarding_returns_visible_when_no_state_exists(monkeypatch):
    monkeypatch.setattr(database, "session_scope", fake_session_scope(FakeDb()))
    handler, captured = make_handler(GetMyOnboardingHandler, "alice")

    asyncio.run(handler.get())

    assert captured["headers"]["Content-Type"] == "application/json"
    assert json.loads(captured["body"]) == {"should_show": True, "dismissed_at": None}


def test_get_my_onboarding_returns_hidden_when_current_user_already_dismissed(monkeypatch):
    dismissed_at = datetime(2026, 4, 22, 12, 30, 0, tzinfo=timezone.utc)
    db = FakeDb([DetachedAwareState(username="alice", dismissed_at=dismissed_at)])
    monkeypatch.setattr(database, "session_scope", fake_session_scope(db))
    handler, captured = make_handler(GetMyOnboardingHandler, "alice")

    asyncio.run(handler.get())

    assert captured["headers"]["Content-Type"] == "application/json"
    assert json.loads(captured["body"]) == {
        "should_show": False,
        "dismissed_at": dismissed_at.isoformat(),
    }


def test_dismiss_my_onboarding_persists_dismissal_for_current_user(monkeypatch):
    existing_state = UserOnboardingState(
        username="bob",
        dismissed_at=datetime(2026, 4, 21, 8, 0, 0, tzinfo=timezone.utc),
    )
    db = FakeDb([existing_state])
    monkeypatch.setattr(database, "session_scope", fake_session_scope(db))
    handler, captured = make_handler(DismissMyOnboardingHandler, "alice")

    asyncio.run(handler.post())

    payload = json.loads(captured["body"])
    assert captured["headers"]["Content-Type"] == "application/json"
    assert payload["should_show"] is False
    assert payload["dismissed_at"] is not None
    dismissed_at = datetime.fromisoformat(payload["dismissed_at"])
    assert dismissed_at.tzinfo == timezone.utc
    assert db.commits == 1
    assert len(db.rows) == 2
    assert db.rows[0].username == "bob"
    assert db.rows[1].username == "alice"
    assert db.rows[1].dismissed_at == dismissed_at
