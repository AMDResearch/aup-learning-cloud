# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
"""Fast repository-evolution demo using a real RAI tool-calling agent.

The candidate repository contains a system prompt and two LangChain tools.
HELIX/OpenCode may edit only those files. Evaluation runs a RAI conversational
agent against a tiny in-memory world, so one generation takes minutes rather
than the hours required by the O3DE benchmark.

``RAI_TOY_MOCK=1`` is a static plumbing check and is always labeled as such.
It must not be presented as a live RAI result.
"""

from __future__ import annotations

import ast
import difflib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import types
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SUPPORT_DIR = Path(__file__).resolve().parent
HELIX = Path(os.environ.get("HELIX_BIN", "/opt/capx-venv/bin/helix"))
RAI_PYTHON = Path(os.environ.get("RAI_PYTHON", "/opt/rai-venv/bin/python"))
DEFAULT_MODEL = os.environ.get("RAI_TOY_MODEL", "Gemma-4-E2B-it-GGUF")
DEFAULT_ENDPOINT = os.environ.get("RAI_TOY_MODEL_ENDPOINT", "http://127.0.0.1:13305/api/v1")
DEFAULT_ROOT = Path("/tmp/rai_toy_evolution/candidate")
DEFAULT_TIMEOUT = 600.0
MOCK_LABEL = "MOCK_STATIC_CONTRACT_NOT_LIVE_RAI"

SCENARIOS = {
    "train-red-cube": {
        "object": "red cube",
        "initial_y": 0.35,
        "target_y": -0.40,
        "instruction": (
            "Move the red cube into the left target centered at y=-0.40. "
            "Inspect the world first, then use the movement tool exactly once."
        ),
    },
    "val-blue-cylinder": {
        "object": "blue cylinder",
        "initial_y": 0.25,
        "target_y": -0.30,
        "instruction": (
            "Move the blue cylinder into the left target centered at y=-0.30. "
            "Inspect the world first, then use the movement tool exactly once."
        ),
    },
    "test-green-cube": {
        "object": "green cube",
        "initial_y": 0.45,
        "target_y": -0.50,
        "instruction": (
            "Move the green cube into the left target centered at y=-0.50. "
            "Inspect the world first, then use the movement tool exactly once."
        ),
    },
}

SEED_PROMPT = '''\
"""System prompt for the toy RAI manipulation agent."""

SYSTEM_PROMPT = """
You are a robot agent controlling objects on a tabletop.
Always inspect the world before moving anything.
Coordinate convention: positive y is LEFT and negative y is RIGHT.
Call move_object with the requested object's name and target y coordinate.
When the tool reports success, briefly report completion.
"""
'''

SEED_TOOLS = '''\
"""Mutable tools for the toy RAI manipulation agent."""

from typing import Any, List, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


class ObserveWorldTool(BaseTool):
    name: str = "observe_world"
    description: str = "Return object positions and the tabletop coordinate convention."
    world: Any = Field(exclude=True)

    def _run(self) -> str:
        return self.world.observe()


class MoveObjectInput(BaseModel):
    object_name: str = Field(description="Object name from observe_world")
    target_y: float = Field(description="Requested destination y coordinate")


class MoveObjectTool(BaseTool):
    name: str = "move_object"
    description: str = "Move one named object to an exact target y coordinate."
    args_schema: Type[MoveObjectInput] = MoveObjectInput
    world: Any = Field(exclude=True)

    def _run(self, object_name: str, target_y: float) -> str:
        # The seed wrapper mistakenly folds negative coordinates to positive.
        normalized_y = abs(float(target_y))
        return self.world.move(object_name, normalized_y)


REQUIRED_TOOL_NAMES = {"observe_world", "move_object"}


def build_tools(world: Any) -> List[BaseTool]:
    return [ObserveWorldTool(world=world), MoveObjectTool(world=world)]
'''

