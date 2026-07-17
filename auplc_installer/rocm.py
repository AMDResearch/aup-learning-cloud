# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""ROCm device plugin and node-labeller DaemonSet deployment.

Mirrors bash ``deploy_rocm_gpu_device_plugin`` / ``deploy_rocm_gpu_node_labeller``.
Pulled out of helm.py because these are kubectl operations (manifest apply
+ wait), not Helm releases.
"""

from __future__ import annotations

import os
from pathlib import Path

from auplc_installer.util import (
    log,
    run,
    run_capture,
    run_streaming,
    verify_sha256,
)

# Pinned ROCm device-plugin / labeller manifests (from the same upstream commit)
ROCM_DEVICE_PLUGIN_COMMIT = "dea1db13f05159e64d8114bca4c31f48c3cfcac6"
ROCM_DEVICE_PLUGIN_SHA256 = "b751e467feecf6118bed1de8ba80b9abff01c1f52a6b0b8f31aca3609e6e9dbd"
ROCM_LABELLER_SHA256 = "c3e456967efdf14bcfeb97d8f87ca75a402cc6c7c8c6201a320efdd0370fa7aa"


def _exists_daemonset(name: str) -> bool:
    res = run_capture(
        ["kubectl", "get", f"ds/{name}", "--namespace=kube-system"],
        check=False,
    )
    return res.returncode == 0


def _wait_daemonset_ready(name: str) -> None:
    """``kubectl wait`` for the daemon set's first ready replica.

    Mirrors bash: ``kubectl wait --for=jsonpath='{.status.numberReady}'=1``.
    """
    rc = run_streaming(
        [
            "kubectl",
            "wait",
            "--for=jsonpath={.status.numberReady}=1",
            "--namespace=kube-system",
            f"ds/{name}",
            "--timeout=300s",
        ],
        check=False,
    )
    if rc != 0:
        from auplc_installer.util import InstallerError

        raise InstallerError(f"DaemonSet {name} did not become ready within 300s")


def _patch_image_pull_policy(daemonset: str) -> None:
    """Avoid pulling ROCm DaemonSet images when they already exist locally."""
    patch = '[{"op":"add","path":"/spec/template/spec/containers/0/imagePullPolicy","value":"IfNotPresent"}]'
    run(
        [
            "kubectl",
            "patch",
            "ds",
            daemonset,
            "-n",
            "kube-system",
            "--type=json",
            "-p",
            patch,
        ]
    )


def deploy_rocm_gpu_device_plugin(*, offline_mode: bool, bundle_dir: Path | None) -> None:
    log("Deploying ROCm GPU device plugin...")

    if _exists_daemonset("amdgpu-device-plugin-daemonset"):
        log("ROCm GPU device plugin already exists.")
    else:
        if offline_mode and bundle_dir is not None:
            run(
                [
                    "kubectl",
                    "create",
                    "-f",
                    str(bundle_dir / "manifests/k8s-ds-amdgpu-dp.yaml"),
                ]
            )
        else:
            url = (
                "https://raw.githubusercontent.com/ROCm/k8s-device-plugin/"
                f"{ROCM_DEVICE_PLUGIN_COMMIT}/k8s-ds-amdgpu-dp.yaml"
            )
            tmp = "/tmp/k8s-ds-amdgpu-dp.yaml"
            run(["wget", url, "-O", tmp])
            verify_sha256(tmp, ROCM_DEVICE_PLUGIN_SHA256)
            run(["kubectl", "create", "-f", tmp])
            os.remove(tmp)
        log("Successfully deployed ROCm GPU device plugin.")

    _patch_image_pull_policy("amdgpu-device-plugin-daemonset")
    _wait_daemonset_ready("amdgpu-device-plugin-daemonset")

    deploy_rocm_gpu_node_labeller(offline_mode=offline_mode, bundle_dir=bundle_dir)


def deploy_rocm_gpu_node_labeller(*, offline_mode: bool, bundle_dir: Path | None) -> None:
    """Deploy the labeller DaemonSet.

    The labeller stamps each GPU node with labels like
    ``amd.com/gpu.product-name`` so values.yaml nodeSelectors can target
    GPUs without manual ``kubectl label`` invocations.
    """
    log("Deploying ROCm GPU node labeller...")
    if _exists_daemonset("amdgpu-labeller-daemonset"):
        log("ROCm GPU node labeller already exists.")
    else:
        if offline_mode and bundle_dir is not None:
            run(
                [
                    "kubectl",
                    "create",
                    "-f",
                    str(bundle_dir / "manifests/k8s-ds-amdgpu-labeller.yaml"),
                ]
            )
        else:
            url = (
                "https://raw.githubusercontent.com/ROCm/k8s-device-plugin/"
                f"{ROCM_DEVICE_PLUGIN_COMMIT}/k8s-ds-amdgpu-labeller.yaml"
            )
            tmp = "/tmp/k8s-ds-amdgpu-labeller.yaml"
            run(["wget", url, "-O", tmp])
            verify_sha256(tmp, ROCM_LABELLER_SHA256)
            run(["kubectl", "create", "-f", tmp])
            os.remove(tmp)
        log("Successfully deployed ROCm GPU node labeller.")

    _patch_image_pull_policy("amdgpu-labeller-daemonset")
    _wait_daemonset_ready("amdgpu-labeller-daemonset")
