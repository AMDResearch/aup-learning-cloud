# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""AMD GPU detection and SKU resolution.

Mirrors the bash version's behavior bit-for-bit:
  1. Try ``rocminfo`` for marketing names of GPU agents (filtered by
     "Device Type: GPU" so AMD CPUs do not bleed in).
  2. Fall back to ``/sys/class/drm/card*/device/product_name`` from the
     amdgpu driver.
  3. If both fail, derive a gfx target from rocminfo or KFD topology
     (handling both hex-packed and decimal encodings).
  4. After helm install, re-read ROCm labeller node labels for the
     authoritative product names.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple

from auplc_installer.rocm_profiles import CatalogError, load_catalog, resolve_profile
from auplc_installer.util import InstallerError, command_exists, log, run_capture


# ---------------------------------------------------------------------------
# Curated SKU table — keep accelerator keys in sync with runtime/values.yaml.
# ---------------------------------------------------------------------------
class SkuRow(NamedTuple):
    """Curated accelerator selection and its canonical image profile."""

    accelerator_key: str
    image_profile: str
    accelerator_env: str
    quota_rate: int
    display_name: str


PRODUCT_NAME_TO_SKU: dict[str, SkuRow] = {
    "AMD_Radeon_780M_Graphics": SkuRow("phx", "gfx1103", "", 2, "AMD Radeon 780M (Phoenix iGPU)"),
    "AMD_Radeon_890M_Graphics": SkuRow("strix", "gfx1150", "", 2, "AMD Radeon 890M (Strix iGPU)"),
    "AMD_Radeon_8060S_Graphics": SkuRow("strix-halo", "gfx1151", "", 3, "AMD Radeon 8060S (Strix Halo iGPU)"),
    "AMD_Radeon_RX_9060": SkuRow("9060", "gfx1200", "", 4, "AMD Radeon RX 9060"),
    "AMD_Radeon_RX_9060_XT": SkuRow("9060xt", "gfx1200", "", 4, "AMD Radeon RX 9060 XT"),
    "AMD_Radeon_RX_9070": SkuRow("9070", "gfx1201", "", 4, "AMD Radeon RX 9070"),
    "AMD_Radeon_RX_9070_XT": SkuRow("9070xt", "gfx1201", "", 4, "AMD Radeon RX 9070 XT"),
    "AMD_Radeon_AI_PRO_R9700": SkuRow("r9700", "gfx1201", "", 4, "AMD Radeon AI PRO R9700"),
}


ACCELERATOR_CONFIGS: dict[str, SkuRow] = {row.accelerator_key: row for row in PRODUCT_NAME_TO_SKU.values()}
CURATED_ACCELERATOR_KEYS = tuple(ACCELERATOR_CONFIGS)


def is_curated_accelerator(key: str) -> bool:
    """Return whether an accelerator is defined by the curated product policy."""
    return key in ACCELERATOR_CONFIGS


# ---------------------------------------------------------------------------
# Accelerator and raw-gfx resolution
# ---------------------------------------------------------------------------


def normalise_gpu_type_key(input_key: str) -> str:
    """Normalise CLI accelerator keys and raw detected gfx target values."""
    key = input_key.strip().lower().replace("_", "-")
    m = re.fullmatch(r"gfx-?([0-9]+)", key)
    if m:
        return f"gfx{m.group(1)}"
    return key


def _validated_row(row: SkuRow) -> SkuRow:
    """Validate and canonicalize a configured profile through the catalog."""
    try:
        plan = resolve_profile(row.image_profile)
    except CatalogError as error:
        raise InstallerError(str(error)) from error
    return row._replace(image_profile=plan.profile)


def resolve_gpu_config(input_key: str) -> SkuRow:
    """Resolve an accelerator key or an unambiguous raw gfx target to a SKU row."""
    key = normalise_gpu_type_key(input_key)
    row = ACCELERATOR_CONFIGS.get(key)
    if row is not None:
        return _validated_row(row)

    try:
        profile = resolve_profile(key).profile
    except CatalogError as error:
        supported = ", ".join(CURATED_ACCELERATOR_KEYS)
        raise InstallerError(
            f"Unsupported accelerator or image profile: {input_key}\n  Supported accelerators: {supported}"
        ) from error

    matches = [row for row in ACCELERATOR_CONFIGS.values() if row.image_profile == profile]
    if len(matches) == 1:
        return _validated_row(matches[0])
    if not matches:
        raise InstallerError(
            f"Detected gfx target '{input_key}' resolves to valid build-only image profile '{profile}', "
            "which has no supported runtime accelerator."
        )
    accelerators = ", ".join(row.accelerator_key for row in matches)
    raise InstallerError(
        f"Detected gfx target '{input_key}' resolves to image profile '{profile}', "
        f"which matches multiple accelerators: {accelerators}.\n"
        "  Re-run with --gpu=<accelerator> to select one explicitly."
    )


