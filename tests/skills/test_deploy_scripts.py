# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.

"""Public CLI regression tests for deploy-skill helper scripts."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPTS = ROOT / "skills" / "deploy-aup-learning-cloud" / "scripts"
VALIDATE = DEPLOY_SCRIPTS / "validate.py"
GEN_CONFIGS = DEPLOY_SCRIPTS / "gen_configs.py"
ARTIFACT_STORE = DEPLOY_SCRIPTS / "artifact_store.py"


def run_script(script: Path, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def write_file(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def fake_ansible_playbook(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_bin = tmp_path / "fake-ansible"
    fake_bin.mkdir()
    fake_ansible = fake_bin / "ansible-playbook"
    fake_ansible.write_text(
        r"""#!/usr/bin/env python3
import json
from pathlib import Path
import sys

arguments = sys.argv[1:]
inventory = Path(arguments[arguments.index('-i') + 1])
output = next(value.split('=', 1)[1] for value in arguments if value.startswith('gpu_access_discovery_output_path='))
hosts = [line.strip()[:-1] for line in inventory.read_text(encoding='utf-8').splitlines() if line.startswith('        ') and line.rstrip().endswith(':')]
evidence = {
        'version': 1,
    'hosts': [{
        'host': host,
        'reachable': True,
        'lspci': {'rc': 0, 'stdout': ''},
        'sysfs': {'rc': 0, 'stdout': ''},
    } for host in hosts],
}
Path(output).write_text(json.dumps(evidence), encoding='utf-8')
""",
        encoding="utf-8",
    )
    fake_ansible.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")


def write_cluster(repo: Path, labels: list[str]) -> Path:
    return write_file(repo / "cluster.json", json.dumps({"gpu_product_names": labels}))


def write_resolved_gpu_artifacts(repo: Path) -> tuple[Path, Path, Path]:
    inventory = write_file(
        repo / "generated/inventory.yml",
        """k3s_cluster:
  children:
    server:
      hosts:
        server:
          ansible_host: 192.168.1.10
          auplc_gpu_access_enabled: true
    agent:
      hosts:
        agent:
          ansible_host: 192.168.1.11
          auplc_gpu_access_enabled: false
""",
    )
    values = write_file(
        repo / "generated/values-basic-example.yaml",
        """custom:
  resources:
    metadata: {}
""",
    )
    resolution = write_file(
        repo / "generated/gpu-access-resolution.json",
        json.dumps(
            {
                "version": 1,
                "status": "gpu_resolved",
                "hosts": {"agent": False, "server": True},
            }
        ),
    )
    return inventory, values, resolution


def load_validate_module():
    sys.path.insert(0, str(DEPLOY_SCRIPTS))
    try:
        spec = importlib.util.spec_from_file_location("deploy_validate", VALIDATE)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


def load_deploy_module(module_name: str, script: Path):
    sys.path.insert(0, str(DEPLOY_SCRIPTS))
    try:
        spec = importlib.util.spec_from_file_location(module_name, script)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def test_ssh_topology_skips_pxe_checks_and_version_sync(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    write_file(repo / "deploy/ansible/inventory.yml", "k3s_version: v1.32.3+k3s1\n")
    write_file(
        repo / "deploy/ansible/playbooks/pb-pxe-controller.yml",
        """pxe_network_interface: ""
pxe_subnet: ""
pxe_controller_ip: ""
pxe_dns_servers: ""
pxe_k3s_server_ips: []
pxe_rootfs_authorized_keys: []
pxe_k3s_version: v1.33.0+k3s1
""",
    )
    write_file(repo / "runtime/values.yaml", "custom:\n  resources:\n    metadata: {}\n")

    result = run_script(VALIDATE, "--repo", str(repo), "--topology", "ssh-preinstalled")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "skipped PXE checks for ssh-preinstalled topology" in result.stdout
    assert "[FAIL] PXE var" not in result.stdout
    assert "version mismatch" not in result.stdout


def test_validator_checks_only_effective_active_accelerators_in_values_order(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    base = write_file(
        repo / "runtime/values.yaml",
        """custom:
  accelerators:
    phx:
      nodeSelector:
        amd.com/gpu.product-name: AMD_Radeon_780M_Graphics
    strix-halo:
      nodeSelector:
        amd.com/gpu.product-name: AMD_Radeon_8060S_Graphics
  resources:
    metadata:
      gpu:
        acceleratorKeys:
          - phx
""",
    )
    overlay = write_file(
        repo / "runtime/values-strix-halo.yaml",
        """custom:
  resources:
    metadata:
      gpu:
        acceleratorKeys:
          - strix-halo
