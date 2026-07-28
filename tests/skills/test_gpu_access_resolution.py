# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

"""Behavior tests for fleet GPU-access discovery resolution."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RESOLUTION = ROOT / "skills" / "deploy-aup-learning-cloud" / "scripts" / "gpu_access_resolution.py"
MANIFEST = ROOT / "skills" / "deploy-aup-learning-cloud" / "scripts" / "gpu_resolution_manifest.py"
GPU_BDF = "0000:03:00.0"


def load_resolution_module():
    sys.path.insert(0, str(RESOLUTION.parent))
    spec = importlib.util.spec_from_file_location("gpu_access_resolution", RESOLUTION)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


def load_manifest_module():
    spec = importlib.util.spec_from_file_location("gpu_resolution_manifest", MANIFEST)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def host_evidence(
    host: str,
    *,
    lspci_bdfs: list[str] | None = None,
    sysfs_bdfs: list[str] | None = None,
    lspci_rc: int = 0,
    sysfs_rc: int = 0,
    reachable: bool = True,
    render_gid: int = 993,
    group_listing: str | None = None,
    state: str | None = None,
    rule: str | None = None,
    state_stat_success: bool = True,
    state_content_success: bool = True,
    legacy_rules: dict[str, str | None] | None = None,
) -> dict:
    lspci = "\n".join(lspci_bdfs or [])
    sysfs = "\n".join(sysfs_bdfs if sysfs_bdfs is not None else lspci_bdfs or [])
    return {
        "host": host,
        "reachable": reachable,
        "lspci": {"rc": lspci_rc, "stdout": lspci},
        "sysfs": {"rc": sysfs_rc, "stdout": sysfs},
        "render_group": {"rc": 0, "stdout": f"render:x:{render_gid}:\n"},
        "groups": {"rc": 0, "stdout": group_listing or f"render:x:{render_gid}:\n"},
        "state": {
            "stat_success": state_stat_success,
            "content_success": state_content_success,
            "exists": state is not None,
            "regular": state is not None,
            "symlink": False,
            "content": state or "",
        },
        "rule": {
            "stat_success": True,
            "content_success": True,
            "exists": rule is not None,
            "regular": rule is not None,
            "symlink": False,
            "content": rule or "",
        },
        "legacy_rules": {
            key: {
                "stat_success": True,
                "content_success": True,
                "exists": content is not None,
                "regular": content is not None,
                "symlink": False,
                "content": content or "",
            }
            for key, content in (legacy_rules or {}).items()
        }
        | {
            key: {
                "stat_success": True,
                "content_success": True,
                "exists": False,
                "regular": False,
                "symlink": False,
                "content": "",
            }
            for key in ("kfd", "amdgpu", "rocm_devices")
            if key not in (legacy_rules or {})
        },
    }


def evidence_document(*hosts: dict) -> str:
    return json.dumps({"version": 2, "hosts": list(hosts)})


def expected_targets(module, *names: str):
    return tuple(module.InventoryTarget(name=name) for name in names)


def test_parse_fleet_evidence_accepts_the_exact_machine_evidence_schema() -> None:
    module = load_resolution_module()
    raw = evidence_document(host_evidence("gpu-1", lspci_bdfs=[GPU_BDF]))

    evidence = module.parse_fleet_evidence(raw)

    assert evidence[0].target == module.InventoryTarget(name="gpu-1")
    assert evidence[0].lspci.stdout == GPU_BDF
    assert evidence[0].state.exists is False


@pytest.mark.parametrize(
    "replacement",
    [
        {"version": True, "hosts": []},
        {"version": 1, "hosts": [], "unexpected": "field"},
        {"version": 1, "hosts": [{"host": "gpu-1"}]},
        {"version": 1, "hosts": [host_evidence("gpu-1", lspci_rc=True)]},
    ],
)
def test_parse_fleet_evidence_rejects_nonexact_or_boolean_integer_values(replacement: dict) -> None:
    module = load_resolution_module()

    with pytest.raises(module.EvidenceParseError):
        module.parse_fleet_evidence(json.dumps(replacement))


def test_parse_fleet_evidence_rejects_duplicate_json_keys() -> None:
    module = load_resolution_module()

    with pytest.raises(module.EvidenceParseError, match="duplicate JSON key 'version'"):
        module.parse_fleet_evidence('{"version":2,"version":2,"hosts":[]}')


def test_resolve_fleet_blocks_duplicate_persisted_state_render_gid() -> None:
    module = load_resolution_module()
    parsed = module.parse_fleet_evidence(
        evidence_document(
            host_evidence("gpu-1", lspci_bdfs=[GPU_BDF], state='{"renderGid":993,"renderGid":993,"version":1}')
        )
    )

    resolution = module.resolve_fleet(expected_targets(module, "gpu-1"), parsed)

    assert resolution.status is module.FleetStatus.BLOCKED


@pytest.mark.parametrize(
    "state",
    [
        '{"renderGid":993,"version":1,"version":1}',
        '{"renderGid":993,"version":1,"r\\u0065nderGid":993}',
        '{"renderGid":993,"version":1,"v\\u0065rsion":1}',
    ],
    ids=["duplicate-version", "escaped-render-gid", "escaped-version"],
)
def test_resolve_fleet_blocks_semantic_duplicate_persisted_state_keys(state: str) -> None:
    module = load_resolution_module()
    parsed = module.parse_fleet_evidence(evidence_document(host_evidence("gpu-1", lspci_bdfs=[GPU_BDF], state=state)))

    resolution = module.resolve_fleet(expected_targets(module, "gpu-1"), parsed)

    assert resolution.status is module.FleetStatus.BLOCKED


def test_resolve_fleet_classifies_matching_amd_bdfs_as_gpu() -> None:
    module = load_resolution_module()
    evidence = module.parse_fleet_evidence(evidence_document(host_evidence("gpu-1", lspci_bdfs=[GPU_BDF])))

    resolution = module.resolve_fleet(expected_targets(module, "gpu-1"), evidence)

    assert resolution.status is module.FleetStatus.GPU_RESOLVED
    assert resolution.render_gid == 993
    assert resolution.hosts[0].status is module.HostStatus.GPU


def test_resolve_fleet_classifies_two_empty_successful_gpu_probes_as_cpu_only() -> None:
    module = load_resolution_module()
    evidence = module.parse_fleet_evidence(evidence_document(host_evidence("cpu-1")))

    resolution = module.resolve_fleet(expected_targets(module, "cpu-1"), evidence)

    assert resolution.status is module.FleetStatus.CPU_ONLY
    assert resolution.render_gid is None
    assert resolution.hosts[0].status is module.HostStatus.CPU


@pytest.mark.parametrize(
    "evidence",
    [
        host_evidence("host-1", lspci_bdfs=[GPU_BDF], sysfs_bdfs=["0000:04:00.0"]),
        host_evidence("host-1", lspci_bdfs=[GPU_BDF], lspci_rc=1),
        host_evidence("host-1", lspci_bdfs=[GPU_BDF], reachable=False),
    ],
)
def test_resolve_fleet_blocks_unknown_gpu_evidence(evidence: dict) -> None:
    module = load_resolution_module()
    parsed = module.parse_fleet_evidence(evidence_document(evidence))

    resolution = module.resolve_fleet(expected_targets(module, "host-1"), parsed)

    assert resolution.status is module.FleetStatus.BLOCKED
    assert resolution.hosts[0].status is module.HostStatus.UNKNOWN


@pytest.mark.parametrize(
    ("targets", "hosts"),
    [
        (("gpu-1", "gpu-2"), ("gpu-1",)),
        (("gpu-1",), ("gpu-1", "gpu-2")),
    ],
)
def test_resolve_fleet_blocks_incomplete_or_unexpected_host_evidence(
    targets: tuple[str, ...], hosts: tuple[str, ...]
) -> None:
    module = load_resolution_module()
    parsed = module.parse_fleet_evidence(
        evidence_document(*(host_evidence(host, lspci_bdfs=[GPU_BDF]) for host in hosts))
    )

    resolution = module.resolve_fleet(expected_targets(module, *targets), parsed)

    assert resolution.status is module.FleetStatus.BLOCKED
    assert resolution.render_gid is None


def test_resolve_fleet_blocks_render_gid_collisions() -> None:
    module = load_resolution_module()
    parsed = module.parse_fleet_evidence(
        evidence_document(
            host_evidence(
                "gpu-1",
                lspci_bdfs=[GPU_BDF],
                group_listing="render:x:993:\nother:x:993:\n",
            )
        )
    )

    resolution = module.resolve_fleet(expected_targets(module, "gpu-1"), parsed)

    assert resolution.status is module.FleetStatus.BLOCKED
    assert resolution.hosts[0].status is module.HostStatus.UNKNOWN


def test_resolve_fleet_blocks_cpu_hosts_with_persisted_gpu_access_contracts() -> None:
    module = load_resolution_module()
    parsed = module.parse_fleet_evidence(
        evidence_document(host_evidence("cpu-1", state='{"renderGid":993,"version":1}'))
    )

    resolution = module.resolve_fleet(expected_targets(module, "cpu-1"), parsed)

    assert resolution.status is module.FleetStatus.BLOCKED
    assert resolution.hosts[0].status is module.HostStatus.UNKNOWN


@pytest.mark.parametrize("legacy_key", ["kfd", "amdgpu", "rocm_devices"])
def test_resolve_fleet_blocks_cpu_hosts_with_any_legacy_gpu_access_rule(legacy_key: str) -> None:
    module = load_resolution_module()
    parsed = module.parse_fleet_evidence(
        evidence_document(host_evidence("cpu-1", legacy_rules={legacy_key: 'KERNEL=="kfd", MODE="0666"\n'}))
    )

    resolution = module.resolve_fleet(expected_targets(module, "cpu-1"), parsed)

    assert resolution.status is module.FleetStatus.BLOCKED
    assert resolution.hosts[0].status is module.HostStatus.UNKNOWN


def test_resolve_fleet_keeps_gpu_legacy_rule_admission_for_the_later_exact_migration() -> None:
    module = load_resolution_module()
    parsed = module.parse_fleet_evidence(
        evidence_document(host_evidence("gpu-1", lspci_bdfs=[GPU_BDF], legacy_rules={"amdgpu": "legacy\n"}))
    )

    resolution = module.resolve_fleet(expected_targets(module, "gpu-1"), parsed)

    assert resolution.status is module.FleetStatus.GPU_RESOLVED


def test_resolve_fleet_blocks_file_probe_failures_instead_of_treating_them_as_absence() -> None:
    module = load_resolution_module()
    parsed = module.parse_fleet_evidence(
        evidence_document(host_evidence("cpu-1", state_stat_success=False, state_content_success=False))
    )

    resolution = module.resolve_fleet(expected_targets(module, "cpu-1"), parsed)

    assert resolution.status is module.FleetStatus.BLOCKED
    assert resolution.hosts[0].status is module.HostStatus.UNKNOWN


@pytest.mark.parametrize(
    "contracts",
    [
        {"state": '{"renderGid":994,"version":1}'},
        {"rule": 'KERNEL=="kfd", MODE="0666"\n'},
    ],
)
def test_resolve_fleet_blocks_gpu_hosts_with_unsafe_persisted_contracts(contracts: dict) -> None:
    module = load_resolution_module()
    parsed = module.parse_fleet_evidence(evidence_document(host_evidence("gpu-1", lspci_bdfs=[GPU_BDF], **contracts)))

    resolution = module.resolve_fleet(expected_targets(module, "gpu-1"), parsed)

    assert resolution.status is module.FleetStatus.BLOCKED
    assert resolution.hosts[0].status is module.HostStatus.UNKNOWN


def test_resolve_fleet_requires_unanimous_gpu_render_gid() -> None:
    module = load_resolution_module()
    same_gid = module.parse_fleet_evidence(
        evidence_document(
            host_evidence("gpu-1", lspci_bdfs=[GPU_BDF], render_gid=993),
            host_evidence("gpu-2", lspci_bdfs=["0000:04:00.0"], render_gid=993),
        )
    )
    mixed_gid = module.parse_fleet_evidence(
        evidence_document(
            host_evidence("gpu-1", lspci_bdfs=[GPU_BDF], render_gid=993),
            host_evidence("gpu-2", lspci_bdfs=["0000:04:00.0"], render_gid=994),
        )
    )

    resolved = module.resolve_fleet(expected_targets(module, "gpu-1", "gpu-2"), same_gid)
    blocked = module.resolve_fleet(expected_targets(module, "gpu-1", "gpu-2"), mixed_gid)

    assert resolved.status is module.FleetStatus.GPU_RESOLVED
    assert resolved.render_gid == 993
    assert blocked.status is module.FleetStatus.BLOCKED
    assert blocked.render_gid is None


def test_resolution_manifest_preserves_explicit_host_booleans_and_unanimous_gid() -> None:
    module = load_resolution_module()
    parsed = module.parse_fleet_evidence(
        evidence_document(
            host_evidence("gpu-1", lspci_bdfs=[GPU_BDF], render_gid=993),
            host_evidence("cpu-1"),
        )
    )

    resolution = module.resolve_fleet(expected_targets(module, "gpu-1", "cpu-1"), parsed)
    manifest = module.resolution_manifest(resolution)

    assert manifest == {
        "version": 1,
        "status": "gpu_resolved",
        "render_gid": 993,
        "hosts": {"cpu-1": False, "gpu-1": True},
    }


def test_resolution_manifest_is_an_ordinary_dict_with_exact_order_and_sorted_hosts() -> None:
    manifest = load_manifest_module().build_resolution_manifest(
        version=1,
        status="gpu_resolved",
        render_gid=993,
        hosts={"zeta": True, "alpha": False},
    )

    assert type(manifest) is dict
    assert list(manifest) == ["version", "status", "render_gid", "hosts"]
    assert list(manifest["hosts"]) == ["alpha", "zeta"]
    assert set(manifest) == {"version", "status", "render_gid", "hosts"}


def test_pxe_resolution_manifest_constructs_without_mutating_base_manifest() -> None:
    module = load_manifest_module()
    base = module.build_resolution_manifest(
        version=1,
        status="gpu_resolved",
        render_gid=993,
        hosts={"gpu-2": True, "gpu-1": True},
    )

    manifest = module.build_pxe_resolution_manifest(
        version=base["version"],
        status=base["status"],
        render_gid=base["render_gid"],
        hosts=base["hosts"],
        gpu_access_enabled=True,
        pxe_render_gid=994,
    )

    assert base == {
        "version": 1,
        "status": "gpu_resolved",
        "render_gid": 993,
        "hosts": {"gpu-1": True, "gpu-2": True},
    }
    assert list(manifest) == ["version", "status", "render_gid", "hosts", "pxe_rootfs"]
    assert manifest["pxe_rootfs"] == {"gpu_access_enabled": True, "render_gid": 994}
    assert set(manifest["pxe_rootfs"]) == {"gpu_access_enabled", "render_gid"}
