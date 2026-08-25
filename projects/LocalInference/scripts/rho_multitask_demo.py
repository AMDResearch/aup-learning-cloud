# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
"""Multi-task CaP-X repository evolution for the HELIX/GEPA workshop."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import rho_demo


HERE = Path(__file__).resolve().parent
_LOCAL_FIXTURE_ROOT = HERE.parent / "fixtures" / "rho_multitask"
FIXTURE_ROOT = Path(
    os.environ.get(
        "RHO_MULTITASK_FIXTURE_ROOT",
        str(
            _LOCAL_FIXTURE_ROOT
            if _LOCAL_FIXTURE_ROOT.exists()
            else Path("/ryzers/notebooks/fixtures/rho_multitask")
        ),
    )
)
DEFAULT_ROOT = Path("/tmp/rho_multitask_workshop/candidate")
DEFAULT_MODEL = os.environ.get(
    "RHO_MULTITASK_MODEL",
    os.environ.get("RHO_MODEL", "user.Qwen3-Coder-30B-A3B-Instruct-Q4_K_M"),
)
DEFAULT_GENERATIONS = 2
DEFAULT_TIMEOUT = 1200.0
MOCK_LABEL = "MOCK_STATIC_CONTRACT_NOT_LIVE_CAPX"

CONFIGS = {
    "cube_stack": "env_configs/cube_stack/franka_robosuite_cube_stack.yaml",
    "spill_wipe": "env_configs/spill_wipe/franka_robosuite_spill_wipe.yaml",
}

SCENARIOS: dict[str, dict[str, Any]] = {
    "stack_train": {
        "task": "cube_stack",
        "trial": 1,
        "policy_path": "solver/tasks/cube_stack.py",
    },
    "wipe_train": {
        "task": "spill_wipe",
        "trial": 1,
        "policy_path": "solver/tasks/spill_wipe.py",
    },
    "stack_val": {
        "task": "cube_stack",
        "trial": 2,
        "policy_path": "solver/tasks/cube_stack.py",
    },
    "wipe_val": {
        "task": "spill_wipe",
        "trial": 2,
        "policy_path": "solver/tasks/spill_wipe.py",
    },
}

SPLITS = {
    "train": ["stack_train", "wipe_train"],
    "val": ["stack_val", "wipe_val"],
}

CONTRACT = """\
# Multi-task CaP-X repository contract

This repository deploys two generated robot policies:

- `solver/tasks/cube_stack.py` stacks a red cube on a green cube.
- `solver/tasks/spill_wipe.py` wipes the complete detected spill region.

The evaluator runs different simulator layouts for training and validation.
Its feedback includes deployable reward, raw environment reward, task completion,
Python tracebacks, and the tail of robot-policy output. An execution failure has
deployable reward zero even if the robot made partial progress.

You may edit any file below `solver/`, including extracting shared calculations
or safety behavior into `solver/geometry.py` and `solver/runtime.py`. Do not
special-case scenario identifiers, trial numbers, or fixed object coordinates.

Important API facts:

- `get_object_pose(..., return_bbox_extent=True)` returns flat XYZ position,
  WXYZ quaternion, and full XYZ extents.
- `sample_grasp_pose(...)` returns a flat XYZ position and WXYZ quaternion.
- `goto_pose(...)` is blocking and may raise if code keeps issuing actions after
  the simulator has already completed or terminated an episode.
- Imported helper modules cannot directly access the injected robot primitives;
  use them for calculations, path generation, and reusable control decisions.
"""

OBJECTIVE = """\
Evolve this repository into a robust two-task robot policy package. Improve
the cube-stack and spill-wipe policies using evaluator evidence. Prefer general
repairs and shared helpers over trial-specific constants. Multiple specialist
candidates are valuable: HELIX will retain repositories that win different
validation tasks."""

BACKGROUND = """\
This is a two-generation GEPA-style repository evolution. Read CONTRACT.md,
the policy files, and the evaluator diagnostics supplied for your sampled task.
Diagnose failures rather than assuming the repair. Treat the sampled task as
the primary edit target: read its policy first and do not inspect or modify
unrelated working task policies unless the diagnostic implicates them. Use the
read and glob tools for discovery instead of shell commands. Robot primitives
are injected only into task-script globals; imported helper modules must remain
pure calculations or control decisions and cannot call those primitives.
Do not edit protected configuration or encode scenario IDs, trial IDs, or fixed
poses. Reserve enough turns to make the edit and run the checks below.
Before finishing, run `/opt/capx-venv/bin/python -m py_compile solver/*.py
solver/tasks/*.py`, then run
`RHO_EVAL_ORIGIN=agent-self-check /opt/capx-venv/bin/python probe.py`, and
inspect `git diff`."""

PROBE_SOURCE = """\
import os
import sys

sys.path.insert(
    0, os.environ.get("RHO_SUPPORT_ROOT", "/ryzers/notebooks/scripts")
)
from rho_multitask_demo import evaluate_cli

