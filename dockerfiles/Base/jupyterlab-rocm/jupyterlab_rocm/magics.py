"""IPython cell magic for Cell Profile.

``%%rocprofv3`` profiles a single PyTorch GPU notebook cell with
``torch.profiler`` in the live kernel. Results render inline and persist for the
JupyterLab sidebar.

Enable with ``%load_ext jupyterlab_rocm``.
"""

from __future__ import annotations

import html
import threading
import time
from typing import Any, Dict, List

from IPython.core.magic import Magics, cell_magic, magics_class
from IPython.core.magic_arguments import argument, magic_arguments, parse_argstring
from IPython.display import HTML, display

from . import profiler


def _fmt_ns(ns: float) -> str:
    ns = float(ns)
    if ns >= 1e9:
        return f"{ns / 1e9:.3f} s"
    if ns >= 1e6:
        return f"{ns / 1e6:.3f} ms"
    if ns >= 1e3:
        return f"{ns / 1e3:.2f} us"
    return f"{ns:.0f} ns"


def _fmt_bytes(num: float) -> str:
    num = float(num)
    sign = "-" if num < 0 else ""
    num = abs(num)
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024.0 or unit == "GB":
            if unit == "B":
                return f"{sign}{num:.0f} {unit}"
            return f"{sign}{num:.2f} {unit}"
        num /= 1024.0
    return f"{sign}{num:.2f} GB"


def _esc(text: Any) -> str:
    return html.escape(str(text))


def _mode_label(job: profiler.ProfileJob) -> str:
    mode = job.extra.get("mode", "full")
    if mode == "live":
        warm = job.extra.get("warmup_s", 0)
        return (
            f"live capture ({job.extra.get('window_s')}s"
            + (f", warmup {warm}s" if warm else "")
            + ", approx)"
        )
    return "full cell"


def _profile_title(job: profiler.ProfileJob) -> str:
    backend = job.extra.get("backend")
    preset = _esc(job.preset)
    mode = _esc(_mode_label(job))
    if backend == "torch":
        return f"Cell Profile — torch.profiler ({preset}) — {mode}"
    if backend == "rocprofv3-subprocess":
        return f"Cell Profile — rocprofv3 subprocess ({preset})"
    return f"Cell Profile ({preset})"


def _error_html(message: str) -> str:
    return (
        "<div style='border-left:3px solid #b00020;padding:6px 10px;margin:6px 0;"
        "color:#b00020'>"
        f"<b>Cell Profile:</b> {_esc(message)}</div>"
    )


def _kernel_table(kernels: List[Dict[str, Any]]) -> str:
    rows = ""
    for k in kernels[:15]:
        name = str(k["name"])
        short = (name[:60] + "\u2026") if len(name) > 60 else name
        rows += (
            f"<tr><td title='{_esc(name)}' style='font-family:monospace;"
            f"padding:2px 8px'>{_esc(short)}</td>"
            f"<td style='text-align:right;padding:2px 8px'>{k['calls']}</td>"
            f"<td style='text-align:right;padding:2px 8px'>"
            f"{_fmt_ns(k['total_ns'])}</td>"
            f"<td style='text-align:right;padding:2px 8px'>"
            f"{_fmt_ns(k['avg_ns'])}</td>"
            f"<td style='text-align:right;padding:2px 8px'>"
            f"{k['percent']:.1f}%</td></tr>"
        )
    head_cells = "".join(
        "<th style='text-align:left;border-bottom:1px solid #ccc;"
        f"padding:2px 8px'>{label}</th>"
        for label in ("Kernel", "Calls", "Total", "Avg", "%")
    )
    return (
        "<table style='border-collapse:collapse;font-size:12px;margin-top:4px'>"
        f"<thead><tr>{head_cells}</tr></thead><tbody>{rows}</tbody></table>"
    )


