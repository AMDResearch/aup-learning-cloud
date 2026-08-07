import importlib.util
import sys
import types
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core"
AUTHENTICATORS = CORE / "authenticators"


class DummyUser:
    def __init__(self, name: str, admin: bool = False) -> None:
        self.name = name
        self.admin = admin


class FakeQuery:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows
        self._filtered = rows

    def filter_by(self, **kwargs: object) -> "FakeQuery":
        self._filtered = [
            row for row in self._rows if all(getattr(row, key, None) == value for key, value in kwargs.items())
        ]
        return self

    def first(self) -> object | None:
        return self._filtered[0] if self._filtered else None

    def all(self) -> list[object]:
        return self._filtered


class FakeDb:
    def __init__(self, rows: list[object] | None = None) -> None:
        self.rows = rows or []
        self.commits = 0

    def query(self, _model: object) -> FakeQuery:
        return FakeQuery(self.rows)

    def add(self, row: object) -> None:
        self.rows.append(row)

    def commit(self) -> None:
        self.commits += 1


@contextmanager
def fake_session_scope(db: FakeDb) -> Iterator[FakeDb]:
    yield db
    for row in db.rows:
        if hasattr(row, "detached"):
            row.detached = True
    db.commit()


def make_handler(handler_cls: type, username: str) -> tuple[object, dict[str, object]]:
    handler = object.__new__(handler_cls)
    handler.current_user = DummyUser(username)
    captured: dict[str, object] = {}
    handler.set_header = lambda key, value: captured.setdefault("headers", {}).__setitem__(key, value)
    handler.finish = lambda payload: captured.setdefault("body", payload)
    return handler, captured


@contextmanager
def load_handlers(monkeypatch: pytest.MonkeyPatch) -> Iterator[types.SimpleNamespace]:
    with monkeypatch.context() as module_patch:
        core = types.ModuleType("core")
        core.__path__ = [str(CORE)]
        module_patch.setitem(sys.modules, "core", core)
        authenticators = types.ModuleType("core.authenticators")
        authenticators.__path__ = [str(AUTHENTICATORS)]
        native_authenticator = type("CustomFirstUseAuthenticator", (), {})
        authenticators.CustomFirstUseAuthenticator = native_authenticator
        authenticators.GITHUB_USERNAME_PREFIX = "github:"
        module_patch.setitem(sys.modules, "core.authenticators", authenticators)

        database = types.ModuleType("core.database")
        database.Base = type("Base", (), {"__init__": lambda self, **kwargs: self.__dict__.update(kwargs)})
        database.session_scope = lambda: (_ for _ in ()).throw(AssertionError("session_scope must be patched"))
        module_patch.setitem(sys.modules, "core.database", database)

        sqlalchemy = types.ModuleType("sqlalchemy")
        sqlalchemy.Boolean = sqlalchemy.DateTime = sqlalchemy.Integer = sqlalchemy.LargeBinary = sqlalchemy.String = (
            lambda *_args: None
        )
        sqlalchemy.func = types.SimpleNamespace(now=lambda: None)
        sqlalchemy_orm = types.ModuleType("sqlalchemy.orm")
        sqlalchemy_orm.Mapped = type("Mapped", (), {"__class_getitem__": classmethod(lambda cls, _item: cls)})
        sqlalchemy_orm.mapped_column = lambda *_args, **_kwargs: None
        module_patch.setitem(sys.modules, "sqlalchemy", sqlalchemy)
        module_patch.setitem(sys.modules, "sqlalchemy.orm", sqlalchemy_orm)

        jupyterhub = types.ModuleType("jupyterhub")
        apihandlers = types.ModuleType("jupyterhub.apihandlers")
        handlers = types.ModuleType("jupyterhub.handlers")
        orm = types.ModuleType("jupyterhub.orm")
        roles = types.ModuleType("jupyterhub.roles")
        scopes = types.ModuleType("jupyterhub.scopes")
        utils = types.ModuleType("jupyterhub.utils")
        apihandlers.APIHandler = type("APIHandler", (), {})
        handlers.BaseHandler = type("BaseHandler", (), {})
        orm.User = type("User", (), {})
        roles.assign_default_roles = lambda *_args, **_kwargs: None
        scopes.needs_scope = lambda _scope: lambda handler: handler

        async def maybe_future(value):
            return value

        utils.maybe_future = maybe_future
        module_patch.setitem(sys.modules, "jupyterhub", jupyterhub)
        module_patch.setitem(sys.modules, "jupyterhub.apihandlers", apihandlers)
        module_patch.setitem(sys.modules, "jupyterhub.handlers", handlers)
        module_patch.setitem(sys.modules, "jupyterhub.orm", orm)
        module_patch.setitem(sys.modules, "jupyterhub.roles", roles)
        module_patch.setitem(sys.modules, "jupyterhub.scopes", scopes)
        module_patch.setitem(sys.modules, "jupyterhub.utils", utils)

        multi = types.ModuleType("multiauthenticator")
        multi_authenticator = type("MultiAuthenticator", (), {})
        multi.MultiAuthenticator = multi_authenticator
        module_patch.setitem(sys.modules, "multiauthenticator", multi)
        quota = types.ModuleType("core.quota")
        quota.BatchQuotaRequest = quota.QuotaAction = quota.QuotaModifyRequest = quota.QuotaRefreshRequest = type(
            "Quota", (), {}
        )
        quota.get_quota_manager = lambda: None
        module_patch.setitem(sys.modules, "core.quota", quota)
        stats = types.ModuleType("core.stats_handlers")
        for name in (
            "StatsActiveSSEHandler",
            "StatsDistributionHandler",
            "StatsHourlyHandler",
            "StatsMyUsageHandler",
            "StatsOverviewHandler",
            "StatsUsageHandler",
            "StatsUserHandler",
        ):
            setattr(stats, name, type(name, (), {}))
        module_patch.setitem(sys.modules, "core.stats_handlers", stats)

        def load(name: str, path: Path) -> types.ModuleType:
            spec = importlib.util.spec_from_file_location(name, path)
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            module_patch.setitem(sys.modules, name, module)
            spec.loader.exec_module(module)
            return module

        models = load("core.authenticators.models", AUTHENTICATORS / "models.py")
        handler_module = load("core.handlers", CORE / "handlers.py")
        yield types.SimpleNamespace(
            database=database,
            handlers=handler_module,
            models=models,
            multi_authenticator=multi_authenticator,
            native_authenticator=native_authenticator,
        )
