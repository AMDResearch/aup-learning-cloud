import importlib.util
import sys
import types
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import anyio
import pytest
from provider_setup_support import GITHUB_SETTINGS, make_config

ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / "core" / "setup.py"
CONFIG = ROOT / "core" / "config.py"
MODULE_NAMES = tuple(
    (
        "bcrypt|core|core.z2jh|core.config|core.authenticators|core.database|core.handlers|core.metrics_updater|"
        "core.spawner|core.groups|jupyterhub|jupyterhub.apihandlers|jupyterhub.apihandlers.groups|tornado|"
        "tornado.web|core.setup"
    )
    .replace("|", "\n")
    .splitlines()
)
_module = types.ModuleType


@contextmanager
def _loaded_setup(
    monkeypatch: pytest.MonkeyPatch,
    providers: tuple[bool, bool, bool, bool],
    *,
    access_policy: str = "group-mapped",
    fail_setup: bool = False,
) -> Iterator[types.SimpleNamespace]:
    with monkeypatch.context() as module_patch:
        for variable in ("JUPYTERHUB_ADMIN_PASSWORD", "JUPYTERHUB_ADMIN_USERNAME", "JUPYTERHUB_API_TOKEN"):
            monkeypatch.delenv(variable, raising=False)
        module_patch.setattr(
            importlib.import_module("asyncio"),
            "get_event_loop",
            lambda: types.SimpleNamespace(call_later=lambda *_args: None),
        )
        bcrypt = _module("bcrypt")
        module_patch.setitem(sys.modules, "bcrypt", bcrypt)
        core = _module("core")
        core.__path__ = [str(ROOT / "core")]
        module_patch.setitem(sys.modules, "core", core)

        config_spec = importlib.util.spec_from_file_location("core.config", CONFIG)
        assert config_spec is not None and config_spec.loader is not None
        config_module = importlib.util.module_from_spec(config_spec)
        module_patch.setitem(sys.modules, "core.config", config_module)
        core.config = config_module
        config_spec.loader.exec_module(config_module)
        auth = config_module.AuthCapabilities(*providers)
        config = make_config(auth, access_policy)
        config_module.HubConfig._instance, config_module.HubConfig._initialized = config, True

        settings_reads: list[str] = []
        z2jh = _module("core.z2jh")

        def get_config(key: str, default: object = None) -> object:
            settings_reads.append(key)
            if fail_setup and key == "hub.db.type":
                raise RuntimeError("forced setup failure")
            if key.startswith("hub.config.GitHubOAuthenticator") and not auth.github:
                raise AssertionError(f"GitHub settings accessed for disabled provider: {key}")
            return GITHUB_SETTINGS.get(key, default)

        z2jh.get_config = get_config
        core.z2jh = z2jh
        module_patch.setitem(sys.modules, "core.z2jh", z2jh)

        authenticator_types = {
            "auto": type("AutoLoginAuthenticator", (), {}),
            "github": type("CustomGitHubOAuthenticator", (), {}),
            "native": type("CustomFirstUseAuthenticator", (), {}),
            "multi": type("CustomMultiAuthenticator", (), {}),
        }
        factory_inputs: list[object] = []
        authenticators = _module("core.authenticators")
        authenticators.GITHUB_USERNAME_PREFIX = "github:"
        authenticators.CustomGitHubOAuthenticator = authenticator_types["github"]
        authenticators.CustomFirstUseAuthenticator = authenticator_types["native"]

        def create_authenticator(_input: object) -> type | str:
            factory_inputs.append(_input)
            if auth.auto_login:
                return authenticator_types["auto"]
            if auth.dummy:
                return "dummy"
            if auth.native and auth.github:
                return authenticator_types["multi"]
            if auth.github:
                return authenticator_types["github"]
            return authenticator_types["native"]

        authenticators.create_authenticator = create_authenticator
        core.authenticators = authenticators
        module_patch.setitem(sys.modules, "core.authenticators", authenticators)

        database = _module("core.database")
        database.init_database = database.create_all_tables = lambda *_args: None
        module_patch.setitem(sys.modules, "core.database", database)
        handler_configs: list[dict[str, object]] = []
        handlers = _module("core.handlers")
        handlers.configure_handlers = lambda **kwargs: handler_configs.append(kwargs)
        handlers.get_handlers = lambda: []
        module_patch.setitem(sys.modules, "core.handlers", handlers)
        metrics = _module("core.metrics_updater")
        metrics.start_metrics_updater = lambda: None
        module_patch.setitem(sys.modules, "core.metrics_updater", metrics)
        spawner_configs: list[object] = []
        spawner = _module("core.spawner")
        spawner.RemoteLabKubeSpawner = type(
            "RemoteLabKubeSpawner", (), {"configure_from_config": lambda config: spawner_configs.append(config)}
        )
        module_patch.setitem(sys.modules, "core.spawner", spawner)

        group_assignments: list[tuple[str, str]] = []
        team_syncs: list[tuple[object, ...]] = []
        groups = _module("core.groups")
        groups.assign_user_to_group = lambda user, group, _db: group_assignments.append((user.name, group))

        async def sync_github_teams_for_user(*args: object, **kwargs: object) -> bool:
            team_syncs.append((*args, kwargs))
            return True

        groups.sync_github_teams_for_user = sync_github_teams_for_user
        groups.is_readonly_group, groups.is_undeletable_group = lambda _group: False, lambda _group: False
        module_patch.setitem(sys.modules, "core.groups", groups)

        jupyterhub = _module("jupyterhub")
        apihandlers = _module("jupyterhub.apihandlers")
        apihandlers.default_handlers = []
        api_groups = _module("jupyterhub.apihandlers.groups")
        api_groups.GroupAPIHandler = type("GroupAPIHandler", (), {})
        api_groups.GroupUsersAPIHandler = type("GroupUsersAPIHandler", (), {})
        jupyterhub.apihandlers = apihandlers
        apihandlers.groups = api_groups
        module_patch.setitem(sys.modules, "jupyterhub", jupyterhub)
        module_patch.setitem(sys.modules, "jupyterhub.apihandlers", apihandlers)
        module_patch.setitem(sys.modules, "jupyterhub.apihandlers.groups", api_groups)
        tornado = _module("tornado")
        web = _module("tornado.web")
        web.HTTPError = RuntimeError
        tornado.web = web
        module_patch.setitem(sys.modules, "tornado", tornado)
        module_patch.setitem(sys.modules, "tornado.web", web)

        setup_spec = importlib.util.spec_from_file_location("core.setup", SETUP)
        assert setup_spec is not None and setup_spec.loader is not None
        setup_module = importlib.util.module_from_spec(setup_spec)
        module_patch.setitem(sys.modules, "core.setup", setup_module)
        setup_spec.loader.exec_module(setup_module)
        if auth.native:
            monkeypatch.setenv("JUPYTERHUB_ADMIN_PASSWORD", "Password1!")
            monkeypatch.setenv("JUPYTERHUB_ADMIN_USERNAME", "admin")
            setup_module._bootstrap_admin_password = lambda *_args, **_kwargs: None
        hub = types.SimpleNamespace(template_vars={}, extra_handlers=[])
        c = types.SimpleNamespace(
            JupyterHub=hub,
            Authenticator=types.SimpleNamespace(),
            Spawner=types.SimpleNamespace(),
            MultiAuthenticator=types.SimpleNamespace(),
        )
        yield types.SimpleNamespace(
            auth=auth,
            config=config,
            c=c,
            factory_inputs=factory_inputs,
            group_assignments=group_assignments,
            team_syncs=team_syncs,
            authenticator_types=authenticator_types,
            settings_reads=settings_reads,
            handler_configs=handler_configs,
            spawner_configs=spawner_configs,
            setup=setup_module,
        )


