# 3 Node Mini-Cluster Example

This is a concrete, end-to-end example of building a small multi-node K3s cluster by PXE-netbooting diskless machines, then deploying AUP Learning Cloud on top of it. One service machine boots the other machines over the network, and those machines auto-join the K3s cluster with no per-machine OS install. It walks one reference topology from bare machines all the way to a JupyterHub login that can spawn a GPU notebook on a netbooted node.

The `pxe_controller` role turns the service machine into the PXE controller. It installs and configures `dnsmasq` as Proxy-DHCP + TFTP, builds an NFS root filesystem under `/srv/nfs/rootfs` with `debootstrap`, copies the netboot kernel/initrd and BIOS/UEFI boot menus to `/srv/tftp`, and prepares Apache to serve the K3s join credentials under `/k3s/`.

![Three AIPC mini-cluster: one service machine and two netboot agents](../../_static/three-node-banner.png)

## Architecture

![Basic example PXE netboot architecture](../../_static/basic-example-pxe-architecture.svg)

In this example **only the service machine (AIPC 1) runs an operating system you install and manage with Ansible.** AIPC 1 hosts the PXE controller and the single-node K3s server, and every Ansible playbook in this guide runs against AIPC 1.

The other machines (the agents) are **diskless**: they have no installed OS and are not managed by Ansible. They netboot from AIPC 1 and join the cluster automatically through the `k3s-auto-join.service` baked into the netboot rootfs.

::::::{note}
The standard k3s-ansible flow in this repo (`pb-k3s-site.yml` with `server` and `agent` inventory groups over SSH) is designed for the case where **every** node already has an OS installed. This PXE example is different: the agents have no OS, so you do **not** put them in the `agent` inventory group. You only configure AIPC 1 as the `server`, and the agents come up by netboot.
::::::

The netbooted agents follow this boot path:

1. Firmware asks the LAN DHCP service for an IP address.
2. `dnsmasq` on AIPC 1 replies with PXE boot metadata (Proxy-DHCP).
3. The agent downloads `pxelinux.0` for BIOS boot or `grubnetx64.efi` for UEFI.
4. The boot menu loads `vmlinuz` and `initrd.img` from TFTP.
5. The kernel mounts the read-only NFS rootfs from `/srv/nfs/rootfs`.
6. `overlayroot` provides a writable tmpfs layer.
7. `set-hostname.service` sets the hostname to `agent-<MAC>`.
8. `k3s-auto-join.service` fetches the K3s token from `http://<SERVICE_IP>:8080/k3s/token` and joins the server at `https://<SERVICE_IP>:6443`.

## What To Prepare

A minimal example uses **three machines** on the **same LAN**:

| Role | Count | Notes |
|------|-------|-------|
| Service machine (AIPC 1) | 1 | Runs the PXE controller and the single-node K3s server. Needs a local disk and a reserved/static IP. The only Ansible-managed node. |
| Agent (AIPC 2, AIPC 3) | 2+ | Diskless workers that netboot. No OS install, not managed by Ansible. |

You also need, already in place on the LAN:

- **A DHCP server** (router/firewall/switch). `dnsmasq` here runs in **Proxy-DHCP** mode and does **not** hand out IP leases — it only adds the PXE boot information on top of your existing DHCP.
- **Internet access** from the service machine, to pull packages and build the rootfs.

Per-machine requirements:

- **Service machine**: Ubuntu 24.04, a reserved/static IP, a local disk, and network reachable by the agents.
- **Agents**: a working **in-kernel** network driver (this role ships no vendor drivers — add the module to `pxe_initramfs_modules` if needed), and a local disk if you want persistent K3s state across reboots.
- **All machines**: UEFI Secure Boot **disabled** in firmware (the UEFI path boots GRUB directly without a Microsoft-signed shim), and the ability to network-boot (PXE) from firmware.

::::::{danger}
Decide how each agent will handle local storage before you expose it to this netboot image. The generated `mount-local-disk` script selects the first existing whole-device candidate in this order: `/dev/sda`, `/dev/vda`, then `/dev/nvme0n1`. If that device isn't already ext4, the script runs `mkfs.ext4 -F` on the whole device. This can erase its partition table and all existing data. There is no interactive confirmation.

