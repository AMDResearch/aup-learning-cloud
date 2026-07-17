# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""Unit tests for the auplc-installer Python package.

Run from the repository root with:

    python -m pytest tests/installer

These tests focus on pure-function logic (catalog parsing, overlay emission,
GPU SKU resolution, manifest round-trip, image-ref normalisation) so they
need no Docker, no kubectl, no rocminfo, and no network.
"""
