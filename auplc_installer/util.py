# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Common helpers: subprocess running, sudo handling, sha256, logging."""

from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

# ----------------------------------------------------------------------
# Output-verbosity flag
# ----------------------------------------------------------------------
#
# Controls whether ``run_streaming`` prints subprocess output live (verbose)
# or buffers it to a log file and only surfaces it when the command fails
# (quiet, the default for a "progress-bar style" installer experience).

_VERBOSE: bool = os.environ.get("AUPLC_VERBOSE") == "1"


def set_verbose(verbose: bool) -> None:
    """Set the global verbose flag (typically from CLI ``--verbose`` parsing)."""
    global _VERBOSE
    _VERBOSE = bool(verbose)


def is_verbose() -> bool:
    return _VERBOSE


class InstallerError(RuntimeError):
    """Domain error raised by the installer.

    Caught at the top of ``cli.main`` and converted into a non-zero exit
    with a friendly error message — never a Python traceback for the user.
    """


# ----------------------------------------------------------------------
# Subprocess wrappers
# ----------------------------------------------------------------------


def _build_cmd(cmd: Sequence[str], *, sudo: bool) -> list[str]:
    if sudo and os.geteuid() != 0:
        return ["sudo", *cmd]
    return list(cmd)


def run(
    cmd: Sequence[str],
    *,
    sudo: bool = False,
    check: bool = True,
    env: Mapping[str, str] | None = None,
    cwd: str | Path | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a command synchronously, optionally with sudo, raise on failure.

    Output handling honours the global ``VERBOSE`` flag and the active
    progress stage:

      * Verbose: stdout/stderr stream live to the user (legacy bash
        behaviour, useful for debugging).
      * Quiet (default), no active stage: output is captured silently
        and only dumped on failure.
      * Quiet (default), inside ``with stage(...)``: output is captured
        AND each line is fed into the stage's live "tail" so the user
        sees what's happening just below the spinner. The tail clears
        when the stage ends.

    Mirrors bash ``set -e`` semantics: ``check=True`` (default) raises
    ``InstallerError`` when the command exits non-zero.
    """
    full = _build_cmd(cmd, sudo=sudo)

    if _VERBOSE or input_text is not None:
        # Verbose path or stdin-feeding path: subprocess.run is fine
        # (Popen with stdin pipes complicates feeding ``input_text``).
        popen_kwargs: dict[str, object] = {
            "check": False,
            "env": dict(env) if env is not None else None,
            "cwd": str(cwd) if cwd is not None else None,
            "text": True,
            "input": input_text,
        }
        if not _VERBOSE:
            # Quiet but with input_text: still capture for failure dump.
            popen_kwargs["stdout"] = subprocess.PIPE
            popen_kwargs["stderr"] = subprocess.STDOUT
        try:
            result = subprocess.run(full, **popen_kwargs)
        except FileNotFoundError as exc:
            raise InstallerError(f"Command not found: {full[0]}") from exc
        if check and result.returncode != 0:
            if not _VERBOSE and result.stdout:
                _dump_captured_output(full, result.returncode, result.stdout)
            raise InstallerError(f"Command failed (exit {result.returncode}): {' '.join(full)}")
        return result

    # Quiet mode without input_text: stream via Popen so we can feed
    # each line into the active progress stage's live tail.
    from auplc_installer.progress import current_stage

    runner = current_stage()
    captured: list[str] = []

    try:
        proc = subprocess.Popen(
            full,
            env=dict(env) if env is not None else None,
            cwd=str(cwd) if cwd is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as exc:
        raise InstallerError(f"Command not found: {full[0]}") from exc

    assert proc.stdout is not None
    for line in proc.stdout:
        captured.append(line)
        if runner is not None:
            runner.append_output(line)
    rc = proc.wait()

    if check and rc != 0:
        _dump_captured_output(full, rc, "".join(captured))
        raise InstallerError(f"Command failed (exit {rc}): {' '.join(full)}")
    return subprocess.CompletedProcess(args=full, returncode=rc, stdout="".join(captured), stderr=None)


def _dump_captured_output(full_cmd: Sequence[str], rc: int, output: str) -> None:
    """Emit the captured-output footer used after a failed quiet command.

    Clears the active stage's live region first so the dump appears on a
    clean stretch of terminal, not interleaved with the leftover spinner
    + tail from the moment of failure.
    """
    from auplc_installer.colors import dim
    from auplc_installer.progress import current_stage

    runner = current_stage()
    if runner is not None:
        runner.clear_live_region()

    print()
    print(f"--- Captured output of: {' '.join(full_cmd)} (exit {rc}) ---")
    print(output.rstrip())
    print(dim("--- end of captured output ---"))
    print()


def run_capture(
    cmd: Sequence[str],
    *,
    sudo: bool = False,
    check: bool = True,
    env: Mapping[str, str] | None = None,
    cwd: str | Path | None = None,
    stderr_to_stdout: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a command and capture stdout (and optionally stderr) as text.

    Used when the caller needs to parse output — e.g. ``rocminfo`` or
    ``kubectl get nodes -o yaml``.
    """
    full = _build_cmd(cmd, sudo=sudo)
    try:
        result = subprocess.run(
            full,
            check=False,
            env=dict(env) if env is not None else None,
            cwd=str(cwd) if cwd is not None else None,
            text=True,
            capture_output=not stderr_to_stdout,
            stdout=subprocess.PIPE if stderr_to_stdout else None,
            stderr=subprocess.STDOUT if stderr_to_stdout else None,
        )
    except FileNotFoundError as exc:
        raise InstallerError(f"Command not found: {full[0]}") from exc

    if check and result.returncode != 0:
        stderr = result.stderr or ""
        raise InstallerError(f"Command failed (exit {result.returncode}): {' '.join(full)}\n{stderr}")
    return result


def run_streaming(
    cmd: Sequence[str],
    *,
    sudo: bool = False,
    env: Mapping[str, str] | None = None,
    cwd: str | Path | None = None,
    log_file: str | Path | None = None,
    check: bool = True,
    force_stream: bool = False,
) -> int:
    """Run a long command and capture its combined output.

    Two output modes, controlled by the global ``VERBOSE`` flag (or the
    ``force_stream`` per-call override):

      * **Verbose** — every output line is written to stdout in real time
        (mirrors the legacy bash behaviour). Use during dev / debugging.

      * **Quiet** (the default) — output is buffered to a temp log file
        as the command runs. The user sees nothing while the command is
        in flight; this gives a progress-bar feel where only the
        surrounding ``log_*`` calls and ``stage()`` markers are visible.
        On non-zero exit the captured log is dumped so the user can see
        why the command failed; on success the temp log is deleted.

    A caller-supplied ``log_file`` is honoured in both modes (caller is
    responsible for inspection / cleanup of that file).

    Returns the exit code. With ``check=True`` (default) raises
    :class:`InstallerError` on non-zero exit.
    """
    full = _build_cmd(cmd, sudo=sudo)
    verbose = _VERBOSE or force_stream

    # In quiet mode, also feed each line into the active progress stage's
    # live tail (if any) so the user sees a dim summary below the spinner.
    from auplc_installer.progress import current_stage

    runner = None if verbose else current_stage()

    # Always log to a file. If caller didn't provide one, mint a temp file
    # and clean it up after the run unless we have to dump it on failure.
    own_log = log_file is None
    if own_log:
        fd, tmp_path = tempfile.mkstemp(prefix="auplc-run-", suffix=".log")
        os.close(fd)
        log_file = tmp_path

    # The log file must outlive the wrapped subprocess and survive iter
    # in ``proc.stdout``; a `with` block doesn't fit. Suppress SIM115.
    # Force UTF-8 so subprocess output (which we already decode as text via
    # text=True with the platform default) lands on disk identically across
    # locales — without this, LANG=C systems would write through ASCII and
    # bomb on non-ASCII bytes from e.g. ``docker pull`` progress lines.
    log_fh = open(log_file, "w", encoding="utf-8")  # noqa: SIM115
    try:
        try:
            proc = subprocess.Popen(
                full,
                env=dict(env) if env is not None else None,
                cwd=str(cwd) if cwd is not None else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError as exc:
            raise InstallerError(f"Command not found: {full[0]}") from exc

        assert proc.stdout is not None
        for line in proc.stdout:
            log_fh.write(line)
            if verbose:
                sys.stdout.write(line)
                sys.stdout.flush()
            elif runner is not None:
                runner.append_output(line)
        rc = proc.wait()
    finally:
        log_fh.close()

    if check and rc != 0:
        if not verbose:
            # Reveal what went wrong so the user can diagnose without
            # re-running with --verbose.
            from auplc_installer.colors import dim

            print()
            print(f"--- Captured output of: {' '.join(full)} (exit {rc}) ---")
            try:
                with open(log_file, encoding="utf-8") as f:
                    sys.stdout.write(f.read())
            except OSError:
                pass
            print(dim("--- end of captured output ---"))
            print()
        if own_log:
            with contextlib.suppress(OSError):
                os.remove(log_file)
        raise InstallerError(f"Command failed (exit {rc}): {' '.join(full)}")

    if own_log:
        with contextlib.suppress(OSError):
            os.remove(log_file)
    return rc


def run_pipe_text_to(cmd: Sequence[str], *, input_text: str, sudo: bool = False) -> int:
    """Run a command, piping ``input_text`` into its stdin. Returns exit code (no exception).

    Honours the global ``VERBOSE`` flag the same way as :func:`run`:
    quiet by default (``tee`` & friends won't echo their input back to
    the user during install stages), full pass-through in verbose mode.
    """
    full = _build_cmd(cmd, sudo=sudo)
    popen_kwargs: dict[str, object] = {
        "input": input_text,
        "text": True,
        "check": False,
    }
    if not _VERBOSE:
        # tee echoes its stdin to stdout by default; suppress in quiet mode.
        popen_kwargs["stdout"] = subprocess.DEVNULL
        popen_kwargs["stderr"] = subprocess.STDOUT
    try:
        proc = subprocess.run(full, **popen_kwargs)
    except FileNotFoundError as exc:
        raise InstallerError(f"Command not found: {full[0]}") from exc
    return proc.returncode


def run_sudo_with_env(
    cmd: Sequence[str],
    env_vars: Mapping[str, str],
    *,
    check: bool = True,
    cwd: str | Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run ``cmd`` as root with extra environment variables.

    By default ``sudo`` resets the environment (``env_reset``), which
    strips custom variables — even ones we set via ``subprocess.run``'s
    ``env=`` kwarg. That breaks installers like ``get.k3s.io`` that read
    ``K3S_KUBECONFIG_MODE`` / ``INSTALL_K3S_VERSION`` from their env.

    The reliable workaround is to prepend ``VAR=val`` arguments to the
    ``sudo`` invocation; sudo recognises this form and forwards the
    variables to the target process. No-op fallback when EUID is already
    0 (we just merge the vars into ``os.environ``).
    """
    if os.geteuid() == 0:
        merged_env = {**os.environ, **env_vars}
        return run(cmd, env=merged_env, check=check, cwd=cwd)

    if shutil.which("sudo") is None:
        raise InstallerError("sudo is not installed; required for this operation.")

    sudo_args = [f"{k}={v}" for k, v in env_vars.items()]
    full = ["sudo", *sudo_args, *cmd]
    return run(full, check=check, cwd=cwd)


# ----------------------------------------------------------------------
# Preconditions
# ----------------------------------------------------------------------


def require_root() -> None:
    """Abort with a clear message when not running as root (EUID != 0).

    Prefer :func:`ensure_sudo_session` for new code: it lets the user keep
    running ``./auplc-installer`` (no sudo prefix) and prompts for the
    password once, then escalates only the subprocess calls that genuinely
    need it.
    """
    if os.geteuid() != 0:
        raise InstallerError("This script must be run as root.  Re-run with sudo.")


def ensure_sudo_session(*, assume_yes: bool = False) -> None:
    """Prime the sudo credential cache so subsequent ``run(..., sudo=True)``
    calls don't repeatedly prompt for a password.

    No-op when already running as root. Otherwise runs ``sudo -v`` which:
      * prompts for the password if no fresh credentials are cached
      * extends the cached-credential timestamp on success

    In ``assume_yes`` mode (CI / scripted contexts) we use ``sudo -n -v``
    which never prompts and fails fast if NOPASSWD is not configured.
    """
    if os.geteuid() == 0:
        return
    require_command("sudo", install_hint="Install the sudo package, or re-run as root.")

    if assume_yes:
        result = subprocess.run(
            ["sudo", "-n", "-v"],
            check=False,
            capture_output=True,
        )
        if result.returncode != 0:
            raise InstallerError(
                "sudo authentication required but --yes was set.\n"
                "  Configure passwordless sudo (NOPASSWD) for this user, "
                "or run without --yes."
            )
        return

    log("This operation needs root privileges. Requesting sudo password...")
    result = subprocess.run(["sudo", "-v"], check=False)
    if result.returncode != 0:
        raise InstallerError(f"sudo authentication failed (exit {result.returncode}).")


def start_sudo_keepalive() -> object:
    """Spawn a daemon thread that refreshes the sudo timestamp every 4 minutes.

    Long installs (large image pulls, helm rollout waits) can outlive the
    default sudo credential cache window (5-15 min), at which point the
    next ``run(..., sudo=True)`` would block on a password prompt. The
    keep-alive sidesteps that by issuing ``sudo -n -v`` periodically.

    Returns an opaque object with a ``stop()`` method the caller invokes
    in a ``finally`` block to terminate the thread.
    """
    import threading

    if os.geteuid() == 0:
        # No keep-alive needed when running as root.
        class _Noop:
            def stop(self) -> None:
                pass

        return _Noop()

    stop_event = threading.Event()

    def _loop() -> None:
        while not stop_event.wait(240):  # 4 minutes
            with contextlib.suppress(Exception):
                subprocess.run(
                    ["sudo", "-n", "-v"],
                    check=False,
                    capture_output=True,
                )

    t = threading.Thread(target=_loop, daemon=True, name="sudo-keepalive")
    t.start()

    class _KeepAlive:
        def stop(self) -> None:
            stop_event.set()

    return _KeepAlive()


def require_command(name: str, install_hint: str | None = None) -> None:
    """Abort when ``name`` is not on PATH."""
    if shutil.which(name) is None:
        msg = f"Required command not found: {name}"
        if install_hint:
            msg += f"\n  {install_hint}"
        raise InstallerError(msg)


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


# ----------------------------------------------------------------------
# Files / hashing
# ----------------------------------------------------------------------


def verify_sha256(path: str | Path, expected: str) -> None:
    """Raise ``InstallerError`` when ``path``'s sha256 differs from ``expected``."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    actual = h.hexdigest()
    if actual != expected:
        raise InstallerError(f"Checksum mismatch for {path}\n  Expected: {expected}\n  Actual:   {actual}")


def chmod_x(path: str | Path) -> None:
    p = Path(path)
    mode = p.stat().st_mode
    p.chmod(mode | 0o111)


# ----------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------


def log(msg: str = "") -> None:
    """Plain log line (stdout). Mirrors bash ``echo``.

    Behaviour while a stage is active:

      * Verbose mode  → print on its own line above the progress bar
        (the progress bar redraws automatically below).
      * Quiet mode    → silently dropped. The user sees only the stage
        label and the live progress bar; detailed status messages are
        considered noise. Use ``-v`` / ``AUPLC_VERBOSE=1`` to see them.
    """
    from auplc_installer.progress import current_stage

    runner = current_stage()
    if runner is not None:
        if _VERBOSE:
            runner.print_above(msg)
        return
    print(msg, flush=True)


def _emit_above_progress(text: str) -> None:
    """Print ``text`` either via the active progress runner (so the bar
    re-draws cleanly) or directly. Used for non-info messages that must
    always be visible (warnings, errors)."""
    from auplc_installer.progress import current_stage

    runner = current_stage()
    if runner is not None:
        runner.print_above(text)
    else:
        print(text, flush=True)


def log_section(title: str) -> None:
    """Visual divider used by long-running operations (mirrors bash ``echo "=== ..."``).

    Silenced inside stages unless verbose mode is on — the live progress
    line and stage label already convey "where we are".
    """
    from auplc_installer.colors import bold_cyan, cyan
    from auplc_installer.progress import current_stage

    if current_stage() is not None and not _VERBOSE:
        return
    bar = "==========================================="
    text = "\n".join([cyan(bar), bold_cyan(title), cyan(bar)])
    _emit_above_progress(text) if current_stage() is not None else print(text, flush=True)


def log_step(title: str) -> None:
    from auplc_installer.colors import bright_cyan
    from auplc_installer.progress import current_stage

    if current_stage() is not None and not _VERBOSE:
        return
    text = bright_cyan(f"--- {title} ---")
    _emit_above_progress(text) if current_stage() is not None else print(text, flush=True)


def log_success(msg: str) -> None:
    """Success-info message; silenced inside stages (the stage ✓ marker
    already conveys success). Verbose mode prints it above the bar."""
    from auplc_installer.colors import bold_green
    from auplc_installer.progress import current_stage

    if current_stage() is not None and not _VERBOSE:
        return
    text = bold_green(msg)
    _emit_above_progress(text) if current_stage() is not None else print(text, flush=True)


def log_warn(msg: str) -> None:
    """Warning. Always visible (printed above the active progress bar
    when one is running, or directly to stderr otherwise)."""
    from auplc_installer.colors import bold_yellow

    text = bold_yellow(f"Warning: {msg}")
    _emit_above_progress(text)


def log_error(msg: str) -> None:
    """Error message. Always visible. Goes to stderr when no progress
    bar is active so CI logs still capture it on the right stream."""
    from auplc_installer.colors import bold_red
    from auplc_installer.progress import current_stage

    text = bold_red(f"Error: {msg}")
    if current_stage() is not None:
        _emit_above_progress(text)
    else:
        print(text, file=sys.stderr, flush=True)


# ----------------------------------------------------------------------
# Misc helpers
# ----------------------------------------------------------------------


def ensure_dir(path: str | Path, *, sudo: bool = False) -> None:
    """``mkdir -p path`` — locally or via sudo when caller needs root."""
    p = Path(path)
    if p.exists():
        return
    if sudo:
        run(["mkdir", "-p", str(p)], sudo=True)
    else:
        p.mkdir(parents=True, exist_ok=True)


def first_or_default(seq: Iterable[str], default: str = "") -> str:
    for x in seq:
        return x
    return default


def sanitize_image_tag(tag: str) -> str:
    """Docker tags cannot contain '/' (e.g. branch names)."""
    return tag.replace("/", "-")
