"""AMD GPU metrics collection backed by the amdsmi Python library.

This module wraps amdsmi in a defensive way: amdsmi raises exceptions or returns
the string ``"N/A"`` for metrics that a given GPU/ASIC does not support. Every
individual metric is therefore guarded so a single unsupported field never
breaks a whole sample. Missing values are normalised to ``None``.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import threading
from typing import Any, Dict, List, Optional

_LOCK = threading.Lock()
_INITIALISED = False
_INIT_ERROR: Optional[str] = None
_NAME_CACHE: Dict[int, str] = {}

try:
    import amdsmi  # type: ignore

    _IMPORT_ERROR: Optional[str] = None
except Exception as exc:  # pragma: no cover - depends on host
    amdsmi = None  # type: ignore
    _IMPORT_ERROR = f"{type(exc).__name__}: {exc}"


# amdsmi reports unsupported numeric fields as the maximum unsigned value for
# the field's width (uint16/uint32/uint64) instead of the string "N/A". These
# must be treated as "no value" or they surface as nonsense readings such as a
# 4294967295 W power draw or a 65535 MHz clock.
_UINT_SENTINELS = frozenset({0xFFFF, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF})


def _normalise(value: Any) -> Any:
    """Convert amdsmi's "N/A" sentinels into ``None``."""
    if isinstance(value, str) and value.strip().upper() in {"N/A", "NA", ""}:
        return None
    return value


def _normalise_metric(value: Any) -> Any:
    """Normalise a numeric metric, also rejecting amdsmi uint-max sentinels.

    Use this for bounded scalar metrics (power, clock, temperature, utilisation)
    where a uint-max value can only mean "unsupported". It is intentionally not
    used for byte/MB counters where such magnitudes can be legitimate.
    """
    value = _normalise(value)
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in _UINT_SENTINELS:
        return None
    return value


def _safe(func, *args, **kwargs) -> Any:
    """Call an amdsmi function, returning ``None`` on any failure."""
    try:
        return _normalise(func(*args, **kwargs))
    except Exception:
        return None


def _ensure_init() -> None:
    """Initialise amdsmi exactly once for the process."""
    global _INITIALISED, _INIT_ERROR
    if _INITIALISED or amdsmi is None:
        return
    with _LOCK:
        if _INITIALISED:
            return
        try:
            amdsmi.amdsmi_init()
            _INITIALISED = True
            _INIT_ERROR = None
        except Exception as exc:
            _INIT_ERROR = f"{type(exc).__name__}: {exc}"


def shutdown() -> None:
    """Shut down amdsmi if it was initialised. Safe to call multiple times."""
    global _INITIALISED
    if amdsmi is None:
        return
    with _LOCK:
        if not _INITIALISED:
            return
        try:
            amdsmi.amdsmi_shut_down()
        except Exception:
            pass
        finally:
            _INITIALISED = False


def get_status() -> Dict[str, Any]:
    """Return availability information for the frontend to display."""
    if amdsmi is None:
        return {
            "available": False,
            "error": (
                "The 'amdsmi' Python package is not importable. Install it from "
                "your ROCm tree, e.g. 'pip install /opt/rocm/share/amd_smi'."
            ),
            "import_error": _IMPORT_ERROR,
        }
    _ensure_init()
    if not _INITIALISED:
        return {
            "available": False,
            "error": (
                "amdsmi failed to initialise. Ensure the amdgpu driver is loaded "
                "and the process can access /dev/kfd and /dev/dri."
            ),
            "init_error": _INIT_ERROR,
        }
    return {"available": True, "error": None}


def _handles() -> List[Any]:
    if amdsmi is None:
        return []
    _ensure_init()
    if not _INITIALISED:
        return []
    try:
        return list(amdsmi.amdsmi_get_processor_handles())
    except Exception:
        return []