For persistent K3s state, expose only a dedicated blank disk, or a disk whose contents have a verified, restorable backup and whose erasure you have explicitly approved. Check the agent's device mapping outside this boot flow before continuing. If persistence isn't wanted, make an explicit decision not to expose a local disk to the agent, for example by disconnecting it or removing it from the VM hardware. With none of the three candidates present, the script uses tmpfs for K3s data instead.
::::::

::::::{warning}
No site values (IPs, subnet, SSH keys, passwords, tokens) ship in this repo. You set them in the inventory and the playbook, and the role **fails fast** if a required value is empty. Keep real secrets out of version control.
::::::

## Step 1 — Prepare The Service Machine

Install Ubuntu 24.04 on AIPC 1 and give it a stable IP. The same IP is used for the PXE controller, NFS rootfs, Apache token endpoint, and K3s API endpoint.

Install the operator tools and the PXE host packages (the role does not install its own host packages):

```bash
sudo apt update
sudo apt install -y git ansible curl ca-certificates jq \
  dnsmasq pxelinux syslinux-common apache2 \
  nfs-kernel-server debootstrap \
  grub-efi-amd64-signed shim-signed
```

Find the interface, subnet, and DNS you will use, and record them for Step 3:

```bash
ip -br addr
ip route
```

Clone the repository on AIPC 1 and work from its root:

```bash
git clone <REPO_URL> ~/aup-learning-cloud
cd ~/aup-learning-cloud
```

### Enable passwordless root SSH

The inventory uses `ansible_user: root` (Step 2), so Ansible connects to the target as `root` over key-based SSH. Before running any playbook you must give `root` a passwordless SSH login, otherwise the very first task ("Gathering Facts") fails with `UNREACHABLE! ... Permission denied (publickey,password)`.

Because AIPC 1 manages **itself** in this single-machine topology, authorise your own SSH key for the local `root` account:

```bash
sudo install -d -m 0700 /root/.ssh
sudo tee -a /root/.ssh/authorized_keys < ~/.ssh/id_ed25519.pub >/dev/null
sudo chmod 0600 /root/.ssh/authorized_keys

# verify root SSH works without a password
ssh root@<SERVICE_IP> true && echo root-ssh-ok
```

::::::{note}
Because the service machine is also the Ansible target, you can avoid SSH entirely by telling Ansible to run on the local host. Add `ansible_connection: local` to the host vars in `inventory.yml` (Step 2); Ansible then executes tasks directly without an SSH round-trip and no root SSH setup is needed.
::::::

## Step 2 — Configure The Inventory

Edit `deploy/ansible/inventory.yml`. You define two things: the `pxe_controller` group (used by the PXE playbook) and the K3s `server` group (used to install the single-node master). AIPC 1 is the only host in both, and the `agent` group stays **empty** because the netboot agents are not Ansible-managed.

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

::::::{note}
Keep `k3s_version` here in sync with `pxe_k3s_version` in the PXE playbook (Step 3). K3s requires every agent to be the same version as, or older than, the server.
::::::

## Step 3 — Configure The PXE Controller Playbook

Edit the `vars:` block in this playbook:

```text
deploy/ansible/playbooks/pb-pxe-controller.yml
```

The required values are empty by default — set them all:

```yaml
pxe_rootfs_force_rebuild: true        # true for the first build

pxe_network_interface: "enp1s0"       # service-machine NIC (from Step 1)
pxe_subnet: "192.168.1.0/24"          # node subnet, CIDR
pxe_dns_servers: "8.8.8.8,8.8.4.4"    # DNS for the rootfs

pxe_controller_ip: "192.168.1.10"     # this service machine's IP
pxe_k3s_server_ips:
  - "192.168.1.10"                    # K3s server IP (this machine)

pxe_k3s_version: "v1.32.3+k3s1"       # must match inventory k3s_version

pxe_rootfs_authorized_keys:
  - "ssh-ed25519 AAAA... you@host"    # at least one key is required
```

::::::{note}
`pxe_gateway` is optional and currently informational only. `pxe_rootfs_password` can stay empty to keep root password login disabled (key-only). Use `pxe_rootfs_force_rebuild: true` for the first build, then set it back to `false` once the rootfs is stable so you do not rebuild it underneath running agents.
::::::