raise SystemExit(evaluate_cli())
"""

GEOMETRY_SOURCE = '''\
"""Shared geometry helpers for robot policies.

Candidates may add reusable, task-independent calculations here.
"""
'''

RUNTIME_SOURCE = '''\
"""Shared path and execution helpers for robot policies.

Robot primitives are injected only into each task script's execution globals.
Helpers in this module should return data or control decisions to those scripts.
"""
'''


def opencode_model_id(model: str = DEFAULT_MODEL) -> str:
    """Return the OpenAI API id for a Lemonade user-registry alias."""
    return model.removeprefix("user.")


def opencode_config(model: str = DEFAULT_MODEL) -> dict[str, Any]:
    api_model = opencode_model_id(model)
    return {
        "$schema": "https://opencode.ai/config.json",
        "model": f"lemonade/{api_model}",
        "small_model": f"lemonade/{api_model}",
        "agent": {"build": {"temperature": 0.1, "steps": 24}},
        "experimental": {"primary_tools": ["read", "edit", "bash"]},
        "provider": {
            "lemonade": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Local Lemonade",
                "options": {
                    "baseURL": "http://127.0.0.1:13305/api/v1",
                    "apiKey": "lemonade",
                },
                "models": {
                    api_model: {
                        "name": api_model,
                        "tool_call": True,
                        "limit": {"context": 32768, "output": 8192},
                    }
                },
            }
        },
        "permission": {
            "*": "allow",
            "edit": {
                "*": "deny",
                "solver/**": "allow",
                "**/solver/**": "allow",
            },
            "external_directory": "deny",
            "webfetch": "deny",
            "websearch": "deny",
            "task": "deny",
            "skill": "deny",
            "todowrite": "deny",
            "bash": {
                "*": "deny",
                (
                    "RHO_EVAL_ORIGIN=agent-self-check "
                    "/opt/capx-venv/bin/python probe.py*"
                ): "allow",
                (
                    "/opt/capx-venv/bin/python -m py_compile "
                    "solver/*.py solver/tasks/*.py"
                ): "allow",
                "git diff*": "allow",
                "git status*": "allow",
            },
        },
    }


def helix_config(
    *,
    model: str = DEFAULT_MODEL,
    generations: int = DEFAULT_GENERATIONS,
) -> str:
    if generations < 2:
        raise ValueError("the multi-task workshop requires at least two generations")
    if generations > 4:
        raise ValueError("the multi-task workshop is capped at four generations")
    api_model = opencode_model_id(model)
    return f'''\
objective = """{OBJECTIVE}"""
seed = "."
rng_seed = 29
passthrough_env = [
  "CUDA_VISIBLE_DEVICES",
  "HIP_VISIBLE_DEVICES",
  "ROCR_VISIBLE_DEVICES",
  "HSA_OVERRIDE_GFX_VERSION",
  "LD_LIBRARY_PATH",
  "HF_HOME",
  "MUJOCO_GL",
  "PYOPENGL_PLATFORM",
  "CAPX_ROOT",
  "RHO_MODEL",
  "RHO_MULTITASK_MODEL",
  "RHO_MULTITASK_MOCK",
  "RHO_PROGRESS_FILE",
  "RHO_SUPPORT_ROOT",
  "XDG_RUNTIME_DIR",
]

[env]
CAPX_ROOT = "/ryzers/cap-x"
HF_HOME = "/opt/capx-cache"
MUJOCO_GL = "egl"
PYOPENGL_PLATFORM = "egl"
RHO_EVAL_TIMEOUT = "180"

[evaluator]
command = "/opt/capx-venv/bin/python probe.py"
protected_files = [
  "probe.py",
  "helix.toml",
  "opencode.json",
  "CONTRACT.md",
  "scenarios.json",
  "provenance.json",
]

[dataset]
train_size = 2
val_size = 2

[evolution]
max_generations = {generations}
# Scores are bounded by 1.0; 1.1 deliberately prevents a generation-1
# universal candidate from short-circuiting the two-generation lesson.
perfect_score_threshold = 1.1
max_evaluations = 40
merge_enabled = true
max_merge_invocations = 2
merge_val_overlap_floor = 1
merge_subsample_size = 2
num_parallel_proposals = 2
mutations_per_parent = 1
minibatch_size = 1
max_workers = 1
cache_evaluation = true
acceptance_criterion = "strict_improvement"
frontier_type = "instance"
batch_sampler = "epoch_shuffled"

[agent]
backend = "opencode"
model = "lemonade/{api_model}"
max_turns = 24
background = """{BACKGROUND}"""

[sandbox]
enabled = false

[worktree]
base_dir = ".helix/worktrees"
'''


def scenario_manifest() -> dict[str, Any]:
    return {
        "schema_version": "rho-multitask-scenarios/v2",
        "splits": SPLITS,
        "scenarios": {
            scenario_id: {
                **scenario,
                "config_path": CONFIGS[str(scenario["task"])],
            }
            for scenario_id, scenario in SCENARIOS.items()
        },
        "hidden_rollouts_exposed_to_evolution": False,
    }


def _safe_reset(path: Path) -> None:
    resolved = path.resolve()
    temporary_root = Path("/tmp").resolve()
    if resolved == temporary_root or temporary_root not in resolved.parents:
        raise ValueError(f"refusing to remove non-workshop path: {resolved}")
    shutil.rmtree(resolved, ignore_errors=True)


def prepare_workshop(
    root: Path | str = DEFAULT_ROOT,
    *,
    model: str = DEFAULT_MODEL,
    generations: int = DEFAULT_GENERATIONS,
    reset: bool = True,
) -> Path:
    """Create a disposable multi-policy Git repository for HELIX."""
    root = Path(root).expanduser().resolve()
    if reset:
        _safe_reset(root)
    tasks = root / "solver" / "tasks"
    tasks.mkdir(parents=True, exist_ok=True)
    (root / "solver" / "__init__.py").write_text("")
    (tasks / "__init__.py").write_text("")
    for task in ("cube_stack", "spill_wipe"):
        shutil.copyfile(FIXTURE_ROOT / f"{task}.py", tasks / f"{task}.py")
    (root / "solver" / "geometry.py").write_text(GEOMETRY_SOURCE)
    (root / "solver" / "runtime.py").write_text(RUNTIME_SOURCE)
    (root / "CONTRACT.md").write_text(CONTRACT)
    (root / "probe.py").write_text(PROBE_SOURCE)
    (root / "scenarios.json").write_text(
        json.dumps(scenario_manifest(), indent=2, sort_keys=True) + "\n"
    )
    (root / "provenance.json").write_text(
        (FIXTURE_ROOT / "provenance.json").read_text()
    )
    (root / "opencode.json").write_text(
        json.dumps(opencode_config(model), indent=2) + "\n"
    )
    (root / "helix.toml").write_text(
        helix_config(model=model, generations=generations)
    )
    (root / ".gitignore").write_text(
        ".helix/\n.helix_artifacts/\n.helix_opencode_state/\n"
        "__pycache__/\n*.pyc\nhelix_batch.json\n"
    )
    rho_demo._git(root, "init", "-b", "main")
    rho_demo._git(root, "add", ".")
    rho_demo._git(root, "commit", "-m", "Seed multi-task CaP-X repository")
    return root


def _load_manifest(root: Path) -> dict[str, Any]:
    payload = json.loads((root / "scenarios.json").read_text())
    if not isinstance(payload, dict):
        raise ValueError("scenarios.json must contain an object")
    return payload


def resolve_scenarios(
    root: Path | str,
    split: str,
    example_ids: Sequence[str],
) -> list[tuple[str, dict[str, Any]]]:
    root = Path(root)
    manifest = _load_manifest(root)
    splits = manifest.get("splits", {})
    names = splits.get(split)
    scenarios = manifest.get("scenarios", {})
    if split not in {"train", "val"} or not isinstance(names, list):
        raise ValueError(f"unknown scenario split: {split}")
    resolved: list[tuple[str, dict[str, Any]]] = []
    for example_id in example_ids:
        if example_id in scenarios:
            scenario_id = example_id
        else:
            try:
                index = int(example_id)
                if index < 0:
                    raise IndexError(index)
                scenario_id = names[index]
            except (ValueError, IndexError, TypeError) as exc:
                raise ValueError(
                    f"invalid {split} example id: {example_id}"
                ) from exc
        scenario = scenarios.get(scenario_id)
        if not isinstance(scenario, dict) or scenario_id not in names:
            raise ValueError(f"scenario {scenario_id!r} is not in split {split}")
        resolved.append((scenario_id, scenario))
    return resolved


def _mock_result(
    root: Path,
    split: str,
    scenario_id: str,
    scenario: Mapping[str, Any],
) -> dict[str, Any]:
    task = str(scenario["task"])
    program = (root / str(scenario["policy_path"])).read_text()
    compact = "".join(program.split())
    if task == "cube_stack":
        passed = (
            "green_pose[2]" in compact
            and "green_pose[0][2]" not in compact
            and "green_pose[0][0]" not in compact
            and "green_pose[0][1]" not in compact
        )
        feedback = (
            "Stack placement used a flat XYZ position."
            if passed
            else "Stack policy raised while indexing a scalar from a flat XYZ pose."
        )
    elif task == "spill_wipe":
        passed = (
            "goto_pose" in program
            and (
                "exceptValueError" in compact
                or "exceptException" in compact
                or "safe_goto" in program
            )
        )
        feedback = (
            "Wipe policy stopped cleanly when the episode terminated."
            if passed
            else "Wipe policy continued issuing blocking poses after termination."
        )
    else:
        raise ValueError(f"unsupported mock task: {task}")
    reward = float(passed)
    return {
        "reward": reward,
        "raw_reward": reward,
        "task_completed": passed,
        "split": split,
        "trial": int(scenario["trial"]),
        "task": task,
        "scenario_id": scenario_id,
        "stdout": "",
        "stderr": "",
        "traceback": "",
        "feedback": f"{MOCK_LABEL}: {feedback}",
        "video": None,
        "timed_out": False,
        "elapsed_seconds": 0.0,
    }


def score_scenario(
    root: Path | str,
    split: str,
    scenario_id: str,
    scenario: Mapping[str, Any],
    *,
    capture: bool = False,
    timeout_seconds: float = 180.0,
) -> dict[str, Any]:
    root = Path(root).resolve()
    if os.environ.get("RHO_MULTITASK_MOCK") == "1":
        return _mock_result(root, split, scenario_id, scenario)
    result = rho_demo.score_candidate(
        root,
        split,
        scenario_id,
        trial=int(scenario["trial"]),
        capture=capture,
        timeout_seconds=timeout_seconds,
        config_path=str(scenario["config_path"]),
        policy_path=str(scenario["policy_path"]),
    )
    result["task"] = str(scenario["task"])
    result["scenario_id"] = scenario_id
    return result


def evaluate_cli() -> int:
    """Evaluate HELIX's positional batch and emit one result per example."""
    root = Path.cwd()
    batch_path = root / "helix_batch.json"
    split = os.environ.get("HELIX_SPLIT", "train")
    manifest = _load_manifest(root)
    default_ids = [str(index) for index, _ in enumerate(manifest["splits"][split])]
    ids = json.loads(batch_path.read_text()) if batch_path.exists() else default_ids
    if not isinstance(ids, list) or not all(isinstance(item, str) for item in ids):
        raise ValueError("helix_batch.json must be a JSON list of strings")
    timeout = float(os.environ.get("RHO_EVAL_TIMEOUT", "180"))
    origin = os.environ.get("RHO_EVAL_ORIGIN", "helix")
    payload: list[list[Any]] = []
    for scenario_id, scenario in resolve_scenarios(root, split, ids):
        evaluation_id = f"{os.getpid()}-{time.time_ns()}-{scenario_id}"
        event = {
            "evaluation_id": evaluation_id,
            "origin": origin,
            "split": split,
            "trial": int(scenario["trial"]),
            "task": str(scenario["task"]),
            "scenario_id": scenario_id,
        }
        rho_demo._append_progress_event(
            {"event": "started", "started_at": time.time(), **event}
        )
        result = score_scenario(
            root,
            split,
            scenario_id,
            scenario,
            timeout_seconds=timeout,
        )
        rho_demo._append_progress_event(
            {
                "event": "completed",
                **event,
                "reward": result["reward"],
                "raw_reward": result.get("raw_reward", result["reward"]),
                "task_completed": result["task_completed"],
                "timed_out": result.get("timed_out", False),
                "elapsed_seconds": result.get("elapsed_seconds"),
            }
        )
        side_info = {
            key: result.get(key)
            for key in (
                "reward",
                "raw_reward",
                "task_completed",
                "split",
                "trial",
                "task",
                "scenario_id",
                "stdout",
                "stderr",
                "traceback",
                "feedback",
                "video",
                "execution_tail",
                "timed_out",
                "elapsed_seconds",
            )
        }
        side_info["scores"] = {
            "completion": float(result["reward"]),
            "raw_reward": float(result.get("raw_reward", result["reward"])),
            "deployable": float(
                not result.get("timed_out")
                and not result.get("stderr")
                and not result.get("traceback")
            ),
        }
        payload.append([float(result["reward"]), side_info])
    print("HELIX_RESULT=" + json.dumps(payload, separators=(",", ":")))
    return 0


