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

# Pre-fetch the GGUFs the notebook uses so a workshop does not spend its first
# minutes downloading them, the same idea as the SAM3 weights below.
#
# `lemonade pull` in this build talks to a running Lemonade server rather than
# downloading on its own, so the step starts lemond, waits for it, pulls, and
# stops it again. No GPU is involved: pulling only downloads weights.
#
# The cache has to live outside /home/jovyan, since the Hub mounts a per-user
# volume there that would hide anything baked in. HF_HOME holds the weights and
# LEMONADE_CACHE_DIR holds the server's own cache; both are pointed at
# ${LEMONADE_CACHE} again in the runtime ENV further down.
#
# Gemma is a built-in registry name and resolves to one file, so the name alone
# is enough. gpt-oss cannot be pulled that way: the built-in entry for
# gpt-oss-20b-mxfp4-GGUF pins no variant, and ggml-org/gpt-oss-20b-GGUF also
# ships EAGLE3 draft models for speculative decoding, so the server downloads
# the whole repo and then loads eagle3-gpt-oss-20b-BF16.gguf, first by name,
# which llama-server dies on with a segfault. Naming the file registers the
# right one and leaves the 2.6 GB of drafts undownloaded. A registered user.*
# model shadows the built-in of the same name, so the notebook keeps asking for
# plain "gpt-oss-20b-mxfp4-GGUF", and user_models.json is written into
# LEMONADE_CACHE, where the runtime ENV further down points as well.
ARG LEMONADE_MODEL="Gemma-4-E2B-it-GGUF"
ARG LEMONADE_BIG_MODEL="user.gpt-oss-20b-mxfp4-GGUF"
ARG LEMONADE_BIG_CHECKPOINT="ggml-org/gpt-oss-20b-GGUF:gpt-oss-20b-MXFP4.gguf"
ENV LEMONADE_CACHE=/opt/lemonade-cache
RUN --mount=type=secret,id=hf_token,required=false \
    set -eu; \
    export HF_TOKEN="$(cat /run/secrets/hf_token 2>/dev/null || true)"; \
    export HF_HOME="${LEMONADE_CACHE}"; \
    export LEMONADE_CACHE_DIR="${LEMONADE_CACHE}"; \
    : "lemond refuses to start without a writable XDG_RUNTIME_DIR, and the" \
      "runtime ENV that sets one is only applied at the end of this file." ; \
    export XDG_RUNTIME_DIR=/tmp/lemond-build-runtime; \
    mkdir -p "${XDG_RUNTIME_DIR}"; chmod 700 "${XDG_RUNTIME_DIR}"; \
    lemond > /tmp/lemond-build.log 2>&1 & \
    LEMOND_PID=$!; \
    for _ in $(seq 180); do \
      if lemonade status >/dev/null 2>&1; then break; fi; \
      : "stop waiting the moment lemond exits, instead of burning the timeout" ; \
      if ! kill -0 "${LEMOND_PID}" 2>/dev/null; then break; fi; \
      sleep 1; \
    done; \
    if ! lemonade status >/dev/null 2>&1; then \
      echo "lemond did not come up during build:"; cat /tmp/lemond-build.log; exit 1; \
    fi; \
    echo "=== pulling ${LEMONADE_MODEL} ==="; \
    lemonade pull "${LEMONADE_MODEL}"; \
    echo "=== pulling ${LEMONADE_BIG_MODEL} ==="; \
    lemonade pull "${LEMONADE_BIG_MODEL}" \
      --checkpoint main "${LEMONADE_BIG_CHECKPOINT}" \
      --recipe llamacpp; \
    kill "${LEMOND_PID}" 2>/dev/null || true; \
    rm -rf "${XDG_RUNTIME_DIR}"; \
    test -d "${LEMONADE_CACHE}/hub"; \
    : "Fail here rather than at a workshop if the pull picks a draft model" ; \
    test -n "$(find "${LEMONADE_CACHE}/hub" -name 'gpt-oss-20b-MXFP4.gguf' -print -quit)"

