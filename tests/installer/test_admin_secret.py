import json
import subprocess

from auplc_installer.helm import ensure_local_admin_secret


def test_creates_local_admin_secret_through_stdin_without_leaking_credentials(monkeypatch, capsys) -> None:
    calls: list[tuple[list[str], str | None]] = []

    def fake_run(command, *, check=True, input_text=None):
        calls.append((command, input_text))
        return subprocess.CompletedProcess(command, 1 if len(calls) == 1 else 0, "")

    monkeypatch.setattr("auplc_installer.helm.run", fake_run)
    monkeypatch.setattr("auplc_installer.helm.secrets.token_urlsafe", lambda _length: "generated-password")

    password = ensure_local_admin_secret("operator")

    assert password == "generated-password"
    assert calls[0] == (
        ["kubectl", "get", "secret", "jupyterhub-admin-credentials", "--namespace", "jupyterhub"],
        None,
    )
    assert "generated-password" not in " ".join(calls[1][0])
    payload = json.loads(calls[1][1] or "")
    assert payload["metadata"]["name"] == "jupyterhub-admin-credentials"
    assert payload["stringData"] == {"admin-username": "operator", "admin-password": "generated-password"}
    assert "generated-password" not in capsys.readouterr().out


def test_reuses_existing_local_admin_secret(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(command, *, check=True, input_text=None):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "")

    monkeypatch.setattr("auplc_installer.helm.run", fake_run)

    assert ensure_local_admin_secret("operator") is None
    assert calls == [["kubectl", "get", "secret", "jupyterhub-admin-credentials", "--namespace", "jupyterhub"]]
