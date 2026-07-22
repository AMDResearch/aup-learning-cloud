# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

from __future__ import annotations

from pathlib import Path

from auplc_installer.catalog import CourseSelection
from auplc_installer.gpu import GpuConfig, append_product
from auplc_installer.pack import pack_save_custom_images_local, pack_save_custom_images_pull


def _gfx1200_config() -> GpuConfig:
    cfg = GpuConfig()
    append_product(cfg, "AMD_Radeon_RX_9060")
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
