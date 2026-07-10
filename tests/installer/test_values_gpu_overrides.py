# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]

VALUES_FILES = (
    ROOT / "runtime" / "values.yaml",
    ROOT / "runtime" / "values-multi-nodes.yaml.example",
)

GPU_ACCELERATOR_TAGS = {
    "phx": "gfx110x",
    "strix": "gfx1150",
    "strix-halo": "gfx1151",
    "9070xt": "gfx120x",
    "r9700": "gfx120x",
    "9600gre": "gfx120x",
}

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
    expected_keys = list(GPU_ACCELERATOR_TAGS)

    for values_file in VALUES_FILES:
        values = _load_values(values_file)
        accelerators = values["custom"]["accelerators"]

        for accelerator_key in expected_keys:
            assert accelerator_key in accelerators, values_file


def test_default_values_keep_visible_gpu_accelerators_conservative() -> None:
    for values_file in VALUES_FILES:
        values = _load_values(values_file)
        metadata = values["custom"]["resources"]["metadata"]

        for resource_key in GPU_RESOURCE_IMAGES:
            assert metadata[resource_key]["acceleratorKeys"] == ["strix-halo"], values_file


def test_default_values_route_gpu_resources_to_supported_image_tags() -> None:
    for values_file in VALUES_FILES:
        values = _load_values(values_file)
        metadata = values["custom"]["resources"]["metadata"]

        for resource_key, image_name in GPU_RESOURCE_IMAGES.items():
            overrides = metadata[resource_key]["acceleratorOverrides"]
            assert set(overrides) == set(GPU_ACCELERATOR_TAGS), values_file

            for accelerator_key, gpu_target in GPU_ACCELERATOR_TAGS.items():
                assert overrides[accelerator_key]["image"] == (
                    f"ghcr.io/amdresearch/{image_name}:latest-{gpu_target}"
                ), values_file
