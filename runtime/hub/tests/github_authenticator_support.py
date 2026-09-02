import importlib.util
import inspect
import sys
import types
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GITHUB_APP = ROOT / "core" / "authenticators" / "github_app.py"
MULTI = ROOT / "core" / "authenticators" / "multi.py"


class _Logger:
    def warning(self, *_args, **_kwargs) -> None:
        pass

    def info(self, *_args, **_kwargs) -> None:
        pass

    def error(self, *_args, **_kwargs) -> None:
        pass


@contextmanager
def loaded_authenticators(monkeypatch: pytest.MonkeyPatch) -> Iterator[types.SimpleNamespace]:
    with monkeypatch.context() as module_patch:
        core = types.ModuleType("core")
        core.__path__ = [str(ROOT / "core")]
        authenticators = types.ModuleType("core.authenticators")
        authenticators.__path__ = [str(ROOT / "core" / "authenticators")]
        core.authenticators = authenticators
        firstuse = types.ModuleType("core.authenticators.firstuse")
        firstuse.CustomFirstUseAuthenticator = type("CustomFirstUseAuthenticator", (), {})
        oauthenticator = types.ModuleType("oauthenticator")
        github = types.ModuleType("oauthenticator.github")
        oauth2 = types.ModuleType("oauthenticator.oauth2")

        class GitHubOAuthenticator:
            def __init__(self) -> None:
                self.enable_auth_state = True
                self.allow_all = False
                self.allow_existing_users = True
                self.allowed_users: set[str] = set()
                self.admin_users: set[str] = set()
                self.blocked_users: set[str] = set()
                self.allowed_organizations: set[str] = set()
                self.organization_members: dict[str, set[str]] = {}
                self.policy_names: list[str] = []
                self.post_auth_models: list[dict] = []
                self.child_add_names: list[str] = []
                self.child_delete_names: list[str] = []
                self.refresh_token_response: dict = {}
                self.refreshed_auth_model: dict = {}
                self.oauth_callback_url = ""
                self.log = _Logger()

            def login_url(self, base_url: str) -> str:
                return f"{base_url.rstrip('/')}/oauth_login"

            def get_handlers(self, _app) -> list[tuple[str, type]]:
                return [
                    ("/oauth_login", type("LoginHandler", (), {})),
                    ("/oauth_callback", type("CallbackHandler", (), {})),
                    ("/logout", type("LogoutHandler", (), {})),
                ]

            def get_callback_url(self, handler=None) -> str:
                if self.oauth_callback_url:
                    return self.oauth_callback_url
                if handler is not None:
                    return f"{handler.request.protocol}://{handler.request.host}{handler.hub.server.base_url}oauth_callback"
                return "https://hub.example/hub/oauth_callback"

            async def authenticate(self, _handler, data=None):
                data = data or {}
                username = data["login"].lower()
                self.policy_names.append(username)
                if username in self.blocked_users:
                    return None
                organization_allowed = any(
                    username in self.organization_members.get(organization, set())
                    for organization in self.allowed_organizations
                )
                if (
                    not self.allow_all
                    and (self.allowed_users or self.allowed_organizations)
                    and username not in self.allowed_users
                    and not organization_allowed
                ):
                    return None
                return {
                    "name": username,
                    "admin": username in self.admin_users,
                    "auth_state": {"token_response": data.get("token_response", {})},
                }

            async def run_post_auth_hook(self, _handler, auth_model):
                self.post_auth_models.append(auth_model)
                return auth_model

            def add_user(self, user) -> None:
                self.child_add_names.append(user.name)
                if self.allow_existing_users and not self.allow_all:
                    self.allowed_users.add(user.name)

            def delete_user(self, user) -> None:
                self.child_delete_names.append(user.name)
                self.allowed_users.discard(user.name)

            def build_refresh_token_request_params(self, refresh_token: str) -> dict[str, str]:
                return {"refresh_token": refresh_token}

            async def get_token_info(self, _handler, _params) -> dict:
                return self.refresh_token_response.copy()

            async def _token_to_auth_model(self, _token_info) -> dict:
                return self.refreshed_auth_model.copy()

        class OAuthCallbackHandler:
            def get_argument(self, name: str, default: str = "") -> str:
                return self.arguments.get(name, default)

            def redirect(self, url: str) -> None:
                self.redirected_to = url

            async def get(self) -> None:
                self.parent_get_called = True

        class MultiAuthenticator:
            def __init__(self) -> None:
                self._authenticators = []
                self.outer_add_names: list[str] = []
                self.outer_delete_names: list[str] = []

            def validate_username(self, _username: str) -> bool:
                return True

            def add_user(self, user) -> None:
                self.outer_add_names.append(user.name)

            def delete_user(self, user) -> None:
                self.outer_delete_names.append(user.name)

        github.GitHubOAuthenticator = GitHubOAuthenticator
        oauth2.OAuthCallbackHandler = OAuthCallbackHandler
        oauthenticator.github, oauthenticator.oauth2 = github, oauth2
        multiauthenticator = types.ModuleType("multiauthenticator")
        multiauthenticator.MultiAuthenticator = MultiAuthenticator
        multiauthenticator_module = types.ModuleType("multiauthenticator.multiauthenticator")
        multiauthenticator_module.PREFIX_SEPARATOR = ":"
        groups_module = types.ModuleType("core.groups")
        membership_calls: list[str] = []

        async def ensure_user_group_membership(user, _db, *, refresh_github_teams=False):
            membership_calls.append(user.name)

        groups_module.ensure_user_group_membership = ensure_user_group_membership

        jupyterhub_utils = types.ModuleType("jupyterhub.utils")

        async def maybe_future(obj):
            if inspect.isawaitable(obj):
                return await obj
            return obj

        jupyterhub_utils.maybe_future = maybe_future

        modules = {
            "core": core,
            "core.authenticators": authenticators,
            "core.authenticators.firstuse": firstuse,
            "oauthenticator": oauthenticator,
            "oauthenticator.github": github,
            "oauthenticator.oauth2": oauth2,
            "multiauthenticator": multiauthenticator,
            "multiauthenticator.multiauthenticator": multiauthenticator_module,
            "core.groups": groups_module,
            "jupyterhub.utils": jupyterhub_utils,
        }
        for name, module in modules.items():
            module_patch.setitem(sys.modules, name, module)

        github_spec = importlib.util.spec_from_file_location("core.authenticators.github_app", GITHUB_APP)
        assert github_spec is not None and github_spec.loader is not None
        github_module = importlib.util.module_from_spec(github_spec)
        module_patch.setitem(sys.modules, "core.authenticators.github_app", github_module)
        github_spec.loader.exec_module(github_module)

        multi_spec = importlib.util.spec_from_file_location("core.authenticators.multi", MULTI)
        assert multi_spec is not None and multi_spec.loader is not None
        multi_module = importlib.util.module_from_spec(multi_spec)
        module_patch.setitem(sys.modules, "core.authenticators.multi", multi_module)
        multi_spec.loader.exec_module(multi_module)

        yield types.SimpleNamespace(github=github_module, multi=multi_module, membership_calls=membership_calls)