""",
    )
    cluster = write_cluster(repo, ["AMD_Radeon_8060S_Graphics"])

    result = run_script(
        VALIDATE,
        "--repo",
        str(repo),
        "--topology",
        "ssh-preinstalled",
        "--values",
        str(base),
        "--values",
        str(overlay),
        "--cluster",
        str(cluster),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "AMD_Radeon_8060S_Graphics" in result.stdout
    assert "AMD_Radeon_780M_Graphics" not in result.stdout


def test_validator_retains_selectors_from_partial_accelerator_overlays(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    base = write_file(
        repo / "runtime/values.yaml",
        """custom:
  accelerators:
    strix-halo:
      nodeSelector:
        amd.com/gpu.product-name: AMD_Radeon_8060S_Graphics
  resources:
    metadata:
      gpu:
        acceleratorKeys: [strix-halo]
""",
    )
    overlay = write_file(
        repo / "runtime/values-overlay.yaml",
        """custom:
  accelerators:
    strix-halo:
      displayName: "Renamed Strix Halo"
""",
    )
    cluster = write_cluster(repo, ["AMD_Radeon_8060S_Graphics"])

    result = run_script(
        VALIDATE,
        "--repo",
        str(repo),
        "--topology",
        "ssh-preinstalled",
        "--values",
        str(base),
        "--values",
        str(overlay),
        "--cluster",
        str(cluster),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "AMD_Radeon_8060S_Graphics" in result.stdout


def test_validator_accepts_quoted_product_label_keys(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    values = write_file(
        repo / "runtime/values.yaml",
        """custom:
  accelerators:
    9070xt:
      nodeSelector:
        "amd.com/gpu.product-name": "AMD_Radeon_RX_9070_XT"
  resources:
    metadata:
      gpu:
        acceleratorKeys: [9070xt]
""",
    )
    cluster = write_cluster(repo, ["AMD_Radeon_RX_9070_XT"])

    result = run_script(
        VALIDATE,
        "--repo",
        str(repo),
        "--topology",
        "ssh-preinstalled",
        "--values",
        str(values),
        "--cluster",
        str(cluster),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "AMD_Radeon_RX_9070_XT" in result.stdout


def test_validator_rejects_relevant_non_empty_flow_mappings(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    values = write_file(
        repo / "runtime/values.yaml",
        """custom:
  accelerators: {9070xt: {nodeSelector: {amd.com/gpu.product-name: AMD_Radeon_RX_9070_XT}}}
  resources:
    metadata:
      gpu: {acceleratorKeys: [9070xt]}
""",
    )

    result = run_script(
        VALIDATE,
        "--repo",
        str(repo),
        "--topology",
        "ssh-preinstalled",
        "--values",
        str(values),
    )

    assert result.returncode == 1
    assert "unsupported non-empty flow-style mapping" in result.stdout


def test_validator_rejects_flow_style_custom_resources_wrapper(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    values = write_file(
        repo / "runtime/values.yaml",
        """custom:
  accelerators:
    strix-halo:
      nodeSelector:
        amd.com/gpu.product-name: AMD_Radeon_8060S_Graphics
  resources: {metadata: {gpu: {acceleratorKeys: [strix-halo]}}}
""",
    )

    result = run_script(VALIDATE, "--repo", str(repo), "--topology", "ssh-preinstalled", "--values", str(values))

    assert result.returncode == 1
    assert "unsupported non-empty flow-style mapping at custom.resources" in result.stdout


def test_validator_rejects_fully_flow_style_custom_wrapper(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    values = write_file(
        repo / "runtime/values.yaml",
        """custom: {accelerators: {strix-halo: {nodeSelector: {amd.com/gpu.product-name: AMD_Radeon_8060S_Graphics}}}, resources: {metadata: {gpu: {acceleratorKeys: [strix-halo]}}}}
""",
    )

    result = run_script(VALIDATE, "--repo", str(repo), "--topology", "ssh-preinstalled", "--values", str(values))

    assert result.returncode == 1
    assert "unsupported non-empty flow-style mapping at custom" in result.stdout


def test_validator_rejects_parent_aliases_and_scalar_accelerator_keys(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    alias_values = write_file(repo / "alias.yaml", "defaults: {}\ncustom: *defaults\n")
    scalar_keys = write_file(
        repo / "scalar-keys.yaml",
        """custom:
  resources:
    metadata:
      gpu:
        acceleratorKeys: strix-halo
