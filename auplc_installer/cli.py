# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Argparse-based CLI for ``auplc-installer``.

Mirrors the bash main case statement and global-flag parser exactly:
same subcommands, same flags, same env vars, same legacy aliases.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from auplc_installer import __version__
from auplc_installer.catalog import parse_selection_spec
from auplc_installer.gpu import (
    detect_and_configure_gpu,
    refine_gpu_config_from_node_labels,
)
from auplc_installer.helm import (
    deploy_runtime,
    dev_quick_rollout,
    remove_runtime,
    upgrade_runtime,
)
from auplc_installer.images import (
    load_offline_images,
    local_image_build,
    pull_custom_images,
    pull_external_images,
)
from auplc_installer.k3s import install_k3s_single_node, install_tools, remove_k3s
from auplc_installer.overlay import generate_values_overlay, try_load_courses_from_overlay
from auplc_installer.pack import pack_bundle
from auplc_installer.progress import stage
from auplc_installer.rocm import deploy_rocm_gpu_device_plugin
from auplc_installer.state import InstallerState
from auplc_installer.summary import format_configuration_summary, resolve_install_image_source
from auplc_installer.util import (
    InstallerError,
    ensure_sudo_session,
    log,
    log_error,
    log_success,
    set_verbose,
    start_sudo_keepalive,
)

# ---------------------------------------------------------------------------
# Help text (mirrors bash show_help output verbatim where reasonable)
# ---------------------------------------------------------------------------