## Step 4 — Run The PXE Controller Playbook

```bash
cd ~/aup-learning-cloud/deploy/ansible
ansible-playbook -i inventory.yml playbooks/pb-pxe-controller.yml
```

The role builds the NFS rootfs, installs the agent boot services into it, pins and installs the K3s agent binary, copies the kernel/initrd and boot menus to `/srv/tftp`, configures NFS and `dnsmasq`, and prepares the Apache `/k3s/` directory. When it finishes it prints a summary with the controller IP and a short next-steps list.

## Step 5 — Verify The Controller

```bash
systemctl is-active dnsmasq nfs-kernel-server apache2
showmount -e localhost
ls -l /srv/tftp/pxelinux.0 /srv/tftp/grubnetx64.efi /srv/tftp/vmlinuz /srv/tftp/initrd.img
curl -I http://127.0.0.1:8080/k3s/
```

Expected: `dnsmasq`, `nfs-kernel-server`, and `apache2` are all `active`; `showmount` lists `/srv/nfs/rootfs` exported to your subnet; the four boot files exist under `/srv/tftp`; and `http://127.0.0.1:8080/k3s/` returns `403` (the directory exists but is empty and not listable). The `token` endpoint is `404` until you publish it in Step 7.

::::::{note}
The role serves the `/k3s/` credential endpoint on port **8080**, not 80. This lets the PXE controller share the host with k3s, whose Traefik / ServiceLB owns host ports 80/443 for cluster ingress. The port is set by `pxe_web_port` in the PXE playbook.
::::::

## Step 6 — Install The Single-Node K3s Server

Install the K3s server on AIPC 1 using the repo's existing k3s-ansible flow. With the `server` group pointing at AIPC 1 and the `agent` group empty (from Step 2), this installs a single-node master and configures `kubectl` for your user automatically.

Run the playbooks **without** `sudo`. With key-based root SSH (Step 1), Ansible already connects as `root`; prefixing `sudo` would make it use the local machine's root SSH key instead and fail authentication.

```bash
cd ~/aup-learning-cloud/deploy/ansible
ansible-playbook -i inventory.yml playbooks/pb-base.yml
ansible-playbook -i inventory.yml playbooks/pb-k3s-site.yml
```

The K3s server install configures `kubectl` for your user and writes `~/.kube/config`. Point `KUBECONFIG` at it once so every later `kubectl` / `helm` command works **without** `sudo` (add this to your `~/.bashrc` to make it stick):

```bash
export KUBECONFIG=~/.kube/config
```

Verify the server is up and `kubectl` works:

```bash
kubectl get nodes -o wide
```

::::::{note}
`kubectl get nodes -o wide` and `sudo k3s kubectl get nodes -o wide` are equivalent — the first uses your user `kubectl` against `~/.kube/config`, the second uses K3s' bundled `kubectl` against the root-only `/etc/rancher/k3s/k3s.yaml`. With `KUBECONFIG` exported as above, prefer the plain, `sudo`-free `kubectl` form throughout this guide.
::::::

::::::{note}
The netbooted agents are diskless and are intentionally **not** in the `agent` inventory group, so `pb-k3s-site.yml` only installs the server. The agents join later by netboot (Step 8), not through this playbook.
::::::

## Step 7 — Publish K3s Credentials For The Agents

At boot, each agent's `k3s-auto-join.sh` fetches `http://<SERVICE_IP>:8080/k3s/token` and `http://<SERVICE_IP>:8080/k3s/kubeconfig`. Publish both through Apache:

::::::{danger}
Use this design only on an isolated, trusted provisioning network. These files are served over plain HTTP and the Apache ACL makes them readable to reachable members of the configured `pxe_subnet`. The token allows a node to join the cluster, and the published server kubeconfig is an administrative kubeconfig. Anyone on that subnet who can reach the endpoint can read those credentials, and HTTP doesn't protect them in transit.

Before publishing, restrict the provisioning subnet with network isolation and ACLs so only intended agents and operators can reach port 8080. Review the subnet before each run. After provisioning, rotate the node-join token and administrative kubeconfig, then update or withdraw the published copies according to the site's agent reboot requirements.
::::::

