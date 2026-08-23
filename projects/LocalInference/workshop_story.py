#!/usr/bin/env python3
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
"""Run the script-first CaP-X generation to RHO improvement story."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
CAPX_STORY = HERE / "capx_story.py"
DEFAULT_OUTPUT = Path("/tmp/capx_rho_story")
DEFAULT_RHO_MODEL = "Qwen3-Coder-30B-A3B-Instruct-GGUF"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def _run_capx(
    *,
    source: str,
    scenario: str,
    output_dir: Path,
    attempt: int,
    skip_lemonade: bool,
    show_primitives: bool,
    model: str,
    temperature: float,
    max_tokens: int,
    timeout: float,
) -> tuple[dict[str, Any], Path]:
    attempt_dir = output_dir / "capx" / scenario / f"attempt_{attempt:02d}"
    manifest_path = attempt_dir / "manifest.json"
    command = [
        sys.executable,
        str(CAPX_STORY),
        "--source",
        source,
        "--scenario",
        scenario,
        "--model",
        model,
        "--temperature",
        str(temperature),
        "--max-tokens",
        str(max_tokens),
        "--timeout",
        str(timeout),
        "--output-dir",
        str(attempt_dir),
        "--manifest",
        str(manifest_path),
    ]
    if skip_lemonade:
        command.append("--skip-lemonade")
    if show_primitives:
        command.append("--show-primitives")
    done = subprocess.run(command, text=True, capture_output=True, check=False)
    if done.stdout:
        print(done.stdout, end="")
    if done.stderr:
        print(done.stderr, file=sys.stderr, end="")
    if done.returncode != 0:
        raise RuntimeError(
            f"CaP-X story failed for {scenario} attempt {attempt} "
            f"(exit {done.returncode})"
        )
    return _read_json(manifest_path), manifest_path


def _select_live_examples(
    args: argparse.Namespace,
) -> tuple[dict[str, Any] | None, dict[str, Any], dict[str, Any]]:
    success: dict[str, Any] | None = None
    showcase: dict[str, Any] | None = None
    failure: dict[str, Any] | None = None
    lemonade_ready = False

    for attempt in range(1, args.max_attempts + 1):
        manifest, path = _run_capx(
            source="live",
            scenario="spill_wipe",
            output_dir=args.output_dir,
            attempt=attempt,
            skip_lemonade=lemonade_ready,
            show_primitives=args.show_primitives,
            model=args.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            timeout=args.capx_timeout,
        )
        lemonade_ready = True
        manifest["_manifest_path"] = str(path)
        if (
            showcase is None
            or manifest["evaluation"]["reward"] > showcase["evaluation"]["reward"]
        ):
            showcase = manifest
        if manifest["evaluation"]["task_completed"]:
            success = manifest
            break
    if success is None and showcase is not None:
        print(
            "\nCaP-X did not complete spill-wipe in the bounded attempts; "
            "continuing with the highest-reward live example.",
            file=sys.stderr,
        )

    for attempt in range(1, args.max_attempts + 1):
        manifest, path = _run_capx(
            source="live",
            scenario="cube_stack",
            output_dir=args.output_dir,
            attempt=attempt,
            skip_lemonade=True,
            show_primitives=args.show_primitives,
            model=args.model,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            timeout=args.capx_timeout,
        )
        manifest["_manifest_path"] = str(path)
        if (
            not manifest["evaluation"]["task_completed"]
            and _has_recorded_indexing_bug(manifest)
        ):
            failure = manifest
            break
    if failure is None:
        raise RuntimeError(
            "Gemma produced no cube-stack failure with the recorded flat-XYZ "
            f"indexing bug in {args.max_attempts} attempts"
        )
    if showcase is None:
        raise RuntimeError("CaP-X produced no spill-wipe artifacts")
    return success, showcase, failure


def _recorded_failure(args: argparse.Namespace) -> dict[str, Any]:
    manifest, path = _run_capx(
        source="recorded",
        scenario="cube_stack",
        output_dir=args.output_dir,
        attempt=1,
        skip_lemonade=True,
        show_primitives=args.show_primitives,
        model=args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        timeout=args.capx_timeout,
    )
    manifest["_manifest_path"] = str(path)
    return manifest


def _metric(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: result.get(key)
        for key in (
            "reward",
            "raw_reward",
            "task_completed",
            "trial",
            "timed_out",
            "feedback",
            "video",
        )
    }


def _has_recorded_indexing_bug(manifest: dict[str, Any]) -> bool:
    code = manifest["generation"]["generated_code"]
    return all(
        access in code
        for access in ("green_pose[0][2]", "green_pose[0][0]", "green_pose[0][1]")
    )


def _run_rho(
    args: argparse.Namespace, failure: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    rho_root = (args.output_dir / "rho").resolve()
    os.environ["RHO_WORKSHOP_ROOT"] = str(rho_root)
    os.environ["RHO_MODEL"] = args.rho_model
    if args.mock_rho:
        os.environ["RHO_MOCK_EVAL"] = "1"

    import rho_demo

    if not args.mock_rho:
        rho_demo.ensure_services()

    artifact = Path(failure["artifacts"]["generated_code"])
    root = rho_demo.prepare_workshop(
        rho_root / "candidate",
        artifact=artifact,
        provenance=failure,
        heldout_trial=args.heldout_trial,
        generations=args.generations,
    )
    seed_train = rho_demo.score_candidate(root, "train", capture=args.capture_video)
    seed_val = rho_demo.score_candidate(root, "val", capture=args.capture_video)

    if args.prepare_only:
        report = {
            "candidate_root": str(root),
            "seed": {"train": _metric(seed_train), "heldout": _metric(seed_val)},
            "evolution": None,
            "best": None,
            "proven": False,
        }
        return report, False

    run = rho_demo.run_helix(
        root,
        generations=args.generations,
        timeout_seconds=args.rho_timeout,
    )
    summary = rho_demo.summarize_run(root)
    best = Path(summary["live_best"])
    best_train = rho_demo.score_candidate(best, "train", capture=args.capture_video)
    best_val = rho_demo.score_candidate(best, "val", capture=args.capture_video)
    proven = bool(
        summary["accepted"]
        and best_train["reward"] > seed_train["reward"]
        and best_val["reward"] > seed_val["reward"]
    )
    report = {
        "candidate_root": str(root),
        "seed": {"train": _metric(seed_train), "heldout": _metric(seed_val)},
        "evolution": {
            **asdict(run),
            "accepted": summary["accepted"],
            "improved_best": summary["improved_best"],
            "best_diff": summary["best_diff"],
            "semantic_mutation": summary["semantic_mutation"],
            "child_candidate": summary["child_candidate"],
        },
        "best": {
            "root": str(best),
            "train": _metric(best_train),
            "heldout": _metric(best_val),
        },
        "proven": proven,
    }
    return report, proven


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, choices=("live", "recorded"))
    parser.add_argument("--model", default="Gemma-4-E4B-it-GGUF")
    parser.add_argument(
        "--rho-model",
        default=DEFAULT_RHO_MODEL,
        help="local code-specialized model used by OpenCode",
    )
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--generations", type=int, choices=(1, 2), default=1)
    parser.add_argument("--heldout-trial", type=int, default=2)
    parser.add_argument("--capx-timeout", type=float, default=1800.0)
    parser.add_argument("--rho-timeout", type=float, default=480.0)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--show-primitives", action="store_true")
    parser.add_argument("--capture-video", action="store_true")
    parser.add_argument(
        "--mock-rho",
        action="store_true",
        help="use deterministic evaluator; intended for static validation",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="prepare and score the seed without running HELIX/OpenCode",
    )
    parser.add_argument(
        "--require-improvement",
        action="store_true",
        help="return nonzero unless train and held-out rewards both improve",
    )
    args = parser.parse_args()
    if args.max_attempts < 1:
        parser.error("--max-attempts must be positive")
    if args.heldout_trial < 0:
        parser.error("--heldout-trial must be non-negative")
    return args


def main() -> int:
    args = _parse_args()
    args.output_dir = args.output_dir.expanduser().resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    success: dict[str, Any] | None
    showcase: dict[str, Any] | None
    if args.source == "live":
        success, showcase, failure = _select_live_examples(args)
    else:
        success = None
        showcase = None
        failure = _recorded_failure(args)

    rho, proven = _run_rho(args, failure)
    report = {
        "schema_version": "capx-rho-story/v1",
        "source": args.source,
        "model": args.model,
        "rho_model": args.rho_model,
        "perception": "owlv2+sam2",
        "capx": {
            "success": success,
            "showcase": showcase,
            "failure": failure,
        },
        "rho": rho,
        "proven": proven,
    }
    report_path = args.output_dir / "story_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print("\n=== RHO before/after ===")
    print(json.dumps(rho, indent=2))
    print(f"\nStory proven: {proven}")
    print(f"Report: {report_path}")
    return 1 if args.require_improvement and not proven else 0


if __name__ == "__main__":
    raise SystemExit(main())
