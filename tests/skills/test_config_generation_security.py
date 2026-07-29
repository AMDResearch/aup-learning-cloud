# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GEN_CONFIGS = ROOT / "skills" / "deploy-aup-learning-cloud" / "scripts" / "gen_configs.py"


def safe_spec() -> dict[str, object]:
    return {
        "topology": "ssh-preinstalled",
        "k3s_version": "v1.32.3+k3s1",
        "server": {"name": "server-1", "ip": "192.168.1.10"},
        "agents": [{"name": "agent-1", "ip": "192.168.1.11"}],
        "images": {"cpu": "registry.example/auplc:latest"},
    }


def load_config_generation_module():
    sys.path.insert(0, str(GEN_CONFIGS.parent))
    try:
        import config_generation

        return config_generation
    finally:
        sys.path.pop(0)


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("server", "name"), "server\n  vars: {injected: true}", "spec.server.name"),
        (("server", "ip"), "192.168.1.10\n  injected: true", "spec.server.ip"),
        (("k3s_version",), "v1.32.3+k3s1\n  injected: true", "spec.k3s_version"),
        (("agents",), [{"name": "server-1", "ip": "192.168.1.11"}], "unique"),
        (("agents",), [{"name": "agent-1", "ip": "not-an-ip"}], "spec.agents[0].ip"),
        (("images",), {"cpu\n  injected": "registry.example/auplc:latest"}, "spec.images key"),
    ],
)
def test_generator_rejects_unsafe_public_spec_scalars_before_discovery(
    path: tuple[str, ...], value: object, message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    module = load_config_generation_module()
    spec = safe_spec()
    if len(path) == 1:
        spec[path[0]] = value
    else:
        target = spec[path[0]]
        assert isinstance(target, dict)
        target[path[1]] = value
    with pytest.raises(SystemExit) as error:
        module.validate_spec(spec)

    assert error.value.code == 1
    assert message in capsys.readouterr().err


def test_generator_rejects_an_invalid_k3s_version_before_discovery(capsys: pytest.CaptureFixture[str]) -> None:
    module = load_config_generation_module()
    spec = safe_spec()
    spec["k3s_version"] = "v1.32.3+k3s1 # comments are not accepted"

    with pytest.raises(SystemExit) as error:
        module.validate_spec(spec)

    assert error.value.code == 1
    assert "spec.k3s_version" in capsys.readouterr().err


def test_generator_applies_the_normal_unknown_field_policy_to_draft_gpu_fields() -> None:
    module = load_config_generation_module()
    spec = safe_spec()
    spec["render_gid"] = 993
    spec["gpu_access"] = {"hosts": []}

    assert module.validate_spec(spec) == "ssh-preinstalled"


@pytest.mark.parametrize(
    "raw",
    [
        '{"topology":"ssh-preinstalled","topology":"pxe-diskless"}',
    ],
)
def test_generator_rejects_duplicate_public_policy_keys_before_discovery(tmp_path: Path, raw: str) -> None:
    spec = tmp_path / "spec.json"
    spec.write_text(raw, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(GEN_CONFIGS), "--spec", str(spec), "--out-dir", str(tmp_path / "generated")],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 1
    assert "duplicate JSON key" in result.stderr
