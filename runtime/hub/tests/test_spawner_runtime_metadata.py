# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

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
    jupyterhub_module = types.ModuleType("jupyterhub")
    user_module = types.ModuleType("jupyterhub.user")
    user_module.User = type("User", (), {})
    sys.modules["jupyterhub"] = jupyterhub_module
    sys.modules["jupyterhub.user"] = user_module

if "kubespawner" not in sys.modules:
    kubespawner_module = types.ModuleType("kubespawner")
    kubespawner_module.KubeSpawner = type("KubeSpawner", (), {})
    sys.modules["kubespawner"] = kubespawner_module

if "tornado.web" not in sys.modules:
    tornado_module = types.ModuleType("tornado")
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


kubernetes = load_module("core.spawner.kubernetes", CORE / "spawner" / "kubernetes.py")
RemoteLabKubeSpawner = kubernetes.RemoteLabKubeSpawner


def build_env(runtime_minutes: int, runtime_limit_enabled: bool, quota_rate: int = 3):
    return RemoteLabKubeSpawner._build_runtime_metadata_env(
        start_time=1_717_171_717,
        runtime_minutes=runtime_minutes,
        quota_rate=quota_rate,
        runtime_limit_enabled=runtime_limit_enabled,
    )


def test_finite_runtime_metadata_includes_positive_job_run_time():
    env = build_env(runtime_minutes=120, runtime_limit_enabled=True)

    assert env == {
        "JOB_START_TIME": "1717171717",
        "JOB_RUN_TIME": "120",
        "QUOTA_RATE": "3",
    }
    assert "AUPLC_RUNTIME_UNLIMITED" not in env


def test_quota_unlimited_finite_runtime_metadata_stays_finite():
    env = build_env(runtime_minutes=120, runtime_limit_enabled=True, quota_rate=0)

    assert env["JOB_RUN_TIME"] == "120"
    assert env["QUOTA_RATE"] == "0"
    assert "AUPLC_RUNTIME_UNLIMITED" not in env


def test_runtime_limit_disabled_metadata_uses_unlimited_flag():
    env = build_env(runtime_minutes=120, runtime_limit_enabled=False)

    assert env == {
        "JOB_START_TIME": "1717171717",
        "QUOTA_RATE": "3",
        "AUPLC_RUNTIME_UNLIMITED": "true",
    }
    assert "JOB_RUN_TIME" not in env
    assert "4320" not in env.values()


@pytest.mark.parametrize("runtime_limit_enabled", [True, False])
def test_start_schedules_shutdown_only_when_runtime_limit_enabled(
    monkeypatch: pytest.MonkeyPatch, runtime_limit_enabled: bool
) -> None:
    class QuotaManager:
        def start_usage_session(self, *_args: str) -> str:
            return "usage-session"

    class TimerLoop:
        def __init__(self) -> None:
            self.calls: list[tuple[int, object]] = []

        def call_later(self, delay: int, callback: object) -> str:
            self.calls.append((delay, callback))
            return "timer"

    quota_module = types.ModuleType("core.quota")
    quota_module.get_quota_manager = lambda: QuotaManager()
    monkeypatch.setitem(sys.modules, "core.quota", quota_module)

    async def base_start(_spawner: object) -> str:
        return "started"

    timer_loop = TimerLoop()
    monkeypatch.setattr(kubernetes.KubeSpawner, "start", base_start, raising=False)
    monkeypatch.setattr(kubernetes.time, "time", lambda: 1_717_171_717)
    monkeypatch.setattr(kubernetes.asyncio, "get_event_loop", lambda: timer_loop)

    spawner = object.__new__(RemoteLabKubeSpawner)
    spawner.user = types.SimpleNamespace(name="student")
    spawner.user_options = {"runtime_minutes": 120, "resource_type": "cpu"}
    spawner.resource_images = {"cpu": "cpu-image"}
    spawner.quota_enabled = False
    spawner.runtime_limit_enabled = runtime_limit_enabled
    spawner.environment = {}
    spawner.extra_pod_config = {}
    spawner.notebook_allowed_origins = []
    spawner._hub_config = None
    spawner.log = types.SimpleNamespace(debug=lambda _message: None)
    spawner._resolve_user_resources = lambda: ["cpu"]
    spawner._resolve_accelerator_selection = lambda _resource_type, _selection: None
    spawner._configure_spawner = lambda _resource_type, _selection: None
    spawner._launches_code_server = lambda _resource_type: False

    result = kubernetes.asyncio.run(spawner.start())

    assert result == "started"
    if runtime_limit_enabled:
        assert spawner.shutdown_time == 1_717_178_917
        assert spawner.check_timer == "timer"
        assert timer_loop.calls == [(60, spawner.check_timeout)]
        assert spawner.environment["JOB_RUN_TIME"] == "120"
        assert "AUPLC_RUNTIME_UNLIMITED" not in spawner.environment
    else:
        assert spawner.shutdown_time is None
        assert spawner.check_timer is None
        assert timer_loop.calls == []
        assert spawner.environment["AUPLC_RUNTIME_UNLIMITED"] == "true"
        assert "JOB_RUN_TIME" not in spawner.environment


