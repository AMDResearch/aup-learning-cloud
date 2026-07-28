from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GEN_CONFIGS = ROOT / "skills" / "deploy-aup-learning-cloud" / "scripts" / "gen_configs.py"
PXE_PLAYBOOK = ROOT / "deploy" / "ansible" / "playbooks" / "pb-pxe-controller.yml"


def pxe_spec(gpu_agents: bool) -> dict:
    return {
        "topology": "pxe-diskless",
        "k3s_version": "v1.32.3+k3s1",
        "server": {"name": "controller", "ip": "192.168.1.10"},
        "agents": [{"name": "diskless-agent", "ip": "192.168.1.11"}],
        "network": {"interface": "enp1s0", "subnet": "192.168.1.0/24"},
        "pxe": {
            "authorized_keys": ["ssh-ed25519 AAAA test@example"],
            "rootfs_password": "do-not-print-this-secret",
            "diskless_agents_have_amd_gpus": gpu_agents,
        },
    }


def write_json(path: Path, document: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def write_fake_ansible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, controller_gpu: bool = False) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_ansible = fake_bin / "ansible-playbook"
    bdf = "0000:03:00.0" if controller_gpu else ""
    fake_ansible.write_text(
        f"""#!/usr/bin/env python3
import json
import sys
from pathlib import Path

output = next(value.split('=', 1)[1] for value in sys.argv if value.startswith('gpu_access_discovery_output_path='))
Path(output).write_text(json.dumps({{
    'version': 2,
    'hosts': [{{
        'host': 'controller', 'reachable': True,
        'lspci': {{'rc': 0, 'stdout': {bdf!r}}},
        'sysfs': {{'rc': 0, 'stdout': {bdf!r}}},
        'render_group': {{'rc': 0, 'stdout': 'render:x:993\\n'}},
        'groups': {{'rc': 0, 'stdout': 'render:x:993\\n'}},
        'state': {{'stat_success': True, 'content_success': True, 'exists': False, 'regular': False, 'symlink': False, 'content': ''}},
        'rule': {{'stat_success': True, 'content_success': True, 'exists': False, 'regular': False, 'symlink': False, 'content': ''}},
        'legacy_rules': {{key: {{'stat_success': True, 'content_success': True, 'exists': False, 'regular': False, 'symlink': False, 'content': ''}} for key in ('kfd', 'amdgpu', 'rocm_devices')}},
    }}],
}}), encoding='utf-8')
""",
        encoding="utf-8",
    )
    fake_ansible.chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")


def run_generator(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GEN_CONFIGS), *arguments],
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )


def load_finalizer_module():
    scripts = GEN_CONFIGS.parent
    sys.path.insert(0, str(scripts))
    try:
        spec = spec_from_file_location("test_pxe_finalizer", scripts / "pxe_finalization.py")
        assert spec is not None and spec.loader is not None
        module = module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


def pending_handoff(out_dir: Path, *, render_gid: int = 995) -> tuple[Path, Path]:
    context_path = out_dir / ".pxe-finalizer-context.json"
    context = json.loads(context_path.read_text(encoding="utf-8"))
    handoff_path = out_dir / ".pxe-finalizer-handoff.json"
    write_json(
        handoff_path,
        {
            "version": 1,
            "generation": context["generation"],
            "spec_sha256": context["spec_sha256"],
            "topology": "pxe-diskless",
            "pxe_gpu_access_enabled": True,
            "render_gid": render_gid,
        },
    )
    return context_path, handoff_path


def canonical_artifacts(out_dir: Path) -> tuple[Path, ...]:
    return (
        out_dir / "inventory.yml",
        out_dir / "pb-pxe-controller.vars.yml",
        out_dir / "values-basic-example.yaml",
        out_dir / "gpu-access-resolution.json",
        out_dir / ".pxe-finalizer-completion.json",
    )


def cpu_controller(finalizer):
    return finalizer.FleetResolution(
        finalizer.FleetStatus.CPU_ONLY,
        (finalizer.HostResolution(finalizer._target("controller"), finalizer.HostStatus.CPU, None, None),),
        None,
        None,
    )


