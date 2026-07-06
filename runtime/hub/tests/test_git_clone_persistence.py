import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core"

if "core" not in sys.modules:
    core_module = types.ModuleType("core")
    core_module.__path__ = [str(CORE)]
    sys.modules["core"] = core_module

if "core.metrics" not in sys.modules:
    metrics_module = types.ModuleType("core.metrics")

    class DummyMetric:
        def labels(self, **_kwargs):
            return self

        def inc(self):
            pass

        def observe(self, _value):
            pass

    for metric_name in [
        "pod_failure_total",
        "repo_clone_failed_total",
        "session_runtime_minutes",
        "spawn_duration_seconds",
        "spawn_failed_total",
        "spawn_gpu_total",
    ]:
        setattr(metrics_module, metric_name, DummyMetric())
    sys.modules["core.metrics"] = metrics_module

if "jupyterhub.user" not in sys.modules:
    jupyterhub_module = sys.modules.setdefault("jupyterhub", types.ModuleType("jupyterhub"))
    user_module = types.ModuleType("jupyterhub.user")
    user_module.User = type("User", (), {})
    sys.modules["jupyterhub"] = jupyterhub_module
    sys.modules["jupyterhub.user"] = user_module

if "kubespawner" not in sys.modules:
    kubespawner_module = types.ModuleType("kubespawner")
    kubespawner_module.KubeSpawner = type("KubeSpawner", (), {})
    sys.modules["kubespawner"] = kubespawner_module

if "tornado.web" not in sys.modules:
    tornado_module = sys.modules.setdefault("tornado", types.ModuleType("tornado"))
    web_module = types.ModuleType("tornado.web")
    web_module.HTTPError = type("HTTPError", (Exception,), {})
    sys.modules["tornado"] = tornado_module
    sys.modules["tornado.web"] = web_module


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


config = load_module("core.config", CORE / "config.py")
kubernetes = load_module("core.spawner.kubernetes", CORE / "spawner" / "kubernetes.py")
GitCloneSettings = config.GitCloneSettings
ResourceMetadata = config.ResourceMetadata
RemoteLabKubeSpawner = kubernetes.RemoteLabKubeSpawner


class StubHubConfig:
    def __init__(
        self,
        git_clone_settings: GitCloneSettings | None = None,
        resource_metadata: dict[str, ResourceMetadata] | None = None,
    ):
        self.git_clone = git_clone_settings or GitCloneSettings()
        self._resource_metadata = resource_metadata or {}

    def get_resource_metadata(self, resource_type: str):
        return self._resource_metadata.get(resource_type)


def make_spawner(
    git_clone_settings: GitCloneSettings | None = None,
    resource_metadata: dict[str, ResourceMetadata] | None = None,
):
    spawner = object.__new__(RemoteLabKubeSpawner)
    spawner._hub_config = StubHubConfig(git_clone_settings, resource_metadata)
    spawner.MAX_CLONE_TIMEOUT = 123
    spawner.GIT_INIT_CONTAINER_IMAGE = "alpine/git:test"
    spawner.DEFAULT_ACCESS_TOKEN = False
    spawner.DEFAULT_ACCESS_TOKEN_SECRET = "unused-default-token-secret"
    spawner.environment = {}
    spawner.notebook_dir = "/home/jovyan"
    spawner.default_url = ""
    return spawner


def env_value(container: dict, name: str) -> str:
    for item in container["env"]:
        if item["name"] == name:
            return item["value"]
    raise AssertionError(f"missing env var: {name}")


def test_git_clone_settings_defaults_keep_repositories_by_default():
    settings = GitCloneSettings()

    assert settings.allowPersistenceChoice is False
    assert settings.defaultPersistence is True


def test_git_clone_settings_explicit_persistence_overrides_parse_correctly():
    settings = GitCloneSettings(allowPersistenceChoice=True, defaultPersistence=False)

    assert settings.allowPersistenceChoice is True
    assert settings.defaultPersistence is False


def test_repo_persist_submission_is_ignored_when_admin_choice_is_disabled():
    spawner = make_spawner(GitCloneSettings(allowPersistenceChoice=False, defaultPersistence=True))

    result = spawner._resolve_repo_persist_option({"repo_persist": ["false"]})

    assert result is True


def test_invalid_repo_persist_submission_falls_back_to_admin_default():
    spawner = make_spawner(GitCloneSettings(allowPersistenceChoice=True, defaultPersistence=False))

    result = spawner._resolve_repo_persist_option({"repo_persist": ["maybe"]})

    assert result is False


