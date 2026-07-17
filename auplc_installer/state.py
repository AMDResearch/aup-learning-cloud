# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Runtime state container shared across modules.

The bash version uses global variables (``GPU_TYPE``, ``K3S_USE_DOCKER``,
``MIRROR_PREFIX``, ``IMAGE_REGISTRY``, ``IMAGE_TAG``, ``SELECTED_COURSES``,
``OFFLINE_MODE``, ``BUNDLE_DIR``, ...). We mirror that here as a single
dataclass that each command receives as its first argument; the TUI fills
the same fields based on the user's input before calling into a command.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from auplc_installer.catalog import CourseSelection
from auplc_installer.gpu import GpuConfig
from auplc_installer.helm import RuntimePaths
from auplc_installer.k3s import K3S_IMAGES_DIR
from auplc_installer.manifest import detect_offline_bundle

DEFAULT_IMAGE_REGISTRY = "ghcr.io/amdresearch"
DEFAULT_IMAGE_TAG = "latest"


@dataclass
class InstallerState:
    """All knobs exposed via CLI flags or environment variables."""

    # GPU override (matches bash GPU_TYPE)
    gpu_type: str = ""

    # K3s container runtime: True = Docker, False = containerd
    use_docker: bool = True

    # Registry / package mirrors
    mirror_prefix: str = ""
    mirror_pip: str = ""
    mirror_npm: str = ""

    # Custom-image registry coords
    image_registry: str = DEFAULT_IMAGE_REGISTRY
    image_tag: str = DEFAULT_IMAGE_TAG

    # Install image acquisition override (CLI --image-source=pull|build).
    # None => default ``pull`` (matches TUI); legacy ``install --pull`` also selects pull.
    image_source: str | None = None

    # Course selection (drives image filtering + teams.mapping override)
    courses: CourseSelection = field(default_factory=CourseSelection.default)

    # Non-interactive / scripted mode
    assume_yes: bool = False

    # Verbose subprocess output (default: quiet; only dumps on failure)
    verbose: bool = False

    # Offline-bundle state
    offline_mode: bool = False
    bundle_dir: Path | None = None

    # Detected GPU (populated lazily by detect_and_configure_gpu)
    gpu: GpuConfig = field(default_factory=GpuConfig)

    # K3s images dir (where containerd looks for tarballs to import)
    k3s_images_dir: str = K3S_IMAGES_DIR

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_environment(cls, *, script_dir: Path) -> InstallerState:
        """Seed an :class:`InstallerState` from environment variables and
        offline-bundle detection.  CLI flags (parsed in ``cli.main``)
        overlay on top of this baseline.
        """
        state = cls(
            gpu_type=os.environ.get("GPU_TYPE", ""),
            use_docker=_bool_env("K3S_USE_DOCKER", True),
            mirror_prefix=os.environ.get("MIRROR_PREFIX", ""),
            mirror_pip=os.environ.get("MIRROR_PIP", ""),
            mirror_npm=os.environ.get("MIRROR_NPM", ""),
            image_registry=os.environ.get("IMAGE_REGISTRY", DEFAULT_IMAGE_REGISTRY),
            image_tag=os.environ.get("IMAGE_TAG", DEFAULT_IMAGE_TAG),
            assume_yes=os.environ.get("AUPLC_YES", "0") == "1",
            verbose=os.environ.get("AUPLC_VERBOSE", "0") == "1",
        )

        # Course selection from env (CLI flag wins via cli.main reapplication)
        from auplc_installer.catalog import parse_selection_spec

        spec = os.environ.get("AUPLC_COURSES", "")
        if spec:
            state.courses = parse_selection_spec(spec)

        # Offline bundle detection. When a bundle is present, the bundle's
        # manifest pins the primary GPU/image-tag/registry that the bundle
        # was built for; we honour those over environment defaults.
        m = detect_offline_bundle(script_dir)
        if m is not None:
            state.offline_mode = True
            state.bundle_dir = Path(script_dir)
            # Bundles ship containerd-mode airgap images; force containerd.
            state.use_docker = False
            print(f"Offline bundle detected at: {script_dir}", flush=True)
            if m.image_registry:
                state.image_registry = m.image_registry
            if m.image_tag:
                state.image_tag = m.image_tag
            if m.gpu_target:
                state.gpu.gpu_target = m.gpu_target
                state.gpu.accel_key = m.accel_key
                state.gpu.accel_env = m.accel_env
                msg = f"  GPU config: accelerator={state.gpu.accel_key}, GPU_TARGET={state.gpu.gpu_target}"
                if state.gpu.accel_env:
                    msg += f", HSA_OVERRIDE={state.gpu.accel_env}"
                print(msg, flush=True)

        return state

    # ------------------------------------------------------------------
    # Path resolution
    # ------------------------------------------------------------------

    def runtime_paths(self) -> RuntimePaths:
        if self.offline_mode and self.bundle_dir is not None:
            return RuntimePaths.for_offline(self.bundle_dir)
        return RuntimePaths.for_repo()


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw not in ("0", "false", "False", "")
