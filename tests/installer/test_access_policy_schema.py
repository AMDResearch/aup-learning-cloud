import json
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts.generate_values_schema import remove_descriptions

ROOT = Path(__file__).resolve().parents[2]
CHART = "runtime/chart"


def render(*settings: str, string_settings: tuple[str, ...] = ()) -> subprocess.CompletedProcess[str]:
    command = ["helm", "template", "jupyterhub", CHART]
    for setting in settings:
        command.extend(("--set", setting))
    for setting in string_settings:
        command.extend(("--set-string", setting))
    return subprocess.run(command, cwd=ROOT, check=False, capture_output=True, text=True)


@pytest.mark.parametrize("access_policy", ("all", "group-mapped"))
def test_chart_accepts_each_access_policy_literal(access_policy: str) -> None:
    result = render(f"custom.resources.accessPolicy={access_policy}")

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("setting", "string_settings"),
    [
        ("custom.resources.accessPolicy=unknown", ()),
        ("custom.resources.accessPolicy=true", ()),
        ("custom.resources.accessPolicy=1", ()),
        ("", ("custom.resources.accessPolicy=unknown",)),
    ],
)
def test_chart_rejects_invalid_access_policy(setting: str, string_settings: tuple[str, ...]) -> None:
    settings = (setting,) if setting else ()
    result = render(*settings, string_settings=string_settings)

    assert result.returncode != 0
    assert "values don't meet the specifications" in result.stderr


def test_chart_yaml_and_json_schema_remain_exactly_in_sync() -> None:
    yaml_schema = yaml.safe_load((ROOT / "runtime/chart/values.schema.yaml").read_text())
    json_schema = json.loads((ROOT / "runtime/chart/values.schema.json").read_text())

    assert json_schema == remove_descriptions(yaml_schema)