def _operator_table(
    operators: List[Dict[str, Any]],
    *,
    show_memory: bool,
    show_shapes: bool,
) -> str:
    columns = ["Operator", "Calls", "Self CPU", "CPU total", "Self GPU", "GPU total", "%"]
    if show_memory:
        columns += ["Self CPU Mem", "Self GPU Mem"]
    if show_shapes:
        columns += ["Input Shapes"]

    head_cells = "".join(
        "<th style='text-align:left;border-bottom:1px solid #ccc;"
        f"padding:2px 8px'>{_esc(label)}</th>"
        for label in columns
    )

    rows = ""
    for op in operators[:15]:
        name = str(op["name"])
        short = (name[:48] + "\u2026") if len(name) > 48 else name
        cells = (
            f"<td title='{_esc(name)}' style='font-family:monospace;"
            f"padding:2px 8px'>{_esc(short)}</td>"
            f"<td style='text-align:right;padding:2px 8px'>{op['calls']}</td>"
            f"<td style='text-align:right;padding:2px 8px'>{_fmt_ns(op['self_cpu_ns'])}</td>"
            f"<td style='text-align:right;padding:2px 8px'>{_fmt_ns(op['cpu_total_ns'])}</td>"
            f"<td style='text-align:right;padding:2px 8px'>{_fmt_ns(op['self_gpu_ns'])}</td>"
            f"<td style='text-align:right;padding:2px 8px'>{_fmt_ns(op['gpu_total_ns'])}</td>"
            f"<td style='text-align:right;padding:2px 8px'>{op.get('percent', 0.0):.1f}%</td>"
        )
        if show_memory:
            cells += (
                f"<td style='text-align:right;padding:2px 8px'>"
                f"{_fmt_bytes(op.get('self_cpu_mem', 0))}</td>"
                f"<td style='text-align:right;padding:2px 8px'>"
                f"{_fmt_bytes(op.get('self_gpu_mem', 0))}</td>"
            )
        if show_shapes:
            shapes = op.get("input_shapes") or ""
            cells += (
                f"<td style='font-family:monospace;padding:2px 8px'>{_esc(shapes)}</td>"
            )
        rows += f"<tr>{cells}</tr>"

    return (
        "<table style='border-collapse:collapse;font-size:12px;margin-top:4px'>"
        f"<thead><tr>{head_cells}</tr></thead><tbody>{rows}</tbody></table>"
    )


def _render_job(job: profiler.ProfileJob) -> str:
    kernels: List[Dict[str, Any]] = job.kernels
    operators: List[Dict[str, Any]] = job.operators
    summary: Dict[str, Any] = job.summary or {}
    backend = job.extra.get("backend")
    header = f"<div class='jp-rocm-profile-title'>{_profile_title(job)}</div>"

    hints: List[str] = []
    if backend == "rocprofv3-subprocess":
        hints.append(
            "This cell ran in a separate process; kernel variables were not updated."
        )

    if not kernels and not operators:
        mode = job.extra.get("mode", "full")
        if mode == "live":
            empty_msg = (
                "The live window captured no GPU work. The kernel may have been idle; "
                "trigger Profile now while the cell is actively running on the GPU."
            )
        else:
            empty_msg = (
                "No kernel dispatches were captured for this cell. "
                "Make sure the cell launches GPU work."
            )
            if backend == "rocprofv3-subprocess":
                empty_msg += " Try the --kernel-trace preset."
        hints.append(empty_msg)
        body = "".join(
            f"<p style='color:#9a6700;margin:4px 0'>{_esc(hint)}</p>" for hint in hints
        )
        return (
            "<div class='jp-rocm-profile-result' style='padding:6px 10px;margin:0'>"
            f"{header}{body}</div>"
        )

    hint_html = "".join(
        f"<p style='color:#6a737d;margin:4px 0;font-size:11px'>{_esc(hint)}</p>"
        for hint in hints
    )

    summary_html = (
        "<div style='margin:4px 0'>"
        f"<b>Operators:</b> {summary.get('operator_count', 0)} &nbsp; "
        f"<b>Kernels:</b> {summary.get('kernel_count', 0)} &nbsp; "
        f"<b>Dispatches:</b> {summary.get('total_dispatches', 0)} &nbsp; "
        f"<b>Self CPU:</b> {_fmt_ns(summary.get('self_cpu_total_ns', 0))} &nbsp; "
        f"<b>Self GPU:</b> {_fmt_ns(summary.get('self_gpu_total_ns', 0))} &nbsp; "
        f"<b>Total GPU time:</b> {_fmt_ns(summary.get('total_kernel_ns', 0))}"
        "</div>"
    )

    show_memory = any(
        op.get("self_cpu_mem") or op.get("self_gpu_mem") for op in operators
    )
    show_shapes = any(op.get("input_shapes") for op in operators)

    body_parts = [hint_html, summary_html]
    if operators:
        body_parts.append(
            "<div style='margin-top:6px;font-size:11px;color:#6a737d'>Operators "
            "(by self device time)</div>"
        )
        body_parts.append(
            _operator_table(operators, show_memory=show_memory, show_shapes=show_shapes)
        )
    if kernels:
        body_parts.append(
            "<div style='margin-top:8px;font-size:11px;color:#6a737d'>GPU kernels</div>"
        )
        body_parts.append(_kernel_table(kernels))

    return (
        "<div class='jp-rocm-profile-result' style='padding:6px 10px;margin:0'>"
        f"{header}{''.join(body_parts)}</div>"
    )


