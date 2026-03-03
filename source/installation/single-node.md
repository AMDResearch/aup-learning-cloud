# Single-Node Deployment

This guide provides step-by-step instructions for manually deploying AUP Learning Cloud on a single node. This deployment is suitable for development, testing, and demo environments.

:::{seealso}
For quick automated installation, see the [Quick Start](quick-start.md) guide.
:::

## Prerequisites

### Hardware Requirements

- **Device**: AMD Ryzen™ AI Halo Device (e.g., AI Max+ 395, AI Max 390)
- **Memory**: 32GB+ RAM (64GB recommended for production-like testing)
- **Storage**: 500GB+ SSD
- **Network**: Stable internet connection for downloading images

### Software Requirements

- **Operating System**: Ubuntu 24.04.3 LTS
- **Docker**: Version 20.10 or later
- **Root/Sudo Access**: Required for installation

## Installation Steps

### 1. Install Docker

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh

# Add current user to docker group
sudo usermod -aG docker $USER

# Apply group changes (or logout/login)
newgrp docker

# Install Build Tools
sudo apt install build-essential

# Verify installation
docker --version
```

:::{seealso}
See [Docker Post-installation Steps](https://docs.docker.com/engine/install/linux-postinstall/) for detailed configuration.
:::

### 2. Install K3s

K3s is a lightweight Kubernetes distribution optimized for resource-constrained environments.

```bash
# Install K3s with readable kubeconfig (recommended for non-root kubectl)
curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION=v1.32.3+k3s1 K3S_KUBECONFIG_MODE="644" sh -

# Verify installation
sudo k3s kubectl get nodes
```

:::{tip}
`K3S_KUBECONFIG_MODE="644"` makes the kubeconfig file readable by your user so you can run `kubectl` without copying the file. See [K3s Cluster Access](https://docs.k3s.io/cluster-access).
:::

K3s includes a built-in **local-path** StorageClass, so no extra storage setup is needed for single-node.

### 3. Configure kubectl

```bash
# Create kubectl config directory
mkdir -p ~/.kube

# Copy K3s config
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config

# Fix permissions (if not using K3S_KUBECONFIG_MODE="644")
sudo chown $USER:$USER ~/.kube/config

# Verify
kubectl get nodes
kubectl get storageclass
```

### 4. Install Helm

Helm is the package manager for Kubernetes.

```bash
# Install Helm (v3.17.2 or later recommended)
wget https://get.helm.sh/helm-v3.17.2-linux-amd64.tar.gz -O /tmp/helm-linux-amd64.tar.gz
cd /tmp && tar -zxvf helm-linux-amd64.tar.gz
sudo mv linux-amd64/helm /usr/local/bin/helm

# Verify installation
helm version
```

### 5. Install ROCm (for GPU nodes)

On AMD GPU systems, install the ROCm driver and device plugin so JupyterHub can schedule GPU workloads.

```bash
# Follow the official guide for Ubuntu 24.04
# https://rocm.docs.amd.com/projects/install-on-linux/en/latest/install/quick-start.html

# Deploy the ROCm device plugin
kubectl create -f https://raw.githubusercontent.com/ROCm/k8s-device-plugin/master/k8s-ds-amdgpu-dp.yaml

# Verify GPU is allocatable
kubectl get nodes -o jsonpath='{.items[*].status.allocatable}' | grep amd
```

### 6. Label the node (GPU / NPU)

If you have GPU or NPU hardware, label the node so the spawner can schedule user pods correctly. Use the same labels as in `custom.accelerators` in `runtime/values.yaml`.

```bash
NODE_NAME=$(kubectl get nodes -o jsonpath='{.items[0].metadata.name}')

# Examples (choose one that matches your hardware):
kubectl label nodes $NODE_NAME node-type=strix-halo    # Strix Halo iGPU
kubectl label nodes $NODE_NAME node-type=strix         # Strix iGPU
kubectl label nodes $NODE_NAME node-type=dgpu          # Discrete GPU

kubectl get nodes --show-labels | grep node-type
```

### 7. Clone the repository and configure

```bash
git clone https://github.com/AMDResearch/aup-learning-cloud.git
cd aup-learning-cloud
git checkout develop   # Use the branch that contains runtime/ and chart/
```

Edit **`runtime/values.yaml`** to match your environment (auth, images, storage, network). The default uses **auto-login** and **NodePort 30890**.

Key sections to configure:

- **custom.authMode** — `auto-login` (dev), `github`, or `multi`
- **custom.resources.images** / **requirements** / **metadata** — Course images and UI
- **custom.accelerators** — GPU/NPU node types and labels
- **custom.teams.mapping** — Which teams can access which courses
- **hub.config.GitHubOAuthenticator** — If using GitHub OAuth
- **proxy** / **ingress** — NodePort (default 30890) or domain + TLS

See the [Configuration Reference: runtime/values.yaml](../jupyterhub/configuration-reference.md) for every section and recommended workflow.

:::{note}
To use **pre-built images** from the registry (default in `runtime/values.yaml`), no local Docker build is required. To build images yourself, use the `dockerfiles/` and `make` targets on the develop branch, then set the image names/tags in `runtime/values.yaml` accordingly.
:::

### 8. Deploy JupyterHub

From the **runtime** directory:

```bash
cd runtime

# First-time install
helm install jupyterhub ./chart \
  --namespace jupyterhub \
  --create-namespace \
  -f values.yaml
```

For upgrades after editing `values.yaml`:

```bash
helm upgrade jupyterhub ./chart -n jupyterhub -f values.yaml
```

On the develop branch, a helper script is also available: `bash scripts/helm_upgrade.bash` (run from the repo root or runtime, depending on the script).

### 9. Verify deployment

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

To upgrade JupyterHub after configuration changes:

```bash
cd runtime
helm upgrade jupyterhub ./chart -n jupyterhub -f values.yaml
```

If you use the develop branch and have the deploy helper script:

```bash
cd runtime
bash scripts/helm_upgrade.bash
```

To rebuild container images after changing Dockerfiles (develop branch):

```bash
cd dockerfiles
make all
```

Then update image tags in `runtime/values.yaml` and run `helm upgrade` as above.

## Uninstalling

To remove the JupyterHub release (keeps the namespace and PVCs unless you delete them):

```bash
helm uninstall jupyterhub -n jupyterhub
```

To remove the namespace and free resources:

```bash
kubectl delete namespace jupyterhub
```

On the develop branch, a full uninstall script is available:

```bash
cd deploy
sudo ./single-node.sh uninstall
```

## Next Steps

- [Configure JupyterHub](../jupyterhub/index.md)
- [Set up Authentication](../jupyterhub/authentication-guide.md)
- [Manage Users](../jupyterhub/user-management.md)
- [Configure Quotas](../jupyterhub/quota-system.md)