def ensure_services(progress: Callable[[str], None] = print) -> list[Any]:
    return rho_demo.ensure_services(progress, model=DEFAULT_MODEL)


def run_helix(
    root: Path | str = DEFAULT_ROOT,
    *,
    generations: int = DEFAULT_GENERATIONS,
    timeout_seconds: float = DEFAULT_TIMEOUT,
    progress: Callable[[str], None] = print,
) -> rho_demo.BoundedRun:
    return rho_demo.run_helix(
        root,
        generations=generations,
        timeout_seconds=timeout_seconds,
        progress=progress,
        merge=True,
    )


def materialize_mock_evolution(
    root: Path | str = DEFAULT_ROOT,
) -> rho_demo.BoundedRun:
    """Create a clearly labeled deterministic two-generation teaching state."""
    root = Path(root)
    helix_root = root / ".helix"
    worktrees = helix_root / "worktrees"
    evaluations = helix_root / "evaluations"
    worktrees.mkdir(parents=True, exist_ok=True)
    evaluations.mkdir(parents=True, exist_ok=True)

    candidates = {
        "g0-s0": {"scores": [0.0, 0.0], "task": None},
        "g1-s1": {"scores": [1.0, 0.0], "task": "cube_stack"},
        "g1-s2": {"scores": [0.0, 1.0], "task": "spill_wipe"},
        "g2-m1": {"scores": [1.0, 1.0], "task": "merge"},
    }
    for candidate_id, candidate in candidates.items():
        destination = worktrees / candidate_id
        shutil.copytree(
            root,
            destination,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(".git", ".helix", "__pycache__"),
        )
        stack = destination / "solver" / "tasks" / "cube_stack.py"
        wipe = destination / "solver" / "tasks" / "spill_wipe.py"
        if candidate_id in {"g1-s1", "g2-m1"}:
            stack.write_text(
                stack.read_text()
                .replace("green_pose[0][2]", "green_pose[2]")
                .replace("green_pose[0][0]", "green_pose[0]")
                .replace("green_pose[0][1]", "green_pose[1]")
            )
        if candidate_id in {"g1-s2", "g2-m1"}:
            wipe.write_text(
                wipe.read_text()
                + "\n# safe_goto handles terminated episodes in the static mock\n"
            )
        if candidate["task"]:
            (destination / ".agent_task_prompt.md").write_text(
                "## Diagnostics\n\n### Example 0\n"
                f"#### task\n{candidate['task']}\n"
                f"#### scenario_id\n{candidate['task']}_train\n"
            )
        side_info = []
        for scenario_id, score in zip(SPLITS["val"], candidate["scores"]):
            task = str(SCENARIOS[scenario_id]["task"])
            side_info.append(
                {
                    "scenario_id": scenario_id,
                    "task": task,
                    "reward": score,
                    "raw_reward": score,
                    "task_completed": bool(score),
                    "elapsed_seconds": 0.0,
                    "feedback": f"{MOCK_LABEL}: deterministic fixture",
                }
            )
        (evaluations / f"{candidate_id}.json").write_text(
            json.dumps(
                {
                    "candidate_id": candidate_id,
                    "instance_scores": {
                        str(index): score
                        for index, score in enumerate(candidate["scores"])
                    },
                    "per_example_side_info": side_info,
                },
                indent=2,
            )
        )

    lineage = [
        {
            "id": "g0-s0",
            "parent": None,
            "parents": [],
            "operation": "seed",
            "generation": 0,
            "files_changed": [],
        },
        {
            "id": "g1-s1",
            "parent": "g0-s0",
            "parents": ["g0-s0"],
            "operation": "mutate",
            "generation": 1,
            "files_changed": ["solver/tasks/cube_stack.py"],
        },
        {
            "id": "g1-s2",
            "parent": "g0-s0",
            "parents": ["g0-s0"],
            "operation": "mutate",
            "generation": 1,
            "files_changed": ["solver/tasks/spill_wipe.py"],
        },
        {
            "id": "g2-m1",
            "parent": "g1-s1",
            "parents": ["g1-s1", "g1-s2"],
            "operation": "merge",
            "generation": 2,
            "files_changed": [
                "solver/tasks/cube_stack.py",
                "solver/tasks/spill_wipe.py",
            ],
        },
    ]
    (helix_root / "lineage.json").write_text(json.dumps(lineage, indent=2))
    (helix_root / "state.json").write_text(
        json.dumps(
            {
                "generation": 2,
                "frontier": list(candidates),
                "instance_scores": {
                    candidate_id: {
                        str(index): score
                        for index, score in enumerate(candidate["scores"])
                    }
                    for candidate_id, candidate in candidates.items()
                },
                "active_frontier": {
                    "0": ["g1-s1", "g2-m1"],
                    "1": ["g1-s2", "g2-m1"],
                },
                "frontier_type": "instance",
                "budget": {"evaluations": 20},
                "merge_counter": 1,
                "merge_attempted_pairs": [["g1-s1", "g1-s2"]],
                "merge_description_triplets": [
                    ["g1-s1", "g1-s2", "4d6f636b4d65726765436f6d6d69745368613031"]
                ],
            },
            indent=2,
        )
    )
    return rho_demo.BoundedRun(
        returncode=0,
        timed_out=False,
        stdout=f"{MOCK_LABEL}: synthetic specialist and merge state",
        elapsed_seconds=0.0,
    )


