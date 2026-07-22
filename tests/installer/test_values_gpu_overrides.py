# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

from __future__ import annotations

from pathlib import Path

import yaml

from auplc_installer.gpu import CURATED_ACCELERATOR_KEYS, PRODUCT_NAME_TO_SKU, resolve_gpu_config

ROOT = Path(__file__).resolve().parents[2]

VALUES_FILES = (
    ROOT / "runtime" / "values.yaml",
    ROOT / "runtime" / "values-multi-nodes.yaml.example",
)

GPU_RESOURCE_IMAGES = {
    "gpu": "auplc-base",
    "code-gpu": "auplc-code-gpu",
    "Course-CV": "auplc-cv",
    "Course-DL": "auplc-dl",
    "Course-LLM": "auplc-llm",
    "Course-PhySim": "auplc-physim",
}


def _load_values(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_default_values_expose_supported_gpu_accelerators() -> None:
    expected_keys = list(CURATED_ACCELERATOR_KEYS)
    expected_product_names = {row.accelerator_key: product_name for product_name, row in PRODUCT_NAME_TO_SKU.items()}

    for values_file in VALUES_FILES:
        values = _load_values(values_file)
        accelerators = values["custom"]["accelerators"]

        assert list(accelerators) == expected_keys, values_file
        for accelerator_key, product_name in expected_product_names.items():
            assert accelerators[accelerator_key]["nodeSelector"] == {"amd.com/gpu.product-name": product_name}, (
                values_file
            )


def test_default_values_keep_visible_gpu_accelerators_conservative() -> None:
    for values_file in VALUES_FILES:
        values = _load_values(values_file)
        metadata = values["custom"]["resources"]["metadata"]

        for resource_key in GPU_RESOURCE_IMAGES:
            assert metadata[resource_key]["acceleratorKeys"] == ["strix-halo"], values_file


def test_default_values_do_not_set_a_phx_environment_override() -> None:
    for values_file in VALUES_FILES:
        values = _load_values(values_file)

        assert values["custom"]["accelerators"]["phx"]["env"] == {}, values_file


def test_default_values_route_gpu_resources_to_supported_image_tags() -> None:
    for values_file in VALUES_FILES:
        values = _load_values(values_file)
        metadata = values["custom"]["resources"]["metadata"]

        for resource_key, image_name in GPU_RESOURCE_IMAGES.items():
            overrides = metadata[resource_key]["acceleratorOverrides"]
            assert list(overrides) == list(CURATED_ACCELERATOR_KEYS), values_file

            for accelerator_key in CURATED_ACCELERATOR_KEYS:
                image_profile = resolve_gpu_config(accelerator_key).image_profile
                assert overrides[accelerator_key]["image"] == (
                    f"ghcr.io/amdresearch/{image_name}:latest-{image_profile}"
                ), values_file
