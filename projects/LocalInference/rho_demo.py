# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
"""Bounded HELIX/CaP-X plumbing for the RHO workshop notebook."""

from __future__ import annotations

import atexit
import difflib
import json
import os
import queue
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")

CAPX_ROOT = Path(os.environ.get("CAPX_ROOT", "/ryzers/cap-x"))
CAPX_PYTHON = Path(os.environ.get("CAPX_PYTHON", "/opt/capx-venv/bin/python"))
HELIX = Path(os.environ.get("HELIX_BIN", "/opt/capx-venv/bin/helix"))
MODEL = "Gemma-4-E2B-it-GGUF"
CONFIG_PATH = "env_configs/cube_stack/franka_robosuite_cube_stack.yaml"
WORKSHOP_ROOT = Path(os.environ.get("RHO_WORKSHOP_ROOT", "/tmp/rho_workshop"))
CANDIDATE_ROOT = WORKSHOP_ROOT / "candidate"
FALLBACK_ROOT = WORKSHOP_ROOT / "prerecorded_fallback"
VIDEO_ROOT = WORKSHOP_ROOT / "videos"
SERVICE_PORTS = (8114, 8115, 8116)
DEFAULT_TIMEOUT = 480
EVALUATION_TIMEOUT = 120

_OWNED_SERVERS: list[subprocess.Popen[Any]] = []


SEED_GEOMETRY = """\
SAFE_LIFT = 0.02
APPROACH_DISTANCE = 0.0
PLACEMENT_CLEARANCE = -0.025
"""

FROZEN_GEOMETRY = """\
SAFE_LIFT = 0.20
APPROACH_DISTANCE = 0.10
PLACEMENT_CLEARANCE = 0.0
"""

POLICY_SOURCE = """\
import numpy as np

from solver.geometry import APPROACH_DISTANCE, PLACEMENT_CLEARANCE, SAFE_LIFT


def build_program() -> str:
    return f\"\"\"
import numpy as np

green_pos, _, green_extent = get_object_pose(
    'green cube', return_bbox_extent=True
)
red_pos, _, red_extent = get_object_pose(
    'red cube', return_bbox_extent=True
)
grasp_pos, grasp_quat = sample_grasp_pose('red cube')

goto_pose(grasp_pos, grasp_quat, z_approach={APPROACH_DISTANCE})
close_gripper()

lift_pos = np.array([
    grasp_pos[0],
    grasp_pos[1],
    grasp_pos[2] + {SAFE_LIFT},
])
goto_pose(lift_pos, grasp_quat)

place_pos = np.array([
    green_pos[0],
    green_pos[1],
    green_pos[2]
    + green_extent[2] / 2
    + red_extent[2] / 2
    + {PLACEMENT_CLEARANCE},
])
goto_pose(place_pos, grasp_quat, z_approach={APPROACH_DISTANCE})
open_gripper()
\"\"\".strip()
"""

API_REFERENCE = """\
# CaP-X cube-stack contract

Improve the policy that stacks the red cube on the green cube.

- `sample_grasp_pose("red cube")` returns a grasp position and a reliable
  gripper quaternion.
- `get_object_pose(name, return_bbox_extent=True)` returns center position,
  quaternion, and full bounding-box side lengths.
- `goto_pose(position, quaternion, z_approach=0.1)` executes an approach and
  target motion; use a non-zero approach for grasping and placement.
- Lift the grasped cube far enough to clear the table and the target cube.
- The placement center height is both cubes' half-heights above the green
  center. Reuse the grasp quaternion for placement.
- `close_gripper()` and `open_gripper()` actuate the gripper.

The evaluator runs one fixed training layout and one different held-out layout.
Only edit files below `solver/`.
"""

