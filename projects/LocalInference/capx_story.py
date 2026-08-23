#!/usr/bin/env python3
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
"""Run or replay the CaP-X half of the script-first workshop story."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DEFAULT_MODEL = "Gemma-4-E4B-it-GGUF"
DEFAULT_SERVER_URL = "http://127.0.0.1:13305/api/v1/chat/completions"
DEFAULT_CAPX_ROOT = Path(os.environ.get("CAPX_ROOT", "/ryzers/cap-x"))
DEFAULT_CAPX_PYTHON = Path(os.environ.get("CAPX_PYTHON", "/opt/capx-venv/bin/python"))
FIXTURE_METADATA = HERE / "fixtures" / "capx_gemma_e4b_sam3_cube_stack_trial_01.json"
SCENARIOS = {
    "cube_lift": (
        "env_configs/cube_lifting/"
        "franka_robosuite_cube_lifting.yaml"
    ),
    "cube_restack": (
        "env_configs/cube_restack/"
        "franka_robosuite_cube_restack.yaml"
    ),
    "cube_stack": "env_configs/cube_stack/franka_robosuite_cube_stack.yaml",
    "spill_wipe": "env_configs/spill_wipe/franka_robosuite_spill_wipe.yaml",
}
SCENARIO_PRIMITIVES = {
    "cube_lift": {
        "get_object_pose",
        "sample_grasp_pose",
        "goto_pose",
        "open_gripper",
        "close_gripper",
        "home_pose",
    },
    "cube_restack": {
        "get_object_pose",
        "sample_grasp_pose",
        "goto_pose",
        "open_gripper",
        "close_gripper",
        "home_pose",
    },
    "cube_stack": {
        "get_object_pose",
        "sample_grasp_pose",
        "goto_pose",
        "open_gripper",
        "close_gripper",
        "home_pose",
    },
    "spill_wipe": {"get_object_pose", "goto_pose"},
}
TRIAL_DIR = re.compile(
    r"trial_(?P<trial>\d+)_sandboxrc_(?P<rc>\d+)_reward_"
    r"(?P<reward>[\d.]+)_taskcompleted_(?P<completed>[01])$"
)


def _read(path: Path | None) -> str:
    return path.read_text(encoding="utf-8") if path and path.is_file() else ""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bool(text: str | None) -> bool | None:
    if text is None:
        return None
    if text.strip().lower() in {"true", "1"}:
        return True
    if text.strip().lower() in {"false", "0"}:
        return False
    return None


def _summary_fields(text: str) -> dict[str, str]:
    """Parse CaP-X's human-readable per-trial environment response."""
    names = (
        "Sandbox failed",
        "Stdout",
        "Stderr",
        "Reward",
        "Task Completed",
        "Terminated",
        "Num Regenerations",
        "Num Finishes",
        "Num Code Blocks",
    )
    marker = re.compile(r"^\s{2}(?P<name>" + "|".join(re.escape(name) for name in names) + r"):\s?(?P<value>.*)$")
    fields: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        match = marker.match(line)
        if match:
            current = match.group("name")
            fields[current] = [match.group("value")]
        elif current is not None and set(line.strip()) != {"-"}:
            fields[current].append(line)
    return {name: "\n".join(lines).rstrip() for name, lines in fields.items()}


