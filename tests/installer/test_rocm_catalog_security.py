# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

import json
from pathlib import Path

import pytest

from auplc_installer.rocm_profiles import DEFAULT_CATALOG_PATH, CatalogError, load_catalog


def _catalog(tmp_path: Path) -> dict:
    data = json.loads(DEFAULT_CATALOG_PATH.read_text(encoding="utf-8"))
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("profiles", "gfx1151", "tag_suffix"), "gfx1151\nINJECT=1"),
        (("targets", "gfx1151", "rocm_package"), "rocm\rpackage"),
        (("repositories", "wheel_index_url"), "http://example.test/index"),
    ],
)
def test_catalog_rejects_line_protocol_injection(tmp_path: Path, path: tuple[str, ...], value: str) -> None:
    data = _catalog(tmp_path)
    target = data
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(CatalogError):
        load_catalog(catalog_path)
