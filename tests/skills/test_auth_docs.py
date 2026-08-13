# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.

"""Structural checks for public authentication documentation."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_AUTH_DOCS = (
    ROOT / "README.md",
    ROOT / "README-SKILL.md",
    ROOT / "runtime/chart/templates/NOTES.txt",
    ROOT / "skills/configure-aup-learning-cloud-auth/SKILL.md",
    ROOT / "skills/configure-aup-learning-cloud-auth/reference.md",
    ROOT / "skills/install-aup-learning-cloud-single-node/SKILL.md",
    ROOT / "skills/install-aup-learning-cloud-single-node/reference.md",
    ROOT / "skills/manage-aup-learning-cloud-users/SKILL.md",
    ROOT / "skills/manage-aup-learning-cloud-users/reference.md",
    ROOT / "skills/deploy-aup-learning-cloud/SKILL.md",
    ROOT / "skills/deploy-aup-learning-cloud/reference.md",
    ROOT / "skills/troubleshoot-aup-learning-cloud/SKILL.md",
    ROOT / "skills/troubleshoot-aup-learning-cloud/reference.md",
)
AUTH_EXAMPLE_MARKER = "auplc-auth-examples: canonical"
DEPLOYMENT_EXAMPLE_MARKER = "auplc-deployment-example: canonical"
RUNTIME_QUOTA_MARKER = "auplc-runtime-quota-matrix: canonical"
VALID_PROVIDER_SETS = {
    frozenset({"autoLogin"}),
    frozenset({"dummy"}),
    frozenset({"native"}),
    frozenset({"github"}),
    frozenset({"native", "github"}),
}


def marked_yaml_documents(text: str, marker: str) -> list[dict]:
    pattern = re.compile(
        rf"<!--\s*{re.escape(marker)}\s*-->\s*```yaml\s*\n(.*?)```",
        re.DOTALL,
    )
    return [document for block in pattern.findall(text) for document in yaml.safe_load_all(block)]


def legacy_auth_mode_outside_migration(text: str) -> list[int]:
    heading = ""
    invalid_lines: list[int] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if match := re.match(r"^#{1,6}\s+(.+)$", line):
            heading = match.group(1).casefold()
        if "authMode" in line and not ({"migration", "deprecation"} & set(heading.split())):
            invalid_lines.append(line_number)
    return invalid_lines


def render_example(tmp_path: Path, index: int, document: dict) -> subprocess.CompletedProcess[str]:
    overlay = tmp_path / f"auth-doc-example-{index}.yaml"
    overlay.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return subprocess.run(
        [
            "helm",
            "template",
            "jupyterhub",
            "runtime/chart",
            "-f",
            "runtime/values.yaml",
            "-f",
            str(overlay),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_canonical_provider_examples_match_truth_table_and_chart_schema(tmp_path: Path) -> None:
    reference = (ROOT / "skills/configure-aup-learning-cloud-auth/reference.md").read_text(encoding="utf-8")
    examples = marked_yaml_documents(reference, AUTH_EXAMPLE_MARKER)

    provider_sets = {
        frozenset(key for key, enabled in example["custom"]["auth"].items() if enabled) for example in examples
    }
    assert provider_sets == VALID_PROVIDER_SETS

    for index, example in enumerate(examples):
        result = render_example(tmp_path, index, example)
        assert result.returncode == 0, result.stderr


def test_canonical_deployment_examples_set_provider_topology_and_quota() -> None:
    examples = [
        example
        for path in PUBLIC_AUTH_DOCS
        for example in marked_yaml_documents(path.read_text(encoding="utf-8"), DEPLOYMENT_EXAMPLE_MARKER)
    ]

    assert examples
    for example in examples:
        custom = example["custom"]
        assert custom["auth"] == {"native": True, "github": True}
        assert custom["runtimeLimitEnabled"] is True
        assert custom["quota"]["enabled"] is True
        assert "authMode" not in custom


def test_runtime_quota_matrix_defines_controls_and_runtime_first_pairs() -> None:
    reference = (ROOT / "skills/configure-aup-learning-cloud-auth/reference.md").read_text(encoding="utf-8")
    matrices = marked_yaml_documents(reference, RUNTIME_QUOTA_MARKER)

    assert len(matrices) == 1
    matrix = matrices[0]
    assert matrix["controls"] == {
        "runtimeLimitEnabled": {
            True: "enforce-session-timer",
            False: "disable-session-timer",
        },
        "quota.enabled": {
            True: "enforce-credits",
            False: "disable-credit-enforcement",
        },
    }
    assert [
        (entry["runtimeLimitEnabled"], entry["quotaEnabled"], entry["valid"]) for entry in matrix["runtimeQuotaPairs"]
    ] == [
        (True, True, True),
        (True, False, True),
        (False, False, True),
        (False, True, False),
    ]
    assert matrix["runtimeQuotaPairs"][0]["examples"] == ["online"]
    assert matrix["runtimeQuotaPairs"][2]["examples"] == ["installer-personal", "installer-local"]


def test_legacy_auth_mode_is_confined_to_migration_sections() -> None:
    invalid_occurrences = {
        str(path.relative_to(ROOT)): legacy_auth_mode_outside_migration(path.read_text(encoding="utf-8"))
        for path in PUBLIC_AUTH_DOCS
        if legacy_auth_mode_outside_migration(path.read_text(encoding="utf-8"))
    }

    assert invalid_occurrences == {}


def test_legacy_auth_mode_classifier_rejects_canonical_and_accepts_migration() -> None:
    canonical = """## Canonical configuration
```yaml
custom:
  authMode: multi
```
"""
    migration = """## One-release migration
```yaml
custom:
  authMode: multi
```
"""

    assert legacy_auth_mode_outside_migration(canonical) == [4]
    assert legacy_auth_mode_outside_migration(migration) == []


def test_removed_resource_visibility_configuration_is_absent_from_public_auth_docs() -> None:
    removed_field = "access" + "Policy"
    occurrences = [
        str(path.relative_to(ROOT)) for path in PUBLIC_AUTH_DOCS if removed_field in path.read_text(encoding="utf-8")
    ]

    assert occurrences == []
