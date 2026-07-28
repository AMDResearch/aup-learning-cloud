# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.

"""Canonical artifact tests for the multi-node GPU access role."""

from pathlib import Path

import pytest
from ansible.errors import AnsibleFilterError
from jinja2 import Environment

from deploy.ansible.filter_plugins.auplc_json import (
    DuplicateJsonKeyError,
    _reject_duplicate_keys,
    auplc_from_json_strict,
)

ROOT = Path(__file__).resolve().parents[2]
ANSIBLE = ROOT / "deploy" / "ansible"
GPU_ACCESS_ROLE = ANSIBLE / "roles" / "gpu_access"
PXE_CONTROLLER_ROLE = ANSIBLE / "roles" / "pxe_controller"
PXE_GPU_ACCESS_TASKS = PXE_CONTROLLER_ROLE / "tasks" / "gpu_access.yml"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_jinja_integer_test_rejects_boolean_and_float_state_values() -> None:
    template = Environment().from_string("{% if value is integer %}integer{% else %}invalid{% endif %}")

    assert template.render(value=993) == "integer"
    assert template.render(value=True) == "invalid"
    assert template.render(value=993.0) == "invalid"


def test_strict_json_filter_parses_canonical_gpu_access_state() -> None:
    assert auplc_from_json_strict('{"renderGid":993,"version":1}\n') == {
        "renderGid": 993,
        "version": 1,
    }


def test_duplicate_json_key_error_preserves_typed_key() -> None:
    with pytest.raises(DuplicateJsonKeyError) as error:
        _reject_duplicate_keys([("version", 1), ("version", 2)])

    assert error.value.key == "version"
    assert str(error.value) == "Duplicate JSON object key: 'version'"


@pytest.mark.parametrize(
    "value",
    [
        '{"renderGid":1,"renderGid":993,"version":1}',
        '{"renderGid":1,"render\\u0047id":993,"version":1}',
        '{"renderGid":1,"version":1,"version":2}',
        '{"outer":{"version":1,"version":2}}',
    ],
)
def test_strict_json_filter_rejects_semantic_duplicate_keys(value: str) -> None:
    with pytest.raises(AnsibleFilterError, match="^Invalid JSON value$"):
        auplc_from_json_strict(value)


@pytest.mark.parametrize("value", ["{", '{"renderGid":1,}'])
def test_strict_json_filter_rejects_malformed_json(value: str) -> None:
    with pytest.raises(AnsibleFilterError, match="^Invalid JSON value$"):
        auplc_from_json_strict(value)


def test_gpu_access_role_renders_the_unified_render_gid_contract() -> None:
    defaults = read(GPU_ACCESS_ROLE / "defaults" / "main.yml")
    tasks = read(GPU_ACCESS_ROLE / "tasks" / "preflight.yml") + read(GPU_ACCESS_ROLE / "tasks" / "apply.yml")
    rules = read(GPU_ACCESS_ROLE / "templates" / "70-auplc-gpu-access.rules.j2")
    state = read(GPU_ACCESS_ROLE / "templates" / "gpu-access.json.j2")

    assert "auplc_render_gid: null" in defaults
    assert "auplc_normalize_render_gid: false" in defaults
    assert 'auplc_rootfs_path: ""' in defaults
    assert "getent" in tasks
    assert "groupmod" in tasks
    assert "auplc_normalize_render_gid" in tasks
    assert "_auplc_all_groups" in tasks
    assert "reject('match', '^render:')" in tasks
    assert "_auplc_render_group.stdout.split(':')[2] | int <= 4294967294" in tasks
    assert "notify:" not in tasks
    assert "Reload live udev rules on every apply" in tasks
    assert "Trigger live udev rules on every apply" in tasks
    assert "ansible.builtin.group:" not in tasks
    assert rules == (
        "# Managed by auplc-installer: AMD GPU device access.\n"
        'KERNEL=="kfd", OWNER="root", GROUP="render", MODE="0660"\n'
        'SUBSYSTEM=="drm", KERNEL=="renderD*", DRIVERS=="amdgpu", OWNER="root", GROUP="render", MODE="0660"\n'
    )
    assert state == '{"renderGid":{{ auplc_render_gid | int }},"version":1}\n'


