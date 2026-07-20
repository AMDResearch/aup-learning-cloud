# Deploy AUP Learning Cloud — Reference

Full, copy-runnable commands for both deployment topologies, the GPU label
mapping, the `values.yaml` field guide, and the troubleshooting table. The
workflow and confirmation gates are in [SKILL.md](SKILL.md).

## Contents

- [Source guides](#source-guides)
- [PXE-diskless topology (3-node mini-cluster)](#pxe-diskless-topology-3-node-mini-cluster)
- [SSH-preinstalled topology (standard multi-node)](#ssh-preinstalled-topology-standard-multi-node)
- [GPU label to accelerator key](#gpu-label-to-accelerator-key)
- [values.yaml field guide](#valuesyaml-field-guide)
- [Troubleshooting](#troubleshooting)

## Source guides

- 3-node mini-cluster (PXE diskless): <https://amdresearch.github.io/aup-learning-cloud/installation/multi-node/multi-aipc-hardware-deployment.html>
- Standard multi-node (SSH): <https://amdresearch.github.io/aup-learning-cloud/installation/multi-node.html>

Treat the live docs as the source of truth for version pins; this file
condenses the opinionated path.

The helper commands are resolved through `DEPLOY_SCRIPTS` as defined in
[SKILL.md](SKILL.md#helper-script-paths), not through a checkout-root
`scripts/` directory.

The two topology sections below are the two branches of the Phase 1a gate in
[SKILL.md](SKILL.md): **PXE Diskless Netboot** (`topology: pxe-diskless`) →
[PXE-diskless topology](#pxe-diskless-topology-3-node-mini-cluster); **Multi Node
SSH Installation** (`topology: ssh-preinstalled`) →
[SSH-preinstalled topology](#ssh-preinstalled-topology-standard-multi-node).

## PXE-diskless topology (3-node mini-cluster)

One service machine (AIPC 1) runs the PXE controller, the single-node k3s
server, NFS, and the apache k3s-credential endpoint. The other machines are
diskless agents that netboot and auto-join. Only AIPC 1 is Ansible-managed.

### Step 1 — Prepare the service machine

```bash
sudo apt update
sudo apt install -y git ansible curl ca-certificates jq \
  dnsmasq pxelinux syslinux-common apache2 \
  nfs-kernel-server debootstrap \
  grub-efi-amd64-signed shim-signed

ip -br addr   # record the NIC and IP
ip route      # record the gateway
```

Give the local `root` a passwordless SSH login (or add `ansible_connection:
local` to the host vars to skip SSH entirely):

```bash
sudo install -d -m 0700 /root/.ssh
sudo tee -a /root/.ssh/authorized_keys < ~/.ssh/id_ed25519.pub >/dev/null
sudo chmod 0600 /root/.ssh/authorized_keys
ssh root@<SERVICE_IP> true && echo root-ssh-ok
```

### Step 2 — Configure the inventory

Edit `deploy/ansible/inventory.yml`. AIPC 1 is the only host; the `agent` group
stays empty (netboot agents are not Ansible-managed). Generate the token with
`openssl rand -base64 64` and keep it out of chat/VCS.

```yaml
k3s_cluster:
  children:
    server:
      hosts:
        aipc1:
          ansible_host: <SERVICE_IP>
    agent:
      hosts: {}        # diskless netboot agents auto-join; do NOT list them here
  vars:
    ansible_user: root
    k3s_version: v1.32.3+k3s1
    token: "<paste-a-strong-random-token>"   # openssl rand -base64 64
    api_endpoint: "{{ hostvars[groups['server'][0]]['ansible_host'] | default(groups['server'][0]) }}"

pxe_controller:
  hosts:
    aipc1:
      ansible_host: <SERVICE_IP>
  vars:
    ansible_port: 22
    ansible_user: root
```

### Step 3 — Prepare the generated PXE controller vars

The network, controller, server-IP, and SSH-key values are empty by default and
the role asserts on them. `$DEPLOY_SCRIPTS/gen_configs.py` writes these values
to `generated/pb-pxe-controller.vars.yml`. Keep that file at mode `0600`; it can
contain `pxe_rootfs_password`. Resolve its absolute path for the Ansible and
validator commands instead of copying or merging it into the playbook:

```bash
PXE_VARS="$(realpath ./generated/pb-pxe-controller.vars.yml)"
chmod 0600 "$PXE_VARS"
test "$(stat -c '%a' "$PXE_VARS")" = 600
```

Review the generated values before the first run:

```yaml
pxe_rootfs_force_rebuild: true        # true for the first build (RISKY: rebuilds rootfs)
pxe_network_interface: "enp1s0"       # service-machine NIC (Step 1)
pxe_subnet: "192.168.1.0/24"          # node subnet, CIDR
pxe_gateway: "192.168.1.1"            # default gateway (informational)
pxe_dns_servers: "8.8.8.8,8.8.4.4"
pxe_controller_ip: "192.168.1.10"     # this service machine's IP
pxe_k3s_server_ips:
  - "192.168.1.10"
pxe_k3s_version: "v1.32.3+k3s1"       # MUST match inventory k3s_version
pxe_web_port: 8080                    # apache port for the k3s token/kubeconfig (not 80)
pxe_rootfs_password: ""               # optional; empty disables password login (use ansible-vault if set)
pxe_rootfs_authorized_keys:
  - "ssh-ed25519 AAAA... you@host"    # at least one key required
```

Set `pxe_rootfs_force_rebuild: false` after the first stable build so you do
not rebuild the rootfs under running agents. The playbook also exposes
`pxe_apt_mirror`, `pxe_rootfs_packages`, and `pxe_initramfs_modules` (add your
NIC module here if it lacks an in-kernel driver) — leave these at their defaults
unless discovery flagged a need.

### Step 4 — Run the PXE controller playbook

```bash
cd ~/aup-learning-cloud
REPO_ROOT="$(pwd)"
DEPLOY_SCRIPTS="$REPO_ROOT/skills/deploy-aup-learning-cloud/scripts"
PXE_VARS="$(realpath "$REPO_ROOT/generated/pb-pxe-controller.vars.yml")"
python3 "$DEPLOY_SCRIPTS/validate.py" --repo "$REPO_ROOT" \
  --topology pxe-diskless --pxe-vars "$PXE_VARS" \
  --values runtime/values.yaml --values runtime/values-basic-example.yaml
cd "$REPO_ROOT/deploy/ansible"
ansible-playbook -i inventory.yml playbooks/pb-pxe-controller.yml -e @"$PXE_VARS"
```

### Step 5 — Verify the controller

```bash
systemctl is-active dnsmasq nfs-kernel-server apache2
showmount -e localhost
ls -l /srv/tftp/pxelinux.0 /srv/tftp/grubnetx64.efi /srv/tftp/vmlinuz /srv/tftp/initrd.img
curl -I http://127.0.0.1:8080/k3s/    # 403 expected (dir exists, empty)
```

The `/k3s/` endpoint is served on port 8080 (k3s owns 80/443 for ingress).

### Step 6 — Install the single-node k3s server

Run **without** `sudo` (key-based root SSH already connects as root):

```bash
cd ~/aup-learning-cloud/deploy/ansible
ansible-playbook -i inventory.yml playbooks/pb-base.yml
ansible-playbook -i inventory.yml playbooks/pb-k3s-site.yml
export KUBECONFIG=~/.kube/config      # add to ~/.bashrc to persist
kubectl get nodes -o wide
```

### Step 7 — Publish k3s credentials for agents

```bash
sudo install -d -m 0755 /var/www/html/k3s
sudo install -m 0644 /var/lib/rancher/k3s/server/token /var/www/html/k3s/token
sudo sed "s#https://127.0.0.1:6443#https://<SERVICE_IP>:6443#g" \
  /etc/rancher/k3s/k3s.yaml | sudo tee /var/www/html/k3s/kubeconfig >/dev/null
sudo chmod 0644 /var/www/html/k3s/token /var/www/html/k3s/kubeconfig
sudo systemctl reload apache2

curl -fsS http://127.0.0.1:8080/k3s/token >/dev/null && echo token-ok
curl -fsS http://127.0.0.1:8080/k3s/kubeconfig >/dev/null && echo kubeconfig-ok
```

### Step 8 — Netboot the agents

On each agent: disable Secure Boot, enable network boot, and put PXE before the
local disk in the firmware boot order. Boot, then watch them register:

```bash
watch kubectl get nodes -o wide
```

Agents appear as `agent-<mac>` nodes and become `Ready`.

### Step 9 — Validate agent persistence

Reboot one agent; confirm it rejoins with the same identity. On the agent:

```bash
mount | grep /var/lib/rancher/k3s
test -f /var/lib/rancher/k3s/node-password && echo node-password-ok
systemctl status mount-local-disk k3s-agent --no-pager
```

`kubectl delete node <name>` clears a stale node object — **debugging only**,
confirm with the user first.

Continue with [Step 10 (GPU)](#step-10--amd-gpu-device-plugin-and-labeller).

## SSH-preinstalled topology (standard multi-node)

Every node already runs Ubuntu 24.04 and is reachable over passwordless SSH.

### Prepare SSH and inventory

Helper scripts in `deploy/scripts/` enable root SSH and distribute kubeconfig:

```bash
./deploy/scripts/edit_sshd.sh
./deploy/scripts/setup_ssh_root_access.sh
./deploy/scripts/deploy-kubeconfig.sh
```

Edit `deploy/ansible/inventory.yml` — list every node under `server`/`agent`:

```yaml
k3s_cluster:
  children:
    server:
      hosts:
        <SERVER-HOSTNAME>:
    agent:
      hosts:
        <AGENT-HOSTNAME-1>:
        <AGENT-HOSTNAME-2>:
  vars:
    ansible_port: 22
    ansible_user: root
    k3s_version: v1.32.3+k3s1
    token: "<strong-random-token>"   # openssl rand -base64 64
    api_endpoint: "{{ hostvars[groups['server'][0]]['ansible_host'] | default(groups['server'][0]) }}"
```

### Build the cluster

```bash
cd deploy/ansible
sudo ansible-playbook playbooks/pb-base.yml        # base OS / packages
sudo ansible-playbook playbooks/pb-k3s-site.yml    # deploy k3s
sudo ansible-playbook playbooks/pb-rocm.yml        # ROCm on GPU nodes
```

Related: `pb-k3s-upgrade.yml` (upgrade), `pb-k3s-reset.yml` (reset — RISKY).
Then install `kubectl`/`helm` on the operator machine (see Helm command below)
and continue with [Step 10 (GPU)](#step-10--amd-gpu-device-plugin-and-labeller).

### Install Helm

```bash
wget https://get.helm.sh/helm-v3.17.2-linux-amd64.tar.gz -O /tmp/helm.tar.gz
cd /tmp && tar -zxvf helm.tar.gz
sudo mv /tmp/linux-amd64/helm /usr/local/bin/helm
```

## Step 10 — AMD GPU device plugin and labeller

```bash
kubectl create -f https://raw.githubusercontent.com/ROCm/k8s-device-plugin/master/k8s-ds-amdgpu-dp.yaml
kubectl create -f https://raw.githubusercontent.com/ROCm/k8s-device-plugin/master/k8s-ds-amdgpu-labeller.yaml

kubectl get pods -A | grep -i amd
kubectl describe node <AGENT_NODE_NAME> | grep amd.com/gpu
```

Use the labels that actually appear. Common keys:
`amd.com/gpu.product-name`, `amd.com/gpu.family`, `amd.com/gpu.device-id`.

## Step 11 — Shared NFS storage for notebook PVCs

This is separate from the PXE rootfs export. Append the export directly to
`/etc/exports` (on Ubuntu 24.04 `/etc/exports.d/*.conf` is ignored):

```bash
sudo mkdir -p <NFS_EXPORT>
sudo chown -R nobody:nogroup <NFS_EXPORT>
sudo chmod 0777 <NFS_EXPORT>
echo "<NFS_EXPORT> <CLUSTER_SUBNET>(rw,sync,no_subtree_check,no_root_squash,insecure)" | sudo tee -a /etc/exports
sudo exportfs -ra
sudo systemctl restart nfs-kernel-server
showmount -e localhost
```

Install the provisioner (storage class `nfs-client`):

```bash
cd ~/aup-learning-cloud
cp deploy/k8s/nfs-provisioner/values.yaml deploy/k8s/nfs-provisioner/values.local.yaml
# edit values.local.yaml: nfs.server, nfs.path, storageClass.name = nfs-client
helm repo add nfs-subdir-external-provisioner https://kubernetes-sigs.github.io/nfs-subdir-external-provisioner/
helm repo update
helm upgrade --install nfs-subdir-external-provisioner \
  nfs-subdir-external-provisioner/nfs-subdir-external-provisioner \
  --namespace nfs-provisioner --create-namespace \
  -f deploy/k8s/nfs-provisioner/values.local.yaml
kubectl get storageclass
```

## Step 12 — Configure JupyterHub values

The generated `runtime/values-basic-example.yaml` is the canonical deployment
overlay. Review and keep it when Phase 3 generated one. Only when no generated
overlay exists, start a manual overlay from the example:

```bash
cd ~/aup-learning-cloud/runtime
if [ ! -e values-basic-example.yaml ]; then
  cp values-multi-nodes.yaml.example values-basic-example.yaml
fi
```

Minimum edits (see the [field guide](#valuesyaml-field-guide)):

```yaml
custom:
  authMode: "auto-login"      # single-machine default; avoid "dummy" (login 404s)
  accelerators:
    strix-halo:
      nodeSelector:
        amd.com/gpu.product-name: "<GPU_PRODUCT_LABEL>"   # from Step 10
      quotaRate: 3
  resources:
    images:
      cpu: "<CPU_NOTEBOOK_IMAGE>"
      gpu: "<GPU_NOTEBOOK_IMAGE>"
hub:
  db:
    pvc:
      storageClassName: nfs-client
singleuser:
  storage:
    dynamic:
      storageClass: nfs-client
proxy:
  service:
    type: NodePort
    nodePorts:
      http: 30890
```

## Step 13 — Deploy AUP Learning Cloud

```bash
cd ~/aup-learning-cloud
helm upgrade --install jupyterhub ./runtime/chart \
  --namespace jupyterhub --create-namespace \
  -f runtime/values.yaml \
  -f runtime/values-basic-example.yaml

kubectl get pods -n jupyterhub -o wide
kubectl get svc -n jupyterhub
```

For later config changes, re-run the same `helm upgrade --install`.

## Step 14 — End-to-end validation

```bash
kubectl get nodes -o wide
kubectl get pods -A
kubectl get storageclass
kubectl describe node <AGENT_NODE_NAME> | grep amd.com/gpu
```

Then browse to `http://<SERVICE_IP>:30890` (or your ingress host), log in,
spawn a CPU notebook, create a file, restart and confirm it persists, then
spawn a GPU notebook and confirm its pod lands on a GPU node.

## GPU label to accelerator key

The chart's accelerator catalog (`runtime/values.yaml`) is keyed by accelerator
names; map the ROCm labeller's `amd.com/gpu.product-name` to the right key. The
GPU is auto-detected (Phase 2 and Phase 5), not named by the user in the
interview — use this table to confirm the detected product-name → key mapping
with the user. Verify against the live values file — product names can normalize
differently per fleet.

| `amd.com/gpu.product-name` (example) | Accelerator key |
| --- | --- |
| `AMD_Radeon_780M_Graphics` | `phx` |
| `AMD_Radeon_890M_Graphics` | `strix` |
| `AMD_Radeon_8060S_Graphics` | `strix-halo` |
| `AMD_Radeon_RX_9070_XT` | `9070xt` |
| `AMD_Radeon_AI_PRO_R9700` | `r9700` |
| `AMD_Radeon_RX_9600_GRE` | `9600gre` |

If your labeller reports a different product name, update the matching
`custom.accelerators.*.nodeSelector` entry to that exact string.

## values.yaml field guide

Sections to review in the generated `values-basic-example.yaml`, or in the
manual `values-multi-nodes.yaml.example` copy when generation was not used:

| Field | Purpose |
| --- | --- |
| `custom.authMode` | `auto-login` for the single-machine example; OAuth modes for real auth |
| `custom.githubOrgName`, `hub.config.GitHubOAuthenticator` | GitHub OAuth (when not auto-login) |
| `custom.adminUser` | Hub admin |
| `custom.accelerators.*.nodeSelector` | Must match real `amd.com/gpu.*` labels |
| `custom.resources.images` | CPU/GPU/course notebook images |
| `custom.resources.requirements`, `custom.teams.mapping`, `custom.quota` | Per-team resources and quotas |
| `hub.db.pvc.storageClassName`, `singleuser.storage.dynamic.storageClass` | `nfs-client` for multi-node |
| `proxy.service`, `ingress` | NodePort (e.g. 30890) or ingress host |

## Troubleshooting

| Symptom | Likely cause | First checks |
| --- | --- | --- |
| Playbook fails immediately on an assert | A required PXE var is empty | Re-check `pxe_controller_ip`, `pxe_subnet`, `pxe_network_interface`, `pxe_dns_servers`, `pxe_k3s_server_ips`, and at least one SSH key |
| Agent never shows the PXE menu | Firmware boot order, network boot disabled, or Proxy-DHCP not reaching the client | Firmware, switch port, `systemctl status dnsmasq`, `journalctl -u dnsmasq` |
| Agent gets an IP but cannot load boot files | TFTP blocked, missing files, or Secure Boot still on | `/srv/tftp`, firewall, Secure Boot disabled, `dnsmasq` logs |
| Agent has no network during netboot | NIC has no in-kernel driver in the initramfs | `lspci -nnk`, add the module to `pxe_initramfs_modules`, rebuild rootfs |
| Agent kernel boots but cannot mount rootfs | NFS export, subnet ACL, or wrong `pxe_controller_ip` | `showmount -e <SERVICE_IP>`, `/etc/exports`, rootfs kernel args |
| Agent waits for the k3s token | Token not published or apache ACL blocks the subnet | `curl http://<SERVICE_IP>:8080/k3s/token`, apache config |
| Agent joins once but fails after reboot | Missing local k3s persistence or lost node password | `mount-local-disk`, `/var/lib/rancher/k3s/node-password`, `k3s-agent` logs |
| Agent fails to join with a version error | Agent rootfs k3s newer than the server | Align `pxe_k3s_version` with `k3s_version`, rebuild rootfs |
| Agent node does not join (SSH path) | Hostname resolution, token, or `api_endpoint` mismatch | `systemctl status k3s-agent`, `journalctl -u k3s-agent`, `/etc/hosts` |
| GPU notebook stays Pending | Chart `nodeSelector` mismatch or GPUs exhausted | `kubectl describe pod -n jupyterhub`, node labels |
| PVC stays Pending | StorageClass name mismatch or NFS provisioner cannot mount | `kubectl get storageclass`, provisioner logs, NFS export |
| `kubectl` permission denied on `k3s.yaml` | kubeconfig not readable | `export KUBECONFIG=~/.kube/config`, or `--write-kubeconfig-mode=644` in inventory `extra_server_args` |

For a complete reset (RISKY — confirm with the user):

```bash
cd deploy/ansible
sudo ansible-playbook playbooks/pb-k3s-reset.yml                 # whole cluster
sudo ansible-playbook playbooks/pb-k3s-reset.yml --limit <node>  # single node
```

## Out of scope

Zot registry mirror, Cloudflare Tunnel ingress, monitoring/Grafana, HA k3s,
external databases, and NPU setup. Add them only after the minimal deployment
boots agents, schedules GPU notebooks, and persists notebook storage.
