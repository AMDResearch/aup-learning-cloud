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
from pathlib import Path

import rho_demo
from helix.config import load_config

root = rho_demo.prepare_workshop()
required = {
    "solver/__init__.py",
    "solver/geometry.py",
    "solver/policy.py",
    "API_REFERENCE.md",
    "probe.py",
    "opencode.json",
    "helix.toml",
}
assert required <= {
    str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()
}

config = load_config(root / "helix.toml")
assert config.agent.backend == "opencode"
assert config.agent.model == "lemonade/Gemma-4-E2B-it-GGUF"
assert config.dataset.train_size == config.dataset.val_size == 1
assert config.evolution.max_generations == 1
assert config.evolution.minibatch_size == 1
assert config.evolution.max_workers == 1
assert config.evolution.merge_enabled is False
assert config.evolution.acceptance_criterion == "strict_improvement"

opencode = json.loads((root / "opencode.json").read_text())
permissions = opencode["permission"]
assert permissions["external_directory"] == "deny"
assert permissions["edit"]["*"] == "deny"
assert permissions["edit"]["**/solver/**"] == "allow"
assert permissions["bash"]["*"] == "deny"

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
assert {"reward", "traceback", "feedback", "scores"} <= payload[0][1].keys()

frozen = rho_demo.score_candidate(
    rho_demo.FALLBACK_ROOT, "val", timeout_seconds=5
)
assert frozen["reward"] == 1.0 and frozen["task_completed"]

bounded = rho_demo.run_bounded(
    [sys.executable, str(Path(rho_demo.__file__)), "_sleep", "2"],
    cwd=root,
    timeout_seconds=0.2,
)
assert bounded.timed_out and bounded.returncode == 124
print("scaffold, HELIX_RESULT protocol, permissions, and timeout cleanup OK")
PY

if [[ "${RHO_RUN_LIVE:-0}" != "1" ]]; then
    echo "Live mutation skipped; run with RHO_RUN_LIVE=1 on a GPU workshop pod."
    echo "================ RHO tests PASSED ================"
    exit 0
fi

echo "================ RHO live one-generation smoke ================"
"${CAPX_PY}" /ryzers/rho_demo.py live-smoke

echo "================ RHO tests PASSED ================"
