#!/bin/bash
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

set -euo pipefail

echo "Testing MolmoAct2 inference and training stack..."

python3 - <<'PY'
import os
import subprocess
import sys
from pathlib import Path

import accelerate
import einops          # noqa: F401
import fastapi         # noqa: F401
import huggingface_hub
import json_numpy      # noqa: F401
import lerobot
import mujoco
import robosuite
import safetensors     # noqa: F401
import sentencepiece   # noqa: F401
import torch
import transformers
from packaging.version import Version

from lerobot.envs.libero import _get_suite
from lerobot.policies.molmoact2.configuration_molmoact2 import MolmoAct2Config
from lerobot.policies.molmoact2.modeling_molmoact2 import MolmoAct2Policy  # noqa: F401
from libero.libero import get_assets_path, get_libero_path

sys.path.insert(0, os.environ["DROID_SERVER_DIR"])
from host_server_droid import NORM_TAG, Policy  # noqa: E402

assert torch.version.hip, f"torch is not a ROCm build: {torch.__version__}"
assert lerobot.__version__ == "0.5.2", lerobot.__version__
assert Version("5.4") <= Version(transformers.__version__) < Version("5.6")
assert Policy.__name__ == "Policy" and NORM_TAG

cfg = MolmoAct2Config(
    checkpoint_path="allenai/MolmoAct2-DROID",
    train_mode_vlm="lora",
    action_mode="both",
    chunk_size=10,
    n_action_steps=10,
    setup_type="single franka robotic arm in libero",
    control_mode="delta end-effector pose",
    image_keys=[
        "observation.images.image",
        "observation.images.wrist_image",
    ],
    model_dtype="bfloat16",
    num_flow_timesteps=8,
    gradient_checkpointing=True,
    freeze_embedding=True,
    normalize_gripper=False,
    enable_knowledge_insulation=False,
    push_to_hub=False,
)
assert cfg.train_mode_vlm == "lora"
assert cfg.action_mode == "both"

for key in ("benchmark_root", "bddl_files", "init_states"):
    assert Path(get_libero_path(key)).exists(), (key, get_libero_path(key))
assert Path(get_assets_path()).exists(), get_assets_path()
suite = _get_suite("libero_object")
assert len(suite.tasks) == 10

help_result = subprocess.run(
    [
        sys.executable,
        "-m",
        "lerobot.scripts.lerobot_train",
        "--policy.type=molmoact2",
        "--help",
    ],
    check=True,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
)
required_flags = {
    "--policy.train_mode_vlm",
    "--policy.setup_type",
    "--policy.control_mode",
    "--policy.image_keys",
    "--policy.model_dtype",
    "--policy.num_flow_timesteps",
    "--policy.freeze_embedding",
    "--policy.normalize_gripper",
    "--policy.enable_knowledge_insulation",
}
missing = sorted(flag for flag in required_flags if flag not in help_result.stdout)
assert not missing, f"MolmoAct2 training CLI is missing: {missing}"

print(f"python           : {sys.executable}")
print(f"torch            : {torch.__version__}")
print(f"lerobot          : {lerobot.__version__}")
print(f"transformers     : {transformers.__version__}")
print(f"accelerate       : {accelerate.__version__}")
print(f"huggingface_hub  : {huggingface_hub.__version__}")
print(f"robosuite/mujoco : {robosuite.__version__} / {mujoco.__version__}")
print(f"libero tasks     : {len(suite.tasks)}")
print("PASS: MolmoAct2 inference, training CLI, and LIBERO metadata OK")
PY
