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

from auplc_installer.util import InstallerError, command_exists, log, run_capture

# ---------------------------------------------------------------------------
# Curated SKU table  — keep accel_key in sync with runtime/values.yaml
# custom.accelerators.*. Rows that are NOT in values.yaml use display_name
# when the installer injects a minimal stanza in the overlay.
#
# Tuple layout: (accel_key, gpu_target, accel_env, quota_rate, display_name)
# ---------------------------------------------------------------------------
SkuRow = tuple[str, str, str, int, str]

PRODUCT_NAME_TO_SKU: dict[str, SkuRow] = {
    "AMD_Radeon_780M_Graphics": ("phx", "gfx110x", "11.0.0", 2, "AMD Radeon 780M (Phoenix Point iGPU)"),
    "AMD_Radeon_890M_Graphics": ("strix", "gfx1150", "", 2, "AMD Radeon 890M (Strix Point iGPU)"),
    "AMD_Radeon_8060S_Graphics": ("strix-halo", "gfx1151", "", 3, "AMD Radeon 8060S (Strix Halo iGPU)"),
    "AMD_Radeon_9070XT": ("9070xt", "gfx120x", "", 4, "AMD Radeon RX 9070 XT"),
    "AMD_Radeon_RX_9070_XT": ("9070xt", "gfx120x", "", 4, "AMD Radeon RX 9070 XT"),
    "AMD_Radeon_RX_9070XT": ("9070xt", "gfx120x", "", 4, "AMD Radeon RX 9070 XT"),
    "AMD_Radeon_AI_PRO_R9700": ("r9700", "gfx120x", "", 4, "AMD Radeon AI PRO R9700"),
    "AMD_Radeon_RX_9600_GRE": ("9600gre", "gfx120x", "", 4, "AMD Radeon RX 9600 GRE"),
    "AMD_Radeon_9600_GRE": ("9600gre", "gfx120x", "", 4, "AMD Radeon RX 9600 GRE"),
    "AMD_Radeon_RX_9600GRE": ("9600gre", "gfx120x", "", 4, "AMD Radeon RX 9600 GRE"),
}


# Accelerator keys defined in runtime/values.yaml custom.accelerators. When
# the resolved accel_key is not in this list, ``overlay.py`` injects a full
# minimal accelerator stanza so helm install succeeds without values.yaml
# edits (useful for ad-hoc SKUs not yet promoted to the default values).
GPU_CURATED_SKU_KEYS = ("phx", "strix", "strix-halo", "9070xt", "r9700", "9600gre")


def is_curated_sku(key: str) -> bool:
    return key in GPU_CURATED_SKU_KEYS


# ---------------------------------------------------------------------------
# gfx-family fallback table (used when product-name detection fails)
# ---------------------------------------------------------------------------

# Quota rates here MUST stay in sync with PRODUCT_NAME_TO_SKU above (and with
# runtime/values.yaml custom.accelerators.<key>.quotaRate) so that whether the
# user lands on the curated path (rocminfo / sysfs found a known marketing
# name) or the gfx-family fallback path (only kernel reports a gfx target),
# the resulting overlay is identical for the same physical GPU.
_GFX_FALLBACK: dict[str, SkuRow] = {
    # phx covers gfx1100..gfx1103
    "phx": ("phx", "gfx110x", "11.0.0", 2, ""),
    "gfx1100": ("phx", "gfx110x", "11.0.0", 2, ""),
    "gfx1101": ("phx", "gfx110x", "11.0.0", 2, ""),
    "gfx1102": ("phx", "gfx110x", "11.0.0", 2, ""),
    "gfx1103": ("phx", "gfx110x", "11.0.0", 2, ""),
    "strix": ("strix", "gfx1150", "", 2, ""),
    "gfx1150": ("strix", "gfx1150", "", 2, ""),
    "strix-halo": ("strix-halo", "gfx1151", "", 3, ""),
    "gfx1151": ("strix-halo", "gfx1151", "", 3, ""),
    "rdna4": ("r9700", "gfx120x", "", 4, ""),
    "dgpu": ("r9700", "gfx120x", "", 4, ""),
    "gfx1200": ("r9700", "gfx120x", "", 4, ""),
    "gfx1201": ("r9700", "gfx120x", "", 4, ""),
    "9070xt": ("9070xt", "gfx120x", "", 4, ""),
    "r9700": ("r9700", "gfx120x", "", 4, ""),
    "9600gre": ("9600gre", "gfx120x", "", 4, ""),
}