# ---------------------------------------------------------------------------
# CaP-X (Code-as-Policies eXtended) - the code-generating manipulation agent
# behind 04_code_as_policies_with_capx.ipynb. Robosuite/MuJoCo rendered
# headless through EGL on the iGPU, perception and IK served on localhost.
#
# CaP-X pins dependencies that would fight the RAI stack (numpy, transformers,
# matplotlib, mujoco), so it gets its own venv plus its own Jupyter kernel
# ("CaP-X (ROCm)", selected by the notebook) instead of sharing /opt/rai-venv.
# --system-site-packages keeps the base ROCm torch rather than pulling CUDA
# wheels, exactly as the RAI venv does.
# ---------------------------------------------------------------------------

# Pinned to a tested CaP-X commit.
ARG CAPX_REF=53e9966d7a8e2fa7494676772bccc35280f5c0ed

ENV CAPX_ROOT=/ryzers/cap-x \
    CAPX_VENV=/opt/capx-venv \
    CAPX_CACHE=/opt/capx-cache

# EGL/GL stack for headless MuJoCo, pyrender and open3d. MuJoCo renders through
# EGL/OpenGL, not through HIP, so this is what puts frames on the iGPU with no
# display attached.
RUN apt-get update && apt-get install -y --no-install-recommends \
      cmake \
      libegl1 \
      libegl-mesa0 \
      libgl1 \
      libgles2 \
      libglew-dev \
      libglfw3 \
      libglfw3-dev \
      libosmesa6 \
      libosmesa6-dev \
      pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Constraints: the base ROCm torch (already captured for RAI) plus CaP-X's uv
# override-dependencies and the Python 3.12 Robosuite resolution from its
# lockfile. Robosuite 1.5.1 still calls the pre-3.10 mj_fullM API, so letting
# pip take the current MuJoCo release breaks startup.
# FIX: CaP-X also pins PyOpenGL-accelerate==3.1.6, which has no cp312 wheel and
# does not compile on Python 3.12 - left out here.
RUN cp /opt/torch-constraints.txt /opt/capx-constraints.txt \
    && printf '%s\n' \
      'numpy==1.26.4' \
      'PyOpenGL==3.1.6' \
      'matplotlib>=3.10,<3.11' \
      'opencv-python-headless<4.13' \
      'jax==0.4.29' \
      'jaxlib==0.4.29' \
      'mujoco==3.5.0' \
      'mink==1.1.0' \
      'networkx==3.6.1' \
      'pyglet==2.1.13' \
      >> /opt/capx-constraints.txt

# Clone WITHOUT --recurse-submodules, then init only the submodules the
# Robosuite eval path uses. This skips curobo (huge, with nested CUDA
# submodules), b1k (BEHAVIOR/Isaac Sim), verl (RL training) and LIBERO-PRO -
# none of them needed here, and a large time and space saving.
RUN /usr/bin/python3 -m venv --system-site-packages ${CAPX_VENV} \
    && git clone https://github.com/capgym/cap-x ${CAPX_ROOT} \
    && git -C ${CAPX_ROOT} checkout ${CAPX_REF} \
    && git -C ${CAPX_ROOT} submodule update --init \
      capx/third_party/sam3 \
      capx/third_party/contact_graspnet_pytorch \
      capx/third_party/robosuite

WORKDIR /ryzers/cap-x

# Base runtime deps: the PyPI-resolvable subset of [project.dependencies],
# minus torch/torchvision (kept from the base image) and the CUDA-only entries.
# FIX: setuptools is pinned from both sides. Below 81 because sam3 imports
# pkg_resources, dropped in 81. At or above 77 because robosuite pulls in
# pynput -> evdev, whose pyproject.toml declares the PEP 639 SPDX form
# (license = "BSD-3-Clause") that older setuptools rejects outright. The lower
# bound is also what forces a copy into the venv: with a bare "<81" pip counts
# the base image's system setuptools 68 as satisfying the requirement, leaves
# the venv without its own, and the later --no-build-isolation builds pick up
# that 68 and fail.
RUN PIP_CONSTRAINT=/opt/capx-constraints.txt ${CAPX_VENV}/bin/pip install --no-cache-dir \
      "gymnasium>=0.29" "tyro>=0.8.5" "pydantic>=2.7" "rich>=13.7" \
      "scipy>=1.12" "matplotlib>=3.10,<3.11" "imageio[ffmpeg]>=0.6.0" \
      requests tqdm h5py einops decord pycocotools pyyaml omegaconf \
      open3d "robot_descriptions>=1.16.0" "yourdfpy>=0.0.56" "viser>=0.2.0" \
      "trimesh>=4.4.0" msgpack_numpy "ray==2.48.0" "mediapy>=1.2.5" \
      uvicorn fastapi "transformers<5.0" openai \
      "opencv-python-headless<4.13" "pillow>=10" cloudpickle \
      "setuptools>=77,<81" \
      "mujoco==3.5.0" "mink==1.1.0" "networkx==3.6.1" "pyglet==2.1.13" \
      "pyliblzfse==0.4.1" freetype-py six \
    && : "CaP-X overrides pyrender's stale PyOpenGL==3.1.0 metadata to 3.1.6." \
         "pip cannot express uv's override, so install the locked pyrender" \
         "once all of its runtime dependencies are already present." \
    && ${CAPX_VENV}/bin/pip install --no-cache-dir --no-deps "pyrender==0.1.45"

