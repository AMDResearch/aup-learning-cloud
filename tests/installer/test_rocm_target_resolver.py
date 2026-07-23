# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from auplc_installer.rocm_profiles import DEFAULT_CATALOG_PATH, CatalogError, load_catalog, resolve_profile

ROOT = Path(__file__).resolve().parents[2]
CLI = ROOT / "dockerfiles" / "Base" / "rocm-targets.py"
CATALOG = ROOT / "auplc_installer" / "data" / "rocm-profiles.yaml"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(CLI), *args], cwd=ROOT, capture_output=True, text=True, check=False)


def test_catalog_separates_concrete_targets_from_one_to_one_profiles() -> None:
    catalog = load_catalog()

    assert tuple(catalog.targets) == ("gfx1103", "gfx1150", "gfx1151", "gfx1152", "gfx1200", "gfx1201")
    assert tuple(catalog.profiles) == ("gfx1103", "gfx1150", "gfx1151", "gfx1152", "gfx1200", "gfx1201")
    assert [profile.targets for profile in catalog.profiles.values()] == [
        ("gfx1103",),
        ("gfx1150",),
        ("gfx1151",),
        ("gfx1152",),
        ("gfx1200",),
        ("gfx1201",),
    ]
    assert [profile.tag_suffix for profile in catalog.profiles.values()] == [
        "gfx1103",
        "gfx1150",
        "gfx1151",
        "gfx1152",
        "gfx1200",
        "gfx1201",
    ]


def test_default_catalog_path_is_stable_and_non_versioned() -> None:
    assert DEFAULT_CATALOG_PATH == CATALOG
    assert DEFAULT_CATALOG_PATH.name == "rocm-profiles.yaml"


def test_catalog_yaml_keeps_artifacts_out_of_profiles() -> None:
    raw = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))

    assert set(raw["profiles"]["gfx1151"]) == {"tag_suffix", "targets"}
    assert raw["targets"]["gfx1151"]["rocm_package"] == "amdrocm-core-sdk7.14-gfx1151"


@pytest.mark.parametrize(
    ("profile", "package", "torch", "vision"),
    [
        (
            "gfx1103",
            "amdrocm-core-sdk7.14-gfx1103",
            "torch[device-gfx1103]==2.12.0+rocm7.14.0",
            "torchvision[device-gfx1103]==0.27.0+rocm7.14.0",
        ),
        (
            "gfx1150",
            "amdrocm-core-sdk7.14-gfx1150",
            "torch[device-gfx1150]==2.12.0+rocm7.14.0",
            "torchvision[device-gfx1150]==0.27.0+rocm7.14.0",
        ),
        (
            "gfx1151",
            "amdrocm-core-sdk7.14-gfx1151",
            "torch[device-gfx1151]==2.12.0+rocm7.14.0",
            "torchvision[device-gfx1151]==0.27.0+rocm7.14.0",
        ),
        (
            "gfx1152",
            "amdrocm-core-sdk7.14-gfx1152",
            "torch[device-gfx1152]==2.12.0+rocm7.14.0",
            "torchvision[device-gfx1152]==0.27.0+rocm7.14.0",
        ),
        (
            "gfx1200",
            "amdrocm-core-sdk7.14-gfx1200",
            "torch[device-gfx1200]==2.12.0+rocm7.14.0",
            "torchvision[device-gfx1200]==0.27.0+rocm7.14.0",
        ),
        (
            "gfx1201",
            "amdrocm-core-sdk7.14-gfx1201",
            "torch[device-gfx1201]==2.12.0+rocm7.14.0",
            "torchvision[device-gfx1201]==0.27.0+rocm7.14.0",
        ),
    ],
)
def test_resolution_uses_exact_catalog_artifacts(profile: str, package: str, torch: str, vision: str) -> None:
    plan = resolve_profile(profile)

    assert (plan.profile, plan.target, plan.rocm_version, plan.rocm_package) == (profile, profile, "7.14.0", package)
    assert plan.tag_suffix == profile
    assert (plan.torch_extra, plan.torchvision_extra) == (f"device-{profile}", f"device-{profile}")
    assert plan.wheel_requirements == (torch, vision, "torchaudio==2.11.0+rocm7.14.0")
    assert (plan.torch_version, plan.torchvision_version, plan.torchaudio_version) == (
        "2.12.0+rocm7.14.0",
        "0.27.0+rocm7.14.0",
        "2.11.0+rocm7.14.0",
    )
    assert plan.apt_key_url == "https://repo.amd.com/rocm/packages-multi-arch/gpg/rocm.gpg"
    assert (
        plan.apt_source
        == "deb [arch=amd64 signed-by=/etc/apt/keyrings/amdrocm.gpg] https://repo.amd.com/rocm/packages-multi-arch/ubuntu2404 stable main"
    )
    assert plan.wheel_index_url == "https://repo.amd.com/rocm/whl-multi-arch/"
    assert (
        plan.provenance.rocm_matrix_url
        == "https://rocm.docs.amd.com/en/docs-7.14.0/compatibility/compatibility-matrix.html"
    )
    assert plan.provenance.packages_stream == "packages-multi-arch"
    assert plan.provenance.therock_commit == "418cd5f63abb7a604bad5874cd7b2e29334e640f"
    assert tuple(record.distribution for record in plan.provenance.wheel_metadata) == (
        "torch",
        "torchvision",
        "torchaudio",
    )
    assert all(record.source == "selected wheel METADATA" for record in plan.provenance.wheel_metadata)