CONTRACT = """\
# Toy RAI evolution contract

The repository controls a real RAI conversational agent in a deterministic,
in-memory tabletop world. Only `solver/prompt.py` and `solver/tools.py` may be
edited.

The world uses the convention **negative y is left**. The seed has two related
defects:

1. `solver/prompt.py` states the opposite coordinate convention.
2. `solver/tools.py` applies `abs()` to the requested target, making every
   negative/left destination positive/right.

Preserve:

- a literal non-empty `SYSTEM_PROMPT` string;
- `build_tools(world) -> list[BaseTool]`;
- tool names `observe_world` and `move_object`;
- an observation before movement.

Training and validation use different objects and coordinates. The final test
uses a third object that is never exposed to HELIX.
"""

DEFAULT_OBJECTIVE = """\
Repair the toy RAI policy so the agent moves objects to negative-y left targets.
Edit BOTH solver/prompt.py and solver/tools.py: state that negative y is LEFT,
and preserve the signed target coordinate instead of applying abs(). Keep the
two-tool contract and make the fix general across object names and coordinates."""

DEFAULT_BACKGROUND = """\
This is a bounded workshop mutation of a real RAI tool-calling agent. Read
CONTRACT.md and evaluator feedback. Your first actions must edit both mutable
files: in solver/prompt.py correct the coordinate convention to say negative y
is LEFT and positive y is RIGHT; in solver/tools.py replace
normalized_y = abs(float(target_y)) with normalized_y = float(target_y).
Do not add shortcuts for scenario names. Do not edit protected files. Run
/opt/rai-venv/bin/python -m py_compile solver/*.py and
/opt/rai-venv/bin/python probe.py before finishing, then inspect git diff."""

PROBE_SOURCE = """\
import os
import sys

sys.path.insert(
    0, os.environ.get("RAI_TOY_SUPPORT_DIR", "/ryzers/notebooks")
)
from rai_toy_demo import evaluate_cli

raise SystemExit(evaluate_cli())
"""


@dataclass
class BoundedRun:
    returncode: int
    timed_out: bool
    stdout: str
    elapsed_seconds: float


class ToyWorld:
    """Minimal stateful world injected into candidate tools."""

    def __init__(self, scenario: Mapping[str, Any]) -> None:
        self.object_name = str(scenario["object"])
        self.position_y = float(scenario["initial_y"])
        self.target_y = float(scenario["target_y"])
        self.events: list[dict[str, Any]] = []

    @staticmethod
    def _normalize_name(value: str) -> str:
        return " ".join(value.lower().replace("_", " ").split())

    def observe(self) -> str:
        event = {
            "tool": "observe_world",
            "object": self.object_name,
            "y": self.position_y,
        }
        self.events.append(event)
        return (
            f"Detected {self.object_name} at y={self.position_y:+.2f}. "
            "World convention: negative y is LEFT; positive y is RIGHT."
        )

    def move(self, object_name: str, target_y: float) -> str:
        requested = float(target_y)
        event = {
            "tool": "move_object",
            "object_name": object_name,
            "target_y": requested,
        }
        self.events.append(event)
        if self._normalize_name(object_name) != self._normalize_name(self.object_name):
            event["accepted"] = False
            return f"Unknown object {object_name!r}; no movement occurred."
        if not -0.60 <= requested <= 0.60:
            event["accepted"] = False
            return f"Target y={requested:+.2f} is outside the workspace."
        self.position_y = requested
        event["accepted"] = True
        return f"Moved {self.object_name} to y={requested:+.2f}."

    @property
    def passed(self) -> bool:
        return abs(self.position_y - self.target_y) <= 0.01


def _mock_enabled() -> bool:
    return os.environ.get("RAI_TOY_MOCK", "") == "1"