HELP_TEXT = """\
Usage: ./auplc-installer [<command>] [options]

When invoked with no command and a real terminal, the interactive TUI is
launched automatically (same as `./auplc-installer tui`). In CI / piped
contexts this help text is printed instead.

Root privileges: you can run the installer as a regular user. When a
command needs sudo (install / uninstall / install-tools), the script
prompts for your password once up-front and keeps the credential cache
fresh so you only enter it a single time. Running the installer with
`sudo` directly is also supported and skips the prompt.

Commands:
  tui                   Open the interactive TUI (recommended for new users).
                        Falls back to a stdlib numbered menu when the
                        optional `questionary` package is not installed.

  install [--pull]      Full installation (k3s + images + runtime)
                        Default: pull pre-built images from --image-registry
                        --pull: legacy alias for --image-source=pull
                        --image-source=build: build via dockerfiles/Makefile

  install --dry-run     Show Configuration summary without making changes
                        (also accepts --try-run). No sudo required.

  pack [--local]        Create offline deployment bundle (requires Docker + internet)
                        Default: pull pre-built images from registry
                        --local: legacy alias for building locally before pack

  uninstall             Remove everything (K3s + runtime)
  install-tools         Install helm and k9s

  dev                   Quick dev cycle: rebuild hub image + restart hub pod
  dev deploy            Full deploy with dev overlay (student=admin, pullPolicy=Never)
  dev upgrade           Helm upgrade with dev overlay (for values changes)
  dev reinstall         Remove + redeploy with dev overlay

  rt install            Deploy JupyterHub runtime only
  rt reinstall          Reinstall JupyterHub runtime (for container image changes)
  rt upgrade            Upgrade JupyterHub runtime (for values.yaml changes)
  rt remove             Remove JupyterHub runtime

  img build [target...] Build custom images (default: all, or hub + selected courses)
                        Targets: all, hub, base-cpu, base-rocm, code, code-cpu, code-gpu, cv, dl, llm, physim
  img pull              Pull external images for offline use

  detect-gpu            Show detected GPU configuration

Options (can also be set via environment variables):
  --gpu=TYPE        Override auto-detected GPU type. Accepts:
                      auto       - auto-detect (same as omitting the flag)
                      phx        - Phoenix Point iGPU (gfx1100..gfx1103)
                      strix      - Strix Point iGPU (gfx1150)
                      strix-halo - Strix Halo iGPU (gfx1151)
                      9070xt     - Radeon RX 9070 XT (gfx1201)
                      r9700      - Radeon AI PRO R9700 (gfx1201)
                      9600gre    - Radeon RX 9600 GRE (gfx1200)
                      rdna4|dgpu - Generic RDNA4 fallback
                      gfxNNNN    - any matching gfx family token also works
                    Auto-detection uses rocminfo or KFD topology.
                    Env: GPU_TYPE

  --runtime=MODE    K3s container runtime: docker (default) or containerd.
                    Env: K3S_USE_DOCKER (1 = docker, 0 = containerd)
                    Legacy: --docker=0|1 (still supported; --runtime wins)

  --image-source=SRC  Custom image acquisition for install:
                      pull  - fetch pre-built images from --image-registry
                      build - build from dockerfiles/ via Makefile
                    Default: pull. Legacy: ghcr is an alias for pull;
                    install --pull is an alias for --image-source=pull

  --image-registry=PREFIX
                    Registry prefix for custom images (default: ghcr.io/amdresearch)
                    Env: IMAGE_REGISTRY

  --image-tag=TAG   Custom-image tag prefix (default: latest). GPU suffix
                    appended automatically. Env: IMAGE_TAG

  --docker=0|1      Use host Docker as K3s container runtime (default: 1).
                    1 = Docker mode: images visible to K3s immediately.
                    0 = containerd mode: images exported for offline use.
                    Env: K3S_USE_DOCKER
                    Prefer --runtime=docker|containerd for new scripts.

  --courses=SPEC    Restrict the install/pack to a subset of courses. Affects
                    image build/pull AND the rendered values.local.yaml so
                    unselected courses are hidden in the spawn UI. Empty (the
                    default) keeps the historical "all courses" behaviour.
                      all     - every course
                      basic   - cpu/gpu base + code-server (code-cpu, code-gpu)
                      none    - Hub only, no courses
                      <list>  - comma-separated keys, e.g. cpu,gpu,Course-CV
                    Env: AUPLC_COURSES

  -y, --yes         Assume yes to all prompts (for scripted/CI use).
                    Env: AUPLC_YES=1

  --dry-run, --try-run
                    With ``install``: print Configuration summary and exit.
                    Does not prompt for sudo or change the system.

  -v, --verbose     Stream every subprocess line live (default is a quiet
                    "progress-bar" mode where only stage labels show, and
                    captured output is dumped only when a command fails).
                    Env: AUPLC_VERBOSE=1

  --mirror=PREFIX   Registry mirror (e.g. mirror.example.com)
                    Env: MIRROR_PREFIX
  --mirror-pip=URL  PyPI mirror URL.  Env: MIRROR_PIP
  --mirror-npm=URL  npm registry URL. Env: MIRROR_NPM

  Examples:
    ./auplc-installer tui                              # interactive wizard
    ./auplc-installer install --dry-run                # preview defaults
    ./auplc-installer install --image-source=pull --image-tag=develop
    ./auplc-installer install --runtime=containerd --image-source=build
    ./auplc-installer install --gpu=strix-halo
    ./auplc-installer install --gpu=auto --dry-run
    ./auplc-installer install --gpu=phx --docker=0     # legacy flags
    ./auplc-installer install --courses=basic          # base + code-server envs
    ./auplc-installer install --courses=cpu,gpu,Course-CV
    ./auplc-installer img build base-rocm --gpu=strix
    ./auplc-installer install --mirror=mirror.example.com

Image Registry (legacy env-only aliases still work):
  IMAGE_REGISTRY  Same as --image-registry (default: ghcr.io/amdresearch)
  IMAGE_TAG       Same as --image-tag (default: latest)

Offline Deployment:
  1. On a machine with internet access, create bundle:
       ./auplc-installer pack --gpu=strix-halo          # pull from registry
       ./auplc-installer pack --gpu=strix-halo --local   # or build locally

  2. Transfer bundle to air-gapped machine, then:
       tar xzf auplc-bundle-gfx1151-*.tar.gz
       cd auplc-bundle-gfx1151-*
       sudo ./auplc-installer install
"""


def show_help() -> None:
    sys.stdout.write(HELP_TEXT)


