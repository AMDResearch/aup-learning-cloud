# Single-Node Deployment

This guide covers the current single-node workflow driven by `./auplc-installer`.

:::{seealso}
For the shortest path, see [Quick Start](quick-start.md).
:::

## What The Installer Does

`./auplc-installer install` is the canonical workstation deployment path. It can:

- detect supported AMD GPU families and SKUs
- install K3s and supporting tools
- deploy the ROCm GPU device plugin and node labeller
- generate a local values overlay
- build or pull required images
- deploy the Hub runtime from `runtime/chart`

## Prerequisites

- Ubuntu 24.04
- sudo access
- Docker installed if you are using the default Docker-backed runtime path
- `build-essential`

```bash
sudo apt install build-essential
```

Optional Docker installation:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
docker --version
```

## Standard Install

```bash
git clone https://github.com/AMDResearch/aup-learning-cloud.git
cd aup-learning-cloud
sudo ./auplc-installer install
```

After installation, access the Hub at <http://localhost:30890>.

## Important Defaults In This Repository

The current checked-in `runtime/values.yaml` is oriented to simple local deployment:

- `custom.authMode: auto-login`
- `custom.adminUser.enabled: false`
- `hub.db.pvc.storageClassName: local-path`
- `singleuser.storage.dynamic.storageClass: local-path`
- `proxy.service.type: NodePort`
- `proxy.service.nodePorts.http: 30890`
- `ingress.enabled: false`
- `prePuller.hook.enabled: false`
- `prePuller.continuous.enabled: false`

That means NFS, ingress, TLS, and auto-created admin credentials are optional configuration choices, not default behavior.

## Installer Command Matrix

### Core Lifecycle

```bash
sudo ./auplc-installer install
sudo ./auplc-installer uninstall
sudo ./auplc-installer detect-gpu
sudo ./auplc-installer install-tools
```

### Runtime Lifecycle

```bash
sudo ./auplc-installer rt install
sudo ./auplc-installer rt upgrade
sudo ./auplc-installer rt remove
sudo ./auplc-installer rt reinstall
```

### Image Lifecycle

```bash
sudo ./auplc-installer img build
sudo ./auplc-installer img build hub cv
sudo ./auplc-installer img pull
```

### Development Workflow

```bash
sudo ./auplc-installer dev
sudo ./auplc-installer dev deploy
sudo ./auplc-installer dev upgrade
sudo ./auplc-installer dev reinstall
```

## Common Install Flags

```bash
# Pull prebuilt custom images instead of building them locally
sudo ./auplc-installer install --pull

# Explicitly set GPU family / target
sudo ./auplc-installer install --gpu=strix-halo

# Use containerd mode instead of Docker-backed mode
sudo ./auplc-installer install --docker=0

# Use registry / package mirrors
sudo ./auplc-installer install \
  --mirror=mirror.example.com \
  --mirror-pip=https://pypi.example.com/simple \
  --mirror-npm=https://registry.npmmirror.com
```

Supported install-time flags map to these environment variables:

| Flag | Environment Variable | Meaning |
|------|----------------------|---------|
| `--gpu=TYPE` | `GPU_TYPE` | Force GPU type / family |
| `--docker=0\|1` | `K3S_USE_DOCKER` | Choose Docker or containerd path |
| `--mirror=HOST` | `MIRROR_PREFIX` | Container registry mirror prefix |
| `--mirror-pip=URL` | `MIRROR_PIP` | Python package mirror |
| `--mirror-npm=URL` | `MIRROR_NPM` | npm registry mirror |

## Offline And Portable Workflows

### Containerd / Portable-Oriented Local Install

```bash
sudo ./auplc-installer install --docker=0
```

This path exports images into K3s image storage and is better suited for portable or partially disconnected use than the default Docker-backed path.

### Offline Bundle Workflow

Create an offline bundle on a connected machine:

```bash
./auplc-installer pack

# Or build bundle from local images/artifacts
./auplc-installer pack --local
```

Transfer the bundle to the target machine, unpack it, then run:

```bash
sudo ./auplc-installer install
```

The installer auto-detects the bundle via `manifest.json` and switches into offline mode.

## Local Configuration Files

- `runtime/values.yaml` - repository default deployment values
- `runtime/values.local.yaml` - installer-generated local overlay

The installer-generated overlay captures detected accelerator selectors and image tags for the local machine. Prefer editing `runtime/values.yaml` for intentional site configuration, then redeploy with:

```bash
sudo ./auplc-installer rt upgrade
```

## Verification

```bash
kubectl get pods -n jupyterhub
kubectl get svc -n jupyterhub
kubectl get pvc -n jupyterhub
```

If you explicitly enabled admin bootstrap:

```bash
kubectl -n jupyterhub get secret jupyterhub-admin-credentials \
  -o jsonpath='{.data.admin-password}' | base64 -d && echo
```

## Troubleshooting Notes

- If you changed `runtime/values.yaml`, use `sudo ./auplc-installer rt upgrade`.
- If you changed container images or Dockerfiles, use `sudo ./auplc-installer img build` followed by `sudo ./auplc-installer rt reinstall`.
- If you need cluster-specific storage, ingress, or TLS behavior, those are configuration changes on top of the default single-node setup, not built-in assumptions.
