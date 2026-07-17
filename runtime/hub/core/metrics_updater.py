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

"""
Background metrics updater for derived metrics.
"""

import threading
import time
from contextlib import suppress

from core.metrics import hub_active_sessions
from core.quota import get_quota_manager

UPDATE_INTERVAL = 15


def _update_once(quota_manager):
    try:
        count = quota_manager.get_active_sessions_count()
        hub_active_sessions.set(count)
    except Exception:
        # keep metric present even if quota manager fails
        hub_active_sessions.set(0)


def _update_loop():
    quota_manager = get_quota_manager()

    # run once immediately so the metric exists
    _update_once(quota_manager)

    while True:
        _update_once(quota_manager)
        time.sleep(UPDATE_INTERVAL)


def start_metrics_updater():
    # ensure metric exists even before first loop tick
    with suppress(Exception):
        hub_active_sessions.set(0)

    t = threading.Thread(target=_update_loop, daemon=True)
    t.start()
