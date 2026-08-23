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

# Keep Lemonade's daemon metadata and Hugging Face model cache outside
# /home/jovyan. JupyterHub mounts each user's PVC over that home directory,
# which would otherwise hide image-baked weights and make every workshop user
# download their own copy.
ENV LEMONADE_CACHE=/opt/lemonade-cache/lemonade \
    LEMONADE_HF_HOME=/opt/lemonade-cache/huggingface

# Models exercised by the workshop notebooks and script-first demos. Download
# only the quantizations Lemonade's built-in aliases use; pulling each complete
# GGUF repository would include many redundant quantizations.
RUN mkdir -p "${LEMONADE_CACHE}" "${LEMONADE_HF_HOME}" \
    && HF_HOME="${LEMONADE_HF_HOME}" python3 - <<'PY'
from huggingface_hub import snapshot_download

models = {
    "unsloth/gemma-4-E2B-it-GGUF": [
        "config.json",
        "gemma-4-E2B-it-Q4_K_M.gguf",
        "mmproj-F16.gguf",
    ],
    "unsloth/gemma-4-E4B-it-GGUF": [
        "config.json",
        "gemma-4-E4B-it-Q4_K_M.gguf",
        "mmproj-F16.gguf",
    ],
}
for repository, files in models.items():
    snapshot_download(repository, allow_patterns=files)
PY

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
# Robosuite eval path uses. SAM2 and OWLv2 come from Transformers, so the gated
# SAM3 submodule is deliberately excluded along with curobo, b1k, verl and
# LIBERO-PRO.
RUN /usr/bin/python3 -m venv --system-site-packages ${CAPX_VENV} \
    && git clone https://github.com/capgym/cap-x ${CAPX_ROOT} \
    && git -C ${CAPX_ROOT} checkout ${CAPX_REF} \
    && git -C ${CAPX_ROOT} submodule update --init \
      capx/third_party/contact_graspnet_pytorch \
      capx/third_party/robosuite

WORKDIR /ryzers/cap-x

# Base runtime deps: the PyPI-resolvable subset of [project.dependencies],
# minus torch/torchvision (kept from the base image) and the CUDA-only entries.
# Setuptools 77+ is needed because Robosuite pulls in pynput -> evdev, whose
# pyproject.toml uses the PEP 639 SPDX license form. The explicit lower bound
# also forces a copy into the venv instead of reusing the base image's older
# system setuptools.
RUN PIP_CONSTRAINT=/opt/capx-constraints.txt ${CAPX_VENV}/bin/pip install --no-cache-dir \
      "gymnasium>=0.29" "tyro>=0.8.5" "pydantic>=2.7" "rich>=13.7" \
      "scipy>=1.12" "matplotlib>=3.10,<3.11" "imageio[ffmpeg]>=0.6.0" \
      requests tqdm h5py einops decord pycocotools pyyaml omegaconf \
      open3d "robot_descriptions>=1.16.0" "yourdfpy>=0.0.56" "viser>=0.2.0" \
      "trimesh>=4.4.0" msgpack_numpy "ray==2.48.0" "mediapy>=1.2.5" \
      uvicorn fastapi "transformers<5.0" openai \
      "opencv-python-headless<4.13" "pillow>=10" cloudpickle \
      "setuptools>=77" \
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

# Perception and simulator. The ungated SAM2 and OWLv2 implementations are
# already part of CaP-X and use Transformers. Editable submodule installs use
# --no-build-isolation because their setup.py imports numpy at build time.
RUN : "contact_graspnet_pytorch ships only a setup.py, so pip would take the" \
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

# CaP-X ships both perception paths but registers SAM3 by default. Make the
# workshop's API and four live scenarios use OWLv2 for text grounding followed
# by box-prompted SAM2 segmentation.
RUN ${CAPX_VENV}/bin/python - <<'PY'
from pathlib import Path

registry = Path("capx/integrations/__init__.py")
text = registry.read_text()
old = 'register_api("FrankaControlApi", lambda env: FrankaControlApi(env, use_sam3=True))'
new = 'register_api("FrankaControlApi", lambda env: FrankaControlApi(env, use_sam3=False))'
assert text.count(old) == 1
text = text.replace(old, new)
old = (
    "lambda env: FrankaControlSpillWipeApi("
    "env, tcp_offset=[0.0, 0.0, -0.0158], use_sam3=True),"
)
new = (
    "lambda env: FrankaControlSpillWipeApi("
    "env, tcp_offset=[0.0, 0.0, -0.0158], use_sam3=False),"
)
assert text.count(old) == 1
registry.write_text(text.replace(old, new))

