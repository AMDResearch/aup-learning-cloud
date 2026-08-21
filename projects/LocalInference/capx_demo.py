# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Setup and reporting helpers for 04_code_as_policies_with_capx.ipynb.
#
# The notebook drives CaP-X through the framework's own API: LaunchArgs,
# _load_config, _start_api_servers, instantiate, ModelQueryArgs, query_model and
# env.step. Reading those calls is the point of the notebook, so what lives here
# is only what would bury them - the process setup a Jupyter kernel does not
# inherit, the Lemonade bring-up that notebooks 02 and 03 already covered, and
# the frame-by-frame video and artifact plumbing around a run.

import os

# MuJoCo picks its GL backend at import time and only once, so this has to be
# set before anything below reaches mujoco. EGL renders on the AMD GPU with no
# display attached. The CaP-X kernel sets it too; this is what also makes the
# module importable from a plain terminal python.
os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")

import base64  # noqa: E402
import contextlib  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import warnings  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
import requests  # noqa: E402

CAPX_ROOT = Path(os.environ.get("CAPX_ROOT", "/ryzers/cap-x"))

# capx resolves config paths, robot assets and controller configs relative to
# the repo root, which is why every launch.py invocation in the README is
# preceded by a cd. A kernel starts in the notebook's directory instead.
if CAPX_ROOT.is_dir():
    os.chdir(CAPX_ROOT)

try:
    import capx  # noqa: F401,E402
except ModuleNotFoundError as exc:
    raise RuntimeError(
        "The CaP-X stack is not on this interpreter's path. In Jupyter, pick the "
        "'CaP-X (ROCm)' kernel from the menu in the top right."
    ) from exc

LEMONADE_PORT = 13305
DEFAULT_MODEL = "Gemma-4-E2B-it-GGUF"

# The script notebook 03 sources in a terminal, reused here for its --serve-only half
LEMONADE_ENV = Path(os.environ.get("LEMONADE_ENV", "/ryzers/lemonade_env.sh"))

# The image bakes the default GGUF here (see the LocalInference Dockerfile).
# The CaP-X kernel sets HF_HOME to its own perception cache, so lemond is
# pointed back at the model cache explicitly when this kernel starts it.
LEMONADE_CACHE = os.environ.get("LEMONADE_CACHE", "/opt/lemonade-cache")

# Scratch space for the episode videos and the benchmark artifacts
WORK = Path("/tmp/capx_notebook")

# CaP-X writes every clip at 30 fps (video_utils._write_video, not configurable)
# and an episode is only a few dozen frames, so a trial flashes past in about a
# second. Everything shown here is re-timed to PLAYBACK_FPS instead, which is
# for watching the arm rather than for real-time fidelity.
SOURCE_FPS = 30
PLAYBACK_FPS = 10

TRIAL_DIR = re.compile(r"trial_(\d+)_sandboxrc_(\d+)_reward_([\d.]+)_taskcompleted_(\d)")

# Robosuite tasks that all ground with SAM3 and declare a subset of the
# perception servers the notebook already started, so benchmark_scenarios can
# run each one without starting anything new. Keyed by a short label used in the
# table and captions. Picking a config for a new task means checking its
# api_servers block first: several ship variants that want SAM2 or OWL-ViT,
# which this image does not carry, or set use_img_differencing, which expects a
# hosted vision model on a port nothing here listens on.
SCENARIOS = {
    "cube stack": "env_configs/cube_stack/franka_robosuite_cube_stack.yaml",
    "cube restack": "env_configs/cube_restack/franka_robosuite_cube_restack.yaml",
    "cube lift": "env_configs/cube_lifting/franka_robosuite_cube_lifting.yaml",
    "nut assembly": "env_configs/nut_assembly/franka_robosuite_nut_assembly.yaml",
    "spill wipe": "env_configs/spill_wipe/franka_robosuite_spill_wipe.yaml",
    "two arm handover": "env_configs/two_arm_handover/two_arm_handover.yaml",
}


