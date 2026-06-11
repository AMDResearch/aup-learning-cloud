# Multi-Node Cluster Deployment

This guide covers the current Ansible + Helm workflow for deploying AUP Learning Cloud on a multi-node K3s cluster.

Unlike the single-node path, multi-node deployment is not driven by `./auplc-installer install`. The main flow is:

1. prepare SSH and inventory
2. build the cluster with Ansible
3. deploy the ROCm device plugin and node labeller
4. prepare storage and images
5. customize the multi-node values file
6. deploy the chart with Helm

## Overview

Multi-node deployment is the right path when you need:

- multiple worker nodes for user workloads
- shared storage across the cluster
- explicit control over ingress, authentication, and network exposure
- a layout that is closer to a long-running lab or production environment

Typical roles in a small cluster:

- **server node**: runs the K3s control plane
- **agent nodes**: run Hub services and user notebook workloads
- **storage node**: optional, if you host NFS separately

## Prerequisites

### Controller / Ansible Host

- Ansible available
- SSH key access to all nodes
- ability to connect as `root` or the configured `ansible_user`
- a checkout of this repository

### Cluster Nodes

- Ubuntu 24.04
- consistent hostname resolution across the fleet
- AMD GPU-capable nodes if you want accelerator-backed resources

Current inventory defaults are defined in `deploy/ansible/inventory.yml`, including the pinned `k3s_version`.

## 1. Prepare SSH Access

The Ansible flow assumes passwordless SSH to all nodes. In practice, the two most common issues are:

- the control node cannot reach every node by hostname
- the server node cannot SSH to agents with the same names used in `inventory.yml`

If needed, use the helper scripts in `deploy/scripts/`:

```bash
./deploy/scripts/edit_sshd.sh
./deploy/scripts/setup_ssh_root_access.sh
./deploy/scripts/deploy-kubeconfig.sh
```

These scripts help enable root SSH login, copy SSH access to cluster nodes, and distribute kubeconfig where needed.

You should also make sure `/etc/hosts` entries are consistent across the nodes when you rely on hostnames instead of direct IPs.

## 2. Configure Inventory

Edit the Ansible inventory:

```bash
cd deploy/ansible
nano inventory.yml
```

Key items to set:

- server and agent hostnames
- `ansible_user`
- cluster token
- `api_endpoint`

Minimal structure:

```yaml
---
k3s_cluster:
  children:
    server:
      hosts:
        <YOUR-SERVER-HOSTNAME>:
    agent:
      hosts:
        <YOUR-AGENT-HOSTNAME-1>:
        <YOUR-AGENT-HOSTNAME-2>:

  vars:
    ansible_port: 22
    ansible_user: root
    k3s_version: v1.32.3+k3s1
    token: "changeme!"
    api_endpoint: "{{ hostvars[groups['server'][0]]['ansible_host'] | default(groups['server'][0]) }}"
```

## 3. Build The Cluster

```bash
cd deploy/ansible

# Base OS / package preparation
sudo ansible-playbook playbooks/pb-base.yml

# Deploy K3s cluster
sudo ansible-playbook playbooks/pb-k3s-site.yml

# Install ROCm on accelerator nodes
sudo ansible-playbook playbooks/pb-rocm.yml
```

Useful related playbooks:

```bash
# Add or reconcile nodes after editing inventory.yml
sudo ansible-playbook playbooks/pb-k3s-site.yml

# Upgrade cluster
sudo ansible-playbook playbooks/pb-k3s-upgrade.yml

# Reset cluster
sudo ansible-playbook playbooks/pb-k3s-reset.yml

# Reset a single node
sudo ansible-playbook playbooks/pb-k3s-reset.yml --limit <node_name>
```

## 4. Install kubectl / Helm On The Operator Machine

You need a working `kubectl` and `helm` on the machine from which you will manage the cluster.

Example Helm install:

