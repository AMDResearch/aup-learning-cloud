# Basic Example Multi-AIPC PXE Netboot Deployment Guide

This guide is a concrete, runnable worked example of deploying AUP Learning Cloud
across three AIPCs using PXE netboot. It walks one specific reference topology end
to end, so the node count, addresses, and hardware here are illustrative rather
than a generic hardware planning worksheet.

The reference topology is:

- AIPC 1: service machine running Ubuntu 24.04, PXE Controller, NFS rootfs,
  Apache token endpoint, K3s server, `kubectl`, Ansible, and Helm
- AIPC 2: diskless K3s agent booted by BIOS or UEFI PXE netboot
- AIPC 3: diskless K3s agent booted by BIOS or UEFI PXE netboot
- LAN DHCP service: assigns IP addresses to the AIPCs
- Shared storage: NFS-backed Kubernetes `StorageClass` for notebook homes

The goal is to finish with a working K3s cluster, two netbooted AMD GPU worker
nodes, shared notebook storage, and a JupyterHub deployment that can spawn a GPU
notebook on a netbooted AIPC.

::::::{warning}
Do not publish real deployment secrets in docs or review builds. Keep passwords,
private keys, K3s tokens, kubeconfig content, node inventory, internal IPs,
OAuth secrets, and registry credentials in private operations notes or an
encrypted secret store.
::::::

::::::{important}
Use placeholders in this guide, then replace them in your private deployment
notes:

- `<SERVICE_IP>`: static IP or DHCP reservation for AIPC 1
- `<CLUSTER_SUBNET>`: node subnet, for example `<192.168.1.0/24>`
- `<GATEWAY_IP>`: default gateway for the node subnet
- `<DNS_SERVERS>`: comma-separated DNS servers for the PXE rootfs
- `<K3S_VERSION>`: K3s version used by the site
- `<SSH_PUBLIC_KEY>`: operator SSH public key injected into netboot agents
- `<NFS_EXPORT>`: storage path for notebook PVCs
- `<HUB_HOSTNAME>`: user-facing hostname or local test endpoint
::::::

::::::{warning}
Disable UEFI Secure Boot in firmware on all three AIPCs before you start. The
UEFI netboot path boots GRUB directly and does not chainload a Microsoft-signed
shim, so the diskless agents (AIPC 2 and AIPC 3) can fail to load the bootloader
while Secure Boot is enabled. Keep Secure Boot off on AIPC 1 as well so its boot
configuration stays consistent with the agents.
::::::

## 1. Architecture

The PXE controller role uses `dnsmasq` as Proxy-DHCP and TFTP. It does not
issue normal DHCP leases. The LAN must already have DHCP from a router,
firewall, switch, or another DHCP server.

![Basic example PXE netboot architecture](../../_static/basic-example-pxe-architecture.svg)

The netbooted agents use this boot path:

1. Firmware asks the LAN DHCP service for an IP address.
2. `dnsmasq` on AIPC 1 replies with PXE boot metadata.
3. The agent downloads `pxelinux.0` for BIOS boot or `grubnetx64.efi` for UEFI.
4. The boot menu loads `vmlinuz` and `initrd.img` from TFTP.
5. The kernel mounts the read-only NFS rootfs from `/srv/nfs/rootfs`.
6. `overlayroot` provides a writable tmpfs layer.
7. `set-hostname.service` sets the hostname to `agent-<MAC>`.
8. `k3s-auto-join.service` fetches the K3s token from
   `http://<SERVICE_IP>/k3s/token` and joins the server at
   `https://<SERVICE_IP>:6443`.

## 2. Repository Layout

The PXE controller role ships with the product repository, so a normal clone
already contains everything you need. Work from the repository root:

```bash
cd ~/aup-learning-cloud
```

The relevant files are:

