# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

"""Load and resolve the canonical ROCm build profile catalog."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CATALOG_PATH = Path(__file__).with_name("data") / "rocm-profiles.yaml"
PROFILE_NAME_PATTERN = re.compile(r"gfx[0-9]+\Z")
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
PACKAGE_PATTERN = re.compile(r"[a-z0-9][a-z0-9+.-]*\Z")
EXTRA_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]*\Z")
WHEEL_METADATA_SOURCE = "selected wheel METADATA"
MERGE_KEY_TAG = "tag:yaml.org,2002:merge"


class CatalogError(ValueError):
    """Raised when the profile catalog or requested profile is invalid."""


@dataclass(frozen=True)
class WheelMetadataAuthority:
    """Declarations read from selected wheel METADATA."""

    authority: str
    source: str
    distribution: str
    version: str
    index_url: str
    provides_extras: tuple[str, ...]


@dataclass(frozen=True)
class Provenance:
    """Sources from which the catalog's artifact records were established."""

    rocm_matrix_url: str
    packages_stream: str
    packages_stream_url: str
    therock_commit: str
    therock_url: str
    wheel_metadata: tuple[WheelMetadataAuthority, ...]


@dataclass(frozen=True)
class Target:
    """One concrete image profile and its exact, non-inferred artifacts."""

    name: str
    rocm_package: str
    torch_extra: str
    torchvision_extra: str
    torch_requirement: str
    torchvision_requirement: str
    torchaudio_requirement: str
    metadata_authorities: tuple[str, str, str]


@dataclass(frozen=True)
class Profile:
    """An AUP build profile referencing concrete targets."""

    name: str
    tag_suffix: str
    targets: tuple[str, ...]


@dataclass(frozen=True)
class Catalog:
    """Validated canonical catalog."""

    default_profile: str
    rocm_version: str
    torch_version: str
    torchvision_version: str
    torchaudio_version: str
    apt_key_url: str
    apt_source: str
    wheel_index_url: str
    provenance: Provenance
    targets: dict[str, Target]
    profiles: dict[str, Profile]