def frontier_summary(root: Path | str = DEFAULT_ROOT) -> dict[str, Any]:
    root = Path(root)
    state_path = root / ".helix" / "state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    manifest = _load_manifest(root)
    val_ids = list(manifest["splits"]["val"])
    active = state.get("active_frontier", {})
    instance_scores = state.get("instance_scores", {})
    retained_ids = {
        str(candidate_id)
        for winners in active.values()
        for candidate_id in winners
    }
    candidates: dict[str, dict[str, Any]] = {}
    for candidate_id, scores in instance_scores.items():
        mapped_scores = {
            val_ids[int(example_id)] if str(example_id).isdigit() else str(example_id): score
            for example_id, score in scores.items()
            if not str(example_id).isdigit() or int(example_id) < len(val_ids)
        }
        candidates[candidate_id] = {
            "scores": mapped_scores,
            "wins": [
                val_ids[int(example_id)]
                if str(example_id).isdigit() and int(example_id) < len(val_ids)
                else str(example_id)
                for example_id, winners in active.items()
                if candidate_id in winners
            ],
            "frontier": candidate_id in retained_ids,
        }
    lineage = candidate_lineage(root)
    merge_ancestry = [
        {
            "candidate": item["id"],
            "parents": list(item.get("parents") or []),
        }
        for item in lineage
        if item.get("operation") == "merge"
    ]
    return {
        "generation": state.get("generation", 0),
        "budget": state.get("budget", {}),
        "frontier_type": state.get("frontier_type"),
        "active_frontier": active,
        "candidates": candidates,
        "merge_counter": state.get("merge_counter", 0),
        "merge_attempted_pairs": state.get("merge_attempted_pairs", []),
        # HELIX stores [parent_a, parent_b, merged_git_sha] here to avoid
        # repeating an equivalent merge. Candidate ancestry comes from
        # lineage.json and is reported separately below.
        "merge_output_dedup_triplets": state.get(
            "merge_description_triplets", []
        ),
        "merge_ancestry": merge_ancestry,
        "lineage": lineage,
    }


