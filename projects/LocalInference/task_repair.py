#!/usr/bin/env python3
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
"""Run bounded RHO repair on one task-specific CaP-X manifest."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import rho_demo
from generalization_eval import TASK_CONFIGS


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _metric(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: result.get(key)
        for key in (
            "trial",
            "reward",
            "raw_reward",
            "task_completed",
            "timed_out",
            "traceback",
            "feedback",
            "video",
        )
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--scenario", choices=tuple(TASK_CONFIGS), required=True)
    parser.add_argument("--heldout-trial", type=int, default=2)
    parser.add_argument("--generations", type=int, choices=(1, 2), default=1)
    parser.add_argument("--rho-timeout", type=float, default=480.0)
    parser.add_argument("--capture-video", action="store_true")
    parser.add_argument("--objective", required=True)
    parser.add_argument("--background", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    args.manifest = args.manifest.expanduser().resolve()
    args.output_dir = args.output_dir.expanduser().resolve()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    manifest_scenario = manifest.get("scenario")
    if manifest_scenario != args.scenario:
        raise ValueError(
            f"manifest scenario {manifest_scenario!r} does not match "
            f"{args.scenario!r}"
        )
    artifact = Path(manifest["artifacts"]["generated_code"])
    api_reference = (
        "# Authentic CaP-X generation prompt and API contract\n\n"
        + manifest["generation"]["prompt"].strip()
        + "\n\nOnly edit files below `solver/`.\n"
    )
    os.environ["RHO_CONFIG_PATH"] = TASK_CONFIGS[args.scenario]
    rho_demo.ensure_services()

    candidate = rho_demo.prepare_workshop(
        args.output_dir / "candidate",
        artifact=artifact,
        provenance=manifest,
        heldout_trial=args.heldout_trial,
        generations=args.generations,
        api_reference=api_reference,
        objective=args.objective,
        background=args.background,
    )
    seed_train = rho_demo.score_candidate(
        candidate, "train", capture=args.capture_video
    )
    seed_val = rho_demo.score_candidate(
        candidate, "val", capture=args.capture_video
    )
    run = rho_demo.run_helix(
        candidate,
        generations=args.generations,
        timeout_seconds=args.rho_timeout,
    )
    summary = rho_demo.summarize_run(candidate)
    best = Path(summary["live_best"])
    best_train = rho_demo.score_candidate(best, "train", capture=args.capture_video)
    best_val = rho_demo.score_candidate(best, "val", capture=args.capture_video)
    proven = bool(
        summary["accepted"]
        and best_train["reward"] > seed_train["reward"]
        and best_val["reward"] > seed_val["reward"]
        and best_train["task_completed"]
        and best_val["task_completed"]
    )
    report = {
        "schema_version": "capx-task-repair/v1",
        "finished_at_utc": _utc_now(),
        "scenario": args.scenario,
        "source_manifest": str(args.manifest),
        "config_path": TASK_CONFIGS[args.scenario],
        "rho_model": rho_demo.MODEL,
        "objective": args.objective,
        "seed": {
            "train": _metric(seed_train),
            "heldout": _metric(seed_val),
        },
        "evolution": {
            **asdict(run),
            "accepted": summary["accepted"],
            "improved_best": summary["improved_best"],
            "best_diff": summary["best_diff"],
            "semantic_mutation": summary["semantic_mutation"],
        },
        "best": {
            "root": str(best),
            "train": _metric(best_train),
            "heldout": _metric(best_val),
        },
        "proven": proven,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.output_dir / "repair_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Report: {report_path}")
    return 0 if proven else 1


if __name__ == "__main__":
    raise SystemExit(main())
