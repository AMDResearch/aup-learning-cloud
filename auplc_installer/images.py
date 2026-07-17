# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Container image management: pull / build / save / mirror handling."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from auplc_installer.catalog import HUB_IMAGE_NAME, CourseSelection
from auplc_installer.gpu import GpuConfig
from auplc_installer.util import (
    InstallerError,
    log,
    log_section,
    log_success,
    log_warn,
    require_command,
    run,
    run_streaming,
)

# External images required by JupyterHub at runtime
EXTERNAL_IMAGES: tuple[str, ...] = (
    "quay.io/jupyterhub/k8s-hub:4.3.3",
    "quay.io/jupyterhub/configurable-http-proxy:5.2.0",
    "quay.io/jupyterhub/k8s-secret-sync:4.3.3",
    "quay.io/jupyterhub/k8s-network-tools:4.3.3",
    "quay.io/jupyterhub/k8s-image-awaiter:4.3.3",
    "quay.io/jupyterhub/k8s-singleuser-sample:4.3.3",
    "registry.k8s.io/kube-scheduler:v1.30.14",
    "registry.k8s.io/pause:3.10.1",
    # traefik is already included in the K3s airgap images bundle
    "curlimages/curl:8.5.0",
    "alpine/git:2.47.2",
)


# Base images only needed for local Docker build, not for runtime or bundle.
# Tags MUST be pinned: a missing tag implicitly resolves to ``:latest`` and makes
# pack-time pre-pulls non-deterministic (and out of sync with the FROM lines in
# dockerfiles/Base/*). Keep these tags in lock-step with the corresponding ARG
# defaults in dockerfiles/Base/Dockerfile.{cpu,rocm} so the pre-pulled cache is
# reusable by ``make`` instead of being silently re-fetched.
BUILD_ONLY_IMAGES: tuple[str, ...] = (
    "node:20-alpine",
    "ubuntu:24.04",
    "quay.io/jupyter/base-notebook:python-3.12",
)


# ---------------------------------------------------------------------------
# Mirror / image-ref helpers
# ---------------------------------------------------------------------------


def resolve_pull_ref(image: str, *, mirror_prefix: str) -> str:
    """Apply a registry mirror prefix to an image reference for pulling.

    Mirrors bash ``resolve_pull_ref``: bare image names get
    ``docker.io/library/`` prefixed; ``foo/bar`` (no dot in first segment)
    becomes ``docker.io/foo/bar``; explicit registries are kept as-is.
    Then ``mirror_prefix/`` is prepended.
    """
    full = image
    first_segment = image.split("/", 1)[0]
    if "/" in image:
        if "." not in first_segment:
            full = f"docker.io/{image}"
    else:
        full = f"docker.io/library/{image}"
    if mirror_prefix:
        return f"{mirror_prefix}/{full}"
    return full


def pull_and_tag(image: str, *, mirror_prefix: str = "") -> bool:
    """Pull ``image`` (via mirror if set) and re-tag back to the original name.

    Returns True on success, False on failure (no exception). Mirrors bash
    ``pull_and_tag``.
    """
    pull_ref = resolve_pull_ref(image, mirror_prefix=mirror_prefix)
    log(f"  Pulling: {pull_ref}")
    rc = run_streaming(["docker", "pull", pull_ref], check=False)
    if rc != 0:
        log(f"  FAILED: {image}")
        return False
    if pull_ref != image:
        run(["docker", "tag", pull_ref, image])
    return True


# ---------------------------------------------------------------------------
# Local image build (Makefile)
# ---------------------------------------------------------------------------


def local_image_build(
    targets: Sequence[str],
    *,
    cfg: GpuConfig,
    courses: CourseSelection,
    mirror_prefix: str,
    mirror_pip: str,
    mirror_npm: str,
    use_docker: bool,
    k3s_images_dir: str,
) -> None:
    """Run ``make`` in ``dockerfiles/``.

    ``targets`` empty + default selection → ``["all"]``.
    ``targets`` empty + non-default selection → ``["hub", *make_targets()]``.
    ``targets`` non-empty (caller supplied) → respect them as-is (so
    ``dev_quick`` can keep passing ``["hub"]``).
    """
    require_command("docker", install_hint="Install Docker first.")

    final_targets: list[str]
    if targets:
        final_targets = list(targets)
    elif courses.is_default():
        final_targets = ["all"]
    else:
        final_targets = ["hub", *courses.make_targets()]
        if len(final_targets) == 1:
            log("Building hub image only (no courses selected).")
    log(f"Building local images: {' '.join(final_targets)}")

    if not use_docker:
        if not Path(k3s_images_dir).is_dir():
            run(["mkdir", "-p", k3s_images_dir], sudo=True)
        log(f"Build & copy images to K3s image pool ({k3s_images_dir})")
    else:
        log("Build images in Docker (K3S_USE_DOCKER=1; K3s will use them directly)")

    save_images_for_make = "" if use_docker else "1"
    images_dir_for_make = "" if use_docker else k3s_images_dir

    cmd = [
        "make",
        f"GPU_TARGET={cfg.gpu_target}",
        f"SAVE_IMAGES={save_images_for_make}",
        f"K3S_IMAGES_DIR={images_dir_for_make}",
        f"MIRROR_PREFIX={mirror_prefix}",
        f"MIRROR_PIP={mirror_pip}",
        f"MIRROR_NPM={mirror_npm}",
        *final_targets,
    ]
    run_streaming(cmd, cwd="dockerfiles/")
    log("-------------------------------------------")


# ---------------------------------------------------------------------------
# Custom image pull (from GHCR)
# ---------------------------------------------------------------------------


