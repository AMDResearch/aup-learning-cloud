from types import SimpleNamespace

import anyio
import pytest
from github_authenticator_support import loaded_authenticators


def test_direct_github_auth_authorizes_raw_login_then_prefixes_accepted_model(monkeypatch: pytest.MonkeyPatch) -> None:
    with loaded_authenticators(monkeypatch) as modules:
        authenticator = modules.github.CustomGitHubOAuthenticator()
        authenticator.admin_users = {"octo"}
        authenticator.allowed_organizations = {"auplc"}
        authenticator.organization_members = {"auplc": {"octo"}}
        raw_model = anyio.run(authenticator.authenticate, None, {"login": "Octo"})
        prefixed_model = anyio.run(authenticator.run_post_auth_hook, None, raw_model)

        assert authenticator.policy_names == ["octo"]
        assert authenticator.post_auth_models == [raw_model]
        assert raw_model["name"] == "octo"
        assert prefixed_model["name"] == "github:octo"
        assert prefixed_model["admin"] is True


def test_github_organization_policy_rejects_nonmember_when_allow_all_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with loaded_authenticators(monkeypatch) as modules:
        authenticator = modules.github.CustomGitHubOAuthenticator()
        authenticator.allowed_organizations = {"auplc"}
        authenticator.organization_members = {"auplc": {"octo"}}

        auth_model = anyio.run(authenticator.authenticate, None, {"login": "outside"})

        assert authenticator.allow_all is False
        assert auth_model is None
        assert authenticator.policy_names == ["outside"]


def test_github_post_auth_prefixing_copies_only_top_level_model_and_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with loaded_authenticators(monkeypatch) as modules:
        authenticator = modules.github.CustomGitHubOAuthenticator()
        auth_state = {"github_user": {"login": "octo"}}
        raw_model = {"name": "octo", "auth_state": auth_state, "admin": None}
        once = anyio.run(authenticator.run_post_auth_hook, None, raw_model)
        twice = anyio.run(authenticator.run_post_auth_hook, None, once)

        assert raw_model["name"] == "octo"
        assert once is not raw_model
        assert once["auth_state"] is auth_state
        assert once["name"] == "github:octo"
        assert twice["name"] == "github:octo"


def test_github_raw_policy_checks_reject_blocked_and_unallowed_logins(monkeypatch: pytest.MonkeyPatch) -> None:
    with loaded_authenticators(monkeypatch) as modules:
        authenticator = modules.github.CustomGitHubOAuthenticator()
        authenticator.allowed_users = {"octo"}
        authenticator.blocked_users = {"blocked"}

        allowed = anyio.run(authenticator.authenticate, None, {"login": "octo"})
        blocked = anyio.run(authenticator.authenticate, None, {"login": "blocked"})
        unallowed = anyio.run(authenticator.authenticate, None, {"login": "other"})

        assert allowed["name"] == "octo"
        assert blocked is None
        assert unallowed is None
        assert authenticator.policy_names == ["octo", "blocked", "other"]


def test_github_refresh_returns_the_same_prefixed_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    with loaded_authenticators(monkeypatch) as modules:
        authenticator = modules.github.CustomGitHubOAuthenticator()
        modules.github.time.time = lambda: 1_000
        authenticator.refresh_token_response = {"access_token": "fresh", "expires_in": 3_600}
        authenticator.refreshed_auth_model = {
            "name": "octo",
            "auth_state": {"token_response": {"access_token": "fresh"}},
        }

        async def get_auth_state() -> dict[str, int | str]:
            return {"refresh_token": "refresh", "expires_at": 1_001}

        user = SimpleNamespace(
            name="github:octo",
            get_auth_state=get_auth_state,
        )

        result = anyio.run(authenticator.refresh_user, user)

        assert result["name"] == "github:octo"
        assert result["auth_state"]["expires_at"] == 4_600
        assert result["auth_state"]["token_response"] == {"access_token": "fresh"}


