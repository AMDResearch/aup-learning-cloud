# Build A Multi-Node K3s Cluster

This guide builds and prepares a multi-node K3s cluster with the repository's Ansible playbooks. It stops at a readiness handoff. The canonical Kubernetes guide owns AUP Learning Cloud values, Helm installation, validation, access, and routine release operations.

Unlike the single-node path, this workflow isn't driven by `./auplc-installer install`. It prepares SSH access and inventory, builds K3s, establishes operator access, and makes cluster-specific storage and image choices.

## Overview

Use this path when you have machines with an operating system and SSH access and want Ansible to provision a new K3s cluster. A small cluster commonly has these roles:

- **server node**: runs the K3s control plane
- **agent nodes**: run Hub services and user notebook workloads
- **storage node**: optional, when the site chooses a separate NFS backend

Shared NFS is one storage example in this guide, not a K3s or AUP requirement. You can use another StorageClass that meets the site's access, topology, persistence, backup, and recovery needs.

## Prerequisites

### Controller / Ansible Host

- Ansible available
- SSH key access to all nodes
- ability to connect as `root` or the configured `ansible_user`
- a checkout of the AUP Learning Cloud repository

### Cluster Nodes

- Ubuntu 24.04
- consistent hostname resolution across the fleet
- AMD GPU-capable nodes for accelerator-backed resources

Current inventory defaults are defined in `deploy/ansible/inventory.yml`, including the pinned `k3s_version`.

The repository-relative commands in this guide use `/path/to/aup-learning-cloud` as the deployment repository root. Replace that placeholder with the absolute path to your checkout. Each block that needs repository files establishes its own working directory, so you can run the guide sequentially without carrying a prior block's directory forward.

## 1. Prepare SSH Access And Hostnames

The Ansible flow assumes passwordless SSH to all nodes. In practice, the two most common issues are:

- the controller can't reach every node by hostname
- the server node can't reach agents with the names used in `inventory.yml`

If needed, use the helper scripts in `deploy/scripts/`:

```bash
cd /path/to/aup-learning-cloud
./deploy/scripts/edit_sshd.sh
./deploy/scripts/setup_ssh_root_access.sh
./deploy/scripts/deploy-kubeconfig.sh
```

These scripts help enable root SSH login, copy SSH access to cluster nodes, and distribute kubeconfig where needed. Make sure `/etc/hosts` entries are consistent across the nodes when you use hostnames instead of direct IP addresses.

## 2. Configure The Ansible Inventory

Edit the inventory:

```bash
cd /path/to/aup-learning-cloud/deploy/ansible
nano inventory.yml
```

Set the server and agent hostnames, `ansible_user`, cluster token, and `api_endpoint`. A minimal structure is:

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

This is the normal inventory for machines that already have an operating system and SSH access. The diskless PXE topology uses a different inventory boundary, documented in the [3 Node Mini-Cluster Example](multi-node/multi-aipc-hardware-deployment.md).

## 3. Build The Cluster

Run the provisioning playbooks from the Ansible directory:

```bash
cd /path/to/aup-learning-cloud/deploy/ansible

# Base OS and package preparation
sudo ansible-playbook playbooks/pb-base.yml

# Deploy the K3s cluster
sudo ansible-playbook playbooks/pb-k3s-site.yml

# Install host ROCm support on accelerator nodes
sudo ansible-playbook playbooks/pb-rocm.yml
```

After editing `inventory.yml`, run `pb-k3s-site.yml` again to add or reconcile nodes. Use the upgrade playbook for a planned K3s upgrade:

```bash
cd /path/to/aup-learning-cloud/deploy/ansible
sudo ansible-playbook playbooks/pb-k3s-site.yml
sudo ansible-playbook playbooks/pb-k3s-upgrade.yml
```

`pb-rocm.yml` installs host support. It doesn't, by itself, choose or satisfy Kubernetes device-plugin ownership. The cluster must still use exactly one GPU management path and meet the label, allocatable-resource, and host-permission contract in the canonical [Kubernetes deployment guide](existing-kubernetes.md). Don't install both the GPU Operator and the standalone device plugin and node labeller.

## 4. Prepare The Operator Machine

The operator machine needs the K3s kubeconfig, a working `kubectl`, and Helm 3. The `deploy-kubeconfig.sh` helper can distribute the kubeconfig. Before handoff, make sure the kubeconfig's server address is reachable from this machine and that its context identifies the intended cluster.

Example Helm installation:

```bash
wget https://get.helm.sh/helm-v3.17.2-linux-amd64.tar.gz -O /tmp/helm-linux-amd64.tar.gz
cd /tmp && tar -zxvf helm-linux-amd64.tar.gz
sudo mv /tmp/linux-amd64/helm /usr/local/bin/helm
rm /tmp/helm-linux-amd64.tar.gz
```

K9s is optional inspection tooling:

