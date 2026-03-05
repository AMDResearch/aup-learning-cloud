# Multi-Node Cluster Deployment

This guide provides instructions for deploying AUP Learning Cloud on a multi-node Kubernetes cluster using Ansible. This deployment is suitable for production environments requiring high availability and scalability.

## Overview

Multi-node deployment provides:
- **High Availability**: Redundancy across multiple nodes
- **Scalability**: Distribute workload across cluster
- **Resource Isolation**: Separate control plane and worker nodes
- **Production Ready**: Suitable for production environments

## Architecture

A typical multi-node setup consists of:
- **Control Plane Nodes** (1-3 nodes): Run Kubernetes control plane components
- **Worker Nodes** (2+ nodes): Run user workloads and JupyterHub services
- **Storage Node** (optional): Dedicated NFS storage server

## Prerequisites

### Hardware Requirements

**Per Node**:
- AMD Ryzen™ AI Halo Device (or compatible AMD hardware)
- 32GB+ RAM (64GB recommended for worker nodes)
- 500GB+ SSD (1TB+ for storage nodes)
- 1Gbps+ network connectivity

**Recommended Cluster**:
- 1 control plane node
- 3+ worker nodes
- 1 dedicated NFS storage node (optional)

### Software Requirements

**All Nodes**:
- Ubuntu 24.04.3 LTS
- SSH access configured
- Root/sudo privileges

**Control Node** (Ansible runner):
- Ansible 2.9 or later
- SSH key access to all nodes
- Python 3.8+

### Network Requirements

- All nodes must be on the same network or have connectivity
- Fixed IP addresses or DHCP with MAC reservation
- Firewall rules configured for Kubernetes ports

## Installation Steps

### 1. Prepare Control Node

Install Ansible on your control machine:

```bash
# Install Ansible
sudo apt update
sudo apt install ansible python3-pip

# Verify installation
ansible --version
```

### 2. Configure SSH Access

Set up passwordless SSH access to all nodes:

```bash
# Generate SSH key (if not already exists)
ssh-keygen -t rsa -b 4096

# Copy SSH key to all nodes
ssh-copy-id user@node1
ssh-copy-id user@node2
ssh-copy-id user@node3
# ... for all nodes

# Test SSH access
ssh user@node1 "hostname"
```

### 3. Clone Repository

```bash
git clone https://github.com/AMDResearch/aup-learning-cloud.git
cd aup-learning-cloud/deploy/ansible
```

### 4. Configure Inventory

Edit `deploy/ansible/inventory.yml` with your cluster node information. The `server` is the control-plane node (also the Ansible control host); `agent` entries are the worker nodes:

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
        <YOUR-AGENT-HOSTNAME-3>:

  vars:
    ansible_port: 22
    ansible_user: root
    k3s_version: v1.32.3+k3s1
    # Generate a random token:  openssl rand -base64 64
    token: "changeme!"
    api_endpoint: "{{ hostvars[groups['server'][0]]['ansible_host'] | default(groups['server'][0]) }}"
```

> **Important**: All nodes must have consistent `/etc/hosts` entries so they can resolve each other by hostname. The server node must also have root SSH key access to all agent nodes. See `deploy/scripts/setup_ssh_root_access.sh` for a helper script.

### 5. Run Base Setup

Install basic requirements on all nodes:

```bash
cd deploy/ansible

# Install base packages and configure hosts
sudo ansible-playbook playbooks/pb-base.yml

# Deploy K3s cluster
sudo ansible-playbook playbooks/pb-k3s-site.yml
```

### 6. Install GPU / NPU Drivers

Install ROCm on all GPU nodes:

```bash
sudo ansible-playbook playbooks/pb-rocm.yml
```

Verify GPU detection:

```bash
rocminfo
rocm-smi
```

**Official documentation**: https://rocm.docs.amd.com/projects/install-on-linux/en/latest/install/quick-start.html

### 7. Install Helm and K9s

```bash
# Install Helm
wget https://get.helm.sh/helm-v3.17.2-linux-amd64.tar.gz -O /tmp/helm-linux-amd64.tar.gz
cd /tmp && tar -zxvf helm-linux-amd64.tar.gz
sudo mv /tmp/linux-amd64/helm /usr/local/bin/helm
rm /tmp/helm-linux-amd64.tar.gz