@pytest.mark.parametrize(
    ("providers", "expected_groups"),
    [
        ((True, False, False, False), {}),
        ((False, True, False, False), {}),
        ((False, False, True, False), {"native-users": []}),
        ((False, False, False, True), {"github-users": []}),
        ((False, False, True, True), {"native-users": [], "github-users": []}),
    ],
)
def test_setup_passes_typed_capabilities_and_creates_only_enabled_groups(
    monkeypatch: pytest.MonkeyPatch, providers: tuple[bool, bool, bool, bool], expected_groups: dict[str, list[object]]
) -> None:
    with _loaded_setup(monkeypatch, providers) as state:
        state.setup.setup_hub(state.c)

        assert state.factory_inputs == [state.auth]
        assert state.c.JupyterHub.load_groups == expected_groups


@pytest.mark.parametrize("providers", ((False, False, False, True), (False, False, True, True)))
def test_setup_loads_github_settings_for_each_github_capability(
    monkeypatch: pytest.MonkeyPatch, providers: tuple[bool, bool, bool, bool]
) -> None:
    with _loaded_setup(monkeypatch, providers) as state:
        state.setup.setup_hub(state.c)

        assert set(GITHUB_SETTINGS).issubset(state.settings_reads)


def test_native_only_setup_never_reads_github_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    with _loaded_setup(monkeypatch, (False, False, True, False)) as state:
        state.setup.setup_hub(state.c)

        assert not any(key.startswith("hub.config.GitHubOAuthenticator") for key in state.settings_reads)