# ROCm takes several minutes to transfer these checkpoints to the APU when
# their CPU tensors are float32. Stage them as float16, then restore float32
# on-device; the GPU-side conversion is effectively instantaneous and retains
# FP32 execution. The workshop's held-out rollouts validate the staged weights.
owl_server = Path("capx/serving/launch_owlvit_server.py")
text = owl_server.read_text()
old = '    try:\n        if is_v2:\n'
new = (
    '    load_dtype = torch.float16 if device.startswith("cuda") else torch.float32\n\n'
    '    try:\n'
    '        if is_v2:\n'
)
assert text.count(old) == 1
text = text.replace(old, new)
for model_class in ("Owlv2ForObjectDetection", "OwlViTForObjectDetection"):
    old = f"_MODEL = {model_class}.from_pretrained(model_name)"
    new = f"_MODEL = {model_class}.from_pretrained(model_name, dtype=load_dtype)"
    assert text.count(old) == 1
    text = text.replace(old, new)
old = "        _MODEL = _MODEL.to(device)\n        _MODEL.eval()\n"
new = (
    "        _MODEL = _MODEL.to(device)\n"
    '        if device.startswith("cuda"):\n'
    "            _MODEL = _MODEL.float()\n"
    "        _MODEL.eval()\n"
)
assert text.count(old) == 1
owl_server.write_text(text.replace(old, new))

sam_server = Path("capx/serving/launch_sam2_server.py")
text = sam_server.read_text()
old = "    # Initialize Pipeline\n"
new = (
    '    load_dtype = torch.float16 if device_arg.startswith("cuda") else torch.float32\n\n'
    "    # Initialize Pipeline\n"
)
assert text.count(old) == 1
text = text.replace(old, new)
old = '    _GENERATOR = pipeline("mask-generation", model=model_name, device=device_arg)\n'
new = (
    '    _GENERATOR = pipeline(\n'
    '        "mask-generation", model=model_name, device=device_arg, dtype=load_dtype\n'
    "    )\n"
)
assert text.count(old) == 1
text = text.replace(old, new)
old = "        _MODEL = Sam2Model.from_pretrained(model_name).to(device_arg)\n"
new = "        _MODEL = Sam2Model.from_pretrained(model_name, dtype=load_dtype).to(device_arg)\n"
assert text.count(old) == 1
text = text.replace(old, new)
old = "    elif hasattr(_MODEL, \"to\"):\n        _MODEL = _MODEL.to(device_arg)\n\n"
new = (
    '    elif hasattr(_MODEL, "to"):\n'
    "        _MODEL = _MODEL.to(device_arg)\n"
    '    if device_arg.startswith("cuda"):\n'
    "        _MODEL = _MODEL.float()\n\n"
)
assert text.count(old) == 1
sam_server.write_text(text.replace(old, new))

old_server = """  - _target_: capx.serving.launch_sam3_server.main
    device: cuda
    port: 8114
    host: 127.0.0.1
"""
new_servers = """  - _target_: capx.serving.launch_owlvit_server.main
    model_name: google/owlv2-large-patch14-ensemble
    device: cuda
    port: 8117
    host: 127.0.0.1

  - _target_: capx.serving.launch_sam2_server.main
    model_name: facebook/sam2.1-hiera-large
    device: cuda
    port: 8113
    host: 127.0.0.1
"""
fast_servers = """  - _target_: capx.serving.launch_owlvit_server.main
    model_name: google/owlv2-base-patch16-ensemble
    device: cuda
    port: 8117
    host: 127.0.0.1

  - _target_: capx.serving.launch_sam2_server.main
    model_name: facebook/sam2.1-hiera-small
    device: cuda
    port: 8113
    host: 127.0.0.1
"""
configs = [
    "env_configs/cube_lifting/franka_robosuite_cube_lifting.yaml",
    "env_configs/cube_restack/franka_robosuite_cube_restack.yaml",
    "env_configs/cube_stack/franka_robosuite_cube_stack.yaml",
    "env_configs/spill_wipe/franka_robosuite_spill_wipe.yaml",
]
for config_name in configs:
    config = Path(config_name)
    text = config.read_text()
    assert text.count(old_server) == 1, config
    config.write_text(text.replace(old_server, new_servers))
    fast_config = config.with_name(f"{config.stem}_fast{config.suffix}")
    fast_config.write_text(text.replace(old_server, fast_servers))
PY

# Pre-fetch the default large and optional fast perception profiles.
# Excluding duplicate .pt/.bin files keeps both profiles reasonably compact.
RUN mkdir -p "${CAPX_CACHE}" \
    && HF_HOME="${CAPX_CACHE}" ${CAPX_VENV}/bin/python - <<'PY'