def normalise_gpu_type_key(input_key: str) -> str:
    """Normalise CLI/detected GPU type aliases to fallback-table keys."""
    key = input_key.strip().lower().replace("_", "-")
    m = re.fullmatch(r"gfx-?([0-9]+)", key)
    if m:
        return f"gfx{m.group(1)}"
    return key


def resolve_gpu_config(input_key: str) -> SkuRow:
    """Map a user-supplied GPU type or detected gfx family to a SKU row.

    Raises :class:`InstallerError` for unsupported inputs.
    """
    key = normalise_gpu_type_key(input_key)
    row = _GFX_FALLBACK.get(key)
    if row is None:
        raise InstallerError(
            f"Unsupported GPU type: {input_key}\n"
            "  Supported: phx (gfx1100-1103), strix (gfx1150), strix-halo (gfx1151), "
            "RDNA4 SKUs (9070xt | r9700 | 9600gre | dgpu fallback)"
        )
    return row


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


def detect_gpu_gfx_family() -> str | None:
    """Best-effort gfx target detection. Used as fallback only.

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

    accel_key: str
    product_name: str  # labeller-normalised, may be empty for gfx-family fallback
    gpu_target: str
    accel_env: str
    quota_rate: int
    display_name: str  # may be empty for curated rows


@dataclass
class GpuConfig:
    """Aggregate detection result.

    ``primary`` mirrors index 0 of ``skus`` and is what image tagging,
    offline-bundle manifest.json and CLI status messages use.
    """

    skus: list[SkuEntry] = field(default_factory=list)
    accel_key: str = ""
    gpu_target: str = ""
    accel_env: str = ""
    gpu_product_name: str = ""

    def reset(self) -> None:
        self.skus = []
        self.accel_key = ""
        self.gpu_target = ""
        self.accel_env = ""
        self.gpu_product_name = ""

    def append(self, entry: SkuEntry) -> None:
        for existing in self.skus:
            if existing.accel_key == entry.accel_key:
                return
        self.skus.append(entry)
        if not self.accel_key:
            # First entry drives the primary scalars.
            self.accel_key = entry.accel_key
            self.gpu_target = entry.gpu_target
            self.accel_env = entry.accel_env
            self.gpu_product_name = entry.product_name

    @property
    def homogeneous_target(self) -> bool:
        """True when every detected SKU shares the primary gfx target."""
        if not self.skus:
            return True
        return all(s.gpu_target == self.gpu_target for s in self.skus)


# ---------------------------------------------------------------------------
# SKU row factory
# ---------------------------------------------------------------------------


def _synthesise_uncurated_row(product: str) -> SkuRow:
    """Default stanza for products that are not in PRODUCT_NAME_TO_SKU.

    Safe defaults: gfx120x image target, no HSA override, quotaRate 4.
    Users hitting this path should add their SKU to PRODUCT_NAME_TO_SKU
    (and ideally to runtime/values.yaml) for a first-class experience.
    """
    display = product.replace("_", " ") or "AMD GPU"
    key = re.sub(r"[^a-z0-9-]", "-", product.lower())
    key = re.sub(r"-{2,}", "-", key).strip("-") or "amd-gpu"
    return (key, "gfx120x", "", 4, display)


def sku_for_product_name(product: str) -> SkuRow:
    """Return curated row, falling back to a synthesised one when unknown."""
    return PRODUCT_NAME_TO_SKU.get(product) or _synthesise_uncurated_row(product)


def sku_for_detected_product(product: str, gfx_family: str = "") -> SkuRow:
    """Resolve a detected product, using gfx family before generic fallback.

    Some ROCm/sysfs stacks report a generic marketing name for Strix-class
    APUs. When a precise gfx family is available, prefer it over the generic
    future-GPU fallback so single-node local builds keep the correct image tag.
    """
    row = PRODUCT_NAME_TO_SKU.get(product)
    if row is not None:
        return row
    if gfx_family:
        try:
            return resolve_gpu_config(gfx_family)
        except InstallerError:
            pass
    return _synthesise_uncurated_row(product)


def append_product(cfg: GpuConfig, product: str, gfx_family: str = "") -> None:
    """Resolve a product name and append it as an SKU entry."""
    if not product:
        return
    accel_key, gpu_target, env, rate, display = sku_for_detected_product(product, gfx_family)
    cfg.append(
        SkuEntry(
            accel_key=accel_key,
            product_name=product,
            gpu_target=gpu_target,
            accel_env=env,
            quota_rate=rate,
            display_name=display,
        )
    )


# ---------------------------------------------------------------------------
# Top-level detection / refinement
# ---------------------------------------------------------------------------


def detect_and_configure_gpu(cfg: GpuConfig, gpu_type_override: str = "") -> None:
    """Populate ``cfg`` from host detection.

    Re-entrant: when ``cfg.skus`` is non-empty (e.g. seeded by an offline
    bundle's manifest.json) this is a no-op, preserving the bundle's pinned
    primary scalars.
    """
    if cfg.skus:
        return

    # Honour pinned scalars (e.g. from offline-bundle manifest). They get
    # restored at the end if host detection produced different values for
    # the primary entry, since the bundle was packed for a specific gfx
    # family and image tag and we must not silently drift.
    pinned_key = cfg.accel_key
    pinned_target = cfg.gpu_target
    pinned_env = cfg.accel_env
    cfg.accel_key = ""
    cfg.gpu_target = ""
    cfg.accel_env = ""
    cfg.gpu_product_name = ""

    names = detect_gpu_product_names()
    detected_gfx = ""
    if len(names) == 1 and names[0] not in PRODUCT_NAME_TO_SKU:
        detected_gfx = detect_gpu_gfx_family() or ""
    if names:
        log("Detected GPU product name(s) from host:")
        for name in names:
            log(f"  - {name}")
            append_product(cfg, name, detected_gfx)

    if not cfg.skus:
        if gpu_type_override:
            log(f"Using GPU type override: {gpu_type_override}")
            input_key = gpu_type_override
        else:
            gfx = detected_gfx or detect_gpu_gfx_family()
            if gfx:
                log(f"Detected GPU: {gfx}")
                input_key = gfx
            else:
                input_key = "strix-halo"
                log("GPU not detected, defaulting to strix-halo (gfx1151)")
        accel_key, gpu_target, env, rate, display = resolve_gpu_config(input_key)
        cfg.append(
            SkuEntry(
                accel_key=accel_key,
                product_name="",
                gpu_target=gpu_target,
                accel_env=env,
                quota_rate=rate,
                display_name=display,
            )
        )

    # Restore manifest-pinned primary if it diverged from host detection.
    if pinned_target and pinned_target != cfg.gpu_target:
        log(
            f"Note: offline bundle was packed for {pinned_key}/{pinned_target}; "
            f"host detected primary={cfg.accel_key}/{cfg.gpu_target}."
        )
        log(f"      Keeping bundle image tag ({pinned_target}); acceleratorKeys reflect host SKUs.")
        cfg.accel_key = pinned_key
        cfg.gpu_target = pinned_target
        cfg.accel_env = pinned_env

    log(
        f"  primary accelerator={cfg.accel_key}, GPU_TARGET={cfg.gpu_target}"
        + (f", HSA_OVERRIDE={cfg.accel_env}" if cfg.accel_env else "")
    )
    if len(cfg.skus) > 1:
        extras = " ".join(s.accel_key for s in cfg.skus[1:])
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

    Safe to call from any code path holding a working ``kubectl``; no-op
    when kubectl is missing or labels are unavailable.
    """
    names = _read_gpu_product_names_from_node_labels()
    if not names:
        return

    prev_keys = " ".join(s.accel_key for s in cfg.skus)
    pinned_target = cfg.gpu_target
    pinned_env = cfg.accel_env

    cfg.reset()
    for n in names:
        append_product(cfg, n, pinned_target)

    log("Refreshed GPU SKUs from node labels (ROCm labeller is authoritative):")
    log("  product names    : " + ", ".join(names))
    log("  resolved SKU keys: " + " ".join(s.accel_key for s in cfg.skus))

    if pinned_target and pinned_target != cfg.gpu_target:
        log(f"  note: image target was {pinned_target}, labeller-refined primary is {cfg.gpu_target}")
    # Preserve HSA override if labeller refinement erased it (e.g. phx with no rocminfo).
    if not cfg.accel_env and pinned_env:
        cfg.accel_env = pinned_env

    new_keys = " ".join(s.accel_key for s in cfg.skus)
    if prev_keys != new_keys:
        log(f"  SKU list changed: [{prev_keys}] → [{new_keys}]")
