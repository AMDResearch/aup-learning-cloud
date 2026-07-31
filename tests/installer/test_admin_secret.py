import json
import subprocess
from pathlib import Path

import pytest

from auplc_installer.helm import RuntimePaths, deploy_runtime, ensure_local_admin_secret
from auplc_installer.util import InstallerError


def test_creates_local_admin_secret_through_stdin_without_leaking_credentials(monkeypatch, capsys) -> None:
    calls: list[tuple[list[str], str | None]] = []

    def fake_run(command, *, check=True, input_text=None):
        calls.append((command, input_text))
        return subprocess.CompletedProcess(command, 1 if len(calls) in (1, 3) else 0, "")

    monkeypatch.setattr("auplc_installer.helm.run", fake_run)
    monkeypatch.setattr("auplc_installer.helm.secrets.token_urlsafe", lambda _length: "generated-password")

    password = ensure_local_admin_secret("operator")

    assert password == "generated-password"
    assert calls[0] == (["kubectl", "get", "namespace", "jupyterhub"], None)
    assert calls[1] == (["kubectl", "create", "namespace", "jupyterhub"], None)
    assert calls[2] == (
        ["kubectl", "get", "secret", "jupyterhub-admin-credentials", "--namespace", "jupyterhub"],
        None,
    )
    assert "generated-password" not in " ".join(calls[3][0])
    payload = json.loads(calls[3][1] or "")
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
    assert calls == [
        ["kubectl", "get", "namespace", "jupyterhub"],
        ["kubectl", "get", "secret", "jupyterhub-admin-credentials", "--namespace", "jupyterhub"],
    ]


def test_deploy_orders_namespace_secret_and_helm_without_printing_new_password(monkeypatch, capsys) -> None:
    calls: list[tuple[str, list[str], str | None]] = []

    def fake_run(command, *, check=True, input_text=None):
        calls.append(("run", command, input_text))
        return subprocess.CompletedProcess(command, 1 if len(calls) in (1, 3) else 0, "")

    def failing_stream(command, **_kwargs):
        calls.append(("stream", command, None))
        raise InstallerError("helm failed")

    monkeypatch.setattr("auplc_installer.helm.run", fake_run)
    monkeypatch.setattr("auplc_installer.helm.run_streaming", failing_stream)
    monkeypatch.setattr("auplc_installer.helm.secrets.token_urlsafe", lambda _length: "generated-password")

    with pytest.raises(InstallerError, match="helm failed"):
        deploy_runtime(
            RuntimePaths(Path("chart"), Path("values.yaml"), Path("values.local.yaml")),
            access_mode="local",
            admin_username="operator",
        )

    assert [command for _, command, _ in calls] == [
        ["kubectl", "get", "namespace", "jupyterhub"],
        ["kubectl", "create", "namespace", "jupyterhub"],
        ["kubectl", "get", "secret", "jupyterhub-admin-credentials", "--namespace", "jupyterhub"],
        ["kubectl", "create", "--namespace", "jupyterhub", "--filename=-"],
        [
            "helm",
            "install",
            "jupyterhub",
            "chart",
            "--namespace",
            "jupyterhub",
            "--create-namespace",
            "-f",
            "values.yaml",
            "-f",
            "values.local.yaml",
        ],
    ]
    assert "generated-password" not in capsys.readouterr().out
