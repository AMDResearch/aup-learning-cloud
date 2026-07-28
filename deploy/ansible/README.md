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

The GPU access role sets AMD device-node policy on GPU hosts and GPU-enabled PXE
root filesystems. `/dev/kfd` and AMD `renderD*` nodes are `root:render 0666`;
AMD `card*` nodes are `root:video 0666`. All injected GPU device nodes therefore
use mode `0666`. Device-plugin allocation is the visibility boundary: only Pods
requesting `amd.com/gpu` receive the nodes. The plugin does not change host inode
permissions, and AUPLC Hub adds no GPU supplemental group to user Pods. Ordinary
container group membership does not participate in GPU permissions; host
provisioning owns device-node discretionary access control.

## Prerequisites

- **Ansible**: 2.18.3+ (on controller node only)
- **Python**: 3.12
- **SSH**: Root login with key-based auth to all nodes
- **Hosts**: Consistent `/etc/hosts` entries across all nodes
- **GPU integration**: The infrastructure owner must deploy and maintain the AMD
  device plugin and ROCm node labeller outside AUPLC. Before Helm, run the
  readiness and capacity checks in the [deployment guide](../README.md).
