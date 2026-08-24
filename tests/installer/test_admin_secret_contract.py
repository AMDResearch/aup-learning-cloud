from __future__ import annotations

import json
import subprocess

import pytest

from auplc_installer.helm import ensure_local_admin_secret
from auplc_installer.util import InstallerError


def test_existing_secret_rejects_a_different_administrator_username(monkeypatch) -> None:
    def fake_run(command, *, check=True, input_text=None, capture_output=False):
        if command[2] == "secret":
            return subprocess.CompletedProcess(
                command,
                0,
                json.dumps(
                    {
                        "data": {
                            "admin-username": "b3RoZXI=",
                            "admin-password": "cGFzc3dvcmQ=",
                            "api-token": "dG9rZW4=",
                        }
                    }
                ),
            )
        return subprocess.CompletedProcess(command, 0, "")

    monkeypatch.setattr("auplc_installer.helm.run", fake_run)

    with pytest.raises(InstallerError, match="different administrator username"):
        ensure_local_admin_secret("operator")