def test_pxe_finalizer_preserves_moved_imports_as_immutable_support_types(tmp_path: Path) -> None:
    finalizer = load_finalizer_module()
    support = sys.modules["pxe_finalization_support"]

    assert finalizer.FinalizationError is support.FinalizationError
    assert finalizer.PxePaths is support.PxePaths
    assert finalizer.paths is support.paths
    assert finalizer.VERSION == support.VERSION == 1
    assert finalizer.MAX_RENDER_GID == support.MAX_RENDER_GID == 4_294_967_294
    assert finalizer._read_document is support.read_document
    assert finalizer._generation_paths is support.generation_paths
    assert finalizer._artifact_attestations is support.artifact_attestations
    assert finalizer._completion is support.completion
    assert finalizer._verify_canonical_artifacts is support.verify_canonical_artifacts
    assert finalizer._exclusive_lock is support.exclusive_lock

    error = finalizer.FinalizationError("immutable")
    pending = finalizer.paths(tmp_path)
    with pytest.raises(FrozenInstanceError):
        error.reason = "changed"
    with pytest.raises(FrozenInstanceError):
        pending.context = tmp_path / "changed.json"


def test_pxe_gpu_agents_stage_only_private_bootstrap_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_fake_ansible(tmp_path, monkeypatch)
    spec_path = write_json(tmp_path / "spec.json", pxe_spec(True))
    out_dir = tmp_path / "generated"

    result = run_generator("--spec", str(spec_path), "--out-dir", str(out_dir))

    assert result.returncode == 0, result.stderr
    assert not (out_dir / "inventory.yml").exists()
    assert not (out_dir / "values-basic-example.yaml").exists()
    assert not (out_dir / "gpu-access-resolution.json").exists()
    assert "pxe_controller:" in (out_dir / ".pxe-bootstrap.inventory.yml").read_text(encoding="utf-8")
    bootstrap = (out_dir / ".pxe-bootstrap.vars.yml").read_text(encoding="utf-8")
    assert "pxe_gpu_access_enabled: true" in bootstrap
    assert "pxe_finalizer_context:" in bootstrap
    assert (out_dir / ".pxe-finalizer-context.json").stat().st_mode & 0o777 == 0o600


def test_pxe_cpu_agents_publish_a_disabled_rootfs_policy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_fake_ansible(tmp_path, monkeypatch)
    spec_path = write_json(tmp_path / "spec.json", pxe_spec(False))
    out_dir = tmp_path / "generated"

    result = run_generator("--spec", str(spec_path), "--out-dir", str(out_dir))

    assert result.returncode == 0, result.stderr
    assert "pxe_gpu_access_enabled: false" in (out_dir / "pb-pxe-controller.vars.yml").read_text(encoding="utf-8")
    assert "auplc_render_gid: null" in (out_dir / "inventory.yml").read_text(encoding="utf-8")
    manifest = json.loads((out_dir / "gpu-access-resolution.json").read_text(encoding="utf-8"))
    assert manifest["pxe_rootfs"] == {"gpu_access_enabled": False, "render_gid": None}


