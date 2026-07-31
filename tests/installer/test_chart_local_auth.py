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
    assert "key: admin-username" in result.stdout
    assert "name: JUPYTERHUB_ADMIN_PASSWORD" in result.stdout
    assert "key: admin-password" in result.stdout
    assert "kind: Secret\nmetadata:\n  name: jupyterhub-admin-credentials" not in result.stdout
