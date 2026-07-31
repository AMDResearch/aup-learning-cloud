# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

"""Tests for offline bundle package artifacts."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from auplc_installer import pack
from auplc_installer.gpu_access import (
    AMD_GPU_UDEV_PACKAGE_FILENAME,
    AMD_GPU_UDEV_PACKAGE_SHA256,
    AMD_GPU_UDEV_PACKAGE_URL,
)


def test_pack_downloads_and_checksums_the_offline_gpu_udev_package(tmp_path: Path, monkeypatch) -> None:
    # Given: an empty bundle staging directory and a recording downloader.
    commands: list[list[str]] = []
    verified: list[tuple[Path, str]] = []

    def fake_run(command: list[str], **_: object) -> SimpleNamespace:
        commands.append(command)
        Path(command[-1]).write_bytes(b"package")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(pack, "run", fake_run)
    monkeypatch.setattr(pack, "verify_sha256", lambda path, checksum: verified.append((Path(path), checksum)))

    # When: package artifacts are added to the offline bundle.
    pack.pack_download_gpu_access_package(tmp_path)

    # Then: the pinned deb is placed in packages/ and verified before archiving.
    deb = tmp_path / "packages" / AMD_GPU_UDEV_PACKAGE_FILENAME
    assert commands == [["wget", "-q", AMD_GPU_UDEV_PACKAGE_URL, "-O", str(deb)]]
    assert verified == [(deb, AMD_GPU_UDEV_PACKAGE_SHA256)]
