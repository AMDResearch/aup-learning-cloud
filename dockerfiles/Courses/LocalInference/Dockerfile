# Copyright (C) 2026 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT

ARG BASE_IMAGE=ghcr.io/amdresearch/auplc-base:latest
FROM ${BASE_IMAGE}

USER root
SHELL ["/bin/bash", "-c"]

ARG ROS_DISTRO=jazzy
ARG RAI_COMMIT=e54f8ca

ENV DEBIAN_FRONTEND=noninteractive \
    ROS_DISTRO=${ROS_DISTRO} \
    LANG=en_US.UTF-8 \
    LC_ALL=en_US.UTF-8

# ROS 2 Jazzy and development tools.
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl \
      gnupg2 \
      locales \
      python3-venv \
      software-properties-common \
    && locale-gen en_US en_US.UTF-8 \
    && update-locale LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 \
    && add-apt-repository universe \
    && ROS_APT_SOURCE_VERSION="$(curl -fsSL https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest \
      | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])')" \
    && curl -fsSL -o /tmp/ros2-apt-source.deb \
      "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.$(. /etc/os-release && echo "${VERSION_CODENAME}")_all.deb" \
    && dpkg -i /tmp/ros2-apt-source.deb \
    && rm /tmp/ros2-apt-source.deb \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
      ros-${ROS_DISTRO}-desktop \
      ros-dev-tools \
      ros-${ROS_DISTRO}-cv-bridge \
      ros-${ROS_DISTRO}-image-transport \
      ros-${ROS_DISTRO}-v4l2-camera \
      ros-${ROS_DISTRO}-web-video-server \
    && rm -rf /var/lib/apt/lists/*

# Vulkan and O3DE.
RUN curl -fsSL https://packages.lunarg.com/lunarg-signing-key-pub.asc \
      -o /etc/apt/trusted.gpg.d/lunarg.asc \
    && curl -fsSL https://packages.lunarg.com/vulkan/lunarg-vulkan-noble.list \
      -o /etc/apt/sources.list.d/lunarg-vulkan-noble.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends vulkan-sdk \
    && curl -fsSL https://o3debinaries.org/main/Latest/Linux/o3de_2510_0.deb \
      -o /tmp/o3de.deb \
    && apt-get install -y /tmp/o3de.deb \
    && rm /tmp/o3de.deb \
    && rm -rf /var/lib/apt/lists/*

# RAI framework and ROS dependencies.
RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg \
      git \
      libgl1-mesa-dri \
      libportaudio2 \
      libvulkan1 \
      mesa-vulkan-drivers \
      ros-${ROS_DISTRO}-ackermann-msgs \
      ros-${ROS_DISTRO}-depth-image-proc \
      ros-${ROS_DISTRO}-gazebo-msgs \
      ros-${ROS_DISTRO}-moveit \
      ros-${ROS_DISTRO}-moveit-resources-panda-moveit-config \
      ros-${ROS_DISTRO}-rai-interfaces \
      ros-${ROS_DISTRO}-sdformat-urdf \
      unzip \
      vulkan-tools \
      weston \
      xwayland \
    && rm -rf /var/lib/apt/lists/*

# Proxy the RAI Streamlit UI and camera stream through each JupyterHub user's
# existing notebook-server route.
RUN /usr/bin/python3 -m pip install --no-cache-dir --break-system-packages \
      jupyter-server-proxy

ENV CARGO_HOME=/opt/cargo \
    RUSTUP_HOME=/opt/rustup \
    PATH="/opt/cargo/bin:/opt/rai-venv/bin:${PATH}"

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
      | sh -s -- -y --default-toolchain stable --no-modify-path \
    && echo "/opt/ros/${ROS_DISTRO}/opt/sdformat_vendor/lib" \
      > /etc/ld.so.conf.d/ros-sdformat.conf \
    && ldconfig

RUN mkdir -p /ryzers \
    && git clone https://github.com/RobotecAI/rai.git /ryzers/rai \
    && git -C /ryzers/rai checkout "${RAI_COMMIT}" \
    && cd /ryzers/rai \
    && vcs import < ros_deps.repos \
    && vcs import < demos.repos

# Reuse the ROCm torch from auplc-base and prevent Python dependencies from
# replacing it with CUDA wheels.
RUN python3 -m venv --system-site-packages /opt/rai-venv \
    && python3 -c "from importlib.metadata import version; \
print('torch==' + version('torch')); \
print('torchvision==' + version('torchvision')); \
print('torchaudio==' + version('torchaudio'))" > /opt/torch-constraints.txt \
    && PIP_CONSTRAINT=/opt/torch-constraints.txt /opt/rai-venv/bin/pip install --no-cache-dir \
      catkin_pkg \
      lark \
      "numpy<2" \
      opencv-python \
      "setuptools<82" \
      "empy<4" \
    && PIP_CONSTRAINT=/opt/torch-constraints.txt /opt/rai-venv/bin/pip install \
      --no-cache-dir --no-build-isolation openai-whisper==20250625

WORKDIR /ryzers/rai
RUN sed -i \
      's/    get_grabbing_point_tool: "GetGrabbingPointTool"/    get_grabbing_point_tool: Any/' \
      src/rai_core/rai/tools/ros2/manipulation/custom.py \
    && PIP_CONSTRAINT=/opt/torch-constraints.txt pip install --no-cache-dir \
      src/rai_core src/rai_whoami \
    && (rosdep init || true) \
    && rosdep update \
    && rosdep install \
      --from-paths src/examples/rai-manipulation-demo/ros2_ws/src \
      --ignore-src -r -y \
    && . ./scripts/download_demo.sh manipulation \
    && . /opt/ros/${ROS_DISTRO}/setup.sh \
    && colcon build --symlink-install \
    && PIP_CONSTRAINT=/opt/torch-constraints.txt pip install --no-cache-dir \
      src/rai_bench src/rai_sim \
    && PIP_CONSTRAINT=/opt/torch-constraints.txt pip install --no-cache-dir \
      "rai-gsam2>=1.1.2,<2" \
      "rf-groundingdino>=0.2.0,<0.3" \
      "scikit-learn>=1.0,<1.4" \
      "transformers<5" \
    && PIP_CONSTRAINT=/opt/torch-constraints.txt pip install --no-cache-dir \
      --no-deps rai-perception==0.3.0 \
    && RAI_PERCEPTION_DIR="$(python3 -c \
      'from pathlib import Path; import rai_perception; print(Path(rai_perception.__file__).parent)')" \
    && sed -i \
      's|Path.home() / Path(".cache/rai/")|Path("/opt/rai-cache")|g' \
      "${RAI_PERCEPTION_DIR}/agents/base_vision_agent.py" \
      "${RAI_PERCEPTION_DIR}/services/base_vision_service.py" \
    && sed -i \
      's|Path.home() / Path(".cache/rai")|Path("/opt/rai-cache")|g' \
      "${RAI_PERCEPTION_DIR}/services/segmentation_service.py" \
    && mkdir -p /opt/rai-cache \
    && download-perception-models \
    && python3 -c \
      "import torch; assert torch.version.hip, 'RAI dependencies replaced ROCm torch'; print('RAI ROCm environment OK:', torch.__version__)"

# Lemonade local OpenAI-compatible model server.
RUN add-apt-repository ppa:lemonade-team/stable \
    && apt-get update \
    && apt-get install -y --no-install-recommends lemonade-server \
    && rm -rf /var/lib/apt/lists/*

RUN getent group audio >/dev/null || groupadd audio \
    && getent group kvm >/dev/null || groupadd kvm \
    && usermod -aG audio,kvm jovyan \
    && mkdir -p \
      /home/jovyan/.cache/huggingface \
      /home/jovyan/.cache/lemonade \
      /home/jovyan/.streamlit \
      /ryzers/notebooks \
      /tmp/runtime-jovyan \
    && chmod 700 /tmp/runtime-jovyan \
    && printf 'pcm.!default = null;\n' > /home/jovyan/.asoundrc \
    && printf '[general]\nemail = ""\n' > /home/jovyan/.streamlit/credentials.toml

COPY ./course_data /ryzers/notebooks
COPY ./course_data/lemonade_env.sh \
     ./course_data/manipulation_demo_headless.sh \
     ./course_data/manipulation_demo_streamlit.py \
     ./course_data/notebook_demo.py \
     /ryzers/

RUN ln -s /ryzers/notebooks/tests/test_ros.sh /ryzers/test_ros.sh \
    && ln -s /ryzers/notebooks/tests/test_o3de.sh /ryzers/test_o3de.sh \
    && ln -s /ryzers/notebooks/tests/test_rai.sh /ryzers/test_rai.sh \
    && ln -s /ryzers/notebooks/tests/test_lemonade-sdk.sh /ryzers/test_lemonade-sdk.sh \
    && chmod +x \
      /ryzers/lemonade_env.sh \
      /ryzers/manipulation_demo_headless.sh \
    && chown -R jovyan:100 \
      /home/jovyan/.cache \
      /home/jovyan/.streamlit \
      /home/jovyan/.asoundrc \
      /ryzers \
      /tmp/runtime-jovyan \
    && printf '%s\n' \
      '#!/usr/bin/env bash' \
      'set -e' \
      'source "/opt/ros/${ROS_DISTRO}/setup.bash"' \
      '[ ! -f /ryzers/rai/install/setup.bash ] || source /ryzers/rai/install/setup.bash' \
      'exec /bin/bash /entrypoint.sh "$@"' \
      > /usr/local/bin/start-local-inference.sh \
    && chmod +x /usr/local/bin/start-local-inference.sh

ENV HOME=/home/jovyan \
    HF_HOME=/home/jovyan/.cache/huggingface \
    XDG_RUNTIME_DIR=/tmp/runtime-jovyan

USER jovyan
WORKDIR /ryzers/notebooks

CMD ["/usr/local/bin/start-local-inference.sh"]
