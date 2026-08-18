"""Headless MuJoCo GL setup backed by pixi-installed Mesa.

Rendering must run in a process started with `LD_LIBRARY_PATH` already
pointing at the pixi libraries. The dynamic loader captures its search path at
process start, so exporting the variable from inside a running interpreter is
too late for the `dlopen` calls MuJoCo makes.

Backends are probed in order because which one works depends on the Mesa build:

- `osmesa` needs `libOSMesa.so.8`, which mesalib provides only before 25.1.
- the EGL backends need `EGL_EXT_platform_device`, which Mesa's software
  renderer does not always expose.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Set in child environments so a re-executed process does not loop.
CONFIGURED_FLAG = "HEADLESS_GL_CONFIGURED"

# Backend name -> variables that select it. Every GL variable listed in any
# candidate is cleared first, so candidates never inherit each other's state.
BACKEND_CANDIDATES: tuple[tuple[str, dict[str, str]], ...] = (
    (
        "osmesa",
        {"MUJOCO_GL": "osmesa", "PYOPENGL_PLATFORM": "osmesa"},
    ),
    (
        "egl-surfaceless",
        {
            "MUJOCO_GL": "egl",
            "PYOPENGL_PLATFORM": "egl",
            "LIBGL_ALWAYS_SOFTWARE": "1",
            "EGL_PLATFORM": "surfaceless",
        },
    ),
    (
        "egl-device",
        {
            "MUJOCO_GL": "egl",
            "PYOPENGL_PLATFORM": "egl",
            "LIBGL_ALWAYS_SOFTWARE": "1",
            "EGL_PLATFORM": "device",
        },
    ),
    (
        "egl-default",
        {
            "MUJOCO_GL": "egl",
            "PYOPENGL_PLATFORM": "egl",
            "LIBGL_ALWAYS_SOFTWARE": "1",
        },
    ),
)

DEFAULT_BACKEND = BACKEND_CANDIDATES[0][0]

_BACKEND_KEYS = (
    "MUJOCO_GL",
    "PYOPENGL_PLATFORM",
    "LIBGL_ALWAYS_SOFTWARE",
    "EGL_PLATFORM",
)

_GL_ENV_KEYS = (
    *_BACKEND_KEYS,
    "LD_LIBRARY_PATH",
    "MESA_LOADER_DRIVER_OVERRIDE",
    "GALLIUM_DRIVER",
    "LIBGL_DRIVERS_PATH",
    "__EGL_VENDOR_LIBRARY_FILENAMES",
    CONFIGURED_FLAG,
)

_PROBE_CODE = (
    "import mujoco\n"
    "model = mujoco.MjModel.from_xml_string('<mujoco><worldbody/></mujoco>')\n"
    "renderer = mujoco.Renderer(model, height=64, width=64)\n"
    "renderer.render()\n"
    "renderer.close()\n"
    "print('probe ok')\n"
)


def pixi_env_root(repo_root: Path) -> Path:
    return repo_root / ".pixi/envs/default"


def pixi_lib_dir(repo_root: Path) -> Path:
    return pixi_env_root(repo_root) / "lib"


def build_gl_env(repo_root: Path, backend: str = DEFAULT_BACKEND) -> dict[str, str]:
    """Environment for rendering with the named backend."""
    overrides = dict(BACKEND_CANDIDATES).get(backend)
    if overrides is None:
        raise ValueError(f"Unknown backend {backend!r}")

    env = os.environ.copy()
    for key in _BACKEND_KEYS:
        env.pop(key, None)

    pixi_env = pixi_env_root(repo_root)
    pixi_lib = pixi_lib_dir(repo_root)
    if not pixi_lib.is_dir():
        env["MUJOCO_GL"] = "disable"
        return env

    env["LD_LIBRARY_PATH"] = str(pixi_lib) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    env["MESA_LOADER_DRIVER_OVERRIDE"] = "llvmpipe"
    env["GALLIUM_DRIVER"] = "llvmpipe"
    env.update(overrides)

    dri = pixi_lib / "dri"
    if dri.is_dir():
        env["LIBGL_DRIVERS_PATH"] = str(dri)

    for vendor in (
        pixi_env / "share/glvnd/egl_vendor.d/50_mesa.json",
        pixi_lib / "egl_vendor.d/50_mesa.json",
    ):
        if vendor.is_file():
            env["__EGL_VENDOR_LIBRARY_FILENAMES"] = str(vendor)
            break

    env[CONFIGURED_FLAG] = "1"
    return env


def apply_gl_env(env: dict[str, str]) -> None:
    """Copy GL variables into this process, for reporting and child processes.

    This does not make rendering work in the current interpreter; `dlopen`
    ignores `LD_LIBRARY_PATH` changes made after process start.
    """
    for key in _GL_ENV_KEYS:
        if key in env:
            os.environ[key] = env[key]
        else:
            os.environ.pop(key, None)


def probe_render_subprocess(
    repo_root: Path,
) -> tuple[bool, str, dict[str, str] | None]:
    """Find a backend that can render, by trying each one in a fresh process.

    Returns whether rendering worked, a description of the outcome, and the
    environment that succeeded.
    """
    if not pixi_lib_dir(repo_root).is_dir():
        return False, "pixi libraries missing — run notebook section 1.5 first", None

    failures = []
    for backend, _ in BACKEND_CANDIDATES:
        env = build_gl_env(repo_root, backend)
        result = subprocess.run(
            [sys.executable, "-c", _PROBE_CODE],
            env=env,
            capture_output=True,
            text=True,
            cwd=repo_root,
        )
        if result.returncode == 0:
            return True, backend, env
        error = (result.stderr or result.stdout or "no output").strip()
        failures.append(f"--- {backend} ---\n{error[-600:]}")

    return False, "\n\n".join(failures), None


def resolve_gl_env(repo_root: Path) -> dict[str, str]:
    """Environment that renders successfully, or the first candidate."""
    ok, _, env = probe_render_subprocess(repo_root)
    if ok and env is not None:
        return env
    return build_gl_env(repo_root)


def reexec_with_gl_env(repo_root: Path) -> None:
    """Restart this process so the dynamic loader sees the pixi GL libraries."""
    if os.environ.get(CONFIGURED_FLAG) == "1":
        return
    os.execve(sys.executable, [sys.executable, *sys.argv], resolve_gl_env(repo_root))