```bash
sudo install -d -m 0755 /var/www/html/k3s

sudo install -m 0644 \
  /var/lib/rancher/k3s/server/token \
  /var/www/html/k3s/token

sudo sed "s#https://127.0.0.1:6443#https://<SERVICE_IP>:6443#g" \
  /etc/rancher/k3s/k3s.yaml | sudo tee /var/www/html/k3s/kubeconfig >/dev/null

sudo chmod 0644 /var/www/html/k3s/token /var/www/html/k3s/kubeconfig
sudo systemctl reload apache2
```

Verify the endpoints respond:

```bash
curl -fsS http://127.0.0.1:8080/k3s/token >/dev/null && echo token-ok
curl -fsS http://127.0.0.1:8080/k3s/kubeconfig >/dev/null && echo kubeconfig-ok
curl -kfsS https://<SERVICE_IP>:6443/ping
```

The Apache ACL generated by the role allows your `pxe_subnet` and localhost. If an agent cannot fetch the token, recheck `pxe_subnet` and the generated Apache config.

## Step 8 — Netboot The Agents

On each agent machine: connect it to the same LAN as AIPC 1, enter firmware setup, disable Secure Boot, enable network boot, and put PXE before local disk in the boot order. BIOS and UEFI PXE both work — the role generates menus for both. Save and boot.

In firmware this is usually a `Boot Device Priority` (or `Boot Order`) screen listing each bootable device. You will see the local disk entry (for example `SATA`, `SCSI`, or `NVMe`) alongside one or more network-boot entries, named something like `PXE`, `Network`, `IBA GE Slot ...`, or `... etherboot`. Move a network/PXE entry to the top so the machine attempts netboot before the local disk, then save and exit. The exact labels vary by vendor, but the goal is the same: the first boot device is the NIC, not the disk.

As the machine netboots you should first see a firmware line such as `>>Start PXE over IPv4`, then the PXE boot menu, where the default entry is `AUP Learning Cloud K3s Agent (Network Boot)`. Let it boot (or select that entry). When it finishes you land at a console login prompt for the generated hostname, for example `agent-bc-24-11-d1-a8-b2 login:` — that confirms the NFS rootfs booted.

::::::{note}
The screenshots below use a virtual machine as the example agent (here a Proxmox VM), so your firmware and console will look different on physical hardware, but the sequence is the same.
::::::

![Agent firmware starting PXE over IPv4 (VM example)](../../_static/pxe-netboot-start.png)

![Agent console login prompt after netboot (VM example)](../../_static/agent-login-prompt.png)

After boot, each agent mounts `/srv/nfs/rootfs`, sets its hostname to `agent-<MAC>`, runs `mount-local-disk`, fetches the token, and joins the server. `mount-local-disk` either mounts the first candidate device for K3s data or, when no candidate exists, creates a temporary in-memory mount as described in the storage warning above.

Watch node registration from AIPC 1:

```bash
watch kubectl get nodes -o wide
```

Expected: AIPC 1 is `Ready`, and each netbooted agent shows up as an `agent-<MAC>` node and becomes `Ready`.

## Step 9 — Validate Agent State Across Reboots

Choose the validation branch that matches the local-storage decision made before netboot.

### Dedicated-disk branch

Use this branch only when the agent exposes an approved dedicated disk. Reboot one agent and confirm it rejoins with the same node identity rather than as a new node:

```bash
kubectl get nodes -o wide
```

On the agent, confirm the dedicated K3s data mount and saved node password exist:

```bash
mount | grep /var/lib/rancher/k3s
test -f /var/lib/rancher/k3s/node-password && echo node-password-ok
systemctl status mount-local-disk --no-pager
systemctl status k3s-agent --no-pager
```

These reboot, mount, and saved-password checks are required acceptance checks for the dedicated-disk branch.

### No-candidate-disk branch

Use this branch when none of `/dev/sda`, `/dev/vda`, or `/dev/nvme0n1` is exposed to the agent. The script mounts tmpfs at the K3s data directory. Node-local K3s state, the saved node password, container images, and container runtime state are therefore ephemeral and are lost across a reboot. Don't claim local persistence or apply the dedicated-disk reboot and saved-password acceptance checks to this branch. After every reboot, validate the agent's boot and cluster registration as a fresh node-local state cycle.

