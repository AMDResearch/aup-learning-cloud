# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Interactive wizard for ``auplc-installer tui``.

Prefers the optional ``questionary`` package (clean modern prompts that
work in VS Code terminal, tmux, ssh, screen) and falls back to a stdlib
numbered-menu implementation when it is not installed.

The TUI never does any work itself — it only collects user input into the
shared ``InstallerState``, then delegates to the same ``cmd_*`` functions
that the CLI dispatches to. That keeps the UI thin and the command logic
single-sourced.
"""

from __future__ import annotations

import contextlib
import select
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from auplc_installer.catalog import (
    COURSE_CATALOG,
    COURSE_PRESET_ALL,
    COURSE_PRESET_BASIC,
    NONE_SENTINEL,
    CourseSelection,
)
from auplc_installer.colors import (
    bold,
    bold_cyan,
    bright_cyan,
    bright_yellow,
    cyan,
    dim,
    green,
    yellow,
)
from auplc_installer.state import InstallerState
from auplc_installer.summary import format_configuration_summary_colored
from auplc_installer.util import (
    InstallerError,
    log,
    log_error,
)

try:
    import questionary  # type: ignore[import-not-found]

    HAS_QUESTIONARY = True
except ImportError:  # pragma: no cover - questionary is optional
    HAS_QUESTIONARY = False


# POSIX raw-mode terminal helpers for arrow-key navigation in the stdlib
# fallback path. Imported lazily so the module still loads on platforms
# without ``termios`` (the numbered-menu fallback covers those cases).
try:
    import termios
    import tty

    HAS_TERMIOS = True
except ImportError:  # pragma: no cover - non-POSIX
    HAS_TERMIOS = False


# ---------------------------------------------------------------------------
# stdin/stdout for piped invocation (e.g. ``curl URL | python3 -``)
# ---------------------------------------------------------------------------


def _ensure_tty_stdin() -> None:
    """Re-open ``/dev/tty`` for stdin when the script is piped in.

    Most modern terminal libraries (``prompt_toolkit``, used by
    questionary, plus stdlib's ``input()`` in interactive mode) expect a
    real TTY on fd 0. The future ``curl URL | python3 -`` invocation will
    pass the script content as stdin; redirect to /dev/tty so the user
    can still answer prompts.
    """
    if sys.stdin.isatty():
        return
    with contextlib.suppress(OSError):
        # Reopened stdin must outlive this function (used by input() etc.),
        # so a `with` block doesn't fit here. Suppress SIM115.
        sys.stdin = open("/dev/tty")  # noqa: SIM115


# ---------------------------------------------------------------------------
# Raw-mode arrow-key navigation (POSIX-only, stdlib fallback)
# ---------------------------------------------------------------------------


def _can_arrow_nav() -> bool:
    """True when we can put the terminal in raw mode for live key input."""
    if not HAS_TERMIOS:
        return False
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return False
    try:
        termios.tcgetattr(sys.stdin.fileno())
    except (termios.error, OSError):
        return False
    return True


def _read_key() -> tuple:
    """Read one keypress from raw stdin.

    Returns a tuple identifying the key:
      ('up',)            - arrow up / 'k'
      ('down',)          - arrow down / 'j'
      ('enter',)         - Return
      ('space',)         - Space (toggle in checkbox)
      ('esc',)           - Esc alone (cancel)
      ('ctrl-c',)        - Ctrl-C
      ('char', c)        - regular printable character
      ('digit', n)       - 1..9 (number jump)
    """
    ch = sys.stdin.read(1)
    if ch == "\x03":
        return ("ctrl-c",)
    if ch in ("\r", "\n"):
        return ("enter",)
    if ch == " ":
        return ("space",)
    if ch == "\x1b":
        # Either ESC alone or the start of an arrow sequence (\x1b[A etc.).
        # A short select() poll disambiguates: a real arrow always sends
        # the rest of the bytes immediately, while a lone ESC waits.
        ready, _, _ = select.select([sys.stdin], [], [], 0.05)
        if not ready:
            return ("esc",)
        ch2 = sys.stdin.read(1)
        if ch2 != "[":
            return ("esc",)
        ch3 = sys.stdin.read(1)
        if ch3 == "A":
            return ("up",)
        if ch3 == "B":
            return ("down",)
        return ("ignore",)
    if ch in ("k",):
        return ("up",)
    if ch in ("j",):
        return ("down",)
    if ch.isdigit():
        return ("digit", int(ch))
    return ("char", ch)


def _hide_cursor() -> None:
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()


def _show_cursor() -> None:
    sys.stdout.write("\033[?25h")
    sys.stdout.flush()


def _erase_block(lines_above: int) -> None:
    """Move the cursor up ``lines_above`` rows and clear to end of screen.

    Used to "tear down" the arrow-nav menu after Enter so the final
    output is just one summary line, leaving a tidy scrollback.
    """
    if lines_above > 0:
        sys.stdout.write(f"\033[{lines_above}A")
    sys.stdout.write("\033[J")
    sys.stdout.flush()


def _arrow_select(prompt: str, choices: Sequence[Choice], *, default_value: str | None = None) -> str:
    """Single-choice prompt with up/down arrows + Enter."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    idx = next((i for i, c in enumerate(choices) if c.value == default_value), 0)

    sys.stdout.write(f"\n{cyan('?')} {bold(prompt)} {dim('(use arrows or j/k, Enter to confirm, Esc to cancel)')}\n")
    sys.stdout.flush()

    def render() -> None:
        for i, c in enumerate(choices):
            if i == idx:
                line = f"  {bright_cyan('>')} {bright_cyan(c.label)}"
            else:
                line = f"    {dim(c.label)}"
            sys.stdout.write(f"\r\033[K{line}\n")
        sys.stdout.flush()

    _hide_cursor()
    try:
        tty.setcbreak(fd)
        render()
        while True:
            key = _read_key()
            kind = key[0]
            if kind == "ctrl-c":
                raise KeyboardInterrupt
            if kind == "esc":
                raise _CancelledError
            if kind == "enter":
                break
            if kind == "up":
                idx = (idx - 1) % len(choices)
            elif kind == "down":
                idx = (idx + 1) % len(choices)
            elif kind == "digit":
                num = key[1]
                if 1 <= num <= len(choices):
                    idx = num - 1
            elif kind == "char" and key[1] == "q":
                raise _CancelledError
            else:
                # Unknown key — just redraw at same idx (cheap)
                pass

            sys.stdout.write(f"\033[{len(choices)}A")
            render()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        _show_cursor()

    # Tear down the multi-line interactive view: erase prompt + options +
    # the implicit blank line above, then leave a single summary line.
    _erase_block(len(choices) + 2)
    sys.stdout.write(f"{cyan('?')} {bold(prompt)} {green(choices[idx].label)}\n")
    sys.stdout.flush()
    return choices[idx].value


def _arrow_checkbox(
    prompt: str,
    choices: Sequence[Choice],
    *,
    preselected: Sequence[str],
) -> list[str]:
    """Multi-select prompt with arrows + Space toggle + Enter confirm."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)

    valid = {c.value for c in choices}
    selected: set[str] = {p for p in preselected if p in valid}
    idx = 0

    sys.stdout.write(
        f"\n{cyan('?')} {bold(prompt)} "
        f"{dim('(arrows to navigate, Space to toggle, a=all, n=none, Enter to confirm, Esc to cancel)')}\n"
    )
    sys.stdout.flush()

    def render() -> None:
        for i, c in enumerate(choices):
            on = c.value in selected
            mark = green("[x]") if on else dim("[ ]")
            cursor = bright_cyan(">") if i == idx else " "
            label = bright_cyan(c.label) if i == idx else (c.label if on else dim(c.label))
            sys.stdout.write(f"\r\033[K {cursor} {mark} {label}\n")
        sys.stdout.flush()

    _hide_cursor()
    try:
        tty.setcbreak(fd)
        render()
        while True:
            key = _read_key()
            kind = key[0]
            if kind == "ctrl-c":
                raise KeyboardInterrupt
            if kind == "esc":
                raise _CancelledError
            if kind == "enter":
                break
            if kind == "up":
                idx = (idx - 1) % len(choices)
            elif kind == "down":
                idx = (idx + 1) % len(choices)
            elif kind == "space":
                v = choices[idx].value
                if v in selected:
                    selected.remove(v)
                else:
                    selected.add(v)
            elif kind == "char":
                c = key[1]
                if c == "a":
                    selected = {ch.value for ch in choices}
                elif c == "n":
                    selected.clear()
                elif c == "q":
                    raise _CancelledError
            elif kind == "digit":
                num = key[1]
                if 1 <= num <= len(choices):
                    v = choices[num - 1].value
                    idx = num - 1
                    if v in selected:
                        selected.remove(v)
                    else:
                        selected.add(v)

            sys.stdout.write(f"\033[{len(choices)}A")
            render()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        _show_cursor()

    picks = [c.value for c in choices if c.value in selected]
    summary = ", ".join(picks) if picks else dim("(none)")
    _erase_block(len(choices) + 2)
    sys.stdout.write(f"{cyan('?')} {bold(prompt)} {green(summary)}\n")
    sys.stdout.flush()
    return picks


# ---------------------------------------------------------------------------
# Choice descriptors (driven by both backends)
# ---------------------------------------------------------------------------


@dataclass
class Choice:
    value: str
    label: str


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------


class _CancelledError(Exception):
    """Raised when the user hits Esc/Ctrl-C/empty-Enter on a prompt."""


def _ask_select(prompt: str, choices: Sequence[Choice], *, default_value: str | None = None) -> str:
    """Single-select. Raises :class:`_CancelledError` on cancel/Esc."""
    if HAS_QUESTIONARY:
        q_choices = [questionary.Choice(c.label, value=c.value, checked=(c.value == default_value)) for c in choices]
        try:
            ans = questionary.select(prompt, choices=q_choices, default=default_value).ask()
        except KeyboardInterrupt:
            raise _CancelledError() from None
        if ans is None:
            raise _CancelledError()
        return ans
    return _stdlib_select(prompt, choices, default_value=default_value)


def _ask_checkbox(
    prompt: str,
    choices: Sequence[Choice],
    *,
    preselected: Sequence[str] = (),
) -> list[str]:
    """Multi-select. Empty selection is allowed; returns ``[]``."""
    if HAS_QUESTIONARY:
        pre = set(preselected)
        q_choices = [questionary.Choice(c.label, value=c.value, checked=(c.value in pre)) for c in choices]
        try:
            ans = questionary.checkbox(prompt, choices=q_choices).ask()
        except KeyboardInterrupt:
            raise _CancelledError() from None
        if ans is None:
            raise _CancelledError()
        return list(ans)
    return _stdlib_checkbox(prompt, choices, preselected=preselected)


def _ask_text(prompt: str, *, default: str = "") -> str:
    """Free-form text input. Empty string is allowed (and means "use default")."""
    if HAS_QUESTIONARY:
        try:
            ans = questionary.text(prompt, default=default).ask()
        except KeyboardInterrupt:
            raise _CancelledError() from None
        if ans is None:
            raise _CancelledError()
        return ans
    suffix = f" {dim(f'[{default}]')}" if default else ""
    sys.stdout.write(f"{cyan('?')} {bold(prompt)}{suffix}: ")
    sys.stdout.flush()
    try:
        line = input()
    except (EOFError, KeyboardInterrupt) as exc:
        raise _CancelledError() from exc
    line = line.strip()
    return line if line else default


def _ask_confirm(prompt: str, *, default: bool = True) -> bool:
    if HAS_QUESTIONARY:
        try:
            ans = questionary.confirm(prompt, default=default).ask()
        except KeyboardInterrupt:
            raise _CancelledError() from None
        if ans is None:
            raise _CancelledError()
        return bool(ans)
    suffix = dim("[Y/n]") if default else dim("[y/N]")
    sys.stdout.write(f"{cyan('?')} {bold(prompt)} {suffix}: ")
    sys.stdout.flush()
    try:
        line = input().strip().lower()
    except (EOFError, KeyboardInterrupt) as exc:
        raise _CancelledError() from exc
    if not line:
        return default
    return line in ("y", "yes")


# ---------------------------------------------------------------------------
# Stdlib fallback (numbered menu)
# ---------------------------------------------------------------------------


def _stdlib_select(prompt: str, choices: Sequence[Choice], *, default_value: str | None = None) -> str:
    if _can_arrow_nav():
        return _arrow_select(prompt, choices, default_value=default_value)

    sys.stdout.write(f"\n{cyan('?')} {bold(prompt)}\n")
    for i, c in enumerate(choices, start=1):
        if c.value == default_value:
            line = f"  {bright_cyan(f'{i}.')}{bright_yellow(' *')} {c.label}"
        else:
            line = f"  {dim(f'{i}.')}   {c.label}"
        sys.stdout.write(line + "\n")
    while True:
        default_idx = next(
            (i + 1 for i, c in enumerate(choices) if c.value == default_value),
            1,
        )
        try:
            line = input(dim(f"Pick a number [1-{len(choices)}, default {default_idx}]: ")).strip()
        except (EOFError, KeyboardInterrupt) as exc:
            raise _CancelledError() from exc
        if not line:
            return choices[default_idx - 1].value
        try:
            idx = int(line)
        except ValueError:
            sys.stdout.write(yellow("  Not a number, try again.\n"))
            continue
        if 1 <= idx <= len(choices):
            return choices[idx - 1].value
        sys.stdout.write(yellow(f"  Out of range, pick 1..{len(choices)}.\n"))


def _stdlib_checkbox(
    prompt: str,
    choices: Sequence[Choice],
    *,
    preselected: Sequence[str],
) -> list[str]:
    """Toggle-based numbered checklist for the stdlib fallback."""
    if _can_arrow_nav():
        return _arrow_checkbox(prompt, choices, preselected=preselected)

    selected: set[str] = {p for p in preselected if p in {c.value for c in choices}}

    while True:
        sys.stdout.write(f"\n{cyan('?')} {bold(prompt)}\n")
        for i, c in enumerate(choices, start=1):
            if c.value in selected:
                mark = green("[x]")
                num = bright_cyan(f"{i}.")
            else:
                mark = dim("[ ]")
                num = dim(f"{i}.")
            sys.stdout.write(f"  {num} {mark} {c.label}\n")
        sys.stdout.write(dim("  Commands:  <number> = toggle  |  a = all  |  n = none  |  d / Enter = done\n"))
        try:
            line = input(bright_cyan("> ")).strip().lower()
        except (EOFError, KeyboardInterrupt) as exc:
            raise _CancelledError() from exc
        if line in ("", "d", "done"):
            return [c.value for c in choices if c.value in selected]
        if line in ("a", "all"):
            selected = {c.value for c in choices}
            continue
        if line in ("n", "none"):
            selected.clear()
            continue
        try:
            idx = int(line)
        except ValueError:
            sys.stdout.write(yellow("  Unknown command. Use a number, 'a', 'n', or 'd'.\n"))
            continue
        if 1 <= idx <= len(choices):
            v = choices[idx - 1].value
            if v in selected:
                selected.remove(v)
            else:
                selected.add(v)
        else:
            sys.stdout.write(yellow(f"  Out of range, pick 1..{len(choices)}.\n"))


# ---------------------------------------------------------------------------
# Sub-flows
# ---------------------------------------------------------------------------


GPU_CHOICES: tuple[Choice, ...] = (
    Choice("", "Auto-detect (rocminfo / KFD topology)"),
    Choice("phx", "phx        - Phoenix Point iGPU (gfx1100..1103)"),
    Choice("strix", "strix      - Strix Point iGPU (gfx1150)"),
    Choice("strix-halo", "strix-halo - Strix Halo iGPU (gfx1151)"),
    Choice("9070xt", "9070xt     - Radeon RX 9070 XT (gfx1201)"),
    Choice("r9700", "r9700      - Radeon AI PRO R9700 (gfx1201)"),
    Choice("9600gre", "9600gre    - Radeon RX 9600 GRE (gfx1200)"),
    Choice("dgpu", "dgpu       - Generic RDNA4 fallback"),
)


def _flow_select_gpu(state: InstallerState) -> None:
    state.gpu_type = _ask_select(
        "GPU selection (Auto-detect is recommended)",
        GPU_CHOICES,
        default_value=state.gpu_type,
    )


def _flow_select_runtime(state: InstallerState) -> None:
    choice = _ask_select(
        "K3s container runtime",
        (
            Choice("docker", "Docker      (default for dev; images visible to K3s immediately)"),
            Choice(
                "containerd", "containerd  (offline / portable; images exported to /var/lib/rancher/k3s/agent/images)"
            ),
        ),
        default_value="docker" if state.use_docker else "containerd",
    )
    state.use_docker = choice == "docker"


def _flow_collect_image_coords(state: InstallerState) -> None:
    state.image_registry = (
        _ask_text(
            "Image registry prefix",
            default=state.image_registry,
        )
        or "ghcr.io/amdresearch"
    )
    state.image_tag = (
        _ask_text(
            "Image tag (GPU suffix appended automatically)",
            default=state.image_tag,
        )
        or "latest"
    )


def _flow_collect_mirrors(state: InstallerState) -> None:
    state.mirror_prefix = _ask_text(
        "Registry mirror prefix (e.g. mirror.example.com; leave blank for default)",
        default=state.mirror_prefix,
    )
    state.mirror_pip = _ask_text(
        "PyPI mirror URL (leave blank for default)",
        default=state.mirror_pip,
    )
    state.mirror_npm = _ask_text(
        "npm mirror URL (leave blank for default)",
        default=state.mirror_npm,
    )


def _flow_select_envs(state: InstallerState, *, allow_back: bool = False) -> bool:
    """Environment selection: preset (all/basic/custom). Custom opens a checklist.

    Returns ``True`` when the user confirms a selection, ``False`` when they
    choose ``← Back`` on the preset menu (only offered when ``allow_back``).
    """
    while True:
        current_label = state.courses.description()
        preset_choices: list[Choice] = [
            Choice("all", "all    — every environment (default)"),
            Choice("basic", "basic  — base + code-server (cpu, gpu, code-cpu, code-gpu)"),
            Choice("custom", "custom — pick environments individually"),
        ]
        if allow_back:
            preset_choices.append(Choice("back", "← Back"))

        preset = _ask_select(
            f"Env selection — current: {current_label}",
            preset_choices,
            default_value="all" if state.courses.is_default() else "custom",
        )
        if preset == "back":
            return False
        if preset == "all":
            state.courses = CourseSelection(picks=list(COURSE_PRESET_ALL))
            return True
        if preset == "basic":
            state.courses = CourseSelection(picks=list(COURSE_PRESET_BASIC))
            return True

        # custom: checklist with an explicit path back to the preset menu
        action = _ask_select(
            "Custom env selection",
            (
                Choice("pick", "Pick environments (checkbox)"),
                Choice("back", "← Back to presets"),
            ),
        )
        if action == "back":
            continue

        choices = [Choice(c.key, f"{c.key:<14} - {c.display_name}") for c in COURSE_CATALOG]
        if state.courses.is_default() or state.courses.is_none():
            preselected: list[str] = list(COURSE_PRESET_ALL) if state.courses.is_default() else []
        else:
            preselected = list(state.courses.picks)

        picks = _ask_checkbox(
            "Pick environments to install (space toggles, Enter confirms; nothing selected = Hub only)",
            choices,
            preselected=preselected,
        )
        if not picks:
            state.courses = CourseSelection(picks=[NONE_SENTINEL])
        else:
            state.courses = CourseSelection(picks=picks)
        return True


# Back-compat alias for any external callers.
_flow_select_courses = _flow_select_envs


# ---------------------------------------------------------------------------
# Top-level flows  (each calls the same cmd_* functions cli.py uses)
# ---------------------------------------------------------------------------


def _flow_install(state: InstallerState) -> None:
    """Run the full install wizard. Raises ``_CancelledError`` on user-aborts."""
    _flow_select_gpu(state)
    if not state.offline_mode:
        _flow_select_runtime(state)

    if state.offline_mode:
        image_source_label = f"Offline bundle ({state.bundle_dir})"
        pull = False
    else:
        while True:
            image_source = _ask_select(
                "Image source",
                (
                    Choice("pull", "pull  - fetch pre-built images from registry (default)"),
                    Choice("build", "build - build from dockerfiles/ via Makefile"),
                ),
                default_value="pull",
            )
            image_source_label = image_source
            pull = image_source == "pull"
            _flow_collect_image_coords(state)
            _flow_collect_mirrors(state)
            if _flow_select_envs(state, allow_back=True):
                break

    if state.offline_mode:
        while True:
            if _flow_select_envs(state, allow_back=True):
                break
            # Back from env selection in offline mode returns to GPU step.
            _flow_select_gpu(state)

    log("\n" + format_configuration_summary_colored(state, image_source_label=image_source_label) + "\n")
    if not _ask_confirm("Proceed with installation?", default=True):
        raise _CancelledError

    from auplc_installer.cli import cmd_install

    cmd_install(state, pull=pull)


def _flow_pack(state: InstallerState, source_root) -> None:
    from auplc_installer.util import command_exists

    if not command_exists("docker"):
        log_error("Docker is required for pack. Install Docker, then re-run the TUI.")
        raise _CancelledError

    _flow_select_gpu(state)
    pack_mode = _ask_select(
        "Pack image source",
        (
            Choice("pull", "pull  - pull pre-built images from registry (default)"),
            Choice("build", "build - build locally then pack (needs build deps)"),
        ),
        default_value="pull",
    )
    while True:
        _flow_collect_image_coords(state)
        _flow_collect_mirrors(state)
        if _flow_select_envs(state, allow_back=True):
            break

    log("\n" + format_configuration_summary_colored(state, image_source_label=pack_mode))
    log("\nThis will create an offline bundle archive in the current directory.")
    if not _ask_confirm("Proceed?", default=True):
        raise _CancelledError

    from auplc_installer.cli import cmd_pack

    cmd_pack(state, local_build=(pack_mode == "build"), source_root=source_root)


def _flow_uninstall(state: InstallerState) -> None:
    if not _ask_confirm(
        "Uninstall AUP Learning Cloud (Helm release + K3s + dummy0)?",
        default=False,
    ):
        raise _CancelledError
    from auplc_installer.cli import cmd_uninstall

    cmd_uninstall(state)


def _flow_detect_gpu(state: InstallerState) -> None:
    from auplc_installer.cli import cmd_detect_gpu

    cmd_detect_gpu(state)


def _flow_install_tools(state: InstallerState) -> None:
    from auplc_installer.cli import cmd_install_tools

    cmd_install_tools(state)


def _flow_dev(state: InstallerState) -> None:
    """Dev sub-menu: pick one action, run it, then return.

    ``upgrade`` does NOT re-prompt for environments — the previous selection
    is preserved by ``cmd_dev_upgrade`` reading the existing overlay
    header. ``deploy`` / ``reinstall`` still ask because they're "fresh"
    from the user's point of view (a dev-overlay redeploy is allowed to
    change scope).
    """
    from auplc_installer.cli import (
        cmd_dev_deploy,
        cmd_dev_quick,
        cmd_dev_reinstall,
        cmd_dev_upgrade,
    )

    while True:
        sub = _ask_select(
            "Dev mode",
            (
                Choice("quick", "quick     — rebuild Hub image and restart pod"),
                Choice("deploy", "deploy    — install with dev overlay (student=admin)"),
                Choice("upgrade", "upgrade   — helm upgrade with dev overlay"),
                Choice("reinstall", "reinstall — uninstall + redeploy with dev overlay"),
                Choice("cancel", "← Cancel (back to main menu)"),
            ),
        )
        if sub == "cancel":
            raise _CancelledError

        if sub == "quick":
            cmd_dev_quick(state)
            return
        if sub == "upgrade":
            cmd_dev_upgrade(state)
            return
        if sub == "deploy":
            while True:
                if _flow_select_envs(state, allow_back=True):
                    cmd_dev_deploy(state)
                    return
                break
            continue
        if sub == "reinstall":
            if not _ask_confirm("Uninstall and redeploy JupyterHub (dev overlay)?", default=False):
                raise _CancelledError
            while True:
                if _flow_select_envs(state, allow_back=True):
                    cmd_dev_reinstall(state)
                    return
                break
            continue


def _flow_rt(state: InstallerState) -> None:
    """Runtime (Helm-only) sub-menu: pick one action, run it, then return.

    See ``_flow_dev`` for the rationale on why ``upgrade`` skips the
    environment prompt.
    """
    from auplc_installer.cli import (
        cmd_rt_install,
        cmd_rt_reinstall,
        cmd_rt_remove,
        cmd_rt_upgrade,
    )

    while True:
        sub = _ask_select(
            "Runtime (Helm) only",
            (
                Choice("install", "install   — deploy JupyterHub"),
                Choice("upgrade", "upgrade   — helm upgrade (for values changes)"),
                Choice("reinstall", "reinstall — uninstall then redeploy"),
                Choice("remove", "remove    — uninstall the Helm release"),
                Choice("cancel", "← Cancel (back to main menu)"),
            ),
        )
        if sub == "cancel":
            raise _CancelledError

        if sub == "install":
            while True:
                if _flow_select_envs(state, allow_back=True):
                    cmd_rt_install(state)
                    return
                break
            continue
        if sub == "upgrade":
            cmd_rt_upgrade(state)
            return
        if sub == "reinstall":
            if not _ask_confirm("Uninstall and redeploy JupyterHub?", default=False):
                raise _CancelledError
            while True:
                if _flow_select_envs(state, allow_back=True):
                    cmd_rt_reinstall(state)
                    return
                break
            continue
        if sub == "remove":
            if not _ask_confirm("Uninstall the JupyterHub Helm release? (K3s remains.)", default=False):
                raise _CancelledError
            cmd_rt_remove(state)
            return


def _flow_img(state: InstallerState) -> None:
    """Image management sub-menu: pick one action, run it, then return."""
    from auplc_installer.cli import cmd_img_build, cmd_img_pull

    while True:
        sub = _ask_select(
            "Image management",
            (
                Choice("build", "build — build custom images via Makefile"),
                Choice("pull", "pull  — pull external images for offline use"),
                Choice("cancel", "← Cancel (back to main menu)"),
            ),
        )
        if sub == "cancel":
            raise _CancelledError
        if sub == "pull":
            cmd_img_pull(state)
            return
        if sub == "build":
            while True:
                if _flow_select_envs(state, allow_back=True):
                    cmd_img_build(state, [])
                    return
                break
            continue


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------


_MAIN_CHOICES: tuple[Choice, ...] = (
    Choice("install", "Install            - full deploy (K3s + images + Hub)"),
    Choice("uninstall", "Uninstall          - remove K3s + Hub"),
    Choice("pack", "Pack offline       - build a portable bundle"),
    Choice("dev", "Dev mode           - fast iteration on the Hub"),
    Choice("rt", "Runtime (Helm) only"),
    Choice("img", "Image management   - build / pull"),
    Choice("install-tools", "Install helm + k9s"),
    Choice("detect-gpu", "Detect GPU         - show host detection result"),
    Choice("quit", "Quit"),
)


def _print_banner() -> None:
    log(cyan("=========================================================="))
    log(bold_cyan(" AUP Learning Cloud Installer"))
    if not HAS_QUESTIONARY:
        log(dim(" (running with stdlib fallback; install `questionary` for"))
        log(dim("  a smoother UI: pipx install questionary)"))
    log(cyan("=========================================================="))


def run_tui(state: InstallerState) -> None:
    """Top-level TUI loop.

    Behaviour: show the main menu, run exactly one action, then return
    (which exits the process via ``cli.main``). The user re-launches
    ``auplc-installer`` if they want to do another thing — that's almost
    always cheaper than dumping them back at a menu they'd just have to
    navigate again, and it matches what the equivalent ``./auplc-installer
    rt upgrade`` CLI invocation would do.

    The exception is cancellation (Esc / Ctrl-C / explicit "cancel" item
    inside a sub-menu): these throw :class:`_CancelledError`, which is
    caught here so the user comes back to the main menu and can pick a
    different action without re-launching.
    """
    _ensure_tty_stdin()
    _print_banner()

    from auplc_installer.cli import _resolve_source_root

    source_root = _resolve_source_root()

    flows: dict[str, Callable[[], object]] = {
        "install": lambda: _flow_install(state),
        "uninstall": lambda: _flow_uninstall(state),
        "pack": lambda: _flow_pack(state, source_root),
        "dev": lambda: _flow_dev(state),
        "rt": lambda: _flow_rt(state),
        "img": lambda: _flow_img(state),
        "install-tools": lambda: _flow_install_tools(state),
        "detect-gpu": lambda: _flow_detect_gpu(state),
    }

    while True:
        try:
            choice = _ask_select("Pick an action", _MAIN_CHOICES)
        except _CancelledError:
            return
        if choice == "quit":
            return
        flow = flows.get(choice)
        if flow is None:
            continue
        try:
            flow()
        except _CancelledError:
            log(yellow("\n(Cancelled — back to main menu)\n"))
            continue
        except InstallerError as exc:
            log_error(str(exc))
        # Successful action OR a fatal error -> we're done. The user can
        # re-launch ``auplc-installer`` for another round.
        return