# ---------------------------------------------------------------------------
# Keeping the cell output readable
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def quiet(log: str | Path = WORK / "setup.log"):
    """Send everything written inside the block to `log` instead of the cell.

    Bringing the stack up prints a few hundred lines that say nothing about
    CaP-X: robosuite's macro warnings, Open3D's WebRTC banner, jax probing for
    backends it will not find, and three uvicorn servers announcing themselves.
    None of it is configurable upstream, so it is diverted rather than silenced.

    Both layers have to move. Python's own `print` goes through sys.stdout,
    which Jupyter has already replaced with a socket, while C libraries and the
    perception subprocesses write to file descriptors 1 and 2 directly. The
    subprocesses inherit the redirected descriptors, so their logs keep landing
    in the file for the rest of the session, which is also what keeps the later
    cells clean. Read the file if a server misbehaves.
    """
    log = Path(log)
    log.parent.mkdir(parents=True, exist_ok=True)
    sink = open(log, "a", buffering=1)
    saved = (os.dup(1), os.dup(2))

    sys.stdout.flush()
    sys.stderr.flush()
    os.dup2(sink.fileno(), 1)
    os.dup2(sink.fileno(), 2)
    try:
        with (
            contextlib.redirect_stdout(sink),
            contextlib.redirect_stderr(sink),
            warnings.catch_warnings(),
        ):
            warnings.simplefilter("ignore")
            yield log
    finally:
        sink.flush()
        os.dup2(saved[0], 1)
        os.dup2(saved[1], 2)
        os.close(saved[0])
        os.close(saved[1])
        sink.close()


# ---------------------------------------------------------------------------
# The model server
# ---------------------------------------------------------------------------


def lemonade_alive(timeout: float = 2.0) -> bool:
    try:
        return requests.get(
            f"http://localhost:{LEMONADE_PORT}/api/v1/health", timeout=timeout
        ).ok
    except requests.RequestException:
        return False


def ensure_lemonade(model: str = DEFAULT_MODEL, progress=print) -> None:
    """Serve the model, by handing off to the script that already knows how.

    lemonade_env.sh is the same script notebook 03 sources in a terminal, and
    its --serve-only path is exactly the part CaP-X needs: start lemond if it is
    down, wait for it, load the model. The rest of that script rewrites RAI's
    config.toml and sources the ROS overlay, which is why this runs it in a
    subshell with the flag rather than trying to source it into the kernel.

    Safe to call again, since every step in there is a no-op once done.
    """
    if lemonade_alive():
        progress(f"Lemonade is already up on port {LEMONADE_PORT}, loading {model}...")
    else:
        progress(f"Starting Lemonade and loading {model}...")
    progress("  the first load downloads the GGUF and takes a few minutes")

    # Streamed rather than captured: the download prints nothing until it
    # finishes, and a silent cell for several minutes reads as a hang. stdin is
    # closed so a prompt fails loudly instead of blocking forever, and setsid
    # leaves lemond orphaned onto PID 1 so a kernel restart does not kill it.
    proc = subprocess.Popen(
        ["setsid", "bash", str(LEMONADE_ENV), "--serve-only", model],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env={**os.environ, "HF_HOME": LEMONADE_CACHE},
    )
    for line in proc.stdout:
        progress(f"  {line.rstrip()}")
    proc.wait()

    if proc.returncode != 0 or not lemonade_alive():
        raise RuntimeError(
            f"{LEMONADE_ENV} --serve-only {model} failed (exit {proc.returncode}) "
            "- see /tmp/lemond.log"
        )
    progress(f"{model} is loaded and serving on port {LEMONADE_PORT}")


# ---------------------------------------------------------------------------
# Watching an episode
# ---------------------------------------------------------------------------