| Path | Purpose |
|------|---------|
| `deploy/ansible/playbooks/pb-pxe-controller.yml` | Main PXE controller playbook |
| `deploy/ansible/roles/pxe_controller/defaults/main.yml` | Default PXE variables |
| `deploy/ansible/roles/pxe_controller/tasks/main.yml` | Rootfs, TFTP, NFS, dnsmasq, Apache tasks |
| `deploy/ansible/roles/pxe_controller/templates/k3s-auto-join.sh.j2` | Agent auto-join logic |
| `deploy/ansible/roles/pxe_controller/templates/pxelinux-default.cfg.j2` | BIOS boot menu |
| `deploy/ansible/roles/pxe_controller/templates/grub.cfg.j2` | UEFI boot menu |
| `runtime/values-multi-nodes.yaml.example` | Starting point for JupyterHub values |

::::::{note}
In the current basic example deployment, K3s server bootstrap is not automated
by Ansible. The PXE playbook prepares netboot agents and the HTTP directory for
K3s credentials; you install the K3s server and publish the token manually.
::::::

## 3. Prepare AIPC 1

Install Ubuntu 24.04 on AIPC 1 and reserve a stable IP address for it. The
examples below assume this same IP is used for the PXE controller, NFS rootfs,
Apache token endpoint, K3s API endpoint, and operator access.

Install the operator tools:

```bash
sudo apt update
sudo apt install -y git ansible curl ca-certificates jq nfs-kernel-server
```

Install the PXE controller host packages. The `pxe_host_packages` list exists in
the role defaults, but the package installation task is commented out in the role
as shipped, so install these explicitly before running the playbook:

```bash
sudo apt install -y \
  dnsmasq \
  pxelinux \
  syslinux-common \
  apache2 \
  nfs-kernel-server \
  debootstrap \
  grub-efi-amd64-signed \
  shim-signed
```

Verify the service machine sees the correct network interface:

```bash
ip -br addr
ip route
```

Record the interface name, subnet, gateway, and DNS servers. These values feed
`pb-pxe-controller.yml`.

## 4. Prepare The Agent Local Disk Persistence

The netbooted rootfs is read-only NFS plus tmpfs overlay. Without additional
persistence, `/etc/rancher/node/password` and parts of
`/var/lib/rancher/k3s` can disappear after reboot. K3s uses that node password
to recognize a returning node with the same hostname, so losing it can cause
rejoin failures or duplicate node cleanup work.

Local-disk persistence ships with the `pxe_controller` role, so a normal clone
already includes it:

- `tasks/main.yml` deploys `mount-local-disk.service.j2` and
  `mount-local-disk.sh.j2` into the rootfs
- `chroot-setup.sh.j2` enables `mount-local-disk.service`
- `mount-local-disk.service` runs `Before=k3s-auto-join.service`
- `k3s-auto-join.sh.j2` persists `node-password` under
  `{{ pxe_k3s_data_dir }}/node-password`

The shipped `mount-local-disk.sh` discovers the first local disk among
`/dev/sda`, `/dev/vda`, and `/dev/nvme0n1`, formats it as ext4 only if it is not
already ext4, and mounts it at `pxe_k3s_data_dir` (default
`/var/lib/rancher/k3s`). If no local disk is found it falls back to a tmpfs
mount so the agent can still boot.

::::::{warning}
`mount-local-disk.sh` runs `mkfs.ext4` on the first matching block device when
that device is not already ext4. On hardware with multiple disks — or where
install media or another OS disk could match first — review and adjust the
device discovery order in
`deploy/ansible/roles/pxe_controller/templates/mount-local-disk.sh.j2` before
running the playbook so it never formats the wrong device.
::::::

After the playbook runs, confirm the generated rootfs contains the units:

```bash
sudo test -f /srv/nfs/rootfs/etc/systemd/system/mount-local-disk.service
sudo test -x /srv/nfs/rootfs/usr/local/bin/mount-local-disk.sh
```

If you intentionally run fully volatile diskless agents, remove the
`mount-local-disk` tasks and service dependency from the role and document a
node cleanup procedure for every reboot. That mode is not recommended for the
copyable deployment path.

## 5. Configure The PXE Controller Playbook

Edit the PXE controller playbook:

```bash
cd ~/aup-learning-cloud/deploy/ansible
nano playbooks/pb-pxe-controller.yml
```

Set these values in the playbook `vars:` block:

