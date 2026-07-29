<!-- Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.  Portions of this notebook consist of AI-generated content. -->
<!--
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
-->


# Deployment

This directory contains infrastructure code for deploying AUP Learning Cloud.

## Directory Structure

```
deploy/
├── ansible/    # Ansible playbooks for K3s cluster setup
├── k8s/        # Kubernetes components (NFS provisioner, device plugins)
├── scripts/    # Helper scripts for cluster setup
└── docs/       # Architecture diagrams
```

## Documentation

For full deployment instructions, see the documentation site:

- [Single-Node Deployment](https://amdresearch.github.io/aup-learning-cloud/installation/single-node.html)
- [Multi-Node Cluster Deployment](https://amdresearch.github.io/aup-learning-cloud/installation/multi-node.html)
- [Configuration Reference](https://amdresearch.github.io/aup-learning-cloud/jupyterhub/configuration-reference.html)

## Quick Start

### Single Node

```bash
cd ..
sudo ./auplc-installer install
```

### Multi-Node Cluster

For SSH-preinstalled nodes, edit the Ansible inventory and multi-node values
file directly. PXE remains generator-based because the controller inventory,
rootfs settings, runtime overlay, and GPU policy must be generated as one
consistent artifact set.

The AMD device plugin and ROCm node labeller are cluster infrastructure
prerequisites owned outside AUPLC. The infrastructure owner must deploy and
maintain them according to AMD's official guidance. If they are not installed,
follow the pinned manual installation commands in the
[Kubernetes components guide](k8s/README.md). Before Helm, verify that the
DaemonSets are ready and that GPU capacity is advertised.

#### SSH-preinstalled

Edit `deploy/ansible/inventory.yml` with the server and agent hostnames, IPs,
k3s token, and other site settings. Keep the human template default,
`auplc_gpu_access_enabled: auto`, unquoted on each host. `auto` runs Python 3 on
that host to scan `/sys/bus/pci/devices` for vendor `0x1002` devices whose PCI
class starts with `0x03`. It does not use `lspci` or require `pciutils`. A match
enables ROCm and the AMD GPU access package; a successful scan with no match
skips both. If a scan fails, the play aborts before either is changed, and
`any_errors_fatal` stops the play for all hosts.

Set an unquoted YAML boolean `true` or `false` only when you need to override
detection. `true` forces ROCm and package installation, while `false` forces
both to be skipped. Either boolean bypasses the scan. Don't quote any of these
values or use alternatives such as `yes` and `no`.

For example:

```yaml
k3s_cluster:
  children:
    server:
      hosts:
        controller-1:
          ansible_host: 192.0.2.10
          auplc_gpu_access_enabled: auto
    agent:
      hosts:
        gpu-worker-1:
          ansible_host: 192.0.2.11
          auplc_gpu_access_enabled: auto
```

Copy the human-maintained multi-node values example, then edit the copy for the
site's authentication, storage, images, accelerators, and network access:

```bash
cd ..
REPO_ROOT="$(pwd)"
DEPLOY_SCRIPTS="$REPO_ROOT/skills/deploy-aup-learning-cloud/scripts"
cp runtime/values-multi-nodes.yaml.example runtime/values-multi-nodes.yaml
# Edit deploy/ansible/inventory.yml and runtime/values-multi-nodes.yaml.

python3 "$DEPLOY_SCRIPTS/validate.py" --repo "$REPO_ROOT" --topology ssh-preinstalled \
  --inventory "$REPO_ROOT/deploy/ansible/inventory.yml" \
  --values "$REPO_ROOT/runtime/values.yaml" \
  --values "$REPO_ROOT/runtime/values-multi-nodes.yaml" \
  --helm-dry-run

cd "$REPO_ROOT/deploy/ansible"
sudo ansible-playbook -i inventory.yml playbooks/pb-base.yml
sudo ansible-playbook -i inventory.yml playbooks/pb-k3s-site.yml
sudo ansible-playbook -i inventory.yml playbooks/pb-rocm.yml

kubectl rollout status -n kube-system daemonset/amdgpu-device-plugin-daemonset --timeout=5m
kubectl rollout status -n kube-system daemonset/amdgpu-labeller-daemonset --timeout=5m
kubectl get nodes -o 'custom-columns=NAME:.metadata.name,AMD_GPU:.status.allocatable.amd\.com/gpu'

cd "$REPO_ROOT"
helm upgrade --install jupyterhub ./runtime/chart \
  --namespace jupyterhub --create-namespace \
  -f runtime/values.yaml \
  -f runtime/values-multi-nodes.yaml
```

With `--inventory` alone, the validator accepts exactly one unquoted `auto`,
`true`, or `false` value for `auplc_gpu_access_enabled` on every managed host.
This validates the direct-edit workflow without a generated GPU resolution
report. `--gpu-resolution` may be supplied only with `--inventory`; that pair
is for generated artifacts, whose inventory values and resolution entries must
remain strict booleans. The generator never writes `auto`.

The installer, Ansible GPU access role, and PXE controller install AMD's
`amdgpu-insecure-instinct-udev-rules` package, pinned to version
`30.30.4.0-2341068.24.04`. Its package-owned rule sets mode `0666` only on
`/dev/kfd` and DRM `/dev/dri/renderD*` nodes. It does not match
`/dev/dri/card*`; card nodes retain the normal system policy, observed as
`root:video 0660`.

This host permission policy is separate from Kubernetes allocation. The AMD
device plugin remains the visibility boundary: only Pods that request
`amd.com/gpu` receive allocated GPU devices, and the plugin does not change
host inode ownership or mode. AUPLC Hub adds no GPU supplemental group. The
tested ROCm compute path needs none: on both SHC GPU nodes, `rocminfo` succeeded
as UID `12345` with only supplemental GID `100`, while card nodes remained
inaccessible at mode `0660`. The reported agents were `gfx1151` and `gfx1200`.

`singleuser.fsGid: 100` controls shared notebook storage ownership only. It is
not part of GPU access and must not be treated as a GPU group setting.

#### PXE-diskless

Create a fresh spec, set `topology` to `pxe-diskless`, fill the PXE network
fields, and set `pxe.diskless_agents_have_amd_gpus` explicitly. Diskless agent
hardware can't be inferred from the controller. Generation writes the canonical
inventory, controller vars, runtime overlay, and GPU resolution report directly.
These artifacts express the desired deployment inputs; their existence is not
proof that rootfs provisioning succeeded. Review and install them before running
the controller playbook, whose successful completion provisions the rootfs.

```bash
cd ..
REPO_ROOT="$(pwd)"
DEPLOY_SCRIPTS="$REPO_ROOT/skills/deploy-aup-learning-cloud/scripts"
python3 "$DEPLOY_SCRIPTS/gen_configs.py" --print-schema > spec.json
# Edit spec.json: choose pxe-diskless and fill the node, network, and PXE fields.
GENERATED_DIR="$REPO_ROOT/generated"

cd "$REPO_ROOT"
python3 "$DEPLOY_SCRIPTS/gen_configs.py" --spec spec.json --out-dir "$GENERATED_DIR"
install -m 0600 "$GENERATED_DIR/inventory.yml" "$REPO_ROOT/deploy/ansible/inventory.yml"
install -m 0644 "$GENERATED_DIR/values-basic-example.yaml" "$REPO_ROOT/runtime/values-basic-example.yaml"
python3 "$DEPLOY_SCRIPTS/validate.py" --repo "$REPO_ROOT" --topology pxe-diskless \
  --inventory "$REPO_ROOT/deploy/ansible/inventory.yml" \
  --gpu-resolution "$GENERATED_DIR/gpu-access-resolution.json" \
  --values "$REPO_ROOT/runtime/values.yaml" \
  --values "$REPO_ROOT/runtime/values-basic-example.yaml" \
  --pxe-vars "$GENERATED_DIR/pb-pxe-controller.vars.yml"

cd "$REPO_ROOT/deploy/ansible"
sudo ansible-playbook \
  -i "$GENERATED_DIR/inventory.yml" \
  playbooks/pb-pxe-controller.yml \
  -e @"$GENERATED_DIR/pb-pxe-controller.vars.yml"

kubectl rollout status -n kube-system daemonset/amdgpu-device-plugin-daemonset --timeout=5m
kubectl rollout status -n kube-system daemonset/amdgpu-labeller-daemonset --timeout=5m
kubectl get nodes -o 'custom-columns=NAME:.metadata.name,AMD_GPU:.status.allocatable.amd\.com/gpu'

cd "$REPO_ROOT"
helm upgrade --install jupyterhub ./runtime/chart \
  --namespace jupyterhub --create-namespace \
  -f runtime/values.yaml \
  -f runtime/values-basic-example.yaml
```

A fresh PXE rootfs receives the pinned AMD udev package during the controller
playbook. A retained rootfs is accepted only when that exact package version and
its unmodified package-owned rule are present, with no conflicting legacy GPU
rule. Rebuild or correct a retained rootfs separately if that safety check fails.

#### Generator discovery failures

| Error | Action |
| --- | --- |
| Host is unreachable | Restore passwordless root SSH to that inventory host, then regenerate. |
| `lspci` is missing or fails | Install `pciutils` on the reported host and rerun generation. |
| Host evidence is `UNKNOWN` or AMD GPU BDF probes disagree | Compare AMD display BDFs from `lspci` with vendor `0x1002` display-class devices under `/sys/bus/pci/devices`; fix missing or inconsistent PCI enumeration, then regenerate. |
| Retained PXE rootfs has the wrong AMD udev package version, a modified package rule, or a conflicting legacy GPU rule | Rebuild the rootfs, or correct the package state through a separate reviewed maintenance action before rerunning the playbook. |

## Deployment branch boundary

This branch and these instructions do not modify or roll out any live
deployment. SHC, FET, and other deployment branches or environments must
backport the host permission and immediate artifact publication changes before
their own reviewed rollout.
