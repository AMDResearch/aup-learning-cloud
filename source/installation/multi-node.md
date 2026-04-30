# Multi-Node Cluster Deployment

This guide covers the current Ansible + Helm workflow for deploying AUP Learning Cloud on a multi-node K3s cluster.

Unlike the single-node path, multi-node deployment is not driven by `./auplc-installer install`. The main flow is:

1. build the cluster with Ansible
2. prepare the multi-node values file
3. deploy the chart with Helm

## Prerequisites

### Controller / Ansible Host

- Ansible available
- SSH key access to all nodes
- ability to connect as `root` or the configured `ansible_user`

### Cluster Nodes

- Ubuntu 24.04
- consistent hostname resolution across the fleet
- AMD GPU-capable nodes if you want accelerator-backed resources

Current inventory defaults are defined in `deploy/ansible/inventory.yml`, including the pinned `k3s_version`.

## 1. Configure Inventory

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

## 2. Build The Cluster

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
# Upgrade cluster
sudo ansible-playbook playbooks/pb-k3s-upgrade.yml

# Reset cluster
sudo ansible-playbook playbooks/pb-k3s-reset.yml
```

## 3. GPU Device Plugin And Labels

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

## 4. Storage

Multi-node deployments usually need a shared storage class. The example values file assumes `nfs-client`.

If you use the included NFS provisioner example:

```bash
helm repo add nfs-subdir-external-provisioner https://kubernetes-sigs.github.io/nfs-subdir-external-provisioner/
helm repo update

helm install nfs-subdir-external-provisioner nfs-subdir-external-provisioner/nfs-subdir-external-provisioner \
  --namespace nfs-provisioner \
  --create-namespace \
  -f deploy/k8s/nfs-provisioner/values.yaml
```

## 5. Prepare The Multi-Node Values File

The repository includes a standalone example file for multi-node deployments:

```bash
cd runtime
cp values-multi-nodes.yaml.example values-multi-nodes.yaml
nano values-multi-nodes.yaml
```

Review at least these sections:

- `custom.authMode`
- `custom.githubOrgName`
- `custom.accelerators`
- `custom.resources.images`
- `custom.resources.requirements`
- `custom.teams.mapping`
- `hub.config.GitHubOAuthenticator`
- `hub.db.pvc.storageClassName`
- `singleuser.storage.dynamic.storageClass`
- `proxy.service`
- `ingress`

## 6. Deploy JupyterHub

```bash
cd runtime
helm upgrade --install jupyterhub ./chart \
  -n jupyterhub --create-namespace \
  -f values-multi-nodes.yaml
```

## 7. Verify Deployment

```bash
kubectl get nodes
kubectl get pods -n jupyterhub
kubectl get pvc -n jupyterhub
kubectl get ingress -n jupyterhub
```

## Notes On Scope

- The sample multi-node values file is a starting point, not a promise that every advanced topology is turnkey.
- High-availability choices such as external databases, multiple Hub replicas, or production ingress/TLS should be treated as explicit operator decisions on top of the base chart deployment.
- If you want the simplest local install, use the single-node installer flow instead of this guide.