def test_pxe_disabled_rootfs_force_replaces_private_generation_state_under_the_generation_lock(tmp_path: Path) -> None:
    finalizer = load_finalizer_module()
    out_dir = tmp_path / "generated"
    pending = finalizer.paths(out_dir)
    for path in (
        pending.bootstrap_inventory,
        pending.bootstrap_vars,
        pending.context,
        pending.handoff,
        pending.completion,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("stale\n", encoding="utf-8")

    finalizer.publish_disabled_rootfs(pxe_spec(False), "token", cpu_controller(finalizer), out_dir, True)

    assert all(
        not path.exists()
        for path in (
            pending.bootstrap_inventory,
            pending.bootstrap_vars,
            pending.context,
            pending.handoff,
            pending.completion,
        )
    )
    assert all(path.exists() for path in canonical_artifacts(out_dir)[:-1])


def test_pxe_disabled_rootfs_force_restores_private_and_canonical_generation_when_publication_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    finalizer = load_finalizer_module()
    artifact_store = sys.modules["artifact_store"]
    out_dir = tmp_path / "generated"
    pending = finalizer.paths(out_dir)
    finalizer.publish_disabled_rootfs(pxe_spec(False), "old-token", cpu_controller(finalizer), out_dir, False)
    for path in (
        pending.bootstrap_inventory,
        pending.bootstrap_vars,
        pending.context,
        pending.handoff,
        pending.completion,
    ):
        path.write_text(f"old {path.name}\n", encoding="utf-8")
    tracked = (
        *canonical_artifacts(out_dir)[:-1],
        pending.bootstrap_inventory,
        pending.bootstrap_vars,
        pending.context,
        pending.handoff,
        pending.completion,
    )
    before = {path.name: path.read_bytes() for path in tracked}
    original_replace = artifact_store.os.replace

    def fail_values_replace(source, destination):
        if Path(destination) == pending.values and ".backup." not in str(source):
            raise OSError("injected disabled-rootfs publication failure")
        return original_replace(source, destination)

    monkeypatch.setattr(artifact_store.os, "replace", fail_values_replace)
    with pytest.raises(SystemExit):
        finalizer.publish_disabled_rootfs(pxe_spec(False), "new-token", cpu_controller(finalizer), out_dir, True)

    assert {path.name: path.read_bytes() for path in tracked} == before


def test_pxe_finalizer_publishes_resolved_policy_idempotently_without_secret_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_fake_ansible(tmp_path, monkeypatch)
    spec_path = write_json(tmp_path / "spec.json", pxe_spec(True))
    out_dir = tmp_path / "generated"
    pending = run_generator("--spec", str(spec_path), "--out-dir", str(out_dir))
    context, handoff = pending_handoff(out_dir)

    first = run_generator(
        "--finalize-pxe", "--out-dir", str(out_dir), "--context", str(context), "--handoff", str(handoff)
    )
    second = run_generator(
        "--finalize-pxe", "--out-dir", str(out_dir), "--context", str(context), "--handoff", str(handoff)
    )

    assert pending.returncode == 0, pending.stderr
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert "do-not-print-this-secret" not in first.stdout + first.stderr + second.stdout + second.stderr
    assert "auplc_render_gid: 995" in (out_dir / "inventory.yml").read_text(encoding="utf-8")
    assert "auplc_gpu_access_enabled: false" in (out_dir / "inventory.yml").read_text(encoding="utf-8")
    assert "renderGid: 995" in (out_dir / "values-basic-example.yaml").read_text(encoding="utf-8")
    manifest = json.loads((out_dir / "gpu-access-resolution.json").read_text(encoding="utf-8"))
    assert manifest["pxe_rootfs"] == {"gpu_access_enabled": True, "render_gid": 995}
    completion = json.loads((out_dir / ".pxe-finalizer-completion.json").read_text(encoding="utf-8"))
    assert completion["artifacts"]["inventory.yml"]["mode"] == 0o600
    assert completion["artifacts"]["inventory.yml"]["owner_uid"] == os.geteuid()


def test_pxe_finalizer_retry_rejects_canonical_mode_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_fake_ansible(tmp_path, monkeypatch)
    spec_path = write_json(tmp_path / "spec.json", pxe_spec(True))
    out_dir = tmp_path / "generated"
    assert run_generator("--spec", str(spec_path), "--out-dir", str(out_dir)).returncode == 0
    context, handoff = pending_handoff(out_dir)
    assert (
        run_generator(
            "--finalize-pxe", "--out-dir", str(out_dir), "--context", str(context), "--handoff", str(handoff)
        ).returncode
        == 0
    )
    (out_dir / "inventory.yml").chmod(0o644)

    result = run_generator(
        "--finalize-pxe", "--out-dir", str(out_dir), "--context", str(context), "--handoff", str(handoff)
    )

    assert result.returncode == 1


def test_pxe_pending_generation_rejects_existing_private_or_canonical_state_without_force(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_fake_ansible(tmp_path, monkeypatch)
    spec_path = write_json(tmp_path / "spec.json", pxe_spec(True))
    out_dir = tmp_path / "generated"
    assert run_generator("--spec", str(spec_path), "--out-dir", str(out_dir)).returncode == 0

    result = run_generator("--spec", str(spec_path), "--out-dir", str(out_dir))

    assert result.returncode == 1
    assert "refusing to overwrite" in result.stderr


def test_pxe_forced_pending_generation_hides_prior_public_and_private_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_fake_ansible(tmp_path, monkeypatch)
    spec_path = write_json(tmp_path / "spec.json", pxe_spec(True))
    out_dir = tmp_path / "generated"
    assert run_generator("--spec", str(spec_path), "--out-dir", str(out_dir)).returncode == 0
    context, handoff = pending_handoff(out_dir)
    assert (
        run_generator(
            "--finalize-pxe", "--out-dir", str(out_dir), "--context", str(context), "--handoff", str(handoff)
        ).returncode
        == 0
    )
    old_generation = json.loads(context.read_text(encoding="utf-8"))["generation"]

    result = run_generator("--spec", str(spec_path), "--out-dir", str(out_dir), "--force")

    assert result.returncode == 0, result.stderr
    assert json.loads(context.read_text(encoding="utf-8"))["generation"] != old_generation
    assert not handoff.exists()
    assert all(not path.exists() for path in canonical_artifacts(out_dir))


def test_pxe_forced_pending_generation_restores_prior_generation_if_staging_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_fake_ansible(tmp_path, monkeypatch)
    spec_path = write_json(tmp_path / "spec.json", pxe_spec(True))
    out_dir = tmp_path / "generated"
    assert run_generator("--spec", str(spec_path), "--out-dir", str(out_dir)).returncode == 0
    context, handoff = pending_handoff(out_dir)
    assert (
        run_generator(
            "--finalize-pxe", "--out-dir", str(out_dir), "--context", str(context), "--handoff", str(handoff)
        ).returncode
        == 0
    )
    previous = {path.name: path.read_bytes() for path in (*canonical_artifacts(out_dir), context, handoff)}
    finalizer = load_finalizer_module()
    artifact_store = sys.modules["artifact_store"]
    original_replace = artifact_store.os.replace

    def fail_new_bootstrap(source, destination):
        if Path(destination) == out_dir / ".pxe-bootstrap.inventory.yml" and ".backup." not in str(source):
            raise OSError("injected staging failure")
        return original_replace(source, destination)

    monkeypatch.setattr(artifact_store.os, "replace", fail_new_bootstrap)
    controller = finalizer._controller_resolution(
        pxe_spec(True), json.loads(context.read_text(encoding="utf-8"))["controller"]
    )
    with pytest.raises(SystemExit):
        finalizer.stage_pending(pxe_spec(True), "replacement-token", controller, out_dir, True)

    assert {path.name: path.read_bytes() for path in (*canonical_artifacts(out_dir), context, handoff)} == previous


@pytest.mark.parametrize("document_name", (".pxe-finalizer-context.json", ".pxe-finalizer-handoff.json"))
def test_pxe_finalizer_rejects_duplicate_keys_in_private_documents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, document_name: str
) -> None:
    write_fake_ansible(tmp_path, monkeypatch)
    spec_path = write_json(tmp_path / "spec.json", pxe_spec(True))
    out_dir = tmp_path / "generated"
    assert run_generator("--spec", str(spec_path), "--out-dir", str(out_dir)).returncode == 0
    context, handoff = pending_handoff(out_dir)
    document_path = out_dir / document_name
    document_path.write_text(
        '{"generation":"duplicate",' + document_path.read_text(encoding="utf-8")[1:], encoding="utf-8"
    )

    result = run_generator(
        "--finalize-pxe", "--out-dir", str(out_dir), "--context", str(context), "--handoff", str(handoff)
    )

    assert result.returncode == 1
    assert all(not path.exists() for path in canonical_artifacts(out_dir))


@pytest.mark.parametrize("mutation", ("missing", "tampered"))
def test_pxe_finalizer_retry_rejects_missing_or_tampered_canonical_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    write_fake_ansible(tmp_path, monkeypatch)
    spec_path = write_json(tmp_path / "spec.json", pxe_spec(True))
    out_dir = tmp_path / "generated"
    assert run_generator("--spec", str(spec_path), "--out-dir", str(out_dir)).returncode == 0
    context, handoff = pending_handoff(out_dir)
    assert (
        run_generator(
            "--finalize-pxe", "--out-dir", str(out_dir), "--context", str(context), "--handoff", str(handoff)
        ).returncode
        == 0
    )
    inventory = out_dir / "inventory.yml"
    if mutation == "missing":
        inventory.unlink()
    else:
        inventory.write_text("tampered\n", encoding="utf-8")

    result = run_generator(
        "--finalize-pxe", "--out-dir", str(out_dir), "--context", str(context), "--handoff", str(handoff)
    )

    assert result.returncode == 1


def test_pxe_finalizer_rejects_symlink_lock_without_touching_its_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_fake_ansible(tmp_path, monkeypatch)
    spec_path = write_json(tmp_path / "spec.json", pxe_spec(True))
    out_dir = tmp_path / "generated"
    assert run_generator("--spec", str(spec_path), "--out-dir", str(out_dir)).returncode == 0
    context, handoff = pending_handoff(out_dir)
    target = tmp_path / "lock-target"
    target.write_text("unchanged\n", encoding="utf-8")
    target.chmod(0o644)
    lock = out_dir / ".pxe-finalizer.lock"
    lock.unlink()
    lock.symlink_to(target)

    result = run_generator(
        "--finalize-pxe", "--out-dir", str(out_dir), "--context", str(context), "--handoff", str(handoff)
    )

    assert result.returncode == 1
    assert target.read_text(encoding="utf-8") == "unchanged\n"
    assert target.stat().st_mode & 0o777 == 0o644


@pytest.mark.parametrize(
    ("field", "value"),
    [("generation", "stale"), ("topology", "ssh-preinstalled"), ("render_gid", None), ("version", True)],
)
def test_pxe_finalizer_rejects_invalid_handoffs_without_publishing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: str | int | None
) -> None:
    write_fake_ansible(tmp_path, monkeypatch)
    spec_path = write_json(tmp_path / "spec.json", pxe_spec(True))
    out_dir = tmp_path / "generated"
    assert run_generator("--spec", str(spec_path), "--out-dir", str(out_dir)).returncode == 0
    context, handoff = pending_handoff(out_dir)
    document = json.loads(handoff.read_text(encoding="utf-8"))
    document[field] = value
    write_json(handoff, document)

    result = run_generator(
        "--finalize-pxe", "--out-dir", str(out_dir), "--context", str(context), "--handoff", str(handoff)
    )

    assert result.returncode == 1
    assert not (out_dir / "inventory.yml").exists()
    assert not (out_dir / "values-basic-example.yaml").exists()
    assert not (out_dir / "gpu-access-resolution.json").exists()