Notebook data has a separate persistence boundary. After Step 11 configures `nfs-client` and the AUP site values select it, notebook PVC data is stored on the dedicated NFS export and can persist across agent reboot or rescheduling. That NFS-backed PVC persistence does not make the agent's tmpfs-backed K3s or container state persistent.

If an agent reboots but cannot rejoin, inspect the boot services on the agent:

```bash
journalctl -u mount-local-disk -n 100 --no-pager
journalctl -u k3s-auto-join -n 100 --no-pager
journalctl -u k3s-agent -n 100 --no-pager
```

If a stale node object blocks rejoin during testing, delete it from AIPC 1 and reboot the agent. This is a debugging action, not a normal operating procedure:

```bash
kubectl delete node <AGENT_NODE_NAME>
```

## Step 10 — Install The AMD GPU Device Plugin And Labeller

Deploy the AMD GPU device plugin and the ROCm node labeller so GPUs are schedulable and labelled:

```bash
kubectl create -f https://raw.githubusercontent.com/ROCm/k8s-device-plugin/master/k8s-ds-amdgpu-dp.yaml
kubectl create -f https://raw.githubusercontent.com/ROCm/k8s-device-plugin/master/k8s-ds-amdgpu-labeller.yaml
```

Verify GPU resources and labels on the agents:

```bash
kubectl get pods -A | grep -i amd
kubectl describe node <AGENT_NODE_NAME> | grep amd.com/gpu
```

Use the labels that actually appear on your agents when you write the chart values in Step 12. Common keys include `amd.com/gpu.product-name`, `amd.com/gpu.family`, and `amd.com/gpu.device-id`.

Example:

```bash
kubectl describe node agent-10-b6-76-52-64-02 | grep amd.com/gpu
Labels:             amd.com/gpu.cu-count=40
                    amd.com/gpu.device-id=1586
                    amd.com/gpu.family=GC_11_5_0
                    amd.com/gpu.product-name=AMD_Radeon_8060S_Graphics
                    amd.com/gpu.simd-count=80
                    amd.com/gpu.vram=64G
                    beta.amd.com/gpu.cu-count=40
                    beta.amd.com/gpu.cu-count.40=1
                    beta.amd.com/gpu.device-id=1586
                    beta.amd.com/gpu.device-id.1586=1
                    beta.amd.com/gpu.family=GC_11_5_0
                    beta.amd.com/gpu.family.GC_11_5_0=1
                    beta.amd.com/gpu.product-name=AMD_Radeon_8060S_Graphics
                    beta.amd.com/gpu.product-name.AMD_Radeon_8060S_Graphics=1
                    beta.amd.com/gpu.simd-count=80
                    beta.amd.com/gpu.simd-count.80=1
                    beta.amd.com/gpu.vram=64G
                    beta.amd.com/gpu.vram.64G=1
  amd.com/gpu:        1
  amd.com/gpu:        1
  amd.com/gpu        0               0
```

## Step 11 — Prepare Shared NFS Storage For Notebook PVCs

The PXE NFS rootfs is not the notebook storage backend. Create a separate NFS export for Kubernetes PVCs; it can run on AIPC 1 for a small lab.

::::::{danger}
Choose a new, dedicated `<NFS_EXPORT>` directory for notebook PVCs. Don't use `/srv/nfs/rootfs`, and don't continue if the chosen path already contains data unless you have a verified, restorable backup. Back up `/etc/exports`, review `<CLUSTER_SUBNET>` so the export isn't open to a broader network, and confirm that an equivalent export entry doesn't already exist before appending one.

The recursive ownership and mode commands below change every existing item under `<NFS_EXPORT>`, and mode `0777` permits all local users to write there. The `no_root_squash` option gives remote root broad access to the export. Continue only if the dedicated path, subnet boundary, permissions, and remote-root risk are approved by the site's storage and security policy.
::::::

```bash
sudo mkdir -p <NFS_EXPORT>
sudo chown -R nobody:nogroup <NFS_EXPORT>
sudo chmod 0777 <NFS_EXPORT>
echo "<NFS_EXPORT> <CLUSTER_SUBNET>(rw,sync,no_subtree_check,no_root_squash,insecure)" | sudo tee -a /etc/exports
sudo exportfs -ra
sudo systemctl restart nfs-kernel-server
showmount -e localhost
```

