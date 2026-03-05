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


# Ryzen AI PC Cluster Ansible Playbooks

Note: This k3s ansible role is a modification based on [k3s-ansible](https://github.com/k3s-io/k3s-ansible/tree/master).

**Official documentation**:
- [Ansible Documentation](https://docs.ansible.com/ansible/latest/index.html)
- [K3s Documentation](https://docs.k3s.io/)



## Prerequisites

Before you start make sure you have setup these requirements:

* **Ansible:** 2.18.3 or later (only required on the kube-controller node)
* **Python:** 3.12
* **SSH:** root login allowed, and SSH keys synced across nodes
* **Hosts:** All nodes share the same `/etc/hosts` entries

> **Tip:** It's recommended to test SSH connectivity from the controller node to all other nodes using key-based authentication with account `root`.



## Initial Setup

### 1. Select the K8s Controller Node

Choose one node as the **Kubernetes controller**. This node will also act as the **Ansible control host**.

### 2. Update `/etc/hosts` on Controller

On the controller node, ensure `/etc/hosts` contains all cluster nodes
```
<host-ip> host
<node1-ip> node1
<node2-ip> node2
<node3-ip> node3
...
```

This allows each node to resolve the others by hostname.

> You can automate this with Ansible using a task that loops through all nodes and adds them to `/etc/hosts` (idempotent).

### 3. Allow Root Login via SSH Key

Ensure the root account on the controller node can login to all nodes using SSH keys:

1. Create `.ssh` directory if it does not exist:

```bash
sudo mkdir -p /root/.ssh
sudo chmod 700 /root/.ssh
```

2. Add your public key to `authorized_keys`:

```bash
sudo sh -c 'cat /home/<user>/.ssh/id_rsa.pub >> /root/.ssh/authorized_keys'
sudo chmod 600 /root/.ssh/authorized_keys
```

> This ensures Ansible can run tasks as root across all nodes without password prompts.

Also you can use [this script](../scripts/setup_ssh_root_access.sh) to help you spread the public key to all nodes for root login.

### Notes

* The controller node is the only one where Ansible needs to be installed.
* All other nodes only require Python 3.12 and SSH access for `root`.
* Maintaining consistent `/etc/hosts` entries is crucial for K3s cluster networking.




## Host Inventory
Config the host inventory in `inventory.yml` file.

The server and agent nodes should be defined in the `inventory.yml` file. The server node is the node you install `ansible` and host `NFS` on (suggested). 
Currently we only support one server node and multiple agent nodes.
The agent nodes are the nodes you want to join to the cluster which are required to have root access from the server node.
```ini
#Example
---
k3s_cluster:
  children:
    server:
      hosts:
        <YOUR-SERVER-HOSTNAME>:
        host:
    agent:
      hosts:
        <YOUR-AGENT-HOSTNAME>:
        strix1:

  # Required Vars
  vars:
    ansible_port: 22
    ansible_user: root
    k3s_version: v1.32.3+k3s1
    # The token should be a random string of reasonable length. You can generate
    # one with the following commands:
    # - openssl rand -base64 64
    # - pwgen -s 64 1
    # You can use ansible-vault to encrypt this value / keep it secret.
    # Or you can omit it if not using Vagrant and let the first server automatically generate one.
    token: "changeme!"
    api_endpoint: "{{ hostvars[groups['server'][0]]['ansible_host'] | default(groups['server'][0]) }}"
```

## Setup with k3s

```bash
# Setup new nodes
cd deploy/ansible/
sudo ansible-playbook playbooks/pb-base.yml
sudo ansible-playbook playbooks/pb-k3s-site.yml
```

> **💡 Tip - Kubeconfig Permissions**: By default, K3s creates `/etc/rancher/k3s/k3s.yaml` with `600` permissions (root-only). To avoid "permission denied" errors, you can configure K3s to generate the kubeconfig with readable permissions by adding the following to your `inventory.yml`:
>
> ```yaml
> k3s_cluster:
>   vars:
>     extra_server_args: "--write-kubeconfig-mode=644"
> ```
>
> This sets the kubeconfig file permissions to `644`, allowing all users to read the file. See [K3s Cluster Access](https://docs.k3s.io/cluster-access) for more details.

## Add a new node
Make sure your private key has access to the node with root permission. 
Insert new hostnames to agent section inside `inventory.yml`, add run site command again.
```bash
sudo ansible-playbook playbooks/pb-k3s-site.yml
```

## Reset 
If you want to reset the entire cluster. All your data and config will be removed.
```bash
sudo ansible-playbook playbooks/pb-k3s-reset.yml 
```
After resetting whole cluster, do remove the folder `~/.kube`.

Only reset a node.f
```bash
sudo ansible-playbook playbooks/pb-k3s-reset.yml --limit <node_name>
```

## Install GPU driver

You should both install GPU driver and ROCm software on each GPU node.
We are using ROCm 7.1.0, you can change the version in `pb-rocm.yml` file.
```bash
sudo ansible-playbook playbooks/pb-rocm.yml
```

**Official documentation**: https://rocm.docs.amd.com/projects/install-on-linux/en/latest/install/quick-start.html

## Install NPU driver (TODO)
You should both install NPU driver and ROCm software on each NPU node.
Please check the exact filename in the `pb-npu.yml` file.
Here NPU-related settings are not ready for open-source review, this section remains for future use.

```bash
#sudo ansible-playbook playbooks/pb-npu.yml
```

## Troubleshooting

### The Ansible process halts at `TASK [k3s_agent : Enable and check K3s service] `

Do check if the k3s service is running on the agent node.
```bash
ssh <agent_node>
sudo systemctl status k3s-agent.service
```
If the service is not running, you can try to restart the service.
If the service is running but spamming connection error to the `k3s-host` machine, do check if you have setup the `/etc/hosts` file on `k3s-agent` machine correctly.

### kubectl commands fail with "permission denied" error

If you encounter errors like:
```
error: error loading config file "/etc/rancher/k3s/k3s.yaml": open /etc/rancher/k3s/k3s.yaml: permission denied
```

**Solution 1 (Recommended)**: Configure K3s to generate kubeconfig with readable permissions by adding to `inventory.yml`:
```yaml
k3s_cluster:
  vars:
    extra_server_args: "--write-kubeconfig-mode=644"
```

Then re-run the playbook:
```bash
sudo ansible-playbook playbooks/pb-k3s-site.yml
```

**Solution 2**: Copy kubeconfig to user directory (already done by playbook if `user_kubectl: true`):
```bash
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $(id -u):$(id -g) ~/.kube/config
export KUBECONFIG=~/.kube/config
```

See [K3s Cluster Access](https://docs.k3s.io/cluster-access) for more details.

