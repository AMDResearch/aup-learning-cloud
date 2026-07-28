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

Generate the spec and fill in the network and node details. The SSH flow needs
only the managed host details. A PXE spec asks one extra GPU question:
`pxe.diskless_agents_have_amd_gpus`. Set it explicitly because the diskless
agents' hardware is not inferred from the controller.

The AMD device plugin and ROCm node labeller are cluster infrastructure
prerequisites owned outside AUPLC. The infrastructure owner must deploy and
maintain them according to AMD's official guidance. Before Helm, verify that the
existing DaemonSets are ready and that GPU capacity is advertised.

#### SSH-preinstalled

```bash
cd ..
REPO_ROOT="$(pwd)"
DEPLOY_SCRIPTS="$REPO_ROOT/skills/deploy-aup-learning-cloud/scripts"
python3 "$DEPLOY_SCRIPTS/gen_configs.py" --print-schema > spec.json
# Edit spec.json: choose ssh-preinstalled and fill the node/network fields.
GENERATED_DIR="$REPO_ROOT/generated"
python3 "$DEPLOY_SCRIPTS/gen_configs.py" --spec spec.json --out-dir "$GENERATED_DIR"
install -m 0600 "$GENERATED_DIR/inventory.yml" "$REPO_ROOT/deploy/ansible/inventory.yml"
install -m 0644 "$GENERATED_DIR/values-basic-example.yaml" "$REPO_ROOT/runtime/values-basic-example.yaml"
python3 "$DEPLOY_SCRIPTS/validate.py" --repo "$REPO_ROOT" --topology ssh-preinstalled \
  --inventory "$REPO_ROOT/deploy/ansible/inventory.yml" \
  --gpu-resolution "$GENERATED_DIR/gpu-access-resolution.json" \
  --values "$REPO_ROOT/runtime/values.yaml" \
  --values "$REPO_ROOT/runtime/values-basic-example.yaml"

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
  -f runtime/values-basic-example.yaml
```

Generation runs read-only Ansible discovery against every managed host. It
cross-checks AMD display BDFs from `lspci` with PCI vendor and display-class
records under `/sys/bus/pci/devices`; it does not require the devices to be
attached to `amdgpu` before ROCm installation. The resulting GPU resolution
report records which managed hosts have AMD display hardware.

The GPU permission contract is fixed across GPU hosts and PXE root filesystems:

- `/dev/kfd` and AMD `/dev/dri/renderD*` nodes are `root:render` with mode `0666`.
- AMD `/dev/dri/card*` nodes are `root:video` with mode `0666`.
- Every GPU device node injected into a Pod therefore has mode `0666`.
- Host provisioning owns device-node discretionary access control.
- AUPLC Hub adds no GPU supplemental group to user Pods.
- AMD device-plugin allocation is the visibility boundary: only Pods that
  request `amd.com/gpu` receive GPU device nodes. The plugin does not set Unix
  ownership or modes on host device nodes.

`singleuser.fsGid: 100` controls shared notebook storage ownership only. It is
not part of GPU access and must not be treated as a GPU group setting.

#### PXE-diskless

After setting `topology` to `pxe-diskless`, fill the PXE network fields and set
`pxe.diskless_agents_have_amd_gpus` explicitly. Generation writes the canonical
inventory, controller vars, runtime overlay, and GPU resolution report directly.
These artifacts express the desired deployment inputs; their existence is not
proof that rootfs provisioning succeeded. Review and install them before running
the controller playbook, whose successful completion provisions the rootfs.

```bash
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

A fresh PXE rootfs receives the fixed udev rule during the controller playbook.
A retained rootfs is accepted only when it already contains that exact canonical
rule and no conflicting legacy GPU rule. Rebuild or correct a retained rootfs
separately if that safety check fails.

#### Discovery failures

| Error | Action |
| --- | --- |
| Host is unreachable | Restore passwordless root SSH to that inventory host, then regenerate. |
| `lspci` is missing or fails | Install `pciutils` on the reported host and rerun generation. |
| Host evidence is `UNKNOWN` or AMD GPU BDF probes disagree | Compare AMD display BDFs from `lspci` with vendor `0x1002` display-class devices under `/sys/bus/pci/devices`; fix missing or inconsistent PCI enumeration, then regenerate. |
| Retained PXE rootfs has a legacy or non-canonical GPU rule | Rebuild the rootfs, or replace the conflicting rule through a separate reviewed maintenance action before rerunning the playbook. |

## Deployment branch boundary

This branch and these instructions do not modify or roll out any live
deployment. SHC, FET, and other deployment branches or environments must
backport the host permission and immediate artifact publication changes before
their own reviewed rollout.