def test_github_allow_existing_users_uses_raw_logins_for_add_and_delete(monkeypatch: pytest.MonkeyPatch) -> None:
    with loaded_authenticators(monkeypatch) as modules:
        authenticator = modules.github.CustomGitHubOAuthenticator()
        user = SimpleNamespace(name="github:octo")

        authenticator.add_user(user)
        authenticator.delete_user(user)

        assert authenticator.child_add_names == ["octo"]
        assert authenticator.child_delete_names == ["octo"]
        assert authenticator.allowed_users == set()


def test_multi_delegates_prefixed_github_lifecycle_to_the_raw_login_child(monkeypatch: pytest.MonkeyPatch) -> None:
    with loaded_authenticators(monkeypatch) as modules:
        github = modules.github.CustomGitHubOAuthenticator()
        github.username_prefix = "github:"
        native = SimpleNamespace(username_prefix="")
        authenticator = modules.multi.CustomMultiAuthenticator()
        authenticator._authenticators = [github, native]
        github_user = SimpleNamespace(name="github:octo")
        native_user = SimpleNamespace(name="learner")

        authenticator.add_user(github_user)
        authenticator.add_user(native_user)
        authenticator.delete_user(github_user)

        assert github.child_add_names == ["octo"]
        assert github.child_delete_names == ["octo"]
        assert authenticator.outer_add_names == ["github:octo", "learner"]
        assert authenticator.outer_delete_names == ["github:octo"]


def test_github_callback_keeps_normal_oauth_flow_and_handles_app_setup_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with loaded_authenticators(monkeypatch) as modules:
        handler = modules.github._GitHubAppInstallCallbackHandler()
        handler.hub = SimpleNamespace(base_url="/hub/")
        handler.arguments = {"setup_action": "install"}
        anyio.run(handler.get)

        normal_handler = modules.github._GitHubAppInstallCallbackHandler()
        normal_handler.hub = SimpleNamespace(base_url="/hub/")
        normal_handler.arguments = {"state": "oauth-state"}
        anyio.run(normal_handler.get)

        assert handler.redirected_to == "/hub/spawn"
        assert not hasattr(handler, "parent_get_called")
        assert normal_handler.parent_get_called is True


def test_github_routes_are_scoped_once_directly_and_when_multi_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    with loaded_authenticators(monkeypatch) as modules:
        direct = modules.github.CustomGitHubOAuthenticator()

        class URLScopeMixin:
            url_scope = "/github"

            def login_url(self, base_url: str) -> str:
                return super().login_url(f"{base_url.rstrip('/')}{self.url_scope}")

            def get_handlers(self, app):
                return [(f"{self.url_scope}{path}", handler) for path, handler in super().get_handlers(app)]

        class WrappedGitHub(URLScopeMixin, modules.github.CustomGitHubOAuthenticator):
            pass

        wrapped = WrappedGitHub()

        assert direct.login_url("/hub/") == "/hub/github/oauth_login"
        assert [path for path, _handler in direct.get_handlers(None)] == [
            "/github/oauth_login",
            "/github/oauth_callback",
            "/github/logout",
        ]
        assert direct.get_callback_url() == "https://hub.example/hub/github/oauth_callback"
        handler = SimpleNamespace(
            request=SimpleNamespace(protocol="https", host="hub.example"),
            hub=SimpleNamespace(server=SimpleNamespace(base_url="/hub/")),
        )
        assert direct.get_callback_url(handler) == "https://hub.example/hub/github/oauth_callback"
        assert wrapped.login_url("/hub/") == "/hub/github/oauth_login"
        assert [path for path, _handler in wrapped.get_handlers(None)] == [
            "/github/oauth_login",
            "/github/oauth_callback",
            "/github/logout",
        ]
        assert wrapped.get_callback_url() == "https://hub.example/hub/github/oauth_callback"
        direct.oauth_callback_url = "https://configured.example/hub/github/oauth_callback"
        assert direct.get_callback_url() == "https://configured.example/hub/github/oauth_callback"
        direct.oauth_callback_url = "https://configured.example/hub/oauth_callback"
        with pytest.raises(ValueError, match="must end in /hub/github/oauth_callback"):
            direct.get_callback_url()
