# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

from pathlib import Path
from typing import Any

import pytest
import yaml

from auplc_installer.rocm_profiles import DEFAULT_CATALOG_PATH, CatalogError, load_catalog


def _catalog(tmp_path: Path) -> dict:
    return yaml.safe_load(DEFAULT_CATALOG_PATH.read_text(encoding="utf-8"))


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
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    with pytest.raises(CatalogError):
        load_catalog(catalog_path)


def test_catalog_rejects_line_protocol_injection_in_wheel_metadata_extras(tmp_path: Path) -> None:
    data = _catalog(tmp_path)
    data["wheel_metadata_authorities"]["torch-2.12.0-rocm7.14.0"]["provides_extras"].append("device-gfx1151\nINJECT=1")
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    with pytest.raises(CatalogError, match=r"provides_extras\[6\] cannot contain control characters"):
        load_catalog(catalog_path)


def test_catalog_rejects_line_protocol_injection_in_wheel_metadata_authority_keys(tmp_path: Path) -> None:
    data = _catalog(tmp_path)
    authorities: dict[str, Any] = data["wheel_metadata_authorities"]
    original = "torch-2.12.0-rocm7.14.0"
    injected = "torch-2.12.0-rocm7.14.0\nINJECT=1"
    authorities[injected] = authorities.pop(original)
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    with pytest.raises(CatalogError, match=r"(?s)wheel_metadata_authorities.*cannot contain control characters"):
        load_catalog(catalog_path)