OPENCODE_CONFIG = {
    "$schema": "https://opencode.ai/config.json",
    "model": f"lemonade/{MODEL}",
    "small_model": f"lemonade/{MODEL}",
    "provider": {
        "lemonade": {
            "npm": "@ai-sdk/openai-compatible",
            "name": "Local Lemonade",
            "options": {
                "baseURL": "http://127.0.0.1:13305/api/v1",
                "apiKey": "lemonade",
            },
            "models": {
                MODEL: {
                    "name": MODEL,
                    "limit": {"context": 32768, "output": 4096},
                }
            },
        }
    },
    "permission": {
        "*": "allow",
        "edit": {"*": "deny", "**/solver/**": "allow"},
        "external_directory": "deny",
        "webfetch": "deny",
        "websearch": "deny",
        "task": "deny",
        "bash": {
            "*": "deny",
            "/opt/capx-venv/bin/python probe.py*": "allow",
            "/opt/capx-venv/bin/python -m py_compile solver/*.py": "allow",
            "git diff*": "allow",
            "git status*": "allow",
        },
    },
}

PROBE_SOURCE = """\
import sys

sys.path.insert(0, "/ryzers")
from rho_demo import evaluate_cli

raise SystemExit(evaluate_cli())
"""


def helix_config(generations: int = 1) -> str:
    return f'''\
objective = """Improve this small multi-file CaP-X policy so it reliably stacks
the red cube on the green cube. Diagnose the evaluator feedback, inspect
API_REFERENCE.md, and edit only solver/. Keep the policy concise."""
seed = "."
rng_seed = 7
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
  "XDG_RUNTIME_DIR",
]

[env]
CAPX_ROOT = "/ryzers/cap-x"
HF_HOME = "/opt/capx-cache"
MUJOCO_GL = "egl"
PYOPENGL_PLATFORM = "egl"
RHO_EVAL_TIMEOUT = "120"

[evaluator]
command = "/opt/capx-venv/bin/python probe.py"
protected_files = ["probe.py", "opencode.json", "API_REFERENCE.md"]

[dataset]
train_size = 1
val_size = 1

[evolution]
max_generations = {generations}
perfect_score_threshold = 1.0
max_evaluations = 8
merge_enabled = false
num_parallel_proposals = 1
mutations_per_parent = 1
minibatch_size = 1
max_workers = 1
cache_evaluation = true
acceptance_criterion = "strict_improvement"
frontier_type = "instance"

[agent]
backend = "opencode"
model = "lemonade/{MODEL}"
max_turns = 8
background = """This is a bounded workshop mutation. Read API_REFERENCE.md and
the evaluator diagnostics first. Only edit solver/. Do not alter evaluation,
configuration, permissions, or files outside this repository. Run
`/opt/capx-venv/bin/python -m py_compile solver/*.py` and
`/opt/capx-venv/bin/python probe.py` before finishing."""

[sandbox]
enabled = false

[worktree]
base_dir = ".helix/worktrees"
'''


@dataclass
class BoundedRun:
    returncode: int
    timed_out: bool
    stdout: str
    elapsed_seconds: float


def _safe_reset(path: Path) -> None:
    resolved = path.resolve()
    allowed = WORKSHOP_ROOT.resolve()
    if resolved != allowed and allowed not in resolved.parents:
        raise ValueError(f"refusing to remove path outside {allowed}: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)


def _write_candidate(root: Path, geometry: str) -> None:
    (root / "solver").mkdir(parents=True, exist_ok=True)
    (root / "solver" / "__init__.py").write_text("")
    (root / "solver" / "geometry.py").write_text(geometry)
    (root / "solver" / "policy.py").write_text(POLICY_SOURCE)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", "user.name=RHO Workshop", "-c", "user.email=rho@localhost",
         *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def prepare_workshop(
    root: Path | str = CANDIDATE_ROOT,
    *,
    generations: int = 1,
    reset: bool = True,
) -> Path:
    """Create the disposable seed repository and a separate labeled fallback."""
    root = Path(root)
    if reset:
        _safe_reset(root.parent)
    root.mkdir(parents=True, exist_ok=True)
    _write_candidate(root, SEED_GEOMETRY)
    (root / "API_REFERENCE.md").write_text(API_REFERENCE)
    (root / "opencode.json").write_text(
        json.dumps(OPENCODE_CONFIG, indent=2) + "\n"
    )
    (root / "helix.toml").write_text(helix_config(generations))
    (root / "probe.py").write_text(PROBE_SOURCE)
    (root / ".gitignore").write_text(
        ".helix/\n.helix_artifacts/\n.helix_opencode_state/\n"
        "__pycache__/\n*.pyc\nhelix_batch.json\n"
    )

    _git(root, "init", "-b", "main")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "Seed the bounded CaP-X policy")

    _write_candidate(FALLBACK_ROOT, FROZEN_GEOMETRY)
    trace = {
        "label": "PRERECORDED FALLBACK — not the live HELIX result",
        "model": MODEL,
        "mutation": [
            "SAFE_LIFT: 0.02 -> 0.20",
            "APPROACH_DISTANCE: 0.0 -> 0.10",
            "PLACEMENT_CLEARANCE: -0.025 -> 0.0",
        ],
        "recorded_heldout": {
            "split": "val",
            "trial": 2,
            "reward": 1.0,
            "task_completed": True,
        },
        "purpose": (
            "Known-good teaching artifact shown only when the live local model "
            "times out or its child is correctly rejected."
        ),
    }
    (FALLBACK_ROOT / "trace.json").write_text(json.dumps(trace, indent=2) + "\n")
    return root


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def service_status() -> dict[int, bool]:
    return {port: _port_open(port) for port in SERVICE_PORTS}


