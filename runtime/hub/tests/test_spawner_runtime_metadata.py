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


def build_env(runtime_minutes: int, runtime_unlimited: bool, quota_rate: int = 3):
    return RemoteLabKubeSpawner._build_runtime_metadata_env(
        start_time=1_717_171_717,
        runtime_minutes=runtime_minutes,
        quota_rate=quota_rate,
        runtime_unlimited=runtime_unlimited,
    )


def test_finite_runtime_metadata_includes_positive_job_run_time():
    env = build_env(runtime_minutes=120, runtime_unlimited=False)

    assert env == {
        "JOB_START_TIME": "1717171717",
        "JOB_RUN_TIME": "120",
        "QUOTA_RATE": "3",
    }
    assert "AUPLC_RUNTIME_UNLIMITED" not in env


def test_quota_unlimited_finite_runtime_metadata_stays_finite():
    env = build_env(runtime_minutes=120, runtime_unlimited=False, quota_rate=0)

    assert env["JOB_RUN_TIME"] == "120"
    assert env["QUOTA_RATE"] == "0"
    assert "AUPLC_RUNTIME_UNLIMITED" not in env


def test_single_node_no_limit_runtime_metadata_uses_unlimited_flag():
    env = build_env(runtime_minutes=120, runtime_unlimited=True)

    assert env == {
        "JOB_START_TIME": "1717171717",
        "QUOTA_RATE": "3",
        "AUPLC_RUNTIME_UNLIMITED": "true",
    }
    assert "JOB_RUN_TIME" not in env
    assert "4320" not in env.values()
