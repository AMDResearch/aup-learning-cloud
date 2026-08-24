#!/usr/bin/env python3
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
"""Stage and atomically publish generated deployment artifacts."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from contextlib import suppress
from pathlib import Path


def die(msg: str, code: int = 1) -> None:
    print(f"gen_configs: {msg}", file=sys.stderr)
    raise SystemExit(code)


def preflight_destinations(paths: list[Path], force: bool) -> None:
    if force:
        return
    for path in paths:
        if os.path.lexists(path):
            die(f"refusing to overwrite existing {path} (use --force)", 1)


def stage_file(path: Path, content: str, mode: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, staged_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as staged_file:
            staged_file.write(content)
            staged_file.flush()
            os.fsync(staged_file.fileno())
    except OSError:
        with suppress(OSError):
            os.close(fd)
        Path(staged_path).unlink(missing_ok=True)
        raise
    return Path(staged_path)


def remove_destination(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def backup_destination(path: Path) -> tuple[Path, Path]:
    backup_dir = Path(tempfile.mkdtemp(prefix=f".{path.name}.backup.", dir=path.parent))
    backup_path = backup_dir / path.name
    os.replace(path, backup_path)
    return backup_dir, backup_path


def _fsync_parent(path: Path) -> None:
    directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def publish_artifacts(
    artifacts: list[tuple[Path, str, int, bool]], force: bool, remove_paths: tuple[Path, ...] = ()
) -> None:
    staged: list[tuple[Path, Path, bool]] = []
    published: list[Path] = []
    backups: list[tuple[Path, Path, Path]] = []
    replacement_paths = tuple(path for path, _, _, _ in artifacts)
    try:
        for path, content, mode, secret in artifacts:
            staged.append((path, stage_file(path, content, mode), secret))
        if force:
            for path in (*replacement_paths, *(path for path in remove_paths if path not in replacement_paths)):
                if os.path.lexists(path):
                    backup_dir, backup_path = backup_destination(path)
                    backups.append((path, backup_dir, backup_path))
                    _fsync_parent(path)
        for path, staged_path, secret in staged:
            if force:
                os.replace(staged_path, path)
            else:
                os.link(staged_path, path)
            published.append(path)
            if not force:
                os.unlink(staged_path)
            _fsync_parent(path)
            print(f"wrote {path}" + ("  (chmod 600 -- contains the k3s token)" if secret else ""))
    except OSError as exc:
        for path in reversed(published):
            remove_destination(path)
            _fsync_parent(path)
        for path, backup_dir, backup_path in reversed(backups):
            remove_destination(path)
            os.replace(backup_path, path)
            _fsync_parent(path)
            backup_dir.rmdir()
        die(f"could not publish generated artifacts: {exc}")
    else:
        for _, backup_dir, _ in backups:
            shutil.rmtree(backup_dir)
    finally:
        for _, staged_path, _ in staged:
            staged_path.unlink(missing_ok=True)