def test_gpu_access_role_is_wired_for_live_hosts_and_pxe_rootfs_without_legacy_udev_paths() -> None:
    rocm_playbook = read(ANSIBLE / "playbooks" / "pb-rocm.yml")
    udev_playbook = read(ANSIBLE / "playbooks" / "pb-udev.yml")
    rocm_tasks = read(ANSIBLE / "roles" / "rocm" / "tasks" / "main.yml")
    pxe_tasks = read(ANSIBLE / "roles" / "pxe_controller" / "tasks" / "main.yml")
    pxe_gpu_tasks = read(PXE_GPU_ACCESS_TASKS)
    pxe_chroot = read(ANSIBLE / "roles" / "pxe_controller" / "templates" / "chroot-setup.sh.j2")

    assert "name: gpu_access" in rocm_playbook
    assert "name: gpu_access" in udev_playbook
    assert "udev-rocm" not in udev_playbook
    assert "render:993" not in rocm_tasks
    assert "70-amdgpu.rules" not in rocm_tasks
    assert "include_tasks: gpu_access.yml" in pxe_tasks
    assert "name: gpu_access" in pxe_gpu_tasks
    assert 'auplc_rootfs_path: "{{ pxe_nfs_root }}"' in pxe_gpu_tasks
    assert "0666" not in pxe_chroot
    assert not (ANSIBLE / "roles" / "udev" / "main.yml").exists()


def test_gpu_access_live_host_playbooks_abort_all_hosts_on_preflight_failure() -> None:
    rocm_playbook = read(ANSIBLE / "playbooks" / "pb-rocm.yml")
    udev_playbook = read(ANSIBLE / "playbooks" / "pb-udev.yml")

    assert "any_errors_fatal: true" in rocm_playbook
    assert "any_errors_fatal: true" in udev_playbook


def test_gpu_access_role_migrates_only_recognized_legacy_rules_and_reconciles_live_devices() -> None:
    tasks = read(GPU_ACCESS_ROLE / "tasks" / "preflight.yml") + read(GPU_ACCESS_ROLE / "tasks" / "apply.yml")

    assert "70-kfd.rules" in tasks
    assert "70-amdgpu.rules" in tasks
    assert "contents:" in tasks
    assert 'KERNEL==\\"renderD[0-9]*\\", MODE=\\"0666\\"' in tasks
    assert "70-rocm-devices.rules" in tasks
    assert 'SUBSYSTEM=="kfd", GROUP="render", MODE="0660"' in tasks
    assert "islnk" in tasks
    assert "ansible.builtin.slurp" in tasks
    assert "Define recognized project-owned legacy GPU rules" in tasks
    assert "Unexpected legacy GPU rule content" in tasks
    assert "udevadm" in tasks
    assert "Verify /dev/kfd ownership and mode" in tasks
    assert "Verify AMD render node ownership and mode" in tasks
    assert "Settle live udev events before inode verification" in tasks
    assert (
        tasks.index("Trigger live udev rules on every apply")
        < tasks.index("Settle live udev events before inode verification")
        < tasks.index("Inspect /dev/kfd after live reconciliation")
    )
    assert tasks.index("Verify AMD render node ownership and mode") < tasks.index("Persist target GPU access state")
    assert "/sys/class/drm" in tasks
    assert "readlink" in tasks
    assert "basename" in tasks
    assert "DRIVER=amdgpu" not in tasks
    assert "notify:" not in tasks