# ---------------------------------------------------------------------------
# Argparse (we intentionally keep most logic in a hand-rolled pre-pass so
# we can preserve the bash version's flag positioning quirks: ``--gpu=phx``
# can appear anywhere on the command line.)
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="auplc-installer",
        add_help=False,
        description="AUP Learning Cloud installer (Python).",
    )
    # Global flags
    p.add_argument("--gpu", dest="gpu_type", default=None)
    p.add_argument("--runtime", dest="runtime", default=None)
    p.add_argument("--docker", dest="use_docker", default=None)
    p.add_argument("--image-source", dest="image_source", default=None)
    p.add_argument("--image-registry", dest="image_registry", default=None)
    p.add_argument("--image-tag", dest="image_tag", default=None)
    p.add_argument("--mirror", dest="mirror_prefix", default=None)
    p.add_argument("--mirror-pip", dest="mirror_pip", default=None)
    p.add_argument("--mirror-npm", dest="mirror_npm", default=None)
    p.add_argument("--courses", dest="courses", default=None)
    p.add_argument("-y", "--yes", dest="assume_yes", action="store_true")
    p.add_argument("--dry-run", "--try-run", dest="dry_run", action="store_true")
    p.add_argument(
        "-v",
        "--verbose",
        dest="verbose",
        action="store_true",
        help="stream every subprocess line (default is quiet; failures are dumped)",
    )
    p.add_argument("--version", action="version", version=__version__)
    # Positional command + remaining args (for sub-subcommands like ``dev deploy``)
    p.add_argument("command", nargs="?", default=None)
    p.add_argument("rest", nargs=argparse.REMAINDER)
    return p


def _apply_global_flags(state: InstallerState, args: argparse.Namespace) -> None:
    if args.gpu_type is not None:
        state.gpu_type = "" if args.gpu_type.lower() == "auto" else args.gpu_type
    if args.runtime is not None:
        runtime = args.runtime.lower()
        if runtime == "docker":
            state.use_docker = True
        elif runtime == "containerd":
            state.use_docker = False
        else:
            raise InstallerError(f"Unknown --runtime={args.runtime!r} (expected docker or containerd)")
    elif args.use_docker is not None:
        state.use_docker = args.use_docker not in ("0", "false", "False")
    if args.image_source is not None:
        state.image_source = args.image_source
    if args.image_registry is not None:
        state.image_registry = args.image_registry
    if args.image_tag is not None:
        state.image_tag = args.image_tag
    if args.mirror_prefix is not None:
        state.mirror_prefix = args.mirror_prefix
    if args.mirror_pip is not None:
        state.mirror_pip = args.mirror_pip
    if args.mirror_npm is not None:
        state.mirror_npm = args.mirror_npm
    if args.courses is not None:
        state.courses = parse_selection_spec(args.courses)
    if args.assume_yes:
        state.assume_yes = True
    if args.verbose:
        state.verbose = True
    # Propagate verbose flag to util.run_streaming.
    set_verbose(state.verbose)


def _install_pull_and_label(
    state: InstallerState,
    *,
    legacy_pull: bool,
) -> tuple[bool, str]:
    return resolve_install_image_source(
        image_source=state.image_source,
        legacy_pull=legacy_pull,
        offline_mode=state.offline_mode,
        bundle_dir=state.bundle_dir,
    )


def cmd_install_plan(state: InstallerState, *, legacy_pull: bool = False) -> None:
    """Print the install Configuration summary without side effects."""
    _, label = _install_pull_and_label(state, legacy_pull=legacy_pull)
    sys.stdout.write(format_configuration_summary(state, image_source_label=label) + "\n")


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------


def cmd_install(state: InstallerState, *, pull: bool) -> None:
    """Mirrors bash ``deploy_all_components`` with progress-bar style stages.

    Root privilege is acquired on demand: when invoked as a regular user
    we call ``sudo -v`` once up-front (prompts for the password), and a
    background thread keeps the sudo timestamp fresh for the duration of
    the install. Individual subprocess calls that need root use
    ``run(..., sudo=True)``; everything else (helm, kubectl) runs as the
    invoking user against their own kubeconfig.
    """
    ensure_sudo_session(assume_yes=state.assume_yes)
    keepalive = start_sudo_keepalive()
    try:
        _cmd_install_inner(state, pull=pull)
    finally:
        keepalive.stop()


