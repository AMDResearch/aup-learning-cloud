import pytest
from test_auth_provider_setup import _loaded_setup


def test_native_setup_does_not_require_optional_admin_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    with _loaded_setup(monkeypatch, (False, False, True, False)) as state:
        monkeypatch.delenv("JUPYTERHUB_ADMIN_PASSWORD", raising=False)
        monkeypatch.delenv("JUPYTERHUB_ADMIN_USERNAME", raising=False)

        state.setup.setup_hub(state.c)

        assert not hasattr(state.c.Authenticator, "admin_users")


def test_enabled_bootstrap_failure_aborts_before_administrator_registration(monkeypatch: pytest.MonkeyPatch) -> None:
    with _loaded_setup(monkeypatch, (False, False, True, False)) as state:

        def fail_bootstrap(_username: str, _password: str) -> None:
            raise OSError("database unavailable")

        state.setup._bootstrap_admin_password = fail_bootstrap

        with pytest.raises(RuntimeError, match="Failed to bootstrap administrator credentials") as error:
            state.setup.setup_hub(state.c)

        assert isinstance(error.value.__cause__, OSError)
        assert not hasattr(state.c.Authenticator, "admin_users")


def test_github_only_rejects_stale_password_before_bootstrap_or_token_configuration(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    with _loaded_setup(monkeypatch, (False, False, False, True)) as state:
        calls: list[tuple[str, str]] = []
        monkeypatch.setenv("JUPYTERHUB_ADMIN_PASSWORD", "Password1!")
        monkeypatch.setenv("JUPYTERHUB_ADMIN_USERNAME", "operator")
        monkeypatch.setenv("JUPYTERHUB_API_TOKEN", "token-value")
        state.setup._bootstrap_admin_password = lambda username, password: calls.append((username, password))

        with pytest.raises(RuntimeError, match="requires native authentication"):
            state.setup.setup_hub(state.c)

        assert calls == []
        assert not hasattr(state.c.JupyterHub, "api_tokens")
        assert not hasattr(state.c.Authenticator, "admin_users")
        output = capsys.readouterr().out
        assert "API token loaded" not in output
        assert "Admin user configured" not in output


def test_token_only_remains_available_without_native_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    with _loaded_setup(monkeypatch, (False, False, False, True)) as state:
        monkeypatch.setenv("JUPYTERHUB_API_TOKEN", "token-value")

        state.setup.setup_hub(state.c)

        assert state.c.JupyterHub.api_tokens == {"token-value": "admin"}
        assert not hasattr(state.c.Authenticator, "admin_users")


def test_bootstrap_failure_preserves_existing_token_and_admin_state(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    with _loaded_setup(monkeypatch, (False, False, True, False)) as state:
        state.c.JupyterHub.api_tokens = {"existing-token": "existing-admin"}
        state.c.Authenticator.admin_users = {"existing-admin"}
        monkeypatch.setenv("JUPYTERHUB_API_TOKEN", "token-value")

        def fail_bootstrap(_username: str, _password: str) -> None:
            raise OSError("database unavailable")

        state.setup._bootstrap_admin_password = fail_bootstrap

        with pytest.raises(RuntimeError, match="Failed to bootstrap administrator credentials"):
            state.setup.setup_hub(state.c)

        assert state.c.JupyterHub.api_tokens == {"existing-token": "existing-admin"}
        assert state.c.Authenticator.admin_users == {"existing-admin"}
        output = capsys.readouterr().out
        assert "API token loaded" not in output
        assert "Admin user configured" not in output


def test_token_failure_follows_successful_bootstrap_without_final_admin_state(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    with _loaded_setup(monkeypatch, (False, False, True, False)) as state:
        calls: list[tuple[str, str]] = []
        monkeypatch.setenv("JUPYTERHUB_API_TOKEN", "token-value")
        state.setup._bootstrap_admin_password = lambda username, password: calls.append((username, password))

        def fail_token(_config, _token: str, _username: str) -> None:
            raise OSError("token storage unavailable")

        state.setup._configure_api_token = fail_token

        with pytest.raises(OSError, match="token storage unavailable"):
            state.setup.setup_hub(state.c)

        assert calls == [("admin", "Password1!")]
        assert not hasattr(state.c.Authenticator, "admin_users")
        output = capsys.readouterr().out
        assert "API token loaded" not in output
        assert "Admin user configured" not in output
