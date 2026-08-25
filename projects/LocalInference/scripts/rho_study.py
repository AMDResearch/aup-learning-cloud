#!/usr/bin/env python3
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
"""Run reproducible single-task Robotics Harness Optimization studies."""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from dataclasses import asdict
from pathlib import Path


SHARED_GEOMETRY = """\
import numpy


def stack_center(target_position, target_extent, object_extent):
    \"\"\"Return the XYZ center for stacking one object on a target object.\"\"\"
    center = numpy.asarray(target_position, dtype=float).copy()
    center[2] += float(target_extent[2] + object_extent[2]) / 2.0
    return center
"""

SHARED_OBJECTIVE = """\
Repair this authentic CaP-X cube-stack policy so it works across layouts.
Use the pure geometry helper in solver/geometry.py for the placement-center
calculation, and correct any misuse of the flat XYZ poses returned by the API."""

SHARED_BACKGROUND = """\
This one-generation study exposes a generated task policy plus a reusable pure
geometry module. Read the evaluator diagnostics and API_REFERENCE.md, then edit
files only below solver/. Do not encode trial IDs or fixed poses. Imported
helpers may perform calculations but cannot directly call robot primitives.
Compile solver/*.py, run the permitted evaluator self-check once, and inspect
the source diff before finishing."""

