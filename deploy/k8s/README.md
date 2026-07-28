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


# Kubernetes Components

Kubernetes resource configurations for AUP Learning Cloud cluster.

For full instructions, see [Multi-Node Cluster Deployment](https://amdresearch.github.io/aup-learning-cloud/installation/multi-node.html).

## Contents

- `nfs-provisioner/` — NFS dynamic provisioner Helm values

## Quick Reference

`auplc-installer install` deploys both the AMD GPU device plugin and the ROCm
node labeller automatically. The labeller publishes labels such as
`amd.com/gpu.product-name`, `amd.com/gpu.family`, `amd.com/gpu.vram`,
`amd.com/gpu.cu-count`, `amd.com/gpu.simd-count`, and `amd.com/gpu.device-id`,
which `runtime/values.yaml` uses as `nodeSelector`s. The installer pins the
accelerator `nodeSelector` to the real `amd.com/gpu.product-name` detected on
the host, so no manual labelling is needed on single-machine deployments.

For multi-node deployments, the AMD device plugin and ROCm node labeller are
cluster infrastructure prerequisites owned outside AUPLC. The infrastructure
owner must select, deploy, and maintain them according to the
[official AMD Kubernetes device plugin project](https://github.com/ROCm/k8s-device-plugin).
AUPLC documentation does not install these privileged components.

Before deploying the AUPLC Helm release, verify the existing infrastructure:

```bash
kubectl rollout status -n kube-system daemonset/amdgpu-device-plugin-daemonset --timeout=5m
kubectl rollout status -n kube-system daemonset/amdgpu-labeller-daemonset --timeout=5m
kubectl get nodes -o 'custom-columns=NAME:.metadata.name,AMD_GPU:.status.allocatable.amd\.com/gpu'
```

`runtime/values-multi-nodes.yaml.example` now follows `runtime/values.yaml` and
uses the ROCm labeller's `amd.com/gpu.product-name` selectors directly, so no
separate legacy host-labelling script is required.
