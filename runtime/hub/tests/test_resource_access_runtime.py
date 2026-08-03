import asyncio
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest
from onboarding_handlers_support import load_handlers

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core"
GROUP_TEST = ROOT / "tests" / "test_groups.py"


def load_groups_test_module(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("task7_groups_test", GROUP_TEST)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def load_spawner(monkeypatch: pytest.MonkeyPatch, groups: types.ModuleType) -> type:
    core = types.ModuleType("core")
    core.__path__ = [str(CORE)]
    metrics = types.ModuleType("core.metrics")
    metric = type(
        "Metric",
        (),
        {"labels": lambda self, **_kwargs: self, "inc": lambda self: None, "observe": lambda self, _value: None},
    )()
    for name in (
        "pod_failure_total",
        "repo_clone_failed_total",
        "session_runtime_minutes",
        "spawn_duration_seconds",
        "spawn_failed_total",
        "spawn_gpu_total",
    ):
        setattr(metrics, name, metric)
    jupyterhub = types.ModuleType("jupyterhub")
    jupyterhub.__path__ = []
    user = types.ModuleType("jupyterhub.user")
    user.User = type("User", (), {})
    kubespawner = types.ModuleType("kubespawner")
    kubespawner.KubeSpawner = type("KubeSpawner", (), {})
    tornado = types.ModuleType("tornado")
    web = types.ModuleType("tornado.web")
    web.HTTPError = RuntimeError
    monkeypatch.setitem(sys.modules, "core", core)
    monkeypatch.setitem(sys.modules, "core.metrics", metrics)
    monkeypatch.setitem(sys.modules, "core.groups", groups)
    monkeypatch.setitem(sys.modules, "jupyterhub", jupyterhub)
    monkeypatch.setitem(sys.modules, "jupyterhub.user", user)
    monkeypatch.setitem(sys.modules, "kubespawner", kubespawner)
    monkeypatch.setitem(sys.modules, "tornado", tornado)
    monkeypatch.setitem(sys.modules, "tornado.web", web)
    spec = importlib.util.spec_from_file_location("core.spawner.kubernetes", CORE / "spawner" / "kubernetes.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module.RemoteLabKubeSpawner


@pytest.mark.parametrize(
    ("access_policy", "expected_resources"),
    (("all", ["cpu", "gpu", "code-cpu"]), ("group-mapped", ["gpu"])),
)
def test_spawner_uses_configured_access_policy_for_exact_resource_list(
    monkeypatch: pytest.MonkeyPatch, access_policy: str, expected_resources: list[str]
) -> None:
    groups_test = load_groups_test_module(monkeypatch)
    spawner_type = load_spawner(monkeypatch, groups_test.groups)
    spawner = object.__new__(spawner_type)
    spawner.user = groups_test.DummyUser([groups_test.DummyGroup("team-gpu")], name="native-user")
    spawner.team_resource_mapping = {"team-gpu": ["gpu"], "native-users": ["cpu"]}
    spawner.resource_images = {"cpu": "cpu-image", "gpu": "gpu-image", "code-cpu": "code-image"}
    spawner.access_policy = access_policy
    spawner.log = types.SimpleNamespace(debug=lambda _message: None)

    assert asyncio.run(spawner.get_user_resources()) == expected_resources


@pytest.mark.parametrize(
    ("access_policy", "expected_resources"),
    (("all", ["code-cpu", "cpu", "gpu"]), ("group-mapped", ["gpu"])),
)
def test_resources_api_uses_configured_access_policy_for_exact_resource_list(
    monkeypatch: pytest.MonkeyPatch, access_policy: str, expected_resources: list[str]
) -> None:
    groups_test = load_groups_test_module(monkeypatch)
    monkeypatch.delitem(sys.modules, "tornado", raising=False)
    monkeypatch.delitem(sys.modules, "tornado.web", raising=False)
    with load_handlers(monkeypatch) as loaded:
        config = types.SimpleNamespace(
            resources=types.SimpleNamespace(
                images={"cpu": "cpu-image", "gpu": "gpu-image", "code-cpu": "code-image"}, groupOrder=[]
            ),
            accelerators={},
            git_clone=types.SimpleNamespace(
                allowedProviders=[], githubAppName="", allowPersistenceChoice=False, defaultPersistence=True
            ),
            get_resource_image=lambda key: {"cpu": "cpu-image", "gpu": "gpu-image", "code-cpu": "code-image"}.get(key),
            get_resource_requirements=lambda _key: None,
            get_resource_metadata=lambda _key: None,
        )
        config_module = types.ModuleType("core.config")
        config_module.HubConfig = type("HubConfig", (), {"get": staticmethod(lambda: config)})
        monkeypatch.setitem(sys.modules, "core.config", config_module)
        monkeypatch.setitem(sys.modules, "core.groups", groups_test.groups)
        loaded.handlers.configure_handlers(
            team_resource_mapping={"team-gpu": ["gpu"], "native-users": ["cpu"]}, access_policy=access_policy
        )
        handler = object.__new__(loaded.handlers.ResourcesAPIHandler)
        handler.current_user = groups_test.DummyUser([groups_test.DummyGroup("team-gpu")], name="native-user")
        response: dict[str, str] = {}
        handler.set_header = lambda _key, _value: None
        handler.finish = lambda body: response.setdefault("body", body)

        asyncio.run(handler.get())

    assert [resource["key"] for resource in json.loads(response["body"])["resources"]] == expected_resources


def test_configure_handlers_replaces_optional_policy_and_mapping_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delitem(sys.modules, "tornado", raising=False)
    monkeypatch.delitem(sys.modules, "tornado.web", raising=False)
    with load_handlers(monkeypatch) as loaded:
        loaded.handlers.configure_handlers(
            accelerator_options={"gpu": {}},
            quota_rates={"gpu": 2},
            team_resource_mapping={"team": ["gpu"]},
            access_policy="all",
        )
        loaded.handlers.configure_handlers(access_policy="group-mapped")

        assert loaded.handlers._handler_config["accelerator_options"] == {}
        assert loaded.handlers._handler_config["quota_rates"] == {}
        assert loaded.handlers._handler_config["team_resource_mapping"] == {}
        assert loaded.handlers._handler_config["access_policy"] == "group-mapped"
