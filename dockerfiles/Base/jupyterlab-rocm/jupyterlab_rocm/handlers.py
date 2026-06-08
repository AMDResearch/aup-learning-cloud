"""Tornado request handlers for the jupyterlab_rocm server extension."""

from __future__ import annotations

import json

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
    ]
    web_app.add_handlers(host_pattern, handlers)
