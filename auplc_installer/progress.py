# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Progress-bar style stage indicators for long install / pack flows.

Each ``stage()`` context manager owns a single live-updating line:

  * While the body runs, the line shows a filled progress bar, the
    stage number, an animated spinner and the elapsed time.
  * On success, the line is "committed" (replaced with a green
    checkmark and final elapsed time, then a newline). The completed
    stage stays in scrollback so the user has a record of what ran.
  * On failure, the line gets a red ✗ marker and the captured
    subprocess output (from ``util.run_streaming`` / ``run`` in quiet
    mode) is dumped immediately afterwards.

In quiet mode (the default), ``util.log`` is silenced for the duration
of a stage so the live line is not pushed off the bottom by helpful-but-
chatty status messages from the underlying modules. Verbose mode (``-v``
/ ``AUPLC_VERBOSE=1``) prints everything line-by-line above the bar
exactly as before.
"""

from __future__ import annotations

import contextlib
import os
import sys
import threading
import time
from collections import deque
from contextlib import contextmanager

from auplc_installer.colors import (
    bold,
    bold_green,
    bold_red,
    bright_cyan,
    dim,
    supports_color,
)

# Spinner frames (Braille; falls back to a simple cycle if Unicode width
# is funky on a terminal we don't recognise).
_SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

# How many most-recent subprocess stdout lines to show as a dim "live
# tail" below the spinner during a stage. Cleared when the stage ends.
_TAIL_MAX = 3


# Module-level handle to the currently-active progress line. ``util.log``
# consults this so it knows whether to print directly or buffer / redirect.
_CURRENT: _ProgressLine | None = None


def current_stage() -> _ProgressLine | None:
    return _CURRENT


def _fmt_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def _can_animate() -> bool:
    """True when we have a TTY and colour-capable terminal for in-place updates."""
    return sys.stdout.isatty() and supports_color()


@contextmanager
def stage(label: str, *, idx: int = 0, total: int = 0):
    """Run a body under a single live-updating progress line.

    See module docstring for behaviour. Use as
    ``with stage("Installing K3s", idx=4, total=8): ...``.
    """
    global _CURRENT

    runner = _ProgressLine(label, idx=idx, total=total)
    _CURRENT = runner
    runner.begin()
    try:
        yield
    except BaseException:
        runner.fail()
        _CURRENT = None
        raise
    runner.complete()
    _CURRENT = None


class _ProgressLine:
    """One stage's live-updating display + animation thread."""

    def __init__(self, label: str, *, idx: int, total: int) -> None:
        self.label = label
        self.idx = idx
        self.total = total
        self.start_t = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._frame = 0
        self._animate = _can_animate()
        # Live "tail" of the most recent subprocess stdout lines. Shown
        # as dim text below the progress line during the stage; cleared
        # when the stage ends.
        self._tail: deque[str] = deque(maxlen=_TAIL_MAX)
        # Number of terminal rows currently occupied by our render so we
        # can erase them on the next iteration.
        self._drawn = 0

    # ---- lifecycle ----

    def begin(self) -> None:
        self.start_t = time.monotonic()
        if self._animate:
            with self._lock:
                self._render_live()
            self._thread = threading.Thread(target=self._animate_loop, daemon=True)
            self._thread.start()
        else:
            # Plain-text fallback: just announce the stage.
            sys.stdout.write(f"  [{self.idx}/{self.total}] {self.label}...\n")
            sys.stdout.flush()

    def complete(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=0.5)
        elapsed = _fmt_elapsed(time.monotonic() - self.start_t)
        with self._lock:
            self._erase_region()
            sys.stdout.write(
                f"  {bold_green('✓')} [{self.idx}/{self.total}] {bold(self.label)}  {dim(f'({elapsed})')}\n"
            )
            sys.stdout.flush()
            self._drawn = 0
            self._tail.clear()

    def fail(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=0.5)
        elapsed = _fmt_elapsed(time.monotonic() - self.start_t)
        with self._lock:
            self._erase_region()
            sys.stdout.write(
                f"  {bold_red('✗')} [{self.idx}/{self.total}] {bold(self.label)}  {dim(f'(failed after {elapsed})')}\n"
            )
            sys.stdout.flush()
            self._drawn = 0
            self._tail.clear()

    # ---- rendering ----

    def _animate_loop(self) -> None:
        while not self._stop.wait(0.1):
            with self._lock:
                self._render_live()
                self._frame += 1

    def _render_live(self) -> None:
        if not self._animate:
            return

        # Invariant: at the end of every successful render we leave the
        # cursor at column 0 of the progress line (the top of our
        # region). Subsequent calls just clear from here down before
        # redrawing — moving up further would erase content that lives
        # ABOVE our region (e.g. the previous stage's ✓ committed
        # line). On the first render the cursor is already at column 0
        # of a fresh line so the carriage-return is a no-op.
        sys.stdout.write("\r\033[J")

        spinner = _SPINNER_FRAMES[self._frame % len(_SPINNER_FRAMES)]
        elapsed = _fmt_elapsed(time.monotonic() - self.start_t)
        sys.stdout.write(f"  {bright_cyan(spinner)} [{self.idx}/{self.total}] {bold(self.label)}  {dim(elapsed)}")

        n_lines = 1
        if self._tail:
            term_w = _term_width()
            for tail_line in self._tail:
                truncated = _truncate(tail_line, term_w - 5)
                sys.stdout.write("\n")
                sys.stdout.write(f"     {dim(truncated)}")
                n_lines += 1

        # Move cursor back to the top of the region for the next redraw.
        if n_lines > 1:
            sys.stdout.write(f"\r\033[{n_lines - 1}A")
        else:
            sys.stdout.write("\r")
        sys.stdout.flush()

        self._drawn = n_lines

    def _erase_region(self) -> None:
        """Clear the entire rendered region (progress + tail). Cursor ends
        at the top of the (now empty) region, ready for fresh writes."""
        if not self._animate or self._drawn == 0:
            return
        sys.stdout.write("\r")
        # Cursor is at start of progress line already (we always reset it
        # at the end of _render_live), so just blow away from here down.
        sys.stdout.write("\033[J")
        sys.stdout.flush()

    # ---- live tail integration ----

    def append_output(self, line: str) -> None:
        """Add a subprocess stdout line to the live tail. Called by
        ``util.run`` / ``util.run_streaming`` in quiet mode.
        """
        line = line.rstrip("\n")
        if not line:
            return
        with self._lock:
            self._tail.append(line)
            self._render_live()

    def clear_live_region(self) -> None:
        """Clear the live progress render so the caller can print
        free-form output below (e.g. a failure dump). The next time the
        animate loop ticks the line is redrawn from scratch.
        """
        with self._lock:
            self._erase_region()
            self._drawn = 0
            self._tail.clear()

    # ---- log integration ----

    def print_above(self, msg: str) -> None:
        """Print ``msg`` on its own line above the progress line, then redraw.

        Called by ``util.log`` in verbose mode. In quiet mode log output
        is silently dropped while a stage is active.
        """
        with self._lock:
            self._erase_region()
            print(msg, flush=True)
            self._drawn = 0
            self._render_live()


def _term_width() -> int:
    try:
        return os.get_terminal_size().columns
    except OSError:
        return 80


def _truncate(text: str, max_len: int) -> str:
    if max_len <= 0:
        return ""
    if len(text) <= max_len:
        return text
    if max_len <= 1:
        return "…"
    return text[: max_len - 1] + "…"


# ---------------------------------------------------------------------------
# Helper for callers that want a one-off "step" line without animation.
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def static_step(label: str):
    """A no-frills timed step (printed once, no spinner). Use for short
    sub-steps inside a larger flow that should not own the progress line.
    """
    sys.stdout.write(f"  {label}...")
    sys.stdout.flush()
    start = time.monotonic()
    try:
        yield
    except BaseException:
        elapsed = _fmt_elapsed(time.monotonic() - start)
        sys.stdout.write(f" {bold_red('failed')} {dim(f'({elapsed})')}\n")
        sys.stdout.flush()
        raise
    elapsed = _fmt_elapsed(time.monotonic() - start)
    sys.stdout.write(f" {bold_green('done')} {dim(f'({elapsed})')}\n")
    sys.stdout.flush()
