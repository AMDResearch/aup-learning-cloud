# Single-Node Deployment

This guide describes single-node deployment of AUP Learning Cloud using the **auplc-installer** script on the **develop** branch. This deployment is suitable for development, testing, and demo environments.

:::{seealso}
For the shortest path, see the [Quick Start](quick-start.md) guide.
:::

## Prerequisites

### Hardware Requirements

- **Device**: AMD Ryzen™ AI Halo Device (e.g., AI Max+ 395, AI Max 390)
- **Memory**: 32GB+ RAM (64GB recommended for production-like testing)
- **Storage**: 500GB+ SSD
- **Network**: Stable internet connection for downloading images

### Software Requirements

- **Operating System**: Ubuntu 24.04.3 LTS
- **Docker**: Version 20.10 or later (required when using default Docker-as-runtime mode)
- **Root/Sudo Access**: Required to run the installer

## Installation with auplc-installer

On the **develop** branch, single-node installation is done with the **auplc-installer** script at the repository root.

### 1. Install Docker

The installer uses the host Docker by default so that image updates are visible to K3s without re-export. Install Docker first:

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh

# Add current user to docker group
sudo usermod -aG docker $USER

# Apply group changes (or logout/login)
newgrp docker

# Install Build Tools (needed for building images)
sudo apt install build-essential

# Verify installation
docker --version
```

:::{seealso}
See [Docker Post-installation Steps](https://docs.docker.com/engine/install/linux-postinstall/) for detailed configuration.
:::

### 2. Clone the repository and run the installer

```bash
git clone https://github.com/AMDResearch/aup-learning-cloud.git
cd aup-learning-cloud
git checkout develop

# Full installation (K3s, Helm, K9s, ROCm device plugin, images, JupyterHub)
sudo ./auplc-installer install
```

After installation completes, open <http://localhost:30890> in your browser. The default uses **auto-login** — no credentials required.

### 3. auplc-installer commands

| Command | Description |
|---------|-------------|
| `install` | Full installation (K3s, tools, GPU plugin, images, JupyterHub) |
| `uninstall` | Remove K3s and all components |
| `install-tools` | Install Helm and K9s only |
| `rt install` | Deploy JupyterHub runtime only |
| `rt upgrade` | Upgrade JupyterHub (e.g. after editing `runtime/values.yaml`) |
| `rt remove` | Remove JupyterHub runtime only |
| `rt reinstall` | Remove and reinstall JupyterHub (e.g. after image changes) |
| `img build` | Build all custom container images |
| `img build [target...]` | Build specific images (e.g. `img build hub`, `img build hub cv`) |
| `img pull` | Pull external images for offline use |

Legacy long-form commands are still supported: `install-runtime`, `remove-runtime`, `upgrade-runtime`, `build-images`, `pull-images`.

**Examples:**

```bash
# Upgrade JupyterHub after changing runtime/values.yaml
sudo ./auplc-installer rt upgrade

# Rebuild images and reinstall runtime after Dockerfile changes
sudo ./auplc-installer img build
sudo ./auplc-installer rt reinstall

# Show all options
./auplc-installer help
```

### 4. Runtime and mirror configuration

You can pass environment variables when running the installer:

- **K3S_USE_DOCKER** (default: `1`) — Use host Docker as K3s container runtime so that images built with `make hub` are visible after `rt upgrade`. Set to `0` for containerd mode with image export (offline/portable).

  ```bash
  K3S_USE_DOCKER=0 sudo ./auplc-installer install
  ```

- **MIRROR_PREFIX** — Registry mirror host (e.g. `mirror.example.com`) for container images.

  ```bash
  MIRROR_PREFIX="mirror.example.com" sudo ./auplc-installer install
  ```

- **MIRROR_PIP** / **MIRROR_NPM** — Package mirrors for image builds (e.g. `img build`).

### 5. Configure runtime (optional)

To customize auth, images, storage, network, and other options, edit **`runtime/values.yaml`**. For all available settings and recommended workflow, see the [Configuration Reference: runtime/values.yaml](../jupyterhub/configuration-reference.md).

After editing, run:

```bash
sudo ./auplc-installer rt upgrade
```

### 6. Verify deployment

```bash
# Check all pods are running
kubectl get pods -n jupyterhub

# Check services
kubectl get svc -n jupyterhub

# Get admin credentials (if auto-admin is enabled)
kubectl -n jupyterhub get secret jupyterhub-admin-credentials \
  -o go-template='{{index .data "admin-password" | base64decode}}'
```

## Access JupyterHub

- **NodePort (default)**: <http://localhost:30890> or <http://node-ip:30890>
- **Domain**: <https://your-domain.com> (if configured)

## Post-Installation

### Configure Authentication

See [Authentication Guide](../jupyterhub/authentication-guide.md) to set up:
- GitHub OAuth
- Native Authenticator
- User management

### Configure Resource Quotas

See [User Quota System](../jupyterhub/quota-system.md) to configure resource limits and tracking.

### Manage Users

See [User Management Guide](../jupyterhub/user-management.md) for batch user operations.

## Troubleshooting

### Pods Not Starting

```bash
# Check pod status
kubectl describe pod <pod-name> -n jupyterhub

# Check logs
kubectl logs <pod-name> -n jupyterhub
```

### Image Pull Errors

```bash
# Check events
kubectl get events -n jupyterhub

# Verify images are available
docker images | grep ghcr.io/amdresearch
```

### Connection Issues

```bash
# Check service status
kubectl get svc -n jupyterhub

# Check ingress (if using domain)
kubectl get ingress -n jupyterhub
```

## Upgrading

To upgrade JupyterHub after editing `runtime/values.yaml`:

```bash
sudo ./auplc-installer rt upgrade
```

To rebuild container images after changing Dockerfiles, then reinstall runtime:

```bash
sudo ./auplc-installer img build
sudo ./auplc-installer rt reinstall
```

## Uninstalling

To remove JupyterHub runtime only (keeps K3s and other components):

```bash
sudo ./auplc-installer rt remove
```

To remove everything (K3s, JupyterHub, and installer-managed resources):

```bash
sudo ./auplc-installer uninstall
```

## Next Steps

- [Configure JupyterHub](../jupyterhub/index.md)
- [Set up Authentication](../jupyterhub/authentication-guide.md)
- [Manage Users](../jupyterhub/user-management.md)
- [Configure Quotas](../jupyterhub/quota-system.md)