def test_start_resolves_auto_with_authorized_keys_and_configures_once(monkeypatch: pytest.MonkeyPatch) -> None:
    class QuotaManager:
        def start_usage_session(self, *_args: str) -> str:
            return "usage-session"

    metadata = types.SimpleNamespace(acceleratorKeys=["gpu-a", "gpu-b"], allowGitClone=False)
    quota_module = types.SimpleNamespace(get_quota_manager=lambda: QuotaManager())
    monkeypatch.setitem(sys.modules, "core.quota", quota_module)

    async def base_start(_spawner: object) -> str:
        return "started"

    monkeypatch.setattr(kubernetes.KubeSpawner, "start", base_start, raising=False)

    spawner = object.__new__(RemoteLabKubeSpawner)
    spawner.user = types.SimpleNamespace(name="student")
    spawner.user_options = {"runtime_minutes": 20, "resource_type": "gpu", "gpu_selection": "auto"}
    spawner.resource_images = {"gpu": "gpu-image"}
    spawner.resource_requirements = {"gpu": {"cpu": "1", "memory": "1Gi", "amd.com/gpu": "1"}}
    spawner.accelerator_options = {"gpu-a": {}, "gpu-b": {}}
    spawner.quota_enabled = False
    spawner.runtime_limit_enabled = False
    spawner.environment = {}
    spawner.extra_pod_config = {}
    spawner.notebook_allowed_origins = []
    spawner._hub_config = types.SimpleNamespace(get_resource_metadata=lambda _resource_type: metadata)
    spawner.log = types.SimpleNamespace(debug=lambda _message: None, info=lambda _message: None)
    spawner._resolve_user_resources = lambda: ["gpu"]
    spawner._launches_code_server = lambda _resource_type: False
    spawner._resolve_target_path = lambda _resource_type, _custom_repo_path: None
    spawner._apply_target_path_mapping = lambda _resource_type, _target_path: None

    auto_calls: list[list[str]] = []
    configure_calls: list[tuple[str, str | None]] = []

    async def resolve_auto(resource_type: str, eligible_keys: list[str]) -> str:
        assert resource_type == "gpu"
        auto_calls.append(eligible_keys)
        return "gpu-b"

    def configure(resource_type: str, selection: str | None) -> None:
        configure_calls.append((resource_type, selection))

    spawner._resolve_auto_accelerator = resolve_auto
    spawner._configure_spawner = configure

    result = kubernetes.asyncio.run(spawner.start())

    assert result == "started"
    assert auto_calls == [["gpu-a", "gpu-b"]]
    assert spawner.user_options["gpu_selection"] == "gpu-b"
    assert configure_calls == [("gpu", "gpu-b")]


@pytest.mark.parametrize(
    ("auto_result", "error"),
    [
        ("gpu-x", "not authorized"),
        ("gpu-unconfigured", "not configured"),
        (None, "must return a concrete accelerator"),
        ("", "must return a concrete accelerator"),
        ("   ", "must return a concrete accelerator"),
        ("auto", "must return a concrete accelerator"),
    ],
)
def test_start_rejects_auto_result_that_is_not_an_authorized_concrete_accelerator(
    auto_result: str | None, error: str
) -> None:
    metadata = types.SimpleNamespace(acceleratorKeys=["gpu-a", "gpu-unconfigured"], allowGitClone=False)

    spawner = object.__new__(RemoteLabKubeSpawner)
    spawner.user = types.SimpleNamespace(name="student")
    spawner.user_options = {"runtime_minutes": 20, "resource_type": "gpu", "gpu_selection": "auto"}
    spawner.resource_images = {"gpu": "gpu-image"}
    spawner.resource_requirements = {"gpu": {"cpu": "1", "memory": "1Gi", "amd.com/gpu": "1"}}
    spawner.accelerator_options = {"gpu-a": {}}
    spawner.extra_pod_config = {}
    spawner._hub_config = types.SimpleNamespace(get_resource_metadata=lambda _resource_type: metadata)
    spawner._resolve_user_resources = lambda: ["gpu"]
    auto_calls: list[list[str]] = []

    async def resolve_auto(_resource_type: str, eligible_keys: list[str]) -> str | None:
        auto_calls.append(eligible_keys)
        return auto_result

    spawner._resolve_auto_accelerator = resolve_auto
    spawner._configure_spawner = lambda *_args: pytest.fail("invalid auto result configured the spawner")

    with pytest.raises(RuntimeError, match=error):
        kubernetes.asyncio.run(spawner.start())

    assert auto_calls == [["gpu-a", "gpu-unconfigured"]]