def candidate_lineage(root: Path | str = DEFAULT_ROOT) -> list[dict[str, Any]]:
    """Join HELIX lineage, prompts, diffs, gates, and validation vectors."""
    root = Path(root)
    helix_root = root / ".helix"
    lineage_path = helix_root / "lineage.json"
    if not lineage_path.exists():
        return []
    records = json.loads(lineage_path.read_text())
    output: list[dict[str, Any]] = []
    for record in records:
        candidate_id = str(record["id"])
        parent_id = record.get("parent")
        candidate_root = helix_root / "worktrees" / candidate_id
        parent_root = (
            helix_root / "worktrees" / str(parent_id)
            if parent_id
            else None
        )
        changed_files = list(record.get("files_changed") or [])
        if not changed_files and parent_root and parent_root.exists():
            diff = rho_demo.source_diff(parent_root, candidate_root)
            changed_files = sorted(
                {
                    line.removeprefix("+++ best/")
                    for line in diff.splitlines()
                    if line.startswith("+++ best/")
                    and not line.endswith("/dev/null")
                }
            )
        prompt_path = candidate_root / ".agent_task_prompt.md"
        prompt = prompt_path.read_text() if prompt_path.exists() else ""
        task_match = re.search(r"#### task\s*\n([^\n]+)", prompt)
        scenario_match = re.search(r"#### scenario_id\s*\n([^\n]+)", prompt)
        evaluation_path = helix_root / "evaluations" / f"{candidate_id}.json"
        evaluation = (
            json.loads(evaluation_path.read_text())
            if evaluation_path.exists()
            else None
        )
        attempt_path = helix_root / "attempts" / f"{candidate_id}.json"
        attempt = (
            json.loads(attempt_path.read_text())
            if attempt_path.exists()
            else {}
        )
        attempt_side_info = attempt.get("per_example_side_info", [])
        sampled_side_info = attempt_side_info[0] if attempt_side_info else {}
        backend_path = candidate_root / ".helix_backend_result.json"
        backend = (
            json.loads(backend_path.read_text()) if backend_path.exists() else {}
        )
        events = backend.get("parsed", {}).get("events", [])
        timestamps = [
            float(event["timestamp"]) / 1000.0
            for event in events
            if event.get("timestamp") is not None
        ]
        prompt_wait_seconds = 0.0
        text_generation_seconds = 0.0
        last_step_start: float | None = None
        for event in events:
            if event.get("type") == "step_start" and event.get("timestamp"):
                last_step_start = float(event["timestamp"]) / 1000.0
            if event.get("type") != "text":
                continue
            timing = event.get("part", {}).get("time", {})
            start = timing.get("start")
            end = timing.get("end")
            if start is not None and last_step_start is not None:
                prompt_wait_seconds += max(0.0, float(start) / 1000.0 - last_step_start)
            if start is not None and end is not None:
                text_generation_seconds += max(
                    0.0, (float(end) - float(start)) / 1000.0
                )
            last_step_start = None
        validation_vector: dict[str, float] = {}
        if evaluation:
            for side_info in evaluation.get("per_example_side_info", []):
                key = str(
                    side_info.get("scenario_id")
                    or side_info.get("task")
                    or side_info.get("trial")
                )
                validation_vector[key] = float(side_info.get("reward", 0.0))
        output.append(
            {
                **record,
                "changed_files": changed_files,
                "sampled_train_task": (
                    task_match.group(1).strip()
                    if task_match
                    else sampled_side_info.get("task")
                ),
                "sampled_train_scenario": (
                    scenario_match.group(1).strip()
                    if scenario_match
                    else sampled_side_info.get("scenario_id")
                ),
                "gate_result": (
                    "seed"
                    if record.get("operation") == "seed"
                    else (
                        (
                            "passed_merge_validation_gate"
                            if evaluation is not None
                            else "rejected_merge"
                        )
                        if record.get("operation") == "merge"
                        else (
                            "passed_strict_train_gate"
                            if evaluation is not None
                            else (
                                "rejected_minibatch_gate"
                                if attempt.get("attempt", {}).get("reason")
                                == "minibatch_gate"
                                else "failed_before_full_validation"
                            )
                        )
                    )
                ),
                "validation_vector": validation_vector,
                "agent_metrics": {
                    "model": backend.get("command", "").split("--model ", 1)[-1]
                    .split(" ", 1)[0]
                    .strip("'\""),
                    "total_seconds": (
                        max(timestamps) - min(timestamps) if timestamps else 0.0
                    ),
                    "prompt_wait_seconds": prompt_wait_seconds,
                    "text_generation_seconds": text_generation_seconds,
                    "usage": backend.get("usage", {}),
                },
                "validation_simulator_seconds": sum(
                    float(item.get("elapsed_seconds") or 0.0)
                    for item in (
                        evaluation.get("per_example_side_info", [])
                        if evaluation
                        else []
                    )
                ),
            }
        )
    return output