def _query_seconds(text: str) -> float | None:
    for pattern in (
        r"Time taken to query(?: model)?:\s*([\d.]+)",
        r"model query took\s*([\d.]+)",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def _called_primitives(code: str, scenario: str) -> list[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []
    called = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    return sorted(called & SCENARIO_PRIMITIVES[scenario])


def _primitive_sources(code: str, scenario: str, capx_root: Path) -> list[dict[str, str]]:
    """Find actual called primitive definitions without importing CaP-X."""
    wanted = _called_primitives(code, scenario)
    integrations = capx_root / "capx" / "integrations"
    if not wanted or not integrations.is_dir():
        return []

    candidates: dict[str, list[tuple[int, Path, str]]] = {name: [] for name in wanted}
    for path in integrations.rglob("*.py"):
        source = _read(path)
        try:
            tree = ast.parse(source)
        except (SyntaxError, UnicodeError):
            continue
        lines = source.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name not in candidates or node.end_lineno is None:
                continue
            snippet = "\n".join(lines[node.lineno - 1 : node.end_lineno])
            implementation = "spill_wipe.py" if scenario == "spill_wipe" else "control.py"
            rank = 0 if path.name == implementation else 1
            candidates[node.name].append((rank, path, snippet))

    found = []
    for name in wanted:
        choices = sorted(candidates[name], key=lambda item: (item[0], str(item[1])))
        if choices:
            _, path, source = choices[0]
            found.append(
                {
                    "name": name,
                    "path": str(path.resolve()),
                    "source": source,
                }
            )
    return found


def _artifact_paths(trial_dir: Path) -> dict[str, Any]:
    prompt = trial_dir / "prompts_and_responses" / "initial_prompt.txt"
    paths = {
        "trial_dir": str(trial_dir.resolve()),
        "generated_code": str((trial_dir / "code.py").resolve()),
        "raw_response": str((trial_dir / "raw_response.sh").resolve()),
        "prompt": str(prompt.resolve()),
        "summary": str((trial_dir / "summary.txt").resolve()),
        "all_responses": str((trial_dir / "all_responses.json").resolve()),
        "videos": [str(path.resolve()) for path in sorted(trial_dir.glob("*.mp4"))],
    }
    return paths


def _trial_manifest(
    trial_dir: Path,
    *,
    source: str,
    scenario: str,
    model: str,
    config_path: str,
    started_at: str,
    wall_seconds: float,
    launch: dict[str, Any],
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    match = TRIAL_DIR.fullmatch(trial_dir.name)
    if match is None:
        raise ValueError(f"not a CaP-X trial artifact: {trial_dir}")

    summary = _read(trial_dir / "summary.txt")
    fields = _summary_fields(summary)
    code = _read(trial_dir / "code.py")
    raw_response = _read(trial_dir / "raw_response.sh")
    prompt = _read(trial_dir / "prompts_and_responses" / "initial_prompt.txt")
    sandbox_rc = int(fields.get("Sandbox failed", match.group("rc")))
    reward = float(fields.get("Reward", match.group("reward")))
    completed = _bool(fields.get("Task Completed"))
    if completed is None:
        completed = match.group("completed") == "1"
    terminated_text = fields.get("Terminated", "")
    terminated_match = re.match(
        r"(?P<terminated>True|False),\s*Truncated:\s*(?P<truncated>True|False)",
        terminated_text,
    )

    return {
        "schema_version": "capx-story/v1",
        "source": source,
        "source_disclosure": (
            "Live CaP-X launch" if source == "live" else "Recorded fixture; no live model or simulator was run"
        ),
        "scenario": scenario,
        "model": model,
        "trial": int(match.group("trial")),
        "perception": {
            "backend": "owlv2+sam2",
            "config_path": config_path,
        },
        "generation": {
            "prompt": prompt,
            "raw_response": raw_response,
            "generated_code": code,
            "called_primitives": _called_primitives(code, scenario),
            "primitive_sources": [],
        },
        "evaluation": {
            "trial": int(match.group("trial")),
            "reward": reward,
            "task_completed": completed,
            "terminated": (_bool(terminated_match.group("terminated")) if terminated_match else None),
            "truncated": (_bool(terminated_match.group("truncated")) if terminated_match else None),
            "sandbox": {
                "returncode": sandbox_rc,
                "stdout": fields.get("Stdout", ""),
                "stderr": fields.get("Stderr", ""),
            },
        },
        "timing": {
            "started_at_utc": started_at,
            "wall_seconds": wall_seconds,
            "query_seconds": _query_seconds(summary + "\n" + launch.get("stdout", "")),
        },
        "launch": launch,
        "artifacts": _artifact_paths(trial_dir),
        "provenance": provenance or {},
    }


def _latest_trial(out_dir: Path, model: str, *, not_before: float) -> Path | None:
    expected = out_dir.parent / model.replace("/", "_") / out_dir.name
    roots = [expected, out_dir]
    if out_dir.parent.is_dir():
        roots.extend(out_dir.parent.glob(f"*/{out_dir.name}"))
    candidates: list[Path] = []
    for root in roots:
        if root.is_dir():
            candidates.extend(
                path
                for path in root.rglob("trial_*")
                if (path.is_dir() and TRIAL_DIR.fullmatch(path.name) and path.stat().st_mtime >= not_before)
            )
    return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None


def _run_live(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    capx_root = args.capx_root.expanduser().resolve()
    # Do not resolve the interpreter symlink: doing so bypasses the virtual
    # environment and invokes its base Python without CaP-X dependencies.
    capx_python = Path(os.path.abspath(args.capx_python.expanduser()))
    launcher = capx_root / "capx" / "envs" / "launch.py"
    if not launcher.is_file():
        raise RuntimeError(f"CaP-X launcher not found: {launcher}")
    if not capx_python.is_file():
        raise RuntimeError(f"CaP-X Python not found: {capx_python}")

    if not args.skip_lemonade:
        sys.path.insert(0, str(HERE))
        try:
            from capx_demo import ensure_lemonade

            ensure_lemonade(args.model)
        finally:
            if str(HERE) in sys.path:
                sys.path.remove(str(HERE))

    out_dir = args.output_dir / "artifacts" / "scenarios" / args.scenario
    out_dir.mkdir(parents=True, exist_ok=True)
    config_path = SCENARIOS[args.scenario]
    command = [
        str(capx_python),
        str(launcher),
        "--config-path",
        config_path,
        "--model",
        args.model,
        "--server-url",
        args.server_url,
        "--temperature",
        str(args.temperature),
        "--max-tokens",
        str(args.max_tokens),
        "--total-trials",
        "1",
        "--num-workers",
        "1",
        "--output-dir",
        str(out_dir),
    ]
    started_at = _utc_now()
    started_epoch = time.time()
    started = time.monotonic()
    env = os.environ.copy()
    env.setdefault("MUJOCO_GL", "egl")
    env.setdefault("PYOPENGL_PLATFORM", "egl")
    env.setdefault("HF_HOME", "/opt/capx-cache")
    try:
        proc = subprocess.run(
            command,
            cwd=capx_root,
            env=env,
            text=True,
            capture_output=True,
            timeout=args.timeout,
            check=False,
        )
        returncode = proc.returncode
        stdout = proc.stdout
        stderr = proc.stderr
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        returncode = 124
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        timed_out = True
    elapsed = time.monotonic() - started
    launch = {
        "returncode": returncode,
        "timed_out": timed_out,
        "command": command,
        "stdout": stdout,
        "stderr": stderr,
    }
    trial_dir = _latest_trial(out_dir, args.model, not_before=started_epoch - 1.0)
    if trial_dir is None:
        diagnostic = (stderr or stdout).strip()[-2000:]
        raise RuntimeError(
            f"CaP-X produced no trial artifact. launch rc={returncode}; final launch output:\n{diagnostic}"
        )
    manifest = _trial_manifest(
        trial_dir,
        source="live",
        scenario=args.scenario,
        model=args.model,
        config_path=config_path,
        started_at=started_at,
        wall_seconds=elapsed,
        launch=launch,
    )
    return manifest, returncode


def _run_recorded(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    fixture = json.loads(_read(args.fixture))
    if args.scenario != fixture["scenario"]:
        raise RuntimeError(f"recorded fixture is only for {fixture['scenario']}; use --source live for {args.scenario}")
    fixture_dir = args.fixture.parent
    code_path = fixture_dir / fixture["files"]["generated_code"]
    prompt_path = fixture_dir / fixture["files"]["prompt"]
    checksums = fixture["provenance"]["sha256"]
    if _sha256(code_path) != checksums["generated_code"]:
        raise RuntimeError(f"recorded policy checksum mismatch: {code_path}")
    if _sha256(prompt_path) != checksums["prompt"]:
        raise RuntimeError(f"recorded prompt checksum mismatch: {prompt_path}")

    code = _read(code_path)
    raw_response = code.removeprefix("# Code block 0\n")
    evaluation = fixture["evaluation"]
    manifest = {
        "schema_version": "capx-story/v1",
        "source": "recorded",
        "source_disclosure": "Recorded fixture; no live model or simulator was run",
        "scenario": fixture["scenario"],
        "model": fixture["model"],
        "trial": int(fixture["provenance"]["source_trial"]),
        "perception": fixture["perception"],
        "generation": {
            "prompt": _read(prompt_path),
            "raw_response": raw_response,
            "generated_code": code,
            "called_primitives": _called_primitives(code, fixture["scenario"]),
            "primitive_sources": [],
        },
        "evaluation": {
            "trial": int(fixture["provenance"]["source_trial"]),
            **evaluation,
        },
        "timing": fixture["timing"],
        "launch": {
            "returncode": None,
            "timed_out": False,
            "command": None,
            "stdout": "",
            "stderr": "",
        },
        "artifacts": {
            "trial_dir": None,
            "generated_code": str(code_path.resolve()),
            "raw_response": None,
            "prompt": str(prompt_path.resolve()),
            "summary": None,
            "all_responses": None,
            "videos": [],
        },
        "provenance": fixture["provenance"],
    }
    return manifest, 0


def _write_manifest(manifest: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest["artifacts"]["manifest"] = str(path.resolve())
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _print_story(manifest: dict[str, Any], show_primitives: bool) -> None:
    source = manifest["source"].upper()
    print(f"=== CaP-X source: {source} ===")
    print(manifest["source_disclosure"])
    print("\n=== Generated high-level code ===")
    print(manifest["generation"]["generated_code"].rstrip())
    if show_primitives:
        print("\n=== Called primitive implementations ===")
        sources = manifest["generation"]["primitive_sources"]
        if not sources:
            called = ", ".join(manifest["generation"]["called_primitives"]) or "none"
            print(f"Source unavailable; called primitives: {called}")
        for primitive in sources:
            print(f"\n--- {primitive['name']} ({primitive['path']}) ---")
            print(primitive["source"])


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        required=True,
        choices=("live", "recorded"),
        help="required provenance mode; recorded is always disclosed as replay",
    )
    parser.add_argument("--scenario", choices=tuple(SCENARIOS), default="cube_stack")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--server-url", default=DEFAULT_SERVER_URL)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--capx-root", type=Path, default=DEFAULT_CAPX_ROOT)
    parser.add_argument("--capx-python", type=Path, default=DEFAULT_CAPX_PYTHON)
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/capx_story"))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--fixture", type=Path, default=FIXTURE_METADATA)
    parser.add_argument(
        "--skip-lemonade",
        action="store_true",
        help="assume the requested model is already serving on --server-url",
    )
    parser.add_argument(
        "--show-primitives",
        action="store_true",
        help="print source for CaP-X primitives called by generated code",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    args.output_dir = args.output_dir.expanduser().resolve()
    args.fixture = args.fixture.expanduser().resolve()
    try:
        manifest, returncode = _run_live(args) if args.source == "live" else _run_recorded(args)
        if args.show_primitives:
            manifest["generation"]["primitive_sources"] = _primitive_sources(
                manifest["generation"]["generated_code"],
                manifest["scenario"],
                args.capx_root.expanduser().resolve(),
            )
        manifest_path = (
            args.manifest.expanduser().resolve()
            if args.manifest
            else args.output_dir / f"{args.scenario}_{args.source}_manifest.json"
        )
        _write_manifest(manifest, manifest_path)
        _print_story(manifest, args.show_primitives)
        print(f"\nManifest: {manifest_path}")
        return returncode
    except (OSError, ValueError, KeyError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"capx_story: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