# Install K9s (optional but recommended)
wget https://github.com/derailed/k9s/releases/latest/download/k9s_linux_amd64.deb
sudo apt install ./k9s_linux_amd64.deb
rm k9s_linux_amd64.deb
```

### 8. Deploy GPU Device Plugin and Label Nodes

Deploy the AMD GPU Kubernetes device plugin:

```bash
kubectl create -f https://raw.githubusercontent.com/ROCm/k8s-device-plugin/master/k8s-ds-amdgpu-dp.yaml
```

Verify GPU is detected:

```bash
kubectl describe node <node-name> | grep amd.com/gpu
```

Label each node based on GPU architecture:

```bash
# Label nodes by GPU type
kubectl label nodes <NODE_NAME> node-type=<TYPE>
```

| Node Group | node-type Label | Hardware Description |
| ---------- | --------------- | -------------------- |
| phx        | `phx`           | Phoenix (AMD 7940HS / 7640HS) |
| dgpu       | `dgpu`          | Discrete GPU (Radeon 7900XTX, 9070XT, W9700) |
| strix      | `strix`         | Strix (AMD AI 370 / 350) |
| strix-halo | `strix-halo`    | Strix-Halo (AMD AI MAX 395) |

Verify labels:

```bash
kubectl get nodes --show-labels | grep node-type
```

### 9. Configure NFS Storage

#### Set up the NFS Server

On the controller node (or a dedicated storage node):

```bash
# Install NFS server
sudo apt install nfs-kernel-server

# Create NFS share
sudo mkdir -p /nfs
sudo chown -R nobody:nogroup /nfs
sudo chmod 777 /nfs

# Configure exports
echo "/nfs <Your-Subnet/24>(rw,sync,no_subtree_check,no_root_squash,insecure)" | sudo tee -a /etc/exports

# Restart NFS server
sudo systemctl restart nfs-kernel-server
```

Install NFS client on all agent nodes (the `pb-base.yml` playbook does this automatically):

```bash
sudo apt install nfs-common
```

#### Deploy NFS Provisioner

```bash
helm repo add nfs-subdir-external-provisioner https://kubernetes-sigs.github.io/nfs-subdir-external-provisioner/
helm repo update

helm install nfs-subdir-external-provisioner nfs-subdir-external-provisioner/nfs-subdir-external-provisioner \
    --namespace nfs-provisioner \
    --create-namespace \
    -f deploy/k8s/nfs-provisioner/values.yaml
```

Set as default StorageClass:

```bash
kubectl patch storageclass nfs-client -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'
kubectl get storageclass
```

### 10. Build and Import Images

**Option A: Use a container registry** (recommended for production):

```bash
# Build images from repo root
cd /path/to/aup-learning-cloud
sudo ./auplc-installer img build

# Push to registry
docker push ghcr.io/amdresearch/auplc-hub:latest
docker push ghcr.io/amdresearch/auplc-cv:latest
# ... for all images
```

**Option B: Import images directly to nodes** (air-gapped environments):

```bash
# Save images to tar files
docker save ghcr.io/amdresearch/auplc-dl:latest -o auplc-dl.tar

# Copy and import to cluster nodes (K3s uses containerd)
ansible workers -m copy -a "src=auplc-dl.tar dest=/tmp/"
ansible workers -m shell -a "k3s ctr images import /tmp/auplc-dl.tar"
```

### 11. Configure JupyterHub

The multi-node template is a **standalone** configuration file that already includes all required settings (accelerators, courses, teams, storage, network, etc.). Copy it and customize for your environment — no need to layer it on top of `values.yaml`:

```bash
cd runtime

# Copy multi-node configuration template
cp values-multi-nodes.yaml.example values-multi-nodes.yaml
nano values-multi-nodes.yaml
```

Key settings to customize:
- **Storage class**: `nfs-client` (already set for multi-node)
- **Ingress**: Configure your domain in the `ingress` section
- **Authentication**: Fill in GitHub App credentials in `hub.config.GitHubOAuthenticator`
- **Images**: Update `custom.resources.images` with your registry/org
- **Admin**: Set `admin_users` and `githubOrgName`

See [Configuration Reference](../jupyterhub/configuration-reference.md) for all available options.

### 12. Deploy JupyterHub

```bash
cd runtime

# Deploy using the multi-node config directly
helm upgrade --install jupyterhub ./chart \
  -n jupyterhub --create-namespace \
  -f values-multi-nodes.yaml
```

### 13. Verify Deployment

```bash
# Get kubeconfig from control plane node
scp user@master1:~/.kube/config ~/.kube/config

# Check nodes
kubectl get nodes

