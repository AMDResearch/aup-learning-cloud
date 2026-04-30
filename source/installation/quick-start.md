# Quick Start

This is the shortest path to a local single-node AUP Learning Cloud deployment.

## Prerequisites

- Ubuntu 24.04
- sudo access
- Docker available for the default install path
- an AMD GPU supported by the installer auto-detection or an explicit `--gpu=...` override

Install the basic host dependency:

```bash
sudo apt install build-essential
```

If Docker is not installed yet:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
docker --version
```

## Install

Clone the repository and run the installer from the repo root:

```bash
git clone https://github.com/AMDResearch/aup-learning-cloud.git
cd aup-learning-cloud
sudo ./auplc-installer install
```

After installation completes, open <http://localhost:30890>.

The checked-in default values in this repository use:

- `custom.authMode: auto-login`
- `proxy.service.type: NodePort`
- `proxy.service.nodePorts.http: 30890`
- `local-path` storage

So the default local experience is a simple HTTP NodePort deployment.

## Common Variants

```bash
# Pull prebuilt images instead of building locally
sudo ./auplc-installer install --pull

# Force a specific GPU family / target
sudo ./auplc-installer install --gpu=strix-halo

# Use containerd mode for more portable/offline-oriented operation
sudo ./auplc-installer install --docker=0

# Use registry and package mirrors
sudo ./auplc-installer install \
  --mirror=mirror.example.com \
  --mirror-pip=https://pypi.tuna.tsinghua.edu.cn/simple
```

## Uninstall

```bash
sudo ./auplc-installer uninstall
```

## Next Steps

- For all installer subcommands and runtime workflows, see [Single-Node Deployment](single-node.md)
- For auth and resource configuration, see [JupyterHub Configuration](../jupyterhub/index.md)