def _safe_reset(path: Path) -> None:
    resolved = path.resolve()
    if resolved == Path("/tmp") or Path("/tmp") not in resolved.parents:
        raise ValueError(f"refusing to reset non-workshop path: {resolved}")
    shutil.rmtree(resolved, ignore_errors=True)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "git",
            "-c",
            "user.name=RAI Toy Workshop",
            "-c",
            "user.email=rai-toy@localhost",
            *args,
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def _opencode_config(model: str, endpoint: str) -> dict[str, Any]:
    return {
        "$schema": "https://opencode.ai/config.json",
        "model": f"lemonade/{model}",
        "small_model": f"lemonade/{model}",
        "agent": {"build": {"temperature": 0.0, "steps": 8}},
        "experimental": {"primary_tools": ["read", "edit", "bash"]},
        "provider": {
            "lemonade": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Local Lemonade",
                "options": {"baseURL": endpoint, "apiKey": "lemonade"},
                "models": {
                    model: {
                        "name": model,
                        "limit": {"context": 32768, "output": 4096},
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
                "/opt/rai-venv/bin/python probe.py*": "allow",
                "/opt/rai-venv/bin/python -m py_compile solver/*.py": "allow",
                "git diff*": "allow",
                "git status*": "allow",
            },
        },
    }


def helix_config(
    *,
    model: str = DEFAULT_MODEL,
    endpoint: str = DEFAULT_ENDPOINT,
    generations: int = 1,
    objective: str = DEFAULT_OBJECTIVE,
    background: str = DEFAULT_BACKGROUND,
) -> str:
    if generations not in {1, 2}:
        raise ValueError("workshop generations must be 1 or 2")
    if '"""' in objective or '"""' in background:
        raise ValueError("HELIX text cannot contain TOML triple quotes")
    return f'''\
objective = """{objective}"""
seed = "."
rng_seed = 23
passthrough_env = [
  "RAI_TOY_MOCK",
  "RAI_TOY_MODEL",
  "RAI_TOY_MODEL_ENDPOINT",
  "RAI_TOY_SUPPORT_DIR",
  "OPENAI_API_KEY",
]

[env]
RAI_TOY_MODEL = "{model}"
RAI_TOY_MODEL_ENDPOINT = "{endpoint}"
RAI_TOY_SUPPORT_DIR = "/ryzers/notebooks"

[evaluator]
command = "/opt/rai-venv/bin/python probe.py"
protected_files = [
  "probe.py",
  "helix.toml",
  "opencode.json",
  "CONTRACT.md",
  "scenarios.json",
]

[dataset]
train_size = 1
val_size = 1

[evolution]
max_generations = {generations}
max_evaluations = 8
minibatch_size = 1
max_workers = 1
num_parallel_proposals = 1
mutations_per_parent = 1
merge_enabled = false
cache_evaluation = true
acceptance_criterion = "strict_improvement"
frontier_type = "instance"
perfect_score_threshold = 1.0

[agent]
backend = "opencode"
model = "lemonade/{model}"
max_turns = 8
background = """{background}"""

[sandbox]
enabled = false

[worktree]
base_dir = ".helix/worktrees"
'''


def prepare_workshop(
    root: Path | str = DEFAULT_ROOT,
    *,
    model: str = DEFAULT_MODEL,
    endpoint: str = DEFAULT_ENDPOINT,
    generations: int = 1,
    reset: bool = True,
) -> Path:
    """Create the disposable prompt+tools repository."""
    root = Path(root).expanduser().resolve()
    if reset:
        _safe_reset(root)
    root.mkdir(parents=True, exist_ok=True)
    solver = root / "solver"
    solver.mkdir()
    (solver / "__init__.py").write_text("")
    (solver / "prompt.py").write_text(SEED_PROMPT)
    (solver / "tools.py").write_text(SEED_TOOLS)
    (root / "CONTRACT.md").write_text(CONTRACT)
    (root / "scenarios.json").write_text(
        json.dumps(
            {
                "splits": {
                    "train": ["train-red-cube"],
                    "val": ["val-blue-cylinder"],
                },
                "scenarios": {task_id: SCENARIOS[task_id] for task_id in ("train-red-cube", "val-blue-cylinder")},
                "test_exposed_to_evolution": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    (root / "probe.py").write_text(PROBE_SOURCE)
    (root / "opencode.json").write_text(json.dumps(_opencode_config(model, endpoint), indent=2) + "\n")
    (root / "helix.toml").write_text(
        helix_config(
            model=model,
            endpoint=endpoint,
            generations=generations,
        )
    )
    (root / ".gitignore").write_text(
        ".helix/\n.helix_artifacts/\n.helix_opencode_state/\n__pycache__/\n*.pyc\nhelix_batch.json\n"
    )
    _git(root, "init", "-b", "main")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "Seed toy RAI prompt and tools")
    return root


def ensure_model(model: str = DEFAULT_MODEL, progress: Callable[[str], None] = print) -> None:
    """Start Lemonade and load the one model used by RAI and OpenCode."""
    if _mock_enabled():
        progress(f"{MOCK_LABEL}: model startup skipped")
        return
    from capx_demo import ensure_lemonade

    ensure_lemonade(model, progress=progress)


def _literal_prompt(source: str) -> str:
    tree = ast.parse(source, filename="solver/prompt.py")
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if any(isinstance(target, ast.Name) and target.id == "SYSTEM_PROMPT" for target in targets):
            value = ast.literal_eval(node.value)
            if isinstance(value, str) and value.strip():
                return value
    raise ValueError("solver/prompt.py must define a literal non-empty SYSTEM_PROMPT")


def _mock_evaluate(task_id: str, prompt_source: str, tools_source: str) -> dict[str, Any]:
    prompt = _literal_prompt(prompt_source).lower()
    tree = ast.parse(tools_source, filename="solver/tools.py")
    functions = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    signed_target = "abs(float(target_y))" not in tools_source
    correct_prompt = "negative y is left" in prompt
    markers = {
        "literal_prompt": True,
        "correct_coordinate_prompt": correct_prompt,
        "signed_target_preserved": signed_target,
        "build_tools": "build_tools" in functions,
        "required_names": ("observe_world" in tools_source and "move_object" in tools_source),
    }
    weights = {
        "literal_prompt": 0.10,
        "correct_coordinate_prompt": 0.25,
        "signed_target_preserved": 0.45,
        "build_tools": 0.10,
        "required_names": 0.10,
    }
    score = round(sum(weights[name] for name, passed in markers.items() if passed), 6)
    return {
        "score": score,
        "passed": bool(correct_prompt and signed_target),
        "side_info": {
            "task_id": task_id,
            "benchmark_kind": MOCK_LABEL,
            "is_live_rai": False,
            "mock": True,
            "markers": markers,
            "scores": {task_id: score},
            "tool_trace": [],
            "error": None,
        },
    }


def _live_evaluate(task_id: str, prompt_source: str, tools_source: str) -> dict[str, Any]:
    scenario = SCENARIOS[task_id]
    world = ToyWorld(scenario)
    error: str | None = None
    response = ""
    started = time.monotonic()
    try:
        prompt = _literal_prompt(prompt_source)
        prompt_correct = "negative y is left" in prompt.lower()
        code = compile(tools_source, "solver/tools.py", "exec")
        module_name = "rai_toy_candidate_tools"
        module = types.ModuleType(module_name)
        sys.modules[module_name] = module
        exec(code, module.__dict__)
        build_tools = getattr(module, "build_tools", None)
        if not callable(build_tools):
            raise ValueError("solver/tools.py must define build_tools(world)")
        tools = build_tools(world)
        names = {getattr(tool, "name", None) for tool in tools}
        if names != {"observe_world", "move_object"}:
            raise ValueError(
                "build_tools must return exactly observe_world and move_object; "
                f"got {sorted(str(name) for name in names)}"
            )

        from langchain_core.messages import HumanMessage
        from langchain_core.runnables import RunnableConfig
        from langchain_openai import ChatOpenAI
        from rai.agents.langchain.core import create_conversational_agent

        llm = ChatOpenAI(
            model=os.environ.get("RAI_TOY_MODEL", DEFAULT_MODEL),
            base_url=os.environ.get("RAI_TOY_MODEL_ENDPOINT", DEFAULT_ENDPOINT),
            api_key=os.environ.get("OPENAI_API_KEY", "lemonade"),
            temperature=0.0,
            max_retries=0,
            timeout=90,
        )
        agent = create_conversational_agent(llm, tools, prompt)
        result = agent.invoke(
            {"messages": [HumanMessage(content=str(scenario["instruction"]))]},
            config=RunnableConfig({"recursion_limit": 20}),
        )
        messages = result.get("messages", [])
        if messages:
            response = str(getattr(messages[-1], "content", ""))
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        prompt_correct = False

    observed = any(event["tool"] == "observe_world" for event in world.events)
    moved = any(event["tool"] == "move_object" for event in world.events)
    negative_move = any(event["tool"] == "move_object" and float(event["target_y"]) < 0 for event in world.events)
    task_passed = world.passed and error is None
    passed = task_passed and prompt_correct
    score = 1.0 if passed else (0.10 + 0.15 * observed + 0.15 * moved + 0.30 * negative_move + 0.20 * prompt_correct)
    score = round(min(float(score), 1.0), 6)
    return {
        "score": score,
        "passed": passed,
        "side_info": {
            "task_id": task_id,
            "instruction": scenario["instruction"],
            "target_y": scenario["target_y"],
            "final_y": world.position_y,
            "tool_trace": world.events,
            "agent_response": response,
            "error": error,
            "wall_seconds": round(time.monotonic() - started, 3),
            "benchmark_kind": "rai_toy_in_memory_manipulation",
            "is_live_rai": True,
            "mock": False,
            "scores": {
                "task_success": 1.0 if task_passed else 0.0,
                "prompt_contract": 1.0 if prompt_correct else 0.0,
                "observed": 1.0 if observed else 0.0,
                "moved": 1.0 if moved else 0.0,
                "negative_move": 1.0 if negative_move else 0.0,
            },
        },
    }


def evaluate_task(root: Path, task_id: str) -> dict[str, Any]:
    if task_id not in SCENARIOS:
        raise ValueError(f"unknown task ID: {task_id}")
    prompt_source = (root / "solver" / "prompt.py").read_text()
    tools_source = (root / "solver" / "tools.py").read_text()
    compile(prompt_source, "solver/prompt.py", "exec")
    compile(tools_source, "solver/tools.py", "exec")
    if _mock_enabled():
        return _mock_evaluate(task_id, prompt_source, tools_source)
    return _live_evaluate(task_id, prompt_source, tools_source)


def _resolve_batch_ids(root: Path) -> list[str]:
    manifest = json.loads((root / "scenarios.json").read_text())
    split = os.environ.get("HELIX_SPLIT", "train")
    split_ids = list(manifest["splits"][split])
    batch_path = root / "helix_batch.json"
    raw = json.loads(batch_path.read_text()) if batch_path.exists() else ["0"]
    resolved = []
    for item in raw:
        text = str(item)
        if text in SCENARIOS:
            resolved.append(text)
        else:
            resolved.append(split_ids[int(text)])
    return resolved


def evaluate_cli(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    root = Path.cwd().resolve()
    if len(argv) == 2 and argv[0] == "--task":
        result = evaluate_task(root, argv[1])
        print("RAI_TOY_RESULT=" + json.dumps(result, separators=(",", ":")))
        return 0
    payload = []
    for task_id in _resolve_batch_ids(root):
        result = evaluate_task(root, task_id)
        side_info = dict(result["side_info"])
        side_info["passed"] = result["passed"]
        payload.append([float(result["score"]), side_info])
    print("HELIX_RESULT=" + json.dumps(payload, separators=(",", ":")))
    return 0


def run_bounded(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: float,
    env: Mapping[str, str] | None = None,
    progress: Callable[[str], None] | None = None,
) -> BoundedRun:
    started = time.monotonic()
    process = subprocess.Popen(
        list(command),
        cwd=cwd,
        env=dict(env or os.environ),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    chunks: list[str] = []
    timed_out = False
    try:
        output, _ = process.communicate(timeout=timeout_seconds)
        chunks.append(output or "")
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(process.pid, signal.SIGTERM)
        try:
            output, _ = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            output, _ = process.communicate()
        chunks.append(output or "")
    stdout = "".join(chunks)
    if progress is not None and stdout:
        for line in stdout.splitlines():
            progress(line)
    return BoundedRun(
        returncode=124 if timed_out else int(process.returncode),
        timed_out=timed_out,
        stdout=stdout,
        elapsed_seconds=time.monotonic() - started,
    )


def _evaluator_python() -> str:
    if _mock_enabled() or not RAI_PYTHON.exists():
        return sys.executable
    return str(RAI_PYTHON)


def score_candidate(
    root: Path | str,
    task_id: str = "test-green-cube",
    *,
    timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    """Evaluate one explicit toy scenario in a bounded subprocess."""
    root = Path(root).resolve()
    completed = run_bounded(
        [_evaluator_python(), "probe.py", "--task", task_id],
        cwd=root,
        timeout_seconds=timeout_seconds,
        env={
            **os.environ,
            "RAI_TOY_SUPPORT_DIR": str(SUPPORT_DIR),
        },
    )
    if completed.timed_out:
        raise TimeoutError(f"RAI toy evaluation exceeded {timeout_seconds}s")
    if completed.returncode != 0:
        raise RuntimeError(completed.stdout)
    marker = "RAI_TOY_RESULT="
    lines = [line for line in completed.stdout.splitlines() if line.startswith(marker)]
    if len(lines) != 1:
        raise RuntimeError(f"missing {marker} in evaluator output:\n{completed.stdout}")
    return json.loads(lines[0][len(marker) :])


def run_helix(
    root: Path | str = DEFAULT_ROOT,
    *,
    generations: int = 1,
    timeout_seconds: float = DEFAULT_TIMEOUT,
    progress: Callable[[str], None] = print,
) -> BoundedRun:
    root = Path(root).resolve()
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
    return run_bounded(
        command,
        cwd=root,
        timeout_seconds=timeout_seconds,
        env=os.environ.copy(),
        progress=progress,
    )


def source_diff(before: Path | str, after: Path | str) -> str:
    before, after = Path(before), Path(after)
    chunks: list[str] = []
    for name in ("prompt.py", "tools.py"):
        old = (before / "solver" / name).read_text().splitlines(keepends=True)
        new = (after / "solver" / name).read_text().splitlines(keepends=True)
        chunks.extend(
            difflib.unified_diff(
                old,
                new,
                fromfile=f"seed/solver/{name}",
                tofile=f"best/solver/{name}",
            )
        )
    return "".join(chunks)


def export_best(root: Path | str = DEFAULT_ROOT) -> Path:
    root = Path(root).resolve()
    destination = root.parent / "live_best"
    _safe_reset(destination)
    completed = subprocess.run(
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
    return destination if completed.returncode == 0 and destination.is_dir() else root


def summarize_run(root: Path | str = DEFAULT_ROOT) -> dict[str, Any]:
    root = Path(root).resolve()
    best = export_best(root)
    difference = source_diff(root, best)
    state_path = root / ".helix" / "state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    return {
        "accepted": bool(difference.strip()),
        "improved_best": bool(difference.strip()),
        "best": str(best),
        "diff": difference,
        "frontier": state.get("frontier", []),
        "prompt": (best / "solver" / "prompt.py").read_text(),
        "tools": (best / "solver" / "tools.py").read_text(),
    }


def _main(argv: Sequence[str]) -> int:
    if argv and argv[0] == "prepare":
        print(prepare_workshop())
        return 0
    if argv and argv[0] == "evaluate":
        return evaluate_cli(argv[1:])
    print("usage: rai_toy_demo.py {prepare|evaluate --task TASK_ID}")
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
