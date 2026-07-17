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

from prometheus_client import Counter, Gauge, Histogram

# GPU spawn attempts
spawn_gpu_total = Counter(
    "hub_spawn_gpu_total",
    "GPU spawn attempts",
    ["accelerator"],
)

# Spawn failures
spawn_failed_total = Counter(
    "hub_spawn_failed_total",
    "Failed spawn attempts",
    ["reason"],
)

# Active sessions (derived from running usage sessions)
hub_active_sessions = Gauge(
    "hub_active_sessions",
    "Active running user sessions",
)

# Session runtime histogram
session_runtime_minutes = Histogram(
    "hub_session_runtime_minutes",
    "Container runtime in minutes",
    buckets=[5, 15, 30, 60, 120, 360],
)

# Spawn duration (seconds)
spawn_duration_seconds = Histogram(
    "hub_spawn_duration_seconds",
    "Time spent spawning user containers",
    buckets=[1, 2, 5, 10, 20, 30, 60, 120, 300],
)

# Quota denied
quota_denied_total = Counter(
    "hub_quota_denied_total",
    "Quota denied events",
    ["reason"],
)

# Quota consumption
quota_deducted_total = Counter(
    "hub_quota_deducted_total",
    "Quota consumed",
)

# Pod failures
pod_failure_total = Counter(
    "hub_pod_failure_total",
    "Pod failures",
    ["reason"],
)

# Git clone failures
repo_clone_failed_total = Counter(
    "hub_repo_clone_failed_total",
    "Repository clone failures",
)