```yaml
pxe_rootfs_force_rebuild: true

pxe_network_interface: "<SERVICE_INTERFACE>"
pxe_subnet: "<CLUSTER_SUBNET>"
pxe_gateway: "<GATEWAY_IP>"
pxe_dns_servers: "<DNS_SERVER_1>,<DNS_SERVER_2>"

pxe_controller_ip: "<SERVICE_IP>"

pxe_k3s_server_ips:
  - "<SERVICE_IP>"

pxe_rootfs_password: ""
pxe_rootfs_authorized_keys:
  - "<SSH_PUBLIC_KEY>"

pxe_apt_mirror: "http://tw.archive.ubuntu.com/ubuntu"
pxe_k3s_data_dir: "/var/lib/rancher/k3s"
```

::::::{important}
`pxe_controller_ip` and `pxe_k3s_server_ips` are intentionally left **empty** in
the role defaults (`deploy/ansible/roles/pxe_controller/defaults/main.yml`) — no
site IP addresses ship in the repository. You **must** set them here in the
playbook `vars:` block to your own PXE controller / service host IP and your k3s
server node IP(s). The playbook runs a pre-flight assertion and **fails fast** if
either is left empty or still contains a `<...>` placeholder.
::::::

Use `pxe_rootfs_force_rebuild: true` for the first build or after changing the
rootfs package list. Set it back to `false` after the rootfs is stable to avoid
rebuilding underneath running agents.

The default rootfs packages include:

- Ubuntu 24.04 `noble`
- `linux-image-6.14.0-1018-oem`
- `linux-headers-6.14.0-1018-oem`
- `nfs-common`
- `overlayroot`
- `openssh-server`
- `dkms` and build tools
- the Realtek `r8125` 2.5GbE vendor driver, built from source bundled in the role
- `amdgpu` and NFS-related initramfs modules

::::::{warning}
Not every machine uses the same NIC. The reference AIPCs have a Realtek RTL8125
2.5GbE controller, so the example rootfs builds the Realtek `r8125` DKMS driver
from the source bundled in the role and blacklists the in-kernel `r8169` driver.

If your agents use a different NIC, or an agent gets no network during netboot
(no DHCP/PXE response, or the kernel never brings the link up), the rootfs is
most likely missing the right driver. In that case:

- Identify the NIC on the agent hardware with `lspci -nnk | grep -A3 -i net`.
- If an in-kernel module covers it, add that module name to
  `pxe_initramfs_modules` so it is present in the netboot initramfs.
- If you need a vendor driver, add its source under the role's `files/` and build
  it in `chroot-setup.sh.j2`, mirroring how the bundled `r8125` driver is built.
- Drop or adjust the `r8125` build and the `blacklist r8169` rule if they do not
  apply to your hardware.
::::::

::::::{warning}
Do not copy committed example passwords, SSH keys, GitHub OAuth values, or site
tokens into a new deployment. Replace every secret with your own private value
or keep password login disabled.
::::::

Add a `pxe_controller` group to `deploy/ansible/inventory.yml` so Ansible can
reach AIPC 1. The shipped inventory only defines the `k3s_cluster` group, so add
this block — the playbook targets `hosts: pxe_controller`, and each host entry
must be a proper YAML mapping key (note the trailing colon on `pxe:`):

```yaml
pxe_controller:
  hosts:
    pxe:
      ansible_host: <SERVICE_IP>
  vars:
    ansible_port: 22
    ansible_user: root
```

If you run Ansible locally on AIPC 1, you can also use a local inventory entry,
but the remote SSH path is easier to reproduce and audit.

## 6. Run The PXE Controller Playbook

Run the playbook:

```bash
cd ~/aup-learning-cloud/deploy/ansible
ansible-playbook -i inventory.yml playbooks/pb-pxe-controller.yml
```

The playbook builds `/srv/nfs/rootfs`, installs the agent services into that
rootfs, copies kernel and initrd files to `/srv/tftp`, configures NFS, configures
`dnsmasq` Proxy-DHCP and TFTP, and prepares Apache to serve `/k3s/`.

