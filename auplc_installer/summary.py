# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Configuration summary formatting shared by the TUI and CLI."""

from __future__ import annotations

from pathlib import Path

from auplc_installer.colors import bold, bold_cyan, bright_cyan, dim, green
from auplc_installer.state import InstallerState
from auplc_installer.util import InstallerError

# Canonical image-source labels shown in Configuration summary (TUI + CLI).
IMAGE_SOURCE_PULL = "pull"
IMAGE_SOURCE_BUILD = "build"


def normalize_image_source(value: str) -> str:
    """Map CLI/TUI input to a canonical ``pull`` or ``build`` label."""
    src = value.lower()
    if src in ("ghcr", "pull"):
        return IMAGE_SOURCE_PULL
    if src == "build":
        return IMAGE_SOURCE_BUILD
    raise InstallerError(f"Unknown --image-source={value!r} (expected pull or build)")


def resolve_install_image_source(
    *,
    image_source: str | None,
    legacy_pull: bool = False,
    offline_mode: bool = False,
    bundle_dir: Path | None = None,
) -> tuple[bool, str]:
    """Return ``(pull, label)`` for an install plan.

    ``pull=True`` means fetch custom images from the configured registry.
    ``pull=False`` means build custom images locally via Makefile.

    Precedence: offline bundle > explicit ``--image-source`` > legacy
    ``install --pull`` > default ``pull`` (matches the TUI default).
    """
    if offline_mode:
        location = bundle_dir or "."
        return False, f"Offline bundle ({location})"

    if image_source is not None:
        label = normalize_image_source(image_source)
        return label == IMAGE_SOURCE_PULL, label

    if legacy_pull:
        return True, IMAGE_SOURCE_PULL

    return True, IMAGE_SOURCE_PULL


def format_configuration_summary(state: InstallerState, *, image_source_label: str = "") -> str:
    """Human-readable install plan (plain text; TUI adds colours separately)."""
    runtime = "Docker" if state.use_docker else "containerd"
    gpu = state.gpu_type or "auto-detect"

    lines = ["Configuration summary", f"  GPU              : {gpu}", f"  K3s runtime      : {runtime}"]
    if image_source_label:
        lines.append(f"  Image source     : {image_source_label}")
    lines.append(f"  Image registry   : {state.image_registry}")
    lines.append(f"  Image tag        : {state.image_tag}")
    lines.append(f"  Registry mirror  : {state.mirror_prefix or '(none)'}")
    lines.append(f"  PyPI mirror      : {state.mirror_pip or '(default)'}")
    lines.append(f"  npm mirror       : {state.mirror_npm or '(default)'}")
    lines.append(f"  Environments     : {state.courses.description()}")
    return "\n".join(lines)


def format_configuration_summary_colored(state: InstallerState, *, image_source_label: str = "") -> str:
    """TUI-friendly coloured variant of :func:`format_configuration_summary`."""
    runtime = "Docker" if state.use_docker else "containerd"

    def row(key: str, value: str, *, accent: bool = False, faint: bool = False) -> str:
        if faint:
            v = dim(value)
        elif accent:
            v = bold(value)
        else:
            v = green(value)
        return f"  {bright_cyan(key.ljust(17))}: {v}"

    lines = [bold_cyan("Configuration summary")]
    lines.append(row("GPU", state.gpu_type or "auto-detect"))
    lines.append(row("K3s runtime", runtime))
    if image_source_label:
        lines.append(row("Image source", image_source_label, accent=True))
    lines.append(row("Image registry", state.image_registry))
    lines.append(row("Image tag", state.image_tag))
    if state.mirror_prefix:
        lines.append(row("Registry mirror", state.mirror_prefix))
    else:
        lines.append(row("Registry mirror", "(none)", faint=True))
    if state.mirror_pip:
        lines.append(row("PyPI mirror", state.mirror_pip))
    else:
        lines.append(row("PyPI mirror", "(default)", faint=True))
    if state.mirror_npm:
        lines.append(row("npm mirror", state.mirror_npm))
    else:
        lines.append(row("npm mirror", "(default)", faint=True))
    lines.append(row("Environments", state.courses.description(), accent=True))
    return "\n".join(lines)
