# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.

"""Public CLI regression tests for the skill-version checker."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_skills_version.py"
CURSOR_GENERATOR = ROOT / ".github" / "scripts" / "generate_cursor_marketplace.py"


def write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_version_checker_fails_for_a_mismatched_manifest_version(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    checker = repo / "scripts" / CHECKER.name
    checker.parent.mkdir(parents=True)
    shutil.copy2(CHECKER, checker)

    (repo / "pyproject.toml").write_text('[project]\nname = "fixture"\nversion = "1.2.3"\n', encoding="utf-8")
    for relative_path, data in {
        ".claude-plugin/marketplace.json": {"metadata": {"version": "1.2.3"}},
        ".cursor-plugin/marketplace.json": {"metadata": {"version": "1.2.3"}},
        ".claude-plugin/plugin.json": {"version": "1.2.3"},
        ".cursor-plugin/plugin.json": {"version": "1.2.3"},
        "plugin-metadata.json": {"version": "0.0.0"},
    }.items():
        write_json(repo / relative_path, data)

    result = subprocess.run(
        [sys.executable, str(checker)],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "version check failed:" in result.stderr
    assert "plugin-metadata.json: version = 0.0.0, expected 1.2.3" in result.stderr


def test_marketplace_uses_root_description_and_metadata_version() -> None:
    marketplace = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    metadata = json.loads((ROOT / "plugin-metadata.json").read_text(encoding="utf-8"))

    assert marketplace["description"] == metadata["description"]
    assert "description" not in marketplace["metadata"]
    assert marketplace["metadata"]["version"] == metadata["version"]
    assert marketplace["plugins"][0]["description"]

    result = subprocess.run(
        [sys.executable, str(CURSOR_GENERATOR), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