def _market_name_from_cli(index: int) -> Optional[str]:
    """Fall back to the ``amd-smi`` CLI to obtain the market name.

    On some ASICs (notably APUs) ``amdsmi_get_gpu_asic_info`` reports
    NOT_SUPPORTED from the Python bindings even though the ``amd-smi`` CLI can
    still resolve the marketing name. Parsing the CLI keeps the displayed name
    consistent with what users see from ``amd-smi``.
    """
    exe = shutil.which("amd-smi")
    if exe is None:
        return None
    try:
        proc = subprocess.run(
            [exe, "static", "--asic", "-g", str(index)],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    match = re.search(r"MARKET_NAME:\s*(.+)", proc.stdout)
    if match:
        value = _normalise(match.group(1).strip())
        if value:
            return str(value)
    return None


def _device_name(handle: Any, index: int) -> str:
    if index in _NAME_CACHE:
        return _NAME_CACHE[index]

    name: Optional[str] = None
    board = _safe(amdsmi.amdsmi_get_gpu_board_info, handle) or {}
    if isinstance(board, dict):
        for key in ("product_name", "model_number"):
            value = _normalise(board.get(key))
            if value:
                name = str(value)
                break
    if name is None:
        asic = _safe(amdsmi.amdsmi_get_gpu_asic_info, handle) or {}
        if isinstance(asic, dict):
            value = _normalise(asic.get("market_name"))
            if value:
                name = str(value)
    if name is None:
        name = _market_name_from_cli(index)

    name = name or f"AMD GPU {index}"
    _NAME_CACHE[index] = name
    return name


def list_devices() -> List[Dict[str, Any]]:
    """Return static, mostly-immutable information about each GPU."""
    devices: List[Dict[str, Any]] = []
    for index, handle in enumerate(_handles()):
        board = _safe(amdsmi.amdsmi_get_gpu_board_info, handle) or {}
        asic = _safe(amdsmi.amdsmi_get_gpu_asic_info, handle) or {}
        if not isinstance(board, dict):
            board = {}
        if not isinstance(asic, dict):
            asic = {}
        devices.append(
            {
                "index": index,
                "name": _device_name(handle, index),
                "serial": _normalise(board.get("product_serial")),
                "manufacturer": _normalise(board.get("manufacturer_name")),
                "market_name": _normalise(asic.get("market_name")),
                "vram_total_mb": _vram(handle).get("total_mb"),
            }
        )
    return devices


def _temperature(handle: Any) -> Optional[float]:
    """Best-effort current temperature; tries several sensor types."""
    if amdsmi is None:
        return None
    sensors = []
    for name in ("HOTSPOT", "JUNCTION", "EDGE", "GPU"):
        sensor = getattr(amdsmi.AmdSmiTemperatureType, name, None)
        if sensor is not None:
            sensors.append(sensor)
    metric = getattr(amdsmi.AmdSmiTemperatureMetric, "CURRENT", None)
    for sensor in sensors:
        value = _normalise_metric(_safe(amdsmi.amdsmi_get_temp_metric, handle, sensor, metric))
        if value is not None:
            return value
    return None


def _clock(handle: Any) -> Optional[Dict[str, Any]]:
    if amdsmi is None:
        return None
    clk_type = getattr(amdsmi.AmdSmiClkType, "GFX", None)
    if clk_type is None:
        return None
    info = _safe(amdsmi.amdsmi_get_clock_info, handle, clk_type)
    if not isinstance(info, dict):
        return None
    return {
        "cur_mhz": _normalise_metric(info.get("cur_clk") or info.get("clk")),
        "max_mhz": _normalise_metric(info.get("max_clk")),
    }


def _power(handle: Any) -> Dict[str, Any]:
    info = _safe(amdsmi.amdsmi_get_power_info, handle) or {}
    if not isinstance(info, dict):
        info = {}
    # socket_power is the unified field that "matches current or average socket
    # power" across ASIC families (current_socket_power is MI300+ only,
    # average_socket_power is Navi/MI200 and earlier). Prefer it, then fall back.
    watts = (
        _normalise_metric(info.get("socket_power"))
    )
    return {
        "watts": watts,
        "limit_watts": _normalise_metric(info.get("power_limit")),
    }


def _activity(handle: Any) -> Dict[str, Any]:
    info = _safe(amdsmi.amdsmi_get_gpu_activity, handle) or {}
    if not isinstance(info, dict):
        info = {}
    return {
        "gfx": _normalise_metric(info.get("gfx_activity")),
        "umc": _normalise_metric(info.get("umc_activity")),
        "mm": _normalise_metric(info.get("mm_activity")),
    }


def _memory_mb(handle: Any, which: str) -> Optional[float]:
    """VRAM total/used in MB via the memory_total/usage API (returns bytes).

    Used as a fallback when ``amdsmi_get_gpu_vram_usage`` is unsupported on a
    given ASIC (common on APUs).
    """
    if amdsmi is None:
        return None
    vram_type = getattr(amdsmi.AmdSmiMemoryType, "VRAM", None)
    if vram_type is None:
        return None
    fn = (
        amdsmi.amdsmi_get_gpu_memory_total
        if which == "total"
        else amdsmi.amdsmi_get_gpu_memory_usage
    )
    value = _safe(fn, handle, vram_type)
    if value is None:
        return None
    try:
        return round(float(value) / 1048576.0)
    except (TypeError, ValueError):
        return None


def _vram(handle: Any) -> Dict[str, Any]:
    info = _safe(amdsmi.amdsmi_get_gpu_vram_usage, handle) or {}
    if not isinstance(info, dict):
        info = {}
    total = _normalise(info.get("vram_total"))
    used = _normalise(info.get("vram_used"))
    if total is None:
        total = _memory_mb(handle, "total")
    if used is None:
        used = _memory_mb(handle, "used")
    percent = None
    try:
        if total and used is not None and float(total) > 0:
            percent = round(float(used) / float(total) * 100.0, 1)
    except (TypeError, ValueError):
        percent = None
    return {"total_mb": total, "used_mb": used, "percent": percent}


def _processes(handle: Any) -> List[Dict[str, Any]]:
    raw = _safe(amdsmi.amdsmi_get_gpu_process_list, handle)
    procs: List[Dict[str, Any]] = []
    if not isinstance(raw, list):
        return procs
    for item in raw:
        if not isinstance(item, dict):
            continue
        mem = item.get("memory_usage")
        vram_used = None
        if isinstance(mem, dict):
            vram_used = _normalise(mem.get("vram_mem"))
        procs.append(
            {
                "pid": _normalise(item.get("pid")),
                "name": _normalise(item.get("name")),
                "vram_bytes": vram_used,
            }
        )
    return procs


def sample() -> Dict[str, Any]:
    """Collect one snapshot of live metrics for every GPU."""
    status = get_status()
    if not status.get("available"):
        return {"available": False, "error": status.get("error"), "gpus": []}

    import time

    gpus: List[Dict[str, Any]] = []
    for index, handle in enumerate(_handles()):
        gpus.append(
            {
                "index": index,
                "name": _device_name(handle, index),
                "activity": _activity(handle),
                "vram": _vram(handle),
                "power": _power(handle),
                "temperature_c": _temperature(handle),
                "clock": _clock(handle),
                "processes": _processes(handle),
            }
        )
    return {"available": True, "error": None, "timestamp": time.time(), "gpus": gpus}
