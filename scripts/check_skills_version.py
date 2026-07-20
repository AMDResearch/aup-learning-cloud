#!/usr/bin/env python3
# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
"""
Check that the bundled auplc-skills version fields stay in sync.

The project version in pyproject.toml is the single source of truth (strategy
A + C: skills share the main project version and are pinned at install time via
git tags/refs). This script is READ-ONLY: it only compares the version strings
declared across the plugin manifests against pyproject.toml and reports any
mismatch. It never edits skills or any other file.

Checked version fields:
  - pyproject.toml                       -> [project].version (source of truth)
  - .claude-plugin/marketplace.json      -> metadata.version
  - .cursor-plugin/marketplace.json      -> metadata.version
  - .claude-plugin/plugin.json           -> version
  - .cursor-plugin/plugin.json           -> version
  - plugin-metadata.json                 -> version

Usage:
    python scripts/check_skills_version.py

Exits non-zero if any version field does not match pyproject.toml.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def read_pyproject_version(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    # Match the version key inside the [project] table without adding a TOML dep.
    match = re.search(r'(?m)^\s*version\s*=\s*"([^"]+)"', text)
    if not match:
        raise ValueError(f"could not find a version in {path}")
    return match.group(1)


def read_json_field(path: Path, *keys: str) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    node = data
    for key in keys:
        node = node[key]
    return node


def main() -> int:
    source_version = read_pyproject_version(REPO_ROOT / "pyproject.toml")

    # (relative path, (nested json keys ...))
    targets = [
        (".claude-plugin/marketplace.json", ("metadata", "version")),
        (".cursor-plugin/marketplace.json", ("metadata", "version")),
        (".claude-plugin/plugin.json", ("version",)),
        (".cursor-plugin/plugin.json", ("version",)),
        ("plugin-metadata.json", ("version",)),
    ]

    mismatches: list[str] = []
    print(f"source of truth: pyproject.toml version = {source_version}")
    for rel_path, keys in targets:
        path = REPO_ROOT / rel_path
        if not path.exists():
            mismatches.append(f"missing file: {rel_path}")
            continue
        try:
            value = read_json_field(path, *keys)
        except (KeyError, TypeError):
            mismatches.append(f"missing field {'.'.join(keys)} in {rel_path}")
            continue
        status = "ok" if value == source_version else "MISMATCH"
        print(f"  [{status}] {rel_path} ({'.'.join(keys)}) = {value}")
        if value != source_version:
            mismatches.append(f"{rel_path}: {'.'.join(keys)} = {value}, expected {source_version}")

    if mismatches:
        print("\nversion check failed:", file=sys.stderr)
        for item in mismatches:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("\nall skill version fields match pyproject.toml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
