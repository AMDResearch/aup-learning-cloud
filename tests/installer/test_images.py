# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Tests for :mod:`auplc_installer.images` reference helpers.

Only covers the pure-function ``resolve_pull_ref`` and the static
``BUILD_ONLY_IMAGES`` / ``EXTERNAL_IMAGES`` constants. The actual ``docker
pull`` / ``docker save`` paths require a real Docker daemon and are not
exercised here.
"""

from __future__ import annotations

import re

import pytest

from auplc_installer.images import (
    BUILD_ONLY_IMAGES,
    EXTERNAL_IMAGES,
    resolve_pull_ref,
)

_TAG_RE = re.compile(r":[A-Za-z0-9_.-]+$")


def test_bare_image_gets_docker_io_library_prefix() -> None:
    assert resolve_pull_ref("alpine", mirror_prefix="") == "docker.io/library/alpine"


def test_user_image_without_dot_in_first_segment_gets_docker_io() -> None:
    assert resolve_pull_ref("foo/bar", mirror_prefix="") == "docker.io/foo/bar"


def test_explicit_registry_is_preserved() -> None:
    assert resolve_pull_ref("quay.io/jupyterhub/k8s-hub:4.3.3", mirror_prefix="") == "quay.io/jupyterhub/k8s-hub:4.3.3"


def test_registry_k8s_io_is_preserved() -> None:
    assert resolve_pull_ref("registry.k8s.io/pause:3.10.1", mirror_prefix="") == "registry.k8s.io/pause:3.10.1"


def test_mirror_prefix_prepended_after_registry_resolution() -> None:
    assert resolve_pull_ref("alpine", mirror_prefix="m.example.com") == "m.example.com/docker.io/library/alpine"
    assert resolve_pull_ref("foo/bar", mirror_prefix="m.example.com") == "m.example.com/docker.io/foo/bar"
    assert (
        resolve_pull_ref("quay.io/jupyterhub/k8s-hub:4.3.3", mirror_prefix="m.example.com")
        == "m.example.com/quay.io/jupyterhub/k8s-hub:4.3.3"
    )


@pytest.mark.parametrize("image", EXTERNAL_IMAGES)
def test_every_external_image_has_explicit_tag(image: str) -> None:
    assert _TAG_RE.search(image), f"{image!r} is missing an explicit tag"


@pytest.mark.parametrize("image", BUILD_ONLY_IMAGES)
def test_every_build_only_image_has_explicit_tag(image: str) -> None:
    assert _TAG_RE.search(image), f"{image!r} is missing an explicit tag"


def test_no_duplicate_external_images() -> None:
    assert len(EXTERNAL_IMAGES) == len(set(EXTERNAL_IMAGES))
