#!/bin/bash
# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

set -e

echo "=========================================="
echo "RAI Framework Test"
echo "=========================================="

# Source ROS environment (ROS_DISTRO set by ros package)
if [ -n "$ROS_DISTRO" ]; then
    source /opt/ros/${ROS_DISTRO}/setup.bash
    echo "ROS 2 ${ROS_DISTRO} environment sourced"
else
    echo "Warning: ROS_DISTRO not set."
fi

# Test RAI core import
echo ""
echo "Testing RAI core import..."
PYTHONWARNINGS=ignore python3 -c "
from rai.agents import AgentRunner, ReActAgent
from rai.initialization import get_llm_model
print('RAI core imports successful!')
print('  - AgentRunner: available')
print('  - ReActAgent: available')
print('  - get_llm_model: available')
"

# Test RAI whoami import
echo ""
echo "Testing RAI whoami import..."
python3 -c "
from rai_whoami import EmbodimentInfo, Pipeline, PipelineBuilder
print('RAI whoami imports successful!')
print('  - EmbodimentInfo: available')
print('  - Pipeline: available')
print('  - PipelineBuilder: available')
"

# Test the perception stack and assets used by 03_robot_agents.ipynb.
echo ""
echo "Testing RAI manipulation demo..."
PYTHONWARNINGS=ignore python3 -c "
from pathlib import Path

from rai_perception.services.detection_service import DetectionService
from rai_perception.services.segmentation_service import SegmentationService

weights = Path('/opt/rai-cache/vision/weights')
expected = [
    weights / 'groundingdino_swint_ogc.pth',
    weights / 'sam2_hiera_large.pt',
]
assert DetectionService.DEFAULT_WEIGHTS_ROOT_PATH == Path('/opt/rai-cache')
assert all(path.stat().st_size > 100_000_000 for path in expected)
assert Path('/ryzers/rai/examples/manipulation-demo-streamlit.py').is_file()
print('RAI perception imports and preloaded weights available!')
"
/usr/bin/python3 -c "import jupyter_server_proxy"
test -x /ryzers/lemonade_env.sh
test -x /ryzers/manipulation_demo_headless.sh
test -f /ryzers/manipulation_demo_streamlit.py
echo "RAI demo scripts and Jupyter port proxy available!"

# Check ROS 2 tools
echo ""
echo "Testing ROS 2 integration..."
ros2 --help > /dev/null 2>&1 && echo "ROS 2 CLI: available"

# Print versions
echo ""
echo "=========================================="
echo "Version Information"
echo "=========================================="
RAI_VERSION=$(grep '^version' /ryzers/rai/src/rai_core/pyproject.toml | head -1 | cut -d'"' -f2)
echo "RAI version: ${RAI_VERSION}"
echo "ROS 2 distro: ${ROS_DISTRO}"
python3 --version
