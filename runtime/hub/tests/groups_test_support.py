import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core"
MODULE_NAMES = (
    "aiohttp",
    "jupyterhub",
    "jupyterhub.orm",
    "jupyterhub.user",
    "sqlalchemy",
    "sqlalchemy.orm",
    "core",
    "core.authenticators",
    "core.authenticators.github_app",
    "core.groups",
)
MISSING = object()


def load_groups_module() -> types.ModuleType:
    original_modules = {name: sys.modules.get(name, MISSING) for name in MODULE_NAMES}
    try:
        aiohttp_module = types.ModuleType("aiohttp")
        aiohttp_module.ClientSession = object
        jupyterhub_module = types.ModuleType("jupyterhub")
        jupyterhub_module.__path__ = []
        orm_module = types.ModuleType("jupyterhub.orm")
        orm_module.Group = type("Group", (), {})
        user_module = types.ModuleType("jupyterhub.user")
        user_module.User = type("User", (), {})
        jupyterhub_module.orm, jupyterhub_module.user = orm_module, user_module
        sqlalchemy_module = types.ModuleType("sqlalchemy")
        sqlalchemy_module.__path__ = []
        sa_orm_module = types.ModuleType("sqlalchemy.orm")
        sa_orm_module.Session = type("Session", (), {})
        sqlalchemy_module.orm = sa_orm_module
        core_module = types.ModuleType("core")
        core_module.__path__ = [str(CORE)]
        authenticators_module = types.ModuleType("core.authenticators")
        authenticators_module.__path__ = [str(CORE / "authenticators")]
        github_app_module = types.ModuleType("core.authenticators.github_app")
        github_app_module.GITHUB_USERNAME_PREFIX = "github:"
        authenticators_module.github_app = github_app_module
        core_module.authenticators = authenticators_module
        sys.modules.update(
            {
                "aiohttp": aiohttp_module,
                "jupyterhub": jupyterhub_module,
                "jupyterhub.orm": orm_module,
                "jupyterhub.user": user_module,
                "sqlalchemy": sqlalchemy_module,
                "sqlalchemy.orm": sa_orm_module,
                "core": core_module,
                "core.authenticators": authenticators_module,
                "core.authenticators.github_app": github_app_module,
            }
        )
        spec = importlib.util.spec_from_file_location("core.groups", CORE / "groups.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules["core.groups"] = module
        spec.loader.exec_module(module)
        return module
    finally:
        for name, original_module in original_modules.items():
            if original_module is MISSING:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original_module


class DummyGroup:
    def __init__(self, name: str, source: str = "github-team") -> None:
        self.name = name
        self.properties = {"source": source}


class DummyOrmUser:
    def __init__(self, groups: list[DummyGroup]) -> None:
        self.groups = groups


class DummyUser:
    def __init__(self, groups: list[DummyGroup], name: str = "github:test") -> None:
        self.name = name
        self.orm_user = DummyOrmUser(groups)
