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

# SHT-HIP Course Dockerfile
# Based on official AMD ROCm Ubuntu 24.04 complete image
FROM rocm/dev-ubuntu-24.04:7.2-complete

SHELL ["/bin/bash", "-c"]

ENV DEBIAN_FRONTEND=noninteractive
ENV ROCM_PATH=/opt/rocm
ENV PATH="${ROCM_PATH}/bin:${PATH}"
ENV LD_LIBRARY_PATH="${ROCM_PATH}/lib:${LD_LIBRARY_PATH}"

# Allow pip to install system-wide
RUN printf '[global]\nbreak-system-packages = true\n' > /etc/pip.conf

# Install system dependencies for HIP development
RUN apt-get update && apt-get install -y --no-install-recommends \
    sudo \
    build-essential \
    python3-dev \
    python3-pip \
    git \
    curl \
    wget \
    file \
    locales \
    fonts-liberation \
    run-one \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages for Jupyter environment
RUN pip3 install --no-cache-dir \
    jupyterhub==4.0.2 \
    jupyterlab==4.0.9 \
    notebook==7.0.6 \
    ipywidgets==8.1.1 \
    ipykernel==6.27.1 \
    matplotlib \
    numpy \
    Pillow

# Remove the default user if it exists (user with ID 1000)
RUN if getent passwd 1000 > /dev/null; then \
    userdel -r $(getent passwd 1000 | cut -d: -f1); \
    fi

# Create jovyan user with UID 1000 for consistency
RUN useradd -m -s /bin/bash -N -u 1000 -g 100 jovyan && \
    echo "jovyan ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Add jovyan to video group for GPU access
RUN usermod -aG video jovyan \
    && if getent group render; then \
        groupmod -g 992 render; \
    else \
        groupadd -g 992 render; \
    fi \
    && usermod -aG render jovyan

# Create necessary Jupyter directories with correct permissions
RUN mkdir -p /home/jovyan/.jupyter && \
    mkdir -p /home/jovyan/.local/share/jupyter/runtime && \
    chown -R 1000:100 /home/jovyan/.jupyter && \
    chown -R 1000:100 /home/jovyan/.local

# Create startup script for Jupyter
RUN echo '#!/bin/bash' > /home/jovyan/start-jupyter.sh && \
    echo 'export USER=jovyan' >> /home/jovyan/start-jupyter.sh && \
    echo 'export SHELL=/bin/bash' >> /home/jovyan/start-jupyter.sh && \
    echo 'exec python3 -m jupyterhub.singleuser --ip=0.0.0.0 --port=8888 "$@"' >> /home/jovyan/start-jupyter.sh && \
    chmod +x /home/jovyan/start-jupyter.sh && \
    chown jovyan:100 /home/jovyan/start-jupyter.sh

# Create entrypoint script to set permissions and start services
RUN echo '#!/bin/bash' > /entrypoint.sh && \
    echo 'chmod 666 /dev/kfd 2>/dev/null || true' >> /entrypoint.sh && \
    echo 'chmod 666 /dev/dri/renderD* 2>/dev/null || true' >> /entrypoint.sh && \
    echo 'export USER=jovyan' >> /entrypoint.sh && \
    echo 'export SHELL=/bin/bash' >> /entrypoint.sh && \
    echo 'exec python3 -m jupyterhub.singleuser --ip=0.0.0.0 --port=8888 "$@"' >> /entrypoint.sh && \
    chmod +x /entrypoint.sh

# Copy course materials
COPY ./course_data /opt/workspace/SHT-HIP

RUN chown -R jovyan:100 /opt/workspace

EXPOSE 8888

USER jovyan
WORKDIR /opt/workspace/SHT-HIP

CMD ["/bin/bash", "/entrypoint.sh"]
