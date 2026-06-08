"""AMD GPU metrics collection backed by the amdsmi Python library.

This module wraps amdsmi in a defensive way: amdsmi raises exceptions or returns
the string ``"N/A"`` for metrics that a given GPU/ASIC does not support. Every
individual metric is therefore guarded so a single unsupported field never
breaks a whole sample. Missing values are normalised to ``None``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
from typing import Any, Dict, List, Optional

_LOCK = threading.Lock()
_INITIALISED = False
_INIT_ERROR: Optional[str] = None
_NAME_CACHE: Dict[int, str] = {}

# Match amd-smi's process refresh behavior. Process rows are short-lived and
# should not be hidden behind a long library cache.
os.environ.setdefault("AMDSMI_PROCESS_INFO_CACHE_MS", "100")

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


def _memory_bytes(value: Any) -> Optional[int]:
    """Parse a byte counter from amdsmi, preserving large legitimate values."""
    value = _normalise(value)
    if value is None:
        return None
    if isinstance(value, str):
        match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*([kmgt]?i?b)?\s*", value, re.IGNORECASE)
        if match:
            number = float(match.group(1))
            unit = (match.group(2) or "b").lower()
            multipliers = {
                "b": 1,
                "kb": 1000,
                "kib": 1024,
                "mb": 1000**2,
                "mib": 1024**2,
                "gb": 1000**3,
                "gib": 1024**3,
                "tb": 1000**4,
                "tib": 1024**4,
            }
            return int(number * multipliers.get(unit, 1))
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _microseconds(value: Any) -> Optional[int]:
    value = _normalise_metric(value)
    if value is None:
        return None
    if isinstance(value, str):
        match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*(us|µs|ms|s)?\s*", value, re.IGNORECASE)
        if match:
            number = float(match.group(1))
            unit = (match.group(2) or "us").lower()
            if unit == "s":
                number *= 1000000
            elif unit == "ms":
                number *= 1000
            return int(number)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _compute_units(handle: Any) -> Optional[int]:
    asic = _safe(amdsmi.amdsmi_get_gpu_asic_info, handle) or {}
    if not isinstance(asic, dict):
        return None
    value = _normalise_metric(asic.get("num_compute_units"))
    if value is None:
        return None
    try:
        units = int(value)
        return units if units > 0 else None
    except (TypeError, ValueError):
        return None


def _cu_percent(cu_occupancy: Any, num_compute_units: Optional[int]) -> Optional[float]:
    occupancy = _normalise_metric(cu_occupancy)
    if occupancy is None or num_compute_units is None:
        return None
    try:
        return round(float(occupancy) / float(num_compute_units) * 100.0, 1)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _percent(value: Any, digits: int = 1) -> Optional[float]:
    value = _normalise_metric(value)
    if value is None:
        return None
    if isinstance(value, str):
        match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*%?\s*", value)
        if not match:
            return None
        value = match.group(1)
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _field(mapping: Dict[str, Any], *names: str) -> Any:
    """Look up an amd-smi JSON field across minor naming variations."""
    for name in names:
        if name in mapping:
            return mapping[name]
    wanted = {re.sub(r"[^a-z0-9]", "", name.lower()) for name in names}
    for key, value in mapping.items():
        if re.sub(r"[^a-z0-9]", "", str(key).lower()) in wanted:
            return value
    return None


def _process_from_mapping(item: Dict[str, Any], num_cu: Optional[int] = None) -> Optional[Dict[str, Any]]:
    pid = _normalise(_field(item, "pid", "PID"))
    if pid is None:
        return None
    try:
        pid_int = int(pid)
        if pid_int <= 0:
            return None
    except (TypeError, ValueError):
        return None

    mem = _field(item, "memory_usage")
    gtt_mem = _field(item, "gtt_mem", "GTT_MEM", "gtt_memory")
    vram_mem = _field(item, "vram_mem", "VRAM_MEM", "vram_memory")
    if isinstance(mem, dict):
        gtt_mem = _field(mem, "gtt_mem", "GTT_MEM", "gtt_memory")
        vram_mem = _field(mem, "vram_mem", "VRAM_MEM", "vram_memory")

    cu_value = _field(item, "cu_occupancy", "cu_percent", "CU %")
    cu_percent = _cu_percent(cu_value, num_cu) if num_cu is not None else _percent(cu_value)

    return {
        "pid": pid_int,
        "name": _normalise(_field(item, "process_name", "name", "Process Name")),
        "gtt_mem": _memory_bytes(gtt_mem),
        "vram_mem": _memory_bytes(vram_mem),
        "mem_usage": _memory_bytes(_field(item, "mem", "mem_usage", "MEM_USAGE", "memory_usage")),
        "cu_percent": cu_percent,
        "sdma_us": _microseconds(_field(item, "sdma_usage", "sdma_us", "SDMA")),
    }


def _fresh_processes_by_gpu(
    num_cu_by_gpu: Optional[Dict[int, Optional[int]]] = None
) -> Optional[Dict[int, List[Dict[str, Any]]]]:
    """Return process rows from a fresh AMD SMI Python subprocess.

    ``amdsmi_get_gpu_process_list`` can keep stale process rows in this
    long-lived Jupyter server process. A short-lived helper keeps the same
    libamd_smi source without depending on the ``amd-smi`` command being present.
    """
    script = """