def test_gpu_access_role_validates_legacy_rules_before_render_gid_normalization() -> None:
    preflight = read(GPU_ACCESS_ROLE / "tasks" / "preflight.yml")
    apply = read(GPU_ACCESS_ROLE / "tasks" / "apply.yml")
    tasks = preflight + apply

    assert "Define recognized project-owned legacy GPU rules" in preflight
    assert "Inspect recognized project-owned legacy GPU rules" in preflight
    assert "Reject legacy GPU rule symlinks and non-regular files" in preflight
    assert "Read recognized project-owned legacy GPU rules" in preflight
    assert "Reject unexpected legacy GPU rule content" in preflight
    assert "follow: false" in preflight
    assert "contents:" in preflight
    assert 'KERNEL==\\"renderD[0-9]*\\", MODE=\\"0666\\"' in preflight
    assert "not item.skipped | default(false)" in preflight
    assert "(item.content | b64decode) in item.item.item.contents" in preflight
    assert preflight.index("Inspect recognized project-owned legacy GPU rules") < preflight.index(
        "Reject legacy GPU rule symlinks and non-regular files"
    )
    assert preflight.index("Reject legacy GPU rule symlinks and non-regular files") < preflight.index(
        "Read recognized project-owned legacy GPU rules"
    )
    assert preflight.index("Read recognized project-owned legacy GPU rules") < preflight.index(
        "Reject unexpected legacy GPU rule content"
    )
    assert tasks.index("Reject unexpected legacy GPU rule content") < tasks.index("Normalize live render GID")
    assert "Remove recognized project-owned legacy GPU rules" in apply
    assert "Inspect recognized project-owned legacy GPU rules for apply" in apply
    assert "Reject legacy GPU rule symlinks and non-regular files before apply" in apply
    assert "Read recognized project-owned legacy GPU rules for apply" in apply
    assert "Reject unexpected legacy GPU rule content before apply" in apply
    assert "register: _auplc_apply_legacy_gpu_rule_stats" in apply
    assert "register: _auplc_apply_legacy_gpu_rule_contents" in apply
    assert "_auplc_apply_legacy_gpu_rule_contents.results" in apply
    assert "_auplc_legacy_gpu_rule_contents.results" not in apply
    assert apply.index("Reject legacy GPU rule symlinks and non-regular files before apply") < apply.index(
        "Read recognized project-owned legacy GPU rules for apply"
    )
    assert apply.index("Read recognized project-owned legacy GPU rules for apply") < apply.index(
        "Reject unexpected legacy GPU rule content before apply"
    )
    assert apply.index("Reject unexpected legacy GPU rule content before apply") < apply.index(
        "Remove recognized project-owned legacy GPU rules"
    )
    assert apply.index("Remove recognized project-owned legacy GPU rules") < apply.index("Normalize live render GID")


def test_pxe_rootfs_lifecycle_uses_an_independent_trusted_parent() -> None:
    defaults = read(ANSIBLE / "roles" / "pxe_controller" / "defaults" / "main.yml")
    tasks = read(ANSIBLE / "roles" / "pxe_controller" / "tasks" / "main.yml")
    gpu_tasks = read(PXE_GPU_ACCESS_TASKS)

    assert 'pxe_nfs_allowed_root: "/srv/nfs"' in defaults
    assert 'auplc_rootfs_allowed_root: "{{ pxe_nfs_allowed_root }}"' in gpu_tasks
    assert "Constrain canonical PXE rootfs before lifecycle changes" in tasks
    assert tasks.index("Constrain canonical PXE rootfs before lifecycle changes") < tasks.index(
        "Admit retained PXE GPU rootfs read-only before lifecycle changes"
    )


def test_pxe_rootfs_is_canonicalized_before_gpu_admission() -> None:
    tasks = read(ANSIBLE / "roles" / "pxe_controller" / "tasks" / "main.yml")

    assert "Canonicalize PXE rootfs before lifecycle changes" in tasks
    assert tasks.index("Canonicalize PXE rootfs before lifecycle changes") < tasks.index(
        "Stop NFS before rootfs rebuild"
    )
    assert "_pxe_canonical_nfs_root" in tasks
    assert tasks.index("Canonicalize PXE rootfs before lifecycle changes") < tasks.index(
        "Admit retained PXE GPU rootfs read-only before lifecycle changes"
    )