# ---------------------------------------------------------------------------
# Product-name detection
# ---------------------------------------------------------------------------


def normalise_product_name(raw: str) -> str:
    """Match the ROCm labeller's ``amd.com/gpu.product-name`` formatting.

    The labeller replaces whitespace runs with ``_`` and strips characters
    that are not valid in a Kubernetes label value. Trailing/leading
    underscores are also dropped.
    See https://github.com/ROCm/k8s-device-plugin/tree/master/cmd/k8s-node-labeller
    """
    s = re.sub(r"\s+", "_", raw)
    s = re.sub(r"[^A-Za-z0-9._-]", "", s)
    return s.strip("_")


def _append_unique(out: list[str], seen: set[str], value: str) -> None:
    if value and value not in seen:
        seen.add(value)
        out.append(value)


def _rocminfo_gpu_agent_records(text: str) -> list[tuple[str, list[str]]]:
    """Return ``(marketing_name, gfx_targets)`` records for GPU agents.

    ROCm reports the GPU agent ``Name`` from the ISA processor target and the
    ``Marketing Name`` from a separate product/branding field. Keep the parser
    scoped to ``Device Type: GPU`` blocks so CPU/APU marketing names do not
    influence image-tag selection.
    """
    records: list[tuple[str, list[str]]] = []
    in_agent = False
    in_isa = False
    device_type = ""
    agent_name = ""
    marketing = ""
    isa_targets: list[str] = []

    def gfx_from(value: str) -> str:
        m = re.search(r"\bgfx[0-9]{3,4}\b", value)
        return m.group(0) if m else ""

    def flush() -> None:
        if not in_agent or device_type != "GPU":
            return
        targets: list[str] = []
        seen_targets: set[str] = set()
        for target in isa_targets:
            _append_unique(targets, seen_targets, target)
        _append_unique(targets, seen_targets, gfx_from(agent_name))
        records.append((marketing, targets))

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if re.match(r"^Agent\s+\d+\b", line):
            flush()
            in_agent = True
            in_isa = False
            device_type = ""
            agent_name = ""
            marketing = ""
            isa_targets = []
            continue
        if not in_agent:
            continue
        if line.startswith("ISA Info:"):
            in_isa = True
            continue
        if line.startswith("Device Type:"):
            device_type = line.split(":", 1)[1].strip()
            continue
        if line.startswith("Marketing Name:"):
            marketing = line.split(":", 1)[1].strip()
            continue
        if line.startswith("Name:"):
            value = line.split(":", 1)[1].strip()
            if in_isa:
                target = gfx_from(value)
                if target:
                    isa_targets.append(target)
            elif not agent_name:
                agent_name = value

    flush()
    return records


