#!/usr/bin/env python3
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
"""Consolidate CaP-X sweep shards into a compact evidence report."""

from __future__ import annotations

import argparse
import ast
import json
import re
import statistics
from collections import Counter
from pathlib import Path


PRIMITIVES = (
    "get_object_pose",
    "sample_grasp_pose",
    "goto_pose",
    "open_gripper",
    "close_gripper",
    "home_pose",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("shards", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def artifact_dir(shard: Path, rollout: dict) -> Path | None:
    raw = rollout.get("dir")
    if not raw:
        return None
    task = re.sub(r"[^0-9A-Za-z]+", "_", str(rollout["label"]))
    return (
        shard.parent
        / "artifacts"
        / "scenarios"
        / str(rollout["model"])
        / task
        / Path(str(raw)).name
    )


def analyze_program(program: str) -> dict:
    calls = Counter({name: 0 for name in PRIMITIVES})
    syntax_error = None
    try:
        tree = ast.parse(program)
    except SyntaxError as exc:
        tree = None
        syntax_error = f"{exc.msg} (line {exc.lineno})"
    if tree is not None:
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in calls
            ):
                calls[node.func.id] += 1
    compact = "".join(program.split())
    return {
        "syntax_error": syntax_error,
        "primitive_calls": dict(calls),
        "uses_bbox_extent": "return_bbox_extent=True" in compact,
        "uses_approach_offset": "z_approach=" in compact,
        "nested_pose_indexing": bool(
            re.search(r"[A-Za-z_][A-Za-z0-9_]*_pose\[0\]\[[012]\]", compact)
        ),
        "line_count": len(program.splitlines()),
    }


def classify(rollout: dict, summary: str) -> str:
    reward = float(rollout.get("reward") or 0.0)
    if rollout.get("solved"):
        return "completed"
    if rollout.get("error"):
        if "SyntaxError" in summary:
            return "syntax failure"
        if "IndexError" in summary:
            return "indexing failure"
        if "terminated episode" in summary.lower():
            return "post-termination action"
        if "too many values to unpack" in summary:
            return "API arity mismatch"
        if "NameError" in summary:
            return "missing name or import"
        return "other execution failure"
    if reward > 0.0:
        return "partial execution"
    return "no progress"


def enriched_rollout(shard: Path, rollout: dict) -> dict:
    directory = artifact_dir(shard, rollout)
    code_path = directory / "code.py" if directory else None
    summary_path = directory / "summary.txt" if directory else None
    program = (
        code_path.read_text(errors="replace")
        if code_path is not None and code_path.is_file()
        else ""
    )
    summary = (
        summary_path.read_text(errors="replace")
        if summary_path is not None and summary_path.is_file()
        else ""
    )
    return {
        **{key: value for key, value in rollout.items() if key != "dir"},
        "outcome": classify(rollout, summary),
        "program_analysis": analyze_program(program),
    }


def aggregate_model_summaries(models: list[dict], rollouts: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    order: list[str] = []
    for model in models:
        key = str(model["key"])
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(model)

    aggregated = []
    dynamic_fields = {
        "solved",
        "rollouts",
        "success_rate",
        "sandbox_errors",
        "mean_reward",
        "mean_rollout_seconds",
        "per_task",
        "total_model_minutes",
    }
    for key in order:
        source_models = grouped[key]
        rows = [row for row in rollouts if row["model_key"] == key]
        per_task = {}
        for task in ("cube lift", "cube stack", "cube restack", "spill wipe"):
            task_rows = [row for row in rows if row["label"] == task]
            per_task[task] = {
                "solved": sum(bool(row["solved"]) for row in task_rows),
                "rollouts": len(task_rows),
                "mean_reward": (
                    statistics.fmean(float(row["reward"]) for row in task_rows)
                    if task_rows
                    else 0.0
                ),
            }
        solved = sum(bool(row["solved"]) for row in rows)
        aggregated.append(
            {
                **{
                    name: value
                    for name, value in source_models[0].items()
                    if name not in dynamic_fields
                },
                "solved": solved,
                "rollouts": len(rows),
                "success_rate": solved / len(rows) if rows else 0.0,
                "sandbox_errors": sum(bool(row["error"]) for row in rows),
                "mean_reward": (
                    statistics.fmean(float(row["reward"]) for row in rows)
                    if rows
                    else 0.0
                ),
                "mean_rollout_seconds": (
                    statistics.fmean(
                        float(row.get("elapsed_seconds", 0.0)) for row in rows
                    )
                    if rows
                    else 0.0
                ),
                "per_task": per_task,
                "total_model_minutes": sum(
                    float(model.get("total_model_minutes", 0.0))
                    for model in source_models
                ),
            }
        )
    return aggregated


def main() -> int:
    args = parse_args()
    shard_payloads = [
        (path.expanduser().resolve(), json.loads(path.read_text()))
        for path in args.shards
    ]
    metadata = [payload["metadata"] for _, payload in shard_payloads]
    raw_summaries = [
        model
        for _, payload in shard_payloads
        for model in payload.get("models", [])
    ]
    shard_rollouts = [
        enriched_rollout(path, rollout)
        for path, payload in shard_payloads
        for rollout in payload.get("rollouts", [])
    ]
    rollouts = []
    seen_rollouts = set()
    for rollout in shard_rollouts:
        identity = (
            rollout.get("model_key"),
            rollout.get("label"),
            rollout.get("trial"),
        )
        if identity not in seen_rollouts:
            seen_rollouts.add(identity)
            rollouts.append(rollout)
    model_rollouts = [
        rollout for rollout in rollouts if rollout.get("model_key") != "oracle"
    ]
    oracle_rollouts = [
        rollout for rollout in rollouts if rollout.get("model_key") == "oracle"
    ]
    summaries = aggregate_model_summaries(raw_summaries, model_rollouts)

    taxonomy = {}
    code_signals = {}
    for model in summaries:
        key = str(model["key"])
        rows = [row for row in model_rollouts if row["model_key"] == key]
        taxonomy[key] = dict(Counter(str(row["outcome"]) for row in rows))
        code_signals[key] = {
            "programs": len(rows),
            "syntax_errors": sum(
                bool(row["program_analysis"]["syntax_error"]) for row in rows
            ),
            "uses_bbox_extent": sum(
                bool(row["program_analysis"]["uses_bbox_extent"]) for row in rows
            ),
            "uses_approach_offset": sum(
                bool(row["program_analysis"]["uses_approach_offset"]) for row in rows
            ),
            "nested_pose_indexing": sum(
                bool(row["program_analysis"]["nested_pose_indexing"]) for row in rows
            ),
            "median_program_lines": (
                statistics.median(
                    int(row["program_analysis"]["line_count"]) for row in rows
                )
                if rows
                else 0
            ),
        }

    identities = {
        (item.get("image_id"), item.get("source_revision"), item.get("perception"))
        for item in metadata
    }
    restack_oracle_solved = any(
        row["label"] == "cube restack" and row["solved"]
        for row in oracle_rollouts
    )
    report = {
        "schema_version": "capx-overnight-analysis/v1",
        "comparable_shards": len(identities) == 1,
        "environment_identities": [
            {
                "hostname": item.get("hostname"),
                "image_id": item.get("image_id"),
                "source_revision": item.get("source_revision"),
                "perception": item.get("perception"),
                "created_at": item.get("created_at"),
            }
            for item in metadata
        ],
        "oracle": {
            "rollouts": len(oracle_rollouts),
            "per_task": {
                task: {
                    "solved": sum(
                        bool(row["solved"])
                        for row in oracle_rollouts
                        if row["label"] == task
                    ),
                    "reward": max(
                        (
                            float(row["reward"])
                            for row in oracle_rollouts
                            if row["label"] == task
                        ),
                        default=None,
                    ),
                }
                for task in ("cube lift", "cube stack", "cube restack", "spill wipe")
            },
        },
        "models": summaries,
        "failure_taxonomy": taxonomy,
        "code_signals": code_signals,
        "rollouts": model_rollouts,
        "cube_restack_viability": {
            "oracle_solved": restack_oracle_solved,
            "oracle_max_reward": max(
                (
                    float(row["reward"])
                    for row in oracle_rollouts
                    if row["label"] == "cube restack"
                ),
                default=None,
            ),
            "mutation_depth_run": None,
            "decision": (
                "eligible for staged mutation-depth experiments"
                if restack_oracle_solved
                else "stop before mutation because the open-perception oracle is unhealthy"
            ),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
