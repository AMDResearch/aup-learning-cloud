#!/usr/bin/env bash
# Regenerate every committed artifact derived from skills/ and the
# canonical marketplace + metadata sources.
#
# Usage:
#   ./.github/scripts/publish.sh            Regenerate all derived artifacts.
#   ./.github/scripts/publish.sh --check    Verify derived artifacts are up to date.
#   ./.github/scripts/publish.sh -h|--help  Print this help.
#
# Currently regenerates:
#   - .cursor-plugin/marketplace.json   (mirror of .claude-plugin/marketplace.json)
#   - .cursor-plugin/plugin.json        (derived from .claude-plugin/plugin.json
#                                        + plugin-metadata.json)
#
# The `.claude-plugin/` manifests are hand-maintained because the human-facing
# plugin description intentionally differs from the SKILL.md routing
# descriptions; ./.github/scripts/check.sh enforces that they stay consistent
# with plugin-metadata.json.
#
# Requires `uv` (https://github.com/astral-sh/uv).

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

usage() {
  sed -n 's/^# \{0,1\}//p' "${BASH_SOURCE[0]}" | sed -n '/^Usage:/,/^Requires/p'
}

case "${1:-}" in
  "")
    uv run .github/scripts/generate_cursor_marketplace.py
    echo "Publish artifacts generated successfully."
    ;;
  --check)
    uv run .github/scripts/generate_cursor_marketplace.py --check
    ;;
  -h|--help)
    usage
    ;;
  *)
    echo "Unknown option: $1" >&2
    echo "Run with --help for usage." >&2
    exit 2
    ;;
esac