RESTACK_CONFIG = "env_configs/cube_restack/franka_robosuite_cube_restack.yaml"
RESTACK_API_REFERENCE = """\
# CaP-X cube-restack contract

Repair an authentic generated policy that should gently place the red cube,
already held by the gripper at episode start, on top of the green cube and then
open the gripper.

- `get_object_pose(name, return_bbox_extent=True)` returns a flat XYZ center,
  WXYZ quaternion, and full XYZ side lengths.
- The target red-cube center height is the green center plus half the green
  height and half the red height.
- Use a reliable downward or held-object orientation for placement.
- `goto_pose(position, quaternion, z_approach=0.1)` performs a controlled
  approach. Do not drop the cube from a height.
- `open_gripper()` releases the cube after reaching the placement pose.
- Robot primitives are already injected; import numerical libraries explicitly.

The evaluator uses the artifact's source trial for training and a separate
held-out trial for validation. Only edit files below `solver/`.
"""
RESTACK_OBJECTIVE = """\
Repair this authentic CaP-X cube-restack program so it reliably places the
already-held red cube on the green cube and releases it without dropping.
Diagnose evaluator feedback and use scene-derived positions and full extents;
do not encode trial-specific coordinates."""
RESTACK_BACKGROUND = """\
This is a bounded cube-restack mutation-depth study. Read API_REFERENCE.md and
the evaluator diagnostics, then edit only solver/. The red cube begins in the
gripper, so focus on general placement geometry, controlled approach, and
release rather than adding an unrelated pickup sequence. Compile solver/*.py,
run the permitted evaluator self-check once, and inspect the diff."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--generations", type=int, default=1, choices=range(1, 5))
    parser.add_argument("--artifact", type=Path)
    parser.add_argument(
        "--config-path",
        default=None,
    )
    parser.add_argument(
        "--task",
        choices=("cube-stack", "cube-restack"),
        default="cube-stack",
    )
    parser.add_argument("--heldout-trial", type=int, default=2)
    parser.add_argument(
        "--surface",
        choices=("single-policy", "one-task-shared-helper"),
        default="single-policy",
    )
    parser.add_argument("--objective")
    parser.add_argument("--background")
    parser.add_argument("--timeout", type=float, default=480.0)
    parser.add_argument("--capture", action="store_true")
    return parser.parse_args()


def compact_result(result: dict) -> dict:
    keys = (
        "reward",
        "raw_reward",
        "task_completed",
        "split",
        "trial",
        "feedback",
        "traceback",
        "video",
        "timed_out",
        "elapsed_seconds",
    )
    return {key: result.get(key) for key in keys}


def main() -> int:
    args = parse_args()
    if args.task == "cube-restack" and args.surface != "single-policy":
        raise SystemExit("cube-restack currently supports only the single-policy surface")
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    config_path = args.config_path or (
        RESTACK_CONFIG
        if args.task == "cube-restack"
        else "env_configs/cube_stack/franka_robosuite_cube_stack.yaml"
    )

    os.environ["RHO_MODEL"] = args.model
    os.environ["RHO_CONFIG_PATH"] = config_path
    os.environ["RHO_WORKSHOP_ROOT"] = str(output_dir)
    os.environ["RHO_VIDEO_ROOT"] = str(output_dir / "videos")
    os.environ.setdefault(
        "RHO_SUPPORT_ROOT",
        str(Path(__file__).resolve().parent),
    )

    # Import only after the model, config, and output roots are fixed because
    # rho_demo intentionally captures those settings at module import time.
    import rho_demo

    prepare_kwargs = {
        "root": output_dir / "candidate",
        "artifact": args.artifact,
        "heldout_trial": args.heldout_trial,
        "generations": args.generations,
    }
    if args.objective:
        prepare_kwargs["objective"] = args.objective
    if args.background:
        prepare_kwargs["background"] = args.background
    if args.task == "cube-restack":
        prepare_kwargs.update(
            {
                "api_reference": RESTACK_API_REFERENCE,
                "objective": args.objective or RESTACK_OBJECTIVE,
                "background": args.background or RESTACK_BACKGROUND,
            }
        )
    if args.surface == "one-task-shared-helper":
        prepare_kwargs.update(
            {
                "objective": args.objective or SHARED_OBJECTIVE,
                "background": args.background or SHARED_BACKGROUND,
                "api_reference": (
                    rho_demo.API_REFERENCE
                    + "\n- `solver.geometry.stack_center(...)` computes the "
                    "placement center from flat XYZ inputs and full extents.\n"
                ),
                "support_files": {
                    "solver/geometry.py": SHARED_GEOMETRY,
                },
            }
        )

    report_path = output_dir / "report.json"
    try:
        rho_demo.ensure_services(model=args.model)
        root = rho_demo.prepare_workshop(**prepare_kwargs)
        before_train = rho_demo.score_candidate(root, "train")
        before_val = rho_demo.score_candidate(root, "val", capture=args.capture)
        run = rho_demo.run_helix(
            root,
            generations=args.generations,
            timeout_seconds=args.timeout,
            progress=lambda line: print(line, flush=True),
        )
        summary = rho_demo.summarize_run(root)
        best = Path(summary["live_best"])
        after_train = rho_demo.score_candidate(best, "train")
        after_val = rho_demo.score_candidate(best, "val", capture=args.capture)
        report = {
            "schema_version": "rho-study/v1",
            "provenance": {
                "created_at": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ",
                    time.gmtime(),
                ),
                "hostname": socket.gethostname(),
                "image_id": os.environ.get("EXPERIMENT_IMAGE_ID"),
                "source_revision": os.environ.get("EXPERIMENT_SOURCE_REVISION"),
            },
            "model": args.model,
            "task": args.task,
            "surface": args.surface,
            "config_path": config_path,
            "generations": args.generations,
            "artifact": str(args.artifact) if args.artifact else None,
            "before": {
                "train": compact_result(before_train),
                "val": compact_result(before_val),
            },
            "helix": asdict(run),
            "summary": summary,
            "after": {
                "train": compact_result(after_train),
                "val": compact_result(after_val),
            },
        }
        report_path.write_text(json.dumps(report, indent=2, default=str) + "\n")
        print(
            "RHO_STUDY_RESULT="
            + json.dumps(
                {
                    "model": args.model,
                    "surface": args.surface,
                    "generations": args.generations,
                    "accepted": summary["accepted"],
                    "before_reward": before_val["reward"],
                    "after_reward": after_val["reward"],
                    "completed": after_val["task_completed"],
                    "helix_seconds": run.elapsed_seconds,
                    "report": str(report_path),
                },
                separators=(",", ":"),
            )
        )
        return 124 if run.timed_out else run.returncode
    finally:
        rho_demo.stop_owned_services()


if __name__ == "__main__":
    sys.exit(main())