# Check all pods
kubectl get pods -n jupyterhub

# Check storage
kubectl get pvc -n jupyterhub
kubectl get storageclass
```

## Access JupyterHub

Configure ingress for domain-based access:

```bash
# Check ingress
kubectl get ingress -n jupyterhub

# Access via domain
https://your-domain.com
```

## High Availability Configuration

For production high availability:

1. **Multiple Control Plane Nodes** (3 recommended):
   - Edit inventory to include multiple control plane nodes
   - K3s will automatically configure HA etcd

2. **Load Balancer**:
   - Use external load balancer for control plane
   - Configure in K3s server installation

3. **Multiple Hub Replicas**:
   ```yaml
   hub:
     replicas: 2
     db:
       type: postgres  # Use external database
   ```

## Monitoring and Maintenance

### Check Cluster Health

```bash
# Node status
kubectl get nodes

# Pod status across namespaces
kubectl get pods -A

# Resource usage
kubectl top nodes
kubectl top pods -n jupyterhub
```

### Upgrade Cluster

```bash
cd deploy/ansible

# Upgrade K3s
ansible-playbook playbooks/pb-k3s-upgrade.yml

# Upgrade JupyterHub (from repo root)
cd /path/to/aup-learning-cloud
bash scripts/helm_upgrade.bash
```

### Backup and Restore

Back up the hub database PVC and NFS storage (if used) before major upgrades. Backup and monitoring guides will be added in a future release.

## Troubleshooting

### kubectl permission denied error

If you encounter errors like:
```
error: error loading config file "/etc/rancher/k3s/k3s.yaml": open /etc/rancher/k3s/k3s.yaml: permission denied
```

**Solution**:
Add the following to your `inventory.yml` before running the playbook:
```yaml
k3s_cluster:
  vars:
    extra_server_args: "--write-kubeconfig-mode=644"
```

Or manually copy the config:
```bash
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $(id -u):$(id -g) ~/.kube/config
```

See [K3s Cluster Access](https://docs.k3s.io/cluster-access) for official documentation.

### Helm command not found

If `helm` command is not found, verify the installation:
```bash
# Check if helm is in PATH
which helm

# If not, ensure /usr/local/bin is in PATH
echo $PATH

# Reinstall helm if needed (see Step 2 above)
```

### Ansible halts at "Enable and check K3s service"

Check if the K3s agent service is running on the problematic node:

```bash
ssh <agent_node>
sudo systemctl status k3s-agent.service
```

If the service is running but shows connection errors to the server, verify that `/etc/hosts` on the agent node resolves the server hostname correctly.

### Node Not Joining Cluster

```bash
# Check K3s service on problem node
ssh <node> "systemctl status k3s-agent"

# Check K3s logs
ssh <node> "journalctl -u k3s-agent -n 100"

# Verify network connectivity
ssh <node> "ping <server-hostname>"
```

### Storage Issues

```bash
# Check NFS mount
kubectl exec -it <pod-name> -n jupyterhub -- df -h

# Check NFS provisioner logs
kubectl logs -n kube-system -l app=nfs-provisioner
```

### Networking Issues

```bash
# Check CNI pods
kubectl get pods -n kube-system

# Test pod-to-pod networking
kubectl run test-pod --image=busybox --rm -it -- ping <pod-ip>
```

## Scaling

### Add Worker Nodes

1. Add new hostnames to the `agent` section in `deploy/ansible/inventory.yml`
2. Run the K3s playbook:
   ```bash
   cd deploy/ansible
   sudo ansible-playbook playbooks/pb-k3s-site.yml
   ```

### Remove Worker Nodes

```bash
# Drain node
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data

# Delete from cluster
kubectl delete node <node-name>

# Uninstall K3s on the node
ssh <node-name> "/usr/local/bin/k3s-agent-uninstall.sh"
```

### Reset Cluster

To reset the entire K3s cluster (all data and config will be removed):

```bash
cd deploy/ansible
sudo ansible-playbook playbooks/pb-k3s-reset.yml
```

To reset a single node only:

```bash
sudo ansible-playbook playbooks/pb-k3s-reset.yml --limit <node_name>
```

After resetting, remove the `~/.kube` directory.

## Next Steps

- [Configure JupyterHub](../jupyterhub/index.md)
- [Set up Authentication](../jupyterhub/authentication-guide.md)
- [Manage Users](../jupyterhub/user-management.md)
- [Configure Quotas](../jupyterhub/quota-system.md)