def test_persistent_init_container_sets_env_without_cleanup_lifecycle():
    spawner = make_spawner()

    container = asyncio.run(
        spawner._build_git_init_container(
            repo_url="https://github.com/example/course",
            repo_name="course",
            home_volume_name="volume-student",
            home_mount_path="/home/jovyan",
            repo_persist=True,
        )
    )

    assert env_value(container, "PERSIST_CLONED_REPO") == "true"
    assert env_value(container, "AUPLC_GIT_METADATA_DIR") == "/home/jovyan/.auplc/git-clones"
    assert "lifecycle" not in container


def test_ephemeral_init_container_sets_env_and_cleanup_preserves_existing_config():
    spawner = make_spawner()

    container = asyncio.run(
        spawner._build_git_init_container(
            repo_url="https://github.com/example/course",
            repo_name="course",
            home_volume_name="volume-student",
            home_mount_path="/home/jovyan",
            repo_persist=False,
            repo_branch="main",
        )
    )
    existing_config = {
        "lifecycle": {"postStart": {"exec": {"command": ["touch", "/tmp/ready"]}}},
        "securityContext": {"runAsUser": 1000, "runAsNonRoot": True},
    }

    merged_config = RemoteLabKubeSpawner._with_ephemeral_clone_cleanup(existing_config, "/home/jovyan/course")

    assert env_value(container, "PERSIST_CLONED_REPO") == "false"
    assert env_value(container, "BRANCH") == "main"
    assert merged_config is not existing_config
    assert merged_config["securityContext"] == existing_config["securityContext"]
    assert merged_config["lifecycle"]["postStart"] == existing_config["lifecycle"]["postStart"]
    assert merged_config["lifecycle"]["preStop"] == {"exec": {"command": ["rm", "-rf", "/home/jovyan/course"]}}
    assert "preStop" not in existing_config["lifecycle"]


def test_target_path_resolver_prefers_custom_repo_path_over_resource_default_path():
    spawner = make_spawner(resource_metadata={"Course-CV": ResourceMetadata(defaultPath="/opt/workspace/CV")})

    result = spawner._resolve_target_path("Course-CV", "/home/jovyan/custom-repo")

    assert result == "/home/jovyan/custom-repo"


def test_target_path_resolver_uses_resource_default_path_without_custom_repo():
    spawner = make_spawner(resource_metadata={"Course-CV": ResourceMetadata(defaultPath="/opt/workspace/CV")})

    result = spawner._resolve_target_path("Course-CV")

    assert result == "/opt/workspace/CV"


def test_target_path_resolver_falls_back_to_home_without_custom_repo_or_default_path():
    spawner = make_spawner(resource_metadata={"cpu": ResourceMetadata()})

    result = spawner._resolve_target_path("cpu")

    assert result == "/home/jovyan"


@pytest.mark.parametrize(
    ("target_path", "expected_url"),
    [
        ("/", "/lab/tree/"),
        ("/home/jovyan", "/lab/tree/home/jovyan"),
        ("/opt/workspace/CV", "/lab/tree/opt/workspace/CV"),
        ("/opt/workspace/My Course", "/lab/tree/opt/workspace/My%20Course"),
        ("/opt/workspace/a#b", "/lab/tree/opt/workspace/a%23b"),
    ],
)
def test_jupyterlab_target_path_mapping_uses_root_notebook_dir_and_encoded_tree_url(target_path, expected_url):
    spawner = make_spawner()

    spawner._apply_target_path_mapping("cpu", target_path)

    assert spawner.notebook_dir == "/"
    assert spawner.default_url == expected_url
    assert "AUPLC_CODE_WORKDIR" not in spawner.environment


@pytest.mark.parametrize(
    "target_path",
    [
        "/",
        "/home/jovyan",
        "/opt/workspace/CV",
        "/opt/workspace/My Course",
        "/opt/workspace/a#b",
    ],
)
def test_code_server_target_path_mapping_sets_workdir_without_replacing_default_url(target_path):
    spawner = make_spawner()
    spawner.default_url = "/existing-default"

    spawner._apply_target_path_mapping("code-cpu", target_path)

    assert spawner.environment["AUPLC_CODE_WORKDIR"] == target_path
    assert spawner.default_url == "/existing-default"
