# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.

"""Contract tests for AMD's packaged GPU udev rules in Ansible."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ANSIBLE = ROOT / "deploy" / "ansible"
GPU_ACCESS_ROLE = ANSIBLE / "roles" / "gpu_access"
PXE_CONTROLLER_ROLE = ANSIBLE / "roles" / "pxe_controller"
PXE_GPU_ACCESS_TASKS = PXE_CONTROLLER_ROLE / "tasks" / "gpu_access.yml"

PACKAGE = "amdgpu-insecure-instinct-udev-rules"
VERSION = "30.30.4.0-2341068.24.04"
FILENAME = f"{PACKAGE}_{VERSION}_all.deb"
URL = f"https://repo.radeon.com/amdgpu/30.30.4/ubuntu/pool/main/a/{PACKAGE}/{FILENAME}"
SHA256 = "4be865985c7a13114c45925e77bc0b411b9fd47d5040ed35df44b9c411766162"
RULE_PATH = "/etc/udev/rules.d/70-amdgpu.rules"
RULE_CONTENT = (
    'KERNEL=="kfd", GROUP="render", MODE="0666"\nSUBSYSTEM=="drm", KERNEL=="renderD*", GROUP="render", MODE="0666"\n'
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_gpu_access_role_pins_the_official_amd_package_contract() -> None:
    defaults = read(GPU_ACCESS_ROLE / "defaults" / "main.yml")
    preflight = read(GPU_ACCESS_ROLE / "tasks" / "preflight.yml")
    apply = read(GPU_ACCESS_ROLE / "tasks" / "apply.yml")
    verify = read(GPU_ACCESS_ROLE / "tasks" / "verify.yml")

    assert PACKAGE in defaults
    assert VERSION in defaults
    assert FILENAME in defaults
    assert URL in defaults
    assert f"sha256:{SHA256}" in defaults
    assert RULE_PATH in defaults
    assert "  " + RULE_CONTENT.replace("\n", "\n  ").rstrip() in defaults
    assert "dpkg-query" in preflight
    assert r"--showformat=${Status}\t${Version}" in preflight
    assert "ansible.builtin.get_url" in apply
    assert "ansible.builtin.apt" in apply
    assert 'checksum: "{{ auplc_gpu_udev_package_checksum }}"' in apply
    assert 'deb: "{{ auplc_gpu_udev_package_cache_path }}"' in apply
    assert "dpkg-query" in verify
    assert r"--showformat=${Status}\t${Version}" in verify
    assert "--search" in verify
    assert "package-owned" in verify
    assert "modified package conffile" in verify


def test_inventory_placeholders_define_boolean_gpu_access() -> None:
    inventory_text = read(ANSIBLE / "inventory.yml")
    inventory = yaml.safe_load(inventory_text)
    raw_inventory = yaml.load(inventory_text, Loader=yaml.BaseLoader)
    hosts = inventory["k3s_cluster"]["children"]
    raw_hosts = raw_inventory["k3s_cluster"]["children"]

    for group_name in ("server", "agent"):
        for host_name, host in hosts[group_name]["hosts"].items():
            value = host["auplc_gpu_access_enabled"]
            assert type(value) is bool
            assert raw_hosts[group_name]["hosts"][host_name]["auplc_gpu_access_enabled"] in {"true", "false"}


def test_gpu_access_role_preserves_rootfs_and_exact_legacy_safety() -> None:
    validation = read(GPU_ACCESS_ROLE / "tasks" / "validate.yml")
    preflight = read(GPU_ACCESS_ROLE / "tasks" / "preflight.yml")
    apply = read(GPU_ACCESS_ROLE / "tasks" / "apply.yml")

    assert "realpath" in validation
    assert "auplc_rootfs_path != '/'" in validation
    assert "_auplc_canonical_allowed_root" in validation
    assert "Inspect GPU access rootfs target" in preflight
    assert "follow: false" in preflight
    assert "Reject unsafe AMD udev rule destination parents" in preflight
    assert "Reject unsafe AMD udev rule destination" in preflight
    assert "Define recognized project-owned legacy GPU rules" in preflight
    assert "hash('sha256')" in preflight
    assert "70-kfd.rules" in preflight
    assert "70-rocm-devices.rules" in preflight
    assert "70-auplc-gpu-access.rules" not in preflight
    assert "Reject unexpected legacy GPU rule content" in preflight
    assert "Recheck recognized project-owned legacy GPU rules before apply" in apply
    assert "Remove recognized project-owned legacy GPU rules" in apply
    assert apply.index("Download checksummed AMD udev package") < apply.index(
        "Remove recognized project-owned legacy GPU rules"
    )
    assert apply.index("Verify installed AMD udev package") < apply.index(
        "Remove recognized project-owned legacy GPU rules"
    )
    assert "Reload live udev rules after legacy cleanup" in apply
    assert "Trigger live udev rules after legacy cleanup" in apply


def test_gpu_access_role_skips_package_cache_and_download_when_exact_version_is_installed() -> None:
    preflight = read(GPU_ACCESS_ROLE / "tasks" / "preflight.yml")
    apply = read(GPU_ACCESS_ROLE / "tasks" / "apply.yml")

    assert "_auplc_gpu_udev_install_needed" in preflight
    assert "Install AMD udev package when required" in apply
    install_block = apply.split("Install AMD udev package when required", maxsplit=1)[1]
    assert "Create deterministic AMD udev package cache" in install_block
    assert "Download checksummed AMD udev package" in install_block
    assert "when: _auplc_gpu_udev_install_needed | bool" in install_block
    assert "Verify installed AMD udev package without installation" in apply
    assert "install ok installed" in preflight


def test_gpu_access_role_requires_installed_status_and_exact_version() -> None:
    verify = read(GPU_ACCESS_ROLE / "tasks" / "verify.yml")

    assert "install ok installed" in verify
    assert "Require installed AMD udev package status and exact version" in verify


def test_preflight_allows_package_owned_wrong_version_rule_for_convergence() -> None:
    preflight = read(GPU_ACCESS_ROLE / "tasks" / "preflight.yml")

    assert "Query AMD udev rule package ownership on live host before admission" in preflight
    assert "Query AMD udev rule package ownership in PXE rootfs before admission" in preflight
    assert preflight.index("Query installed AMD udev package") < preflight.index("Read existing AMD udev rule")
    assert preflight.index("Query AMD udev rule package ownership") < preflight.index("Read existing AMD udev rule")
    assert "_auplc_gpu_udev_install_needed | bool" in preflight
    assert "_auplc_rule_owned_by_amd_package | bool" in preflight


def test_preflight_allows_package_owned_partial_state_rule_for_convergence() -> None:
    preflight = read(GPU_ACCESS_ROLE / "tasks" / "preflight.yml")

    assert "Record whether AMD udev package installation is needed" in preflight
    assert "Allow package-owned AMD udev rule convergence" in preflight
    assert "install ok installed" in preflight


def test_preflight_rejects_unknown_unowned_rule_content() -> None:
    preflight = read(GPU_ACCESS_ROLE / "tasks" / "preflight.yml")

    assert "Reject modified AMD udev rule before package installation" in preflight
    assert "_auplc_rule_owned_by_amd_package | bool" in preflight
    assert "Existing AMD udev rule is neither the package rule nor a recognized legacy rule." in preflight


def test_preflight_legacy_admission_matches_package_owned_convergence_admission() -> None:
    preflight = read(GPU_ACCESS_ROLE / "tasks" / "preflight.yml")
    primary_admission = preflight.split("Allow package-owned AMD udev rule convergence", maxsplit=1)[1].split(
        "Reject modified AMD udev rule before package installation", maxsplit=1
    )[0]
    legacy_admission = preflight.split("Reject unexpected legacy GPU rule content", maxsplit=1)[1].split(
        "fail_msg:", maxsplit=1
    )[0]

    assert "_auplc_gpu_udev_install_needed | bool" in primary_admission
    assert "_auplc_rule_owned_by_amd_package | bool" in primary_admission
    assert "_auplc_gpu_udev_install_needed | bool" in legacy_admission
    assert "_auplc_rule_owned_by_amd_package | bool" in legacy_admission
    assert "auplc_gpu_udev_rule_path" in legacy_admission
    assert "auplc_gpu_udev_rule_content" in legacy_admission


def test_gpu_access_role_installs_the_package_without_custom_rule_or_device_probes() -> None:
    apply = read(GPU_ACCESS_ROLE / "tasks" / "apply.yml")

    assert not (GPU_ACCESS_ROLE / "templates" / "70-auplc-gpu-access.rules.j2").exists()
    assert "ansible.builtin.template" not in apply
    assert "70-auplc-gpu-access.rules.j2" not in apply
    assert "udevadm settle" not in apply
    assert "/dev/kfd" not in apply
    assert "/dev/dri" not in apply
    assert "/sys/class/drm" not in apply
    assert "card" not in apply


def test_gpu_access_role_verifies_exact_installed_package_version_and_rule() -> None:
    verify = read(GPU_ACCESS_ROLE / "tasks" / "verify.yml")

    assert "auplc_gpu_udev_package_version" in verify
    assert "auplc_gpu_udev_rule_path" in verify
    assert "auplc_gpu_udev_rule_content" in verify
    assert "Require installed AMD udev package status and exact version" in verify
    assert "Require package-owned AMD udev rule" in verify
    assert "Require exact AMD udev rule content" in verify
    assert "follow: false" in verify


def test_pxe_gpu_access_uses_safe_chroot_install_and_strict_retained_admission() -> None:
    main = read(PXE_CONTROLLER_ROLE / "tasks" / "main.yml")
    tasks = read(PXE_GPU_ACCESS_TASKS)
    apply = read(GPU_ACCESS_ROLE / "tasks" / "apply.yml")
    verify = read(GPU_ACCESS_ROLE / "tasks" / "verify.yml")

    assert "Admit retained PXE GPU rootfs read-only before lifecycle changes" in main
    assert "Re-preflight PXE GPU rootfs before TFTP" in main
    assert main.index("Admit retained PXE GPU rootfs read-only before lifecycle changes") < main.index(
        "Stop NFS before rootfs rebuild"
    )
    assert "tasks_from: verify" in tasks
    assert "tasks_from: preflight" in tasks
    assert "tasks_from: apply" in tasks
    assert 'auplc_rootfs_path: "{{ pxe_nfs_root }}"' in tasks
    assert 'auplc_rootfs_allowed_root: "{{ pxe_nfs_allowed_root }}"' in tasks
    assert "auplc_reject_legacy_gpu_rules: true" in tasks
    assert "Reject retained PXE shipped legacy GPU rules" in verify
    assert "chroot" in apply
    assert "apt-get" in apply
    assert "Copy AMD udev package into PXE rootfs" in apply
    assert "Mount virtual filesystems for AMD udev package installation" not in apply
    assert "mount --bind" not in apply
    assert "Unmount virtual filesystems after AMD udev package installation" not in apply
    assert apply.index("Verify installed AMD udev package") < apply.index(
        "Remove temporary AMD udev package from PXE rootfs"
    )
    assert main.index("Re-preflight PXE GPU rootfs before TFTP") < main.index("Find latest kernel in rootfs")
    assert RULE_CONTENT not in tasks
    assert "/dev/kfd" not in tasks
    assert "/dev/dri" not in tasks


def test_pxe_rootfs_unmounts_fail_on_real_errors_but_skip_absent_mounts() -> None:
    main = read(PXE_CONTROLLER_ROLE / "tasks" / "main.yml")

    rootfs_removal = main.split("Remove existing rootfs (force rebuild)", maxsplit=1)[1].split(
        "Check if NFS rootfs already exists", maxsplit=1
    )[0]
    chroot_unmount = main.split("Unmount virtual filesystems from chroot", maxsplit=1)[1].split(
        "Remove chroot setup script", maxsplit=1
    )[0]
    for task in (rootfs_removal, chroot_unmount):
        assert "set -e" in task
        assert "if mountpoint -q" in task
        assert "&& umount" not in task
        assert "|| true" not in task


def test_gpu_access_playbooks_keep_two_phase_live_and_rootfs_safety() -> None:
    rocm_playbook = read(ANSIBLE / "playbooks" / "pb-rocm.yml")
    udev_playbook = read(ANSIBLE / "playbooks" / "pb-udev.yml")
    pxe_playbook = read(ANSIBLE / "playbooks" / "pb-pxe-controller.yml")

    assert "any_errors_fatal: true" in rocm_playbook
    assert "any_errors_fatal: true" in udev_playbook
    assert rocm_playbook.index("tasks_from: preflight") < rocm_playbook.index("- role: rocm")
    assert "tasks_from: apply" in rocm_playbook
    assert "tasks_from: preflight" in udev_playbook
    assert "tasks_from: apply" in udev_playbook
    assert "render_gid" not in pxe_playbook


def test_deploy_ansible_has_no_obsolete_gpu_access_policy_or_state_contract() -> None:
    forbidden = (
        "auplc_render_gid",
        "auplc_normalize_render_gid",
        "gpu-access.json",
        "auplc_from_json_strict",
        "groupmod",
        "render GID collision",
    )
    ansible_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in ANSIBLE.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )

    for term in forbidden:
        assert term not in ansible_text
