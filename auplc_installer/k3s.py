# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""K3s install / uninstall, dummy0 setup, registry mirror configuration."""

from __future__ import annotations

import contextlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

from auplc_installer.util import (
    InstallerError,
    command_exists,
    log,
    log_success,
    run,
    run_capture,
    run_pipe_text_to,
    run_sudo_with_env,
    verify_sha256,
)

# Pinned tool versions (mirrors bash constants block)
K3S_VERSION = "v1.32.3+k3s1"
HELM_VERSION = "v3.17.2"
HELM_LINUX_AMD64_SHA256 = "90c28792a1eb5fb0b50028e39ebf826531ebfcf73f599050dbd79bab2f277241"
K9S_VERSION = "v0.32.7"
K9S_LINUX_AMD64_DEB_SHA256 = "3f12b34557d9ed9eada465b6fad57dbe9367786f68cfd4604a6771a9f08446b8"

K3S_IMAGES_DIR = "/var/lib/rancher/k3s/agent/images"
K3S_REGISTRIES_FILE = "/etc/rancher/k3s/registries.yaml"
K3S_NODE_IP = "10.255.255.1"


# ---------------------------------------------------------------------------
# Helm / K9s installation
# ---------------------------------------------------------------------------


def install_tools(*, offline_mode: bool, bundle_dir: Path | None) -> None:
    """Install helm and k9s. Mirrors bash ``install_tools``.

    Online mode pulls binaries from upstream releases; offline mode copies
    them from the bundle staged at ``bundle_dir``.
    """
    log("Checking/Installing tools (may require sudo)...")

    if offline_mode and bundle_dir is not None:
        if not command_exists("helm"):
            log("Installing Helm from bundle...")
            run(["cp", str(bundle_dir / "bin/helm"), "/usr/local/bin/helm"], sudo=True)
            run(["chmod", "+x", "/usr/local/bin/helm"], sudo=True)
        if not command_exists("k9s"):
            log("Installing K9s from bundle...")
            run(["dpkg", "-i", str(bundle_dir / "bin/k9s_linux_amd64.deb")], sudo=True)
        return

    if not command_exists("helm"):
        log("Installing Helm...")
        tar_path = "/tmp/helm-linux-amd64.tar.gz"
        run(
            [
                "wget",
                f"https://get.helm.sh/helm-{HELM_VERSION}-linux-amd64.tar.gz",
                "-O",
                tar_path,
            ]
        )
        verify_sha256(tar_path, HELM_LINUX_AMD64_SHA256)
        run(["tar", "-zxvf", tar_path, "-C", "/tmp"])
        run(["mv", "/tmp/linux-amd64/helm", "/usr/local/bin/helm"], sudo=True)
        os.remove(tar_path)
        shutil.rmtree("/tmp/linux-amd64", ignore_errors=True)

    if not command_exists("k9s"):
        log("Installing K9s...")
        deb = "/tmp/k9s_linux_amd64.deb"
        run(
            [
                "wget",
                f"https://github.com/derailed/k9s/releases/download/{K9S_VERSION}/k9s_linux_amd64.deb",
                "-O",
                deb,
            ]
        )
        verify_sha256(deb, K9S_LINUX_AMD64_DEB_SHA256)
        run(["apt", "install", deb, "-y"], sudo=True)
        os.remove(deb)


# ---------------------------------------------------------------------------
# Registry mirrors
# ---------------------------------------------------------------------------