from huggingface_hub import snapshot_download

snapshot_download(
    "facebook/sam2.1-hiera-small",
    allow_patterns=[
        "config.json",
        "model.safetensors",
        "preprocessor_config.json",
        "processor_config.json",
        "*.yaml",
        "video_preprocessor_config.json",
    ],
)
snapshot_download(
    "google/owlv2-base-patch16-ensemble",
    allow_patterns=[
        "added_tokens.json",
        "config.json",
        "merges.txt",
        "model.safetensors",
        "preprocessor_config.json",
        "special_tokens_map.json",
        "tokenizer_config.json",
        "vocab.json",
    ],
)
snapshot_download(
    "facebook/sam2.1-hiera-large",
    allow_patterns=[
        "config.json",
        "model.safetensors",
        "preprocessor_config.json",
        "processor_config.json",
        "*.yaml",
        "video_preprocessor_config.json",
    ],
)
snapshot_download(
    "google/owlv2-large-patch14-ensemble",
    allow_patterns=[
        "added_tokens.json",
        "config.json",
        "merges.txt",
        "model.safetensors",
        "preprocessor_config.json",
        "special_tokens_map.json",
        "tokenizer_config.json",
        "vocab.json",
    ],
)
PY

# Loading the perception models onto the GPU can take several minutes on a cold
# start. Upstream begins trials after 120 seconds even when those services are
# still unavailable, which fails the first trials of every run.
RUN sed -i \
      's/api_servers: list | None, wait_timeout: float = 120.0/api_servers: list | None, wait_timeout: float = 900.0/' \
      capx/envs/runner.py \
    && grep -q "wait_timeout: float = 900.0" capx/envs/runner.py

# The CaP-X kernel. Its `env` is why the notebook needs no setup cell: the
# perception servers and launch.py are children of the kernel, so they inherit
# the baked perception cache and the headless GL backend from here.
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

# HELIX drives repository-level evolution; OpenCode is its local coding-agent
# backend. Keep this after the expensive CaP-X/weights layers so workshop
# harness changes do not rebuild the simulator and perception stack.
ARG HELIX_REF=29cfa6e5eae902f6bc6d2113e51499e92c6109ee
ARG OPENCODE_VERSION=1.18.18

RUN apt-get update \
    && apt-get install -y --no-install-recommends nodejs npm \
    && rm -rf /var/lib/apt/lists/* \
    && git clone https://github.com/KE7/helix.git /ryzers/helix \
    && git -C /ryzers/helix checkout "${HELIX_REF}" \
    && ${CAPX_VENV}/bin/pip install --no-cache-dir -e /ryzers/helix \
    && npm install --global "opencode-ai@${OPENCODE_VERSION}" \
    && npm cache clean --force \
    && ${CAPX_VENV}/bin/helix --help >/dev/null \
    && opencode --version \
    && MUJOCO_GL=egl ${CAPX_VENV}/bin/python -c \
      "import capx, helix, torch; assert torch.version.hip; print('HELIX/OpenCode workshop stack OK')"

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
     ./course_data/rho_demo.py \
     /ryzers/

RUN ln -s /ryzers/notebooks/tests/test_ros.sh /ryzers/test_ros.sh \
    && ln -s /ryzers/notebooks/tests/test_o3de.sh /ryzers/test_o3de.sh \
    && ln -s /ryzers/notebooks/tests/test_rai.sh /ryzers/test_rai.sh \
    && ln -s /ryzers/notebooks/tests/test_lemonade-sdk.sh /ryzers/test_lemonade-sdk.sh \
    && ln -s /ryzers/notebooks/tests/test_capx.sh /ryzers/test_capx.sh \
    && ln -s /ryzers/notebooks/tests/test_rho.sh /ryzers/test_rho.sh \
    && ln -s /ryzers/notebooks/tests/test_rai_toy_evolution.sh /ryzers/test_rai_toy_evolution.sh \
    && chmod +x \
      /ryzers/lemonade_env.sh \
      /ryzers/manipulation_demo_headless.sh \
      /ryzers/test_rho.sh \
      /ryzers/test_rai_toy_evolution.sh \
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

ENV HOME=/home/jovyan \
    HF_HOME=/home/jovyan/.cache/huggingface \
    LEMONADE_CACHE=/opt/lemonade-cache/lemonade \
    LEMONADE_HF_HOME=/opt/lemonade-cache/huggingface \
    XDG_RUNTIME_DIR=/tmp/runtime-jovyan

USER jovyan
WORKDIR /ryzers/notebooks

CMD ["/usr/local/bin/start-local-inference.sh"]
