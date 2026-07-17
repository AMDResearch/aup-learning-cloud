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

from auplc_jupyterlab_runtime_status.handlers import build_runtime_metadata_payload, setup_handlers


def test_metadata_payload_contains_only_display_safe_fields():
    payload = build_runtime_metadata_payload(
        {
            "JOB_START_TIME": "1717171717",
            "JOB_RUN_TIME": "120",
            "QUOTA_RATE": "3",
            "AUPLC_RUNTIME_UNLIMITED": "false",
            "JUPYTERHUB_API_TOKEN": "secret-token",
            "JUPYTERHUB_USER": "student",
            "HOSTNAME": "pod-name",
            "SOME_ARBITRARY_ENV": "do-not-expose",
        }
    )

    assert payload == {
        "startTimeSeconds": 1717171717,
        "runTimeMinutes": 120,
        "quotaRate": 3,
    }
    assert set(payload) <= {"startTimeSeconds", "runTimeMinutes", "quotaRate", "unlimited"}
    assert "secret-token" not in repr(payload)
    assert "student" not in repr(payload)
    assert "pod-name" not in repr(payload)
    assert "do-not-expose" not in repr(payload)


def test_metadata_payload_reports_unlimited_display_flag_without_fake_runtime():
    payload = build_runtime_metadata_payload(
        {
            "JOB_START_TIME": "1717171717",
            "QUOTA_RATE": "0",
            "AUPLC_RUNTIME_UNLIMITED": "true",
        }
    )

    assert payload == {
        "startTimeSeconds": 1717171717,
        "quotaRate": 0,
        "unlimited": True,
    }
    assert "runTimeMinutes" not in payload


def test_setup_handlers_uses_base_url_for_endpoint_path():
    captured = []

    class WebApp:
        settings = {"base_url": "/user/student/"}

        def add_handlers(self, host_pattern, handlers):
            captured.append((host_pattern, handlers))

    setup_handlers(WebApp())

    assert captured[0][0] == ".*$"
    assert captured[0][1][0][0] == "/user/student/auplc/runtime-status/api/metadata"