def evolution_lesson(summary: Mapping[str, Any]) -> dict[str, Any]:
    """Extract the specialist/frontier/merge teaching claims from a run."""
    candidates = summary.get("candidates", {})
    stack_specialists: list[str] = []
    wipe_specialists: list[str] = []
    broad_candidates: list[str] = []
    covered_difficult_keys: set[str] = set()
    for candidate_id, candidate in candidates.items():
        scores = candidate.get("scores", {})
        stack = float(scores.get("stack_val", 0.0))
        wipe = float(scores.get("wipe_val", 0.0))
        if candidate.get("frontier"):
            if "stack_val" in candidate.get("wins", []) and stack > 0.0:
                covered_difficult_keys.add("stack_val")
            if "wipe_val" in candidate.get("wins", []) and wipe > 0.0:
                covered_difficult_keys.add("wipe_val")
        if stack > 0.0 and wipe <= 0.0:
            stack_specialists.append(candidate_id)
        if wipe > 0.0 and stack <= 0.0:
            wipe_specialists.append(candidate_id)
        if stack > 0.0 and wipe > 0.0:
            broad_candidates.append(candidate_id)
    return {
        "multi_key_frontier": len(covered_difficult_keys) == 2,
        "covered_difficult_keys": sorted(covered_difficult_keys),
        "specialist_pair": bool(stack_specialists and wipe_specialists),
        "stack_specialists": stack_specialists,
        "wipe_specialists": wipe_specialists,
        "broad_candidates": broad_candidates,
        "merge_attempted": bool(summary.get("merge_attempted_pairs")),
        "merge_ancestry": summary.get("merge_ancestry", []),
    }