```bash
wget https://get.helm.sh/helm-v3.17.2-linux-amd64.tar.gz -O /tmp/helm-linux-amd64.tar.gz
cd /tmp && tar -zxvf helm-linux-amd64.tar.gz
sudo mv /tmp/linux-amd64/helm /usr/local/bin/helm
rm /tmp/helm-linux-amd64.tar.gz
```

Optional but useful for inspection:

```bash
wget https://github.com/derailed/k9s/releases/latest/download/k9s_linux_amd64.deb
sudo apt install ./k9s_linux_amd64.deb
rm k9s_linux_amd64.deb
```

## 5. GPU Device Plugin And Labels

For manual cluster setup, deploy the ROCm device plugin and node labeller:

```bash
kubectl create -f https://raw.githubusercontent.com/ROCm/k8s-device-plugin/master/k8s-ds-amdgpu-dp.yaml
kubectl create -f https://raw.githubusercontent.com/ROCm/k8s-device-plugin/master/k8s-ds-amdgpu-labeller.yaml
```

Verify labels:

```bash
kubectl describe node <node-name> | grep amd.com/gpu
```

### About Accelerator Selectors

The sample file `runtime/values-multi-nodes.yaml.example` now follows `runtime/values.yaml` and uses ROCm labeller keys such as `amd.com/gpu.product-name` directly.

That means multi-node deployments should rely on the device plugin plus labeller output, not on a separate manual `node-type` labelling convention.

Current examples in the values file include selectors like:

- `AMD_Radeon_780M_Graphics`
- `AMD_Radeon_890M_Graphics`
- `AMD_Radeon_8060S_Graphics`
- `AMD_Radeon_RX_9070_XT`
- `AMD_Radeon_AI_PRO_R9700`

If your labeller normalizes a specific product name differently on your fleet, update the corresponding `custom.accelerators.<key>.nodeSelector` entry.

## 6. Storage

Multi-node deployments usually need a shared storage class. The example values file assumes `nfs-client`.

### Configure An NFS Server

On the controller node or a dedicated storage node:

```bash
sudo apt install nfs-kernel-server
sudo mkdir -p /nfs
sudo chown -R nobody:nogroup /nfs
sudo chmod 777 /nfs
```

Add an export for your subnet:

```bash
echo "/nfs <Your-Subnet/24>(rw,sync,no_subtree_check,no_root_squash,insecure)" | sudo tee -a /etc/exports
sudo systemctl restart nfs-kernel-server
```

Install the NFS client on worker nodes if it is not already present:

```bash
sudo apt install nfs-common
```

### Deploy The NFS Provisioner

```bash
helm repo add nfs-subdir-external-provisioner https://kubernetes-sigs.github.io/nfs-subdir-external-provisioner/
helm repo update

helm install nfs-subdir-external-provisioner nfs-subdir-external-provisioner/nfs-subdir-external-provisioner \
  --namespace nfs-provisioner \
  --create-namespace \
  -f deploy/k8s/nfs-provisioner/values.yaml
```

Optionally make it the default storage class:

```bash
kubectl patch storageclass nfs-client -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'
kubectl get storageclass
```

## 7. Prepare Images

You can either push images to a registry or import them directly into cluster nodes.

### Option A: Use A Registry

```bash
cd /path/to/aup-learning-cloud
sudo ./auplc-installer img build

docker push ghcr.io/amdresearch/auplc-hub:latest
docker push ghcr.io/amdresearch/auplc-default:latest
docker push ghcr.io/amdresearch/auplc-cv:latest
```

Then update `custom.resources.images` and, if needed, `prePuller.extraImages` to match your registry.

### Option B: Import Images Directly To Nodes

```bash
docker save ghcr.io/amdresearch/auplc-dl:latest -o auplc-dl.tar

ansible agent -m copy -a "src=auplc-dl.tar dest=/tmp/"
ansible agent -m shell -a "k3s ctr images import /tmp/auplc-dl.tar"
```

## 8. Prepare The Multi-Node Values File

The repository includes a standalone example file for multi-node deployments:

```bash
cd runtime
cp values-multi-nodes.yaml.example values-multi-nodes.yaml
nano values-multi-nodes.yaml
```

