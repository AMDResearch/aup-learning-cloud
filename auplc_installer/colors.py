# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""ANSI colour helpers (stdlib only).

Auto-disabled when stdout is not a TTY or ``NO_COLOR`` is set in the
environment, so CI logs and pipes stay plain. Honour these standards:

  * https://no-color.org   - ``NO_COLOR`` (any value) disables colour.
  * https://bixense.com/clicolors  - ``CLICOLOR=0`` also disables colour.
"""

from __future__ import annotations

import os
import sys

# ANSI escape codes
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"

BRIGHT_RED = "\033[91m"
BRIGHT_GREEN = "\033[92m"
BRIGHT_YELLOW = "\033[93m"
BRIGHT_BLUE = "\033[94m"
BRIGHT_CYAN = "\033[96m"


def supports_color() -> bool:
    """True when stdout looks like a colour-capable terminal."""
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("CLICOLOR") == "0":
        return False
    term = os.environ.get("TERM", "")
    if term == "dumb":
        return False
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def _wrap(code: str, text: str) -> str:
    if not supports_color():
        return text
    return f"{code}{text}{RESET}"


def red(text: str) -> str:
    return _wrap(RED, text)


def green(text: str) -> str:
    return _wrap(GREEN, text)


def yellow(text: str) -> str:
    return _wrap(YELLOW, text)


def blue(text: str) -> str:
    return _wrap(BLUE, text)


def cyan(text: str) -> str:
    return _wrap(CYAN, text)


def magenta(text: str) -> str:
    return _wrap(MAGENTA, text)


def bold(text: str) -> str:
    return _wrap(BOLD, text)


def dim(text: str) -> str:
    return _wrap(DIM, text)


def bright_cyan(text: str) -> str:
    return _wrap(BRIGHT_CYAN, text)


def bright_green(text: str) -> str:
    return _wrap(BRIGHT_GREEN, text)


def bright_yellow(text: str) -> str:
    return _wrap(BRIGHT_YELLOW, text)


def bright_red(text: str) -> str:
    return _wrap(BRIGHT_RED, text)


def bold_cyan(text: str) -> str:
    return _wrap(BOLD + CYAN, text)


def bold_red(text: str) -> str:
    return _wrap(BOLD + RED, text)


def bold_green(text: str) -> str:
    return _wrap(BOLD + GREEN, text)


def bold_yellow(text: str) -> str:
    return _wrap(BOLD + YELLOW, text)
