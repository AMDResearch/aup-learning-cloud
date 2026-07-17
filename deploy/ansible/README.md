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

For full instructions, see [Multi-Node Cluster Deployment](https://amdresearch.github.io/aup-learning-cloud/installation/multi-node.html).

## Quick Reference

```bash
# Configure inventory
vim inventory.yml

# Base setup
sudo ansible-playbook playbooks/pb-base.yml

# Deploy K3s cluster
sudo ansible-playbook playbooks/pb-k3s-site.yml

# Install ROCm GPU drivers
sudo ansible-playbook playbooks/pb-rocm.yml

# Add new nodes (update inventory.yml first)
sudo ansible-playbook playbooks/pb-k3s-site.yml

# Reset cluster
sudo ansible-playbook playbooks/pb-k3s-reset.yml

# Reset single node
sudo ansible-playbook playbooks/pb-k3s-reset.yml --limit <node_name>
```

## Prerequisites

- **Ansible**: 2.18.3+ (on controller node only)
- **Python**: 3.12
- **SSH**: Root login with key-based auth to all nodes
- **Hosts**: Consistent `/etc/hosts` entries across all nodes
