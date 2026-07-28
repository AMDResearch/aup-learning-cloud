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

Generate the spec, fill in the normal network and node details, then let the
generator discover GPU hosts and their shared `render` GID. The SSH flow asks
for no GPU host list and no GID. A PXE spec asks one extra GPU question:
`pxe.diskless_agents_have_amd_gpus`. Set it explicitly because the diskless
agents' hardware is not inferred from the controller.

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

cd "$REPO_ROOT"
helm upgrade --install jupyterhub ./runtime/chart \
  --namespace jupyterhub --create-namespace \
  -f runtime/values.yaml \
  -f runtime/values-basic-example.yaml
```

Generation runs read-only Ansible discovery against every managed host. It
cross-checks AMD display BDFs from `lspci` with PCI vendor and display-class
records under `/sys/bus/pci/devices`; it does not require the devices to be
attached to `amdgpu` before ROCm installation. It checks
the `render` group and existing GPU access files, and publishes only when every
GPU host agrees on one GID. CPU-only fleets publish `null` for the generated
inventory and Helm render GID. GPU policy details in generated files are
internal outputs, not fields to maintain by hand.

Configure notebook storage ownership with `singleuser.fsGid: 100`. Never set
storage `fsGroup` through `extraPodConfig.securityContext`, because that Pod
security-context override can replace the GPU resource's generated
`supplementalGroups`.

#### PXE-diskless

After setting `topology` to `pxe-diskless`, fill the PXE network fields and set
only `pxe.diskless_agents_have_amd_gpus` for GPU policy. When it is `true`, the
first generation is pending and creates private bootstrap files instead of
canonical deployment files.

```bash
cd "$REPO_ROOT"
python3 "$DEPLOY_SCRIPTS/gen_configs.py" --spec spec.json --out-dir "$GENERATED_DIR"
cd "$REPO_ROOT/deploy/ansible"
sudo ansible-playbook \
  -i "$GENERATED_DIR/.pxe-bootstrap.inventory.yml" \
  playbooks/pb-pxe-controller.yml \
  -e @"$GENERATED_DIR/.pxe-bootstrap.vars.yml"

# pb-pxe-controller finalizes automatically after a successful rootfs build.
install -m 0600 "$GENERATED_DIR/inventory.yml" "$REPO_ROOT/deploy/ansible/inventory.yml"
install -m 0644 "$GENERATED_DIR/values-basic-example.yaml" "$REPO_ROOT/runtime/values-basic-example.yaml"
python3 "$DEPLOY_SCRIPTS/validate.py" --repo "$REPO_ROOT" --topology pxe-diskless \
  --inventory "$REPO_ROOT/deploy/ansible/inventory.yml" \
  --gpu-resolution "$GENERATED_DIR/gpu-access-resolution.json" \
  --values "$REPO_ROOT/runtime/values.yaml" \
  --values "$REPO_ROOT/runtime/values-basic-example.yaml" \
  --pxe-vars "$GENERATED_DIR/pb-pxe-controller.vars.yml"
```

Don't invoke the hidden finalizer yourself. The playbook writes a private
handoff and runs finalization locally. `inventory.yml`,
`pb-pxe-controller.vars.yml`, `values-basic-example.yaml`, and
`gpu-access-resolution.json` appear only after success.

A fresh PXE rootfs can create a missing `render` group and align it with a
unanimous live controller GPU GID after collision checks. A retained rootfs is
never silently changed. It must already contain one valid `render` group and,
when the controller has a resolved GPU GID, the rootfs GID must match. Rebuild
the rootfs or migrate the retained rootfs separately if it doesn't match.
Offline checks don't replace post-boot verification of GPU device ownership,
mode, supplemental groups, and workload access.

#### Discovery failures and migration

| Error | Action |
| --- | --- |
| Host is unreachable | Restore passwordless root SSH to that inventory host, then regenerate. |
| `lspci` is missing or fails | Install `pciutils` on the reported host and rerun generation. |
| Host evidence is `UNKNOWN` or AMD GPU BDF probes disagree | Compare AMD display BDFs from `lspci` with vendor `0x1002` display-class devices under `/sys/bus/pci/devices`; fix missing or inconsistent PCI enumeration, then regenerate. |
| GPU host has no valid `render` group | Install the correct GPU userspace or create one valid system `render` group, then regenerate. |
| GPU render GIDs disagree | Plan and perform a reviewed group migration so every GPU host uses one free GID, then regenerate. |
| CPU host retains GPU access contract, or canonical state/rule conflicts | Inspect `/var/lib/auplc/gpu-access.json` and `/etc/udev/rules.d/70-auplc-gpu-access.rules`. Remove stale project-owned files from a truly CPU-only host, or complete the GPU migration. Never overwrite unknown content. |
| Retained PXE rootfs GID differs from the unanimous live GID | Rebuild the rootfs, or migrate that retained rootfs separately before rerunning the playbook. |

Old unshipped specs aren't compatible. Remove the former manual GPU policy
fields, regenerate the schema, copy the ordinary node and PXE network values
into it, and set only `pxe.diskless_agents_have_amd_gpus` on PXE deployments.

## Deployment branch boundary

This branch and these instructions do not modify or roll out any live
deployment. SHC, FET, and other deployment branches or environments must
backport the automatic discovery and generated-artifact changes before their
own reviewed rollout.
