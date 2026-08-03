#!/bin/bash
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
#
# Runs the RAI manipulation demo without a monitor.
#
# O3DE renders through Vulkan, which needs a presentable surface: Xvfb can't
# provide one (no DRI3, so only the llvmpipe software device is presentable),
# but Xwayland on a headless Weston compositor can - it hands the X server the
# real /dev/dri render node, so the iGPU does the rendering. The simulation
# camera is then republished as MJPEG by web_video_server and shown next to the
# agent chat in the Streamlit page, so the whole demo lives in the browser.

set -e

RAI_DIR=/ryzers/rai
WESTON_LOG=/tmp/weston.log
VIDEO_PORT=8080

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/runtime-root}"
mkdir -p -m 700 "$XDG_RUNTIME_DIR"

# Xwayland needs this to exist. The container runs with --network=host, which
# shares the abstract socket namespace, so the abstract @X0 name is taken and
# Xwayland falls back to a socket file in here - Weston crashes if it's missing.
mkdir -p -m 1777 /tmp/.X11-unix

cleanup() {
    [ -n "$WESTON_PID" ] && kill "$WESTON_PID" 2>/dev/null
    [ -n "$VIDEO_PID" ] && kill "$VIDEO_PID" 2>/dev/null
    return 0
}
trap cleanup EXIT

# 1. Headless GPU display
if pgrep -f "weston --backend=headless" > /dev/null; then
    echo "Reusing the Weston compositor that is already running"
else
    echo "Starting headless Weston + Xwayland..."
    weston --backend=headless --renderer=gl \
           --width=1920 --height=1080 \
           --xwayland --socket=wayland-headless > "$WESTON_LOG" 2>&1 &
    WESTON_PID=$!
fi

for _ in $(seq 30); do
    DISPLAY=$(grep -oP 'xserver listening on display \K:[0-9]+' "$WESTON_LOG" | head -1)
    [ -n "$DISPLAY" ] && break
    sleep 1
done
if [ -z "$DISPLAY" ]; then
    echo "Xwayland did not come up - see $WESTON_LOG" >&2
    exit 1
fi
export DISPLAY
echo "Headless display ready on $DISPLAY"

# 2. ROS 2 + RAI environment (the demo resolves its assets relative to $RAI_DIR)
cd "$RAI_DIR"
source /opt/ros/${ROS_DISTRO}/setup.bash
source install/setup.bash

# 3. Republish the simulation camera as MJPEG for the browser
echo "Starting web_video_server on port $VIDEO_PORT..."
ros2 run web_video_server web_video_server --ros-args -p port:=$VIDEO_PORT \
    > /tmp/web_video_server.log 2>&1 &
VIDEO_PID=$!

# 4. Streamlit page: simulation view + agent chat
echo "Starting the demo - open http://localhost:8501 once the scene has loaded"
streamlit run /ryzers/manipulation_demo_streamlit.py \
    --server.headless true --server.address 0.0.0.0