def test_gpu_access_preflight_refuses_unmanaged_canonical_destinations() -> None:
    preflight = read(GPU_ACCESS_ROLE / "tasks" / "preflight.yml")

    assert "Inspect canonical GPU access destinations" in preflight
    assert "70-auplc-gpu-access.rules" in preflight
    assert "gpu-access.json" in preflight
    assert "follow: false" in preflight
    assert "Reject unmanaged canonical GPU access rule" in preflight
    assert "Reject invalid canonical GPU access state" in preflight
    assert "auplc_from_json_strict" in preflight
    assert "| from_json" not in preflight
    assert "renderGid" in preflight
    assert "version" in preflight
    assert 'src: "{{ _auplc_target_root }}{{ item.item }}"' in preflight
    assert "Interrupted normalization retry" in preflight
    assert "_auplc_current_render_gid == auplc_render_gid" in preflight
    assert "_auplc_existing_state.version is integer" in preflight
    assert "_auplc_existing_state.renderGid is integer" in preflight
    assert "_auplc_existing_state.renderGid | int" not in preflight


def test_gpu_access_roles_use_strict_json_for_canonical_state_readers() -> None:
    preflight = read(GPU_ACCESS_ROLE / "tasks" / "preflight.yml")
    pxe_tasks = read(PXE_GPU_ACCESS_TASKS)

    assert "Parse existing canonical GPU access state" in preflight
    assert "auplc_from_json_strict" in preflight
    assert "auplc_from_json_strict" in pxe_tasks
    assert "| from_json" not in preflight
    assert "| from_json" not in pxe_tasks


def test_canonical_gpu_access_state_contract_is_exact_json() -> None:
    state = read(GPU_ACCESS_ROLE / "templates" / "gpu-access.json.j2")

    assert state == '{"renderGid":{{ auplc_render_gid | int }},"version":1}\n'


def test_gpu_access_role_splits_safe_preflight_and_rootfs_apply() -> None:
    defaults = read(GPU_ACCESS_ROLE / "defaults" / "main.yml")
    preflight = read(GPU_ACCESS_ROLE / "tasks" / "preflight.yml")
    validation = read(GPU_ACCESS_ROLE / "tasks" / "validate.yml")
    pxe_tasks = read(ANSIBLE / "roles" / "pxe_controller" / "tasks" / "main.yml")
    pxe_gpu_tasks = read(PXE_GPU_ACCESS_TASKS)

    assert "auplc_gpu_access_enabled: false" in defaults
    assert "auplc_rootfs_allowed_root" in defaults
    assert "realpath" in validation
    assert "auplc_rootfs_path != '/'" in validation
    assert "islnk" in preflight
    assert "include_tasks: gpu_access.yml" in pxe_tasks
    assert "tasks_from: validate" not in pxe_tasks
    assert "Constrain canonical PXE rootfs before lifecycle changes" in pxe_tasks
    assert pxe_tasks.index("Constrain canonical PXE rootfs before lifecycle changes") < pxe_tasks.index(
        "Stop NFS before rootfs rebuild"
    )
    assert "tasks_from: preflight" in pxe_gpu_tasks
    assert "tasks_from: apply" in pxe_gpu_tasks
    assert "auplc_normalize_render_gid:" in pxe_gpu_tasks
    assert "pxe_rootfs_force_rebuild | bool" in pxe_tasks
    assert "pxe_gpu_access_normalize_render_gid | bool" not in pxe_tasks
    assert "pxe_gpu_access_normalize_render_gid" not in read(PXE_CONTROLLER_ROLE / "defaults" / "main.yml")


def test_live_playbooks_preflight_gpu_hosts_before_mutating_roles() -> None:
    rocm_playbook = read(ANSIBLE / "playbooks" / "pb-rocm.yml")
    udev_playbook = read(ANSIBLE / "playbooks" / "pb-udev.yml")

    assert "pre_tasks:" in rocm_playbook
    assert "Assert explicit GPU access enablement" in rocm_playbook
    assert "auplc_gpu_access_enabled is defined" in rocm_playbook
    assert "auplc_gpu_access_enabled is boolean" in rocm_playbook
    assert "default(false)" not in rocm_playbook
    assert "tasks_from: preflight" in rocm_playbook
    assert rocm_playbook.index("tasks_from: preflight") < rocm_playbook.index("- role: rocm")
    assert "- role: rocm" in rocm_playbook
    assert rocm_playbook.count("auplc_gpu_access_enabled") >= 3
    assert "tasks_from: apply" in rocm_playbook
    assert "auplc_gpu_access_enabled" in rocm_playbook
    assert "pre_tasks:" in udev_playbook
    assert "Assert explicit GPU access enablement" in udev_playbook
    assert "auplc_gpu_access_enabled is defined" in udev_playbook
    assert "auplc_gpu_access_enabled is boolean" in udev_playbook
    assert "default(false)" not in udev_playbook
    assert "tasks_from: preflight" in udev_playbook
    assert "tasks_from: apply" in udev_playbook