import json

import amdsmi

amdsmi.amdsmi_init()
try:
    rows = []
    for index, handle in enumerate(amdsmi.amdsmi_get_processor_handles()):
        try:
            processes = amdsmi.amdsmi_get_gpu_process_list(handle)
        except Exception:
            processes = []
        rows.append({"gpu": index, "processes": processes})
    print(json.dumps(rows))
finally:
    try:
        amdsmi.amdsmi_shut_down()
    except Exception:
        pass
"""
    env = os.environ.copy()
    env.setdefault("AMDSMI_PROCESS_INFO_CACHE_MS", "100")
    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            env=env,
            text=True,
            timeout=3,
        )
    except Exception:
        return None

    out = (proc.stdout or "").strip()
    if not out:
        return None
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None

    by_gpu: Dict[int, List[Dict[str, Any]]] = {}
    for gpu_item in data:
        if not isinstance(gpu_item, dict):
            continue
        try:
            gpu_index = int(_field(gpu_item, "gpu", "GPU"))
        except (TypeError, ValueError):
            continue

        rows: List[Dict[str, Any]] = []
        process_list = _field(gpu_item, "processes", "process_list") or []
        if isinstance(process_list, list):
            for item in process_list:
                if not isinstance(item, dict):
                    continue
                process_info = _field(item, "process_info")
                if isinstance(process_info, str):
                    continue
                source = process_info if isinstance(process_info, dict) else item
                row = _process_from_mapping(
                    source, (num_cu_by_gpu or {}).get(gpu_index)
                )
                if row is not None:
                    rows.append(row)
        by_gpu[gpu_index] = rows
    return by_gpu


def _processes(handle: Any) -> List[Dict[str, Any]]:
    """Return GPU processes exactly from libamd_smi's process list API.

    This intentionally does not validate PIDs with ``/proc``. amd-smi itself
    trusts ``amdsmi_get_gpu_process_list``; in containers, GPU-visible PIDs can
    be outside the Jupyter server's process namespace.
    """
    raw = _safe(amdsmi.amdsmi_get_gpu_process_list, handle)
    procs: List[Dict[str, Any]] = []
    if not isinstance(raw, list):
        return procs
    num_cu = _compute_units(handle)
    for item in raw:
        if not isinstance(item, dict):
            continue
        pid = _normalise(item.get("pid"))
        if pid is None:
            continue
        try:
            pid_int = int(pid)
            if pid_int <= 0:
                continue
        except (TypeError, ValueError):
            continue
        row = _process_from_mapping(item, num_cu)
        if row is not None:
            procs.append(row)
    return procs


def sample() -> Dict[str, Any]:
    """Collect one snapshot of live metrics for every GPU."""
    status = get_status()
    if not status.get("available"):
        return {"available": False, "error": status.get("error"), "gpus": []}

    import time

    handles = _handles()
    num_cu_by_gpu = {index: _compute_units(handle) for index, handle in enumerate(handles)}
    fresh_processes = _fresh_processes_by_gpu(num_cu_by_gpu)
    gpus: List[Dict[str, Any]] = []
    for index, handle in enumerate(handles):
        gpus.append(
            {
                "index": index,
                "name": _device_name(handle, index),
                "activity": _activity(handle),
                "vram": _vram(handle),
                "power": _power(handle),
                "temperature_c": _temperature(handle),
                "clock": _clock(handle),
                "processes": (
                    fresh_processes.get(index, [])
                    if fresh_processes is not None
                    else _processes(handle)
                ),
            }
        )
    return {"available": True, "error": None, "timestamp": time.time(), "gpus": gpus}
