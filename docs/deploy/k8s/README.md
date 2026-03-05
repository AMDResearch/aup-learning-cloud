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


# Ryzen AI PC Cluster Kubernetes Configuration

## Prerequisites

### Install K9s (optional but recommended)
[K9s](https://github.com/derailed/k9s) provides a nice command line dashboard for cluster inspection.

```bash
wget https://github.com/derailed/k9s/releases/latest/download/k9s_linux_amd64.deb && \
sudo apt install ./k9s_linux_amd64.deb && \
rm k9s_linux_amd64.deb   
```

### Install Helm

Every release of Helm provides binary releases for a variety of OSes. These binary versions can be manually downloaded and installed.

1. Download your [desired version](https://github.com/helm/helm/releases)
2. Unpack it (`tar -zxvf helm-linux-amd64.tar.gz`)
3. Find the helm binary in the unpacked directory, and move it to its desired destination (mv linux-amd64/helm /usr/local/bin/helm)

Example:
```bash
wget https://get.helm.sh/helm-v3.17.2-linux-amd64.tar.gz -O /tmp/helm-linux-amd64.tar.gz
cd /tmp && tar -zxvf helm-linux-amd64.tar.gz
sudo mv /tmp/linux-amd64/helm /usr/local/bin/helm
rm /tmp/helm-linux-amd64.tar.gz
```

**Official documentation**: https://helm.sh/docs/intro/install/

Copy kube config to current user

```bash
mkdir -p $HOME/.kube
sudo cp -i /etc/rancher/k3s/k3s.yaml $HOME/.kube/config
sudo chown $(id -u):$(id -g) $HOME/.kube/config
```

and then export KUBECONFIG in your `.bashrc`

```bash
echo "export KUBECONFIG=$HOME/.kube/config" >> $HOME/.bashrc
source $HOME/.bashrc
```

## Deploy AMD GPU k8s Device Plugin

To schedule GPU pods, we need to deploy the AMD GPU k8s device plugin.

```bash
kubectl create -f https://raw.githubusercontent.com/ROCm/k8s-device-plugin/master/k8s-ds-amdgpu-dp.yaml
```

**Official documentation**: https://github.com/ROCm/k8s-device-plugin

After deployment, you can see a new resource `amd.com/gpu` in `kubectl describe node`.

```bash
kubectl describe node <node-name> | grep  amd.com/gpu:
  amd.com/gpu:        1
```


## Label Nodes According to GPU Architecture

Proper node labeling is essential for **scheduling workloads on the correct hardware**. Labels allow Kubernetes to distinguish between CPU-only nodes, discrete GPUs, and different GPU groups.

> **⚠️ Important**: Always verify the actual node names first using `kubectl get nodes` before applying labels.

The general syntax is: `kubectl label nodes <NODE_NAME> node-type=<NODE_GROUP>`

**Step 1: Get actual node names**
```bash
# List all nodes with their actual names
kubectl get nodes

# Example output:
# NAME          STATUS   ROLES                  AGE   VERSION
# phx-1         Ready    <none>                 1d    v1.32.3+k3s1
# strix-1       Ready    <none>                 1d    v1.32.3+k3s1
# strix-halo-1  Ready    control-plane,master   1d    v1.32.3+k3s1
```

**Step 2: Label nodes based on GPU/CPU architecture**

You can use the provided script `scripts/label-node.sh` or manually label nodes:

```bash
#!/bin/bash

# Label CPU nodes
kubectl label nodes phx-1 node-type=phx
kubectl label nodes phx-64g node-type=phx

# Label discrete GPU nodes
kubectl label nodes rdna4-1 node-type=dgpu

# Label Strix GPU nodes
kubectl label nodes strix-1 node-type=strix
kubectl label nodes strix-2 node-type=strix
kubectl label nodes strix-3 node-type=strix

# Label Strix Halo GPU nodes
kubectl label nodes strix-halo-1 node-type=strix-halo

# Verify labels
kubectl get nodes --show-labels | grep node-type
```

### Label Mapping

| Node Group | Example Nodes     | node-type Label | Hardware Description                   |
| ---------- | ----------------- | --------------- | -------------------------------------- |
| phx        | phx-1, phx-64g    | `phx`           | Phoenix nodes (AMD 7940HS 7640HS)      |
| dgpu       | rdna4-1           | `dgpu`          | Discrete GPUs (AMD Radeon 7900XTX, 9070XT, W9700) |
| strix      | strix-1 ~ strix-3 | `strix`         | Strix nodes (AMD AI 370 350)           |
| strix-halo | strix-halo-1      | `strix-halo`    | Strix-Halo nodes (AMD AI MAX 395)      |

> Using these labels, workloads can specify `nodeSelector` to schedule pods on nodes with the desired GPU type.



## (Experimental) NPU non-sudo support in K8s

To enable NPU non-sudo support in K3s, you need to deploy the following components:
1. For every NPU node, you should edit their `k3s-agent.service` to solve the `ulimit` issue.
2. Add this line in the service file `LimitMEMLOCK=infinity`.
3. Reload the systemctl and restart K3s service.
4. You can use NPU inside K3s dockers. Known issues include sudden hang up with `signal 15`.

## Deploy Kubernetes components

1. nfs-provisioner [nfs-provisioner/README.md](./nfs-provisioner/README.md)


Then you can deploy other applications you like.