def detect_gpu_product_names() -> list[str]:
    """All distinct AMD GPU product names on this host (labeller-normalised)."""
    out: list[str] = []
    seen: set[str] = set()

    # 1. rocminfo: track the most recent "Marketing Name" before each
    #    "Device Type"; commit only when device type is GPU.
    if command_exists("rocminfo"):
        try:
            res = run_capture(["rocminfo"], check=False, stderr_to_stdout=True)
            text = res.stdout or ""
        except Exception:
            text = ""
        for marketing, _ in _rocminfo_gpu_agent_records(text):
            name = normalise_product_name(marketing)
            _append_unique(out, seen, name)

    # 2. amdgpu sysfs (no ROCm dependency).
    for f in sorted(Path("/sys/class/drm").glob("card*/device/product_name")):
        try:
            raw = f.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not raw:
            continue
        name = normalise_product_name(raw)
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def detect_gpu_gfx_target() -> str | None:
    """Best-effort concrete gfx target detection. Used as fallback only.

    Returns a gfx family string (e.g. ``gfx1151``) or None when nothing
    can be determined.
    """
    if command_exists("rocminfo"):
        try:
            res = run_capture(["rocminfo"], check=False, stderr_to_stdout=True)
            for _, targets in _rocminfo_gpu_agent_records(res.stdout or ""):
                if targets:
                    return targets[0]
        except Exception:
            pass

    # KFD topology fallback. ``gfx_target_version`` uses two encodings:
    #   - hex-packed (kernel <6.14):  0x0B0501 = 722177  → 11, 5, 1   → gfx1151
    #   - decimal     (kernel ≥6.14):  110501             → 11, 05, 01 → gfx1151
    # Hex-packed values for any GPU (major≥9) start at 0x090000 = 589824;
    # the largest decimal value for current GPUs is ~120201. We pick 200000
    # as the threshold to disambiguate.
    for prop_path in sorted(Path("/sys/class/kfd/kfd/topology/nodes").glob("*/properties")):
        try:
            text = prop_path.read_text(encoding="utf-8")
        except OSError:
            continue
        for raw_line in text.splitlines():
            parts = raw_line.split()
            if len(parts) >= 2 and parts[0] == "gfx_target_version":
                try:
                    val = int(parts[1])
                except ValueError:
                    continue
                if val <= 0:
                    continue
                if val >= 200000:
                    major = (val >> 16) & 0xFF
                    minor = (val >> 8) & 0xFF
                    stepping = val & 0xFF
                else:
                    major = val // 10000
                    minor = (val // 100) % 100
                    stepping = val % 100
                return f"gfx{major}{minor}{stepping}"
    return None


# ---------------------------------------------------------------------------
# State container
# ---------------------------------------------------------------------------


@dataclass
class SkuEntry:
    """One detected SKU.  Multiple entries cohabit on multi-GPU hosts."""

    accelerator_key: str
    product_name: str  # labeller-normalised, may be empty for raw-gfx fallback
    image_profile: str
    accelerator_env: str
    quota_rate: int
    display_name: str  # may be empty for curated rows


@dataclass
class GpuConfig:
    """Aggregate detection result.

    ``primary`` mirrors index 0 of ``skus`` and is what image tagging,
    offline-bundle manifest.json and CLI status messages use.
    """

    skus: list[SkuEntry] = field(default_factory=list)
    accelerator_key: str = ""
    image_profile: str = ""
    accelerator_env: str = ""
    gpu_product_name: str = ""
    fallback_accelerator_key: str = ""
    pinned_image_profile: str = ""
    fallback_accelerator_env: str = ""
    offline_pin_validated: bool = False

    def reset(self) -> None:
        self.skus = []
        self.accelerator_key = ""
        self.image_profile = ""
        self.accelerator_env = ""
        self.gpu_product_name = ""

    def append(self, entry: SkuEntry) -> None:
        for existing in self.skus:
            if existing.accelerator_key == entry.accelerator_key:
                return
        self.skus.append(entry)
        if not self.accelerator_key:
            # First entry drives the primary scalars.
            self.accelerator_key = entry.accelerator_key
            self.image_profile = entry.image_profile
            self.accelerator_env = entry.accelerator_env
            self.gpu_product_name = entry.product_name

    @property
    def homogeneous_profile(self) -> bool:
        """True when every detected SKU shares the primary image profile."""
        if not self.skus:
            return True
        return all(s.image_profile == self.image_profile for s in self.skus)

    @property
    def has_offline_pin(self) -> bool:
        """Whether this configuration has an offline bundle profile contract."""
        return bool(self.pinned_image_profile)


# ---------------------------------------------------------------------------
# SKU row factory
# ---------------------------------------------------------------------------


def sku_for_product_name(product: str) -> SkuRow:
    """Resolve a supported labeller product name to its canonical profile."""
    try:
        row = PRODUCT_NAME_TO_SKU[product]
    except KeyError as error:
        supported = ", ".join(PRODUCT_NAME_TO_SKU)
        raise InstallerError(
            f"Unsupported AMD GPU product '{product}'.\n  Supported ROCm labeller products: {supported}"
        ) from error
    return _validated_row(row)


def sku_for_detected_product(product: str, detected_gfx_target: str = "") -> SkuRow:
    """Resolve a detected product without treating raw gfx data as a product alias."""
    try:
        return sku_for_product_name(product)
    except InstallerError as error:
        if detected_gfx_target:
            raise InstallerError(f"{error}\n  Detected gfx target: {detected_gfx_target}") from error
        raise


def append_product(cfg: GpuConfig, product: str, detected_gfx_target: str = "") -> None:
    """Resolve a product name and append it as an SKU entry."""
    if not product:
        return
    row = sku_for_detected_product(product, detected_gfx_target)
    cfg.append(
        SkuEntry(
            accelerator_key=row.accelerator_key,
            product_name=product,
            image_profile=row.image_profile,
            accelerator_env=row.accelerator_env,
            quota_rate=row.quota_rate,
            display_name=row.display_name,
        )
    )


# ---------------------------------------------------------------------------
# Top-level detection / refinement
# ---------------------------------------------------------------------------


def detect_and_configure_gpu(cfg: GpuConfig, gpu_type_override: str = "") -> None:
    """Populate ``cfg`` from host detection.

    Re-entrant: a previously detected configuration is left unchanged. Offline
    manifest pins are recorded separately, so they never suppress initial host
    detection.
    """
    if cfg.skus:
        return

    pinned_profile = cfg.pinned_image_profile
    fallback_key = cfg.fallback_accelerator_key
    cfg.accelerator_key = ""
    cfg.image_profile = ""
    cfg.accelerator_env = ""
    cfg.gpu_product_name = ""

    names = detect_gpu_product_names()
    detected_gfx_target = ""
    if len(names) == 1 and names[0] not in PRODUCT_NAME_TO_SKU:
        detected_gfx_target = detect_gpu_gfx_target() or ""
    if names:
        log("Detected GPU product name(s) from host:")
        for name in names:
            log(f"  - {name}")
            append_product(cfg, name, detected_gfx_target)

    host_facts_available = bool(names)
    if not cfg.skus:
        if gpu_type_override:
            log(f"Using GPU type override: {gpu_type_override}")
            input_key = gpu_type_override
        else:
            raw_gfx_target = detected_gfx_target or detect_gpu_gfx_target()
            if raw_gfx_target:
                log(f"Detected GPU gfx target: {raw_gfx_target}")
                if cfg.has_offline_pin:
                    pinned_targets = load_catalog().profiles[pinned_profile].targets
                    target = normalise_gpu_type_key(raw_gfx_target)
                    if target not in pinned_targets:
                        raise InstallerError(
                            f"Offline bundle profile pin {pinned_profile} is incompatible with "
                            f"detected GPU gfx target {raw_gfx_target}."
                        )
                    row = resolve_gpu_config(fallback_key)
                    cfg.append(
                        SkuEntry(
                            accelerator_key=row.accelerator_key,
                            product_name="",
                            image_profile=row.image_profile,
                            accelerator_env=cfg.fallback_accelerator_env,
                            quota_rate=row.quota_rate,
                            display_name=row.display_name,
                        )
                    )
                    host_facts_available = True
                    input_key = ""
                else:
                    input_key = raw_gfx_target
                    host_facts_available = True
            elif cfg.has_offline_pin:
                row = resolve_gpu_config(fallback_key)
                cfg.append(
                    SkuEntry(
                        accelerator_key=row.accelerator_key,
                        product_name="",
                        image_profile=row.image_profile,
                        accelerator_env=cfg.fallback_accelerator_env,
                        quota_rate=row.quota_rate,
                        display_name=row.display_name,
                    )
                )
                log(
                    "GPU host facts unavailable; using offline manifest fallback accelerator provisionally "
                    f"({fallback_key}/{pinned_profile})."
                )
                host_facts_available = False
                input_key = ""
            else:
                input_key = "strix-halo"
                log("GPU not detected, defaulting to strix-halo (gfx1151)")
        if input_key:
            row = resolve_gpu_config(input_key)
            cfg.append(
                SkuEntry(
                    accelerator_key=row.accelerator_key,
                    product_name="",
                    image_profile=row.image_profile,
                    accelerator_env=row.accelerator_env,
                    quota_rate=row.quota_rate,
                    display_name=row.display_name,
                )
            )

    if cfg.has_offline_pin and any(sku.image_profile != pinned_profile for sku in cfg.skus):
        raise InstallerError(
            f"Offline bundle profile pin {pinned_profile} is incompatible with "
            f"detected accelerator {cfg.accelerator_key}/{cfg.image_profile}."
        )
    if cfg.has_offline_pin and host_facts_available:
        cfg.offline_pin_validated = True

    log(
        f"  primary accelerator={cfg.accelerator_key}, image_profile={cfg.image_profile}"
        + (f", HSA_OVERRIDE={cfg.accelerator_env}" if cfg.accelerator_env else "")
    )
    if len(cfg.skus) > 1:
        extras = " ".join(s.accelerator_key for s in cfg.skus[1:])
        log(f"  additional SKUs: {extras}")


# ---------------------------------------------------------------------------
# Cluster-side refinement (after the labeller is up)
# ---------------------------------------------------------------------------


def _read_gpu_product_names_from_node_labels() -> list[str]:
    """Parse all distinct product names from current node labels.

    Prefers ``beta.amd.com/gpu.product-name.<NAME>=<count>`` (which the
    labeller emits per-product on multi-GPU nodes); falls back to the
    scalar ``amd.com/gpu.product-name`` label for single-GPU hosts.
    """
    if not command_exists("kubectl"):
        return []
    # First, make sure kubectl can reach the cluster at all.
    try:
        run_capture(["kubectl", "get", "nodes", "-o", "name"], check=True)
    except Exception:
        return []

    seen: set[str] = set()
    out: list[str] = []

    # beta.amd.com/gpu.product-name.<PRODUCT>=<count>
    try:
        res = run_capture(["kubectl", "get", "nodes", "-o", "yaml"], check=False)
        text = res.stdout or ""
    except Exception:
        text = ""
    for m in re.finditer(r"beta\.amd\.com/gpu\.product-name\.([A-Za-z0-9_.-]+)", text):
        name = m.group(1)
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    if out:
        return out

    # Fallback: scalar amd.com/gpu.product-name (one product per node).
    try:
        res = run_capture(
            [
                "kubectl",
                "get",
                "nodes",
                "-o",
                r'jsonpath={range .items[*]}{.metadata.labels.amd\.com/gpu\.product-name}{"\n"}{end}',
            ],
            check=False,
        )
        text = res.stdout or ""
    except Exception:
        text = ""
    for raw in text.splitlines():
        name = raw.strip()
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def refine_gpu_config_from_node_labels(cfg: GpuConfig) -> None:
    """Replace the SKU list with the labeller's authoritative version.

    Safe to call from any code path holding a working ``kubectl``. An offline
    manifest pin that lacks host validation requires labeller labels before
    installation can proceed.
    """
    names = _read_gpu_product_names_from_node_labels()
    if not names:
        if cfg.has_offline_pin and not cfg.offline_pin_validated:
            raise InstallerError(
                "Offline bundle pin could not be validated: GPU host facts and ROCm labeller labels are unavailable."
            )
        return

    prev_keys = " ".join(s.accelerator_key for s in cfg.skus)

    refreshed = GpuConfig()
    for n in names:
        append_product(refreshed, n)

    if cfg.has_offline_pin and any(sku.image_profile != cfg.pinned_image_profile for sku in refreshed.skus):
        profiles = ", ".join(sorted({sku.image_profile for sku in refreshed.skus}))
        raise InstallerError(
            f"Offline bundle profile pin {cfg.pinned_image_profile} "
            f"is incompatible with ROCm labeller profile(s): {profiles}."
        )

    cfg.skus = refreshed.skus
    cfg.accelerator_key = refreshed.accelerator_key
    cfg.image_profile = refreshed.image_profile
    cfg.accelerator_env = refreshed.accelerator_env
    cfg.gpu_product_name = refreshed.gpu_product_name

    log("Refreshed GPU SKUs from node labels (ROCm labeller is authoritative):")
    log("  product names    : " + ", ".join(names))
    log("  resolved accelerator keys: " + " ".join(s.accelerator_key for s in cfg.skus))

    if cfg.has_offline_pin:
        cfg.offline_pin_validated = True
        if not cfg.accelerator_env and cfg.fallback_accelerator_env:
            cfg.accelerator_env = cfg.fallback_accelerator_env

    new_keys = " ".join(s.accelerator_key for s in cfg.skus)
    if prev_keys != new_keys:
        log(f"  SKU list changed: [{prev_keys}] → [{new_keys}]")
