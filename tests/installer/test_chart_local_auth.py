import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_local_chart_render_uses_existing_secret_only_for_hub_bootstrap() -> None:
    result = subprocess.run(
        [
            "helm",
            "template",
            "jupyterhub",
            "runtime/chart",
            "--set",
            "custom.authMode=local",
            "--set",
            "custom.adminUser.enabled=true",
            "--set",
            "custom.adminUser.username=operator",
            "--set",
            "custom.adminUser.existingSecret=jupyterhub-admin-credentials",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "authMode: local" in result.stdout
    assert "name: JUPYTERHUB_ADMIN_USERNAME" in result.stdout
    assert 'value: "operator"' in result.stdout
    assert "name: JUPYTERHUB_ADMIN_PASSWORD" in result.stdout
    assert "key: admin-password" in result.stdout
    assert "name: JUPYTERHUB_API_TOKEN" in result.stdout
    assert "key: api-token" in result.stdout
    assert "optional: true" in result.stdout
    assert "kind: Secret\nmetadata:\n  name: jupyterhub-admin-credentials" not in result.stdout


def test_local_chart_schema_rejects_uppercase_admin_username() -> None:
    result = subprocess.run(
        [
            "helm",
            "template",
            "jupyterhub",
            "runtime/chart",
            "--set",
            "custom.authMode=local",
            "--set",
            "custom.adminUser.enabled=true",
            "--set",
            "custom.adminUser.username=Operator",
            "--set",
            "custom.adminUser.existingSecret=jupyterhub-admin-credentials",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "does not match pattern" in result.stderr


def test_local_chart_render_allows_chart_managed_credentials() -> None:
    result = subprocess.run(
        [
            "helm",
            "template",
            "jupyterhub",
            "runtime/chart",
            "--set",
            "custom.authMode=local",
            "--set",
            "custom.adminUser.enabled=true",
            "--set",
            "custom.adminUser.username=operator",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "kind: Secret\nmetadata:\n  name: jupyterhub-admin-credentials" in result.stdout
    assert 'name: JUPYTERHUB_ADMIN_USERNAME\n              value: "operator"' in result.stdout


def test_chart_schema_rejects_existing_secret_outside_local_mode() -> None:
    result = subprocess.run(
        [
            "helm",
            "template",
            "jupyterhub",
            "runtime/chart",
            "--set",
            "custom.authMode=auto-login",
            "--set",
            "custom.adminUser.enabled=true",
            "--set",
            "custom.adminUser.username=operator",
            "--set",
            "custom.adminUser.existingSecret=legacy-admin-credentials",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "authMode" in result.stderr