# PyRoKi: JAX-based IK / trajopt, and the default motion layer here - it
# replaces cuRobo for the Robosuite bench. Deliberately CPU-only, which keeps
# the GPU for perception.
RUN PIP_CONSTRAINT=/opt/capx-constraints.txt ${CAPX_VENV}/bin/pip install --no-cache-dir \
      "jax==0.4.29" "jaxlib==0.4.29" \
      jaxlie jax_dataclasses jaxtyping loguru termcolor \
    && PIP_CONSTRAINT=/opt/capx-constraints.txt ${CAPX_VENV}/bin/pip install \
      --no-cache-dir --no-deps \
      "git+https://github.com/brentyi/jaxls.git@6fe7cf9d56223736b2c0272d080ec7346203c648" \
      "git+https://github.com/chungmin99/pyroki.git@95afccc22658c461ab1042a048ae4e9c24bc2a47"

# Perception and simulator. All editable submodule installs use
# --no-build-isolation because their setup.py imports numpy at build time,
# mirroring CaP-X's uv `extra-build-dependencies`.
# SAM3 is pure PyTorch and runs on ROCm torch. Its weights are gated on
# HuggingFace, so they are pre-fetched with a token further down rather than
# downloaded at runtime.
RUN PIP_CONSTRAINT=/opt/capx-constraints.txt ${CAPX_VENV}/bin/pip install --no-cache-dir \
      -e capx/third_party/sam3 \
    && : "contact_graspnet_pytorch ships only a setup.py, so pip would take the" \
         "legacy 'setup.py develop' path. Setuptools >=77 implements that by" \
         "re-invoking pip in a subprocess WITHOUT --no-build-isolation, which" \
         "then cannot see numpy. --use-pep517 keeps the build in this env." \
    && PIP_CONSTRAINT=/opt/capx-constraints.txt ${CAPX_VENV}/bin/pip install --no-cache-dir \
      --use-pep517 --no-build-isolation -e capx/third_party/contact_graspnet_pytorch \
    && PIP_CONSTRAINT=/opt/capx-constraints.txt ${CAPX_VENV}/bin/pip install --no-cache-dir \
      --no-build-isolation -e capx/third_party/robosuite \
    && : "capx itself goes in without deps - they are all handled above - so" \
         "this only puts the package on the path, editable so that students" \
         "can change a docstring and see the agent's prompt change." \
    && ${CAPX_VENV}/bin/pip install --no-cache-dir --no-deps --no-build-isolation -e .

# Loading the perception models onto the GPU can take several minutes on a cold
# start. Upstream begins trials after 120 seconds even when those services are
# still unavailable, which fails the first trials of every run.
RUN sed -i \
      's/api_servers: list | None, wait_timeout: float = 120.0/api_servers: list | None, wait_timeout: float = 900.0/' \
      capx/envs/runner.py \
    && grep -q "wait_timeout: float = 900.0" capx/envs/runner.py

# ---------------------------------------------------------------------------
# PASTE YOUR HUGGINGFACE TOKEN HERE TO BUILD, AND CLEAR IT BEFORE COMMITTING.
# A build arg ends up in the image metadata, so this is for local builds only.
# The committed value must stay empty; export HF_TOKEN and let build.sh pass
# --secret id=hf_token instead, which keeps the token out of every layer.
# ---------------------------------------------------------------------------
ARG HF_TOKEN=""