def test_gpu_access_discovery_playbook_is_read_only_and_serializes_live_host_evidence() -> None:
    playbook = read(ANSIBLE / "playbooks" / "pb-gpu-access-discovery.yml")

    assert "hosts: k3s_cluster" in playbook
    assert "gather_facts: false" in playbook
    assert "ignore_unreachable: true" in playbook
    assert "ansible.builtin.command:" in playbook
    assert "ansible.builtin.stat:" in playbook
    assert "ansible.builtin.slurp:" in playbook
    assert "ansible.builtin.shell:" not in playbook
    assert "changed_when: false" in playbook
    assert "lspci" in playbook
    assert '"1002::0300"' in playbook
    assert '"1002::0302"' in playbook
    assert '"1002::0380"' in playbook
    assert "getent" in playbook
    assert "/sys/bus/pci/devices" in playbook
    assert "gpu_access_discovery_output_path" in playbook
    assert "delegate_to: localhost" in playbook
    assert "ansible.builtin.copy:" in playbook
    assert "to_json" in playbook
    assert "stat_success" in playbook
    assert "content_success" in playbook
    assert "legacy_rules" in playbook
    assert "/etc/udev/rules.d/70-kfd.rules" in playbook
    assert "/etc/udev/rules.d/70-amdgpu.rules" in playbook
    assert "/etc/udev/rules.d/70-rocm-devices.rules" in playbook
    file_probes = playbook[
        playbook.index("Inspect persisted GPU access state") : playbook.index(
            "Record machine-readable GPU access discovery evidence"
        )
    ]
    assert file_probes.count("ignore_errors: true") == 10
    assert "failed_when: false" not in file_probes
    assert 'mode: "0600"' in playbook
    assert "hosts: pxe_controller" not in playbook


def test_pxe_gpu_admission_resolves_fresh_rootfs_and_refuses_retained_migrations() -> None:
    assert PXE_GPU_ACCESS_TASKS.exists()

    main = read(PXE_CONTROLLER_ROLE / "tasks" / "main.yml")
    tasks = read(PXE_GPU_ACCESS_TASKS)

    assert "Record PXE rootfs state before lifecycle changes" in main
    assert "_pxe_rootfs_existed_at_start" in main
    assert "_pxe_rootfs_rebuilt_this_run" in main
    assert "include_tasks: gpu_access.yml" in main
    assert main.index("Record PXE rootfs state before lifecycle changes") < main.index("Stop NFS before rootfs rebuild")
    assert main.index("include_tasks: gpu_access.yml") < main.index("Find latest kernel in rootfs")
    assert "tasks_from: validate" not in main
    assert "tasks_from: preflight" not in main
    assert "tasks_from: apply" not in main

    assert "_pxe_rootfs_disposition" in tasks
    assert "_pxe_unanimous_live_render_gid" in tasks
    assert "_pxe_resolved_render_gid" in tasks
    assert "fresh" in tasks
    assert "retained" in tasks
    assert "groupadd" in tasks
    assert "--system" in tasks
    assert "groupmod" not in tasks
    assert "getent" in tasks
    assert 'auplc_render_gid: "{{ _pxe_resolved_render_gid }}"' in tasks
    assert "auplc_normalize_render_gid: \"{{ _pxe_rootfs_disposition == 'fresh' }}\"" in tasks
    assert "Require retained PXE legacy GPU rules absent" in tasks
    assert "Require retained PXE render GID matches unanimous live GID" in tasks
    assert "tasks_from: preflight" in tasks
    assert "tasks_from: apply" in tasks
    assert "render:993" not in tasks
    assert "lspci" not in tasks
    assert "pxe_gpu_access_normalize_render_gid" not in tasks


