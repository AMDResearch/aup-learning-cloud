#!/usr/bin/env python3
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
"""Evaluate unchanged CaP-X policy files across deterministic task trials."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import rho_demo

TASK_CONFIGS = {
    "cube_lift": ("env_configs/cube_lifting/franka_robosuite_cube_lifting.yaml"),
    "cube_restack": ("env_configs/cube_restack/franka_robosuite_cube_restack.yaml"),
    "cube_stack": "env_configs/cube_stack/franka_robosuite_cube_stack.yaml",
    "spill_wipe": "env_configs/spill_wipe/franka_robosuite_spill_wipe.yaml",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _policy_spec(value: str) -> tuple[str, str, Path]:
    try:
        label, scenario, raw_path = value.split(":", 2)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("policy must have the form LABEL:SCENARIO:PATH") from exc
    if not label:
        raise argparse.ArgumentTypeError("policy label cannot be empty")
    if scenario not in TASK_CONFIGS:
        choices = ", ".join(sorted(TASK_CONFIGS))
        raise argparse.ArgumentTypeError(f"unknown scenario {scenario!r}; choose from {choices}")
    path = Path(raw_path).expanduser().resolve()
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"policy file does not exist: {path}")
    return label, scenario, path


def _trials(value: str) -> list[int]:
    try:
        trials = [int(item.strip()) for item in value.split(",") if item.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("trials must be comma-separated integers") from exc
    if not trials or any(trial < 0 for trial in trials):
        raise argparse.ArgumentTypeError("trials must contain non-negative integers")
    if len(set(trials)) != len(trials):
        raise argparse.ArgumentTypeError("trials must be unique")
    return trials


def _metric(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: result.get(key)
        for key in (
            "trial",
            "reward",
            "raw_reward",
            "task_completed",
            "timed_out",
            "stderr",
            "traceback",
            "feedback",
            "video",
            "elapsed_seconds",
        )
    }


def _aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(results)
    completed = sum(bool(result.get("task_completed")) for result in results)
    execution_failures = sum(
        bool(result.get("stderr"))
        or bool(result.get("traceback"))
        or bool(result.get("timed_out"))
        or "Sandbox stderr:" in str(result.get("feedback") or "")
        for result in results
    )
    return {
        "trials": count,
        "completed": completed,
        "success_rate": completed / count,
        "mean_reward": sum(float(result.get("reward") or 0.0) for result in results) / count,
        "mean_raw_reward": sum(float(result.get("raw_reward") or 0.0) for result in results) / count,
        "execution_failures": execution_failures,
    }


def _write(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--policy",
        type=_policy_spec,
        action="append",
        required=True,
        metavar="LABEL:SCENARIO:PATH",
        help="unchanged policy artifact to evaluate; may be repeated",
    )
    parser.add_argument("--trials", type=_trials, default=[1, 2, 3, 4, 5])
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--capture-video", action="store_true")
    parser.add_argument("--work-dir", type=Path, default=Path("/tmp/capx_generalization"))
    parser.add_argument("--output", type=Path, default=Path("/tmp/capx_generalization/report.json"))
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    args.work_dir = args.work_dir.expanduser().resolve()
    args.output = args.output.expanduser().resolve()
    report: dict[str, Any] = {
        "schema_version": "capx-generalization/v1",
        "started_at_utc": _utc_now(),
        "method": (
            "Each policy file is held byte-for-byte constant while the simulator "
            "is independently reset with each listed trial ID and seed. The "
            "simulator and perception stack may still contain nondeterminism."
        ),
        "trials": args.trials,
        "policies": [],
    }
    _write(report, args.output)

    rho_demo.ensure_services()
    for label, scenario, policy_path in args.policy:
        policy = policy_path.read_bytes()
        candidate = rho_demo.prepare_workshop(
            args.work_dir / label,
            artifact=policy_path,
            provenance={
                "source": "generalization_evaluation",
                "scenario": scenario,
                "trial": args.trials[0],
                "policy_sha256": hashlib.sha256(policy).hexdigest(),
            },
            heldout_trial=args.trials[0],
        )
        os.environ["RHO_CONFIG_PATH"] = TASK_CONFIGS[scenario]
        results: list[dict[str, Any]] = []
        item = {
            "label": label,
            "scenario": scenario,
            "config_path": TASK_CONFIGS[scenario],
            "policy_path": str(policy_path),
            "policy_sha256": hashlib.sha256(policy).hexdigest(),
            "policy_bytes": len(policy),
            "results": results,
            "aggregate": None,
        }
        report["policies"].append(item)

        for trial in args.trials:
            result = rho_demo.score_candidate(
                candidate,
                "val",
                trial=trial,
                capture=args.capture_video,
                timeout_seconds=args.timeout,
            )
            results.append(_metric(result))
            item["aggregate"] = _aggregate(results)
            _write(report, args.output)
            status = "PASS" if result.get("task_completed") else "FAIL"
            print(
                f"{label} trial {trial}: {status} "
                f"reward={float(result.get('reward') or 0.0):.4f} "
                f"raw={float(result.get('raw_reward') or 0.0):.4f}",
                flush=True,
            )

    report["finished_at_utc"] = _utc_now()
    _write(report, args.output)
    print(json.dumps({item["label"]: item["aggregate"] for item in report["policies"]}, indent=2))
    print(f"Report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