""",
    )

    alias_result = run_script(
        VALIDATE, "--repo", str(repo), "--topology", "ssh-preinstalled", "--values", str(alias_values)
    )
    scalar_result = run_script(
        VALIDATE, "--repo", str(repo), "--topology", "ssh-preinstalled", "--values", str(scalar_keys)
    )

    assert alias_result.returncode == 1
    assert "unsupported YAML syntax at custom" in alias_result.stdout
    assert scalar_result.returncode == 1
    assert "acceleratorKeys must be a list" in scalar_result.stdout


def test_validator_fails_for_missing_explicit_and_default_values_files(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    repo.mkdir()
    explicit_result = run_script(
        VALIDATE,
        "--repo",
        str(repo),
        "--topology",
        "ssh-preinstalled",
        "--values",
        str(repo / "missing.yaml"),
    )
    default_result = run_script(VALIDATE, "--repo", str(repo), "--topology", "ssh-preinstalled")

    assert explicit_result.returncode == 1
    assert default_result.returncode == 1
    assert "values file not found" in explicit_result.stdout
    assert "values file not found" in default_result.stdout


def test_validator_rejects_duplicate_pxe_and_inventory_safety_keys(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    write_file(repo / "runtime/values.yaml", "custom:\n  resources:\n    metadata: {}\n")
    write_file(repo / "deploy/ansible/inventory.yml", "k3s_version: v1.32.3+k3s1\nk3s_version: v1.33.0+k3s1\n")
    vars_file = write_file(
        repo / "pxe-vars.yml",
        """pxe_network_interface: enp1s0
pxe_network_interface: ""
pxe_subnet: 192.168.1.0/24
pxe_controller_ip: 192.168.1.10
pxe_dns_servers: 8.8.8.8
pxe_k3s_server_ips:
  - 192.168.1.10
pxe_rootfs_authorized_keys:
  - ssh-ed25519 AAAA test@example
pxe_k3s_version: v1.32.3+k3s1
pxe_k3s_version: v1.33.0+k3s1
""",
    )

    result = run_script(
        VALIDATE,
        "--repo",
        str(repo),
        "--topology",
        "pxe-diskless",
        "--pxe-vars",
        str(vars_file),
    )

    assert result.returncode == 1
    assert "duplicate PXE key 'pxe_network_interface'" in result.stdout
    assert "duplicate PXE key 'pxe_k3s_version'" in result.stdout
    assert "duplicate inventory key 'k3s_version'" in result.stdout


def test_validator_fails_empty_supplied_cluster_for_active_accelerators(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    values = write_file(
        repo / "runtime/values.yaml",
        """custom:
  accelerators:
    strix-halo:
      nodeSelector:
        amd.com/gpu.product-name: AMD_Radeon_8060S_Graphics
  resources:
    metadata:
      gpu:
        acceleratorKeys: [strix-halo]
""",
    )
    cluster = write_file(repo / "cluster.json", "{}")

    result = run_script(
        VALIDATE,
        "--repo",
        str(repo),
        "--topology",
        "ssh-preinstalled",
        "--values",
        str(values),
        "--cluster",
        str(cluster),
    )

    assert result.returncode == 1
    assert "cluster snapshot has no GPU product labels" in result.stdout


def test_validator_rejects_unsupported_yaml_syntax_at_relevant_values(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    base = write_file(
        repo / "runtime/values.yaml",
        """custom:
  accelerators:
    strix-halo:
      nodeSelector:
        amd.com/gpu.product-name: AMD_Radeon_8060S_Graphics
  resources:
    metadata:
      gpu:
        acceleratorKeys: [strix-halo]
""",
    )
    for index, value in enumerate(("&keys [strix-halo]", "*keys", "!list [strix-halo]", "|")):
        overlay = write_file(
            repo / f"unsupported-keys-{index}.yaml",
            f"""custom:
  resources:
    metadata:
      gpu:
        acceleratorKeys: {value}
""",
        )
        result = run_script(
            VALIDATE,
            "--repo",
            str(repo),
            "--topology",
            "ssh-preinstalled",
            "--values",
            str(base),
            "--values",
            str(overlay),
        )
        assert result.returncode == 1
        assert "unsupported YAML syntax" in result.stdout


def test_validator_rejects_unsupported_yaml_syntax_at_product_selector(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    values = write_file(
        repo / "runtime/values.yaml",
        """custom:
  accelerators:
    strix-halo:
      nodeSelector:
        amd.com/gpu.product-name: &label AMD_Radeon_8060S_Graphics
  resources:
    metadata:
      gpu:
        acceleratorKeys: [strix-halo]