def test_pxe_gpu_admission_preflights_retained_rootfs_before_lifecycle_mutation() -> None:
    main = read(PXE_CONTROLLER_ROLE / "tasks" / "main.yml")

    retained_admission = "Admit retained PXE GPU rootfs read-only before lifecycle changes"
    final_admission = "Re-preflight PXE GPU rootfs before TFTP"

    assert main.count("include_tasks: gpu_access.yml") == 2
    assert main.index("Record PXE rootfs state before lifecycle changes") < main.index(retained_admission)
    assert main.index(retained_admission) < main.index("Stop NFS before rootfs rebuild")
    assert main.index("Remove chroot setup script") < main.index(final_admission)
    assert main.index(final_admission) < main.index("Find latest kernel in rootfs")

    retained_branch = main[main.index(retained_admission) : main.index("Stop NFS before rootfs rebuild")]
    final_branch = main[main.index(final_admission) : main.index("Find latest kernel in rootfs")]

    assert "pxe_gpu_access_enabled | bool" in retained_branch
    assert "not (_pxe_rootfs_rebuilt_this_run | bool)" in retained_branch
    assert "pxe_gpu_access_enabled | bool" in final_branch
    assert "pxe_gpu_admission_phase: final" in final_branch


def test_pxe_rootfs_disposition_uses_initial_root_path_and_rejects_partial_retained_trees() -> None:
    main = read(PXE_CONTROLLER_ROLE / "tasks" / "main.yml")

    assert "Require existing PXE rootfs is a directory" in main
    assert "Require incomplete PXE rootfs force rebuild" in main
    assert '_pxe_rootfs_existed_at_start: "{{ _pxe_rootfs_lstat.stat.exists | bool }}"' in main
    assert "not (_pxe_rootfs_lstat.stat.exists | bool)" in main
    assert main.index("Require incomplete PXE rootfs force rebuild") < main.index("Stop NFS before rootfs rebuild")
    assert main.index("Require incomplete PXE rootfs force rebuild") < main.index("- name: Build NFS rootfs")


def test_pxe_retained_admission_is_read_only_until_post_chroot_repreflight_and_apply() -> None:
    main = read(PXE_CONTROLLER_ROLE / "tasks" / "main.yml")
    tasks = read(PXE_GPU_ACCESS_TASKS)

    assert "Admit retained PXE GPU rootfs read-only before lifecycle changes" in main
    assert "Re-preflight PXE GPU rootfs before TFTP" in main
    assert main.index("Admit retained PXE GPU rootfs read-only before lifecycle changes") < main.index(
        "Stop NFS before rootfs rebuild"
    )
    assert main.index("Remove chroot setup script") < main.index("Re-preflight PXE GPU rootfs before TFTP")
    assert "pxe_gpu_admission_phase: retained-read-only" in main
    assert "pxe_gpu_admission_phase: final" in main
    assert "Require retained PXE canonical GPU rule" in tasks
    assert "Require retained PXE canonical GPU state" in tasks
    assert "Apply GPU access after final PXE re-preflight" in tasks
    retained_read_only = tasks[: tasks.index("Preflight GPU access after final PXE re-preflight")]
    assert "tasks_from: apply" not in retained_read_only
    assert "pxe_gpu_admission_phase == 'final'" in tasks


def test_pxe_retained_admission_checks_canonical_parent_chain_before_lifecycle_or_chroot_mutation() -> None:
    main = read(PXE_CONTROLLER_ROLE / "tasks" / "main.yml")
    tasks = read(PXE_GPU_ACCESS_TASKS)

    assert "Inspect retained PXE canonical GPU access parents" in tasks
    assert "Require retained PXE canonical GPU access parents" in tasks
    for parent in ("/etc", "/etc/udev", "/etc/udev/rules.d", "/var", "/var/lib", "/var/lib/auplc"):
        assert parent in tasks
    assert "item.stat.exists" in tasks
    assert "item.stat.isdir" in tasks
    assert "not item.stat.islnk" in tasks
    assert main.index("Admit retained PXE GPU rootfs read-only before lifecycle changes") < main.index(
        "Execute chroot setup"
    )