::::::{note}
When the playbook finishes it prints a summary with a short "Next steps" list.
Continue with the manual K3s server install in step 7 and the token publishing
in step 8.
::::::

Verify the services and boot files on AIPC 1:

```bash
systemctl is-active dnsmasq
systemctl is-active nfs-kernel-server
systemctl is-active apache2
showmount -e localhost
ls -l /srv/tftp/pxelinux.0 /srv/tftp/grubnetx64.efi /srv/tftp/vmlinuz /srv/tftp/initrd.img
curl -I http://127.0.0.1/k3s/
```

Expected results:

- `dnsmasq`, `nfs-kernel-server`, and `apache2` are active
- `/srv/nfs/rootfs` is exported to `<CLUSTER_SUBNET>`
- BIOS and UEFI boot files exist under `/srv/tftp`
- `http://127.0.0.1/k3s/` returns `403` (the directory exists but is empty and not
  listable) or `200`

The playbook creates the `/k3s/` directory but does not place any files in it yet,
so `http://127.0.0.1/k3s/token` returns `404` until you publish the token and
kubeconfig in step 8 (*Publish K3s Credentials For PXE Agents*).

The generated PXE boot menus use this rootfs pattern:

```text
root=/dev/nfs nfsroot=<SERVICE_IP>:/srv/nfs/rootfs,ro,vers=3 ip=dhcp rootdelay=10 rw
```

## 7. Install The K3s Server

Install a single-node K3s server on AIPC 1. HA mode is not used in this
three-AIPC deployment.

Pin a specific K3s version and use the same version on the server and every agent.
This guide uses `v1.32.3+k3s1`, which matches the version pinned in
`deploy/ansible/inventory.yml` and `auplc_installer/k3s.py`.

```bash
curl -sfL https://get.k3s.io | \
  INSTALL_K3S_VERSION="v1.32.3+k3s1" \
  sh -s - server \
    --node-name "<SERVICE_NODE_NAME>" \
    --write-kubeconfig-mode 644
```

::::::{warning}
K3s requires every agent to be the **same version as, or older than, the server**.
The netboot rootfs currently installs the *latest* K3s agent at build time (the
`curl ... | sh -s - agent` line in `chroot-setup.sh.j2` has no version pin), so a
freshly built agent can be newer than a pinned server and then fail to join. Keep
them aligned: either add `INSTALL_K3S_VERSION="v1.32.3+k3s1"` to that agent install
line in `chroot-setup.sh.j2`, or install the server without a pin so both use the
latest.
::::::

Wait for the server:

```bash
sudo k3s kubectl get nodes -o wide
sudo systemctl status k3s --no-pager
```

Configure local `kubectl` access for the operator user:

```bash
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown "$(id -u):$(id -g)" ~/.kube/config
sed -i "s#https://127.0.0.1:6443#https://<SERVICE_IP>:6443#g" ~/.kube/config
kubectl get nodes -o wide
```

## 8. Publish K3s Credentials For PXE Agents

The netboot agents do not have static files baked into their rootfs. At boot,
`k3s-auto-join.sh` fetches:

- `http://<SERVICE_IP>/k3s/token`
- `http://<SERVICE_IP>/k3s/kubeconfig`

Publish the token and a sanitized kubeconfig through Apache:

```bash
sudo install -d -m 0755 /var/www/html/k3s

sudo install -m 0644 \
  /var/lib/rancher/k3s/server/node-token \
  /var/www/html/k3s/token

sudo sed "s#https://127.0.0.1:6443#https://<SERVICE_IP>:6443#g" \
  /etc/rancher/k3s/k3s.yaml | sudo tee /var/www/html/k3s/kubeconfig >/dev/null

sudo chmod 0644 /var/www/html/k3s/token /var/www/html/k3s/kubeconfig
sudo systemctl reload apache2
```

Verify from AIPC 1:

```bash
curl -fsS http://127.0.0.1/k3s/token >/dev/null
curl -fsS http://127.0.0.1/k3s/kubeconfig >/dev/null
```

Verify from the deployment subnet when possible:

```bash
curl -fsS http://<SERVICE_IP>/k3s/token >/dev/null
curl -kfsS https://<SERVICE_IP>:6443/ping
```

The Apache ACL generated by the role allows `<CLUSTER_SUBNET>` and localhost.
If a client cannot fetch the token, check the subnet value in
`pxe_subnet` and the generated Apache config.

## 9. Configure AIPC 2 And AIPC 3 For Netboot

On each agent machine:

1. Connect the machine to the same LAN as AIPC 1.
2. Confirm the LAN DHCP service gives it an address in `<CLUSTER_SUBNET>`.
3. Enter firmware setup.
4. Disable Secure Boot. The UEFI path boots GRUB directly without a
   Microsoft-signed shim, so it may not load while Secure Boot is enabled.
5. Enable network boot.
6. Put PXE network boot before local disk in the boot order.
7. Use BIOS PXE or UEFI PXE; the role generates menus for both.
8. Save settings and boot.

The default menu entry is `Diskless Boot (NFS root + overlayfs)`. After boot,
the agent should:

- mount `/srv/nfs/rootfs` from AIPC 1
- set hostname to `agent-<MAC>`
- mount its local K3s persistence disk
- fetch K3s token and kubeconfig from AIPC 1
- start `k3s-agent`
- join the K3s server

Watch node registration from AIPC 1:

```bash
watch kubectl get nodes -o wide
```

After both agents join, record their generated names:

```bash
kubectl get nodes -o custom-columns='NAME:.metadata.name,INTERNAL-IP:.status.addresses[?(@.type=="InternalIP")].address,OS:.status.nodeInfo.osImage,KERNEL:.status.nodeInfo.kernelVersion'
```

Expected result:

- one service node is `Ready`
- two `agent-<MAC>` nodes are `Ready`
- agent kernel version matches the OEM kernel used in the PXE rootfs

## 10. Validate Agent Persistence

Reboot one agent and confirm it rejoins with the same node identity:

```bash
kubectl get nodes -o wide
kubectl describe node <AGENT_NODE_NAME> | grep -E 'Name:|InternalIP|Kernel Version'
```

On the agent, confirm the persistent K3s data mount exists:

```bash
mount | grep /var/lib/rancher/k3s
test -f /var/lib/rancher/k3s/node-password
systemctl status mount-local-disk --no-pager
systemctl status k3s-agent --no-pager
```

If the agent reboots but cannot rejoin, inspect:

```bash
journalctl -u mount-local-disk -n 100 --no-pager
journalctl -u k3s-auto-join -n 100 --no-pager
journalctl -u k3s-agent -n 100 --no-pager
```

If a stale node object blocks rejoin during testing, remove the Kubernetes node
object and reboot the agent:

```bash
kubectl delete node <AGENT_NODE_NAME>
```

Do not use this as a normal operating procedure. Stable local persistence is the
expected path.

## 11. Install AMD GPU Device Plugin And Labeller

Deploy the AMD GPU device plugin and ROCm node labeller:

```bash
kubectl create -f https://raw.githubusercontent.com/ROCm/k8s-device-plugin/master/k8s-ds-amdgpu-dp.yaml
kubectl create -f https://raw.githubusercontent.com/ROCm/k8s-device-plugin/master/k8s-ds-amdgpu-labeller.yaml
```

Verify GPU resources and labels:

```bash
kubectl get nodes
kubectl describe node <AGENT_NODE_NAME> | grep amd.com/gpu
kubectl get pods -A | grep -i amd
```

Use the labels that actually appear on your agents when editing
`runtime/values-multi-nodes.yaml`. Common label keys include:

- `amd.com/gpu.product-name`
- `amd.com/gpu.family`
- `amd.com/gpu.vram`
- `amd.com/gpu.cu-count`
- `amd.com/gpu.device-id`

::::::{note}
Some basic example branch values and README text refer to a custom `gfx-target` label.
If your selected values file uses `gfx-target`, either change the selectors to
the real ROCm labeller keys or apply a consistent manual label, for example:

```bash
kubectl label node <AGENT_NODE_NAME> gfx-target=gfx1151 --overwrite
```