""",
    )

    result = run_script(VALIDATE, "--repo", str(repo), "--topology", "ssh-preinstalled", "--values", str(values))

    assert result.returncode == 1
    assert "unsupported YAML syntax at custom.accelerators.strix-halo.nodeSelector" in result.stdout


def test_validator_uses_generated_pxe_vars_file_when_requested(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    spec_path = write_file(repo / "spec.json", json.dumps(generator_spec("pxe-diskless")))
    generated = repo / "generated"
    generation = run_script(GEN_CONFIGS, "--spec", str(spec_path), "--out-dir", str(generated))
    write_file(repo / "deploy/ansible/inventory.yml", "k3s_version: v1.32.3+k3s1\n")
    write_file(repo / "deploy/ansible/playbooks/pb-pxe-controller.yml", "pxe_k3s_version: v1.33.0+k3s1\n")
    write_file(repo / "runtime/values.yaml", "custom:\n  resources:\n    metadata: {}\n")

    result = run_script(
        VALIDATE,
        "--repo",
        str(repo),
        "--topology",
        "pxe-diskless",
        "--pxe-vars",
        str(generated / "pb-pxe-controller.vars.yml"),
    )

    assert generation.returncode == 0, generation.stdout + generation.stderr
    assert result.returncode == 0, result.stdout + result.stderr
    assert "k3s_version == pxe_k3s_version" in result.stdout


def test_validator_honors_every_supported_explicit_clear_syntax(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    base = write_file(
        repo / "runtime/values.yaml",
        """custom:
  accelerators:
    strix-halo:
      nodeSelector:
        amd.com/gpu.product-name: AMD_Radeon_8060S_Graphics
  resources:
    metadata:
      gpu:
        acceleratorKeys: [strix-halo]
""",
    )

    for index, clear_value in enumerate(('""', "null", "~")):
        selector_overlay = write_file(
            repo / f"selector-clear-{index}.yaml",
            f"""custom:
  accelerators:
    strix-halo:
      nodeSelector:
        amd.com/gpu.product-name: {clear_value}
""",
        )
        result = run_script(
            VALIDATE,
            "--repo",
            str(repo),
            "--topology",
            "ssh-preinstalled",
            "--values",
            str(base),
            "--values",
            str(selector_overlay),
        )
        assert result.returncode == 1
        assert "has no amd.com/gpu.product-name nodeSelector" in result.stdout

    for index, clear_value in enumerate(("null", "~", "[]")):
        keys_overlay = write_file(
            repo / f"keys-clear-{index}.yaml",
            f"""custom:
  resources:
    metadata:
      gpu:
        acceleratorKeys: {clear_value}
""",
        )
        result = run_script(
            VALIDATE,
            "--repo",
            str(repo),
            "--topology",
            "ssh-preinstalled",
            "--values",
            str(base),
            "--values",
            str(keys_overlay),
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "no acceleratorKeys found" in result.stdout


def test_validator_main_resets_report_state_between_invocations(tmp_path: Path) -> None:
    module = load_validate_module()
    failed_repo = tmp_path / "failed"
    success_repo = tmp_path / "success"
    failed_values = write_file(
        failed_repo / "runtime/values.yaml",
        """custom:
  accelerators: {}
  resources:
    metadata:
      gpu:
        acceleratorKeys: [missing]
""",
    )
    success_values = write_file(success_repo / "runtime/values.yaml", "custom:\n  resources:\n    metadata: {}\n")

    with redirect_stdout(io.StringIO()):
        first = module.main(
            ["--repo", str(failed_repo), "--topology", "ssh-preinstalled", "--values", str(failed_values)]
        )
        second = module.main(
            ["--repo", str(success_repo), "--topology", "ssh-preinstalled", "--values", str(success_values)]
        )

    assert first == 1
    assert second == 0


def test_validator_ignores_accelerators_and_metadata_outside_custom_resources(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    values = write_file(
        repo / "runtime/values.yaml",
        """custom:
  accelerators:
    strix-halo:
      nodeSelector:
        amd.com/gpu.product-name: AMD_Radeon_8060S_Graphics
  resources:
    metadata:
      gpu:
        acceleratorKeys: [strix-halo]
other:
  accelerators:
    typo-gpu:
      nodeSelector:
        amd.com/gpu.product-name: AMD_Typo_GPU
  metadata:
    gpu:
      acceleratorKeys: [typo-gpu]
""",
    )
    cluster = write_cluster(repo, ["AMD_Radeon_8060S_Graphics"])

    result = run_script(
        VALIDATE,
        "--repo",
        str(repo),
        "--topology",
        "ssh-preinstalled",
        "--values",
        str(values),
        "--cluster",
        str(cluster),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "typo-gpu" not in result.stdout


def test_validator_fails_when_an_active_accelerator_key_is_missing(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    values = write_file(
        repo / "runtime/values.yaml",
        """custom:
  accelerators: {}
  resources:
    metadata:
      gpu:
        acceleratorKeys:
          - typo-gpu