def configure_registry_mirrors(mirror_prefix: str) -> None:
    """Write ``/etc/rancher/k3s/registries.yaml`` if a mirror is set."""
    if not mirror_prefix:
        log("No registry mirror configured. Using default registries.")
        return

    log(f"Configuring registry mirrors with prefix: {mirror_prefix}")
    cfg_dir = os.path.dirname(K3S_REGISTRIES_FILE)
    run(["mkdir", "-p", cfg_dir], sudo=True)

    config = (
        "mirrors:\n"
        "  docker.io:\n"
        "    endpoint:\n"
        f'      - "https://{mirror_prefix}/docker.io"\n'
        "  quay.io:\n"
        "    endpoint:\n"
        f'      - "https://{mirror_prefix}/quay.io"\n'
        "  registry.k8s.io:\n"
        "    endpoint:\n"
        f'      - "https://{mirror_prefix}/registry.k8s.io"\n'
        "  ghcr.io:\n"
        "    endpoint:\n"
        f'      - "https://{mirror_prefix}/ghcr.io"'
    )
    rc = run_pipe_text_to(["tee", K3S_REGISTRIES_FILE], input_text=config + "\n", sudo=True)
    if rc != 0:
        raise InstallerError(f"Failed to write {K3S_REGISTRIES_FILE}")
    log(f"Registry mirrors configured at {K3S_REGISTRIES_FILE}")


# ---------------------------------------------------------------------------
# Dummy interface (so K3s has a stable node IP across networks)
# ---------------------------------------------------------------------------


def _dummy_interface_exists() -> bool:
    res = run_capture(["ip", "link", "show", "dummy0"], check=False)
    return res.returncode == 0


