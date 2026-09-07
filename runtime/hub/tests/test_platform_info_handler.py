# Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import asyncio
import importlib
import json
import sys
from types import SimpleNamespace

import pytest
from onboarding_handlers_support import load_handlers

# Sibling test modules leave a bare tornado.web stub in sys.modules; restore the
# real package so core.handlers can import web.authenticated.
if not hasattr(sys.modules.get("tornado.web"), "authenticated"):
    sys.modules.pop("tornado.web", None)
    sys.modules.pop("tornado", None)
    importlib.import_module("tornado.web")


@pytest.fixture
def loaded_handlers(monkeypatch: pytest.MonkeyPatch):
    with load_handlers(monkeypatch) as state:
        yield state


def _run(handlers, platform_name: str) -> dict:
    handlers.configure_handlers(platform_name=platform_name)
    handler = object.__new__(handlers.PlatformInfoHandler)
    handler.headers = {}
    handler.set_header = lambda name, value: handler.headers.__setitem__(name, value)
    handler.finish = lambda payload: setattr(handler, "body", payload)

    asyncio.run(handler.get())
    return json.loads(handler.body)


def test_platform_endpoint_reports_the_cluster_suffixed_name(loaded_handlers) -> None:
    payload = _run(loaded_handlers.handlers, "AUP Learning Cloud Dublin")

    assert payload["platform"] == "AUP Learning Cloud Dublin"
    assert payload["powered_by"] == "AUP Learning Cloud Dublin"


def test_platform_endpoint_skips_xsrf_so_logged_in_clients_can_read_it(loaded_handlers) -> None:
    """Regression: APIHandler enforces XSRF once a session cookie exists, so the
    React apps got 403 and fell back to the hardcoded platform name."""
    handler_class = loaded_handlers.handlers.PlatformInfoHandler

    assert "check_xsrf_cookie" in handler_class.__dict__
    assert handler_class.check_xsrf_cookie(SimpleNamespace()) is None
