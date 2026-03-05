# Quick Start

The simplest way to deploy AUP Learning Cloud on a single machine in a development or demo environment.

## Prerequisites

- **Hardware**: Supported AMD GPU or APU — select your device in the Installation section below. Examples:
  - **Radeon PRO**: AI PRO R9700/R9600D
  - **Radeon**: RX 9070/9060 series
  - **Ryzen AI**: Max+ PRO 395, Max PRO 390/385/380, Max+ 395, Max 390/385, 9 HX 375/370, 9 365
- **Memory**: 32GB+ RAM (64GB recommended)
- **Storage**: 500GB+ SSD
- **OS**: Ubuntu 24.04.3 LTS
- **Docker**: Install Docker and configure for non-root access (see below; skip if already installed)

### Package dependencies

Install build tools (required for building container images):

```bash
sudo apt install build-essential
```

### Install Docker

:::{dropdown} Install Docker — skip if already installed
:animate: fade-in

If Docker is already installed and your user is in the `docker` group, skip this section.

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh

# Add current user to docker group
sudo usermod -aG docker $USER

# Apply group changes without logout (or logout/login instead)
newgrp docker

# Verify installation
docker --version
```

See [Docker Post-installation Steps](https://docs.docker.com/engine/install/linux-postinstall/) and [Install Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/) for details.


:::

## Installation

Select your AMD device family and GPU below. The install commands update to use the correct **GPU_TYPE** for your selection.

```{eval-rst}
.. include:: includes/selector-quickstart-gpu.rst
```

After installation completes, open <http://localhost:30890> in your browser. No login credentials are required — you will be automatically logged in.

## Uninstall

To remove all components (K3s, JupyterHub, and related resources):

```bash
sudo ./auplc-installer uninstall
```

:::{seealso}
For all other commands (upgrade, runtime-only install/remove, image build/pull, mirror configuration, etc.), see the [Single-Node Deployment](single-node.md) guide.
:::

## Next Steps

After installation:

1. Access JupyterHub at <http://localhost:30890>
2. Review the [JupyterHub Configuration](../jupyterhub/index.md) guide
3. Set up [Authentication](../jupyterhub/authentication-guide.md) if needed
4. Configure [User Management](../jupyterhub/user-management.md) for your environment
5. Explore the available learning toolkits