def setup_dummy_interface() -> None:
    if _dummy_interface_exists():
        log("Dummy interface already exists, skipping setup")
        return

    log("Setting up dummy network interface for portable operation...")
    run(["ip", "link", "add", "dummy0", "type", "dummy"], sudo=True)
    run(["ip", "link", "set", "dummy0", "up"], sudo=True)
    run(["ip", "addr", "add", f"{K3S_NODE_IP}/32", "dev", "dummy0"], sudo=True)

    unit = (
        "[Unit]\n"
        "Description=Setup dummy network interface for K3s portable operation\n"
        "Before=k3s.service\n"
        "After=network.target\n\n"
        "[Service]\n"
        "Type=oneshot\n"
        "RemainAfterExit=yes\n"
        f"ExecStart=/bin/bash -c 'ip link show dummy0 || (ip link add dummy0 type dummy && ip link set dummy0 up && ip addr add {K3S_NODE_IP}/32 dev dummy0)'\n"
        "ExecStop=/bin/bash -c 'ip link del dummy0 2>/dev/null || true'\n\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )
    rc = run_pipe_text_to(
        ["tee", "/etc/systemd/system/dummy-interface.service"],
        input_text=unit,
        sudo=True,
    )
    if rc != 0:
        raise InstallerError("Failed to write dummy-interface.service")
    run(["systemctl", "daemon-reload"], sudo=True)
    run(["systemctl", "enable", "dummy-interface.service"], sudo=True)
    log(f"Dummy interface configured with IP: {K3S_NODE_IP}")


def remove_dummy_interface() -> None:
    unit_path = "/etc/systemd/system/dummy-interface.service"
    if os.path.isfile(unit_path):
        log("Removing dummy interface service...")
        run(["systemctl", "disable", "dummy-interface.service"], sudo=True, check=False)
        run(["rm", "-f", unit_path], sudo=True)
        run(["systemctl", "daemon-reload"], sudo=True)
    if _dummy_interface_exists():
        log("Removing dummy interface...")
        run(["ip", "link", "del", "dummy0"], sudo=True)


# ---------------------------------------------------------------------------
# K3s installation
# ---------------------------------------------------------------------------


def install_k3s_single_node(
    *,
    offline_mode: bool,
    bundle_dir: Path | None,
    use_docker: bool,
    mirror_prefix: str,
) -> None:
    """Mirrors bash ``install_k3s_single_node``.

    Sets up the dummy0 interface, copies airgap images (offline) or
    downloads K3s + writes registries (online), then runs the K3s install
    script with the right flags. Finally copies the kubeconfig into the
    invoking user's $HOME/.kube/config so kubectl works without sudo.
    """
    log("Starting K3s installation...")
    setup_dummy_interface()
    k3s_exec_args = ["--node-ip", K3S_NODE_IP, "--flannel-iface", "dummy0"]

    if offline_mode and bundle_dir is not None:
        log("Offline mode: installing K3s from bundle (containerd)...")
        run(["cp", str(bundle_dir / "bin/k3s"), "/usr/local/bin/k3s"], sudo=True)
        run(["chmod", "+x", "/usr/local/bin/k3s"], sudo=True)
        run(["mkdir", "-p", K3S_IMAGES_DIR], sudo=True)
        for img_file in sorted((bundle_dir / "k3s-images").iterdir()):
            if not img_file.is_file():
                continue
            log(f"  Copying: {img_file.name}")
            run(["cp", str(img_file), K3S_IMAGES_DIR + "/"], sudo=True)
        # Pass env vars via sudo's VAR=val arg form so they survive
        # sudo's default env_reset (otherwise K3S_KUBECONFIG_MODE=644
        # would be silently stripped and the kubeconfig would end up at
        # mode 600, unreadable by the invoking user).
        run_sudo_with_env(
            ["bash", str(bundle_dir / "bin/k3s-install.sh")],
            {
                "INSTALL_K3S_SKIP_DOWNLOAD": "true",
                "K3S_KUBECONFIG_MODE": "644",
                "INSTALL_K3S_EXEC": " ".join(k3s_exec_args),
            },
        )
    else:
        if use_docker:
            log("Using Docker as container runtime (K3S_USE_DOCKER=1).")
            if not command_exists("docker"):
                raise InstallerError("K3S_USE_DOCKER is set but Docker is not installed.")
            k3s_exec_args.append("--docker")

        configure_registry_mirrors(mirror_prefix)

        with tempfile.NamedTemporaryFile(suffix=".sh", delete=False) as f:
            installer_script = f.name
        try:
            run(["wget", "https://get.k3s.io", "-O", installer_script])
            run_sudo_with_env(
                ["sh", installer_script],
                {
                    "INSTALL_K3S_VERSION": K3S_VERSION,
                    "K3S_KUBECONFIG_MODE": "644",
                    "INSTALL_K3S_EXEC": " ".join(k3s_exec_args),
                },
            )
        finally:
            with contextlib.suppress(OSError):
                os.remove(installer_script)

    _configure_kubeconfig()


def _configure_kubeconfig() -> None:
    """Place a readable kubeconfig at ``/home/<USER>/.kube/config``.

    Goal: after K3s install, the *invoking user* can run ``kubectl`` and
    ``helm`` without sudo. To make that work we:

      1. Force ``/etc/rancher/k3s/k3s.yaml`` to mode 644. We already pass
         ``K3S_KUBECONFIG_MODE=644`` through ``sudo`` at install time,
         but older K3s installs left it at 600. ``chmod`` here is a
         no-op on a fresh install and a fix-up on stale ones.

      2. Resolve the target user as ``SUDO_USER`` (when launched via
         sudo) or the current EUID otherwise. The kubeconfig goes to
         that user's ``$HOME/.kube/config`` — never ``/root/.kube/config``
         when the original invoker was a regular user.

      3. Copy the file there and ``chown`` to the target user.

      4. Point ``$KUBECONFIG`` in this process at the new copy so helm
         (which lacks the K3s kubectl wrapper's magic) finds it.

      5. Smoke-test: run ``kubectl get nodes`` to confirm the cluster
         is reachable using this kubeconfig. Fail-fast if not, so the
         user sees the problem here rather than five stages later.
    """
    target_user, uid, gid, home = _resolve_target_user()
    log(f"Configuring kubeconfig for user: {target_user} (home: {home})")

    # 1. Make sure the K3s-emitted file is world-readable.
    if Path("/etc/rancher/k3s/k3s.yaml").is_file():
        run(["chmod", "644", "/etc/rancher/k3s/k3s.yaml"], sudo=True, check=False)

    # 2-3. Drop a copy in the target user's home, owned by them.
    target_path = _install_kubeconfig_at(home, uid, gid)

    # 4. Point THIS process's helm/kubectl at the readable copy.
    os.environ["KUBECONFIG"] = target_path
    log(f"  KUBECONFIG -> {target_path}")

    # 5. Smoke test the kubeconfig.
    _verify_kubeconfig(target_path, target_user)


def _resolve_target_user() -> tuple[str, int, int, str]:
    """Return ``(username, uid, gid, home)`` for the user that should own
    the kubeconfig and run kubectl/helm afterwards.

    When launched via sudo (``$SUDO_USER`` set, EUID == 0) we resolve
    the original invoking user — NOT root. Otherwise we use the current
    process user. This guarantees the file lands at
    ``/home/<USER>/.kube/config`` instead of ``/root/.kube/config``.
    """
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user and os.geteuid() == 0:
        try:
            res = run_capture(["getent", "passwd", sudo_user], check=False)
            line = (res.stdout or "").strip()
            if line:
                parts = line.split(":")
                if len(parts) >= 6:
                    return (sudo_user, int(parts[2]), int(parts[3]), parts[5])
        except (OSError, ValueError):
            pass
    # Fall back to the current process user.
    import pwd

    try:
        pw = pwd.getpwuid(os.getuid())
        return (pw.pw_name, pw.pw_uid, pw.pw_gid, pw.pw_dir)
    except KeyError:
        # Fallback when uid not in passwd db (rare; e.g. containerised CI).
        return ("user", os.getuid(), os.getgid(), os.path.expanduser("~"))


def _install_kubeconfig_at(home: str, uid: int, gid: int) -> str:
    """Place /etc/rancher/k3s/k3s.yaml at ``{home}/.kube/config`` owned by ``uid:gid``.

    Returns the full path of the destination file so the caller can plug
    it into ``KUBECONFIG``.
    """
    kube_dir = str(Path(home, ".kube"))
    target = str(Path(home, ".kube", "config"))
    run(["mkdir", "-p", kube_dir], sudo=True)
    run(["cp", "/etc/rancher/k3s/k3s.yaml", target], sudo=True)
    # ``chown -R`` covers both the directory (in case sudo just created
    # it as root) and the file we just dropped.
    run(["chown", "-R", f"{uid}:{gid}", kube_dir], sudo=True)
    return target


def _verify_kubeconfig(kubeconfig: str, user: str) -> None:
    """Quick fail-fast smoke test: kubectl can reach the cluster.

    We do this immediately after K3s install (and BEFORE proceeding to
    image pull / helm install) so any kubeconfig misconfiguration shows
    up here instead of buried inside a 5-minute image pull.

    Retries for up to 30 seconds because the K3s API server can take a
    few seconds to come up after the install script finishes.
    """
    import time

    log("  Verifying kubeconfig (waiting for K3s API to respond)...")
    env = {**os.environ, "KUBECONFIG": kubeconfig}
    deadline = time.monotonic() + 30
    last_error = ""
    while time.monotonic() < deadline:
        try:
            res = run_capture(
                ["kubectl", "get", "nodes", "--request-timeout=5s"],
                check=True,
                env=env,
            )
            log_success(f"  kubectl OK (as {user}):")
            for line in (res.stdout or "").rstrip().splitlines():
                log(f"    {line}")
            return
        except InstallerError as exc:
            last_error = str(exc).splitlines()[0] if str(exc) else ""
            time.sleep(2)
    raise InstallerError(
        f"kubectl smoke test failed (timed out after 30s).\n"
        f"  kubeconfig: {kubeconfig}\n"
        f"  last error: {last_error}\n"
        f"  Check that K3s service is running:  systemctl status k3s"
    )


def _username() -> str:
    return os.environ.get("SUDO_USER") or os.environ.get("USER") or ""


# ---------------------------------------------------------------------------
# K3s removal
# ---------------------------------------------------------------------------


def remove_k3s_docker_containers(
    *,
    assume_yes: bool,
    decision: bool | None = None,
) -> None:
    """Clean up leftover Kubernetes-managed Docker containers.

    ``k3s-uninstall.sh`` only cleans up its embedded containerd; when
    K3s runs with ``--docker`` it leaves Pod containers in ``docker ps``
    (filtered by the ``io.kubernetes.pod.name`` label). See
    https://github.com/k3s-io/k3s/issues/1469.

    ``decision`` lets the caller short-circuit the interactive prompt
    that would otherwise interrupt the live progress bar:

      * ``True``   → remove (no prompt)
      * ``False``  → skip silently (no prompt)
      * ``None``   → legacy behaviour: remove on ``--yes``, skip on
                     non-TTY, otherwise prompt mid-uninstall.
    """
    if not command_exists("docker"):
        return

    res = run_capture(
        ["docker", "ps", "-a", "-q", "--filter", "label=io.kubernetes.pod.name"],
        check=False,
    )
    container_ids = [line for line in (res.stdout or "").splitlines() if line.strip()]
    if not container_ids:
        return

    if decision is False:
        log("Skipping Docker container cleanup (per user choice).")
        log("  Remove later with:")
        log("    docker rm -f $(docker ps -a -q --filter 'label=io.kubernetes.pod.name')")
        return

    if decision is True:
        confirm = "y"
    elif assume_yes:
        log("Non-interactive mode (--yes): removing containers automatically.")
        confirm = "y"
    elif not sys.stdin.isatty():
        log("Non-interactive environment detected. Skipping Docker container cleanup.")
        log("  Remove later with:")
        log("    docker rm -f $(docker ps -a -q --filter 'label=io.kubernetes.pod.name')")
        return
    else:
        # Fall back to the in-flow prompt (only reached when caller did
        # not pre-decide; used for legacy CLI invocations).
        log("")
        log("The following Docker containers managed by Kubernetes were found.")
        log("These are Pod containers left behind by k3s (Docker runtime mode).")
        log("")
        run(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                "label=io.kubernetes.pod.name",
                "--format",
                "  {{.ID}}  {{.Names}}",
            ]
        )
        log("")
        try:
            confirm = input("Remove all of the above containers? [y/N] ").strip().lower()
        except EOFError:
            confirm = ""

    if confirm != "y":
        log("Skipping Docker container cleanup. You can remove them manually with:")
        log("  docker rm -f $(docker ps -a -q --filter 'label=io.kubernetes.pod.name')")
        return

    log("Stopping and removing containers...")
    run(["docker", "stop", *container_ids], check=False)
    run(["docker", "rm", *container_ids], check=False)
    log_success("Docker containers removed.")


