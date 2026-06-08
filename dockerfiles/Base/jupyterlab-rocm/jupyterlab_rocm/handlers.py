"""Tornado request handlers for the jupyterlab_rocm server extension."""

from __future__ import annotations

import json
import os
import time

import tornado
import tornado.websocket
from jupyter_server.base.handlers import APIHandler, JupyterHandler
from jupyter_server.base.websocket import WebSocketMixin
from jupyter_server.utils import url_path_join
from tornado.ioloop import PeriodicCallback

from . import metrics, profiler, sysinfo

NAMESPACE = "jupyterlab-rocm"


class GpusHandler(APIHandler):
    """Static information about the available GPUs and tooling."""

    @tornado.web.authenticated
    def get(self):
        self.finish(
            json.dumps(
                {
                    "status": metrics.get_status(),
                    "devices": metrics.list_devices(),
                    "rocprof": profiler.get_status(),
                }
            )
        )


class MetricsHandler(APIHandler):
    """One-shot metrics sample (useful as a polling fallback)."""

    @tornado.web.authenticated
    def get(self):
        self.finish(json.dumps(metrics.sample()))


class StaticHandler(APIHandler):
    """Static GPU information from ``amd-smi list`` / ``amd-smi static``."""

    @tornado.web.authenticated
    def get(self):
        self.finish(json.dumps(sysinfo.static_info()))


class StreamHandler(WebSocketMixin, JupyterHandler, tornado.websocket.WebSocketHandler):
    """Streams metrics samples over a WebSocket at a fixed interval."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pc = None

    async def pre_get(self):
        user = self.current_user
        if user is None:
            raise tornado.web.HTTPError(403)

    async def get(self, *args, **kwargs):
        await self.pre_get()
        return await super().get(*args, **kwargs)

    def open(self):
        try:
            interval = int(self.get_query_argument("interval", "1000"))
        except (ValueError, tornado.web.MissingArgumentError):
            interval = 1000
        interval = max(200, min(interval, 10000))
        self._pc = PeriodicCallback(self._emit, interval)
        self._emit()
        self._pc.start()

    def _emit(self):
        try:
            self.write_message(json.dumps(metrics.sample()))
        except Exception:
            pass

    def on_close(self):
        if self._pc is not None:
            self._pc.stop()
            self._pc = None


class CellProfileHandler(APIHandler):
    """Cell Profile jobs produced by the ``%%rocprofv3`` magic."""

    @tornado.web.authenticated
    def get(self):
        self.finish(json.dumps({"jobs": profiler.list_cell_jobs()}))


class CellProfileTraceHandler(APIHandler):
    """Serve the persisted chrome trace for a Cell Profile job (``--trace``)."""

    @tornado.web.authenticated
    def get(self):
        job_id = self.get_query_argument("id", "")
        if not job_id or not job_id.isalnum():
            raise tornado.web.HTTPError(400, "Invalid or missing job id.")
        path = profiler.trace_path_for(job_id)
        if not os.path.isfile(path):
            raise tornado.web.HTTPError(404, "Trace not found for this job.")
        self.set_header("Content-Type", "application/json")
        self.set_header(
            "Content-Disposition",
            f'attachment; filename="cell_profile_{job_id}.json"',
        )
        with open(path, "rb") as handle:
            self.finish(handle.read())


class CellProfileLiveHandler(APIHandler):
    """Live-capture: arm status (GET) and trigger requests (POST)."""

    @tornado.web.authenticated
    def get(self):
        kernel_id = self.get_query_argument("kernel_id", "") or None
        self.finish(
            json.dumps(
                {
                    "armed": profiler.live_armed(kernel_id),
                    "busy": profiler.live_busy(kernel_id),
                }
            )
        )

    @tornado.web.authenticated
    def post(self):
        try:
            body = json.loads(self.request.body or b"{}")
        except ValueError:
            body = {}
        kernel_id = body.get("kernel_id") or None
        armed = profiler.live_armed(kernel_id)
        payload = {
            "kernel_id": kernel_id,
            "window_s": float(body.get("window_s", 2.0)),
            "warmup_s": float(body.get("warmup_s", 0.0)),
            "preset": body.get("preset", "kernel"),
            "options": body.get("options") or {},
            "label": body.get("label") or "live capture",
            "created": time.time(),
        }
        profiler.write_live_trigger(kernel_id, payload)
        self.finish(json.dumps({"ok": True, "armed": armed}))


def setup_handlers(web_app):
    host_pattern = ".*$"
    base_url = web_app.settings["base_url"]

    def route(*parts):
        return url_path_join(base_url, NAMESPACE, *parts)

    handlers = [
        (route("gpus"), GpusHandler),
        (route("metrics"), MetricsHandler),
        (route("static"), StaticHandler),
        (route("stream"), StreamHandler),
        (route("profile", "cell"), CellProfileHandler),
        (route("profile", "cell", "trace"), CellProfileTraceHandler),
        (route("profile", "cell", "live"), CellProfileLiveHandler),
    ]
    web_app.add_handlers(host_pattern, handlers)
