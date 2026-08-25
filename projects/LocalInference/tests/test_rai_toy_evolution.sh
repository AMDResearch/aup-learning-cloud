#!/usr/bin/env bash
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
set -euo pipefail

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "${SCRIPT_PATH}")" && pwd)"
HERE="$(cd "${SCRIPT_DIR}/../scripts" && pwd)"
PYTHON_BIN="${RAI_TOY_TEST_PYTHON:-python3}"
export PYTHONPATH="${HERE}${PYTHONPATH:+:${PYTHONPATH}}"
export RAI_TOY_SUPPORT_DIR="${HERE}"
export RAI_TOY_MOCK=1

echo "================ RAI toy static compile ================"
"${PYTHON_BIN}" -m py_compile "${HERE}/rai_toy_demo.py"

echo "================ RAI toy mock contract ================"
"${PYTHON_BIN}" - <<'PY'
import json
import os
import subprocess
import tomllib
from pathlib import Path

import rai_toy_demo as demo

assert os.environ["RAI_TOY_MOCK"] == "1"
root = demo.prepare_workshop(
    Path("/tmp/rai-toy-static/candidate"),
    model="test-model",
)
manifest = json.loads((root / "scenarios.json").read_text())
assert manifest["splits"] == {
    "train": ["train-red-cube"],
    "val": ["val-blue-cylinder"],
}
assert "test-green-cube" not in manifest["scenarios"]
assert manifest["test_exposed_to_evolution"] is False

config = tomllib.loads((root / "helix.toml").read_text())
assert config["dataset"] == {"train_size": 1, "val_size": 1}
assert config["evolution"]["max_generations"] == 1
assert config["evolution"]["acceptance_criterion"] == "strict_improvement"
assert "scenarios.json" in config["evaluator"]["protected_files"]
assert config["sandbox"]["enabled"] is False

permissions = json.loads((root / "opencode.json").read_text())["permission"]
assert permissions["edit"]["*"] == "deny"
assert permissions["edit"]["solver/**"] == "allow"
assert permissions["external_directory"] == "deny"

seed_prompt = (root / "solver/prompt.py").read_text()
seed_tools = (root / "solver/tools.py").read_text()
before = demo.score_candidate(root, "test-green-cube", timeout_seconds=5)
assert before["side_info"]["benchmark_kind"] == demo.MOCK_LABEL
assert before["side_info"]["is_live_rai"] is False
assert before["score"] == 0.3
assert before["passed"] is False
assert (root / "solver/prompt.py").read_text() == seed_prompt
assert (root / "solver/tools.py").read_text() == seed_tools

(root / "solver/prompt.py").write_text(
    seed_prompt.replace(
        "positive y is LEFT and negative y is RIGHT",
        "negative y is LEFT and positive y is RIGHT",
    )
)
(root / "solver/tools.py").write_text(
    seed_tools.replace(
        "normalized_y = abs(float(target_y))",
        "normalized_y = float(target_y)",
    )
)
after = demo.score_candidate(root, "test-green-cube", timeout_seconds=5)
assert after["score"] == 1.0
assert after["passed"] is True
assert demo.source_diff(
    Path("/tmp/rai-toy-static/candidate") / ".git" / "..", root
) == ""

completed = subprocess.run(
    [os.sys.executable, "probe.py", "--task", "val-blue-cylinder"],
    cwd=root,
    check=True,
    capture_output=True,
    text=True,
    env={**os.environ, "RAI_TOY_SUPPORT_DIR": str(Path(demo.__file__).parent)},
)
assert "RAI_TOY_RESULT=" in completed.stdout
print("candidate, protection, explicit tasks, mock failure, and repaired pass OK")
PY

if [[ -x /opt/capx-venv/bin/python ]]; then
  /opt/capx-venv/bin/python - <<'PY'
from pathlib import Path
from helix.config import load_config

load_config(Path("/tmp/rai-toy-static/candidate/helix.toml"))
print("workshop HELIX config schema OK")
PY
fi

if [[ "${RAI_TOY_RUN_LIVE:-0}" != "1" ]]; then
  echo "Live RAI check skipped; set RAI_TOY_RUN_LIVE=1 in the workshop image."
  echo "================ RAI toy tests PASSED ================"
  exit 0
fi

echo "================ RAI toy live agent gate ================"
unset RAI_TOY_MOCK
"${RAI_PYTHON:-/opt/rai-venv/bin/python}" - <<'PY'
from pathlib import Path

import rai_toy_demo as demo

demo.ensure_model()
root = demo.prepare_workshop(Path("/tmp/rai-toy-live/candidate"))
before = demo.score_candidate(root, "test-green-cube")
prompt = (root / "solver/prompt.py").read_text()
tools = (root / "solver/tools.py").read_text()
(root / "solver/prompt.py").write_text(
    prompt.replace(
        "positive y is LEFT and negative y is RIGHT",
        "negative y is LEFT and positive y is RIGHT",
    )
)
(root / "solver/tools.py").write_text(
    tools.replace(
        "normalized_y = abs(float(target_y))",
        "normalized_y = float(target_y)",
    )
)
after = demo.score_candidate(root, "test-green-cube")
assert before["passed"] is False, before
assert after["side_info"]["is_live_rai"] is True, after
assert after["passed"] is True, after
print("LIVE_SEED=", before)
print("LIVE_REPAIRED=", after)
PY

echo "================ RAI toy tests PASSED ================"