def remove_k3s(
    *,
    assume_yes: bool,
    docker_containers_decision: bool | None = None,
) -> None:
    uninstall_script = "/usr/local/bin/k3s-uninstall.sh"
    if os.path.isfile(uninstall_script):
        log("Removing K3s (requires sudo)...")
        run([uninstall_script], sudo=True)
        log("K3s removed successfully.")
    else:
        log(f"K3s uninstall script not found at {uninstall_script}. Is K3s installed?")

    remove_k3s_docker_containers(assume_yes=assume_yes, decision=docker_containers_decision)

    home = os.path.expanduser("~")
    kube_dir = Path(home) / ".kube"
    if kube_dir.is_dir():
        log(f"Removing kubeconfig files from {kube_dir}...")
        shutil.rmtree(kube_dir, ignore_errors=True)

    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user:
        try:
            res = run_capture(["getent", "passwd", sudo_user], check=False)
            line = (res.stdout or "").strip()
            if line:
                user_home = line.split(":")[5]
                if Path(user_home, ".kube").is_dir():
                    log(f"Removing kubeconfig for user: {sudo_user}")
                    run(["rm", "-rf", f"{user_home}/.kube"], sudo=True)
        except Exception:
            pass

    log("Removing K3S local data")
    run(["rm", "-rf", "/var/lib/rancher/k3s"], sudo=True)

    remove_dummy_interface()
