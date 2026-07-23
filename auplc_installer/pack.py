# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Offline-bundle packing.

Mirrors bash ``pack_*`` and ``pack_bundle``. Output is a ``.tar.gz`` archive
that, when untarred on an air-gapped host, can be installed via the bundled
``auplc-installer`` (Python launcher).
"""

from __future__ import annotations

import datetime as _dt
import os
import re
import shutil
import urllib.parse
from importlib import metadata
from pathlib import Path

from auplc_installer.catalog import HUB_IMAGE_NAME, CourseSelection
from auplc_installer.gpu import GpuConfig, detect_and_configure_gpu
from auplc_installer.images import (
    EXTERNAL_IMAGES,
    pull_and_tag,
)
from auplc_installer.k3s import (
    HELM_VERSION,
    K3S_VERSION,
    K9S_VERSION,
)
from auplc_installer.manifest import BundleManifest
from auplc_installer.rocm import (
    ROCM_DEVICE_PLUGIN_COMMIT,
    ROCM_DEVICE_PLUGIN_SHA256,
    ROCM_LABELLER_SHA256,
)
from auplc_installer.util import (
    InstallerError,
    chmod_x,
    log,
    log_step,
    require_command,
    run,
    run_capture,
    run_streaming,
    sanitize_image_tag,
    verify_sha256,
)

MAKE_IMAGE_REGISTRY = "ghcr.io/amdresearch"
PY_YAML_DISTRIBUTION = "PyYAML"
PY_YAML_LICENSE_DESTINATION = Path("third_party_licenses") / "PyYAML-LICENSE"
PY_YAML_SYSTEM_LICENSE_CANDIDATES = (Path("/usr/share/doc/python3-yaml/copyright"),)

# ---------------------------------------------------------------------------
# Stage population
# ---------------------------------------------------------------------------


def pack_download_binaries(staging: Path) -> None:
    log_step("Downloading binaries")
    bin_dir = staging / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)

    k3s_url_ver = urllib.parse.quote(K3S_VERSION, safe="")  # e.g. v1.32.3+k3s1 → v1.32.3%2Bk3s1

    log(f"  K3s {K3S_VERSION}...")
    run(
        [
            "wget",
            "-q",
            f"https://github.com/k3s-io/k3s/releases/download/{k3s_url_ver}/k3s",
            "-O",
            str(bin_dir / "k3s"),
        ]
    )
    chmod_x(bin_dir / "k3s")

    log("  K3s install script...")
    run(["wget", "-q", "https://get.k3s.io", "-O", str(bin_dir / "k3s-install.sh")])
    chmod_x(bin_dir / "k3s-install.sh")

    log(f"  Helm {HELM_VERSION}...")
    helm_tar = "/tmp/helm-pack.tar.gz"
    run(
        [
            "wget",
            "-q",
            f"https://get.helm.sh/helm-{HELM_VERSION}-linux-amd64.tar.gz",
            "-O",
            helm_tar,
        ]
    )
    run(["tar", "-zxf", helm_tar, "-C", "/tmp", "linux-amd64/helm"])
    shutil.move("/tmp/linux-amd64/helm", str(bin_dir / "helm"))
    chmod_x(bin_dir / "helm")
    os.remove(helm_tar)
    shutil.rmtree("/tmp/linux-amd64", ignore_errors=True)

    log(f"  K9s {K9S_VERSION}...")
    run(
        [
            "wget",
            "-q",
            f"https://github.com/derailed/k9s/releases/download/{K9S_VERSION}/k9s_linux_amd64.deb",
            "-O",
            str(bin_dir / "k9s_linux_amd64.deb"),
        ]
    )


def pack_download_k3s_images(staging: Path) -> None:
    log_step("Downloading K3s airgap images")
    images_dir = staging / "k3s-images"
    images_dir.mkdir(parents=True, exist_ok=True)

    k3s_url_ver = urllib.parse.quote(K3S_VERSION, safe="")
    run(
        [
            "wget",
            "-q",
            f"https://github.com/k3s-io/k3s/releases/download/{k3s_url_ver}/k3s-airgap-images-amd64.tar.zst",
            "-O",
            str(images_dir / "k3s-airgap-images-amd64.tar.zst"),
        ]
    )


def pack_save_manifests(staging: Path) -> None:
    log_step("Saving manifests")
    out_dir = staging / "manifests"
    out_dir.mkdir(parents=True, exist_ok=True)

    dp_yaml = out_dir / "k8s-ds-amdgpu-dp.yaml"
    run(
        [
            "wget",
            "-q",
            f"https://raw.githubusercontent.com/ROCm/k8s-device-plugin/{ROCM_DEVICE_PLUGIN_COMMIT}/k8s-ds-amdgpu-dp.yaml",
            "-O",
            str(dp_yaml),
        ]
    )
    verify_sha256(dp_yaml, ROCM_DEVICE_PLUGIN_SHA256)
    log("  Saved ROCm device plugin DaemonSet.")

    lab_yaml = out_dir / "k8s-ds-amdgpu-labeller.yaml"
    run(
        [
            "wget",
            "-q",
            f"https://raw.githubusercontent.com/ROCm/k8s-device-plugin/{ROCM_DEVICE_PLUGIN_COMMIT}/k8s-ds-amdgpu-labeller.yaml",
            "-O",
            str(lab_yaml),
        ]
    )
    verify_sha256(lab_yaml, ROCM_LABELLER_SHA256)
    log("  Saved ROCm node labeller DaemonSet.")


def pack_copy_chart(staging: Path) -> None:
    log_step("Copying chart and config")
    shutil.copytree("runtime/chart", staging / "chart")
    (staging / "config").mkdir(parents=True, exist_ok=True)
    shutil.copy2("runtime/values.yaml", staging / "config" / "values.yaml")


# ---------------------------------------------------------------------------
# Custom images
# ---------------------------------------------------------------------------


def pack_save_custom_images_pull(
    staging: Path,
    *,
    cfg: GpuConfig,
    courses: CourseSelection,
    image_registry: str,
    image_tag: str,
    mirror_prefix: str,
) -> None:
    """Pull custom images from GHCR, then save them as a single tar."""
    tag = f"{image_tag}-{cfg.image_profile}"
    log_step(f"Pulling and saving custom images ({image_registry})")
    log(f"    Courses: {courses.description()}")

    out_dir = staging / "images" / "custom"
    out_dir.mkdir(parents=True, exist_ok=True)

    failed = 0
    all_refs: list[str] = []

    # GPU-tagged courses
    for name in courses.gpu_image_basenames():
        image = f"{image_registry}/{name}:{tag}"
        if pull_and_tag(image, mirror_prefix=mirror_prefix):
            all_refs.append(f"{image_registry}/{name}:{tag}")
            log(f"  Pulled: {name} (:{tag})")
        else:
            failed += 1

    # Plain-tagged: hub (always) + selected non-GPU courses
    plain_names = [HUB_IMAGE_NAME, *courses.plain_image_basenames()]
    for name in plain_names:
        image = f"{image_registry}/{name}:{image_tag}"
        if pull_and_tag(image, mirror_prefix=mirror_prefix):
            run(["docker", "tag", image, f"{image_registry}/{name}:latest"])
            all_refs.append(f"{image_registry}/{name}:latest")
            all_refs.append(f"{image_registry}/{name}:{image_tag}")
            log(f"  Pulled: {name} (:latest + :{image_tag})")
        else:
            failed += 1

    if failed:
        shutil.rmtree(staging, ignore_errors=True)
        raise InstallerError(
            f"{failed} custom image(s) failed to pull. Bundle would be incomplete.\n"
            f"  Check that IMAGE_REGISTRY ({image_registry}) is correct and you have pull access."
        )
    if not all_refs:
        shutil.rmtree(staging, ignore_errors=True)
        raise InstallerError("no images to save (course selection produced empty list).")

    log("  Saving all custom images (shared layers deduplicated)...")
    out_path = out_dir / "auplc-custom.tar"
    run(["docker", "save", *all_refs, "-o", str(out_path)])
    log(f"  Saved: {out_path}")


def pack_save_custom_images_local(
    staging: Path,
    *,
    cfg: GpuConfig,
    courses: CourseSelection,
    image_registry: str,
    image_tag: str,
    mirror_prefix: str,
    mirror_pip: str,
    mirror_npm: str,
) -> None:
    """Build custom images locally via Makefile, then save them.

    The Makefile produces images under ``ghcr.io/amdresearch`` with ``:latest``
    and ``:latest-<image_profile>`` regardless of ``image_tag``. To stay aligned with the ``--pull`` path (and with the
    ``:{image_tag}-{image_profile}`` reference that ``overlay.emit_overlay``
    bakes into the bundle's values.local.yaml), retag the GPU images to
    ``:{image_tag}-<image_profile>`` and the plain images to ``:{image_tag}``
    before saving. Skipped when the desired tag already matches the source
    so the no-op ``image_tag=latest`` case stays a docker-tag-no-op.
    """
    built_gpu_tag = f"latest-{cfg.image_profile}"
    desired_gpu_tag = f"{image_tag}-{cfg.image_profile}"
    log_step("Building and saving custom images locally")
    log(f"    Courses: {courses.description()}")

    out_dir = staging / "images" / "custom"
    out_dir.mkdir(parents=True, exist_ok=True)

    if courses.is_default():
        make_targets = ["all"]
    else:
        make_targets = ["hub", *courses.make_targets()]

    run_streaming(
        [
            "make",
            f"AUP_IMAGE_PROFILE={cfg.image_profile}",
            f"MIRROR_PREFIX={mirror_prefix}",
            f"MIRROR_PIP={mirror_pip}",
            f"MIRROR_NPM={mirror_npm}",
            *make_targets,
        ],
        cwd="dockerfiles/",
    )

    log_step("Saving built images to bundle (shared layers deduplicated)")

    all_refs: list[str] = []
    for name in courses.gpu_image_basenames():
        source = f"{MAKE_IMAGE_REGISTRY}/{name}:{built_gpu_tag}"
        destination = f"{image_registry}/{name}:{desired_gpu_tag}"
        if source != destination:
            run(
                [
                    "docker",
                    "tag",
                    source,
                    destination,
                ]
            )
        all_refs.append(destination)
        log(f"  Queued: {name} (:{desired_gpu_tag})")

    plain_names = [HUB_IMAGE_NAME, *courses.plain_image_basenames()]
    for name in plain_names:
        source = f"{MAKE_IMAGE_REGISTRY}/{name}:latest"
        latest_destination = f"{image_registry}/{name}:latest"
        tagged_destination = f"{image_registry}/{name}:{image_tag}"
        if source != latest_destination:
            run(["docker", "tag", source, latest_destination])
        if tagged_destination != latest_destination and source != tagged_destination:
            run(
                [
                    "docker",
                    "tag",
                    source,
                    tagged_destination,
                ]
            )
        all_refs.append(latest_destination)
        if tagged_destination != latest_destination:
            all_refs.append(tagged_destination)
        log(f"  Queued: {name} (:latest + :{image_tag})")

    if not all_refs:
        shutil.rmtree(staging, ignore_errors=True)
        raise InstallerError("no images to save (course selection produced empty list).")

    out_path = out_dir / "auplc-custom.tar"
    run(["docker", "save", *all_refs, "-o", str(out_path)])
    log(f"  Saved: {out_path}")


# ---------------------------------------------------------------------------
# External images (always pulled at pack time, even with --local)
# ---------------------------------------------------------------------------


def pack_save_external_images(staging: Path, *, mirror_prefix: str) -> None:
    log_step("Pulling and saving external images")
    out_dir = staging / "images" / "external"
    out_dir.mkdir(parents=True, exist_ok=True)

    pack_images: list[str] = list(EXTERNAL_IMAGES)

    # Add ROCm device plugin / labeller images parsed from the saved manifests
    for manifest_name in (
        "k8s-ds-amdgpu-dp.yaml",
        "k8s-ds-amdgpu-labeller.yaml",
    ):
        m_path = staging / "manifests" / manifest_name
        if not m_path.is_file():
            continue
        text = m_path.read_text(encoding="utf-8")
        m = re.search(r"^\s*image:\s*(\S+)", text, re.MULTILINE)
        if m:
            rocm_image = m.group(1)
            log(f"  Found ROCm image ({manifest_name}): {rocm_image}")
            pack_images.append(rocm_image)

    failed: list[str] = []
    for image in pack_images:
        if pull_and_tag(image, mirror_prefix=mirror_prefix):
            filename = image.replace("/", "-").replace(":", "-") + ".tar"
            out_path = out_dir / filename
            run(["docker", "save", image, "-o", str(out_path)])
            log(f"  Saved: {image}")
        else:
            failed.append(image)

    if failed:
        for img in failed:
            log(f"    - {img}")
        shutil.rmtree(staging, ignore_errors=True)
        raise InstallerError(f"{len(failed)} external image(s) failed to pull.")


# ---------------------------------------------------------------------------
# Manifest + installer payload
# ---------------------------------------------------------------------------


def pack_write_manifest(
    staging: Path,
    *,
    cfg: GpuConfig,
    image_registry: str,
    image_tag: str,
) -> None:
    BundleManifest(
        build_date=_dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        image_profile=cfg.image_profile,
        accelerator_key=cfg.accelerator_key,
        accelerator_env=cfg.accelerator_env,
        image_registry=image_registry,
        image_tag=image_tag,
        k3s_version=K3S_VERSION,
        helm_version=HELM_VERSION,
        k9s_version=K9S_VERSION,
    ).write(staging / "manifest.json")


def _pyyaml_package_path() -> Path | None:
    try:
        import yaml
    except ModuleNotFoundError:
        return None
    package_path = Path(yaml.__file__).resolve().parent
    return package_path if (package_path / "__init__.py").is_file() else None


def _pyyaml_license_path() -> Path | None:
    try:
        distribution = metadata.distribution(PY_YAML_DISTRIBUTION)
    except metadata.PackageNotFoundError:
        distribution = None
    if distribution is not None:
        for file in distribution.files or ():
            if file.name == "LICENSE" and "licenses" in file.parts:
                license_path = Path(distribution.locate_file(file))
                if license_path.is_file():
                    return license_path
    for license_path in PY_YAML_SYSTEM_LICENSE_CANDIDATES:
        if license_path.is_file():
            return license_path
    return None


def _copy_pure_python_pyyaml(staging: Path) -> None:
    package_path = _pyyaml_package_path()
    if package_path is None:
        raise InstallerError("Mandatory PyYAML package could not be located for the offline bundle.")
    license_path = _pyyaml_license_path()
    if license_path is None:
        raise InstallerError("Mandatory PyYAML license could not be located for the offline bundle.")

    vendor_package = staging / "_vendor" / "yaml"
    for source in package_path.rglob("*"):
        relative = source.relative_to(package_path)
        if "__pycache__" in relative.parts or source.name.startswith("_yaml."):
            continue
        destination = vendor_package / relative
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif source.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    license_destination = staging / PY_YAML_LICENSE_DESTINATION
    license_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(license_path, license_destination)


def _copy_installer_payload(staging: Path, *, source_root: Path) -> None:
    """Copy the launcher script and the auplc_installer/ package into the bundle.

    The payload includes pure-Python PyYAML and its third-party license so the
    extracted installer runs without network or package installation. It also
    ships ``requirements-installer.txt`` for source and venv installs; optional
    ``questionary`` / ``prompt_toolkit`` are not vendored, so their absence uses
    the stdlib numbered-menu TUI fallback.
    """
    reqs_src = source_root / "requirements-installer.txt"
    if not reqs_src.is_file():
        raise InstallerError(f"Mandatory installer requirements file not found at {reqs_src}.")

    launcher_src = source_root / "auplc-installer"
    launcher_dst = staging / "auplc-installer"
    if not launcher_src.is_file():
        raise InstallerError(
            f"Launcher script not found at {launcher_src}. "
            "Make sure auplc-installer (the Python entry script) is present."
        )
    shutil.copy2(launcher_src, launcher_dst)
    chmod_x(launcher_dst)

    pkg_src = source_root / "auplc_installer"
    pkg_dst = staging / "auplc_installer"
    if not pkg_src.is_dir():
        raise InstallerError(f"Python package not found at {pkg_src}. Bundle would be unrunnable.")
    if pkg_dst.exists():
        shutil.rmtree(pkg_dst)
    # Skip __pycache__ when copying so the bundle stays small.
    shutil.copytree(pkg_src, pkg_dst, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(reqs_src, staging / "requirements-installer.txt")
    _copy_pure_python_pyyaml(staging)


# ---------------------------------------------------------------------------
# Top-level entry
# ---------------------------------------------------------------------------


def pack_bundle(
    *,
    cfg: GpuConfig,
    courses: CourseSelection,
    image_registry: str,
    image_tag: str,
    mirror_prefix: str,
    mirror_pip: str,
    mirror_npm: str,
    local_build: bool,
    source_root: Path,
    gpu_type_override: str = "",
) -> Path:
    """Mirrors bash ``pack_bundle``.

    Returns the path to the produced ``.tar.gz`` archive.
    """
    # Sanitise IMAGE_TAG: Docker tags cannot contain '/' (e.g. branch names)
    image_tag = sanitize_image_tag(image_tag)

    log("===========================================")
    log("AUP Learning Cloud - Pack Offline Bundle")
    log("  Image source: " + ("build" if local_build else "pull"))
    log("===========================================")

    require_command("docker", install_hint="Docker is required for pack.")

    detect_and_configure_gpu(cfg, gpu_type_override=gpu_type_override)

    date_stamp = _dt.datetime.now().strftime("%Y%m%d")
    bundle_name = f"auplc-bundle-{cfg.image_profile}-{date_stamp}"
    staging = Path(bundle_name)
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    _copy_installer_payload(staging, source_root=source_root)

    pack_download_binaries(staging)
    pack_download_k3s_images(staging)
    pack_save_manifests(staging)

    if local_build:
        pack_save_custom_images_local(
            staging,
            cfg=cfg,
            courses=courses,
            image_registry=image_registry,
            image_tag=image_tag,
            mirror_prefix=mirror_prefix,
            mirror_pip=mirror_pip,
            mirror_npm=mirror_npm,
        )
    else:
        pack_save_custom_images_pull(
            staging,
            cfg=cfg,
            courses=courses,
            image_registry=image_registry,
            image_tag=image_tag,
            mirror_prefix=mirror_prefix,
        )

    pack_save_external_images(staging, mirror_prefix=mirror_prefix)
    pack_copy_chart(staging)
    pack_write_manifest(
        staging,
        cfg=cfg,
        image_registry=image_registry,
        image_tag=image_tag,
    )

    archive = Path(f"{bundle_name}.tar.gz")
    log("===========================================")
    log(f"Creating archive: {archive} ...")
    log("===========================================")
    run(["tar", "czf", str(archive), f"{bundle_name}/"])
    shutil.rmtree(staging)

    size_res = run_capture(["du", "-sh", str(archive)], check=False)
    size = (size_res.stdout or "").split()[0] if size_res.stdout else "?"
    log("===========================================")
    log(f"Bundle created: {archive} ({size})")
    log("")
    log("Deploy on air-gapped machine:")
    log(f"  tar xzf {archive}")
    log(f"  cd {bundle_name}")
    log("  sudo ./auplc-installer install")
    log("  (The bundle includes PyYAML; no network or package installation is required.)")
    log("===========================================")
    return archive