def test_wheel_metadata_authority_does_not_claim_unknown_artifact_identity() -> None:
    raw = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))

    for authority in raw["wheel_metadata_authorities"].values():
        assert authority["source"] == "selected wheel METADATA"
        assert "artifact_url" not in authority
        assert "digest" not in authority


def test_wheel_metadata_authorities_list_every_concrete_profile_extra() -> None:
    raw = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))

    expected_extras = [
        "device-gfx1103",
        "device-gfx1150",
        "device-gfx1151",
        "device-gfx1152",
        "device-gfx1200",
        "device-gfx1201",
    ]
    assert raw["wheel_metadata_authorities"]["torch-2.12.0-rocm7.14.0"]["provides_extras"] == expected_extras
    assert raw["wheel_metadata_authorities"]["torchvision-0.27.0-rocm7.14.0"]["provides_extras"] == expected_extras


def test_omitted_and_empty_profiles_use_gfx1151() -> None:
    assert resolve_profile().profile == "gfx1151"
    assert resolve_profile("").profile == "gfx1151"


@pytest.mark.parametrize("profile", ["gfx120x", "gfx110x", "gfx1100"])
def test_unsupported_profiles_fail_explicitly(profile: str) -> None:
    with pytest.raises(CatalogError, match=rf"unsupported ROCm profile '{profile}'"):
        resolve_profile(profile)


@pytest.mark.parametrize(
    ("content", "key"),
    [
        ("schema_version: 1\nschema_version: 1\n", "schema_version"),
        ("profiles:\n  gfx1151:\n    tag_suffix: gfx1151\n    tag_suffix: gfx1151\n", "tag_suffix"),
        ("base: &base\n  schema_version: 1\n<<: *base\nschema_version: 1\n", "schema_version"),
    ],
)
def test_duplicate_yaml_keys_are_rejected_at_every_mapping_depth(tmp_path: Path, content: str, key: str) -> None:
    path = tmp_path / "duplicate.yaml"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(CatalogError, match=rf"duplicate YAML key '{key}'"):
        load_catalog(path)


def test_duplicate_yaml_merge_keys_are_rejected_before_merge_flattening(tmp_path: Path) -> None:
    path = tmp_path / "duplicate-merge.yaml"
    path.write_text(
        "base_one: &base_one\n  first: value\nbase_two: &base_two\n  second: value\n<<: *base_one\n<<: *base_two\n",
        encoding="utf-8",
    )

    with pytest.raises(CatalogError, match="duplicate YAML key '<<'"):
        load_catalog(path)


def test_non_conflicting_yaml_merge_is_supported(tmp_path: Path) -> None:
    catalog_path = tmp_path / "merged-catalog.yaml"
    catalog_path.write_text(
        CATALOG.read_text(encoding="utf-8").replace(
            "  gfx1151:\n    tag_suffix: gfx1151\n    targets: [gfx1151]\n",
            "  gfx1151:\n    <<: &gfx1151_profile\n      tag_suffix: gfx1151\n    targets: [gfx1151]\n",
        ),
        encoding="utf-8",
    )

    catalog = load_catalog(catalog_path)

    assert catalog.profiles["gfx1151"].tag_suffix == "gfx1151"


def test_malformed_yaml_is_wrapped_in_catalog_error(tmp_path: Path) -> None:
    path = tmp_path / "malformed.yaml"
    path.write_text("schema_version: [\n", encoding="utf-8")

    with pytest.raises(CatalogError, match="invalid YAML") as error:
        load_catalog(path)

    assert isinstance(error.value.__cause__, yaml.YAMLError)


def test_unsafe_yaml_tag_is_wrapped_in_catalog_error(tmp_path: Path) -> None:
    path = tmp_path / "unsafe-tag.yaml"
    path.write_text("schema_version: !unsafe 1\n", encoding="utf-8")

    with pytest.raises(CatalogError, match="invalid YAML") as error:
        load_catalog(path)

    assert isinstance(error.value.__cause__, yaml.YAMLError)