def test_pxe_finalizer_rolls_back_if_late_canonical_publication_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_fake_ansible(tmp_path, monkeypatch)
    spec_path = write_json(tmp_path / "spec.json", pxe_spec(True))
    out_dir = tmp_path / "generated"
    assert run_generator("--spec", str(spec_path), "--out-dir", str(out_dir)).returncode == 0
    context, handoff = pending_handoff(out_dir)
    finalizer = load_finalizer_module()
    artifact_store = sys.modules["artifact_store"]
    original_link = artifact_store.os.link

    def fail_values_link(source, destination):
        if Path(destination).name == "values-basic-example.yaml":
            raise OSError("injected publication failure")
        return original_link(source, destination)

    monkeypatch.setattr(artifact_store.os, "link", fail_values_link)
    with pytest.raises(SystemExit):
        finalizer.finalize(out_dir, context, handoff)

    assert not (out_dir / "inventory.yml").exists()
    assert not (out_dir / "pb-pxe-controller.vars.yml").exists()
    assert not (out_dir / "values-basic-example.yaml").exists()
    assert not (out_dir / "gpu-access-resolution.json").exists()
    assert not (out_dir / ".pxe-finalizer-completion.json").exists()


def test_pxe_playbook_writes_and_finalizes_private_rootfs_handoff_locally() -> None:
    playbook = PXE_PLAYBOOK.read_text(encoding="utf-8")

    assert "pxe_finalizer_handoff" in playbook
    assert "pxe_finalizer_context" in playbook
    assert "--finalize-pxe" in playbook
    assert "delegate_to: localhost" in playbook
    assert "run_once: true" in playbook
    assert "become: false" in playbook
    assert "argv:" in playbook