def show_video(
    env, name: str = "notebook_run", width: int = 640, fps: int = PLAYBACK_FPS
) -> str | None:
    """Encode the frames captured during the last step and play them inline.

    env.get_video_frames returns raw frames, so this is the encode-and-embed
    dance rather than anything about CaP-X. The frames are written here rather
    than through video_utils._write_video only because that helper fixes fps at
    30, which is too quick to follow for an episode this short.
    """
    import imageio.v2 as imageio
    from IPython.display import Video, display

    frames = env.get_video_frames(clear=True)
    if not frames:
        print("no frames captured - was enable_video_capture called before the step?")
        return None

    WORK.mkdir(parents=True, exist_ok=True)
    path = WORK / f"video_{name}.mp4"
    with imageio.get_writer(path, fps=fps, format="FFMPEG", codec="libx264") as writer:
        for frame in frames:
            writer.append_data(np.ascontiguousarray(frame))
    print(f"Saved interaction video to {path} ({len(frames)} frames at {fps} fps)")

    display(Video(str(path), embed=True, width=width))
    return str(path)


def _ffmpeg() -> str:
    """The ffmpeg binary, preferring the one imageio ships with."""
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _scaled(video: Path, dest: Path, width: int, fps: int = PLAYBACK_FPS) -> Path:
    """Scale a clip down and slow it for embedding, falling back to the original.

    -2 keeps the aspect ratio and rounds the height to an even number, which
    h264 requires. setpts stretches the presentation timestamps, which is what
    slows a clip already written at SOURCE_FPS without re-rendering or dropping
    a frame. -an drops the (silent) audio track. A missing ffmpeg raises rather
    than returning non-zero, so both failures are caught here.
    """
    slow = SOURCE_FPS / fps
    try:
        done = subprocess.run(
            [_ffmpeg(), "-y", "-loglevel", "error", "-i", str(video),
             "-vf", f"scale={width}:-2,setpts={slow}*PTS", "-an", str(dest)],
            capture_output=True, text=True,
        )
    except OSError:
        return video
    return dest if done.returncode == 0 and dest.exists() else video


def show_trial_grid(
    trials: list[dict], width: int = 240, fps: int = PLAYBACK_FPS, progress=print
) -> None:
    """Every trial's episode, side by side, captioned with its reward.

    Each clip is scaled down first and then embedded in the page, because a
    notebook cannot play a file from /tmp: the browser never sees that path.
    Scaling is what keeps five embedded videos smaller than one full-size one.
    """
    from IPython.display import HTML, display

    thumbs = WORK / "thumbs"
    thumbs.mkdir(parents=True, exist_ok=True)

    figures = []
    embedded = 0
    for i, t in enumerate(trials):
        # A scenario run carries a label; a single-task run carries a trial index
        title = t.get("label", f"trial {t.get('trial', i)}")
        video = None
        if t.get("dir") is not None:
            video = next(iter(sorted(t["dir"].glob("video_combined*.mp4"))), None)
        caption = f"{title} · reward {t['reward']:.3f}"
        caption += " · solved" if t["solved"] else ""

        if video is None:
            figures.append(
                f'<figure style="margin:0;text-align:center;font:12px/1.4 sans-serif">'
                f'<div style="width:{width}px;height:{width * 3 // 4}px;display:flex;'
                f'align-items:center;justify-content:center;border:1px dashed currentColor;'
                f'opacity:.5">no video</div><figcaption>{caption}</figcaption></figure>'
            )
            continue

        safe = re.sub(r"[^0-9A-Za-z]+", "_", title)
        source = _scaled(video, thumbs / f"{i}_{safe}.mp4", width, fps)
        if source is video:
            progress(f"  could not scale {video.name}, embedding it as it is")

        data = base64.b64encode(source.read_bytes()).decode()
        embedded += len(data)
        figures.append(
            f'<figure style="margin:0;text-align:center;font:12px/1.4 sans-serif">'
            f'<video src="data:video/mp4;base64,{data}" width="{width}" '
            f'controls loop muted playsinline></video>'
            f"<figcaption>{caption}</figcaption></figure>"
        )

    # Half the clips on top and the rest centred underneath, so five trials
    # read as a pyramid rather than as a row that wraps wherever it happens to.
    def row(items: list[str]) -> str:
        return (
            '<div style="display:flex;flex-wrap:wrap;gap:12px;justify-content:center;'
            'align-items:flex-start;margin-bottom:12px">' + "".join(items) + "</div>"
        )

    top = (len(figures) + 1) // 2
    display(HTML(row(figures[:top]) + (row(figures[top:]) if len(figures) > top else "")))
    progress(f"{len(figures)} episodes, {embedded / 1e6:.1f} MB embedded in this notebook")


