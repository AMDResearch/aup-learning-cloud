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
import re  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
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

# Lemonade and CaP-X need different Hugging Face caches. The CaP-X interpreter
# points HF_HOME at the baked perception weights; the Lemonade subprocess
# explicitly switches to the image-baked GGUF cache.
LEMONADE_CACHE = os.environ.get(
    "LEMONADE_CACHE", "/opt/lemonade-cache/lemonade"
)
LEMONADE_HF_HOME = os.environ.get(
    "LEMONADE_HF_HOME", "/opt/lemonade-cache/huggingface"
)

# Scratch space for the episode videos and the benchmark artifacts
WORK = Path("/tmp/capx_notebook")

TRIAL_DIR = re.compile(r"trial_(\d+)_sandboxrc_(\d+)_reward_([\d.]+)_taskcompleted_(\d)")


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
    progress("  loading from the image cache (custom models download on first use)")

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
        env={
            **os.environ,
            "HF_HOME": LEMONADE_HF_HOME,
            "LEMONADE_CACHE": LEMONADE_CACHE,
            "LEMONADE_HF_HOME": LEMONADE_HF_HOME,
        },
    )
    load_error = None
    for line in proc.stdout:
        rendered = line.rstrip()
        progress(f"  {rendered}")
        if "Error loading model:" in rendered:
            load_error = rendered
    proc.wait()

    if load_error is not None:
        raise RuntimeError(load_error)
    if proc.returncode != 0 or not lemonade_alive():
        raise RuntimeError(
            f"{LEMONADE_ENV} --serve-only {model} failed (exit {proc.returncode}) "
            "- see /tmp/lemond.log"
        )
    progress(f"{model} is loaded and serving on port {LEMONADE_PORT}")


# ---------------------------------------------------------------------------
# Watching an episode
# ---------------------------------------------------------------------------


def show_video(env, name: str = "notebook_run", width: int = 640) -> str | None:
    """Encode the frames captured during the last step and play them inline.

    env.get_video_frames returns raw frames, so this is the encode-and-embed
    dance rather than anything about CaP-X.
    """
    from capx.utils.video_utils import _write_video
    from IPython.display import Video, display

    frames = env.get_video_frames(clear=True)
    if not frames:
        print("no frames captured - was enable_video_capture called before the step?")
        return None

    WORK.mkdir(parents=True, exist_ok=True)
    _write_video(frames, str(WORK), suffix=name)
    path = str(WORK / f"video_{name}.mp4")
    display(Video(path, embed=True, width=width))
    return path


def _ffmpeg() -> str:
    """The ffmpeg binary, preferring the one imageio ships with."""
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _scaled(video: Path, dest: Path, width: int) -> Path:
    """Scale a clip down for embedding, falling back to the original.

    -2 keeps the aspect ratio and rounds the height to an even number, which
    h264 requires. -an drops the (silent) audio track. A missing ffmpeg raises
    rather than returning non-zero, so both failures are caught here.
    """
    try:
        done = subprocess.run(
            [_ffmpeg(), "-y", "-loglevel", "error", "-i", str(video),
             "-vf", f"scale={width}:-2", "-an", str(dest)],
            capture_output=True, text=True,
        )
    except OSError:
        return video
    return dest if done.returncode == 0 and dest.exists() else video


def show_trial_grid(trials: list[dict], width: int = 240, progress=print) -> None:
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
    for t in trials:
        video = next(iter(sorted(t["dir"].glob("video_combined*.mp4"))), None)
        caption = f"trial {t['trial']} · reward {t['reward']:.3f}"
        caption += " · solved" if t["solved"] else ""

        if video is None:
            figures.append(
                f'<figure style="margin:0;text-align:center;font:12px/1.4 sans-serif">'
                f'<div style="width:{width}px;height:{width * 3 // 4}px;display:flex;'
                f'align-items:center;justify-content:center;border:1px dashed currentColor;'
                f'opacity:.5">no video</div><figcaption>{caption}</figcaption></figure>'
            )
            continue

        source = _scaled(video, thumbs / f"trial_{t['trial']}.mp4", width)
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


def benchmark(
    model: str,
    server_url: str,
    config_path: str,
    temperature: float = 0.2,
    max_tokens: int = 16384,
    trials: int = 5,
    oracle: bool = False,
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

    proc = subprocess.Popen(
        cmd, cwd=str(CAPX_ROOT), stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    for line in proc.stdout:
        progress(line.rstrip())
    proc.wait()

    return read_results(out_dir, model, progress=progress)


def read_results(out_dir: Path, model: str, progress=print) -> list[dict]:
    """Collect the per-trial artifacts launch.py just wrote.

    Every trial gets a directory whose name carries its result, and the run
    splices the model name into the path so a second model does not overwrite
    the first. That is why the results are not where --output-dir said.
    """
    root = out_dir.parent / model.replace("/", "_") / out_dir.name
    if not root.is_dir():
        # Upstream may sanitise the model name differently; take the newest.
        found = sorted(out_dir.parent.glob(f"*/{out_dir.name}"), key=lambda p: p.stat().st_mtime)
        if not found:
            progress(f"no results under {out_dir.parent}")
            return []
        root = found[-1]

    summary = root / "summaries.txt"
    if summary.exists():
        progress("\n" + summary.read_text())

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