def _cmd_install_inner(state: InstallerState, *, pull: bool) -> None:
    """Body of ``cmd_install`` after sudo session has been primed."""
    # Pre-compute the image-stage label so the user knows up-front which path
    # the installer is taking (offline / pull / build).
    if state.offline_mode:
        image_stage_label = "Loading images from offline bundle"
    elif pull:
        image_stage_label = "Pulling custom + external images"
    else:
        image_stage_label = "Pulling external images & building custom images"

    total = 8

    with stage("Detecting GPU", idx=1, total=total):
        detect_and_configure_gpu(state.gpu, gpu_type_override=state.gpu_type)
    paths = state.runtime_paths()

    with stage("Generating values overlay (initial)", idx=2, total=total):
        # First pass: use local detection so image pulls / builds get the
        # right GPU_TARGET. Overlay is regenerated again below from
        # labeller-published labels.
        generate_values_overlay(
            state.gpu,
            image_registry=state.image_registry,
            image_tag=state.image_tag,
            courses=state.courses,
            offline_mode=state.offline_mode,
            overlay_path=paths.overlay_path,
        )

    with stage("Installing helm + k9s", idx=3, total=total):
        install_tools(offline_mode=state.offline_mode, bundle_dir=state.bundle_dir)

    with stage("Installing K3s (single-node)", idx=4, total=total):
        install_k3s_single_node(
            offline_mode=state.offline_mode,
            bundle_dir=state.bundle_dir,
            use_docker=state.use_docker,
            mirror_prefix=state.mirror_prefix,
        )

    with stage(image_stage_label, idx=5, total=total):
        if state.offline_mode and state.bundle_dir is not None:
            load_offline_images(state.bundle_dir)
        elif pull:
            pull_custom_images(
                cfg=state.gpu,
                courses=state.courses,
                image_registry=state.image_registry,
                image_tag=state.image_tag,
                use_docker=state.use_docker,
                k3s_images_dir=state.k3s_images_dir,
                mirror_prefix=state.mirror_prefix,
            )
            pull_external_images(
                skip_build_only=True,  # match bash: `pull_external_images 1`
                use_docker=state.use_docker,
                k3s_images_dir=state.k3s_images_dir,
                mirror_prefix=state.mirror_prefix,
            )
        else:
            pull_external_images(
                skip_build_only=False,
                use_docker=state.use_docker,
                k3s_images_dir=state.k3s_images_dir,
                mirror_prefix=state.mirror_prefix,
            )
            local_image_build(
                [],
                cfg=state.gpu,
                courses=state.courses,
                mirror_prefix=state.mirror_prefix,
                mirror_pip=state.mirror_pip,
                mirror_npm=state.mirror_npm,
                use_docker=state.use_docker,
                k3s_images_dir=state.k3s_images_dir,
            )

    with stage("Deploying ROCm GPU device plugin + node labeller", idx=6, total=total):
        deploy_rocm_gpu_device_plugin(
            offline_mode=state.offline_mode,
            bundle_dir=state.bundle_dir,
        )

    with stage("Refreshing values overlay from node labels", idx=7, total=total):
        refine_gpu_config_from_node_labels(state.gpu)
        generate_values_overlay(
            state.gpu,
            image_registry=state.image_registry,
            image_tag=state.image_tag,
            courses=state.courses,
            offline_mode=state.offline_mode,
            overlay_path=paths.overlay_path,
        )

    with stage("Deploying JupyterHub runtime (helm install + wait)", idx=8, total=total):
        deploy_runtime(paths)

    _print_success_banner()


