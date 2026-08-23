#!/usr/bin/env bash
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Static RHO harness checks always run. Set RHO_RUN_LIVE=1 for one real local
# Gemma/OpenCode/HELIX mutation against the CaP-X simulator.
set -euo pipefail

CAPX_PY="${CAPX_VENV:-/opt/capx-venv}/bin/python"
HELIX_REF="29cfa6e5eae902f6bc6d2113e51499e92c6109ee"
OPENCODE_VERSION="1.18.18"

export PYTHONPATH="/ryzers${PYTHONPATH:+:${PYTHONPATH}}"
export CAPX_ROOT="${CAPX_ROOT:-/ryzers/cap-x}"
export HF_HOME="${CAPX_CACHE:-/opt/capx-cache}"
export MUJOCO_GL=egl
export PYOPENGL_PLATFORM=egl

cd /ryzers

echo "================ RHO toolchain ================"
test "$(git -C /ryzers/helix rev-parse HEAD)" = "${HELIX_REF}"
"${CAPX_PY}" -c "import capx, helix, torch; assert torch.version.hip"
"${CAPX_PY}" -c "from helix import __version__; assert __version__ == '0.2.1', __version__"
"${CAPX_VENV:-/opt/capx-venv}/bin/helix" --version
test "$(opencode --version)" = "${OPENCODE_VERSION}"
node --version

echo "================ RHO static harness ================"
RHO_MOCK_EVAL=1 "${CAPX_PY}" - <<'PY'
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import rho_demo
from helix.config import load_config

root = rho_demo.prepare_workshop(
    support_files={"solver/strategy.py": "CLEARANCE = 0.1\n"}
)
required = {
    "solver/__init__.py",
    "solver/geometry.py",
    "solver/program.py",
    "solver/policy.py",
    "solver/strategy.py",
    "API_REFERENCE.md",
    "probe.py",
    "opencode.json",
    "helix.toml",
    "provenance.json",
}
assert required <= {
    str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()
}
assert (root / ".git").is_dir()
assert (root / "solver" / "program.py").read_text() == rho_demo.DEFAULT_PROGRAM
assert "program.py" in (root / "solver" / "policy.py").read_text()
assert (root / "solver" / "strategy.py").read_text() == "CLEARANCE = 0.1\n"

provenance = json.loads((root / "provenance.json").read_text())
assert provenance["source"] == "recorded_capx_generation"
assert provenance["artifact_trial"] == provenance["training_trial"] == 1
assert provenance["heldout_trial"] == 2
assert provenance["recorded_task_completed"] is False
assert not hasattr(rho_demo, "SEED_GEOMETRY")
assert not hasattr(rho_demo, "FROZEN_GEOMETRY")
assert not hasattr(rho_demo, "FALLBACK_ROOT")

config = load_config(root / "helix.toml")
assert config.agent.backend == "opencode"
assert config.agent.model == f"lemonade/{rho_demo.MODEL}"
assert config.dataset.train_size == config.dataset.val_size == 1
assert config.evolution.max_generations == 1
assert config.evolution.minibatch_size == 1
assert config.evolution.max_workers == 1
assert config.evolution.merge_enabled is False
assert config.evolution.acceptance_criterion == "strict_improvement"
assert set(config.evaluator.protected_files) >= {
    "probe.py",
    "helix.toml",
    "opencode.json",
    "provenance.json",
}
assert "max_generations = 2" in rho_demo.helix_config(2)
four_generation_config = rho_demo.helix_config(4)
assert "max_generations = 4" in four_generation_config
assert "max_evaluations = 14" in four_generation_config
custom_config = rho_demo.helix_config(
    objective="Repair another task.",
    background="Edit solver/program.py first.",
)
assert 'objective = """Repair another task."""' in custom_config
assert 'background = """Edit solver/program.py first."""' in custom_config
assert '"RHO_CONFIG_PATH"' in custom_config
try:
    rho_demo.helix_config(5)
except ValueError:
    pass
else:
    raise AssertionError("more than four generations must be rejected")

opencode = json.loads((root / "opencode.json").read_text())
permissions = opencode["permission"]
assert permissions["external_directory"] == "deny"
assert permissions["edit"]["*"] == "deny"
assert permissions["edit"]["solver/**"] == "allow"
assert permissions["edit"]["**/solver/**"] == "allow"
assert permissions["bash"]["*"] == "deny"
assert list(permissions["edit"])[0] == "*"
assert list(permissions["bash"])[0] == "*"

# The default authentic recording deterministically reproduces its scalar-index
# error without importing CaP-X.
before = rho_demo.score_candidate(root, "train", timeout_seconds=5)
assert before["reward"] == 0.0 and before["task_completed"] is False
assert before["trial"] == 1
assert before["elapsed_seconds"] >= 0.0
assert "green_pose[0]" in before["traceback"]

(root / "helix_batch.json").write_text('["0"]\n')
env = os.environ.copy()
env.update(RHO_MOCK_EVAL="1", HELIX_SPLIT="train")
done = subprocess.run(
    [sys.executable, str(Path(rho_demo.__file__)), "evaluate"],
    cwd=root,
    env=env,
    check=True,
    capture_output=True,
    text=True,
)
lines = done.stdout.splitlines()
assert len(lines) == 1 and lines[0].startswith("HELIX_RESULT="), done.stdout
payload = json.loads(lines[0].split("=", 1)[1])
assert payload[0][0] == 0.0
assert payload[0][1]["task_completed"] is False
assert payload[0][1]["trial"] == 1
assert {
    "reward",
    "stdout",
    "stderr",
    "traceback",
    "feedback",
    "video",
    "scores",
} <= payload[0][1].keys()