def ensure_services(progress: Callable[[str], None] = print) -> list[Any]:
    """Start/reuse Lemonade, SAM3, Contact-GraspNet, and PyRoKi."""
    from capx_demo import ensure_lemonade

    ensure_lemonade(MODEL, progress=progress)
    old_cwd = Path.cwd()
    try:
        os.chdir(CAPX_ROOT)
        from capx.envs.launch import LaunchArgs
        from capx.envs.runner import _start_api_servers
        from capx.utils.launch_utils import _load_config

        args = LaunchArgs(
            config_path=CONFIG_PATH,
            model=MODEL,
            server_url="http://127.0.0.1:13305/api/v1/chat/completions",
            temperature=0.2,
            max_tokens=4096,
        )
        _, _, api_servers = _load_config(args)
        servers = _start_api_servers(api_servers, 900.0)
    finally:
        os.chdir(old_cwd)

    for proc in servers:
        if hasattr(proc, "poll") and proc.poll() is None:
            _OWNED_SERVERS.append(proc)
    progress(f"CaP-X services: {service_status()}")
    return servers


def stop_owned_services() -> None:
    while _OWNED_SERVERS:
        proc = _OWNED_SERVERS.pop()
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


atexit.register(stop_owned_services)


def _terminate_group(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()


def run_bounded(
    command: list[str],
    *,
    cwd: Path | str,
    timeout_seconds: float,
    env: dict[str, str] | None = None,
    progress: Callable[[str], None] | None = None,
) -> BoundedRun:
    """Run a command in its own process group and enforce a wall-clock limit."""
    started = time.monotonic()
    proc = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    assert proc.stdout is not None
    lines: list[str] = []
    output_queue: queue.Queue[str | None] = queue.Queue()

    def _reader() -> None:
        for line in proc.stdout:
            output_queue.put(line)
        output_queue.put(None)

    threading.Thread(target=_reader, daemon=True).start()
    timed_out = False
    stream_done = False
    deadline = started + timeout_seconds

    while proc.poll() is None or not stream_done:
        if proc.poll() is None and time.monotonic() >= deadline:
            timed_out = True
            _terminate_group(proc)
        try:
            line = output_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        if line is None:
            stream_done = True
            continue
        lines.append(line)
        if progress is not None:
            progress(line.rstrip())

    return BoundedRun(
        returncode=124 if timed_out else int(proc.returncode or 0),
        timed_out=timed_out,
        stdout="".join(lines),
        elapsed_seconds=time.monotonic() - started,
    )


def _trial_id(split: str, example_id: str) -> int:
    value = int(example_id)
    return value if split == "train" else value + 2


def _mock_evaluation(candidate_root: Path, split: str, example_id: str) -> dict[str, Any]:
    namespace: dict[str, Any] = {}
    exec((candidate_root / "solver" / "geometry.py").read_text(), namespace)
    success = (
        float(namespace.get("SAFE_LIFT", 0)) >= 0.10
        and float(namespace.get("APPROACH_DISTANCE", 0)) >= 0.05
        and float(namespace.get("PLACEMENT_CLEARANCE", -1)) >= -0.005
    )
    return {
        "reward": float(success),
        "task_completed": success,
        "split": split,
        "trial": _trial_id(split, example_id),
        "traceback": "",
        "feedback": (
            "Mock policy completed the stack."
            if success
            else "Mock policy missed: add approach distance, clearance, and a safe lift."
        ),
        "video": None,
    }


def _live_evaluation(
    candidate_root: Path,
    split: str,
    example_id: str,
    *,
    capture: bool,
) -> dict[str, Any]:
    old_cwd = Path.cwd()
    env = None
    try:
        os.chdir(CAPX_ROOT)
        from capx.envs.configs.instantiate import instantiate
        from capx.envs.launch import LaunchArgs
        from capx.utils.launch_utils import _load_config

        args = LaunchArgs(
            config_path=CONFIG_PATH,
            model=MODEL,
            server_url="http://127.0.0.1:13305/api/v1/chat/completions",
            temperature=0.2,
            max_tokens=4096,
        )
        env_factory, _, _ = _load_config(args)
        env = instantiate(env_factory)
        trial = _trial_id(split, example_id)
        env.reset(options={"trial": trial}, seed=trial)

        sys.path.insert(0, str(candidate_root))
        for name in list(sys.modules):
            if name == "solver" or name.startswith("solver."):
                del sys.modules[name]
        from solver.policy import build_program

        if capture:
            env.enable_video_capture()
        _, reward, _, _, info = env.step(build_program())
        score = float(reward)
        video: str | None = None
        if capture:
            from capx.utils.video_utils import _write_video

            frames = env.get_video_frames(clear=True)
            if frames:
                VIDEO_ROOT.mkdir(parents=True, exist_ok=True)
                suffix = f"{split}_{example_id}_{int(time.time())}"
                _write_video(frames, str(VIDEO_ROOT), suffix=suffix)
                video = str(VIDEO_ROOT / f"video_{suffix}.mp4")
        return {
            "reward": score,
            "task_completed": bool(score >= 1.0),
            "split": split,
            "trial": trial,
            "traceback": "",
            "feedback": (
                "Task completed."
                if score >= 1.0
                else f"Task not completed; simulator info: {str(info)[-800:]}"
            ),
            "video": video,
        }
    finally:
        if candidate_root.as_posix() in sys.path:
            sys.path.remove(candidate_root.as_posix())
        if env is not None and hasattr(env, "close"):
            env.close()
        os.chdir(old_cwd)


def _worker_result(
    candidate_root: Path, split: str, example_id: str, capture: bool
) -> dict[str, Any]:
    try:
        if os.environ.get("RHO_MOCK_EVAL") == "1":
            return _mock_evaluation(candidate_root, split, example_id)
        return _live_evaluation(candidate_root, split, example_id, capture=capture)
    except Exception:
        return {
            "reward": 0.0,
            "task_completed": False,
            "split": split,
            "trial": _trial_id(split, example_id),
            "traceback": traceback.format_exc()[-2400:],
            "feedback": "Candidate raised during execution; inspect traceback.",
            "video": None,
        }


def score_candidate(
    candidate_root: Path | str,
    split: str = "train",
    example_id: str = "0",
    *,
    capture: bool = False,
    timeout_seconds: float = EVALUATION_TIMEOUT,
) -> dict[str, Any]:
    """Evaluate one fixed layout in a killable child process."""
    candidate_root = Path(candidate_root).resolve()
    worker = run_bounded(
        [
            str(CAPX_PYTHON if CAPX_PYTHON.exists() else Path(sys.executable)),
            str(Path(__file__).resolve()),
            "_evaluate_worker",
            str(candidate_root),
            split,
            str(example_id),
            "1" if capture else "0",
        ],
        cwd=candidate_root,
        timeout_seconds=timeout_seconds,
        env=os.environ.copy(),
    )
    if worker.timed_out:
        return {
            "reward": 0.0,
            "task_completed": False,
            "split": split,
            "trial": _trial_id(split, example_id),
            "traceback": "",
            "feedback": f"Evaluation timed out after {timeout_seconds:.0f}s.",
            "video": None,
            "timed_out": True,
        }
    for line in reversed(worker.stdout.splitlines()):
        try:
            result = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(result, dict) and "reward" in result:
            result["execution_tail"] = "\n".join(worker.stdout.splitlines()[-12:-1])[-1200:]
            result["timed_out"] = False
            return result
    return {
        "reward": 0.0,
        "task_completed": False,
        "split": split,
        "trial": _trial_id(split, example_id),
        "traceback": worker.stdout[-2400:],
        "feedback": "Evaluator worker returned no JSON result.",
        "video": None,
        "timed_out": False,
    }


def evaluate_cli() -> int:
    """Emit HELIX's exact positional per-example result protocol."""
    root = Path.cwd()
    batch_path = root / "helix_batch.json"
    ids = json.loads(batch_path.read_text()) if batch_path.exists() else ["0"]
    if not isinstance(ids, list) or not all(isinstance(item, str) for item in ids):
        raise ValueError("helix_batch.json must be a JSON list of strings")
    split = os.environ.get("HELIX_SPLIT", "train")
    timeout = float(os.environ.get("RHO_EVAL_TIMEOUT", EVALUATION_TIMEOUT))
    payload: list[list[Any]] = []
    for example_id in ids:
        result = score_candidate(root, split, example_id, timeout_seconds=timeout)
        side_info = {
            "reward": result["reward"],
            "task_completed": result["task_completed"],
            "split": result["split"],
            "trial": result["trial"],
            "traceback": result.get("traceback", ""),
            "feedback": result.get("feedback", ""),
            "execution_tail": result.get("execution_tail", ""),
            "timed_out": result.get("timed_out", False),
            "scores": {"completion": result["reward"]},
        }
        payload.append([float(result["reward"]), side_info])
    print("HELIX_RESULT=" + json.dumps(payload, separators=(",", ":")))
    return 0


def run_helix(
    root: Path | str = CANDIDATE_ROOT,
    *,
    generations: int = 1,
    timeout_seconds: float = DEFAULT_TIMEOUT,
    progress: Callable[[str], None] = print,
) -> BoundedRun:
    """Stream a bounded HELIX evolution in the disposable candidate repo."""
    root = Path(root)
    command = [
        str(HELIX if HELIX.exists() else Path("helix")),
        "evolve",
        "--dir",
        str(root),
        "--config",
        "helix.toml",
        "--generations",
        str(generations),
        "--no-merge",
    ]
    result = run_bounded(
        command,
        cwd=root,
        timeout_seconds=timeout_seconds,
        env=os.environ.copy(),
        progress=progress,
    )
    if result.timed_out:
        progress(f"HELIX stopped at the {timeout_seconds:.0f}s workshop deadline.")
    return result


def source_diff(before: Path | str, after: Path | str) -> str:
    before, after = Path(before), Path(after)
    chunks: list[str] = []
    for relative in ("solver/geometry.py", "solver/policy.py"):
        old = (before / relative).read_text().splitlines(keepends=True)
        new = (after / relative).read_text().splitlines(keepends=True)
        chunks.extend(
            difflib.unified_diff(
                old, new, fromfile=f"seed/{relative}", tofile=f"best/{relative}"
            )
        )
    return "".join(chunks)


def semantic_mutation(diff: str) -> list[str]:
    removed: dict[str, str] = {}
    changes: list[str] = []
    assignment = re.compile(r"^[+-]([A-Z][A-Z0-9_]*)\s*=\s*(.+)$")
    for line in diff.splitlines():
        match = assignment.match(line)
        if not match:
            continue
        name, value = match.groups()
        if line.startswith("-"):
            removed[name] = value
        elif name in removed:
            changes.append(f"{name}: {removed[name]} -> {value}")
    if not changes and diff:
        files = sorted(
            {
                line.removeprefix("+++ best/")
                for line in diff.splitlines()
                if line.startswith("+++ best/")
            }
        )
        changes = [f"Changed {name}" for name in files]
    return changes


def export_best(root: Path | str = CANDIDATE_ROOT) -> Path:
    root = Path(root)
    destination = root.parent / "live_best"
    _safe_reset(destination)
    done = subprocess.run(
        [
            str(HELIX if HELIX.exists() else Path("helix")),
            "best",
            "--dir",
            str(root),
            "--export",
            str(destination),
        ],
        cwd=root,
        capture_output=True,
        text=True,
    )
    return destination if done.returncode == 0 and destination.exists() else root


def summarize_run(root: Path | str = CANDIDATE_ROOT) -> dict[str, Any]:
    root = Path(root)
    best = export_best(root)
    best_diff = source_diff(root, best)
    state_path = root / ".helix" / "state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    child_ids = [
        candidate_id
        for candidate_id in state.get("frontier", [])
        if candidate_id != "g0-s0"
    ]
    child = (
        root / ".helix" / "worktrees" / child_ids[-1]
        if child_ids
        else None
    )
    child_diff = (
        source_diff(root, child)
        if child is not None and (child / "solver" / "policy.py").exists()
        else ""
    )
    fallback_trace = json.loads((FALLBACK_ROOT / "trace.json").read_text())
    return {
        "accepted": bool(child_ids),
        "improved_best": bool(best_diff.strip()),
        "live_best": str(best),
        "best_diff": best_diff,
        "child_candidate": str(child) if child is not None else None,
        "semantic_mutation": semantic_mutation(child_diff or best_diff),
        "child_diff": child_diff,
        "fallback": {
            "candidate": str(FALLBACK_ROOT),
            "trace": fallback_trace,
            "label": fallback_trace["label"],
        },
    }