Keep the chart values and the node labels aligned. A mismatch leaves GPU
notebook pods in `Pending`.
::::::

## 12. Prepare Shared NFS Storage

The PXE NFS rootfs is not the notebook storage backend. Create a separate NFS
export for Kubernetes PVCs. It can run on AIPC 1 for a small lab deployment.

On the NFS server:

```bash
sudo mkdir -p <NFS_EXPORT>
sudo chown -R nobody:nogroup <NFS_EXPORT>
sudo chmod 0777 <NFS_EXPORT>
echo "<NFS_EXPORT> <CLUSTER_SUBNET>(rw,sync,no_subtree_check,no_root_squash,insecure)" | \
  sudo tee /etc/exports.d/auplc.conf
sudo exportfs -ra
sudo systemctl restart nfs-kernel-server
showmount -e localhost
```

Create local Helm values for the NFS provisioner:

```bash
cd ~/aup-learning-cloud
cp deploy/k8s/nfs-provisioner/values.yaml deploy/k8s/nfs-provisioner/values.local.yaml
nano deploy/k8s/nfs-provisioner/values.local.yaml
```

Set:

```yaml
nfs:
  server: <NFS_SERVER_IP>
  path: "<NFS_EXPORT>"

storageClass:
  name: nfs-client
  defaultClass: true
  onDelete: retain
  pathPattern: "/${.PVC.namespace}-${.PVC.name}"
```

Install the provisioner:

```bash
helm repo add nfs-subdir-external-provisioner https://kubernetes-sigs.github.io/nfs-subdir-external-provisioner/
helm repo update
helm upgrade --install nfs-subdir-external-provisioner \
  nfs-subdir-external-provisioner/nfs-subdir-external-provisioner \
  --namespace nfs-provisioner \
  --create-namespace \
  -f deploy/k8s/nfs-provisioner/values.local.yaml
```

Verify:

```bash
kubectl get storageclass
kubectl get pods -n nfs-provisioner
kubectl get pvc -A
```

## 13. Prepare JupyterHub Values

Create a deployment-specific values file:

```bash
cd ~/aup-learning-cloud/runtime
cp values-multi-nodes.yaml.example values-basic-example.yaml
nano values-basic-example.yaml
```

At minimum, set:

```yaml
custom:
  authMode: "dummy"
  githubOrgName: "<YOUR_ORG_OR_PLACEHOLDER>"
  accelerators:
    strix-halo:
      nodeSelector:
        amd.com/gpu.product-name: "<GPU_PRODUCT_LABEL>"
      quotaRate: 3
  resources:
    images:
      cpu: "<CPU_NOTEBOOK_IMAGE>"
      gpu: "<GPU_NOTEBOOK_IMAGE>"

hub:
  db:
    pvc:
      storageClassName: nfs-client
  image:
    name: "<HUB_IMAGE_NAME>"
    tag: "<HUB_IMAGE_TAG>"
    pullPolicy: IfNotPresent

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

For a private registry, create the pull secret before installing the chart:

```bash
kubectl create namespace jupyterhub
kubectl -n jupyterhub create secret docker-registry github-registry-secret \
  --docker-server=<REGISTRY_HOST> \
  --docker-username=<REGISTRY_USER> \
  --docker-password=<REGISTRY_TOKEN> \
  --docker-email=<REGISTRY_EMAIL>
```

If you use public images for a local validation deployment, remove or adjust
`imagePullSecrets` and `pullSecrets` in the values file.

::::::{warning}
Do not use any site-specific values override as-is for a new deployment. It may
contain real hostnames, OAuth settings, image tags, or other
environment-specific values that must be sanitized or replaced.
::::::

## 14. Deploy AUP Learning Cloud

Install or upgrade the chart:

```bash
cd ~/aup-learning-cloud
helm upgrade --install jupyterhub ./runtime/chart \
  --namespace jupyterhub \
  --create-namespace \
  -f runtime/values.yaml \
  -f runtime/values-basic-example.yaml