program_path = root / "solver" / "program.py"
corrected = program_path.read_text()
corrected = corrected.replace("green_pose[0][2]", "green_pose[2]")
corrected = corrected.replace("green_pose[0][0]", "green_pose[0]")
corrected = corrected.replace("green_pose[0][1]", "green_pose[1]")
program_path.write_text(corrected)
after = rho_demo.score_candidate(root, "val", timeout_seconds=5)
assert after["reward"] == 1.0 and after["task_completed"]
assert after["trial"] == 2
provenance_before_override = (root / "provenance.json").read_text()
random_trial = rho_demo.score_candidate(
    root, "val", trial=7331, timeout_seconds=5
)
assert random_trial["reward"] == 1.0 and random_trial["trial"] == 7331
assert (root / "provenance.json").read_text() == provenance_before_override

# A real CaP-X trial directory is accepted as input, copied byte-for-byte, and
# fixes the training trial to the artifact while preserving caller metadata.
with tempfile.TemporaryDirectory(prefix="rho-artifact-") as temporary:
    temporary = Path(temporary)
    artifact = temporary / "trial_07_sandboxrc_1_reward_0.000_taskcompleted_0"
    artifact.mkdir()
    artifact_code = "# authentic generated bytes\nprint('artifact')\n"
    (artifact / "code.py").write_text(artifact_code)
    artifact_root = temporary / "candidate"
    rho_demo.prepare_workshop(
        artifact_root,
        artifact=artifact,
        provenance={"run": "workshop-recording"},
        heldout_trial=9,
    )
    assert (artifact_root / "solver" / "program.py").read_text() == artifact_code
    artifact_provenance = json.loads(
        (artifact_root / "provenance.json").read_text()
    )
    assert artifact_provenance["training_trial"] == 7
    assert artifact_provenance["heldout_trial"] == 9
    assert artifact_provenance["run"] == "workshop-recording"

bounded = rho_demo.run_bounded(
    [sys.executable, str(Path(rho_demo.__file__)), "_sleep", "2"],
    cwd=root,
    timeout_seconds=0.2,
)
assert bounded.timed_out and bounded.returncode == 124

proof = json.loads(
    Path(
        "/ryzers/notebooks/fixtures/rho_qwen_cube_stack_repair_proof.json"
    ).read_text()
)
assert proof["rho"]["accepted"] is True
assert proof["rho"]["generations"] == 1
assert proof["evaluation"]["before"]["heldout"]["task_completed"] is False
assert proof["evaluation"]["after"]["train"]["task_completed"] is True
assert proof["evaluation"]["after"]["heldout"]["task_completed"] is True
generalization = json.loads(
    Path(
        "/ryzers/notebooks/fixtures/capx_rho_generalization_5_trials.json"
    ).read_text()
)
results = generalization["results"]
assert results["cube_stack_before_rho"]["completed"] == 0
assert results["cube_stack_after_rho"]["completed"] == 3
assert results["cube_lift_fixed_policy"]["completed"] == 4
assert results["spill_wipe_fixed_policy"]["completed"] == 1
assert results["cube_restack_before_rho"]["execution_failures"] == 5
assert results["cube_restack_after_rho"]["execution_failures"] == 0
assert results["cube_restack_after_rho"]["completed"] == 0
print("artifact scaffold, mock repair, HELIX_RESULT, permissions, and timeout OK")
PY

echo "================ CaP-X to RHO story scaffold ================"
STORY_TMP="/tmp/capx-rho-story-test"
rm -rf "${STORY_TMP}"
"${CAPX_PY}" /ryzers/notebooks/capx_story.py \
  --source recorded \
  --scenario cube_stack \
  --output-dir "${STORY_TMP}/capx"
"${CAPX_PY}" /ryzers/notebooks/workshop_story.py \
  --source recorded \
  --mock-rho \
  --prepare-only \
  --output-dir "${STORY_TMP}/story"
"${CAPX_PY}" - <<'PY'
import json
from pathlib import Path

report = json.loads(
    Path("/tmp/capx-rho-story-test/story/story_report.json").read_text()
)
assert report["source"] == "recorded"
assert report["capx"]["success"] is None
failure = report["capx"]["failure"]
assert failure["source"] == "recorded"
assert failure["trial"] == 1
assert failure["evaluation"]["reward"] == 0.7243017351331602
assert failure["evaluation"]["task_completed"] is False
assert report["rho"]["seed"]["train"]["reward"] == 0.0
assert report["rho"]["seed"]["train"]["trial"] == 1
assert report["rho"]["seed"]["heldout"]["trial"] == 2
print("recorded provenance and end-to-end scaffold OK")
PY

if [[ "${RHO_RUN_LIVE:-0}" != "1" ]]; then
    echo "Live mutation skipped; run with RHO_RUN_LIVE=1 on a GPU workshop pod."
    echo "================ RHO tests PASSED ================"
    exit 0
fi

echo "================ RHO live one-generation smoke ================"
"${CAPX_PY}" /ryzers/rho_demo.py live-smoke

echo "================ RHO tests PASSED ================"