def live_smoke_cli() -> int:
    """Run the file-backed live path used by the optional image smoke test."""
    started = time.monotonic()
    ensure_services()
    root = prepare_workshop()
    seed = score_candidate(root, "train")
    run = run_helix(root, generations=1, timeout_seconds=DEFAULT_TIMEOUT)
    summary = summarize_run(root)
    frozen = score_candidate(FALLBACK_ROOT, "val")
    elapsed = time.monotonic() - started
    if run.timed_out:
        raise RuntimeError("HELIX exceeded its 480-second hard deadline")
    if run.returncode != 0:
        raise RuntimeError(run.stdout[-4000:])
    if elapsed >= 600:
        raise RuntimeError(f"live workshop path took {elapsed:.1f}s")
    if frozen.get("timed_out") or frozen.get("traceback"):
        raise RuntimeError(f"frozen candidate failed: {frozen}")
    result = {
        "seed_reward": seed["reward"],
        "accepted": summary["accepted"],
        "frozen_reward": frozen["reward"],
        "frozen_completed": frozen["task_completed"],
        "helix_seconds": round(run.elapsed_seconds, 1),
        "total_seconds": round(elapsed, 1),
    }
    print("RHO_LIVE_RESULT=" + json.dumps(result, separators=(",", ":")))
    return 0


def _main(argv: list[str]) -> int:
    if not argv:
        print("usage: rho_demo.py {prepare|evaluate|run|summary}")
        return 2
    if argv[0] == "prepare":
        print(prepare_workshop())
        return 0
    if argv[0] == "evaluate":
        return evaluate_cli()
    if argv[0] == "run":
        result = run_helix()
        print(json.dumps(asdict(result), indent=2))
        return result.returncode
    if argv[0] == "summary":
        print(json.dumps(summarize_run(), indent=2))
        return 0
    if argv[0] == "live-smoke":
        return live_smoke_cli()
    if argv[0] == "_evaluate_worker":
        result = _worker_result(
            Path(argv[1]), argv[2], argv[3], bool(int(argv[4]))
        )
        print(json.dumps(result, separators=(",", ":")))
        return 0
    if argv[0] == "_sleep":
        time.sleep(float(argv[1]))
        return 0
    raise ValueError(f"unknown command: {argv[0]}")


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
