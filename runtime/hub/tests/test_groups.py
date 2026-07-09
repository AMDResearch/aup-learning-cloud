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

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core"

if "aiohttp" not in sys.modules:
    aiohttp_module = types.ModuleType("aiohttp")
    aiohttp_module.ClientSession = object
    sys.modules["aiohttp"] = aiohttp_module

if "jupyterhub.orm" not in sys.modules:
    orm_module = types.ModuleType("jupyterhub.orm")
    orm_module.Group = type("Group", (), {})
    sys.modules["jupyterhub.orm"] = orm_module

if "jupyterhub.user" not in sys.modules:
    user_module = types.ModuleType("jupyterhub.user")
    user_module.User = type("User", (), {})
    sys.modules["jupyterhub.user"] = user_module

if "sqlalchemy.orm" not in sys.modules:
    sa_orm_module = types.ModuleType("sqlalchemy.orm")
    sa_orm_module.Session = type("Session", (), {})
    sys.modules["sqlalchemy.orm"] = sa_orm_module

if "core" not in sys.modules:
    core_module = types.ModuleType("core")
    core_module.__path__ = [str(CORE)]
    sys.modules["core"] = core_module

if "core.authenticators" not in sys.modules:
    authenticators_module = types.ModuleType("core.authenticators")
    authenticators_module.__path__ = [str(CORE / "authenticators")]
    sys.modules["core.authenticators"] = authenticators_module

if "core.authenticators.github_app" not in sys.modules:
    github_app_module = types.ModuleType("core.authenticators.github_app")
    github_app_module.GITHUB_USERNAME_PREFIX = "github:"
    sys.modules["core.authenticators.github_app"] = github_app_module


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


groups = load_module("core.groups", CORE / "groups.py")
resolve_resources_for_user = groups.resolve_resources_for_user
fetch_github_team_members = groups.fetch_github_team_members
get_github_app_installation_token = groups.get_github_app_installation_token
fetch_github_team_members_table = groups.fetch_github_team_members_table
sync_user_github_teams = groups.sync_user_github_teams


class DummyGroup:
    def __init__(self, name, source="github-team"):
        self.name = name
        self.properties = {"source": source}


class DummyOrmUser:
    def __init__(self, groups):
        self.groups = groups


class DummyUser:
    def __init__(self, groups, name="github:test"):
        self.name = name
        self.orm_user = DummyOrmUser(groups)


class DummyQuery:
    def filter_by(self, **kwargs):
        return self

    def first(self):
        return None


class DummyDb:
    def query(self, _model):
        return DummyQuery()

    def add(self, _obj):
        pass

    def commit(self):
        pass


class DummyResponse:
    def __init__(self, status, payload):
        self.status = status
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def json(self):
        return self._payload


class DummyClientSession:
    created = 0
    get_calls = 0
    post_calls = 0
    graphql_calls = 0

    def __init__(self):
        type(self).created += 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def get(self, url, headers=None):
        type(self).get_calls += 1
        if url.endswith("/orgs/test-org/installation"):
            return DummyResponse(200, {"id": 12345})
        if url.endswith("/orgs/test-org/teams/missing-team/members?per_page=100&page=1"):
            return DummyResponse(404, {})
        if url.endswith("/orgs/test-org/teams/aup/members?per_page=100&page=1"):
            return DummyResponse(200, [{"login": "OctoUser"}])
        return DummyResponse(200, {"repositories": []})

    def post(self, url, headers=None, json=None):
        type(self).post_calls += 1
        if url.endswith("/app/installations/12345/access_tokens"):
            return DummyResponse(201, {"token": "cached-token", "expires_at": "2099-01-01T00:00:00Z"})
        if url == "https://api.github.com/graphql":
            type(self).graphql_calls += 1
            if "teams(first: 100" in (json or {}).get("query", ""):
                return DummyResponse(
                    200,
                    {
                        "data": {
                            "organization": {
                                "teams": {
                                    "nodes": [{"name": "AUP", "slug": "aup"}],
                                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                                }
                            }
                        }
                    },
                )

            organization = {}
            variables = (json or {}).get("variables", {})
            for key, value in variables.items():
                if not key.startswith("slug"):
                    continue
                index = key.removeprefix("slug")
                if value == "missing-team":
                    organization[f"team{index}"] = None
                elif value == "aup":
                    organization[f"team{index}"] = {
                        "members": {
                            "nodes": [{"login": "OctoUser"}],
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                        }
                    }
                else:
                    organization[f"team{index}"] = {
                        "members": {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}
                    }
            return DummyResponse(200, {"data": {"organization": organization}})
        return DummyResponse(500, {})