# ---------------------------------------------------------------------------
# The benchmark
# ---------------------------------------------------------------------------


class _RunFilter:
    """Keep the lines of a launch.py run that say something about the model.

    A run brings the whole stack up again in its own process, so it reprints
    every warning from the setup cell, logs each request the perception servers
    answer, and echoes the program's prints twice: once as they happen and
    again inside the environment's response. What is left once those are gone
    is the progress bar, the program the model wrote, the verdict on it and the
    run summary. Callers take verbose=True to see everything instead.

    Stateful, because these are blocks rather than lines: one instance per run.
    """

    SECTIONS = ("Generated program:", "Environment response:", "Summary Statistics:")
    FIELDS = (
        "Sandbox failed:", "Stdout:", "Stderr:", "Reward:", "Task Completed:",
        "Terminated:", "Num Regenerations:", "Num Finishes:", "Num Code Blocks:",
    )

    def __init__(self):
        self._section = None
        self._in_stderr = False

    def __call__(self, line: str) -> str | None:
        stripped = line.strip()

        # The bar, and the rules that frame a trial
        if stripped.startswith("Running Trials") or (stripped and set(stripped) == {"-"}):
            self._section = None
            return line

        for name in self.SECTIONS:
            if stripped.startswith(name):
                self._section, self._in_stderr = name, False
                return line

        if self._section == "Generated program:":
            return line

        if self._section == "Environment response:":
            field = next((f for f in self.FIELDS if stripped.startswith(f)), None)
            if field is not None:
                # Stdout is the program's own prints, already read above
                self._in_stderr = field == "Stderr:"
                return None if field == "Stdout:" else line
            # A traceback is the only continuation worth keeping
            return line if self._in_stderr and stripped else None

        if self._section == "Summary Statistics:":
            if stripped.startswith("Elapsed time:"):
                self._section = None
            return line

        return None


