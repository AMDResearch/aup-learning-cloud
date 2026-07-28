# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.

"""Contract tests for the Ansible GPU device-mode role."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ANSIBLE = ROOT / "deploy" / "ansible"
GPU_ACCESS_ROLE = ANSIBLE / "roles" / "gpu_access"
PXE_CONTROLLER_ROLE = ANSIBLE / "roles" / "pxe_controller"
PXE_GPU_ACCESS_TASKS = PXE_CONTROLLER_ROLE / "tasks" / "gpu_access.yml"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_gpu_access_role_uses_shc_proven_device_mode_contract() -> None:
    defaults = read(GPU_ACCESS_ROLE / "defaults" / "main.yml")
    preflight = read(GPU_ACCESS_ROLE / "tasks" / "preflight.yml")
    apply = read(GPU_ACCESS_ROLE / "tasks" / "apply.yml")
    rules = read(GPU_ACCESS_ROLE / "templates" / "70-auplc-gpu-access.rules.j2")

    assert "auplc_gpu_access_enabled: false" in defaults
    assert 'auplc_rootfs_path: ""' in defaults
    assert "auplc_render_gid" not in defaults
    assert "normalize" not in defaults
    assert "gpu-access.json" not in preflight
    assert "groupmod" not in apply
    assert "GID collision" not in preflight
    assert rules == (
        "# Managed by auplc-installer: AMD GPU device access.\n"
        'KERNEL=="kfd", OWNER="root", GROUP="render", MODE="0666"\n'
        'SUBSYSTEM=="drm", KERNEL=="renderD*", DRIVERS=="amdgpu", OWNER="root", GROUP="render", MODE="0666"\n'
        'SUBSYSTEM=="drm", KERNEL=="card*", DRIVERS=="amdgpu", OWNER="root", GROUP="video", MODE="0666"\n'
    )


def test_gpu_access_role_preserves_safe_preflight_and_exact_legacy_admission() -> None:
    validation = read(GPU_ACCESS_ROLE / "tasks" / "validate.yml")
    preflight = read(GPU_ACCESS_ROLE / "tasks" / "preflight.yml")
    apply = read(GPU_ACCESS_ROLE / "tasks" / "apply.yml")

    assert "realpath" in validation
    assert "auplc_rootfs_path != '/'" in validation
    assert "_auplc_canonical_allowed_root" in validation
    assert "Inspect GPU access rootfs target" in preflight
    assert "follow: false" in preflight
    assert "Reject unsafe canonical GPU access destination parents" in preflight
    assert "Reject unsafe canonical GPU access destination" in preflight
    assert "Define recognized project-owned legacy GPU rules" in preflight
    assert "Reject unexpected legacy GPU rule content" in preflight
    assert "70-kfd.rules" in preflight
    assert "70-amdgpu.rules" in preflight
    assert "70-rocm-devices.rules" in preflight
    assert "Remove recognized project-owned legacy GPU rules" in apply
    assert apply.index("Reject unexpected legacy GPU rule content before apply") < apply.index(
        "Remove recognized project-owned legacy GPU rules"
    )


def test_gpu_access_role_reconciles_and_verifies_live_devices_only() -> None:
    apply = read(GPU_ACCESS_ROLE / "tasks" / "apply.yml")

    assert "Reload live udev rules on every apply" in apply
    assert "Trigger live udev rules on every apply" in apply
    assert "Settle live udev events before inode verification" in apply
    assert "Inspect /dev/kfd after live reconciliation" in apply
    assert "Verify /dev/kfd ownership and mode" in apply
    assert "Find live DRM render nodes" in apply
    assert "Verify AMD render node ownership and mode" in apply
    assert "Find live DRM card nodes" in apply
    assert "Verify AMD card node ownership and mode" in apply
    assert "/sys/class/drm" in apply
    assert "readlink" in apply
    assert "basename" in apply
    assert "_auplc_kfd.stat.mode == '0666'" in apply
    assert "item.stat.mode == '0666'" in apply
    assert "item.stat.mode == '0666'" in apply
    assert "item.stat.gr_name == 'render'" in apply
    assert "item.stat.gr_name == 'video'" in apply
    assert (
        apply.index("Trigger live udev rules on every apply")
        < apply.index("Settle live udev events before inode verification")
        < apply.index("Inspect /dev/kfd after live reconciliation")
    )
    assert "when: _auplc_target_root | length == 0" in apply
    assert "gpu-access.json" not in apply


def test_gpu_access_role_rejects_noncanonical_managed_rule_content() -> None:
    preflight = read(GPU_ACCESS_ROLE / "tasks" / "preflight.yml")
    apply = read(GPU_ACCESS_ROLE / "tasks" / "apply.yml")
    pxe_tasks = read(PXE_GPU_ACCESS_TASKS)

    assert "_auplc_previous_canonical_rule" not in preflight
    assert "(_auplc_existing_rule.content | b64decode) == _auplc_canonical_rule" in preflight
    assert "Reject unmanaged canonical GPU access rule" in preflight
    assert "_auplc_apply_previous_canonical_rule" not in apply
    assert "Recheck canonical GPU access rule before apply" in apply
    assert "(_auplc_apply_existing_rule.content | b64decode) == _auplc_apply_canonical_rule" in apply
    assert "Unmanaged canonical GPU access rule." in apply
    assert "_pxe_retained_previous_canonical_rule" not in pxe_tasks
    assert "(_pxe_retained_canonical_gpu_rule.content | b64decode) == _pxe_retained_canonical_rule" in pxe_tasks
    assert "non-canonical GPU access rule" in pxe_tasks


def test_pxe_gpu_access_installs_rules_without_gid_or_state_contract() -> None:
    main = read(PXE_CONTROLLER_ROLE / "tasks" / "main.yml")
    tasks = read(PXE_GPU_ACCESS_TASKS)

    assert "Admit retained PXE GPU rootfs read-only before lifecycle changes" in main
    assert "Re-preflight PXE GPU rootfs before TFTP" in main
    assert main.index("Admit retained PXE GPU rootfs read-only before lifecycle changes") < main.index(
        "Stop NFS before rootfs rebuild"
    )
    assert "Inspect retained PXE canonical GPU access parents" in tasks
    assert "Require retained PXE canonical GPU access parents" in tasks
    assert "Require retained PXE canonical GPU rule" in tasks
    assert "tasks_from: preflight" in tasks
    assert "tasks_from: apply" in tasks
    assert 'auplc_rootfs_path: "{{ pxe_nfs_root }}"' in tasks
    assert 'auplc_rootfs_allowed_root: "{{ pxe_nfs_allowed_root }}"' in tasks
    assert "auplc_render_gid" not in tasks
    assert "render_gid" not in tasks
    assert "groupadd" not in tasks
    assert "groupmod" not in tasks
    assert "collision" not in tasks.lower()
    assert "gpu-access.json" not in tasks
    assert "/dev/kfd" not in tasks
    assert "/dev/dri" not in tasks


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


def test_pxe_controller_playbook_has_no_obsolete_finalizer_post_tasks() -> None:
    pxe_playbook = read(ANSIBLE / "playbooks" / "pb-pxe-controller.yml")

    assert "post_tasks:" not in pxe_playbook
    assert "pxe_finalizer_" not in pxe_playbook
    assert "--finalize-pxe" not in pxe_playbook


def test_deploy_ansible_has_no_render_gid_normalization_or_gpu_state_contract() -> None:
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
