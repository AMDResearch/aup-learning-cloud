# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Portions of this file consist of AI-generated content.

"""AMD GPU detection and SKU resolution.

The installer combines live AMDGPU driver inventory with ROCm/KFD fallbacks:
  1. Read current driver metadata from ``/sys/class/drm/card*/device``.
  2. Try ``rocminfo`` for marketing names of GPU agents (filtered by
     "Device Type: GPU" so AMD CPUs do not bleed in).
  3. Derive a gfx target from rocminfo or KFD topology when product names are
     absent (handling both hex-packed and decimal encodings).
  4. After helm install, re-read ROCm labeller node labels for authoritative
     scheduler product names, while preserving local driver descriptions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from auplc_installer.util import InstallerError, command_exists, log, run_capture

SYS_DRM_ROOT = Path("/sys/class/drm")
KFD_TOPOLOGY_ROOT = Path("/sys/class/kfd/kfd/topology/nodes")

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
# edits (useful for ad-hoc SKUs like 9600gre).
GPU_CURATED_SKU_KEYS = ("phx", "strix", "strix-halo", "9070xt", "r9700")

_ACCEL_KEY_DISPLAY_NAMES: dict[str, str] = {
    "phx": "AMD Radeon 780M (Phoenix Point iGPU)",
    "strix": "AMD Radeon 890M (Strix Point iGPU)",
    "strix-halo": "AMD Radeon 8060S (Strix Halo iGPU)",
    "9070xt": "AMD Radeon RX 9070 XT",
    "r9700": "AMD Radeon AI PRO R9700",
    "9600gre": "AMD Radeon RX 9600 GRE",
}


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


def resolve_gpu_config(input_key: str) -> SkuRow:
    """Map a user-supplied GPU type or detected gfx family to a SKU row.

    Raises :class:`InstallerError` for unsupported inputs.
    """
    row = _GFX_FALLBACK.get(input_key)
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


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _read_int(path: Path) -> int | None:
    text = _read_text(path)
    if not text:
        return None
    try:
        return int(text, 0)
    except ValueError:
        return None


def format_gpu_memory(bytes_value: int | None) -> str:
    """Format driver byte counts into stable GiB labels."""
    if bytes_value is None or bytes_value <= 0:
        return ""
    gib = bytes_value / 1024 / 1024 / 1024
    if gib >= 10 or gib.is_integer():
        return f"{gib:.0f} GiB"
    return f"{gib:.1f} GiB"


def build_gpu_description(
    gfx: str | None,
    *,
    vram_bytes: int | None,
    visible_vram_bytes: int | None,
    gtt_bytes: int | None,
) -> str:
    """Build the UI-facing accelerator description from live driver data."""
    parts: list[str] = []
    if gfx:
        parts.append(gfx)
    if vram := format_gpu_memory(vram_bytes):
        parts.append(f"VRAM {vram}")
    if visible_vram := format_gpu_memory(visible_vram_bytes):
        parts.append(f"Visible VRAM {visible_vram}")
    if gtt := format_gpu_memory(gtt_bytes):
        parts.append(f"GTT {gtt}")
    return " | ".join(parts) if parts else "Auto-detected AMD GPU"


def detect_rocminfo_gpu_marketing_names() -> list[str]:
    """Raw GPU marketing names from rocminfo, excluding CPU agents."""
    if not command_exists("rocminfo"):
        return []
    try:
        res = run_capture(["rocminfo"], check=False, stderr_to_stdout=True)
        text = res.stdout or ""
    except Exception:
        text = ""

    names: list[str] = []
    seen: set[str] = set()
    marketing = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        m = re.match(r"^Marketing Name:\s*(.*)$", line)
        if m:
            marketing = m.group(1).strip()
            continue
        m = re.match(r"^Device Type:\s*(.*)$", line)
        if not m:
            continue
        devtype = m.group(1).strip()
        if devtype == "GPU" and marketing and marketing not in seen:
            seen.add(marketing)
            names.append(marketing)
        marketing = ""
    return names


def _read_dmesg_gpu_memory_bytes(field: str) -> int | None:
    """Fallback parser for VRAM/GTT boot messages when sysfs files are absent."""
    if not command_exists("dmesg"):
        return None
    try:
        res = run_capture(["dmesg"], check=False, stderr_to_stdout=True)
    except Exception:
        return None
    text = res.stdout or ""

    if field == "gtt":
        pattern = r"amdgpu:\s+(\d+)M of GTT memory ready"
    elif field == "vram":
        pattern = r"amdgpu:\s+(\d+)M of VRAM memory ready"
    elif field == "visible_vram":
        pattern = r"Detected VRAM RAM=\d+M,\s+BAR=(\d+)M"
    else:
        return None

    m = re.search(pattern, text, flags=re.IGNORECASE)
    if not m:
        return None
    return int(m.group(1)) * 1024 * 1024


def detect_gpu_product_names() -> list[str]:
    """All distinct AMD GPU product names on this host (labeller-normalised)."""
    out: list[str] = []
    seen: set[str] = set()

    # 1. rocminfo: track the most recent "Marketing Name" before each
    #    "Device Type"; commit only when device type is GPU.
    for marketing in detect_rocminfo_gpu_marketing_names():
        name = normalise_product_name(marketing)
        if name and name not in seen:
            seen.add(name)
            out.append(name)

    # 2. amdgpu sysfs (no ROCm dependency).
    for f in sorted(SYS_DRM_ROOT.glob("card*/device/product_name")):
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
            for line in (res.stdout or "").splitlines():
                m = re.search(r"gfx[0-9]+", line)
                if m:
                    return m.group(0)
        except Exception:
            pass

    # KFD topology fallback. ``gfx_target_version`` uses two encodings:
    #   - hex-packed (kernel <6.14):  0x0B0501 = 722177  → 11, 5, 1   → gfx1151
    #   - decimal     (kernel ≥6.14):  110501             → 11, 05, 01 → gfx1151
    # Hex-packed values for any GPU (major≥9) start at 0x090000 = 589824;
    # the largest decimal value for current GPUs is ~120201. We pick 200000
    # as the threshold to disambiguate.
    for prop_path in sorted(KFD_TOPOLOGY_ROOT.glob("*/properties")):
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
    description: str = ""  # live driver metadata, when available


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
                if entry.product_name and not existing.product_name:
                    existing.product_name = entry.product_name
                if entry.display_name:
                    existing.display_name = entry.display_name
                if entry.description:
                    existing.description = entry.description
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


def _display_name_for_accel_key(accel_key: str) -> str:
    return _ACCEL_KEY_DISPLAY_NAMES.get(accel_key, f"AMD GPU ({accel_key})")


def _sku_entry_from_row(
    row: SkuRow,
    *,
    product_name: str = "",
    display_name: str = "",
    description: str = "",
) -> SkuEntry:
    accel_key, gpu_target, env, rate, row_display = row
    return SkuEntry(
        accel_key=accel_key,
        product_name=product_name,
        gpu_target=gpu_target,
        accel_env=env,
        quota_rate=rate,
        display_name=display_name or row_display,
        description=description,
    )


def _row_for_detected_gpu(product_name: str, detected_gfx: str | None) -> SkuRow:
    if product_name:
        return sku_for_product_name(product_name)
    if detected_gfx and (row := _GFX_FALLBACK.get(detected_gfx)):
        return row
    return ("amd-gpu", detected_gfx or "gfx120x", "", 4, "AMD GPU")


def append_product(cfg: GpuConfig, product: str, *, display_name: str = "", description: str = "") -> None:
    """Resolve a product name and append it as an SKU entry."""
    if not product:
        return
    cfg.append(
        _sku_entry_from_row(
            sku_for_product_name(product),
            product_name=product,
            display_name=display_name,
            description=description,
        )
    )


def detect_driver_gpu_inventory() -> list[SkuEntry]:
    """Build SKU entries from the AMDGPU driver inventory.

    The driver sysfs memory files are authoritative for descriptions because
    BIOS RAM allocation and installed hardware can change between installer
    runs. Product names may be absent on some iGPU systems; in that case the
    entry still carries a display name resolved from the detected gfx family.
    """
    rocminfo_names = detect_rocminfo_gpu_marketing_names()
    marketing_index = 0
    detected_gfx = detect_gpu_gfx_family()
    entries: list[SkuEntry] = []
    seen: set[tuple[str, str]] = set()

    for card in sorted(SYS_DRM_ROOT.glob("card[0-9]*")):
        device_dir = card / "device"
        if not device_dir.is_dir():
            continue
        vendor = _read_text(device_dir / "vendor").lower()
        if vendor != "0x1002":
            continue

        driver_link = device_dir / "driver"
        if driver_link.exists():
            try:
                driver = driver_link.resolve().name
            except OSError:
                driver = ""
            if driver and driver != "amdgpu":
                continue

        raw_display_name = _read_text(device_dir / "product_name")
        if not raw_display_name and marketing_index < len(rocminfo_names):
            raw_display_name = rocminfo_names[marketing_index]
            marketing_index += 1
        product_name = normalise_product_name(raw_display_name) if raw_display_name else ""

        vram_bytes = _read_int(device_dir / "mem_info_vram_total")
        visible_vram_bytes = _read_int(device_dir / "mem_info_vis_vram_total")
        gtt_bytes = _read_int(device_dir / "mem_info_gtt_total")
        if vram_bytes is None:
            vram_bytes = _read_dmesg_gpu_memory_bytes("vram")
        if visible_vram_bytes is None:
            visible_vram_bytes = _read_dmesg_gpu_memory_bytes("visible_vram")
        if gtt_bytes is None:
            gtt_bytes = _read_dmesg_gpu_memory_bytes("gtt")

        description = build_gpu_description(
            detected_gfx,
            vram_bytes=vram_bytes,
            visible_vram_bytes=visible_vram_bytes,
            gtt_bytes=gtt_bytes,
        )
        row = _row_for_detected_gpu(product_name, detected_gfx)
        entry = _sku_entry_from_row(
            row,
            product_name=product_name,
            display_name=raw_display_name,
            description=description,
        )
        if not entry.display_name:
            entry.display_name = _display_name_for_accel_key(entry.accel_key)

        key = (entry.accel_key, product_name or str(device_dir))
        if key in seen:
            continue
        seen.add(key)
        entries.append(entry)

    if not entries and rocminfo_names:
        for raw_display_name in rocminfo_names:
            product_name = normalise_product_name(raw_display_name)
            description = build_gpu_description(
                detected_gfx,
                vram_bytes=None,
                visible_vram_bytes=None,
                gtt_bytes=None,
            )
            entries.append(
                _sku_entry_from_row(
                    _row_for_detected_gpu(product_name, detected_gfx),
                    product_name=product_name,
                    display_name=raw_display_name,
                    description=description,
                )
            )

    return entries


def apply_driver_metadata_to_config(cfg: GpuConfig) -> None:
    """Enrich already-resolved SKU entries with local driver descriptions."""
    for entry in detect_driver_gpu_inventory():
        for existing in cfg.skus:
            if existing.accel_key != entry.accel_key:
                continue
            if entry.product_name and existing.product_name and existing.product_name != entry.product_name:
                continue
            if entry.product_name:
                existing.product_name = entry.product_name
            if entry.display_name:
                existing.display_name = entry.display_name
            if entry.description:
                existing.description = entry.description


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

    entries = detect_driver_gpu_inventory()
    if entries:
        log("Detected AMD GPU(s) from driver:")
        for entry in entries:
            log(f"  - {entry.display_name or _display_name_for_accel_key(entry.accel_key)}")
            log(f"    {entry.description}")
            cfg.append(entry)

    if not cfg.skus:
        names = detect_gpu_product_names()
        if names:
            log("Detected GPU product name(s) from host:")
            for name in names:
                log(f"  - {name}")
                append_product(cfg, name)

    if not cfg.skus:
        if gpu_type_override:
            log(f"Using GPU type override: {gpu_type_override}")
            input_key = gpu_type_override
        else:
            gfx = detect_gpu_gfx_family()
            if gfx:
                log(f"Detected GPU: {gfx}")
                input_key = gfx
            else:
                if pinned_target:
                    key = pinned_key or pinned_target
                    rate = 4
                    display = _display_name_for_accel_key(key)
                    if row := _GFX_FALLBACK.get(key):
                        _, _, _, rate, row_display = row
                        display = row_display or display
                    log(f"GPU not detected; using manifest-pinned GPU config ({key}/{pinned_target}).")
                    cfg.append(
                        SkuEntry(
                            accel_key=key,
                            product_name="",
                            gpu_target=pinned_target,
                            accel_env=pinned_env,
                            quota_rate=rate,
                            display_name=display,
                        )
                    )
                    input_key = ""
                else:
                    raise InstallerError("GPU not detected. Re-run with --gpu=TYPE if you need to force a target.")
        if input_key:
            cfg.append(_sku_entry_from_row(resolve_gpu_config(input_key)))

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
        append_product(cfg, n)
    apply_driver_metadata_to_config(cfg)

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
