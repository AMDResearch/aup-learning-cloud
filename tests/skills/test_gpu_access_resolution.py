# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

"""Behavior tests for fleet GPU-access discovery resolution."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RESOLUTION = ROOT / "skills" / "deploy-aup-learning-cloud" / "scripts" / "gpu_access_resolution.py"
MANIFEST = ROOT / "skills" / "deploy-aup-learning-cloud" / "scripts" / "gpu_resolution_manifest.py"
DISCOVERY_PLAYBOOK = ROOT / "deploy" / "ansible" / "playbooks" / "pb-gpu-access-discovery.yml"
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
) -> dict:
    lspci = "\n".join(lspci_bdfs or [])
    sysfs = "\n".join(sysfs_bdfs if sysfs_bdfs is not None else lspci_bdfs or [])
    return {
        "host": host,
        "reachable": reachable,
        "lspci": {"rc": lspci_rc, "stdout": lspci},
        "sysfs": {"rc": sysfs_rc, "stdout": sysfs},
    }


def evidence_document(*hosts: dict) -> str:
    return json.dumps({"version": 1, "hosts": list(hosts)})


def expected_targets(module, *names: str):
    return tuple(module.InventoryTarget(name=name) for name in names)


def test_discovery_playbook_preserves_lspci_agreement_and_exact_v1_host_evidence_shape() -> None:
    playbook = DISCOVERY_PLAYBOOK.read_text(encoding="utf-8")
    evidence_block = playbook.split("_auplc_gpu_access_discovery_evidence:", maxsplit=1)[1].split(
        "      changed_when:", maxsplit=1
    )[0]
    fallback_block = playbook.split("_auplc_gpu_access_unknown_evidence:", maxsplit=1)[1].split(
        "  pre_tasks:", maxsplit=1
    )[0]
    evidence_keys = re.findall(r"^          ([a-z_]+):", evidence_block, re.MULTILINE)
    fallback_keys = re.findall(r"^      ([a-z_]+):", fallback_block, re.MULTILINE)

    assert evidence_keys == ["host", "reachable", "lspci", "sysfs"]
    assert fallback_keys == ["reachable", "lspci", "sysfs"]
    assert "combine({'host': discovery_host})" in playbook
    assert '{"version":1,"hosts":[' in playbook
    assert "hostvars[discovery_host]._auplc_gpu_access_discovery_evidence" in playbook
    assert "| to_json" in playbook
    assert "name: gpu_access" in playbook
    assert "tasks_from: detect" in playbook
    assert "_auplc_gpu_access_sysfs.rc" in playbook
    assert "_auplc_gpu_access_sysfs.stdout" in playbook
    assert "/sys/bus/pci/devices" not in playbook
    assert 'argv: [lspci, -Dnn, -d, "1002::0300"]' in playbook
    assert 'argv: [lspci, -Dnn, -d, "1002::0302"]' in playbook
    assert 'argv: [lspci, -Dnn, -d, "1002::0380"]' in playbook


def test_parse_fleet_evidence_accepts_the_exact_machine_evidence_schema() -> None:
    module = load_resolution_module()

    evidence = module.parse_fleet_evidence(evidence_document(host_evidence("gpu-1", lspci_bdfs=[GPU_BDF])))

    assert evidence[0].target == module.InventoryTarget(name="gpu-1")
    assert evidence[0].lspci.stdout == GPU_BDF
    assert evidence[0].sysfs.stdout == GPU_BDF


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
        module.parse_fleet_evidence('{"version":1,"version":1,"hosts":[]}')


def test_resolve_fleet_classifies_matching_amd_bdfs_as_gpu() -> None:
    module = load_resolution_module()
    evidence = module.parse_fleet_evidence(evidence_document(host_evidence("gpu-1", lspci_bdfs=[GPU_BDF])))

    resolution = module.resolve_fleet(expected_targets(module, "gpu-1"), evidence)

    assert resolution.status is module.FleetStatus.GPU_RESOLVED
    assert resolution.hosts[0].status is module.HostStatus.GPU


def test_resolve_fleet_classifies_two_empty_successful_gpu_probes_as_cpu_only() -> None:
    module = load_resolution_module()
    evidence = module.parse_fleet_evidence(evidence_document(host_evidence("cpu-1")))

    resolution = module.resolve_fleet(expected_targets(module, "cpu-1"), evidence)

    assert resolution.status is module.FleetStatus.CPU_ONLY
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
    assert resolution.reason == "incomplete host coverage"


def test_resolve_fleet_accepts_gpu_hosts_without_a_shared_gid() -> None:
    module = load_resolution_module()
    parsed = module.parse_fleet_evidence(
        evidence_document(
            host_evidence("gpu-1", lspci_bdfs=[GPU_BDF]),
            host_evidence("gpu-2", lspci_bdfs=["0000:04:00.0"]),
        )
    )

    resolution = module.resolve_fleet(expected_targets(module, "gpu-1", "gpu-2"), parsed)

    assert resolution.status is module.FleetStatus.GPU_RESOLVED
    assert [host.status for host in resolution.hosts] == [module.HostStatus.GPU, module.HostStatus.GPU]


def test_resolution_manifest_preserves_explicit_host_booleans() -> None:
    module = load_resolution_module()
    parsed = module.parse_fleet_evidence(
        evidence_document(
            host_evidence("gpu-1", lspci_bdfs=[GPU_BDF]),
            host_evidence("cpu-1"),
        )
    )

    manifest = module.resolution_manifest(module.resolve_fleet(expected_targets(module, "gpu-1", "cpu-1"), parsed))

    assert manifest == {
        "version": 1,
        "status": "gpu_resolved",
        "hosts": {"cpu-1": False, "gpu-1": True},
    }


def test_resolution_manifest_is_an_ordinary_dict_with_exact_order_and_sorted_hosts() -> None:
    manifest = load_manifest_module().build_resolution_manifest(
        status="gpu_resolved",
        hosts={"zeta": True, "alpha": False},
    )

    assert type(manifest) is dict
    assert list(manifest) == ["version", "status", "hosts"]
    assert list(manifest["hosts"]) == ["alpha", "zeta"]
    assert set(manifest) == {"version", "status", "hosts"}


def test_pxe_resolution_manifest_constructs_without_mutating_base_manifest() -> None:
    module = load_manifest_module()
    base = module.build_resolution_manifest(
        status="gpu_resolved",
        hosts={"gpu-2": True, "gpu-1": True},
    )

    manifest = module.build_pxe_resolution_manifest(
        base,
        gpu_access_enabled=True,
    )

    assert base == {
        "version": 1,
        "status": "gpu_resolved",
        "hosts": {"gpu-1": True, "gpu-2": True},
    }
    assert list(manifest) == ["version", "status", "hosts", "pxe_rootfs"]
    assert manifest["pxe_rootfs"] == {"gpu_access_enabled": True}
    assert set(manifest["pxe_rootfs"]) == {"gpu_access_enabled"}
