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

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from jupyter_server.base.handlers import APIHandler
from jupyter_server.utils import url_path_join
from tornado import web

METADATA_ENDPOINT = "auplc/runtime-status/api/metadata"


def _parse_positive_int(value: str | None) -> int | None:
    if value is None:
        return None

    try:
        parsed_value = int(value.strip())
    except ValueError:
        return None

    return parsed_value if parsed_value > 0 else None


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None

    try:
        return int(value.strip())
    except ValueError:
        return None


def _parse_boolean_flag(value: str | None) -> bool:
    if value is None:
        return False

    return value.strip().lower() in {"1", "true", "yes"}


def build_runtime_metadata_payload(environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = environ if environ is not None else os.environ
    payload: dict[str, Any] = {}

    start_time_seconds = _parse_positive_int(source.get("JOB_START_TIME"))
    if start_time_seconds is not None:
        payload["startTimeSeconds"] = start_time_seconds

    run_time_minutes = _parse_positive_int(source.get("JOB_RUN_TIME"))
    if run_time_minutes is not None:
        payload["runTimeMinutes"] = run_time_minutes

    quota_rate = _parse_int(source.get("QUOTA_RATE"))
    if quota_rate is not None:
        payload["quotaRate"] = quota_rate

    if _parse_boolean_flag(source.get("AUPLC_RUNTIME_UNLIMITED")):
        payload["unlimited"] = True

    return payload


class RuntimeStatusMetadataHandler(APIHandler):
    @web.authenticated
    async def get(self):
        self.finish(build_runtime_metadata_payload())


def setup_handlers(web_app):
    base_url = web_app.settings.get("base_url", "/")
    route_pattern = url_path_join(base_url, METADATA_ENDPOINT)
    web_app.add_handlers(".*$", [(route_pattern, RuntimeStatusMetadataHandler)])