@magics_class
class RocmMagics(Magics):
    """Cell magics for the jupyterlab_rocm extension."""

    @magic_arguments()
    @argument(
        "--preset",
        default="kernel",
        help="Trace preset: runtime | kernel | sys | hip (default: kernel).",
    )
    @argument("--kernel-trace", action="store_true", help="Shortcut for --preset kernel.")
    @argument("--hip-trace", action="store_true", help="Shortcut for --preset hip.")
    @argument("--sys-trace", action="store_true", help="Shortcut for --preset sys.")
    @argument(
        "--runtime-trace", action="store_true", help="Shortcut for --preset runtime."
    )
    @argument("--label", default=None, help="Human-readable label for this profile.")
    @argument(
        "--shapes",
        action="store_true",
        help="Record operator input shapes (adds overhead).",
    )
    @argument(
        "--memory",
        action="store_true",
        help="Record per-operator CPU/GPU memory allocation.",
    )
    @argument(
        "--stack",
        action="store_true",
        help="Record Python/source stacks for operators (adds overhead).",
    )
    @argument(
        "--trace",
        action="store_true",
        help="Keep the chrome trace for download (Perfetto / chrome://tracing).",
    )
    @argument(
        "--ready-timeout",
        type=float,
        default=10.0,
        help="Ignored (kept for backward compatibility with saved magics).",
    )
    @cell_magic
    def rocprofv3(self, line: str, cell: str) -> None:
        args = parse_argstring(self.rocprofv3, line)

        preset = args.preset
        if args.kernel_trace:
            preset = "kernel"
        elif args.hip_trace:
            preset = "hip"
        elif args.sys_trace:
            preset = "sys"
        elif args.runtime_trace:
            preset = "runtime"

        label = args.label or "notebook cell"
        unavailable = profiler.cell_profile_unavailable_reason(cell)
        if unavailable:
            display(HTML(_error_html(unavailable)))
            return

        options: Dict[str, Any] = {
            "record_shapes": bool(args.shapes),
            "profile_memory": bool(args.memory),
            "with_stack": bool(args.stack),
            "keep_trace": bool(args.trace),
        }

        job = profiler.run_cell_profile(
            self.shell,
            cell,
            label=label,
            preset=preset,
            options=options,
        )

        try:
            profiler.register_cell_job(job)
        except Exception:
            pass

        if job.status == "error":
            display(HTML(_error_html(job.error or "Profiling failed.")))
        else:
            display(HTML(_render_job(job)))


# ---------------------------------------------------------------------------
# Live-capture watcher (armed when the extension loads)
# ---------------------------------------------------------------------------

_live_watcher_started = False
_live_watcher_guard = threading.Lock()


def _handle_live_trigger(payload: Dict[str, Any]) -> None:
    job = profiler.profile_live_window(
        window_s=float(payload.get("window_s", 2.0)),
        warmup_s=float(payload.get("warmup_s", 0.0)),
        preset=payload.get("preset", "kernel"),
        options=payload.get("options") or {},
        label=payload.get("label") or "live capture",
    )
    try:
        profiler.register_cell_job(job)
    except Exception:
        pass


def _live_watcher_loop(poll_interval: float = 0.5) -> None:
    kernel_id = profiler.current_kernel_id()
    last_heartbeat = 0.0
    while True:
        try:
            now = time.time()
            if now - last_heartbeat >= 2.0:
                profiler.live_heartbeat(kernel_id)
                last_heartbeat = now
            payload = profiler.claim_live_trigger(kernel_id)
            if payload:
                window_s = float(payload.get("window_s", 2.0))
                warmup_s = float(payload.get("warmup_s", 0.0))
                # Mark busy so the sidebar can lock "Profile now" until done.
                profiler.set_live_busy(
                    kernel_id, time.time() + window_s + warmup_s + 30.0
                )
                try:
                    _handle_live_trigger(payload)
                finally:
                    profiler.clear_live_busy(kernel_id)
        except Exception:
            pass
        time.sleep(poll_interval)


def start_live_watcher(shell: Any = None) -> None:
    """Arm the per-kernel background watcher for live-capture triggers (idempotent)."""
    global _live_watcher_started
    with _live_watcher_guard:
        if _live_watcher_started:
            return
        _live_watcher_started = True
    thread = threading.Thread(
        target=_live_watcher_loop, name="rocm-live-watcher", daemon=True
    )
    thread.start()


def load_ipython_extension(ipython) -> None:
    ipython.register_magics(RocmMagics)
    try:
        start_live_watcher(ipython)
    except Exception:
        pass
