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

K3s cluster setup playbooks based on [k3s-ansible](https://github.com/k3s-io/k3s-ansible/tree/master).

For the generator, canonical inventory, validator arguments, and topology-specific
playbook commands, see the authoritative [deployment guide](../README.md).

Don't write GPU policy into the inventory by hand. SSH generation discovers GPU
hosts and their shared `render` group ID. PXE generation uses only
`pxe.diskless_agents_have_amd_gpus`; when enabled, the controller playbook uses
private bootstrap inputs and publishes canonical files automatically after a
successful rootfs build.

## Prerequisites

- **Ansible**: 2.18.3+ (on controller node only)
- **Python**: 3.12
- **SSH**: Root login with key-based auth to all nodes
- **Hosts**: Consistent `/etc/hosts` entries across all nodes
