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

```bash
# 1. Configure Ansible inventory
cd ansible
vim inventory.yml

# 2. Run playbooks
sudo ansible-playbook playbooks/pb-base.yml
sudo ansible-playbook playbooks/pb-k3s-site.yml

# 3. Deploy JupyterHub
cd ../../runtime
cp values-multi-nodes.yaml.example values-multi-nodes.yaml
vim values-multi-nodes.yaml
helm upgrade --install jupyterhub ./chart -n jupyterhub --create-namespace -f values-multi-nodes.yaml
```