def hidden_rollouts(
    root: Path | str,
    *,
    trials: Mapping[str, int | Sequence[int]],
    capture: bool = True,
) -> list[dict[str, Any]]:
    """Run frozen policies on caller-selected trials never used by HELIX."""
    root = Path(root)
    results = []
    for task, task_trials in trials.items():
        if isinstance(task_trials, int):
            normalized_trials = [task_trials]
        elif isinstance(task_trials, Sequence) and not isinstance(task_trials, (str, bytes)):
            normalized_trials = [int(trial) for trial in task_trials]
        else:
            raise TypeError(f"Hidden trials for {task!r} must be an integer or sequence of integers")
        if not normalized_trials:
            raise ValueError(f"Hidden trials for {task!r} cannot be empty")
        if len(set(normalized_trials)) != len(normalized_trials):
            raise ValueError(f"Hidden trials for {task!r} must be unique")

        for trial in normalized_trials:
            scenario = {
                "task": task,
                "trial": trial,
                "policy_path": f"solver/tasks/{task}.py",
                "config_path": CONFIGS[task],
            }
            result = score_scenario(
                root,
                "val",
                f"hidden_{task}_{trial}",
                scenario,
                capture=capture,
            )
            results.append(result)
    return results


def summarize_rollouts(results: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Aggregate repeated rollout evidence without hiding individual trials."""
    buckets: dict[str, list[Mapping[str, Any]]] = {}
    for result in results:
        task = str(result.get("task") or "")
        if not task:
            raise ValueError("Every hidden rollout must include its task")
        buckets.setdefault(task, []).append(result)

    summary: dict[str, dict[str, Any]] = {}
    for task, task_results in buckets.items():
        count = len(task_results)
        completed = sum(bool(result.get("task_completed")) for result in task_results)
        rewards = [float(result.get("reward") or 0.0) for result in task_results]
        raw_rewards = [float(result.get("raw_reward") or 0.0) for result in task_results]
        execution_failures = sum(
            bool(result.get("stderr") or result.get("traceback") or result.get("timed_out"))
            for result in task_results
        )
        summary[task] = {
            "rollouts": count,
            "trials": [int(result["trial"]) for result in task_results],
            "completed": completed,
            "completion_rate": completed / count,
            "mean_reward": sum(rewards) / count,
            "mean_raw_reward": sum(raw_rewards) / count,
            "execution_failures": execution_failures,
        }
    return summary


def deployment_success_criterion(
    before: Mapping[str, Mapping[str, Any]],
    after: Mapping[str, Mapping[str, Any]],
    *,
    required_tasks: Sequence[str] = tuple(CONFIGS),
    minimum_hard_reward_gain: float = 0.05,
) -> dict[str, Any]:
    """Compare repeated before/after rollouts across required evolved tasks."""
    tasks = tuple(str(task) for task in required_tasks)
    if not tasks:
        raise ValueError("At least one evolved task is required")
    if len(set(tasks)) != len(tasks):
        raise ValueError("Required evolved tasks must be unique")
    if minimum_hard_reward_gain < 0.0:
        raise ValueError("minimum_hard_reward_gain must be non-negative")

    missing = [task for task in tasks if task not in before or task not in after]
    if missing:
        raise ValueError(
            f"Missing deployment rollout summaries for: {', '.join(missing)}"
        )

    rollout_counts_before = {
        task: int(before[task]["rollouts"]) for task in tasks
    }
    rollout_counts_after = {
        task: int(after[task]["rollouts"]) for task in tasks
    }
    nonpositive = [
        task
        for task in tasks
        if rollout_counts_before[task] <= 0 or rollout_counts_after[task] <= 0
    ]
    if nonpositive:
        raise ValueError(
            "Deployment rollout counts must be positive for: "
            + ", ".join(nonpositive)
        )
    mismatched = [
        task
        for task in tasks
        if rollout_counts_before[task] != rollout_counts_after[task]
    ]
    if mismatched:
        raise ValueError(
            "Before/after rollout counts must match for: " + ", ".join(mismatched)
        )

    rollouts = sum(rollout_counts_before.values())
    completed_before = sum(int(before[task]["completed"]) for task in tasks)
    completed_after = sum(int(after[task]["completed"]) for task in tasks)
    mean_reward_before = sum(
        float(before[task]["mean_reward"]) * rollout_counts_before[task]
        for task in tasks
    ) / rollouts
    mean_reward_after = sum(
        float(after[task]["mean_reward"]) * rollout_counts_after[task]
        for task in tasks
    ) / rollouts
    completion_improved = completed_after > completed_before
    reward_improved = (
        completed_after == completed_before
        and mean_reward_after >= mean_reward_before + minimum_hard_reward_gain
    )
    deployment_improved = completion_improved or reward_improved

    return {
        "required_tasks": list(tasks),
        "rollouts": rollouts,
        "completed_before": completed_before,
        "completed_after": completed_after,
        "completion_rate_before": completed_before / rollouts,
        "completion_rate_after": completed_after / rollouts,
        "mean_reward_before": mean_reward_before,
        "mean_reward_after": mean_reward_after,
        "minimum_hard_reward_gain": minimum_hard_reward_gain,
        "completion_improved": completion_improved,
        "reward_improved": reward_improved,
        "deployment_improved": deployment_improved,
        "met": deployment_improved,
    }


def live_smoke() -> int:
    """Run one real validation scenario from a spawn-safe module entrypoint."""
    root = Path("/tmp/rho_multitask_smoke/candidate")
    try:
        ensure_services()
        prepare_workshop(root)
        scenario_id, scenario = resolve_scenarios(root, "val", ["0"])[0]
        result = score_scenario(
            root,
            "val",
            scenario_id,
            scenario,
            timeout_seconds=180.0,
        )
        print(json.dumps(result, indent=2))
        return int(
            result.get("timed_out")
            or result.get("raw_reward") is None
            or bool(result.get("traceback"))
        )
    finally:
        rho_demo.stop_owned_services()


def _main(argv: Sequence[str]) -> int:
    command = argv[0] if argv else ""
    if command == "prepare":
        print(prepare_workshop())
        return 0
    if command == "evaluate":
        return evaluate_cli()
    if command == "run":
        result = run_helix()
        print(json.dumps(rho_demo.asdict(result), indent=2))
        return result.returncode
    if command == "frontier":
        print(json.dumps(frontier_summary(), indent=2))
        return 0
    if command == "live-smoke":
        return live_smoke()
    print(
        "usage: rho_multitask_demo.py "
        "{prepare|evaluate|run|frontier|live-smoke}"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
