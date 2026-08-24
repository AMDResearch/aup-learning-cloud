#!/usr/bin/env bash
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
set -euo pipefail

CAPX_PY="${CAPX_VENV:-/opt/capx-venv}/bin/python"
export PYTHONPATH="/ryzers:/ryzers/notebooks${PYTHONPATH:+:${PYTHONPATH}}"

echo "================ Multi-task RHO static harness ================"
RHO_MULTITASK_MOCK=1 "${CAPX_PY}" - <<'PY'
import json
import hashlib
import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path

from helix.config import load_config
import rho_demo
import rho_multitask_demo as demo

override_env = os.environ.copy()
override_env.pop("RHO_MULTITASK_MODEL", None)
override_env["RHO_MODEL"] = "rho-model-override"
override = subprocess.run(
    [
        sys.executable,
        "-c",
        "import rho_multitask_demo as demo; print(demo.DEFAULT_MODEL)",
    ],
    env=override_env,
    check=True,
    capture_output=True,
    text=True,
)
assert override.stdout.strip() == "rho-model-override"


with tempfile.TemporaryDirectory(prefix="rho-multitask-", dir="/tmp") as temporary:
    root = demo.prepare_workshop(Path(temporary) / "candidate")
    manifest = json.loads((root / "scenarios.json").read_text())
    assert manifest["splits"] == {
        "train": ["stack_train", "wipe_train"],
        "val": ["stack_val", "wipe_val", "lift_guard_val"],
    }
    os.environ["RHO_TRIAL_ID"] = "2"
    try:
        assert rho_demo._trial_id(root, "val", "stack_val") == 2
    finally:
        os.environ.pop("RHO_TRIAL_ID")
    provenance = json.loads((root / "provenance.json").read_text())
    assert provenance["seed_model"] == "Gemma-4-E4B-it-GGUF"
    for policy in provenance["policies"].values():
        assert len(policy["source_policy_sha256"]) == 64
        assert policy["source_prompt"]
        assert policy["source_trial"] == 1
        assert policy["source_git_commit"]
    assert demo.resolve_scenarios(root, "train", ["0", "1"])[0][0] == "stack_train"
    assert demo.resolve_scenarios(root, "val", ["2"])[0][0] == "lift_guard_val"
    for invalid_id in ("stack_val", "-1", "2"):
        try:
            demo.resolve_scenarios(root, "train", [invalid_id])
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid train scenario was accepted: {invalid_id}")
    shuffled = list(manifest["splits"]["train"])
    random.Random(29).shuffle(shuffled)
    assert shuffled == ["wipe_train", "stack_train"]

    config = load_config(root / "helix.toml")
    assert config.dataset.train_size == 2
    assert config.dataset.val_size == 3
    assert config.evolution.max_generations == 2
    assert config.evolution.perfect_score_threshold == 1.1
    assert config.evolution.minibatch_size == 1
    assert config.evolution.num_parallel_proposals == 2
    assert config.evolution.max_workers == 1
    assert config.evolution.merge_enabled is True
    assert config.evolution.max_merge_invocations == 2
    assert config.evolution.merge_val_overlap_floor == 1
    assert config.evolution.merge_subsample_size == 3
    assert config.evolution.frontier_type == "instance"
    assert config.evolution.acceptance_criterion == "strict_improvement"

    opencode = json.loads((root / "opencode.json").read_text())
    assert opencode["model"] == f"lemonade/{demo.opencode_model_id()}"
    assert opencode["provider"]["lemonade"]["models"][
        demo.opencode_model_id()
    ]["tool_call"] is True
    assert opencode["agent"]["build"]["steps"] == 24
    assert config.agent.model == f"lemonade/{demo.opencode_model_id()}"
    assert config.agent.max_turns == 24
    assert opencode["permission"]["edit"]["solver/**"] == "allow"
    assert opencode["permission"]["edit"]["*"] == "deny"
    assert "change green_pose" not in demo.BACKGROUND
    assert "except ValueError" not in demo.BACKGROUND

    protected = [
        "probe.py",
        "helix.toml",
        "opencode.json",
        "CONTRACT.md",
        "scenarios.json",
        "provenance.json",
    ]
    protected_before = {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in protected
    }
    (root / "helix_batch.json").write_text('["0","1"]\n')
    env = os.environ.copy()
    env.update(RHO_MULTITASK_MOCK="1", HELIX_SPLIT="train")
    done = subprocess.run(
        [sys.executable, str(Path(demo.__file__)), "evaluate"],
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(done.stdout.split("HELIX_RESULT=", 1)[1])
    assert [entry[1]["task"] for entry in payload] == ["cube_stack", "spill_wipe"]
    assert [entry[0] for entry in payload] == [0.0, 0.0]
    assert set(payload[0][1]["scores"]) == {"completion", "raw_reward", "deployable"}
    assert demo.MOCK_LABEL in payload[0][1]["feedback"]
    assert protected_before == {
        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
        for name in protected
    }

    stack = root / "solver" / "tasks" / "cube_stack.py"
    stack.write_text(
        stack.read_text()
        .replace("green_pose[0][2]", "green_pose[2]")
        .replace("green_pose[0][0]", "green_pose[0]")
        .replace("green_pose[0][1]", "green_pose[1]")
    )
    wipe = root / "solver" / "tasks" / "spill_wipe.py"
    wipe.write_text(wipe.read_text() + "\n# safe_goto handles terminated episodes\n")
    train_results = [
        demo.score_scenario(root, "train", scenario_id, scenario)
        for scenario_id, scenario in demo.resolve_scenarios(root, "train", ["0", "1"])
    ]
    assert [result["reward"] for result in train_results] == [1.0, 1.0]
    _, lift = demo.resolve_scenarios(root, "val", ["2"])[0]
    assert demo.score_scenario(root, "val", "lift_guard_val", lift)["reward"] == 1.0

    root = demo.prepare_workshop(root)
    mocked = demo.materialize_mock_evolution(root)
    assert demo.MOCK_LABEL in mocked.stdout
    summary = demo.frontier_summary(root)
    assert summary["generation"] == 2
    assert summary["candidates"]["g1-s1"]["wins"] == [
        "stack_val",
        "lift_guard_val",
    ]
    assert summary["candidates"]["g1-s2"]["wins"] == [
        "wipe_val",
        "lift_guard_val",
    ]
    assert summary["candidates"]["g0-s0"]["frontier"] is True
    assert summary["candidates"]["g2-m1"]["frontier"] is True
    assert summary["merge_counter"] == 1
    lesson = demo.evolution_lesson(summary)
    assert lesson["multi_key_frontier"] is True
    assert lesson["covered_difficult_keys"] == ["stack_val", "wipe_val"]
    assert lesson["specialist_pair"] is True
    assert lesson["stack_specialists"] == ["g1-s1"]
    assert lesson["wipe_specialists"] == ["g1-s2"]
    assert lesson["broad_candidates"] == ["g2-m1"]
    assert lesson["merge_attempted"] is True
    assert summary["merge_ancestry"] == [
        {"candidate": "g2-m1", "parents": ["g1-s1", "g1-s2"]}
    ]
    assert summary["merge_output_dedup_triplets"] == [
        ["g1-s1", "g1-s2", "4d6f636b4d65726765436f6d6d69745368613031"]
    ]
    lineage = {item["id"]: item for item in summary["lineage"]}
    assert lineage["g1-s1"]["changed_files"] == ["solver/tasks/cube_stack.py"]
    assert lineage["g1-s2"]["changed_files"] == ["solver/tasks/spill_wipe.py"]
    assert lineage["g2-m1"]["parents"] == ["g1-s1", "g1-s2"]
    assert all(
        lineage[candidate_id]["gate_result"] == "passed_strict_train_gate"
        for candidate_id in ("g1-s1", "g1-s2")
    )
    assert lineage["g2-m1"]["gate_result"] == "passed_merge_validation_gate"
    assert "cube_stack.py" in rho_demo.source_diff(
        root / ".helix" / "worktrees" / "g0-s0",
        root / ".helix" / "worktrees" / "g1-s1",
    )
    assert "spill_wipe.py" in rho_demo.source_diff(
        root / ".helix" / "worktrees" / "g0-s0",
        root / ".helix" / "worktrees" / "g1-s2",
    )

    captured = {}
    original_run_bounded = rho_demo.run_bounded

    def fake_run_bounded(command, **kwargs):
        captured["command"] = command
        return rho_demo.BoundedRun(0, False, "", 0.1)

    rho_demo.run_bounded = fake_run_bounded
    try:
        run = demo.run_helix(root, progress=lambda _: None)
    finally:
        rho_demo.run_bounded = original_run_bounded
    assert run.returncode == 0
    assert "--no-merge" not in captured["command"]
    assert captured["command"][-2:] == ["--generations", "2"]

    hidden_calls = []
    original_score_scenario = demo.score_scenario

    def fake_score_scenario(candidate_root, split, scenario_id, scenario, **kwargs):
        hidden_calls.append((scenario_id, scenario["task"], scenario["trial"], kwargs["capture"]))
        return {
            "scenario_id": scenario_id,
            "task": scenario["task"],
            "trial": scenario["trial"],
            "reward": 1.0,
            "raw_reward": 1.0,
            "task_completed": True,
            "stderr": "",
            "traceback": "",
            "timed_out": False,
        }

    demo.score_scenario = fake_score_scenario
    try:
        hidden = demo.hidden_rollouts(
            root,
            trials={
                "cube_stack": [100, 101, 102, 103, 104],
                "spill_wipe": [200, 201, 202, 203, 204],
                "cube_lift": [300, 301, 302, 303, 304],
            },
            capture=True,
        )
    finally:
        demo.score_scenario = original_score_scenario
    assert len(hidden) == 15
    assert len(hidden_calls) == 15
    assert all(call[3] is True for call in hidden_calls)
    assert hidden_calls[0][:3] == ("hidden_cube_stack_100", "cube_stack", 100)
    assert hidden_calls[-1][:3] == ("hidden_cube_lift_304", "cube_lift", 304)

    def rollout(task, trial, reward, completed):
        return {
            "task": task,
            "trial": trial,
            "reward": reward,
            "raw_reward": reward,
            "task_completed": completed,
            "stderr": "",
            "traceback": "",
            "timed_out": False,
        }

    before_rollouts = [
        *[rollout("cube_stack", trial, 0.0, False) for trial in range(100, 105)],
        *[rollout("spill_wipe", trial, 1.0, True) for trial in range(200, 205)],
        *[rollout("cube_lift", trial, 1.0, True) for trial in range(300, 305)],
    ]
    after_rollouts = [
        rollout("cube_stack", 100, 1.0, True),
        *[rollout("cube_stack", trial, 0.0, False) for trial in range(101, 105)],
        *[rollout("spill_wipe", trial, 1.0, True) for trial in range(200, 205)],
        *[rollout("cube_lift", trial, 1.0, True) for trial in range(300, 304)],
        rollout("cube_lift", 304, 0.5, False),
    ]
    before_summary = demo.summarize_rollouts(before_rollouts)
    after_summary = demo.summarize_rollouts(after_rollouts)
    assert before_summary["cube_lift"]["rollouts"] == 5
    assert after_summary["cube_lift"]["completion_rate"] == 0.8
    criterion = demo.hidden_success_criterion(
        before_summary,
        after_summary,
        lift_policy_unchanged=True,
    )
    assert criterion["hard_task_completed_before"] == 5
    assert criterion["hard_task_completed_after"] == 6
    assert criterion["hard_task_improved"] is True
    assert criterion["lift_guard_preserved"] is True
    assert criterion["met"] is True

    noisy_rollouts = [
        *[rollout("cube_stack", trial, 0.001, False) for trial in range(100, 105)],
        *[rollout("spill_wipe", trial, 1.0, True) for trial in range(200, 205)],
        *[rollout("cube_lift", trial, 1.0, True) for trial in range(300, 305)],
    ]
    noisy_criterion = demo.hidden_success_criterion(
        before_summary,
        demo.summarize_rollouts(noisy_rollouts),
        lift_policy_unchanged=True,
    )
    assert noisy_criterion["hard_task_improved"] is False
    assert noisy_criterion["met"] is False

print("multi-task manifest, evaluator, frontier, and merge plumbing OK")
PY

echo "================ Multi-task RHO tests PASSED ================"