@dataclass(frozen=True)
class BuildPlan:
    """Complete artifact and repository selection for one image profile."""

    profile: str
    tag_suffix: str
    target: str
    rocm_version: str
    rocm_package: str
    torch_extra: str
    torchvision_extra: str
    torch_version: str
    torchvision_version: str
    torchaudio_version: str
    wheel_requirements: tuple[str, str, str]
    apt_key_url: str
    apt_source: str
    wheel_index_url: str
    provenance: Provenance

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation in field order."""
        return asdict(self)


class _CatalogSafeLoader(yaml.SafeLoader):
    """Safe YAML loader scoped to the ROCm catalog parser."""


def _mapping_key(loader: _CatalogSafeLoader, key_node: Any) -> str:
    if key_node.tag == MERGE_KEY_TAG:
        return "<<"
    key = loader.construct_object(key_node, deep=False)
    if not isinstance(key, str):
        raise CatalogError("YAML mapping keys must be strings")
    return key


def _validate_raw_yaml_node(loader: _CatalogSafeLoader, node: Any, visited: set[int]) -> None:
    """Reject duplicate and non-string map keys before YAML merge processing mutates nodes."""
    if id(node) in visited:
        return
    visited.add(id(node))
    if node.id == "mapping":
        keys: set[str] = set()
        for key_node, value_node in node.value:
            key = _mapping_key(loader, key_node)
            if key in keys:
                raise CatalogError(f"duplicate YAML key '{key}'")
            keys.add(key)
            _validate_raw_yaml_node(loader, value_node, visited)
    elif node.id == "sequence":
        for value_node in node.value:
            _validate_raw_yaml_node(loader, value_node, visited)


def _construct_catalog_mapping(loader: _CatalogSafeLoader, node: Any, deep: bool = False) -> dict[str, Any]:
    """Construct maps while preserving safe YAML merges and rejecting duplicate keys."""
    _validate_raw_yaml_node(loader, node, set())
    loader.flatten_mapping(node)
    result: dict[str, Any] = {}
    for key_node, value_node in node.value:
        key = _mapping_key(loader, key_node)
        if key in result:
            raise CatalogError(f"duplicate YAML key '{key}'")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_CatalogSafeLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_catalog_mapping)


def _object(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CatalogError(f"{location} must be an object")
    return value


def _string(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value:
        raise CatalogError(f"{location} must be a non-empty string")
    if any(character in value for character in "\r\n\x00"):
        raise CatalogError(f"{location} cannot contain control characters")
    return value


def _https_url(value: Any, location: str) -> str:
    url = _string(value, location)
    if not re.fullmatch(r"https://[^\s/]+(?:/[^\s]*)?", url):
        raise CatalogError(f"{location} must be an HTTPS URL")
    return url


def _token(value: Any, location: str, pattern: re.Pattern[str]) -> str:
    token = _string(value, location)
    if not pattern.fullmatch(token):
        raise CatalogError(f"{location} has invalid characters")
    return token


def _exact_keys(value: dict[str, Any], expected: set[str], location: str) -> None:
    missing = expected - value.keys()
    extra = value.keys() - expected
    if missing:
        raise CatalogError(f"{location} is missing field '{sorted(missing)[0]}'")
    if extra:
        raise CatalogError(f"{location} contains unknown field '{sorted(extra)[0]}'")


def _load_wheel_metadata(raw: Any, wheel_index_url: str) -> dict[str, WheelMetadataAuthority]:
    records = _object(raw, "wheel_metadata_authorities")
    if not records:
        raise CatalogError("wheel_metadata_authorities must not be empty")
    result: dict[str, WheelMetadataAuthority] = {}
    expected = {"source", "distribution", "version", "index_url", "provides_extras"}
    for raw_authority, raw_record in records.items():
        authority = _token(raw_authority, f"wheel_metadata_authorities.{raw_authority}", PACKAGE_PATTERN)
        record = _object(raw_record, f"wheel_metadata_authorities.{authority}")
        _exact_keys(record, expected, f"wheel_metadata_authorities.{authority}")
        extras = record["provides_extras"]
        if not isinstance(extras, list) or any(not isinstance(extra, str) or not extra for extra in extras):
            raise CatalogError(f"wheel_metadata_authorities.{authority}.provides_extras must be a string list")
        validated_extras = tuple(
            _token(extra, f"wheel_metadata_authorities.{authority}.provides_extras[{index}]", EXTRA_PATTERN)
            for index, extra in enumerate(extras)
        )
        if len(extras) != len(set(extras)):
            raise CatalogError(f"wheel_metadata_authorities.{authority}.provides_extras contains duplicates")
        index_url = _https_url(record["index_url"], f"wheel_metadata_authorities.{authority}.index_url")
        if index_url != wheel_index_url:
            raise CatalogError(f"wheel metadata authority '{authority}' uses a different wheel index")
        source = _string(record["source"], f"wheel_metadata_authorities.{authority}.source")
        if source != WHEEL_METADATA_SOURCE:
            raise CatalogError(f"wheel metadata authority '{authority}' source must be {WHEEL_METADATA_SOURCE}")
        result[authority] = WheelMetadataAuthority(
            authority=authority,
            source=source,
            distribution=_string(record["distribution"], f"wheel_metadata_authorities.{authority}.distribution"),
            version=_string(record["version"], f"wheel_metadata_authorities.{authority}.version"),
            index_url=index_url,
            provides_extras=validated_extras,
        )
    return result


def _validate_requirement(
    requirement: str,
    profile_name: str,
    distribution: str,
    authority: WheelMetadataAuthority,
    *,
    extra: str | None,
) -> None:
    if extra is not None:
        if extra not in authority.provides_extras:
            raise CatalogError(f"wheel metadata authority '{authority.authority}' does not provide extra '{extra}'")
        expected = f"{distribution}[{extra}]=={authority.version}"
        if requirement != expected:
            raise CatalogError(f"profiles.{profile_name} has unauthorized {distribution} requirement '{requirement}'")
    elif authority.provides_extras:
        raise CatalogError(f"{distribution} metadata must not require a device extra")
    elif requirement != f"{distribution}=={authority.version}":
        raise CatalogError(f"profiles.{profile_name} has unauthorized {distribution} requirement '{requirement}'")


def _load_targets(raw: Any, authorities: dict[str, WheelMetadataAuthority]) -> dict[str, Target]:
    records = _object(raw, "targets")
    if not records:
        raise CatalogError("targets must not be empty")
    expected = {
        "rocm_package",
        "torch_extra",
        "torchvision_extra",
        "torch_requirement",
        "torchvision_requirement",
        "torchaudio_requirement",
        "torch_metadata",
        "torchvision_metadata",
        "torchaudio_metadata",
    }
    targets: dict[str, Target] = {}
    for name, raw_target in records.items():
        if not PROFILE_NAME_PATTERN.fullmatch(name):
            raise CatalogError(f"malformed target name '{name}'")
        target = _object(raw_target, f"targets.{name}")
        _exact_keys(target, expected, f"targets.{name}")

        authority_names_list = [
            _string(target[field], f"targets.{name}.{field}")
            for field in ("torch_metadata", "torchvision_metadata", "torchaudio_metadata")
        ]
        authority_names = (authority_names_list[0], authority_names_list[1], authority_names_list[2])
        resolved_authorities: list[WheelMetadataAuthority] = []
        for authority_name in authority_names:
            if authority_name not in authorities:
                raise CatalogError(f"unknown wheel metadata authority '{authority_name}'")
            resolved_authorities.append(authorities[authority_name])

        requirements_list = [
            _string(target[field], f"targets.{name}.{field}")
            for field in ("torch_requirement", "torchvision_requirement", "torchaudio_requirement")
        ]
        requirements = (requirements_list[0], requirements_list[1], requirements_list[2])
        extras = (
            _token(target["torch_extra"], f"targets.{name}.torch_extra", EXTRA_PATTERN),
            _token(target["torchvision_extra"], f"targets.{name}.torchvision_extra", EXTRA_PATTERN),
            None,
        )
        for requirement, distribution, authority, extra in zip(
            requirements,
            ("torch", "torchvision", "torchaudio"),
            resolved_authorities,
            extras,
        ):
            if authority.distribution != distribution:
                raise CatalogError(f"wheel metadata authority '{authority.authority}' is not for {distribution}")
            _validate_requirement(requirement, name, distribution, authority, extra=extra)

        targets[name] = Target(
            name=name,
            rocm_package=_token(target["rocm_package"], f"targets.{name}.rocm_package", PACKAGE_PATTERN),
            torch_extra=extras[0],
            torchvision_extra=extras[1],
            torch_requirement=requirements[0],
            torchvision_requirement=requirements[1],
            torchaudio_requirement=requirements[2],
            metadata_authorities=authority_names,
        )
    return targets


def _load_profiles(raw: Any, targets: dict[str, Target]) -> dict[str, Profile]:
    records = _object(raw, "profiles")
    if not records:
        raise CatalogError("profiles must not be empty")
    profiles: dict[str, Profile] = {}
    for name, raw_profile in records.items():
        if not PROFILE_NAME_PATTERN.fullmatch(name):
            raise CatalogError(f"malformed profile name '{name}'")
        profile = _object(raw_profile, f"profiles.{name}")
        _exact_keys(profile, {"tag_suffix", "targets"}, f"profiles.{name}")
        tag_suffix = _token(profile["tag_suffix"], f"profiles.{name}.tag_suffix", PROFILE_NAME_PATTERN)
        raw_targets = profile["targets"]
        if not isinstance(raw_targets, list) or not raw_targets:
            raise CatalogError(f"profiles.{name}.targets must be a non-empty list")
        profile_targets: list[str] = []
        seen: set[str] = set()
        for index, raw_target in enumerate(raw_targets):
            target = _string(raw_target, f"profiles.{name}.targets[{index}]")
            if target in seen:
                raise CatalogError(f"profile '{name}' contains duplicate target '{target}'")
            if target not in targets:
                raise CatalogError(f"profile '{name}' references unknown target '{target}'")
            seen.add(target)
            profile_targets.append(target)
        profiles[name] = Profile(name=name, tag_suffix=tag_suffix, targets=tuple(profile_targets))
    return profiles


def load_catalog(path: Path = DEFAULT_CATALOG_PATH) -> Catalog:
    """Load and fully validate a ROCm profile catalog."""
    try:
        raw = yaml.load(path.read_text(encoding="utf-8"), Loader=_CatalogSafeLoader)
    except OSError as error:
        raise CatalogError(f"cannot read catalog '{path}': {error}") from error
    except yaml.YAMLError as error:
        raise CatalogError(f"invalid YAML in catalog '{path}': {error}") from error

    root = _object(raw, "catalog")
    _exact_keys(
        root,
        {
            "copyright",
            "schema_version",
            "default_profile",
            "versions",
            "repositories",
            "provenance",
            "wheel_metadata_authorities",
            "targets",
            "profiles",
        },
        "catalog",
    )
    if root["schema_version"] != 1 or isinstance(root["schema_version"], bool):
        raise CatalogError("schema_version must be 1")
    _string(root["copyright"], "copyright")
    versions = _object(root["versions"], "versions")
    _exact_keys(versions, {"rocm", "torch", "torchvision", "torchaudio"}, "versions")
    repositories = _object(root["repositories"], "repositories")
    _exact_keys(repositories, {"apt_key_url", "apt_source", "wheel_index_url"}, "repositories")
    provenance_raw = _object(root["provenance"], "provenance")
    _exact_keys(
        provenance_raw,
        {"rocm_matrix_url", "packages_stream", "packages_stream_url", "therock_commit", "therock_url"},
        "provenance",
    )

    wheel_index_url = _https_url(repositories["wheel_index_url"], "repositories.wheel_index_url")
    authorities = _load_wheel_metadata(root["wheel_metadata_authorities"], wheel_index_url)
    targets = _load_targets(root["targets"], authorities)
    profiles = _load_profiles(root["profiles"], targets)
    default_profile = _string(root["default_profile"], "default_profile")
    if default_profile not in profiles:
        raise CatalogError(f"default_profile '{default_profile}' is not defined")
    commit = _string(provenance_raw["therock_commit"], "provenance.therock_commit")
    if not COMMIT_PATTERN.fullmatch(commit):
        raise CatalogError("provenance.therock_commit must be a full lowercase commit hash")
    provenance = Provenance(
        rocm_matrix_url=_https_url(provenance_raw["rocm_matrix_url"], "provenance.rocm_matrix_url"),
        packages_stream=_string(provenance_raw["packages_stream"], "provenance.packages_stream"),
        packages_stream_url=_https_url(provenance_raw["packages_stream_url"], "provenance.packages_stream_url"),
        therock_commit=commit,
        therock_url=_https_url(provenance_raw["therock_url"], "provenance.therock_url"),
        wheel_metadata=tuple(authorities.values()),
    )
    return Catalog(
        default_profile=default_profile,
        rocm_version=_string(versions["rocm"], "versions.rocm"),
        torch_version=_string(versions["torch"], "versions.torch"),
        torchvision_version=_string(versions["torchvision"], "versions.torchvision"),
        torchaudio_version=_string(versions["torchaudio"], "versions.torchaudio"),
        apt_key_url=_https_url(repositories["apt_key_url"], "repositories.apt_key_url"),
        apt_source=_string(repositories["apt_source"], "repositories.apt_source"),
        wheel_index_url=wheel_index_url,
        provenance=provenance,
        targets=targets,
        profiles=profiles,
    )


def list_profiles(catalog_path: Path = DEFAULT_CATALOG_PATH) -> tuple[str, ...]:
    """Return supported profile names in canonical catalog order."""
    return tuple(load_catalog(catalog_path).profiles)


def resolve_profile(profile: str | None = None, catalog_path: Path = DEFAULT_CATALOG_PATH) -> BuildPlan:
    """Resolve one supported profile to a complete build plan."""
    catalog = load_catalog(catalog_path)
    selected = profile or catalog.default_profile
    try:
        resolved_profile = catalog.profiles[selected]
    except KeyError as error:
        raise CatalogError(f"unsupported ROCm profile '{selected}'") from error
    if len(resolved_profile.targets) != 1:
        raise CatalogError(f"profile '{selected}' must reference exactly one target to produce a BuildPlan")
    resolved = catalog.targets[resolved_profile.targets[0]]
    return BuildPlan(
        profile=resolved_profile.name,
        tag_suffix=resolved_profile.tag_suffix,
        target=resolved.name,
        rocm_version=catalog.rocm_version,
        rocm_package=resolved.rocm_package,
        torch_extra=resolved.torch_extra,
        torchvision_extra=resolved.torchvision_extra,
        torch_version=catalog.torch_version,
        torchvision_version=catalog.torchvision_version,
        torchaudio_version=catalog.torchaudio_version,
        wheel_requirements=(
            resolved.torch_requirement,
            resolved.torchvision_requirement,
            resolved.torchaudio_requirement,
        ),
        apt_key_url=catalog.apt_key_url,
        apt_source=catalog.apt_source,
        wheel_index_url=catalog.wheel_index_url,
        provenance=catalog.provenance,
    )
