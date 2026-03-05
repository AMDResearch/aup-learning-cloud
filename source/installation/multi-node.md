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

Edit `inventory.yml` with your cluster node information:

```yaml
all:
  children:
    control_plane:
      hosts:
        master1:
          ansible_host: 192.168.1.10
          ansible_user: ubuntu

    workers:
      hosts:
        worker1:
          ansible_host: 192.168.1.11
          ansible_user: ubuntu
        worker2:
          ansible_host: 192.168.1.12
          ansible_user: ubuntu
        worker3:
          ansible_host: 192.168.1.13
          ansible_user: ubuntu

    storage:
      hosts:
        nfs1:
          ansible_host: 192.168.1.20
          ansible_user: ubuntu
```

### 5. Run Base Setup

Install basic requirements on all nodes:

```bash
# Update all nodes
ansible-playbook playbooks/pb-apt-upgrade.yml

# Install base packages
ansible-playbook playbooks/pb-base.yml

# Verify connectivity
ansible all -m ping
```

### 6. Install K3s Cluster

Deploy K3s across the cluster:

```bash
# Install K3s on all nodes
ansible-playbook playbooks/pb-k3s-site.yml
```

This playbook will:
- Install K3s server on control plane node
- Install K3s agents on worker nodes
- Configure networking
- Set up kubectl access

### 7. Configure NFS Storage

#### Option A: Dedicated NFS Server

If using a dedicated NFS server:

```bash
# Install and configure NFS server
ansible-playbook playbooks/pb-nfs-server.yml
```

#### Option B: NFS Provisioner in Kubernetes

Deploy NFS provisioner in the cluster:

```bash
cd ../../deploy/k8s/nfs-provisioner

# Edit values.yaml with your NFS server details
nano values.yaml

# Deploy NFS provisioner
helm install nfs-provisioner . -n kube-system
```

See `deploy/k8s/nfs-provisioner/README.md` for detailed configuration.

### 8. Build and Import Images

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

### 9. Configure JupyterHub

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

### 10. Deploy JupyterHub

```bash
cd runtime

# Deploy using the multi-node config directly
helm upgrade --install jupyterhub ./chart \
  -n jupyterhub --create-namespace \
  -f values-multi-nodes.yaml
```

### 11. Verify Deployment

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

### Node Not Joining Cluster

```bash
# Check K3s service on problem node
ansible worker1 -m shell -a "systemctl status k3s-agent"

# Check K3s logs
ansible worker1 -m shell -a "journalctl -u k3s-agent -n 100"

# Verify network connectivity
ansible worker1 -m shell -a "ping master1"
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

1. Update `inventory.yml` with new worker nodes
2. Run the K3s playbook:
   ```bash
   ansible-playbook playbooks/pb-k3s-site.yml --limit new_worker
   ```

### Remove Worker Nodes

```bash
# Drain node
kubectl drain worker4 --ignore-daemonsets --delete-emptydir-data

# Delete from cluster
kubectl delete node worker4

# Uninstall K3s on the node
ansible worker4 -m shell -a "/usr/local/bin/k3s-agent-uninstall.sh"
```

## Next Steps

- [Configure JupyterHub](../jupyterhub/index.md)
- [Set up Authentication](../jupyterhub/authentication-guide.md)
- [Manage Users](../jupyterhub/user-management.md)
- [Configure Quotas](../jupyterhub/quota-system.md)
