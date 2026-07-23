# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import auplc_installer.pack as pack
from auplc_installer.catalog import CourseSelection
from auplc_installer.gpu import GpuConfig, append_product
from auplc_installer.pack import (
    _copy_installer_payload,
    pack_save_custom_images_local,
    pack_save_custom_images_pull,
)

ROOT = Path(__file__).resolve().parents[2]


def _gfx1200_config() -> GpuConfig:
    cfg = GpuConfig()
    append_product(cfg, "AMD_Radeon_RX_9060")
    return cfg


def _gfx1103_config() -> GpuConfig:
    cfg = GpuConfig()
    append_product(cfg, "AMD_Radeon_780M_Graphics")
    return cfg


def _docker_save_references(calls: list[list[str]]) -> list[str]:
    command = next(call for call in calls if call[:2] == ["docker", "save"])
    return command[2 : command.index("-o")]


def test_local_pack_saves_only_profile_specific_gpu_tags(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr("auplc_installer.pack.run", lambda command, **_: calls.append(command))
    monkeypatch.setattr("auplc_installer.pack.run_streaming", lambda command, **_: calls.append(command))

    pack_save_custom_images_local(
        tmp_path,
        cfg=_gfx1200_config(),
        courses=CourseSelection(picks=["gpu", "code-gpu"]),
        image_registry="ghcr.io/example",
        image_tag="v1",
        mirror_prefix="",
        mirror_pip="",
        mirror_npm="",
    )

    references = _docker_save_references(calls)
    assert "ghcr.io/example/auplc-base:v1-gfx1200" in references
    assert "ghcr.io/example/auplc-code-gpu:v1-gfx1200" in references
    assert "ghcr.io/example/auplc-base:latest" not in references
    assert "ghcr.io/example/auplc-code-gpu:latest" not in references


def test_pull_pack_saves_restored_phx_profile_tags(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr("auplc_installer.pack.pull_and_tag", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("auplc_installer.pack.run", lambda command, **_: calls.append(command))

    pack_save_custom_images_pull(
        tmp_path,
        cfg=_gfx1103_config(),
        courses=CourseSelection(picks=["gpu", "code-gpu"]),
        image_registry="ghcr.io/example",
        image_tag="v1",
        mirror_prefix="",
    )

    references = _docker_save_references(calls)
    assert "ghcr.io/example/auplc-base:v1-gfx1103" in references
    assert "ghcr.io/example/auplc-code-gpu:v1-gfx1103" in references


def test_local_pack_retags_make_images_from_default_registry_to_custom_registry(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr("auplc_installer.pack.run", lambda command, **_: calls.append(command))
    monkeypatch.setattr("auplc_installer.pack.run_streaming", lambda command, **_: calls.append(command))

    pack_save_custom_images_local(
        tmp_path,
        cfg=_gfx1200_config(),
        courses=CourseSelection.default(),
        image_registry="registry.example/auplc",
        image_tag="v1",
        mirror_prefix="",
        mirror_pip="",
        mirror_npm="",
    )

    tag_calls = [call for call in calls if call[:2] == ["docker", "tag"]]
    assert [
        "docker",
        "tag",
        "ghcr.io/amdresearch/auplc-base:latest-gfx1200",
        "registry.example/auplc/auplc-base:v1-gfx1200",
    ] in tag_calls
    assert [
        "docker",
        "tag",
        "ghcr.io/amdresearch/auplc-code-gpu:latest-gfx1200",
        "registry.example/auplc/auplc-code-gpu:v1-gfx1200",
    ] in tag_calls
    assert [
        "docker",
        "tag",
        "ghcr.io/amdresearch/auplc-cv:latest-gfx1200",
        "registry.example/auplc/auplc-cv:v1-gfx1200",
    ] in tag_calls
    assert [
        "docker",
        "tag",
        "ghcr.io/amdresearch/auplc-default:latest",
        "registry.example/auplc/auplc-default:v1",
    ] in tag_calls
    assert [
        "docker",
        "tag",
        "ghcr.io/amdresearch/auplc-code-cpu:latest",
        "registry.example/auplc/auplc-code-cpu:v1",
    ] in tag_calls
    assert [
        "docker",
        "tag",
        "ghcr.io/amdresearch/auplc-hub:latest",
        "registry.example/auplc/auplc-hub:v1",
    ] in tag_calls

    references = _docker_save_references(calls)
    assert "registry.example/auplc/auplc-base:v1-gfx1200" in references
    assert "registry.example/auplc/auplc-code-gpu:v1-gfx1200" in references
    assert "registry.example/auplc/auplc-cv:v1-gfx1200" in references
    assert "registry.example/auplc/auplc-default:latest" in references
    assert "registry.example/auplc/auplc-default:v1" in references
    assert "registry.example/auplc/auplc-code-cpu:latest" in references
    assert "registry.example/auplc/auplc-code-cpu:v1" in references
    assert "registry.example/auplc/auplc-hub:latest" in references
    assert "registry.example/auplc/auplc-hub:v1" in references

    for call in tag_calls:
        assert call[2].startswith("ghcr.io/amdresearch/")


def test_local_pack_avoids_duplicate_custom_registry_latest_tag(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr("auplc_installer.pack.run", lambda command, **_: calls.append(command))
    monkeypatch.setattr("auplc_installer.pack.run_streaming", lambda command, **_: calls.append(command))

    pack_save_custom_images_local(
        tmp_path,
        cfg=_gfx1200_config(),
        courses=CourseSelection(picks=["none"]),
        image_registry="registry.example/auplc",
        image_tag="latest",
        mirror_prefix="",
        mirror_pip="",
        mirror_npm="",
    )

    hub_tag = [
        "docker",
        "tag",
        "ghcr.io/amdresearch/auplc-hub:latest",
        "registry.example/auplc/auplc-hub:latest",
    ]
    assert [call for call in calls if call == hub_tag] == [hub_tag]


def test_pull_pack_saves_only_profile_specific_gpu_tags(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr("auplc_installer.pack.pull_and_tag", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("auplc_installer.pack.run", lambda command, **_: calls.append(command))

    pack_save_custom_images_pull(
        tmp_path,
        cfg=_gfx1200_config(),
        courses=CourseSelection(picks=["gpu", "code-gpu"]),
        image_registry="ghcr.io/example",
        image_tag="v1",
        mirror_prefix="",
    )

    references = _docker_save_references(calls)
    assert "ghcr.io/example/auplc-base:v1-gfx1200" in references
    assert "ghcr.io/example/auplc-code-gpu:v1-gfx1200" in references
    assert "ghcr.io/example/auplc-base:latest" not in references
    assert "ghcr.io/example/auplc-code-gpu:latest" not in references


def test_offline_payload_includes_the_yaml_catalog_and_installer_requirements(tmp_path: Path) -> None:
    staging = tmp_path / "bundle"
    staging.mkdir()

    _copy_installer_payload(staging, source_root=ROOT)

    assert (staging / "auplc_installer" / "data" / "rocm-profiles.yaml").is_file()
    assert "PyYAML==6.0.3" in (staging / "requirements-installer.txt").read_text(encoding="utf-8")


def test_offline_payload_vendors_pure_python_pyyaml_for_an_isolated_launcher(tmp_path: Path) -> None:
    staging = tmp_path / "bundle"
    staging.mkdir()

    _copy_installer_payload(staging, source_root=ROOT)

    vendor = staging / "_vendor"
    assert (vendor / "yaml" / "__init__.py").is_file()
    assert not list((vendor / "yaml").glob("_yaml.*"))
    assert (staging / "third_party_licenses" / "PyYAML-LICENSE").is_file()
    environment = {key: value for key, value in os.environ.items() if key not in {"PYTHONHOME", "PYTHONPATH"}}
    environment["PYTHONNOUSERSITE"] = "1"
    result = subprocess.run(
        [sys.executable, "-S", str(staging / "auplc-installer"), "help"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Usage:" in result.stdout


def test_offline_payload_requires_the_installer_requirements_file(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    shutil.copy2(ROOT / "auplc-installer", source_root / "auplc-installer")
    shutil.copytree(ROOT / "auplc_installer", source_root / "auplc_installer")
    staging = tmp_path / "bundle"
    staging.mkdir()

    with pytest.raises(pack.InstallerError, match="requirements-installer.txt"):
        _copy_installer_payload(staging, source_root=source_root)


def test_pyyaml_license_path_prefers_distribution_metadata(monkeypatch, tmp_path: Path) -> None:
    metadata_license = tmp_path / "metadata-license"
    metadata_license.write_text("metadata", encoding="utf-8")
    fallback_license = tmp_path / "debian-copyright"
    fallback_license.write_text("fallback", encoding="utf-8")

    class Distribution:
        files = (Path("pyyaml-6.0.3.dist-info/licenses/LICENSE"),)

        @staticmethod
        def locate_file(_file: Path) -> Path:
            return metadata_license

    monkeypatch.setattr(pack.metadata, "distribution", lambda _name: Distribution())
    monkeypatch.setattr(pack, "PY_YAML_SYSTEM_LICENSE_CANDIDATES", (fallback_license,), raising=False)

    assert pack._pyyaml_license_path() == metadata_license


def test_pyyaml_license_path_uses_debian_fallback_when_distribution_metadata_is_missing(
    monkeypatch, tmp_path: Path
) -> None:
    fallback_license = tmp_path / "copyright"
    fallback_license.write_text("debian", encoding="utf-8")

    def missing_distribution(_name: str):
        raise pack.metadata.PackageNotFoundError

    monkeypatch.setattr(pack.metadata, "distribution", missing_distribution)
    monkeypatch.setattr(pack, "PY_YAML_SYSTEM_LICENSE_CANDIDATES", (fallback_license,), raising=False)

    assert pack._pyyaml_license_path() == fallback_license


def test_pyyaml_license_path_returns_none_when_metadata_and_explicit_fallback_are_unavailable(
    monkeypatch, tmp_path: Path
) -> None:
    def missing_distribution(_name: str):
        raise pack.metadata.PackageNotFoundError

    monkeypatch.setattr(pack.metadata, "distribution", missing_distribution)
    monkeypatch.setattr(
        pack,
        "PY_YAML_SYSTEM_LICENSE_CANDIDATES",
        (tmp_path / "does-not-exist",),
        raising=False,
    )

    assert pack._pyyaml_license_path() is None


@pytest.mark.parametrize(
    ("attribute", "message"),
    [
        ("_pyyaml_package_path", "PyYAML package"),
        ("_pyyaml_license_path", "PyYAML license"),
    ],
)
def test_offline_payload_requires_pyyaml_package_and_license(
    monkeypatch, tmp_path: Path, attribute: str, message: str
) -> None:
    monkeypatch.setattr(pack, attribute, lambda: None, raising=False)
    staging = tmp_path / "bundle"
    staging.mkdir()

    with pytest.raises(pack.InstallerError, match=message):
        _copy_installer_payload(staging, source_root=ROOT)