def _print_success_banner() -> None:
    """Show the post-install celebration / next-steps panel.

    The full "AUP Learning Cloud" figlet logo, a "ready" message, and the
    URL the user should open. Generated with
    https://patorjk.com/software/taag/#p=display&h=0&f=Standard&t=AUP%20Learning%20Cloud
    (matches the helm chart's NOTES.txt).
    Colours come from ``auplc_installer.colors`` so they auto-disable in
    non-TTY / NO_COLOR contexts.
    """
    from auplc_installer.colors import bold, bold_cyan, bold_green, cyan, dim

    logo = r"""
   _    _   _ ____    _                          _                  ____ _                 _
  / \  | | | |  _ \  | |    ___  __ _ _ __ _ __ (_)_ __   __ _     / ___| | ___  _   _  __| |
 / _ \ | | | | |_) | | |   / _ \/ _` | '__| '_ \| | '_ \ / _` |   | |   | |/ _ \| | | |/ _` |
/ ___ \| |_| |  __/  | |__|  __/ (_| | |  | | | | | | | | (_| |   | |___| | (_) | |_| | (_| |
/_/   \_\___/|_|     |_____\___|\__,_|_|  |_| |_|_|_| |_|\__, |    \____|_|\___/ \__,_|\__,_|
                                                         |___/
"""

    log("")
    for line in logo.splitlines():
        log(bold_cyan(line))
    log("    " + bold_green("You have successfully installed AUP Learning Cloud!"))
    log("")
    log("    " + bold("Open in your browser: ") + bold_cyan("http://localhost:30890"))
    log("    " + dim("(auto-logged-in as 'student' — no login needed)"))
    log("")
    log("    " + dim("kubectl is configured at $HOME/.kube/config; try ") + cyan("`kubectl get nodes`"))
    log("")


def cmd_uninstall(state: InstallerState) -> None:
    ensure_sudo_session(assume_yes=state.assume_yes)
    keepalive = start_sudo_keepalive()
    try:
        # Ask the docker-cleanup question UP FRONT, before the live
        # progress bar starts, so the y/N prompt doesn't collide with
        # the in-place spinner redraws.
        docker_decision = _preask_docker_container_cleanup(state)

        with stage("Uninstalling JupyterHub helm release", idx=1, total=2), contextlib.suppress(InstallerError):
            # Match bash: ``remove_aup_learning_cloud_runtime || true``
            remove_runtime()
        with stage("Removing K3s + dummy0", idx=2, total=2):
            remove_k3s(
                assume_yes=state.assume_yes,
                docker_containers_decision=docker_decision,
            )
    finally:
        keepalive.stop()


def _preask_docker_container_cleanup(state: InstallerState) -> bool | None:
    """Decide up-front whether to also remove leftover K8s-managed Docker
    containers (the ones K3s leaves behind in ``--docker`` mode).

    Returning ``True`` / ``False`` short-circuits the prompt that
    ``remove_k3s_docker_containers`` would otherwise raise mid-uninstall.
    Returning ``None`` keeps the legacy behaviour (``--yes`` removes,
    non-TTY skips, TTY prompts).
    """
    from auplc_installer.util import command_exists, log, run_capture

    if state.assume_yes:
        return True
    if not command_exists("docker"):
        return False

    # Detect leftover containers without disturbing the user when there
    # are none.
    try:
        res = run_capture(
            ["docker", "ps", "-a", "-q", "--filter", "label=io.kubernetes.pod.name"],
            check=False,
        )
    except InstallerError:
        return None
    container_ids = [line for line in (res.stdout or "").splitlines() if line.strip()]
    if not container_ids:
        return False
    if not sys.stdin.isatty():
        # Non-interactive: defer to the existing skip-and-print-hint path.
        return None

    # Show what would be removed, then ask once.
    log("")
    log("Leftover Kubernetes-managed Docker containers detected:")
    listing = run_capture(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            "label=io.kubernetes.pod.name",
            "--format",
            "  {{.ID}}  {{.Names}}",
        ],
        check=False,
    )
    if listing.stdout:
        sys.stdout.write(listing.stdout)
    log("")
    log("These are Pod containers left behind by K3s in --docker mode.")
    try:
        ans = input("Also remove them as part of uninstall? [Y/n] ").strip().lower()
    except EOFError:
        return False
    return ans in ("", "y", "yes")


