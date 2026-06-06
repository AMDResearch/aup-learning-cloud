"""IPython cell magic for per-cell rocprofv3 profiling.

``%%rocprofv3`` attaches ``rocprofv3`` to the *live* IPython kernel, runs the
cell body in the current user namespace (so variables from earlier cells are
preserved), detaches, then renders the hottest kernels inline and persists the
result so the JupyterLab sidebar can display it.

Enable with ``%load_ext jupyterlab_rocm``.
"""

from __future__ import annotations

import html
import os
from typing import Any, Dict, List

from IPython.core.magic import Magics, cell_magic, magics_class
from IPython.core.magic_arguments import argument, magic_arguments, parse_argstring
from IPython.display import HTML, display

from . import profiler


def _gpu_sync() -> None:
    """Flush outstanding GPU work so it lands inside the attach window."""
    try:
        import torch  # type: ignore

        if torch.cuda.is_available():
            torch.cuda.synchronize()
    except Exception:
        pass


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


def _error_html(message: str) -> str:
    return (
        "<div style='border-left:3px solid #b00020;padding:6px 10px;margin:6px 0;"
        "color:#b00020'>"
        f"<b>rocprofv3:</b> {_esc(message)}</div>"
    )


def _render_job(job: profiler.ProfileJob) -> str:
    kernels: List[Dict[str, Any]] = job.kernels
    summary: Dict[str, Any] = job.summary or {}
    header = (
        "<div style='font-weight:600;color:#e8500e'>"
        f"rocprofv3 cell profile ({_esc(job.preset)})</div>"
    )

    if not kernels:
        body = (
            "<p style='color:#9a6700;margin:4px 0'>No kernel dispatches were "
            "captured for this cell. Make sure the cell launches GPU work, try "
            "the <code>--kernel-trace</code> preset, and confirm "
            "<code>ROCP_TOOL_ATTACH=1</code> is set for the kernel.</p>"
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
        body = (
            "<div style='margin:4px 0'>"
            f"<b>Kernels:</b> {summary.get('kernel_count', 0)} &nbsp; "
            f"<b>Dispatches:</b> {summary.get('total_dispatches', 0)} &nbsp; "
            f"<b>Total GPU time:</b> {_fmt_ns(summary.get('total_kernel_ns', 0))}"
            "</div>"
            "<table style='border-collapse:collapse;font-size:12px'>"
            f"<thead><tr>{head_cells}</tr></thead><tbody>{rows}</tbody></table>"
        )

    return (
        "<div style='border-left:3px solid #e8500e;padding:6px 10px;margin:6px 0'>"
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
        help="Seconds to wait for attach before running the cell.",
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

        status = profiler.get_status()
        if not status.get("available"):
            display(HTML(_error_html(status.get("error") or "rocprofv3 not available.")))
            self.shell.run_cell(cell, store_history=False)
            return

        label = args.label or "notebook cell"
        session = profiler.AttachSession(os.getpid(), preset, extra, label=label)

        started = False
        try:
            session.start(ready_timeout=args.ready_timeout)
            started = True
        except Exception as exc:  # noqa: BLE001 - surfaced to the user
            display(HTML(_error_html(f"Failed to attach rocprofv3: {exc}")))

        # Run the user's code in the live kernel so its state is preserved.
        self.shell.run_cell(cell, store_history=False)
        _gpu_sync()

        if started:
            job = session.stop()
            try:
                profiler.register_cell_job(job)
            except Exception:
                pass
            if job.status == "error":
                display(HTML(_error_html(job.error or "rocprofv3 attach failed.")))
            else:
                display(HTML(_render_job(job)))


def load_ipython_extension(ipython) -> None:
    ipython.register_magics(RocmMagics)