```

Wait for the deployment:

```bash
kubectl get pods -n jupyterhub -o wide
kubectl get svc -n jupyterhub
kubectl get pvc -n jupyterhub
```

For the NodePort example, open:

```text
http://<SERVICE_IP>:30890
```

If you use ingress instead of NodePort, configure `ingress.hosts`,
`ingress.tls`, DNS, and certificates in `values-basic-example.yaml`.

## 15. End-To-End Validation

Validate infrastructure first:

```bash
kubectl get nodes -o wide
kubectl get pods -A
kubectl get storageclass
kubectl get pvc -A
kubectl describe node <AGENT_NODE_NAME> | grep amd.com/gpu
```

Expected result:

- AIPC 1 and both netbooted agents are `Ready`
- no platform pod is unexpectedly stuck in `CrashLoopBackOff`, `Pending`, or
  `ImagePullBackOff`
- `nfs-client` exists
- JupyterHub PVCs bind
- AMD GPU resources or labels appear on the agent nodes

Validate from the user path:

1. Open the Hub URL.
2. Log in with the configured authentication mode.
3. Spawn a CPU notebook.
4. Create a file in the notebook home directory.
5. Stop and restart the notebook.
6. Confirm the file persists.
7. Spawn a GPU notebook.
8. Confirm the notebook pod lands on one of the netbooted agents.

Useful scheduling checks:

```bash
kubectl get pods -n jupyterhub -o wide
kubectl describe pod <USER_POD_NAME> -n jupyterhub
```

## 16. Troubleshooting

| Symptom | Likely Cause | First Checks |
|---------|--------------|--------------|
| Agent never shows PXE menu | Firmware boot order, network boot disabled, VLAN mismatch, or Proxy-DHCP not reaching client | Check firmware, switch port, `systemctl status dnsmasq`, and `journalctl -u dnsmasq` |
| Agent gets IP but cannot load boot files | TFTP blocked, missing files, or UEFI Secure Boot still enabled | Check `/srv/tftp`, firewall rules, that Secure Boot is disabled, and `dnsmasq` logs |
| Agent kernel boots but cannot mount rootfs | NFS export, subnet ACL, wrong `pxe_controller_ip`, or network driver issue | Check `showmount -e <SERVICE_IP>`, `/etc/exports`, and rootfs kernel args |
| RTL8125 NIC is unstable | Wrong driver or `r8169` claiming the device | Confirm `r8125` DKMS build and `blacklist-r8169.conf` in the rootfs |
| Agent waits for K3s token | Token not published or Apache ACL blocks the client subnet | Check `curl http://<SERVICE_IP>/k3s/token` and Apache config |
| Agent joins once but fails after reboot | Missing local K3s persistence or lost node password | Check `mount-local-disk`, `/var/lib/rancher/k3s/node-password`, and `k3s-agent` logs |
| Node is Ready but has no GPU labels | Device plugin/labeller not running, GPU not exposed, or unsupported kernel path | Check `kubectl get pods -A | grep -i amd` and `kubectl describe node` |
| GPU notebook remains Pending | Chart nodeSelector does not match real labels or GPU resources are exhausted | Check `kubectl describe pod <pod> -n jupyterhub` |
| PVC remains Pending | StorageClass name mismatch or NFS provisioner cannot mount export | Check `kubectl get storageclass`, provisioner logs, and NFS export |
| Hub image pull fails | Registry secret, image tag, or network path mismatch | Check `kubectl describe pod` and the configured image names |

## 17. Out Of Scope For The Minimal Guide

The following components are useful for a longer-running site, but they are not
required for the minimal three-AIPC deployment:

- Zot registry mirror
- Cloudflare Tunnel
- WARP egress proxy
- monitoring and Grafana
- HA K3s
- external databases
- NPU-specific setup

Add these only after the minimal deployment can boot both agents, schedule GPU
notebooks, and persist notebook storage successfully.

<!--
TODO (future docs): the components listed above (Zot registry mirror, Cloudflare
Tunnel, WARP egress proxy, monitoring and Grafana, HA K3s, external databases,
NPU-specific setup) are intentionally out of scope for this minimal guide. This
is the place to add their step-by-step configuration tutorials when they are
ready to be documented — left for whoever extends this guide next.
-->