def cmd_install_tools(state: InstallerState) -> None:
    ensure_sudo_session(assume_yes=state.assume_yes)
    install_tools(offline_mode=state.offline_mode, bundle_dir=state.bundle_dir)


def cmd_detect_gpu(state: InstallerState) -> None:
    detect_and_configure_gpu(state.gpu, gpu_type_override=state.gpu_type)


def cmd_pack(state: InstallerState, *, local_build: bool, source_root: Path) -> None:
    with stage("Packing offline bundle"):
        pack_bundle(
            cfg=state.gpu,
            courses=state.courses,
            image_registry=state.image_registry,
            image_tag=state.image_tag,
            mirror_prefix=state.mirror_prefix,
            mirror_pip=state.mirror_pip,
            mirror_npm=state.mirror_npm,
            local_build=local_build,
            source_root=source_root,
            gpu_type_override=state.gpu_type,
        )


# --- dev subcommands ---


def cmd_dev_quick(state: InstallerState) -> None:
    """``./auplc-installer dev`` — rebuild Hub image + restart pod."""
    log("===========================================")
    log("Dev quick cycle: build hub → restart pod")
    log("===========================================")
    detect_and_configure_gpu(state.gpu, gpu_type_override=state.gpu_type)
    with stage("Building Hub image", idx=1, total=2):
        local_image_build(
            ["hub"],
            cfg=state.gpu,
            courses=state.courses,
            mirror_prefix=state.mirror_prefix,
            mirror_pip=state.mirror_pip,
            mirror_npm=state.mirror_npm,
            use_docker=state.use_docker,
            k3s_images_dir=state.k3s_images_dir,
        )
    with stage("Restarting Hub pod", idx=2, total=2):
        dev_quick_rollout()


def cmd_dev_deploy(state: InstallerState) -> None:
    detect_and_configure_gpu(state.gpu, gpu_type_override=state.gpu_type)
    paths = state.runtime_paths()
    refine_gpu_config_from_node_labels(state.gpu)
    generate_values_overlay(
        state.gpu,
        image_registry=state.image_registry,
        image_tag=state.image_tag,
        courses=state.courses,
        offline_mode=state.offline_mode,
        overlay_path=paths.overlay_path,
    )
    deploy_runtime(paths, dev=True)


def cmd_dev_upgrade(state: InstallerState) -> None:
    detect_and_configure_gpu(state.gpu, gpu_type_override=state.gpu_type)
    paths = state.runtime_paths()
    refine_gpu_config_from_node_labels(state.gpu)
    _preserve_courses_for_upgrade(state, paths.overlay_path)
    generate_values_overlay(
        state.gpu,
        image_registry=state.image_registry,
        image_tag=state.image_tag,
        courses=state.courses,
        offline_mode=state.offline_mode,
        overlay_path=paths.overlay_path,
    )
    upgrade_runtime(paths, dev=True)


def cmd_dev_reinstall(state: InstallerState) -> None:
    with contextlib.suppress(InstallerError):
        remove_runtime()
    time.sleep(0.5)
    cmd_dev_deploy(state)


# --- rt subcommands ---


def cmd_rt_install(state: InstallerState) -> None:
    detect_and_configure_gpu(state.gpu, gpu_type_override=state.gpu_type)
    paths = state.runtime_paths()
    refine_gpu_config_from_node_labels(state.gpu)
    generate_values_overlay(
        state.gpu,
        image_registry=state.image_registry,
        image_tag=state.image_tag,
        courses=state.courses,
        offline_mode=state.offline_mode,
        overlay_path=paths.overlay_path,
    )
    deploy_runtime(paths)


def cmd_rt_upgrade(state: InstallerState) -> None:
    detect_and_configure_gpu(state.gpu, gpu_type_override=state.gpu_type)
    paths = state.runtime_paths()
    refine_gpu_config_from_node_labels(state.gpu)
    _preserve_courses_for_upgrade(state, paths.overlay_path)
    generate_values_overlay(
        state.gpu,
        image_registry=state.image_registry,
        image_tag=state.image_tag,
        courses=state.courses,
        offline_mode=state.offline_mode,
        overlay_path=paths.overlay_path,
    )
    upgrade_runtime(paths)