def test_yaml_catalog_rejects_non_string_mapping_keys(tmp_path: Path) -> None:
    path = tmp_path / "non-string-key.yaml"
    path.write_text("1: catalog\n", encoding="utf-8")

    with pytest.raises(CatalogError, match="YAML mapping keys must be strings"):
        load_catalog(path)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda data: data.update(unexpected={}), "catalog contains unknown field 'unexpected'"),
        (lambda data: data.update(schema_version=2), "schema_version must be 1"),
        (lambda data: data.update(default_profile="gfx9999"), "default_profile 'gfx9999' is not defined"),
        (lambda data: data["targets"].update({"GFX1200": data["targets"]["gfx1200"]}), "malformed target name"),
        (lambda data: data["profiles"].update({"GFX1200": data["profiles"]["gfx1200"]}), "malformed profile name"),
        (
            lambda data: data["profiles"]["gfx1200"].update(targets=[]),
            "profiles.gfx1200.targets must be a non-empty list",
        ),
        (
            lambda data: data["profiles"]["gfx1200"].update(targets=["gfx1200", "gfx1200"]),
            "profile 'gfx1200' contains duplicate target 'gfx1200'",
        ),
        (
            lambda data: data["profiles"]["gfx1200"].update(targets=["gfx9999"]),
            "profile 'gfx1200' references unknown target 'gfx9999'",
        ),
        (
            lambda data: data["wheel_metadata_authorities"]["torch-2.12.0-rocm7.14.0"].update(source="wheel index"),
            "wheel metadata authority 'torch-2.12.0-rocm7.14.0' source must be selected wheel METADATA",
        ),
    ],
)
def test_schema_and_reference_errors_are_rejected(
    tmp_path: Path,
    mutation: Callable[[dict[str, Any]], Any],
    message: str,
) -> None:
    data = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    mutation(data)
    path = tmp_path / "invalid.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    with pytest.raises(CatalogError, match=message):
        load_catalog(path)


def test_concrete_target_can_be_reused_by_future_explicit_profile(tmp_path: Path) -> None:
    data = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    data["profiles"]["gfx1202"] = {"tag_suffix": "gfx1202", "targets": ["gfx1151"]}
    path = tmp_path / "future-profile.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    catalog = load_catalog(path)
    plan = resolve_profile("gfx1202", path)

    assert catalog.profiles["gfx1202"].targets == ("gfx1151",)
    assert plan.profile == "gfx1202"
    assert plan.tag_suffix == "gfx1202"
    assert plan.target == "gfx1151"
    assert plan.rocm_package == "amdrocm-core-sdk7.14-gfx1151"


def test_public_cli_validates_lists_and_emits_complete_plans() -> None:
    validated = run_cli("validate")
    listed = run_cli("list-profiles")
    listed_lines = run_cli("list-profiles", "--format", "lines")
    resolved = run_cli("resolve-profile", "gfx1200", "--format", "lines")

    assert (validated.returncode, validated.stdout, validated.stderr) == (0, "valid\n", "")
    assert json.loads(listed.stdout) == ["gfx1103", "gfx1150", "gfx1151", "gfx1152", "gfx1200", "gfx1201"]
    assert listed_lines.stdout == "gfx1103\ngfx1150\ngfx1151\ngfx1152\ngfx1200\ngfx1201\n"
    assert resolved.returncode == 0
    assert "ROCM_PACKAGE=amdrocm-core-sdk7.14-gfx1200" in resolved.stdout
    assert "PROFILE=gfx1200" in resolved.stdout
    assert "TORCH_REQUIREMENT=torch[device-gfx1200]==2.12.0+rocm7.14.0" in resolved.stdout
    assert "TORCH_EXTRA=device-gfx1200" in resolved.stdout
    assert "WHEEL_INDEX_URL=https://repo.amd.com/rocm/whl-multi-arch/" in resolved.stdout
    assert "THEROCK_COMMIT=418cd5f63abb7a604bad5874cd7b2e29334e640f" in resolved.stdout
    assert "WHEEL_METADATA_0_DISTRIBUTION=torch" in resolved.stdout
    assert "WHEEL_METADATA_2_PROVIDES_EXTRAS=\n" in resolved.stdout


def test_public_cli_uses_an_explicit_yaml_catalog(tmp_path: Path) -> None:
    data = yaml.safe_load(CATALOG.read_text(encoding="utf-8"))
    data["default_profile"] = "gfx1200"
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    result = run_cli("--catalog", str(catalog_path), "resolve-profile")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["profile"] == "gfx1200"


def test_public_cli_rejects_unsupported_profile() -> None:
    result = run_cli("resolve-profile", "gfx120x")

    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        "",
        "error: unsupported ROCm profile 'gfx120x'\n",
    )


def test_public_cli_reports_a_missing_resolver_dependency_actionably() -> None:
    environment = {key: value for key, value in os.environ.items() if key not in {"PYTHONHOME", "PYTHONPATH"}}
    result = subprocess.run(
        [sys.executable, "-S", str(CLI), "validate"],
        cwd=ROOT,
        capture_output=True,
        check=False,
        env=environment,
        text=True,
    )

    assert (result.returncode, result.stdout, result.stderr) == (
        2,
        "",
        "error: missing required dependency 'yaml' for auplc_installer.rocm_profiles\n",
    )
