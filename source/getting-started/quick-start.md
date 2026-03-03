# Quick Start

The simplest way to deploy AUP Learning Cloud on a single machine in a development or demo environment.

## Prerequisites

- **Hardware**: AMD Ryzen™ AI Halo Device (e.g., AI Max+ 395, AI Max 390)
- **Memory**: 32GB+ RAM (64GB recommended)
- **Storage**: 500GB+ SSD
- **OS**: Ubuntu 24.04.3 LTS
- **Docker**: Install Docker and configure for non-root access

### Install Docker

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh

# Add current user to docker group
sudo usermod -aG docker $USER

# Apply group changes without logout (or logout/login instead)
newgrp docker

# Install Build Tools
sudo apt install build-essential
```

:::{seealso}
See [Docker Post-installation Steps](https://docs.docker.com/engine/install/linux-postinstall/) and [Install Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/) for details.
:::

## Installation

Use the **auplc-installer** script on the **develop** branch:

```bash
git clone https://github.com/AMDResearch/aup-learning-cloud.git
cd aup-learning-cloud
git checkout develop

sudo ./auplc-installer install
```

After installation completes, open <http://localhost:30890> in your browser. No login credentials are required — you will be automatically logged in.

## Uninstall

To remove all components (K3s, JupyterHub, and related resources):

```bash
sudo ./auplc-installer uninstall
```

:::{seealso}
For all other commands (upgrade, runtime-only install/remove, image build/pull, mirror configuration, etc.), see the [Single-Node Deployment](../installation/single-node.md) guide.
:::

## Next Steps

After installation:

1. Access JupyterHub at <http://localhost:30890>
2. Review the [JupyterHub Configuration](../jupyterhub/index.md) guide
3. Set up [Authentication](../jupyterhub/authentication-guide.md) if needed
4. Configure [User Management](../jupyterhub/user-management.md) for your environment
5. Explore the available [Learning Solutions](index.md#learning-solutions)