def benchmark(
    model: str,
    server_url: str,
    config_path: str,
    temperature: float = 0.2,
    max_tokens: int = 16384,
    trials: int = 5,
    oracle: bool = False,
    verbose: bool = False,
    progress=print,
) -> list[dict]:
    """Run launch.py over N layouts and report the success rate.

    launch.py is the framework's own entry point, so it starts its own servers.
    The notebook's are already listening, so it finds those ports busy and skips
    them.

    Keep one worker: Lemonade serves one request at a time and the perception
    servers serialise GPU access, so more only queue. With oracle=True the
    hand-written reference program runs instead of the model, which is the
    control to reach for when a result looks wrong.
    """
    out_dir = WORK / "eval"
    cmd = [
        sys.executable, "capx/envs/launch.py",
        "--config-path", config_path,
        "--model", model,
        "--server-url", server_url,
        "--temperature", str(temperature),
        "--max-tokens", str(max_tokens),
        "--total-trials", str(trials),
        "--num-workers", "1",
        "--output-dir", str(out_dir),
    ]
    if oracle:
        cmd.append("--use-oracle-code")
    progress(" ".join(cmd) + "\n")

    keep = (lambda line: line) if verbose else _RunFilter()
    proc = subprocess.Popen(
        cmd, cwd=str(CAPX_ROOT), stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    for line in proc.stdout:
        shown = keep(line.rstrip())
        if shown is not None:
            progress(shown)
    proc.wait()

    return read_results(out_dir, model, progress=progress)


def read_results(out_dir: Path, model: str, progress=print) -> list[dict]:
    """Collect the per-trial artifacts launch.py just wrote.

    Every trial gets a directory whose name carries its result, and the run
    splices the model name into the path so a second model does not overwrite
    the first. That is why the results are not where --output-dir said.

    Only the per-trial table is printed here. summaries.txt next to it holds a
    copy of the Summary Statistics the run already printed on its way past.
    """
    root = out_dir.parent / model.replace("/", "_") / out_dir.name
    if not root.is_dir():
        # Upstream may sanitise the model name differently; take the newest.
        found = sorted(out_dir.parent.glob(f"*/{out_dir.name}"), key=lambda p: p.stat().st_mtime)
        if not found:
            progress(f"no results under {out_dir.parent}")
            return []
        root = found[-1]

    trials = []
    for d in sorted(root.glob("trial_*")):
        m = TRIAL_DIR.match(d.name)
        if m:
            trials.append({
                "trial": int(m[1]),
                "error": m[2] != "0",
                "reward": float(m[3]),
                "solved": m[4] == "1",
                "dir": d,
            })

    progress(f"{'trial':>5} {'sandbox':>8} {'reward':>7} {'solved':>7}")
    for t in trials:
        progress(
            f"{t['trial']:>5} {'error' if t['error'] else 'ok':>8} "
            f"{t['reward']:>7.3f} {str(t['solved']):>7}"
        )
    if trials:
        solved = sum(t["solved"] for t in trials)
        mean = np.mean([t["reward"] for t in trials])
        progress(f"\nsuccess rate: {solved}/{len(trials)}   mean reward: {mean:.3f}")
    return trials


def benchmark_scenarios(
    model: str,
    server_url: str,
    scenarios: dict | None = None,
    temperature: float = 0.2,
    max_tokens: int = 16384,
    oracle: bool = False,
    verbose: bool = False,
    progress=print,
) -> list[dict]:
    """Run one episode of each of several different tasks, side by side.

    Where benchmark() reruns one task over reseeded layouts, this runs a
    different task per entry, which is a broader read on the model since each
    task needs a different program. Every task grounds with SAM3 and reuses the
    servers already started; each runs in its own output dir so the single
    trials cannot collide. A task that fails to run is recorded and the rest
    continue.
    """
    scenarios = scenarios or SCENARIOS
    results = []
    for label, config_path in scenarios.items():
        progress(f"\n===== {label}: {config_path} =====")
        out_dir = WORK / "scenarios" / re.sub(r"[^0-9A-Za-z]+", "_", label)
        cmd = [
            sys.executable, "capx/envs/launch.py",
            "--config-path", config_path,
            "--model", model,
            "--server-url", server_url,
            "--temperature", str(temperature),
            "--max-tokens", str(max_tokens),
            "--total-trials", "1",
            "--num-workers", "1",
            "--output-dir", str(out_dir),
        ]
        if oracle:
            cmd.append("--use-oracle-code")

        keep = (lambda line: line) if verbose else _RunFilter()
        proc = subprocess.Popen(
            cmd, cwd=str(CAPX_ROOT), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        for line in proc.stdout:
            shown = keep(line.rstrip())
            if shown is not None:
                progress(shown)
        proc.wait()

        # read_results prints its own one-line table; silence it and re-report below
        got = read_results(out_dir, model, progress=lambda *a, **k: None)
        entry = got[0] if got else {"reward": 0.0, "solved": False, "error": True, "dir": None}
        entry["label"] = label
        results.append(entry)

    progress(f"\n{'scenario':<14}{'sandbox':>8}{'reward':>8}{'solved':>8}")
    for r in results:
        progress(
            f"{r['label']:<14}{'error' if r.get('error') else 'ok':>8}"
            f"{r['reward']:>8.3f}{str(r['solved']):>8}"
        )
    solved = sum(r["solved"] for r in results)
    progress(f"\nsolved {solved}/{len(results)} scenarios")
    return results
