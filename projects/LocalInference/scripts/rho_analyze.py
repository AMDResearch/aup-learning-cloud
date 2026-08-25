#!/usr/bin/env python3
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
"""Build a compact summary from recorded RHO study reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recorded-root", type=Path, required=True)
    parser.add_argument("--capx-analysis", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def compact_single(path: Path) -> dict:
    report = json.loads(path.read_text())
    return {
        "id": path.parent.name,
        "model": report["model"],
        "task": report.get("task", "cube-stack"),
        "surface": report["surface"],
        "generations": report["generations"],
        "artifact": report.get("artifact"),
        "provenance": report.get("provenance", {}),
        "accepted": bool(report["summary"]["accepted"]),
        "before_reward": float(report["before"]["val"]["reward"]),
        "after_reward": float(report["after"]["val"]["reward"]),
        "before_completed": bool(report["before"]["val"]["task_completed"]),
        "after_completed": bool(report["after"]["val"]["task_completed"]),
        "helix_seconds": float(report["helix"]["elapsed_seconds"]),
        "semantic_mutation": report["summary"]["semantic_mutation"],
    }


def main() -> int:
    args = parse_args()
    root = args.recorded_root.expanduser().resolve()
    singles = [
        compact_single(path)
        for path in sorted((root / "rho_single").glob("*/report.json"))
    ]
    multi = json.loads((root / "rho_multitask_report.json").read_text())
    capx = json.loads(args.capx_analysis.read_text())

    preflights = [
        run
        for run in singles
        if run["task"] == "cube-stack" and run["surface"] == "single-policy"
    ]
    restack_runs = [
        run
        for run in singles
        if run["task"] == "cube-restack"
    ]
    identities = {
        (
            run["provenance"].get("image_id"),
            run["provenance"].get("source_revision"),
        )
        for run in preflights
    }
    qwen_runs = [
        run
        for run in singles
        if (
            run["task"] == "cube-stack"
            and "Qwen3-Coder-30B-A3B" in run["model"]
        )
    ]
    criterion = multi["success_criterion"]
    restack_depths = [
        int(run["id"].rsplit("depth", 1)[1])
        for run in restack_runs
        if run["id"].rsplit("depth", 1)[-1].isdigit()
    ]
    restack = {
        **capx["cube_restack_viability"],
        "mutation_depth_run": max(restack_depths, default=0),
        "mutation_runs": restack_runs,
    }
    if restack_runs:
        restack["decision"] = (
            "mutation reached task completion"
            if any(run["after_completed"] for run in restack_runs)
            else "mutation remained below task completion"
        )
    report = {
        "schema_version": "rho-overnight-analysis/v1",
        "agent_preflights_comparable": len(identities) == 1,
        "agent_preflights": preflights,
        "qwen_surface_study": {
            "single_task_runs": qwen_runs,
            "multi_task": {
                "model": multi["mutation_model_loader_alias"],
                "surface": "multi-task repository",
                "generations": multi["generations"],
                "selected_candidate": multi["selected_candidate"],
                "completed_before": criterion["completed_before"],
                "completed_after": criterion["completed_after"],
                "completion_rate_before": criterion["completion_rate_before"],
                "completion_rate_after": criterion["completion_rate_after"],
                "mean_reward_before": criterion["mean_reward_before"],
                "mean_reward_after": criterion["mean_reward_after"],
                "criterion_met": criterion["met"],
                "evolution_seconds": multi["timing"]["evolution_seconds"],
            },
        },
        "cube_restack": restack,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