def _reset_dummy_client_session():
    DummyClientSession.created = 0
    DummyClientSession.get_calls = 0
    DummyClientSession.post_calls = 0
    DummyClientSession.graphql_calls = 0
    groups._GITHUB_APP_INSTALLATION_ID_CACHE.clear()
    groups._GITHUB_APP_INSTALLATION_TOKEN.clear()
    groups._GITHUB_TEAM_MEMBERS_CACHE.clear()


def test_sync_user_github_teams_skips_removals_when_team_fetch_failed():
    existing_group = DummyGroup("team-a")
    user = DummyUser([existing_group])

    sync_user_github_teams(user, None, {"team-a"}, DummyDb())

    assert user.orm_user.groups == [existing_group]


def test_fetch_github_team_members_treats_missing_team_as_empty_set(monkeypatch, caplog):
    _reset_dummy_client_session()
    monkeypatch.setattr(groups.aiohttp, "ClientSession", DummyClientSession)

    caplog.set_level("WARNING", logger="jupyterhub.groups")
    members = asyncio.run(fetch_github_team_members("token", "test-org", "missing-team"))

    assert members == set()
    assert "team missing-team" in caplog.text
    assert "test-org" in caplog.text


def test_get_github_app_installation_token_discovers_installation_id(monkeypatch):
    _reset_dummy_client_session()
    monkeypatch.setattr(groups.aiohttp, "ClientSession", DummyClientSession)
    monkeypatch.setattr(groups.jwt, "encode", lambda payload, private_key, algorithm: "jwt-token")

    token = asyncio.run(
        get_github_app_installation_token(
            "app-123",
            "",
            org_name="test-org",
            private_key="dummy-private-key",
        )
    )
    cached_token = asyncio.run(
        get_github_app_installation_token(
            "app-123",
            "",
            org_name="test-org",
            private_key="dummy-private-key",
        )
    )

    assert token == "cached-token"
    assert cached_token == "cached-token"
    assert DummyClientSession.created == 2
    assert DummyClientSession.get_calls == 1
    assert DummyClientSession.post_calls == 1


def test_fetch_github_team_members_table_uses_api_slug_and_preserves_group_key(monkeypatch):
    _reset_dummy_client_session()
    monkeypatch.setattr(groups.aiohttp, "ClientSession", DummyClientSession)
    monkeypatch.setattr(groups.jwt, "encode", lambda payload, private_key, algorithm: "jwt-token")

    teams_by_login = asyncio.run(
        fetch_github_team_members_table(
            "app-123",
            "",
            "dummy-private-key",
            "",
            "test-org",
            {"AUP"},
            force=True,
        )
    )

    assert teams_by_login == {"octouser": ["AUP"]}
    assert DummyClientSession.graphql_calls == 2


def test_fetch_github_team_members_table_skips_missing_graphql_team(monkeypatch, caplog):
    _reset_dummy_client_session()
    monkeypatch.setattr(groups.aiohttp, "ClientSession", DummyClientSession)
    monkeypatch.setattr(groups.jwt, "encode", lambda payload, private_key, algorithm: "jwt-token")

    caplog.set_level("WARNING", logger="jupyterhub.groups")
    teams_by_login = asyncio.run(
        fetch_github_team_members_table(
            "app-123",
            "",
            "dummy-private-key",
            "",
            "test-org",
            {"AUP", "missing-team"},
            force=True,
        )
    )

    assert teams_by_login == {"octouser": ["AUP"]}
    assert "configured team missing-team" in caplog.text
    assert DummyClientSession.graphql_calls == 2


def test_resolve_resources_for_user_uses_group_mapping():
    user = DummyUser([DummyGroup("team-a"), DummyGroup("team-b")])

    resources = resolve_resources_for_user(
        user,
        {"team-a": ["cpu", "course-a"], "team-b": ["course-a", "course-b"]},
        "multi",
        ["cpu", "gpu", "code-cpu", "course-a", "course-b"],
    )

    assert set(resources) == {"cpu", "course-a", "course-b"}
    assert resources.count("course-a") == 1


def test_resolve_resources_for_user_falls_back_for_native_users():
    user = DummyUser([], name="native-user")

    resources = resolve_resources_for_user(
        user,
        {"official": ["cpu"], "native-users": ["code-cpu"]},
        "multi",
        ["cpu", "gpu", "code-cpu"],
    )

    assert resources == ["code-cpu"]


def test_resolve_resources_for_user_denies_unmapped_github_users():
    user = DummyUser([])

    resources = resolve_resources_for_user(user, {"official": ["cpu"]}, "multi", ["cpu", "gpu"])

    assert resources == ["none"]


def test_resolve_resources_for_user_uses_all_resources_for_auto_login():
    user = DummyUser([], name="demo-user")

    resources = resolve_resources_for_user(user, {"official": ["cpu"]}, "auto-login", ["cpu", "gpu", "code-cpu"])

    assert resources == ["cpu", "gpu", "code-cpu"]
