# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Helm operations: deploy / upgrade / remove of the JupyterHub release.

Mirrors bash ``deploy_aup_learning_cloud_runtime`` /
``upgrade_aup_learning_cloud_runtime`` / ``remove_aup_learning_cloud_runtime``
plus the dev-mode helpers (``dev_deploy``, ``dev_upgrade``, ``dev_quick``).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from auplc_installer.util import log, run_streaming

DEV_VALUES_PATH = "runtime/values-dev.yaml"


@dataclass
class RuntimePaths:
    """Resolved chart / values paths (offline bundle vs local repo)."""

    chart_path: Path
    values_path: Path
    overlay_path: Path

    @classmethod
    def for_offline(cls, bundle_dir: Path) -> RuntimePaths:
        return cls(
            chart_path=bundle_dir / "chart",
            values_path=bundle_dir / "config" / "values.yaml",
            overlay_path=bundle_dir / "config" / "values.local.yaml",
        )

    @classmethod
    def for_repo(cls) -> RuntimePaths:
        return cls(
            chart_path=Path("runtime/chart"),
            values_path=Path("runtime/values.yaml"),
            overlay_path=Path("runtime/values.local.yaml"),
        )


def _helm_install_args(paths: RuntimePaths, *, dev: bool = False) -> list[str]:
    args = ["-f", str(paths.values_path)]
    if dev:
        args += ["-f", DEV_VALUES_PATH]
    args += ["-f", str(paths.overlay_path)]
    return args


def deploy_runtime(paths: RuntimePaths, *, dev: bool = False) -> None:
    """Initial Helm install of JupyterHub. Waits for hub/proxy/scheduler ready."""
    msg = "Deploying AUP Learning Cloud Runtime"
    if dev:
        msg += " (dev mode)"
    log(msg + "...")
    cmd = [
        "helm",
        "install",
        "jupyterhub",
        str(paths.chart_path),
        "--namespace",
        "jupyterhub",
        "--create-namespace",
        *_helm_install_args(paths, dev=dev),
    ]
    run_streaming(cmd)

    log("Waiting for JupyterHub deployments to be ready...")
    run_streaming(
        [
            "kubectl",
            "wait",
            "--namespace",
            "jupyterhub",
            "--for=condition=available",
            "--timeout=600s",
            "deployment/hub",
            "deployment/proxy",
            "deployment/user-scheduler",
        ]
    )
    if dev:
        log("")
        log("Dev deployment ready.  Admin UI: http://localhost:30890/hub/admin/users")


def upgrade_runtime(paths: RuntimePaths, *, dev: bool = False) -> None:
    """Helm upgrade. Used after values changes."""
    cmd = [
        "helm",
        "upgrade",
        "jupyterhub",
        str(paths.chart_path),
        "--namespace",
        "jupyterhub",
        "--create-namespace",
        *_helm_install_args(paths, dev=dev),
    ]
    run_streaming(cmd)


def remove_runtime() -> None:
    """``helm uninstall jupyterhub``. Tolerant of "not found" exit code."""
    run_streaming(
        ["helm", "uninstall", "jupyterhub", "--namespace", "jupyterhub"],
        check=False,
    )


def dev_quick_rollout() -> None:
    """Restart the hub deployment to pick up a freshly-built image."""
    log("Restarting hub pod to pick up new image...")
    run_streaming(["kubectl", "rollout", "restart", "deployment/hub", "--namespace", "jupyterhub"])
    run_streaming(
        [
            "kubectl",
            "rollout",
            "status",
            "deployment/hub",
            "--namespace",
            "jupyterhub",
            "--timeout=120s",
        ]
    )
    log("")
    log("Hub restarted.  Admin UI: http://localhost:30890/hub/admin/users")