""",
    )

    result = run_script(
        VALIDATE,
        "--repo",
        str(repo),
        "--topology",
        "ssh-preinstalled",
        "--values",
        str(values),
    )

    assert result.returncode == 1
    assert "active accelerator 'typo-gpu' is not defined under custom.accelerators" in result.stdout


def test_validator_fails_when_an_active_accelerator_has_no_product_selector(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    values = write_file(
        repo / "runtime/values.yaml",
        """custom:
  accelerators:
    strix-halo: {}
  resources:
    metadata:
      gpu:
        acceleratorKeys:
          - strix-halo
""",
    )

    result = run_script(
        VALIDATE,
        "--repo",
        str(repo),
        "--topology",
        "ssh-preinstalled",
        "--values",
        str(values),
    )

    assert result.returncode == 1
    assert "active accelerator 'strix-halo' has no amd.com/gpu.product-name nodeSelector" in result.stdout


def test_validator_accepts_consistent_gpu_resolved_artifacts(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    inventory, values, resolution = write_resolved_gpu_artifacts(repo)

    result = run_script(
        VALIDATE,
        "--repo",
        str(repo),
        "--topology",
        "ssh-preinstalled",
        "--inventory",
        str(inventory),
        "--values",
        str(values),
        "--gpu-resolution",
        str(resolution),
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "GPU access artifacts agree" in result.stdout


@pytest.mark.parametrize(
    ("resolution_content", "expected_error"),
    [
        ("not JSON", "GPU resolution manifest is malformed"),
        (
            '{"version":1,"status":"pending","hosts":{"agent":false,"server":true}}',
            "GPU resolution manifest status must be cpu_only or gpu_resolved",
        ),
        (
            '{"version":1,"status":"gpu_resolved","hosts":{"server":true,"server":false}}',
            "duplicate JSON key 'server'",
        ),
        (
            '{"version":1,"status":"gpu_resolved","hosts":{"ser\\u0076er":true,"server":false}}',
            "duplicate JSON key 'server'",
        ),
    ],
)
def test_validator_rejects_malformed_pending_or_duplicate_gpu_resolution(
    tmp_path: Path, resolution_content: str, expected_error: str
) -> None:
    repo = tmp_path / "checkout"
    inventory, values, resolution = write_resolved_gpu_artifacts(repo)
    resolution.write_text(resolution_content, encoding="utf-8")

    result = run_script(
        VALIDATE,
        "--repo",
        str(repo),
        "--topology",
        "ssh-preinstalled",
        "--inventory",
        str(inventory),
        "--values",
        str(values),
        "--gpu-resolution",
        str(resolution),
    )

    assert result.returncode == 1
    assert expected_error in result.stdout


def test_validator_rejects_missing_generated_gpu_resolution_artifact(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    inventory, values, _ = write_resolved_gpu_artifacts(repo)
    missing_resolution = repo / "generated/missing-gpu-access-resolution.json"

    result = run_script(
        VALIDATE,
        "--repo",
        str(repo),
        "--topology",
        "ssh-preinstalled",
        "--inventory",
        str(inventory),
        "--values",
        str(values),
        "--gpu-resolution",
        str(missing_resolution),
    )

    assert result.returncode == 1
    assert "GPU resolution manifest not found" in result.stdout


def test_validator_rejects_mismatched_host_boolean(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    inventory, values, resolution = write_resolved_gpu_artifacts(repo)
    resolution.write_text(
        json.dumps(
            {
                "version": 1,
                "status": "gpu_resolved",
                "hosts": {"agent": True, "server": True},
            }
        ),
        encoding="utf-8",
    )

    result = run_script(
        VALIDATE,
        "--repo",
        str(repo),
        "--topology",
        "ssh-preinstalled",
        "--inventory",
        str(inventory),
        "--values",
        str(values),
        "--gpu-resolution",
        str(resolution),
    )

    assert result.returncode == 1
    assert "inventory host 'agent' GPU access boolean disagrees" in result.stdout


def test_validator_rejects_pxe_rootfs_boolean_mismatch(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    inventory = write_file(
        repo / "generated/inventory.yml",
        """k3s_cluster:
  children:
    server:
      hosts:
        server:
          ansible_host: 192.168.1.10
          auplc_gpu_access_enabled: false
    agent:
      hosts: {}
""",
    )
    values = write_file(repo / "generated/values-basic-example.yaml", "custom:\n  resources:\n    metadata: {}\n")
    resolution = write_file(
        repo / "generated/gpu-access-resolution.json",
        json.dumps(
            {
                "version": 1,
                "status": "cpu_only",
                "hosts": {"server": False},
                "pxe_rootfs": {"gpu_access_enabled": True},
            }
        ),
    )
    pxe_vars = write_file(
        repo / "generated/pb-pxe-controller.vars.yml",
        """pxe_network_interface: eno1
