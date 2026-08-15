#!/bin/bash
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

set -euo pipefail

echo "Testing FastWAM world-action model + LIBERO sim stack..."

# The FastWAM stack lives in its OWN isolated venv (numpy 1.26.4) with its OWN LIBERO config
# path, so this test never touches the MolmoAct2 train-venv.
FW_PY="${FASTWAM_VENV:-/opt/fastwam-venv}/bin/python"
export LIBERO_CONFIG_PATH="${LIBERO_CONFIG_PATH_FASTWAM:-/opt/libero-config-fastwam}"

"$FW_PY" - <<'PY'
import os
import sys

import numpy as np
import torch
import mujoco
import robosuite  # noqa: F401

from libero.libero import benchmark  # noqa: F401
from libero.libero.envs import OffScreenRenderEnv  # noqa: F401

import sim_libero  # noqa: F401
from sim_libero.libero_env import SUITES, get_benchmark_dict, get_max_steps
from sim_libero.policy import Policy, load_policy  # noqa: F401

import fastwam  # noqa: F401
from fastwam.runtime import create_fastwam  # noqa: F401
from fastwam.datasets.lerobot.utils.normalizer import load_dataset_stats_from_json  # noqa: F401
import experiments.libero.eval_libero_single as E  # noqa: F401

# The runtime policy factory (POLICY_FACTORY target for the interactive server).
sys.path.insert(0, "/opt/fastwam-adapters")
import fastwam_libero_policy  # noqa: E402
assert hasattr(fastwam_libero_policy, "build_policy"), "fastwam_libero_policy.build_policy missing"

assert torch.version.hip, f"torch is not a ROCm build: {torch.__version__}"
assert np.__version__.startswith("1.26"), f"expected numpy 1.26.x in fastwam venv, got {np.__version__}"

benchmark_dict = get_benchmark_dict()
for suite in ("libero_object", "libero_goal", "libero_spatial", "libero_10"):
    assert suite in benchmark_dict, f"suite {suite} missing from LIBERO benchmark dict"
    get_max_steps(suite)

rel = os.environ.get("FASTWAM_RELEASE_DIR", "/opt/fastwam-assets/fastwam_release")
ckpt = os.path.join(rel, "libero_uncond_2cam224.pt")
stats = os.path.join(rel, "libero_uncond_2cam224_dataset_stats.json")
diffsynth = os.environ.get("DIFFSYNTH_MODEL_BASE_PATH", "/opt/fastwam-assets/diffsynth")

print(f"python           : {sys.executable}")
print(f"torch            : {torch.__version__}  hip={torch.version.hip}")
print(f"numpy            : {np.__version__}")
print(f"mujoco/robosuite : {mujoco.__version__} / {robosuite.__version__}")
print(f"libero suites    : {', '.join(SUITES)}")
print(f"baked ckpt       : {ckpt} -> {'PRESENT' if os.path.exists(ckpt) else 'absent'}")
print(f"baked stats      : {stats} -> {'PRESENT' if os.path.exists(stats) else 'absent'}")
print(f"Wan2.2 base      : {diffsynth} -> {'PRESENT' if os.path.isdir(diffsynth) else 'absent'}")
print("PASS: FastWAM world-action + LIBERO sim imports OK")
PY

echo "(env-check only; run scripts/fastwam_smoke.py on a GPU for a full infer_action smoke.)"