def pull_custom_images(
    *,
    cfg: GpuConfig,
    courses: CourseSelection,
    image_registry: str,
    image_tag: str,
    use_docker: bool,
    k3s_images_dir: str,
    mirror_prefix: str,
) -> None:
    """Mirrors bash ``pull_custom_images``."""
    require_command("docker")

    tag = f"{image_tag}-{cfg.gpu_target}"
    log_section(
        "Pulling pre-built custom images from registry...\n"
        f"  GPU_TARGET={cfg.gpu_target}, tag={tag}\n"
        f"  Courses: {courses.description()}"
    )

    if not use_docker and not Path(k3s_images_dir).is_dir():
        run(["mkdir", "-p", k3s_images_dir], sudo=True)

    failed: list[str] = []

    # Hub image (infrastructure, always required, plain-tagged)
    hub_image = f"{image_registry}/{HUB_IMAGE_NAME}:{image_tag}"
    if pull_and_tag(hub_image, mirror_prefix=mirror_prefix):
        if not use_docker:
            run(
                ["docker", "save", hub_image, "-o", f"{k3s_images_dir}/{HUB_IMAGE_NAME}.tar"],
                sudo=True,
            )
    else:
        failed.append(hub_image)

    # GPU-tagged course images
    for name in courses.gpu_image_basenames():
        image = f"{image_registry}/{name}:{tag}"
        if pull_and_tag(image, mirror_prefix=mirror_prefix):
            run(["docker", "tag", image, f"{image_registry}/{name}:latest"])
            if not use_docker:
                run(
                    [
                        "docker",
                        "save",
                        f"{image_registry}/{name}:latest",
                        f"{image_registry}/{name}:{tag}",
                        "-o",
                        f"{k3s_images_dir}/{name}.tar",
                    ],
                    sudo=True,
                )
        else:
            failed.append(image)

    # Plain-tagged course images
    for name in courses.plain_image_basenames():
        image = f"{image_registry}/{name}:{image_tag}"
        if pull_and_tag(image, mirror_prefix=mirror_prefix):
            if not use_docker:
                run(
                    ["docker", "save", image, "-o", f"{k3s_images_dir}/{name}.tar"],
                    sudo=True,
                )
        else:
            failed.append(image)

    log("===========================================")
    if not failed:
        log_success("All custom images pulled successfully!")
    else:
        log("Failed images:")
        for img in failed:
            log(f"  - {img}")
        log_warn("Some custom images failed.")
    log("===========================================")


# ---------------------------------------------------------------------------
# External image pull (k8s control plane, jupyterhub side images, etc.)
# ---------------------------------------------------------------------------


def pull_external_images(
    *,
    skip_build_only: bool,
    use_docker: bool,
    k3s_images_dir: str,
    mirror_prefix: str,
) -> None:
    """Mirrors bash ``pull_external_images``."""
    require_command("docker")

    log_section("Pulling external images..." + (f"\nUsing mirror prefix: {mirror_prefix}" if mirror_prefix else ""))

    if not use_docker and not Path(k3s_images_dir).is_dir():
        run(["mkdir", "-p", k3s_images_dir], sudo=True)

    images_to_pull: list[str] = list(EXTERNAL_IMAGES)
    if not skip_build_only:
        images_to_pull += list(BUILD_ONLY_IMAGES)

    failed: list[str] = []

    for image in images_to_pull:
        pull_image = resolve_pull_ref(image, mirror_prefix=mirror_prefix)

        log("-------------------------------------------")
        log(f"Pulling: {pull_image}")

        rc = run_streaming(["docker", "pull", pull_image], check=False)
        if rc != 0:
            log(f"Failed to pull: {pull_image}")
            failed.append(image)
            continue

        if pull_image != image:
            run(["docker", "tag", pull_image, image])

        if not use_docker and k3s_images_dir:
            filename = image.replace("/", "-").replace(":", "-") + ".tar"
            out_path = f"{k3s_images_dir}/{filename}"
            log(f"Saving to: {out_path}")
            try:
                run(["docker", "save", image, "-o", out_path], sudo=True)
                log(f"Saved: {image}")
            except InstallerError:
                log(f"Failed to save: {image}")
                failed.append(image)
        else:
            log(f"In Docker: {image}")

    log("===========================================")
    if not failed:
        log_success("All external images pulled and saved successfully!")
    else:
        log("Failed images:")
        for img in failed:
            log(f"  - {img}")
        log_warn("Some images failed. Deployment may require internet access.")
    log("===========================================")


# ---------------------------------------------------------------------------
# Offline image load
# ---------------------------------------------------------------------------


def load_offline_images(bundle_dir: Path) -> None:
    """Import every ``.tar`` from the bundle into the K3s containerd store."""
    log_section("Loading images from offline bundle...")

    loaded = 0
    failed = 0

    for subdir in ("images/custom", "images/external"):
        d = bundle_dir / subdir
        if not d.is_dir():
            continue
        for tar_file in sorted(d.iterdir()):
            if not tar_file.is_file() or tar_file.suffix != ".tar":
                continue
            log(f"  Importing: {tar_file.name}")
            rc = run_streaming(
                ["k3s", "ctr", "images", "import", str(tar_file)],
                sudo=True,
                check=False,
            )
            if rc == 0:
                loaded += 1
            else:
                log("    Failed!")
                failed += 1

    log("===========================================")
    log(f"Loaded {loaded} images, {failed} failed")
    if failed > 0:
        raise InstallerError(f"{failed} image(s) failed to import. Bundle may be corrupted.")
    log("===========================================")