def _preserve_courses_for_upgrade(state: InstallerState, overlay_path: Path) -> None:
    """Inherit the previous overlay's course selection on a bare upgrade.

    A bare ``rt upgrade`` (no ``--courses=`` flag and no env var) leaves
    ``state.courses`` at its default sentinel, which means "all courses".
    Without this helper, regenerating the overlay would silently widen
    the install — e.g. someone who originally picked ``--courses=basic``
    would suddenly get every course's spawn entry back. Reading the prior
    selection out of the existing overlay header preserves the user's
    last decision unless they explicitly override it again.
    """
    if not state.courses.is_default():
        return  # caller passed an explicit selection — respect it.
    previous = try_load_courses_from_overlay(overlay_path)
    if previous is None:
        return  # no overlay yet (or unparseable) — fall back to default.
    state.courses = previous
    log(f"Preserving previous course selection: {previous.description()}")


def cmd_rt_remove(state: InstallerState) -> None:
    remove_runtime()


def cmd_rt_reinstall(state: InstallerState) -> None:
    with contextlib.suppress(InstallerError):
        remove_runtime()
    time.sleep(0.5)
    cmd_rt_install(state)


# --- img subcommands ---


def cmd_img_build(state: InstallerState, targets: Sequence[str]) -> None:
    detect_and_configure_gpu(state.gpu, gpu_type_override=state.gpu_type)
    with stage("Building custom images", idx=1, total=1):
        local_image_build(
            targets,
            cfg=state.gpu,
            courses=state.courses,
            mirror_prefix=state.mirror_prefix,
            mirror_pip=state.mirror_pip,
            mirror_npm=state.mirror_npm,
            use_docker=state.use_docker,
            k3s_images_dir=state.k3s_images_dir,
        )
    log_success("Custom images built successfully.")