```bash
wget https://github.com/derailed/k9s/releases/latest/download/k9s_linux_amd64.deb
sudo apt install ./k9s_linux_amd64.deb
rm k9s_linux_amd64.deb
```

Use the {ref}`canonical preflight checks <existing-kubernetes-preflight>` to verify API access, the current context, node readiness, permissions, Helm, and StorageClasses. That section also owns the full GPU management and admission-policy contract for the AUP deployment.

## 5. Select Storage

Choose a StorageClass for the cluster's persistence and topology needs. A named CSI StorageClass with suitable volume mobility can be enough. Network storage is another choice when the site needs shared access across nodes.

The repository's multi-node values example uses `nfs-client`, so the following steps show one optional NFS backend. Skip them when the site has selected another StorageClass.

### Optional: Configure An NFS Server

Run these commands only on the host selected to serve NFS. Before changing it, confirm `/nfs` isn't an existing data directory, review the subnet boundary, and back up `/etc/exports`. The recursive ownership and mode changes affect every existing item below `/nfs`. The `no_root_squash` export option grants remote root broad access, so use it only when the site's security policy explicitly approves that risk.

```bash
sudo apt install nfs-kernel-server
sudo mkdir -p /nfs
sudo chown -R nobody:nogroup /nfs
sudo chmod 777 /nfs
```

After checking that an equivalent export doesn't already exist, add the export for the intended cluster subnet and reload the NFS service:

```bash
echo "/nfs <Your-Subnet/24>(rw,sync,no_subtree_check,no_root_squash,insecure)" | sudo tee -a /etc/exports
sudo systemctl restart nfs-kernel-server
```

Install the NFS client only on cluster nodes that will mount this backend:

```bash
sudo apt install nfs-common
```

### Optional: Deploy The NFS Provisioner

Confirm that `deploy/k8s/nfs-provisioner/values.yaml` points to the intended NFS server and export before installing the provisioner:

```bash
cd /path/to/aup-learning-cloud
helm repo add nfs-subdir-external-provisioner https://kubernetes-sigs.github.io/nfs-subdir-external-provisioner/
helm repo update

helm install nfs-subdir-external-provisioner nfs-subdir-external-provisioner/nfs-subdir-external-provisioner \
  --namespace nfs-provisioner \
  --create-namespace \
  -f deploy/k8s/nfs-provisioner/values.yaml
```

Making a StorageClass the default changes how future PVCs without an explicit class are provisioned cluster-wide. Check the current defaults and pending workloads first. If that site-wide change is intended, apply it to `nfs-client`:

```bash
kubectl get storageclass
kubectl patch storageclass nfs-client -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'
```

## 6. Prepare Image Access

The cluster can pull AUP images from a registry, or you can import images directly into K3s nodes. Pick the path that every node scheduled for the corresponding workload can use.

### Option A: Use A Registry

```bash
cd /path/to/aup-learning-cloud
sudo ./auplc-installer img build

docker push ghcr.io/amdresearch/auplc-hub:latest
docker push ghcr.io/amdresearch/auplc-default:latest
docker push ghcr.io/amdresearch/auplc-cv:latest
```

The site values must point `custom.resources.images` and, when used, `prePuller.extraImages` to accessible images. Private registries also need the appropriate pull credentials.

### Option B: Import Images Directly Into K3s Nodes

```bash
cd /path/to/aup-learning-cloud/deploy/ansible
docker save ghcr.io/amdresearch/auplc-dl:latest -o /tmp/auplc-dl.tar

ansible agent -m copy -a "src=/tmp/auplc-dl.tar dest=/tmp/"
ansible agent -m shell -a "k3s ctr images import /tmp/auplc-dl.tar"
```

Repeat the import for each required image and every K3s node that may run it. A successful import on one node doesn't make that image available on the others.

## 7. Create The Topology-Specific Values File

`runtime/values-multi-nodes.yaml.example` is a standalone multi-node example, not a small override. Keep the generated site filename `runtime/values-multi-nodes.yaml`. From the repository root, create it only when it doesn't already exist:

```bash
cd /path/to/aup-learning-cloud
test ! -e runtime/values-multi-nodes.yaml
cp --no-clobber runtime/values-multi-nodes.yaml.example runtime/values-multi-nodes.yaml
chmod 600 runtime/values-multi-nodes.yaml
```

If the file exists, stop and review it instead of overwriting it. Maps are merged by Helm, but arrays are replaced. For example, changing `custom.teams.mapping.gpu` replaces that whole list.

The canonical Kubernetes guide owns the complete values review, GPU selector and image alignment, storage fields, exposure gate, manifest inspection, and Helm install. Keep using `runtime/values-multi-nodes.yaml` when following that workflow rather than changing to its example filename.

## High Availability Scope

This guide builds a basic multi-node cluster with one K3s server in the example inventory. Multiple agents don't make the control plane highly available. A highly available K3s server topology, external database, multiple Hub replicas, dedicated load balancers, production TLS, and certificate rotation are separate operator designs.