# Pre-fetch the SAM3 weights so a workshop does not spend its first ten minutes
# downloading them, and so nothing at runtime needs a token. They cannot live
# under /home/jovyan: the Hub mounts a per-user volume there, which would hide
# anything baked in. facebook/sam3 is gated, so the build needs an account with
# approved access.
RUN --mount=type=secret,id=hf_token,required=false \
    HF_TOKEN="$(cat /run/secrets/hf_token 2>/dev/null || echo "${HF_TOKEN}")" \
    HF_HOME=${CAPX_CACHE} ${CAPX_VENV}/bin/python -c \
      "import os; \
from huggingface_hub import snapshot_download; \
assert os.environ.get('HF_TOKEN'), 'facebook/sam3 is gated - set HF_TOKEN, see the note above'; \
snapshot_download('facebook/sam3', ignore_patterns=['*.msgpack', '*.h5', '*.onnx', '*tf_model*', '*flax*'])"

# The CaP-X kernel. Its `env` is why the notebook needs no setup cell: the
# perception servers and launch.py are children of the kernel, so they inherit
# the weight cache and the headless GL backend from here. HF_HOME is scoped to
# this kernel for SAM3; notebook 04 starts lemond with HF_HOME=/opt/lemonade-cache
# so the LLM still resolves against the baked GGUF.
RUN mkdir -p /usr/local/share/jupyter/kernels/capx \
    && printf '%s\n' \
      '{' \
      '  "argv": ["/opt/capx-venv/bin/python", "-m", "ipykernel_launcher", "-f", "{connection_file}"],' \
      '  "display_name": "CaP-X (ROCm)",' \
      '  "language": "python",' \
      '  "env": {' \
      '    "HF_HOME": "/opt/capx-cache",' \
      '    "MUJOCO_GL": "egl",' \
      '    "PYOPENGL_PLATFORM": "egl",' \
      '    "CAPX_ROOT": "/ryzers/cap-x"' \
      '  }' \
      '}' \
      > /usr/local/share/jupyter/kernels/capx/kernel.json \
    && MUJOCO_GL=egl ${CAPX_VENV}/bin/python -c \
      "import torch, capx, robosuite, mujoco, pyroki; \
assert torch.version.hip, 'CaP-X dependencies replaced ROCm torch'; \
print('CaP-X ROCm environment OK:', torch.__version__, '| robosuite', robosuite.__version__)"

WORKDIR /ryzers

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
     ./course_data/capx_demo.py \
     /ryzers/

RUN ln -s /ryzers/notebooks/tests/test_ros.sh /ryzers/test_ros.sh \
    && ln -s /ryzers/notebooks/tests/test_o3de.sh /ryzers/test_o3de.sh \
    && ln -s /ryzers/notebooks/tests/test_rai.sh /ryzers/test_rai.sh \
    && ln -s /ryzers/notebooks/tests/test_lemonade-sdk.sh /ryzers/test_lemonade-sdk.sh \
    && ln -s /ryzers/notebooks/tests/test_capx.sh /ryzers/test_capx.sh \
    && chmod +x \
      /ryzers/lemonade_env.sh \
      /ryzers/manipulation_demo_headless.sh \
    && chown -R jovyan:100 \
      /home/jovyan/.cache \
      /home/jovyan/.streamlit \
      /home/jovyan/.asoundrc \
      /opt/capx-cache \
      /opt/lemonade-cache \
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

# HF_HOME is the baked model cache, so every notebook's lemond finds the
# pre-fetched GGUFs instead of re-downloading them into the empty user volume.
# LEMONADE_CACHE_DIR is what lemond reports as its cache dir and where it writes
# hub/, so it has to match the value the build pulled with.
ENV HOME=/home/jovyan \
    HF_HOME=/opt/lemonade-cache \
    LEMONADE_CACHE_DIR=/opt/lemonade-cache \
    XDG_RUNTIME_DIR=/tmp/runtime-jovyan

USER jovyan
WORKDIR /ryzers/notebooks

CMD ["/usr/local/bin/start-local-inference.sh"]
