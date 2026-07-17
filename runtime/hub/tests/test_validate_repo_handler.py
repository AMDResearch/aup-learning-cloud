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
import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core"

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
    auth_module.CustomFirstUseAuthenticator = type("CustomFirstUseAuthenticator", (), {})
    sys.modules["core.authenticators"] = auth_module

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


git_validation = load_module("core.git_validation", CORE / "git_validation.py")
handlers = load_module("core.handlers", CORE / "handlers.py")
validate_and_sanitize_repo_url = git_validation.validate_and_sanitize_repo_url
ValidateRepoHandler = handlers.ValidateRepoHandler


class DummyUser:
    def __init__(self, auth_state=None):
        self._auth_state = auth_state or {}

    async def get_auth_state(self):
        return self._auth_state


class DummyGitClone:
    def __init__(self, allowed_providers, github_app_name="", default_access_token=""):
        self.allowedProviders = allowed_providers
        self.githubAppName = github_app_name
        self.defaultAccessToken = default_access_token


class DummyConfig:
    def __init__(self, allowed_providers, github_app_name="", default_access_token=""):
        self.git_clone = DummyGitClone(allowed_providers, github_app_name, default_access_token)


def test_validate_repo_url_adds_https_and_strips_tree_and_dot_git():
    ok, error, sanitized = validate_and_sanitize_repo_url(
        "github.com/example/project.git/tree/main",
        ["github.com"],
    )
    assert ok is True
    assert error == ""
    assert sanitized == "https://github.com/example/project"


def test_validate_repo_url_rejects_disallowed_host():
    ok, error, sanitized = validate_and_sanitize_repo_url(
        "https://evil.example.com/org/repo",
        ["github.com", "gitlab.com"],
    )
    assert ok is False
    assert "not authorized" in error
    assert sanitized == ""


def test_validate_repo_post_returns_400_for_invalid_json(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "core.config",
        types.SimpleNamespace(
            HubConfig=type("HubConfig", (), {"get": staticmethod(lambda: DummyConfig(["github.com"]))})
        ),
    )

    handler = object.__new__(ValidateRepoHandler)
    handler.request = types.SimpleNamespace(body=b"{not-json")
    handler.current_user = DummyUser()

    captured = {}
    handler.set_status = lambda status: captured.setdefault("status", status)
    handler.set_header = lambda key, value: captured.setdefault("headers", {}).__setitem__(key, value)
    handler.finish = lambda payload: captured.setdefault("body", payload)

    import asyncio

    asyncio.run(handler.post())

    assert captured["status"] == 400
    assert captured["headers"]["Content-Type"] == "application/json"
    assert json.loads(captured["body"]) == {"error": "Invalid JSON"}


def test_validate_repo_post_rejects_disallowed_provider_before_remote_call(monkeypatch):
    monkeypatch.setitem(
        sys.modules,
        "core.config",
        types.SimpleNamespace(
            HubConfig=type("HubConfig", (), {"get": staticmethod(lambda: DummyConfig(["github.com"]))})
        ),
    )

    handler = object.__new__(ValidateRepoHandler)
    handler.request = types.SimpleNamespace(
        body=json.dumps({"url": "https://evil.example.com/org/repo", "branch": "main"}).encode("utf-8")
    )
    handler.current_user = DummyUser()

    called = {"value": False}

    async def fake_validate(url, branch, token):
        called["value"] = True
        return {"valid": True, "error": ""}

    handler._validate = fake_validate
    handler.set_header = lambda key, value: None
    result = {}
    handler.finish = lambda payload: result.setdefault("payload", payload)

    import asyncio

    asyncio.run(handler.post())

    assert called["value"] is False
    assert json.loads(result["payload"])["valid"] is False
    assert "not authorized" in json.loads(result["payload"])["error"]
