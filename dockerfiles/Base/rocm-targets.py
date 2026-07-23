#!/usr/bin/env python3
# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

"""Thin command-line adapter for the canonical ROCm profile resolver."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _import_resolver() -> tuple[Any, Any, Any, Path]:
    for parent in Path(__file__).resolve().parents:
        if (parent / "auplc_installer" / "rocm_profiles.py").is_file():
            sys.path.insert(0, str(parent))
            break
    try:
        from auplc_installer.rocm_profiles import (
            DEFAULT_CATALOG_PATH,
            CatalogError,
            list_profiles,
            resolve_profile,
        )
    except ModuleNotFoundError as error:
        if error.name in {"auplc_installer", "auplc_installer.rocm_profiles"}:
            raise RuntimeError("cannot locate auplc_installer.rocm_profiles") from error
        raise RuntimeError(f"missing required dependency '{error.name}' for auplc_installer.rocm_profiles") from error
    return CatalogError, list_profiles, resolve_profile, DEFAULT_CATALOG_PATH


def _parse_args(argv: list[str], default_catalog: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=default_catalog, help="path to the canonical profile catalog")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="validate the catalog")
    listing = subparsers.add_parser("list-profiles", help="list supported profile names")
    listing.add_argument("--format", choices=("json", "lines"), default="json")
    resolve = subparsers.add_parser("resolve-profile", help="resolve a profile to a complete build plan")
    resolve.add_argument("profile", nargs="?", help="profile name; defaults to gfx1151")
    resolve.add_argument("--format", choices=("json", "lines"), default="json")
    return parser.parse_args(argv)


def _emit_lines(plan: Any) -> None:
    values = (
        ("PROFILE", plan.profile),
        ("TAG_SUFFIX", plan.tag_suffix),
        ("TARGET", plan.target),
        ("ROCM_VERSION", plan.rocm_version),
        ("ROCM_PACKAGE", plan.rocm_package),
        ("TORCH_EXTRA", plan.torch_extra),
        ("TORCHVISION_EXTRA", plan.torchvision_extra),
        ("TORCH_VERSION", plan.torch_version),
        ("TORCHVISION_VERSION", plan.torchvision_version),
        ("TORCHAUDIO_VERSION", plan.torchaudio_version),
        ("TORCH_REQUIREMENT", plan.wheel_requirements[0]),
        ("TORCHVISION_REQUIREMENT", plan.wheel_requirements[1]),
        ("TORCHAUDIO_REQUIREMENT", plan.wheel_requirements[2]),
        ("APT_KEY_URL", plan.apt_key_url),
        ("APT_SOURCE", plan.apt_source),
        ("WHEEL_INDEX_URL", plan.wheel_index_url),
        ("ROCM_MATRIX_URL", plan.provenance.rocm_matrix_url),
        ("PACKAGES_STREAM", plan.provenance.packages_stream),
        ("PACKAGES_STREAM_URL", plan.provenance.packages_stream_url),
        ("THEROCK_COMMIT", plan.provenance.therock_commit),
        ("THEROCK_URL", plan.provenance.therock_url),
    )
    for key, value in values:
        print(f"{key}={value}")
    for index, record in enumerate(plan.provenance.wheel_metadata):
        prefix = f"WHEEL_METADATA_{index}"
        print(f"{prefix}_AUTHORITY={record.authority}")
        print(f"{prefix}_SOURCE={record.source}")
        print(f"{prefix}_DISTRIBUTION={record.distribution}")
        print(f"{prefix}_VERSION={record.version}")
        print(f"{prefix}_INDEX_URL={record.index_url}")
        print(f"{prefix}_PROVIDES_EXTRAS={','.join(record.provides_extras)}")


def main(argv: list[str] | None = None) -> int:
    try:
        catalog_error, list_profiles, resolve_profile, default_catalog = _import_resolver()
    except RuntimeError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    args = _parse_args(sys.argv[1:] if argv is None else argv, default_catalog)
    try:
        if args.command == "validate":
            list_profiles(args.catalog)
            print("valid")
        elif args.command == "list-profiles":
            profiles = list_profiles(args.catalog)
            print(json.dumps(profiles, separators=(",", ":")) if args.format == "json" else "\n".join(profiles))
        else:
            plan = resolve_profile(args.profile, args.catalog)
            if args.format == "lines":
                _emit_lines(plan)
            else:
                print(json.dumps(plan.as_dict(), separators=(",", ":")))
        return 0
    except catalog_error as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
