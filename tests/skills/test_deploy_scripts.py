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

ROOT = Path(__file__).resolve().parents[2]
DEPLOY_SCRIPTS = ROOT / "skills" / "deploy-aup-learning-cloud" / "scripts"
VALIDATE = DEPLOY_SCRIPTS / "validate.py"
GEN_CONFIGS = DEPLOY_SCRIPTS / "gen_configs.py"
CONFIG_GENERATION = DEPLOY_SCRIPTS / "config_generation.py"
ARTIFACT_STORE = DEPLOY_SCRIPTS / "artifact_store.py"
VALUES_RESOLUTION_PARSING = DEPLOY_SCRIPTS / "values_resolution_parsing.py"

EXPECTED_GENERATOR_SCHEMA = {
    "topology": "pxe-diskless | ssh-preinstalled",
    "k3s_version": "v1.32.3+k3s1",
    "server": {"name": "aipc1", "ip": "192.168.0.140"},
    "agents": [{"name": "aipc2", "ip": "192.168.0.141"}],
    "network": {
        "interface": "enp1s0",
        "subnet": "192.168.0.0/24",
        "gateway": "192.168.0.1",
        "dns_servers": "8.8.8.8,8.8.4.4",
    },
    "pxe": {
        "authorized_keys": ["ssh-ed25519 AAAA... you@host"],
        "rootfs_password": "",
        "web_port": 8080,
        "diskless_agents_have_amd_gpus": True,
    },
    "accelerators": {"strix-halo": {"product_name": "AMD_Radeon_8060S_Graphics"}},
    "storage": {"class": "nfs-client"},
    "proxy": {"node_port": 30890},
    "auth_mode": "auto-login",
    "images": {"cpu": "ghcr.io/amdresearch/auplc-default:latest", "gpu": "ghcr.io/amdresearch/auplc-base:latest"},
}


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
    'version': 2,
    'hosts': [{
        'host': host,
        'reachable': True,
        'lspci': {'rc': 0, 'stdout': ''},
        'sysfs': {'rc': 0, 'stdout': ''},
        'render_group': {'rc': 0, 'stdout': 'render:x:993:\\n'},
        'groups': {'rc': 0, 'stdout': 'render:x:993:\\n'},
        'state': {'stat_success': True, 'content_success': True, 'exists': False, 'regular': False, 'symlink': False, 'content': ''},
        'rule': {'stat_success': True, 'content_success': True, 'exists': False, 'regular': False, 'symlink': False, 'content': ''},
        'legacy_rules': {
            key: {'stat_success': True, 'content_success': True, 'exists': False, 'regular': False, 'symlink': False, 'content': ''}
            for key in ('kfd', 'amdgpu', 'rocm_devices')
        },
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
  vars:
    auplc_render_gid: 993
""",
    )
    values = write_file(
        repo / "generated/values-basic-example.yaml",
        """custom:
  gpuAccess:
    renderGid: 993
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
                "render_gid": 993,
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


def test_values_resolution_parser_preserves_overlay_precedence_and_error_categories(tmp_path: Path) -> None:
    parser = load_deploy_module("values_resolution_parsing", VALUES_RESOLUTION_PARSING)
    repo = tmp_path / "checkout"
    base = write_file(
        repo / "base.yaml",
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
    partial_overlay = write_file(
        repo / "partial.yaml",
        """custom:
  accelerators:
    strix-halo:
      displayName: Renamed
""",
    )
    invalid_overlay = write_file(repo / "invalid.yaml", "custom: *defaults\n")

    result = parser.collect_effective_values(
        repo,
        [str(base), str(partial_overlay), "missing.yaml", str(invalid_overlay)],
    )

    assert result.accelerators == {"strix-halo": "AMD_Radeon_8060S_Graphics"}
    assert result.metadata == {"gpu": ["strix-halo"]}
    assert result.missing_files == ["values file not found: missing.yaml"]
    assert result.parse_errors == ["unsupported YAML syntax at custom"]


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


def test_validator_preserves_explicit_selector_and_accelerator_key_clears(tmp_path: Path) -> None:
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
    selector_clear = write_file(
        repo / "selector-clear.yaml",
        """custom:
  accelerators:
    strix-halo:
      nodeSelector:
        amd.com/gpu.product-name: null
""",
    )
    keys_clear = write_file(
        repo / "keys-clear.yaml",
        """custom:
  resources:
    metadata:
      gpu:
        acceleratorKeys: ~
""",
    )

    selector_result = run_script(
        VALIDATE,
        "--repo",
        str(repo),
        "--topology",
        "ssh-preinstalled",
        "--values",
        str(base),
        "--values",
        str(selector_clear),
    )
    keys_result = run_script(
        VALIDATE,
        "--repo",
        str(repo),
        "--topology",
        "ssh-preinstalled",
        "--values",
        str(base),
        "--values",
        str(keys_clear),
    )

    assert selector_result.returncode == 1
    assert "active accelerator 'strix-halo' has no amd.com/gpu.product-name nodeSelector" in selector_result.stdout
    assert keys_result.returncode == 0, keys_result.stdout + keys_result.stderr
    assert "no acceleratorKeys found" in keys_result.stdout


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


def test_validator_requires_product_labels_under_active_accelerator_node_selectors(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    values = write_file(
        repo / "runtime/values.yaml",
        """custom:
  accelerators:
    strix-halo:
      env:
        amd.com/gpu.product-name: AMD_Radeon_8060S_Graphics
  resources:
    metadata:
      gpu:
        acceleratorKeys: [strix-halo]
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


def test_validator_accepts_consistent_cpu_only_gpu_artifacts(tmp_path: Path) -> None:
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
      hosts:
        agent:
          ansible_host: 192.168.1.11
          auplc_gpu_access_enabled: false
  vars:
    auplc_render_gid: null
""",
    )
    values = write_file(
        repo / "generated/values-basic-example.yaml",
        """custom:
  gpuAccess:
    renderGid: null
  resources:
    metadata: {}
""",
    )
    resolution = write_file(
        repo / "generated/gpu-access-resolution.json",
        json.dumps(
            {
                "version": 1,
                "status": "cpu_only",
                "render_gid": None,
                "hosts": {"agent": False, "server": False},
            }
        ),
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

    assert result.returncode == 0, result.stdout + result.stderr
    assert "GPU access artifacts agree" in result.stdout


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
            '{"version":1,"status":"pending","render_gid":993,"hosts":{"agent":false,"server":true}}',
            "GPU resolution manifest status must be cpu_only or gpu_resolved",
        ),
        (
            '{"version":1,"status":"gpu_resolved","render_gid":993,"hosts":{"server":true,"server":false}}',
            "duplicate JSON key 'server'",
        ),
        (
            '{"version":1,"status":"gpu_resolved","render_gid":993,"hosts":{"ser\\u0076er":true,"server":false}}',
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


@pytest.mark.parametrize(
    ("inventory_content", "expected_error"),
    [
        (
            """k3s_cluster:
  children:
    server:
      hosts:
        server:
          ansible_host: 192.168.1.10
    agent:
      hosts:
        agent:
          ansible_host: 192.168.1.11
          auplc_gpu_access_enabled: false
  vars:
    auplc_render_gid: 993
""",
            "inventory host 'server' must define exactly one auplc_gpu_access_enabled",
        ),
        (
            """k3s_cluster:
  children:
    server:
      hosts:
        server:
          ansible_host: 192.168.1.10
          auplc_gpu_access_enabled: yes
    agent:
      hosts:
        agent:
          ansible_host: 192.168.1.11
          auplc_gpu_access_enabled: false
  vars:
    auplc_render_gid: 993
""",
            "inventory host 'server' has malformed auplc_gpu_access_enabled",
        ),
        (
            """k3s_cluster:
  children:
    server:
      hosts:
        server:
          ansible_host: 192.168.1.10
          auplc_gpu_access_enabled: true
          auplc_gpu_access_enabled: false
    agent:
      hosts:
        agent:
          ansible_host: 192.168.1.11
          auplc_gpu_access_enabled: false
  vars:
    auplc_render_gid: 993
""",
            "inventory host 'server' must define exactly one auplc_gpu_access_enabled",
        ),
    ],
)
def test_validator_rejects_missing_malformed_or_duplicate_inventory_host_booleans(
    tmp_path: Path, inventory_content: str, expected_error: str
) -> None:
    repo = tmp_path / "checkout"
    inventory, values, resolution = write_resolved_gpu_artifacts(repo)
    inventory.write_text(inventory_content, encoding="utf-8")

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


def test_validator_rejects_mismatched_host_boolean_and_render_gid(tmp_path: Path) -> None:
    repo = tmp_path / "checkout"
    inventory, values, resolution = write_resolved_gpu_artifacts(repo)
    values.write_text(
        """custom:
  gpuAccess:
    renderGid: 994
  resources:
    metadata: {}
""",
        encoding="utf-8",
    )
    resolution.write_text(
        json.dumps(
            {
                "version": 1,
                "status": "gpu_resolved",
                "render_gid": 993,
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
    assert "render GIDs disagree" in result.stdout


def test_validator_rejects_pxe_rootfs_boolean_and_gid_mismatch(tmp_path: Path) -> None:
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
  vars:
    auplc_render_gid: 993
""",
    )
    values = write_file(repo / "generated/values-basic-example.yaml", "custom:\n  gpuAccess:\n    renderGid: 993\n")
    resolution = write_file(
        repo / "generated/gpu-access-resolution.json",
        json.dumps(
            {
                "version": 1,
                "status": "gpu_resolved",
                "render_gid": 993,
                "hosts": {"server": False},
                "pxe_rootfs": {"gpu_access_enabled": True, "render_gid": 993},
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
auplc_render_gid: 994
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
    assert "PXE auplc_render_gid disagrees" in result.stdout


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


def test_artifact_store_rolls_back_destination_when_staged_unlink_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = load_deploy_module("deploy_artifact_store_unlink", ARTIFACT_STORE)
    destination = tmp_path / "inventory.yml"
    original_unlink = module.os.unlink
    failed = False

    def fail_first_staged_unlink(path, *args, **kwargs):
        nonlocal failed
        if not failed and Path(path).name.startswith(".inventory.yml."):
            failed = True
            raise OSError("injected staged unlink failure")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(module.os, "unlink", fail_first_staged_unlink)

    with pytest.raises(SystemExit):
        module.publish_artifacts([(destination, "new inventory\n", 0o600, True)], force=False)

    assert not destination.exists()


@pytest.mark.parametrize("force", (False, True))
def test_artifact_store_rolls_back_destination_when_parent_fsync_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, force: bool
) -> None:
    module = load_deploy_module(f"deploy_artifact_store_fsync_{force}", ARTIFACT_STORE)
    destination = tmp_path / "inventory.yml"
    if force:
        destination.write_text("old inventory\n", encoding="utf-8")
    original_fsync_parent = module._fsync_parent
    calls = 0

    def fail_after_publication(path):
        nonlocal calls
        calls += 1
        if calls == (2 if force else 1):
            raise OSError("injected parent fsync failure")
        return original_fsync_parent(path)

    monkeypatch.setattr(module, "_fsync_parent", fail_after_publication)

    with pytest.raises(SystemExit):
        module.publish_artifacts([(destination, "new inventory\n", 0o600, True)], force=force)

    if force:
        assert destination.read_text(encoding="utf-8") == "old inventory\n"
    else:
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


def test_generator_print_schema_is_byte_stable() -> None:
    result = run_script(GEN_CONFIGS, "--print-schema")

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == ""
    assert result.stdout == json.dumps(EXPECTED_GENERATOR_SCHEMA, indent=2) + "\n"


def test_generator_exits_with_usage_error_when_spec_is_omitted() -> None:
    result = run_script(GEN_CONFIGS)

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "gen_configs: --spec is required (or use --print-schema)\n"


def test_generator_replaces_colliding_artifacts_when_force_is_given(tmp_path: Path) -> None:
    spec_path = write_file(tmp_path / "spec.json", json.dumps(generator_spec("pxe-diskless")))
    token_path = write_file(tmp_path / "token.txt", "characterization-token\n")
    out_dir = tmp_path / "generated"
    write_file(out_dir / "inventory.yml", "old inventory\n")
    write_file(out_dir / "pb-pxe-controller.vars.yml", "old pxe vars\n")
    write_file(out_dir / "values-basic-example.yaml", "old values\n")

    result = run_script(
        GEN_CONFIGS,
        "--spec",
        str(spec_path),
        "--out-dir",
        str(out_dir),
        "--token-file",
        str(token_path),
        "--force",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "old inventory" not in (out_dir / "inventory.yml").read_text(encoding="utf-8")
    assert "old pxe vars" not in (out_dir / "pb-pxe-controller.vars.yml").read_text(encoding="utf-8")
    assert "old values" not in (out_dir / "values-basic-example.yaml").read_text(encoding="utf-8")
    assert os.stat(out_dir / "inventory.yml").st_mode & 0o777 == 0o600
    assert os.stat(out_dir / "pb-pxe-controller.vars.yml").st_mode & 0o777 == 0o600
    assert os.stat(out_dir / "values-basic-example.yaml").st_mode & 0o777 == 0o644


def test_generator_exposes_extracted_generation_and_artifact_modules() -> None:
    generation = load_deploy_module("deploy_config_generation", CONFIG_GENERATION)
    artifacts = load_deploy_module("deploy_artifact_store", ARTIFACT_STORE)

    assert generation.SCHEMA == EXPECTED_GENERATOR_SCHEMA
    assert generation.validate_spec(generator_spec()) == "ssh-preinstalled"
    assert callable(generation.render_inventory)
    assert callable(generation.render_pxe_vars)
    assert callable(generation.render_values)
    assert callable(artifacts.preflight_destinations)
    assert callable(artifacts.publish_artifacts)


def test_generator_rejects_legacy_public_gpu_policy_fields_before_discovery(tmp_path: Path) -> None:
    spec = generator_spec()
    spec["render_gid"] = 1055
    spec["gpu_access"] = {"hosts": [], "pxe_rootfs_enabled": False}
    spec_path = write_file(tmp_path / "spec.json", json.dumps(spec))
    out_dir = tmp_path / "generated"

    result = run_script(GEN_CONFIGS, "--spec", str(spec_path), "--out-dir", str(out_dir))

    assert result.returncode == 1
    assert "spec.render_gid is no longer accepted" in result.stderr
    assert not out_dir.exists()


def test_generator_uses_fake_ansible_discovery_to_publish_resolved_ssh_policy(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_ansible = fake_bin / "ansible-playbook"
    fake_ansible.write_text(
        r"""#!/usr/bin/env python3
import json
import pathlib
import sys
args = sys.argv[1:]
output = next(arg.split('=', 1)[1] for arg in args if arg.startswith('gpu_access_discovery_output_path='))
def host(name, bdf):
    return {
        'host': name, 'reachable': True,
        'lspci': {'rc': 0, 'stdout': bdf}, 'sysfs': {'rc': 0, 'stdout': bdf},
        'render_group': {'rc': 0, 'stdout': 'render:x:993:\\n'},
        'groups': {'rc': 0, 'stdout': 'render:x:993:\\n'},
        'state': {'stat_success': True, 'content_success': True, 'exists': False, 'regular': False, 'symlink': False, 'content': ''},
        'rule': {'stat_success': True, 'content_success': True, 'exists': False, 'regular': False, 'symlink': False, 'content': ''},
        'legacy_rules': {key: {'stat_success': True, 'content_success': True, 'exists': False, 'regular': False, 'symlink': False, 'content': ''} for key in ('kfd', 'amdgpu', 'rocm_devices')},
    }
pathlib.Path(output).write_text(json.dumps({'version': 2, 'hosts': [host('server', '0000:03:00.0'), host('agent', '')]}), encoding='utf-8')
""",
        encoding="utf-8",
    )
    fake_ansible.chmod(0o755)
    spec = generator_spec()
    spec["agents"] = [{"name": "agent", "ip": "192.168.1.11"}]
    spec_path = write_file(tmp_path / "spec.json", json.dumps(spec))
    out_dir = tmp_path / "generated"
    result = subprocess.run(
        [sys.executable, str(GEN_CONFIGS), "--spec", str(spec_path), "--out-dir", str(out_dir)],
        capture_output=True,
        check=False,
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    inventory = (out_dir / "inventory.yml").read_text(encoding="utf-8")
    assert "auplc_render_gid: 993" in inventory
    assert inventory.count("auplc_gpu_access_enabled: true") == 1
    assert inventory.count("auplc_gpu_access_enabled: false") == 1
    assert "renderGid: 993" in (out_dir / "values-basic-example.yaml").read_text(encoding="utf-8")
    manifest = json.loads((out_dir / "gpu-access-resolution.json").read_text(encoding="utf-8"))
    assert manifest["hosts"] == {"agent": False, "server": True}