Review at least these sections:

- `custom.authMode`
- `custom.githubOrgName`
- `custom.adminUser`
- `custom.accelerators`
- `custom.resources.images`
- `custom.resources.requirements`
- `custom.resources.metadata`
- `custom.teams.mapping`
- `custom.quota`
- `hub.config.GitHubOAuthenticator`
- `hub.db.pvc.storageClassName`
- `singleuser.storage.dynamic.storageClass`
- `proxy.service`
- `ingress`

### What The Example Already Assumes

The current example is not just a tiny patch file. It already includes:

- accelerator definitions aligned with `runtime/values.yaml`
- course image placeholders using the current image set
- team-to-resource mappings
- quota configuration knobs
- Git clone settings
- storage, ingress, and Hub sections for a real deployment

## 9. Deploy JupyterHub

```bash
cd runtime
helm upgrade --install jupyterhub ./chart \
  -n jupyterhub --create-namespace \
  -f values-multi-nodes.yaml
```

## 10. Verify Deployment

```bash
kubectl get nodes
kubectl get pods -n jupyterhub
kubectl get pvc -n jupyterhub
kubectl get ingress -n jupyterhub
kubectl get storageclass
```

If you copied kubeconfig from the server node, verify the current context too:

```bash
kubectl config current-context
```

## Access JupyterHub

If you use ingress:

```bash
kubectl get ingress -n jupyterhub
```

Then access the configured hostname, for example:

```text
https://your-domain.com
```

If you expose the proxy with `NodePort`, use the node IP and configured port instead.

## Operational Notes

### Apply Later Configuration Changes

Most routine changes after initial deployment are another Helm upgrade with the same values file:

```bash
cd runtime
helm upgrade --install jupyterhub ./chart \
  -n jupyterhub \
  -f values-multi-nodes.yaml
```

### High Availability Scope

This guide covers the base multi-node chart deployment. Choices such as:

- external database backends
- multiple Hub replicas
- dedicated load balancers
- production TLS and certificate rotation

should be treated as explicit operator decisions layered on top of this base flow.

## Troubleshooting

### kubectl Permission Denied On k3s.yaml

If you hit an error like:

```text
error: error loading config file "/etc/rancher/k3s/k3s.yaml": open /etc/rancher/k3s/k3s.yaml: permission denied
```

Set write permissions through the inventory before deployment:

```yaml
k3s_cluster:
  vars:
    extra_server_args: "--write-kubeconfig-mode=644"
```

Or copy the config manually:

```bash
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $(id -u):$(id -g) ~/.kube/config
```

### Agent Node Does Not Join The Cluster

```bash
ssh <agent-node>
sudo systemctl status k3s-agent.service
journalctl -u k3s-agent -n 100
ping <server-hostname>
```

Most often this is a hostname resolution, token, or API endpoint mismatch in `inventory.yml`.

### GPU Labels Or Resources Missing

Check the daemonsets first:

```bash
kubectl get ds -A | grep amdgpu
kubectl describe node <node-name> | grep amd.com/gpu
```

If the labels do not match your `custom.accelerators.<key>.nodeSelector`, the resource will not schedule onto that node.

### Storage Provisioning Fails

```bash
kubectl get pods -n nfs-provisioner
kubectl get pvc -n jupyterhub
kubectl logs -n nfs-provisioner deployment/nfs-subdir-external-provisioner
```

### Resetting The Cluster

To remove the cluster completely:

```bash
cd deploy/ansible
sudo ansible-playbook playbooks/pb-k3s-reset.yml
```

To reset a single node only:

```bash
sudo ansible-playbook playbooks/pb-k3s-reset.yml --limit <node_name>
```

## Notes On Scope

- The sample multi-node values file is a starting point, not a promise that every advanced topology is turnkey.
- The most important cluster-specific alignment is between real node labels and `custom.accelerators.*.nodeSelector`.
- If you want the simplest local install, use the single-node installer flow instead of this guide.
