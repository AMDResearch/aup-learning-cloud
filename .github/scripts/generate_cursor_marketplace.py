#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Generate the Cursor plugin manifests from the canonical sources.

`auplc-skills` ships as a single bundled plugin: the whole repository is one
plugin whose `skills/` folder every supported agent discovers automatically
(this mirrors how `cloudflare/skills` is published). To avoid drift, the Cursor
manifests are generated from the Claude manifests rather than hand-maintained.

Sources of truth:
- `plugin-metadata.json` (repo root): shared identity and discovery metadata
  (name, description, version, author, homepage, repository,
  keywords). This is the vendor-neutral metadata file, reused by every
  marketplace/manifest target. It is NOT a plugin manifest.
- `.claude-plugin/marketplace.json`: the marketplace catalog with the single
  bundled plugin entry and its human-readable description (hand-maintained,
  since the catalog blurb intentionally differs from the SKILL.md routing
  descriptions).
- `.claude-plugin/plugin.json`: the bundled plugin manifest (hand-maintained).

Outputs:
- `.cursor-plugin/marketplace.json`: a mirror of the Claude marketplace so
  Cursor exposes exactly the same plugin as Claude.
- `.cursor-plugin/plugin.json`: the Cursor plugin manifest derived from the
  Claude plugin manifest + `plugin-metadata.json`.

Usage:
    uv run .github/scripts/generate_cursor_marketplace.py            # write
    uv run .github/scripts/generate_cursor_marketplace.py --check    # validate only

`--check` fails if any generated file is stale or if the Claude manifests'
top-level identity has drifted from `plugin-metadata.json`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PLUGIN_METADATA = ROOT / "plugin-metadata.json"
CLAUDE_MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
CLAUDE_PLUGIN = ROOT / ".claude-plugin" / "plugin.json"
CURSOR_MARKETPLACE = ROOT / ".cursor-plugin" / "marketplace.json"
CURSOR_PLUGIN = ROOT / ".cursor-plugin" / "plugin.json"


def load_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def check_identity_consistency(
    metadata: dict, claude: dict, claude_plugin: dict
) -> list[str]:
    """Return error strings if the Claude manifests' identity has drifted from
    the canonical `plugin-metadata.json`."""
    errors: list[str] = []

    name = metadata.get("name")
    description = metadata.get("description")
    version = metadata.get("version")

    if claude.get("name") != name:
        errors.append(
            f".claude-plugin/marketplace.json `name` ({claude.get('name')!r}) "
            f"must match plugin-metadata.json `name` ({name!r})."
        )
    if claude.get("description") != description:
        errors.append(
            ".claude-plugin/marketplace.json `description` must match "
            "plugin-metadata.json `description`."
        )
    claude_version = (claude.get("metadata") or {}).get("version")
    if claude_version != version:
        errors.append(
            f".claude-plugin/marketplace.json metadata.version "
            f"({claude_version!r}) must match plugin-metadata.json `version` "
            f"({version!r})."
        )

    # The single bundled plugin entry's name must match the plugin manifest.
    plugins = claude.get("plugins")
    if not isinstance(plugins, list) or len(plugins) != 1:
        errors.append(
            ".claude-plugin/marketplace.json must list exactly one bundled "
            "plugin (source `./`)."
        )
    else:
        entry_name = plugins[0].get("name")
        if entry_name != claude_plugin.get("name"):
            errors.append(
                f".claude-plugin/marketplace.json plugin `name` ({entry_name!r}) "
                f"must match .claude-plugin/plugin.json `name` "
                f"({claude_plugin.get('name')!r})."
            )

    if claude_plugin.get("version") != version:
        errors.append(
            f".claude-plugin/plugin.json `version` "
            f"({claude_plugin.get('version')!r}) must match plugin-metadata.json "
            f"`version` ({version!r})."
        )
    return errors


def build_cursor_marketplace(metadata: dict, claude: dict) -> dict:
    author = metadata.get("author") or {}
    owner_name = author.get("name") if isinstance(author, dict) else None

    return {
        "name": metadata["name"],
        "owner": {"name": owner_name} if owner_name else {},
        "description": metadata["description"],
        "metadata": {
            "description": metadata["description"],
            "version": metadata["version"],
        },
        "plugins": claude.get("plugins", []),
    }


def build_cursor_plugin(metadata: dict, claude_plugin: dict) -> dict:
    return {
        "name": claude_plugin["name"],
        "version": metadata["version"],
        "description": claude_plugin.get("description", metadata["description"]),
        "author": metadata.get("author") or {},
        "keywords": metadata.get("keywords", []),
    }


def render_json(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def write_or_check(path: Path, content: str, check: bool) -> bool:
    """Return True when the file is already up to date."""
    current = path.read_text(encoding="utf-8") if path.exists() else None
    if current == content:
        return True
    if check:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the .cursor-plugin/ manifests from the canonical "
        "Claude manifests and plugin-metadata.json."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate the generated manifests are up to date without writing.",
    )
    args = parser.parse_args(argv)

    metadata = load_json(PLUGIN_METADATA)
    claude = load_json(CLAUDE_MARKETPLACE)
    claude_plugin = load_json(CLAUDE_PLUGIN)

    identity_errors = check_identity_consistency(metadata, claude, claude_plugin)
    if identity_errors:
        print("Plugin manifest identity is inconsistent:", file=sys.stderr)
        for err in identity_errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    targets = {
        CURSOR_MARKETPLACE: render_json(build_cursor_marketplace(metadata, claude)),
        CURSOR_PLUGIN: render_json(build_cursor_plugin(metadata, claude_plugin)),
    }

    stale = [
        path
        for path, content in targets.items()
        if not write_or_check(path, content, check=args.check)
    ]

    if args.check:
        if stale:
            for path in stale:
                print(f"{path.relative_to(ROOT)} is out of date.", file=sys.stderr)
            print(
                "Run: uv run .github/scripts/generate_cursor_marketplace.py",
                file=sys.stderr,
            )
            return 1
        print("Cursor plugin manifests are up to date.")
        return 0

    for path in targets:
        print(f"Wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