pxe_subnet: 192.168.1.0/24
pxe_controller_ip: 192.168.1.10
pxe_dns_servers: 8.8.8.8
pxe_k3s_server_ips: [192.168.1.10]
pxe_rootfs_authorized_keys: [ssh-ed25519-AAA]
pxe_k3s_version: v1.32.3+k3s1
pxe_gpu_access_enabled: false
""",
    )

    result = run_script(
        VALIDATE,
        "--repo",
        str(repo),
        "--topology",
        "pxe-diskless",
        "--inventory",
        str(inventory),
        "--values",
        str(values),
        "--gpu-resolution",
        str(resolution),
        "--pxe-vars",
        str(pxe_vars),
    )

    assert result.returncode == 1
    assert "pxe_gpu_access_enabled disagrees" in result.stdout


def test_generator_rejects_unknown_accelerator_keys_before_writing_artifacts(tmp_path: Path) -> None:
    spec = write_file(
        tmp_path / "spec.json",
        json.dumps(
            {
                "topology": "ssh-preinstalled",
                "k3s_version": "v1.32.3+k3s1",
                "server": {"name": "server", "ip": "192.168.1.10"},
                "accelerators": {"typo-gpu": {"product_name": "AMD_Typo_GPU"}},
            }
        ),
    )
    out_dir = tmp_path / "generated"

    result = run_script(GEN_CONFIGS, "--spec", str(spec), "--out-dir", str(out_dir))

    assert result.returncode == 1
    assert "unsupported accelerator key 'typo-gpu'" in result.stderr
    assert not out_dir.exists()


def test_generator_retains_known_accelerator_product_name_overrides(tmp_path: Path) -> None:
    spec = write_file(
        tmp_path / "spec.json",
        json.dumps(
            {
                "topology": "ssh-preinstalled",
                "k3s_version": "v1.32.3+k3s1",
                "server": {"name": "server", "ip": "192.168.1.10"},
                "accelerators": {"strix-halo": {"product_name": "AMD_Custom_8060S"}},
            }
        ),
    )
    out_dir = tmp_path / "generated"

    result = run_script(GEN_CONFIGS, "--spec", str(spec), "--out-dir", str(out_dir))

    assert result.returncode == 0, result.stdout + result.stderr
    values = (out_dir / "values-basic-example.yaml").read_text(encoding="utf-8")
    assert 'amd.com/gpu.product-name: "AMD_Custom_8060S"' in values


@pytest.mark.parametrize(
    ("auth_mode", "expected_auth"),
    [
        ("auto-login", {"autoLogin": True}),
        ("dummy", {"dummy": True}),
        ("github", {"github": True}),
        ("local", {"native": True}),
        ("multi", {"native": True, "github": True}),
    ],
)
def test_generator_emits_canonical_auth_and_runtime_policy(
    tmp_path: Path, auth_mode: str, expected_auth: dict[str, bool]
) -> None:
    spec = generator_spec()
    spec["auth_mode"] = auth_mode
    spec_path = write_file(tmp_path / "spec.json", json.dumps(spec))
    out_dir = tmp_path / "generated"

    result = run_script(GEN_CONFIGS, "--spec", str(spec_path), "--out-dir", str(out_dir))

    assert result.returncode == 0, result.stdout + result.stderr
    values = yaml.safe_load((out_dir / "values-basic-example.yaml").read_text(encoding="utf-8"))
    custom = values["custom"]
    assert custom["auth"] == expected_auth
    assert "authMode" not in custom
    assert custom["runtimeLimitEnabled"] is True
    assert custom["quota"]["enabled"] is True


@pytest.mark.parametrize("auth_mode", [None, 42, "unsupported"])
def test_generator_rejects_invalid_auth_mode_before_discovery(
    tmp_path: Path, auth_mode: str | int | None
) -> None:
    spec = generator_spec()
    spec["auth_mode"] = auth_mode
    spec_path = write_file(tmp_path / "spec.json", json.dumps(spec))
    out_dir = tmp_path / "generated"

    result = run_script(GEN_CONFIGS, "--spec", str(spec_path), "--out-dir", str(out_dir))

    assert result.returncode == 1
    assert "spec.auth_mode must be one of: auto-login, dummy, github, local, multi" in result.stderr
    assert not out_dir.exists()


def test_generator_rejects_a_non_mapping_accelerators_field_before_writing_artifacts(tmp_path: Path) -> None:
    spec = write_file(
        tmp_path / "spec.json",
        json.dumps(
            {
                "topology": "ssh-preinstalled",
                "k3s_version": "v1.32.3+k3s1",
                "server": {"name": "server", "ip": "192.168.1.10"},
                "accelerators": [],
            }
        ),
    )
    out_dir = tmp_path / "generated"

    result = run_script(GEN_CONFIGS, "--spec", str(spec), "--out-dir", str(out_dir))

    assert result.returncode == 1
    assert "spec.accelerators must be a mapping" in result.stderr
    assert not out_dir.exists()


def generator_spec(topology: str = "ssh-preinstalled", accelerators: object | None = None) -> dict[str, object]:
    spec: dict[str, object] = {
        "topology": topology,
        "k3s_version": "v1.32.3+k3s1",
        "server": {"name": "server", "ip": "192.168.1.10"},
    }
    if accelerators is not None:
        spec["accelerators"] = accelerators
    if topology == "pxe-diskless":
        spec["network"] = {"interface": "enp1s0", "subnet": "192.168.1.0/24"}
        spec["pxe"] = {"authorized_keys": ["ssh-ed25519 AAAA test@example"], "diskless_agents_have_amd_gpus": False}
    return spec


def test_generator_validates_all_pxe_requirements_before_writing(tmp_path: Path) -> None:
    spec = generator_spec("pxe-diskless")
    spec["pxe"] = {"authorized_keys": [], "diskless_agents_have_amd_gpus": False}
    spec_path = write_file(tmp_path / "spec.json", json.dumps(spec))
    out_dir = tmp_path / "generated"

    result = run_script(GEN_CONFIGS, "--spec", str(spec_path), "--out-dir", str(out_dir))

    assert result.returncode == 1
    assert "pxe.authorized_keys must contain at least one SSH public key" in result.stderr
    assert not out_dir.exists()


def test_generator_rejects_non_mapping_known_accelerator_config_before_writing(tmp_path: Path) -> None:
    spec_path = write_file(tmp_path / "spec.json", json.dumps(generator_spec(accelerators={"9070xt": []})))
    out_dir = tmp_path / "generated"

    result = run_script(GEN_CONFIGS, "--spec", str(spec_path), "--out-dir", str(out_dir))

    assert result.returncode == 1
    assert "accelerators.9070xt must be a mapping" in result.stderr
    assert not out_dir.exists()


def test_generator_preflights_second_destination_collisions_before_writing(tmp_path: Path) -> None:
    spec_path = write_file(tmp_path / "spec.json", json.dumps(generator_spec("pxe-diskless")))
    out_dir = tmp_path / "generated"
    write_file(out_dir / "pb-pxe-controller.vars.yml", "existing\n")

    result = run_script(GEN_CONFIGS, "--spec", str(spec_path), "--out-dir", str(out_dir))

    assert result.returncode == 1
    assert "refusing to overwrite existing" in result.stderr
    assert not (out_dir / "inventory.yml").exists()


def test_generator_preflights_third_destination_collisions_before_writing(tmp_path: Path) -> None:
    spec_path = write_file(tmp_path / "spec.json", json.dumps(generator_spec("pxe-diskless")))
    out_dir = tmp_path / "generated"
    write_file(out_dir / "values-basic-example.yaml", "existing\n")

    result = run_script(GEN_CONFIGS, "--spec", str(spec_path), "--out-dir", str(out_dir))

    assert result.returncode == 1
    assert "refusing to overwrite existing" in result.stderr
    assert not (out_dir / "inventory.yml").exists()
    assert not (out_dir / "pb-pxe-controller.vars.yml").exists()


def test_generator_refuses_dangling_symlink_destinations_without_partial_artifacts(tmp_path: Path) -> None:
    spec_path = write_file(tmp_path / "spec.json", json.dumps(generator_spec()))
    out_dir = tmp_path / "generated"
    dangling_target = tmp_path / "missing-target"
    out_dir.mkdir()
    (out_dir / "inventory.yml").symlink_to(dangling_target)

    result = run_script(GEN_CONFIGS, "--spec", str(spec_path), "--out-dir", str(out_dir))

    assert result.returncode == 1
    assert "refusing to overwrite existing" in result.stderr
    assert (out_dir / "inventory.yml").is_symlink()
    assert not dangling_target.exists()
    assert not (out_dir / "values-basic-example.yaml").exists()


def test_generator_publishes_secret_and_public_artifacts_with_expected_modes(tmp_path: Path) -> None:
    spec_path = write_file(tmp_path / "spec.json", json.dumps(generator_spec("pxe-diskless")))
    out_dir = tmp_path / "generated"

    result = run_script(GEN_CONFIGS, "--spec", str(spec_path), "--out-dir", str(out_dir))

    assert result.returncode == 0, result.stdout + result.stderr
    assert os.stat(out_dir / "inventory.yml").st_mode & 0o777 == 0o600
    assert os.stat(out_dir / "pb-pxe-controller.vars.yml").st_mode & 0o777 == 0o600
    assert os.stat(out_dir / "values-basic-example.yaml").st_mode & 0o777 == 0o644


def test_generator_force_replaces_symlink_entry_without_following_target(tmp_path: Path) -> None:
    spec_path = write_file(tmp_path / "spec.json", json.dumps(generator_spec()))
    out_dir = tmp_path / "generated"
    target = write_file(tmp_path / "target-values.yaml", "keep-this-target\n")
    out_dir.mkdir()
    (out_dir / "values-basic-example.yaml").symlink_to(target)

    result = run_script(GEN_CONFIGS, "--spec", str(spec_path), "--out-dir", str(out_dir), "--force")

    published = out_dir / "values-basic-example.yaml"
    assert result.returncode == 0, result.stdout + result.stderr
    assert not published.is_symlink()
    assert target.read_text(encoding="utf-8") == "keep-this-target\n"
    assert "Helm overlay generated" in published.read_text(encoding="utf-8")


def test_generator_force_failure_restores_all_original_destination_types(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_deploy_module("deploy_artifact_store", ARTIFACT_STORE)
    inventory = write_file(tmp_path / "inventory.yml", "old inventory\n")
    pxe_vars = tmp_path / "pb-pxe-controller.vars.yml"
    pxe_vars.mkdir()
    write_file(pxe_vars / "legacy", "old directory\n")
    values_target = write_file(tmp_path / "values-target.yml", "old symlink target\n")
    values = tmp_path / "values-basic-example.yaml"
    values.symlink_to(values_target)
    artifacts = [
        (inventory, "new inventory\n", 0o600, True),
        (pxe_vars, "new pxe vars\n", 0o600, False),
        (values, "new values\n", 0o644, False),
    ]
    original_replace = module.os.replace

    def fail_late_replace(source, destination):
        if Path(destination).name == "values-basic-example.yaml" and ".backup." not in Path(source).name:
            raise OSError("injected late publish failure")
        return original_replace(source, destination)

    monkeypatch.setattr(module.os, "replace", fail_late_replace)

    with pytest.raises(SystemExit):
        module.publish_artifacts(artifacts, force=True)

    assert inventory.read_text(encoding="utf-8") == "old inventory\n"
    assert pxe_vars.is_dir()
    assert (pxe_vars / "legacy").read_text(encoding="utf-8") == "old directory\n"
    assert values.is_symlink()
    assert values_target.read_text(encoding="utf-8") == "old symlink target\n"


def test_artifact_store_rolls_back_non_force_destination_after_post_link_fsync_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_deploy_module("deploy_artifact_store_nonforce_fsync", ARTIFACT_STORE)
    destination = tmp_path / "inventory.yml"
    original_fsync_parent = module._fsync_parent
    calls = 0

    def fail_after_publication(path: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("injected parent fsync failure")
        original_fsync_parent(path)

    monkeypatch.setattr(module, "_fsync_parent", fail_after_publication)

    with pytest.raises(SystemExit):
        module.publish_artifacts([(destination, "new inventory\n", 0o600, True)], force=False)

    assert not destination.exists()


def test_generated_overlay_activates_selected_accelerators_for_validation(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    base_values = write_file(
        repo / "runtime/values.yaml",
        """custom:
  accelerators:
    strix-halo:
      nodeSelector:
        amd.com/gpu.product-name: AMD_Radeon_8060S_Graphics
    9070xt:
      nodeSelector:
        amd.com/gpu.product-name: AMD_Radeon_RX_9070_XT
  resources:
    metadata:
      gpu:
        acceleratorKeys: [strix-halo]
