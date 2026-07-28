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


# Ansible Playbooks

K3s cluster setup playbooks based on [k3s-ansible](https://github.com/k3s-io/k3s-ansible).

For the generator, canonical inventory, validator arguments, and topology-specific
playbook commands, see the authoritative [deployment guide](../README.md).

Don't write GPU policy into the inventory by hand. SSH generation discovers GPU
hosts from managed-host evidence. PXE generation uses only
`pxe.diskless_agents_have_amd_gpus` and writes canonical files before the
controller playbook runs.

The GPU access role installs AMD's `amdgpu-insecure-instinct-udev-rules`
package, pinned to `30.30.4.0-2341068.24.04`, on GPU hosts and GPU-enabled PXE
root filesystems. The package sets mode `0666` only on `/dev/kfd` and DRM
`renderD*` nodes. It does not change `card*` nodes, which retain normal system
policy, observed as `root:video 0660`.

Device-plugin allocation is a separate layer and remains the visibility
boundary for Pods requesting `amd.com/gpu`; it does not change host inode
permissions. AUPLC Hub adds no GPU supplemental group. No GPU group was needed
for the tested ROCm compute path.

## Prerequisites

- **Ansible**: 2.18.3+ (on controller node only)
- **Python**: 3.12
- **SSH**: Root login with key-based auth to all nodes
- **Hosts**: Consistent `/etc/hosts` entries across all nodes
- **GPU integration**: The infrastructure owner must deploy and maintain the AMD
  device plugin and ROCm node labeller outside AUPLC. Use the pinned manual
  installation in the [Kubernetes components guide](../k8s/README.md) when the
  cluster does not already provide them. Before Helm, run the readiness and
  capacity checks in the [deployment guide](../README.md).
