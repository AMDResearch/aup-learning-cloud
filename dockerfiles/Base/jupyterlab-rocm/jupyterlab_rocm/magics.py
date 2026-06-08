"""IPython cell magic for Cell Profile.

``%%rocprofv3`` profiles a single PyTorch GPU notebook cell with
``torch.profiler`` in the live kernel. Results render inline and persist for the
JupyterLab sidebar.

Enable with ``%load_ext jupyterlab_rocm``.
"""

from __future__ import annotations

import html
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


def _esc(text: Any) -> str:
    return html.escape(str(text))


def _profile_title(job: profiler.ProfileJob) -> str:
    backend = job.extra.get("backend")
    preset = _esc(job.preset)
    if backend == "torch":
        return f"Cell Profile — torch.profiler ({preset})"
    if backend == "rocprofv3-subprocess":
        return f"Cell Profile — rocprofv3 subprocess ({preset})"
    return f"Cell Profile ({preset})"


def _error_html(message: str) -> str:
    return (
        "<div style='border-left:3px solid #b00020;padding:6px 10px;margin:6px 0;"
        "color:#b00020'>"
        f"<b>Cell Profile:</b> {_esc(message)}</div>"
    )


def _render_job(job: profiler.ProfileJob) -> str:
    kernels: List[Dict[str, Any]] = job.kernels
    summary: Dict[str, Any] = job.summary or {}
    backend = job.extra.get("backend")
    header = (
        f"<div class='jp-rocm-profile-title'>{_profile_title(job)}</div>"
    )

    hints: List[str] = []
    if backend == "rocprofv3-subprocess":
        hints.append(
            "This cell ran in a separate process; kernel variables were not updated."
        )

    if not kernels:
        empty_msg = (
            "No kernel dispatches were captured for this cell. "
            "Make sure the cell launches GPU work."
        )
        if backend == "rocprofv3-subprocess":
            empty_msg += " Try the <code>--kernel-trace</code> preset."
        hints.append(empty_msg)
        body = "".join(
            f"<p style='color:#9a6700;margin:4px 0'>{_esc(hint)}</p>" for hint in hints
        )
    else:
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
        hint_html = "".join(
            f"<p style='color:#6a737d;margin:4px 0;font-size:11px'>{_esc(hint)}</p>"
            for hint in hints
        )
        body = (
            f"{hint_html}"
            "<div style='margin:4px 0'>"
            f"<b>Kernels:</b> {summary.get('kernel_count', 0)} &nbsp; "
            f"<b>Dispatches:</b> {summary.get('total_dispatches', 0)} &nbsp; "
            f"<b>Total GPU time:</b> {_fmt_ns(summary.get('total_kernel_ns', 0))}"
            "</div>"
            "<table style='border-collapse:collapse;font-size:12px'>"
            f"<thead><tr>{head_cells}</tr></thead><tbody>{rows}</tbody></table>"
        )

    return (
        "<div class='jp-rocm-profile-result' style='padding:6px 10px;margin:0'>"
        f"{header}{body}</div>"
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
    @argument("--include", default=None, help="Kernel include regex.")
    @argument("--exclude", default=None, help="Kernel exclude regex.")
    @argument("--label", default=None, help="Human-readable label for this profile.")
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

        extra: Dict[str, Any] = {}
        if args.include:
            extra["kernel_include_regex"] = args.include
        if args.exclude:
            extra["kernel_exclude_regex"] = args.exclude

        label = args.label or "notebook cell"
        unavailable = profiler.cell_profile_unavailable_reason(cell)
        if unavailable:
            display(HTML(_error_html(unavailable)))
            return

        job = profiler.profile_cell_torch(self.shell, cell, label=label, preset=preset)

        try:
            profiler.register_cell_job(job)
        except Exception:
            pass

        if job.status == "error":
            display(HTML(_error_html(job.error or "Profiling failed.")))
        else:
            display(HTML(_render_job(job)))


def load_ipython_extension(ipython) -> None:
    ipython.register_magics(RocmMagics)
