# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.

from dataclasses import dataclass
from pathlib import Path

from gpu_resolution_parsing import (
    configured_path,
    parse_gpu_inventory,
    parse_gpu_resolution,
    parse_pxe_gpu_policy,
    validate_direct_gpu_inventory,
)


@dataclass(frozen=True, slots=True)
class GpuArtifactValidationRequest:
    repo: Path
    inventory_path: str
    resolution_path: str
    topology: str
    pxe_vars_path: Path
    has_prior_errors: bool


@dataclass(frozen=True, slots=True)
class GpuArtifactValidationResult:
    errors: list[str]
    passed: list[str]


@dataclass(frozen=True, slots=True)
class AcceleratorValidationResult:
    errors: list[str]
    warnings: list[str]
    passed: list[str]


def check_gpu_inventory(repo: Path, inventory_path: str) -> GpuArtifactValidationResult:
    inventory_file = configured_path(repo, inventory_path)
    if not inventory_file.exists():
        return GpuArtifactValidationResult([f"inventory not found: {inventory_file}"], [])
    errors = validate_direct_gpu_inventory(inventory_file.read_text(encoding="utf-8"))
    return GpuArtifactValidationResult(errors, [] if errors else ["GPU access inventory is valid"])


def check_accelerator_labels(
    accelerators: dict[str, str], metadata: dict[str, list[str]], cluster: dict | None
) -> AcceleratorValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    passed: list[str] = []
    active_keys = sorted({key for keys in metadata.values() for key in keys})
    if not active_keys:
        return AcceleratorValidationResult([], ["no acceleratorKeys found in effective custom.resources.metadata"], [])
    declared: list[str] = []
    for key in active_keys:
        if key not in accelerators:
            errors.append(f"active accelerator '{key}' is not defined under custom.accelerators")
        elif not accelerators[key]:
            errors.append(f"active accelerator '{key}' has no amd.com/gpu.product-name nodeSelector")
        else:
            declared.append(accelerators[key])
    if not declared:
        return AcceleratorValidationResult(errors, warnings, passed)
    if cluster is None:
        warnings.append(
            "no --cluster snapshot; cannot confirm nodeSelector labels match real "
            f"nodes. Declared: {', '.join(declared)}"
        )
        return AcceleratorValidationResult(errors, warnings, passed)
    real = set(cluster.get("gpu_product_names", []))
    if not real:
        errors.append("cluster snapshot has no GPU product labels for active accelerators")
        return AcceleratorValidationResult(errors, warnings, passed)
    for declared_label in declared:
        if declared_label in real:
            passed.append(f"nodeSelector '{declared_label}' matches a real node label")
        else:
            errors.append(
                f"nodeSelector '{declared_label}' matches no node label. Real labels: {', '.join(sorted(real))}"
            )
    return AcceleratorValidationResult(errors, warnings, passed)


def check_gpu_artifacts(request: GpuArtifactValidationRequest) -> GpuArtifactValidationResult:
    errors: list[str] = []
    inventory_file = configured_path(request.repo, request.inventory_path)
    resolution_file = configured_path(request.repo, request.resolution_path)
    if not inventory_file.exists():
        return GpuArtifactValidationResult([f"generated inventory not found: {inventory_file}"], [])
    if not resolution_file.exists():
        return GpuArtifactValidationResult([f"GPU resolution manifest not found: {resolution_file}"], [])
    inventory, inventory_errors = parse_gpu_inventory(inventory_file.read_text(encoding="utf-8"))
    resolution, resolution_errors = parse_gpu_resolution(resolution_file.read_text(encoding="utf-8"), request.topology)
    errors.extend([*inventory_errors, *resolution_errors])
    if inventory is None or resolution is None or errors:
        return GpuArtifactValidationResult(errors, [])
    if set(inventory.hosts) != set(resolution.hosts):
        errors.append("inventory hosts do not exactly match GPU resolution manifest hosts")
    for host, enabled in inventory.hosts.items():
        if resolution.hosts.get(host) != enabled:
            errors.append(f"inventory host '{host}' GPU access boolean disagrees with the resolution manifest")
    pxe_policy = None
    if request.topology == "pxe-diskless":
        if not request.pxe_vars_path.exists():
            return GpuArtifactValidationResult([*errors, f"PXE vars file not found: {request.pxe_vars_path}"], [])
        pxe_policy, pxe_errors = parse_pxe_gpu_policy(request.pxe_vars_path.read_text(encoding="utf-8"))
        errors.extend(pxe_errors)
        if pxe_policy is None or pxe_errors:
            return GpuArtifactValidationResult(errors, [])
        if pxe_policy.enabled != resolution.pxe_rootfs_enabled:
            errors.append("PXE pxe_gpu_access_enabled disagrees with GPU resolution manifest pxe_rootfs")
    if resolution.status == "cpu_only":
        if any(resolution.hosts.values()):
            errors.append("cpu_only GPU resolution requires all host booleans false")
    elif not any(resolution.hosts.values()):
        errors.append("gpu_resolved GPU resolution requires an enabled host")
    passed = [] if request.has_prior_errors or errors else ["GPU access artifacts agree"]
    return GpuArtifactValidationResult(errors, passed)
