"""Static GPU information obtained from the ``amd-smi`` CLI.

This wraps ``amd-smi list --json`` and ``amd-smi static --json`` and returns the
parsed structures for display. The CLI is used (rather than the Python bindings)
because it resolves many fields that the Python ``amdsmi_get_gpu_*_info`` calls
report as NOT_SUPPORTED on some ASICs (notably APUs).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any, List, Optional, Tuple


def amd_smi_executable() -> Optional[str]:
    found = shutil.which("amd-smi")
    if found:
        return found
    for candidate in ("/opt/rocm/bin/amd-smi", "/usr/bin/amd-smi"):
        if os.path.exists(candidate):
            return candidate
    return None


def _run_json(exe: str, args: List[str]) -> Tuple[Any, Optional[str]]:
    """Run an amd-smi subcommand and parse its JSON stdout.

    amd-smi can exit with a non-zero status while still emitting valid JSON, so
    we parse stdout whenever it looks like JSON instead of trusting the return
    code.
    """
    try:
        proc = subprocess.run(
            [exe, *args],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"

    out = (proc.stdout or "").strip()
    if not out:
        return None, (proc.stderr or "").strip() or f"amd-smi exited {proc.returncode}"
    try:
        return json.loads(out), None
    except json.JSONDecodeError as exc:
        return None, f"Failed to parse amd-smi JSON: {exc}"


def static_info() -> dict:
    """Return parsed ``amd-smi list`` and ``amd-smi static`` data."""
    exe = amd_smi_executable()
    if exe is None:
        return {
            "available": False,
            "error": "amd-smi was not found on PATH or in /opt/rocm/bin.",
            "list": [],
            "static": [],
        }

    listing, list_err = _run_json(exe, ["list", "--json"])
    static, static_err = _run_json(exe, ["static", "--json"])

    static_list: List[Any] = []
    if isinstance(static, dict):
        static_list = static.get("gpu_data") or static.get("gpus") or [static]
    elif isinstance(static, list):
        static_list = static

    list_data: List[Any] = listing if isinstance(listing, list) else []

    error = None
    if not static_list and not list_data:
        error = static_err or list_err or "amd-smi returned no data."

    return {
        "available": True,
        "error": error,
        "executable": exe,
        "list": list_data,
        "static": static_list,
    }