@pytest.mark.parametrize("access_policy", ("all", "group-mapped"))
def test_setup_propagates_effective_access_policy(monkeypatch: pytest.MonkeyPatch, access_policy: str) -> None:
    with _loaded_setup(monkeypatch, (False, False, False, True), access_policy=access_policy) as state:
        state.setup.setup_hub(state.c)

        assert state.spawner_configs == [state.config]
        assert state.handler_configs[0]["access_policy"] == access_policy


@pytest.mark.parametrize("providers", ((False, False, False, True), (False, False, True, True)))
def test_github_prefixed_users_sync_teams_for_each_github_capability(
    monkeypatch: pytest.MonkeyPatch, providers: tuple[bool, bool, bool, bool]
) -> None:
    with _loaded_setup(monkeypatch, providers) as state:
        state.setup.setup_hub(state.c)
        github_user = types.SimpleNamespace(name="github:octo", db=object())
        spawner = types.SimpleNamespace(user=github_user)

        anyio.run(state.c.Spawner.auth_state_hook, spawner, {"access_token": "token"})

        assert spawner.github_access_token == "token"
        assert len(state.team_syncs) == 1
        assert state.group_assignments == [("github:octo", "github-users")]


def test_native_user_retains_native_group_without_github_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    with _loaded_setup(monkeypatch, (False, False, True, True)) as state:
        state.setup.setup_hub(state.c)
        native_user = types.SimpleNamespace(name="learner", db=object())
        spawner = types.SimpleNamespace(user=native_user)

        anyio.run(state.c.Spawner.auth_state_hook, spawner, None)

        assert spawner.github_access_token is None
        assert state.team_syncs == []
        assert state.group_assignments == [("learner", "native-users")]


def test_github_only_preserves_direct_callback_path(monkeypatch: pytest.MonkeyPatch) -> None:
    with _loaded_setup(monkeypatch, (False, False, False, True)) as state:
        state.setup.setup_hub(state.c)

        assert state.c.JupyterHub.authenticator_class is state.authenticator_types["github"]
        assert not hasattr(state.c.MultiAuthenticator, "authenticators")


def test_composed_auth_preserves_prefixed_github_and_unprefixed_native_callbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _loaded_setup(monkeypatch, (False, False, True, True)) as state:
        state.setup.setup_hub(state.c)

        assert state.c.JupyterHub.authenticator_class is state.authenticator_types["multi"]
        assert state.c.MultiAuthenticator.authenticators == [
            {"authenticator_class": state.authenticator_types["github"], "url_prefix": "/github"},
            {
                "authenticator_class": state.authenticator_types["native"],
                "url_prefix": "/native",
                "config": {"prefix": "", "allow_all": True},
            },
        ]


def test_setup_module_cleanup_survives_a_forced_setup_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    missing = object()
    original_modules = {name: sys.modules.get(name, missing) for name in MODULE_NAMES}

    with (
        pytest.raises(RuntimeError, match="forced setup failure"),
        _loaded_setup(monkeypatch, (False, False, False, True), fail_setup=True) as state,
    ):
        state.setup.setup_hub(state.c)

    for name, original_module in original_modules.items():
        if original_module is missing:
            assert name not in sys.modules
        else:
            assert sys.modules[name] is original_module