""",
    )
    spec_path = write_file(
        repo / "spec.json",
        json.dumps(generator_spec(accelerators={"9070xt": {"product_name": "AMD_Radeon_RX_9070_XT"}})),
    )
    generated = repo / "generated"
    generation = run_script(GEN_CONFIGS, "--spec", str(spec_path), "--out-dir", str(generated))
    cluster = write_cluster(repo, ["AMD_Radeon_RX_9070_XT"])

    validation = run_script(
        VALIDATE,
        "--repo",
        str(repo),
        "--topology",
        "ssh-preinstalled",
        "--values",
        str(base_values),
        "--values",
        str(generated / "values-basic-example.yaml"),
        "--cluster",
        str(cluster),
    )

    assert generation.returncode == 0, generation.stdout + generation.stderr
    assert validation.returncode == 0, validation.stdout + validation.stderr
    assert "AMD_Radeon_RX_9070_XT" in validation.stdout
    assert "AMD_Radeon_8060S_Graphics" not in validation.stdout


def test_checkout_root_helper_path_is_a_runnable_public_cli() -> None:
    result = run_script(GEN_CONFIGS, "--print-schema", cwd=ROOT)

    assert result.returncode == 0, result.stdout + result.stderr
    assert '"topology": "pxe-diskless | ssh-preinstalled"' in result.stdout