::::::{note}
Append the export to `/etc/exports` directly. On Ubuntu 24.04 the `/etc/exports.d/` directory does not exist by default, and `exportfs` only reads files there that end in `.exports` (see `man exports`) — a `.conf` file is silently ignored, so the export never takes effect and notebook PVCs stay `Pending`. Confirm the new line appears in `showmount -e localhost` before continuing.
::::::

Create local Helm values for the NFS provisioner from the shipped example and install it:

```bash
cd ~/aup-learning-cloud
cp deploy/k8s/nfs-provisioner/values.yaml deploy/k8s/nfs-provisioner/values.local.yaml
# edit values.local.yaml: set nfs.server, nfs.path, and storageClass.name (nfs-client)

helm repo add nfs-subdir-external-provisioner https://kubernetes-sigs.github.io/nfs-subdir-external-provisioner/
helm repo update
helm upgrade --install nfs-subdir-external-provisioner \
  nfs-subdir-external-provisioner/nfs-subdir-external-provisioner \
  --namespace nfs-provisioner --create-namespace \
  -f deploy/k8s/nfs-provisioner/values.local.yaml
```

Verify the storage class and provisioner pod:

```bash
kubectl get storageclass
kubectl get pods -n nfs-provisioner
```

## Step 12: Apply The PXE Topology Deltas

First, from the deployment repository root, create `runtime/values-basic-example.yaml`. The guarded sequence stops without overwriting an existing site file:

```bash
(
  set -e
  if test -e runtime/values-basic-example.yaml; then
    printf '%s\n' 'Refusing to overwrite runtime/values-basic-example.yaml; review the existing site file.' >&2
    exit 1
  fi
  umask 077
  cp --no-clobber runtime/values-multi-nodes.yaml.example runtime/values-basic-example.yaml
  chmod 600 runtime/values-basic-example.yaml
)
```

After creating the file, complete the {ref}`K3s readiness checklist <multi-node-k3s-ready>`. For this PXE topology, `runtime/values-basic-example.yaml` substitutes for the checklist's normal `runtime/values-multi-nodes.yaml` site-values gate. Require the PXE file to exist as a reviewed site file that wasn't created by overwriting prior configuration. All other checklist gates remain unchanged. The Ready-node gate includes AIPC 1 and every netbooted `agent-<MAC>` node intended for notebook workloads. The GPU discovery gate must use the labels and allocatable resources observed on those agents in Step 10.

Then follow the {ref}`canonical Kubernetes preflight and deployment flow <existing-kubernetes-preflight>` for values review, manifest inspection, installation, and infrastructure validation. Use `runtime/values-basic-example.yaml` as this topology's site values file when following those canonical steps.

Keep these PXE-specific choices in the site values:

- Point both the Hub database PVC and dynamic notebook PVCs at the `nfs-client` StorageClass from Step 11. Confirm that its provisioner still targets `<NFS_EXPORT>`, not the read-only PXE rootfs at `/srv/nfs/rootfs`.
- Set each GPU resource's node selector from labels observed on a netbooted agent. Do not copy a product label from another cluster.
- For this isolated lab example, expose the proxy with a NodePort and reserve HTTP port `30890`. Use the canonical exposure gate before making the service reachable from an untrusted network.
- Select authentication and notebook images through the canonical values review. Keep credentials and private-registry secrets out of the values file and version control.

## Step 13: Install Through The Canonical Flow

Complete the canonical render, inspection, install, and infrastructure-validation steps linked in Step 12, substituting `runtime/values-basic-example.yaml` for the canonical guide's example site values filename. Do not omit the explicit site values file from any Helm operation.

After the canonical infrastructure checks pass, the lab NodePort URL is:

```text
http://<SERVICE_IP>:30890
```

## Step 14: Validate The PXE Deployment Deltas

Run the complete {ref}`canonical end-to-end acceptance <existing-kubernetes-end-to-end-acceptance>`. In addition to those checks, require the following PXE-specific results:

- AIPC 1 and every intended `agent-<MAC>` node are `Ready` after a netboot cycle.
- The `nfs-client` provisioner uses the separate notebook export `<NFS_EXPORT>`; it does not store notebook PVC data in `/srv/nfs/rootfs`.
- The CPU notebook's persisted test file survives a server restart because it is backed by its notebook PVC, not by the agent's volatile rootfs overlay.
- The GPU notebook pod lands on a netbooted `agent-<MAC>` node with the selected GPU label and a non-zero `amd.com/gpu` allocation.
- The NodePort URL `http://<SERVICE_IP>:30890` reaches the Hub from the intended lab network.

## Troubleshooting

| Symptom | Likely cause | First checks |
|---------|--------------|--------------|
| Playbook fails immediately on an assert | A required var is still empty | Re-check `pxe_controller_ip`, `pxe_subnet`, `pxe_network_interface`, `pxe_dns_servers`, `pxe_k3s_server_ips`, and at least one SSH key |
| Agent never shows the PXE menu | Firmware boot order, network boot disabled, or Proxy-DHCP not reaching the client | Check firmware, switch port, `systemctl status dnsmasq`, and `journalctl -u dnsmasq` |
| Agent gets an IP but cannot load boot files | TFTP blocked, missing files, or UEFI Secure Boot still enabled | Check `/srv/tftp`, firewall rules, that Secure Boot is disabled, and `dnsmasq` logs |
| Agent has no network during netboot | Agent NIC has no in-kernel driver in the initramfs | Identify the NIC with `lspci -nnk`, add its in-kernel module to `pxe_initramfs_modules`, and rebuild the rootfs |
| Agent kernel boots but cannot mount rootfs | NFS export, subnet ACL, or wrong `pxe_controller_ip` | Check `showmount -e <SERVICE_IP>`, `/etc/exports`, and the rootfs kernel args |
| Agent waits for the K3s token | Token not published or Apache ACL blocks the client subnet | Check `curl http://<SERVICE_IP>:8080/k3s/token` and the Apache config |
| Agent joins once but fails after reboot | Missing local K3s persistence or lost node password | Check `mount-local-disk`, `/var/lib/rancher/k3s/node-password`, and `k3s-agent` logs |
| Agent fails to join with a version error | Agent rootfs k3s version newer than the server | Align `pxe_k3s_version` with the server `k3s_version` and rebuild the rootfs |
| GPU notebook stays Pending | Chart `nodeSelector` does not match real labels, or GPUs are exhausted | Check `kubectl describe pod <pod> -n jupyterhub` and the node labels |
| PVC stays Pending | StorageClass name mismatch or NFS provisioner cannot mount the export | Check `kubectl get storageclass`, provisioner logs, and the NFS export |

## Out Of Scope

The following are useful for a longer-running site but are not required for this minimal example: a Zot registry mirror, Cloudflare Tunnel ingress, monitoring and Grafana, HA K3s, external databases, and NPU-specific setup. Add them only after the minimal deployment can boot the agents, schedule GPU notebooks, and persist notebook storage.

## Scope and Limitations

This is a minimal teaching/lab example, not a production reference. To keep it to three machines, the service machine (AIPC 1) runs **everything central on one host**: the PXE controller, the TFTP/NFS rootfs, the Apache K3s credential endpoint, the **single-node K3s server (control plane)**, and the notebook **NFS storage**. Keep these consequences in mind:

- **Single point of failure.** If AIPC 1 goes down, the control plane, the netboot path, and notebook storage all go down with it. The agents also lose their NFS rootfs, so they cannot run while AIPC 1 is offline.
- **No high availability.** There is one K3s server with embedded SQLite, no HA control plane, and no external database.
- **Shared resource contention.** PXE/NFS/Apache/K3s-server and the notebook storage compete for the same CPU, memory, disk, and network on one box.
- **Storage durability.** The example NFS export lives on AIPC 1's local disk with no replication or backup; treat notebook data as disposable unless you add your own backups.
- **Agents are volatile.** Netboot agents run from a read-only NFS rootfs with a tmpfs overlay. With an approved dedicated disk, only the local K3s data directory persists across reboots. Without a candidate disk, that directory also uses tmpfs, so all node-local K3s and container state is ephemeral. Notebook PVC persistence remains separate and depends on the configured NFS StorageClass.

For a longer-running or production deployment, split these roles onto separate hosts, use an HA K3s control plane with an external/replicated datastore, and back the storage with a dedicated, redundant NFS (or other) backend.
