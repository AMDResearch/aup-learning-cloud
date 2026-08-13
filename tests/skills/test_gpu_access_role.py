# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
"""Contract tests for AMD's packaged GPU udev rules in Ansible."""

import hashlib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
ANSIBLE = ROOT / "deploy" / "ansible"
GPU_ACCESS_ROLE = ANSIBLE / "roles" / "gpu_access"
PXE_CONTROLLER_ROLE = ANSIBLE / "roles" / "pxe_controller"
PXE_GPU_ACCESS_TASKS = PXE_CONTROLLER_ROLE / "tasks" / "gpu_access.yml"

PACKAGE = "amdgpu-insecure-instinct-udev-rules"
VERSION = "30.30.4.0-2341068.24.04"
URL = f"https://repo.radeon.com/amdgpu/30.30.4/ubuntu/pool/main/a/{PACKAGE}/{PACKAGE}_{VERSION}_all.deb"
SHA256 = "4be865985c7a13114c45925e77bc0b411b9fd47d5040ed35df44b9c411766162"
RULE_PATH = "/etc/udev/rules.d/70-amdgpu.rules"
RULE_CONTENT = (
    'KERNEL=="kfd", GROUP="render", MODE="0666"\nSUBSYSTEM=="drm", KERNEL=="renderD*", GROUP="render", MODE="0666"\n'
)
LEGACY_RENDER_GROUP_RULE_CONTENT = (
    'KERNEL=="kfd", GROUP="render", MODE="0660"\nSUBSYSTEM=="drm", KERNEL=="renderD*", GROUP="render", MODE="0660"\n'
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_gpu_access_role_enforces_pinned_package_contract() -> None:
    defaults = yaml.safe_load(read(GPU_ACCESS_ROLE / "defaults" / "main.yml"))
    apply = read(GPU_ACCESS_ROLE / "tasks" / "apply.yml")
    verify = read(GPU_ACCESS_ROLE / "tasks" / "verify.yml")

    assert [
        defaults[key]
        for key in (
            "auplc_gpu_udev_package_name",
            "auplc_gpu_udev_package_version",
            "auplc_gpu_udev_package_url",
            "auplc_gpu_udev_package_checksum",
            "auplc_gpu_udev_rule_path",
            "auplc_gpu_udev_rule_content",
        )
    ] == [PACKAGE, VERSION, URL, f"sha256:{SHA256}", RULE_PATH, RULE_CONTENT]
    assert all(token in apply for token in ("ansible.builtin.get_url", "ansible.builtin.apt", "checksum:", "deb:"))
    assert all(
        token in verify
        for token in (
            "dpkg-query",
            r"--showformat=${Status}\t${Version}",
            "--search",
            "install ok installed",
            "_auplc_verify_live_rule_owner.stdout == auplc_gpu_udev_package_name + ': ' + auplc_gpu_udev_rule_path",
            "(_auplc_verify_rule_content.content | b64decode) == auplc_gpu_udev_rule_content",
        )
    )


def test_gpu_access_defaults_and_inventory_leave_auto_unquoted() -> None:
    defaults = read(GPU_ACCESS_ROLE / "defaults" / "main.yml")
    inventory = read(ANSIBLE / "inventory.yml")

    assert "auplc_gpu_access_enabled: auto" in defaults
    assert inventory.count("auplc_gpu_access_enabled: auto") == 2
    assert 'auplc_gpu_access_enabled: "auto"' not in inventory
    assert "auplc_gpu_access_enabled: 'auto'" not in inventory


def test_gpu_access_rootfs_and_legacy_cleanup_remain_contained_and_verified() -> None:
    validation = read(GPU_ACCESS_ROLE / "tasks" / "validate.yml")
    preflight = read(GPU_ACCESS_ROLE / "tasks" / "preflight.yml")
    apply = read(GPU_ACCESS_ROLE / "tasks" / "apply.yml")

    assert all(
        token in validation
        for token in (
            "realpath",
            "auplc_rootfs_path != '/'",
            "_auplc_canonical_rootfs.stdout.startswith(_auplc_canonical_allowed_root.stdout + '/')",
        )
    )
    assert all(
        token in preflight
        for token in (
            "follow: false",
            "_auplc_legacy_gpu_rules",
            "hash('sha256')",
            "70-kfd.rules",
            "70-rocm-devices.rules",
        )
    )
    assert apply.index("ansible.builtin.import_tasks: verify.yml") < apply.rindex("state: absent")
    assert apply.index("item.content | b64decode") < apply.rindex("state: absent")


def test_pxe_gpu_access_chroots_without_bind_mounts_and_rejects_unsafe_retained_rules() -> None:
    main = read(PXE_CONTROLLER_ROLE / "tasks" / "main.yml")
    tasks = read(PXE_GPU_ACCESS_TASKS)
    apply = read(GPU_ACCESS_ROLE / "tasks" / "apply.yml")
    verify = read(GPU_ACCESS_ROLE / "tasks" / "verify.yml")

    assert main.index("pxe_gpu_admission_phase: retained-read-only") < main.index("rm -rf {{ pxe_nfs_root }}")
    assert main.index("pxe_gpu_admission_phase: final") < main.index("ls {{ pxe_nfs_root }}/boot/vmlinuz-")
    assert all(
        token in tasks
        for token in (
            "tasks_from: verify",
            "tasks_from: preflight",
            "tasks_from: apply",
            'auplc_rootfs_path: "{{ pxe_nfs_root }}"',
            'auplc_rootfs_allowed_root: "{{ pxe_nfs_allowed_root }}"',
            "auplc_reject_legacy_gpu_rules: true",
        )
    )
    assert "not item.stat.exists" in verify
    assert "chroot" in apply
    assert "apt-get" in apply
    assert "mount --bind" not in apply


def test_pxe_unmounts_only_when_present_and_propagates_failures() -> None:
    main = read(PXE_CONTROLLER_ROLE / "tasks" / "main.yml")

    assert main.count("set -e") == 2
    for mount in ("dev", "sys", "proc"):
        assert main.count("if mountpoint -q {{ pxe_nfs_root }}/" + mount + "; then") == 2
        assert main.count("umount {{ pxe_nfs_root }}/" + mount) == 2
    assert "&& umount" not in main
    assert "|| true" not in main


def test_gpu_access_resolves_before_preflight_rocm_and_apply_fail_fatally() -> None:
    role_main = read(GPU_ACCESS_ROLE / "tasks" / "main.yml")
    rocm = read(ANSIBLE / "playbooks" / "pb-rocm.yml")
    udev = read(ANSIBLE / "playbooks" / "pb-udev.yml")

    assert role_main.index("import_tasks: resolve.yml") < role_main.index("import_tasks: preflight.yml")
    assert role_main.index("import_tasks: preflight.yml") < role_main.index("import_tasks: apply.yml")
    for playbook in (rocm, udev):
        assert "any_errors_fatal: true" in playbook
        assert playbook.index("tasks_from: resolve") < playbook.index("tasks_from: preflight")
        assert playbook.index("tasks_from: preflight") < playbook.index("tasks_from: apply")
        assert "when: _auplc_gpu_access_enabled_resolved" in playbook
    assert rocm.index("tasks_from: preflight") < rocm.index("- role: rocm") < rocm.index("tasks_from: apply")


def test_gpu_access_auto_detection_requires_successful_boolean_resolution_before_preflight() -> None:
    role_main = read(GPU_ACCESS_ROLE / "tasks" / "main.yml")
    resolve = read(GPU_ACCESS_ROLE / "tasks" / "resolve.yml")

    assert "auplc_gpu_access_enabled == 'auto'" in resolve
    assert resolve.index("ansible.builtin.import_tasks: detect.yml") < resolve.index("_auplc_gpu_access_sysfs.rc == 0")
    assert resolve.index("_auplc_gpu_access_sysfs.rc == 0") < resolve.index("_auplc_gpu_access_enabled_resolved: >-")
    assert resolve.index("_auplc_gpu_access_enabled_resolved: >-") < resolve.index(
        "_auplc_gpu_access_enabled_resolved is boolean"
    )
    assert role_main.index("ansible.builtin.import_tasks: resolve.yml") < role_main.index(
        "ansible.builtin.import_tasks: preflight.yml"
    )


def test_gpu_access_rejects_unknown_unowned_udev_content_before_deletion() -> None:
    role_main = read(GPU_ACCESS_ROLE / "tasks" / "main.yml")
    preflight = read(GPU_ACCESS_ROLE / "tasks" / "preflight.yml")
    apply = read(GPU_ACCESS_ROLE / "tasks" / "apply.yml")
    admission = preflight.split("_auplc_rule_content_admitted: >-", maxsplit=1)[1]
    cleanup = apply.split("register: _auplc_apply_legacy_gpu_rule_contents", maxsplit=1)[1]

    assert "(_auplc_rule_owned_by_amd_package | bool)" in admission
    assert "that: _auplc_rule_content_admitted | bool" in admission
    assert role_main.index("ansible.builtin.import_tasks: preflight.yml") < role_main.index(
        "ansible.builtin.import_tasks: apply.yml"
    )
    assert cleanup.index("item.content | b64decode") < cleanup.index("state: absent")
    assert "in item.item.item.sha256" in cleanup


def test_gpu_access_rule_admission_expression_has_balanced_parentheses() -> None:
    tasks = yaml.safe_load(read(GPU_ACCESS_ROLE / "tasks" / "preflight.yml"))
    admission_task = next(task for task in tasks if task["name"] == "Allow package-owned AMD udev rule convergence")
    expression = admission_task["ansible.builtin.set_fact"]["_auplc_rule_content_admitted"]

    assert expression.count("(") == expression.count(")")


def test_gpu_access_admits_legacy_render_group_rule() -> None:
    tasks = yaml.safe_load(read(GPU_ACCESS_ROLE / "tasks" / "preflight.yml"))
    legacy_task = next(task for task in tasks if task["name"] == "Define recognized project-owned legacy GPU rules")
    rules = legacy_task["ansible.builtin.set_fact"]["_auplc_legacy_gpu_rules"]
    amdgpu_rule = next(rule for rule in rules if rule["path"].endswith("/etc/udev/rules.d/70-amdgpu.rules"))
    legacy_rule_sha256 = hashlib.sha256(LEGACY_RENDER_GROUP_RULE_CONTENT.encode()).hexdigest()

    assert legacy_rule_sha256 in amdgpu_rule["sha256"]
