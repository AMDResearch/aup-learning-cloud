# Single-Node Deployment

This guide describes single-node deployment of AUP Learning Cloud using the **auplc-installer** script on the **develop** branch. This deployment is suitable for development, testing, and demo environments.

:::{seealso}
For the shortest path, see the [Quick Start](quick-start.md) guide.
:::

## Prerequisites

### Hardware Requirements

- **Device**: Supported AMD GPU or APU — select your device in the Installation section below. Examples:
  - **Radeon PRO**: AI PRO R9700/R9600D
  - **Radeon**: RX 9070/9060 series
  - **Ryzen AI**: Max+ PRO 395, Max PRO 390/385/380, Max+ 395, Max 390/385, 9 HX 375/370, 9 365
- **Memory**: 32GB+ RAM (64GB recommended for production-like testing)
- **Storage**: 500GB+ SSD
- **Network**: Stable internet connection for downloading images

### Software Requirements

- **Operating System**: Ubuntu 24.04.3 LTS
- **Docker**: Version 20.10 or later (required when using default Docker-as-runtime mode)
- **Root/Sudo Access**: Required to run the installer

## Installation with auplc-installer

On the **develop** branch, single-node installation is done with the **auplc-installer** script at the repository root.

### 1. Package dependency

Install build tools (required for building container images):

```bash
sudo apt install build-essential
```

### 2. Install Docker

By default, Docker is used as the K3s container runtime (backend).

:::{dropdown} Install Docker — skip if already installed
:animate: fade-in

If Docker is already installed and your user is in the `docker` group, skip this section.

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh

# Add current user to docker group
sudo usermod -aG docker $USER

# Apply group changes (or logout/login)
newgrp docker

# Verify installation
docker --version
```

See [Docker Post-installation Steps](https://docs.docker.com/engine/install/linux-postinstall/) for detailed configuration.

:::

### 3. Clone the repository and run the installer

Select your AMD device family and GPU below. The install commands update to use the correct **GPU_TYPE** for your selection.

```{eval-rst}
.. include:: includes/selector-quickstart-gpu.rst
```

After installation completes, open <http://localhost:30890> in your browser. The default uses **auto-login** — no credentials required.

### 4. auplc-installer commands

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

### 5. Runtime and mirror configuration

You can pass environment variables when running the installer:

- **K3S_USE_DOCKER** (default: `1`) — Use host Docker as K3s container runtime so that images built with `img build` are visible after `rt upgrade`. Set to `0` for containerd mode with image export (offline/portable).

  ```bash
  K3S_USE_DOCKER=0 sudo ./auplc-installer install
  ```

- **MIRROR_PREFIX** — Registry mirror host (e.g. `mirror.example.com`) for container images.

  ```bash
  MIRROR_PREFIX="mirror.example.com" sudo ./auplc-installer install
  ```

- **MIRROR_PIP** / **MIRROR_NPM** — Package mirrors for image builds (e.g. `img build`).

### 6. Configure runtime (optional)

To customize auth, images, storage, network, and other options, edit **`runtime/values.yaml`**. For all available settings and recommended workflow, see the [Configuration Reference: runtime/values.yaml](../jupyterhub/configuration-reference.md).

After editing, run:

```bash
sudo ./auplc-installer rt upgrade
```

### 7. Verify deployment

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

## Offline / Portable Operation

The installer automatically configures the system for offline and portable operation. When you run `sudo ./auplc-installer install`, it:

1. **Creates a dummy network interface** (`dummy0`) with a stable IP address (`10.255.255.1`)
2. **Binds K3s to the dummy interface** using `--node-ip` and `--flannel-iface`
3. **Pre-pulls all required container images** to local storage
4. **Configures K3s to use local images** from `/var/lib/rancher/k3s/agent/images/`

This ensures the cluster remains fully functional even when:
- External network is disconnected (network cable unplugged)
- WiFi network changes (connecting to different access points)
- No network is available at all

**How it works**: K3s is bound to a stable dummy interface IP instead of the physical network interface. This means K3s doesn't care about external network changes -- it always uses the same internal IP for cluster communication.

**Reference**: [K3s Air-Gap Installation](https://docs.k3s.io/installation/airgap)

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