(multi-node-k3s-ready)=

## K3s Readiness Handoff

Don't start the AUP Helm workflow until every applicable gate below passes:

- [ ] **Kubernetes API:** the operator kubeconfig reaches the intended K3s API and the current context names that cluster.
- [ ] **Ready nodes:** every server and agent intended for AUP reports `Ready`.
- [ ] **GPU ownership:** exactly one Kubernetes GPU management path owns the device plugin and node labeller. `pb-rocm.yml` host support isn't counted as that path.
- [ ] **GPU discovery:** intended GPU nodes expose the expected `amd.com/gpu.product-name` labels and a non-zero allocatable `amd.com/gpu` resource.
- [ ] **StorageClass:** the selected StorageClass exists and matches the site's access mode, topology, persistence, backup, and recovery needs. NFS is optional.
- [ ] **Image access:** each schedulable node can pull or has directly imported every image it may run, with private-registry credentials available where needed.
- [ ] **Operator tools:** the operator machine has the K3s kubeconfig, working `kubectl`, and Helm 3.
- [ ] **Site values:** `runtime/values-multi-nodes.yaml` exists as a reviewed site file and wasn't created by overwriting prior configuration.

When all eight gates pass, continue at the {ref}`canonical Kubernetes preflight <existing-kubernetes-preflight>`. Follow the canonical values, render, install, and infrastructure-validation steps, substituting `runtime/values-multi-nodes.yaml` as the explicit site values file. Finish with {ref}`canonical end-to-end acceptance <existing-kubernetes-end-to-end-acceptance>`. If a user spawn fails at admission or during metadata blocking, use {ref}`canonical metadata troubleshooting <existing-kubernetes-metadata-troubleshooting>`.

## K3s Provisioning Troubleshooting

### kubectl Permission Denied On k3s.yaml

If the operator sees this error:

```text
error: error loading config file "/etc/rancher/k3s/k3s.yaml": open /etc/rancher/k3s/k3s.yaml: permission denied
```

Set the kubeconfig mode through the inventory before deployment:

```yaml
k3s_cluster:
  vars:
    extra_server_args: "--write-kubeconfig-mode=644"
```

Or copy the config on the K3s server for the current operator account:

```bash
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $(id -u):$(id -g) ~/.kube/config
```

When using that copy from another machine, make sure its server address is reachable and identifies the intended K3s server.

### Agent Node Does Not Join The Cluster

On the affected agent only, inspect the service and its route to the server:

```bash
ssh <agent-node>
sudo systemctl status k3s-agent.service
journalctl -u k3s-agent -n 100
ping <server-hostname>
```

The usual causes are hostname resolution, token, or API endpoint mismatches in `inventory.yml`.

### Optional NFS Backend Fails

Use this section only when the site selected the optional NFS provisioner. Check the provisioner against the intended server and export before changing either one:

```bash
kubectl get pods -n nfs-provisioner
kubectl logs -n nfs-provisioner deployment/nfs-subdir-external-provisioner
```

For AUP PVC failures after the cluster handoff, use the PVC troubleshooting section in the canonical [Kubernetes deployment guide](existing-kubernetes.md). GPU labels, allocatable resources, scheduling, and user Pod GPU access are also owned by that guide and its {ref}`end-to-end acceptance <existing-kubernetes-end-to-end-acceptance>`.

### Reset The Cluster Or One Node

:::{danger}
The reset playbook removes K3s state and interrupts workloads on its target. A full reset targets every host in the active Ansible inventory and can make the cluster unavailable. A limited reset removes one node's K3s state and any node-local workload data. Neither operation is a routine repair, and neither backs up AUP data, PVC contents, K3s state, or site configuration.

Before running either command, verify the repository and inventory path, print and review the resolved target hosts, stop or evacuate affected workloads, and confirm tested backups for every persistent or node-local data set. Record a maintenance window and recovery plan. Don't continue if the target list, backup state, or storage impact is uncertain.
:::

To reset the entire cluster, run this only after the full-inventory preflight above:

```bash
cd /path/to/aup-learning-cloud/deploy/ansible
sudo ansible-playbook playbooks/pb-k3s-reset.yml
```

To reset one node, first confirm that `<node_name>` resolves to exactly the intended inventory host and that its workloads and local data have been handled. Then limit the destructive playbook to that host:

```bash
cd /path/to/aup-learning-cloud/deploy/ansible
sudo ansible-playbook playbooks/pb-k3s-reset.yml --limit <node_name>
```

## Notes On Scope

- This page owns normal Ansible and K3s provisioning for machines with an operating system and SSH access.
- The diskless PXE flow remains a specialized reference with different controller, inventory, and boot boundaries.
- The canonical Kubernetes guide owns AUP configuration, Helm operations, validation, access, GPU and PVC troubleshooting, and user-facing acceptance.
- For the simplest local installation, use the single-node installer instead.