def cmd_img_pull(state: InstallerState) -> None:
    with stage("Pulling external images", idx=1, total=1):
        pull_external_images(
            skip_build_only=False,
            use_docker=state.use_docker,
            k3s_images_dir=state.k3s_images_dir,
            mirror_prefix=state.mirror_prefix,
        )
    log_success("External images pulled successfully.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _resolve_source_root() -> Path:
    """The directory that contains the launcher script and the package."""
    # When run via the auplc-installer launcher, sys.argv[0] is the launcher.
    # When run via `python3 -m auplc_installer`, the parent of __file__ works.
    if sys.argv and sys.argv[0]:
        return Path(sys.argv[0]).resolve().parent
    return Path(__file__).resolve().parent.parent


def main(argv: Sequence[str] | None = None) -> None:
    argv = list(argv) if argv is not None else sys.argv[1:]

    # Custom help text (add_help=False on the parser). Intercept -h/--help
    # before argparse runs so `./auplc-installer --help` works as users expect.
    if any(tok in ("-h", "--help") for tok in argv):
        show_help()
        return

    parser = _build_parser()

    # Argparse refuses positional + --foo=bar interleaving in some edge
    # cases. argparse with REMAINDER + global flags works as long as
    # the global flags come before the positional command, but bash
    # accepts them anywhere. To keep CLI compat, do a quick prefilter:
    # extract --foo / -y / --yes from any position into ``flags``.
    filtered: list[str] = []
    flags: list[str] = []
    for tok in argv:
        if (
            tok.startswith("--gpu=")
            or tok.startswith("--runtime=")
            or tok.startswith("--docker=")
            or tok.startswith("--image-source=")
            or tok.startswith("--image-registry=")
            or tok.startswith("--image-tag=")
            or tok.startswith("--mirror=")
            or tok.startswith("--mirror-pip=")
            or tok.startswith("--mirror-npm=")
            or tok.startswith("--courses=")
            or tok in ("-y", "--yes", "-v", "--verbose", "--version", "--dry-run", "--try-run")
        ):
            flags.append(tok)
        else:
            filtered.append(tok)

    args = parser.parse_args(flags + filtered)

    script_dir = _resolve_source_root()
    try:
        state = InstallerState.from_environment(script_dir=script_dir)
        _apply_global_flags(state, args)
        _dispatch(args.command, list(args.rest), state, source_root=script_dir, dry_run=args.dry_run)
    except InstallerError as exc:
        log_error(str(exc))
        sys.exit(1)
    except KeyboardInterrupt:
        log_error("Aborted by user (Ctrl-C).")
        sys.exit(130)


def _dispatch(
    cmd: str | None,
    rest: list[str],
    state: InstallerState,
    *,
    source_root: Path,
    dry_run: bool = False,
) -> None:
    # Default behaviour when invoked with no subcommand: launch the TUI in
    # an interactive terminal, fall back to printing help in a piped /
    # non-TTY context (CI logs, redirects). This matches the user's
    # expectation that `./auplc-installer` "just works" out of the box.
    if cmd is None:
        if sys.stdin.isatty() and sys.stdout.isatty():
            from auplc_installer.tui import run_tui

            run_tui(state)
            return
        show_help()
        sys.exit(1)

    if cmd == "tui":
        from auplc_installer.tui import run_tui

        run_tui(state)
        return

    if cmd == "install":
        legacy_pull = "--pull" in rest
        rest = [t for t in rest if t != "--pull"]
        if rest:
            raise InstallerError(f"Unexpected install argument(s): {' '.join(rest)}")
        if dry_run:
            cmd_install_plan(state, legacy_pull=legacy_pull)
            return
        pull, _ = _install_pull_and_label(state, legacy_pull=legacy_pull)
        cmd_install(state, pull=pull)
        return

    if dry_run:
        raise InstallerError("--dry-run is only supported with the install command")

    if cmd == "pack":
        local_build = bool(rest) and rest[0] == "--local"
        cmd_pack(state, local_build=local_build, source_root=source_root)
        return

    if cmd == "uninstall":
        cmd_uninstall(state)
        return

    if cmd == "install-tools":
        cmd_install_tools(state)
        return

    if cmd == "detect-gpu":
        cmd_detect_gpu(state)
        return

    if cmd == "dev":
        sub = rest[0] if rest else ""
        if sub == "deploy":
            cmd_dev_deploy(state)
        elif sub == "upgrade":
            cmd_dev_upgrade(state)
        elif sub == "reinstall":
            cmd_dev_reinstall(state)
        elif sub == "":
            cmd_dev_quick(state)
        else:
            log_error("Usage: auplc-installer dev {deploy|upgrade|reinstall} or just 'dev' for quick rebuild")
            sys.exit(1)
        return

    if cmd == "rt":
        sub = rest[0] if rest else ""
        if sub == "install":
            cmd_rt_install(state)
        elif sub == "upgrade":
            cmd_rt_upgrade(state)
        elif sub == "remove":
            cmd_rt_remove(state)
        elif sub == "reinstall":
            cmd_rt_reinstall(state)
        else:
            log_error("Usage: auplc-installer rt {install|upgrade|remove|reinstall}")
            sys.exit(1)
        return

    if cmd == "img":
        sub = rest[0] if rest else ""
        if sub == "build":
            targets = rest[1:]
            cmd_img_build(state, targets)
        elif sub == "pull":
            cmd_img_pull(state)
        else:
            log_error(
                "Usage: auplc-installer img {build [target...]|pull}. "
                "Targets: all, hub, base-cpu, base-rocm, code, code-cpu, code-gpu, cv, dl, llm, physim"
            )
            sys.exit(1)
        return

    # Legacy long-form aliases (still supported)
    if cmd == "install-runtime":
        cmd_rt_install(state)
        return
    if cmd == "remove-runtime":
        cmd_rt_remove(state)
        return
    if cmd == "upgrade-runtime":
        cmd_rt_upgrade(state)
        return
    if cmd == "build-images":
        cmd_img_build(state, [])
        return
    if cmd == "pull-images":
        cmd_img_pull(state)
        return

    if cmd in ("help", "--help", "-h"):
        show_help()
        return

    show_help()
    sys.exit(1)
