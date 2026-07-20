---
name: deploy-aup-learning-cloud
description: >-
  Group: Plan & deploy AUP Learning Cloud. Deploys AUP Learning Cloud (a
  multi-node JupyterHub-on-k3s platform for AMD
  GPUs) onto physical hardware end to end. Use when the user wants to install,
  deploy, set up, or stand up AUP Learning Cloud, AUPLC, or "the learning
  cloud" on a cluster; mentions a multi-AIPC or 3-node mini-cluster, PXE /
  netboot / diskless agents, the Ansible inventory.yml, pb-pxe-controller,
  pb-k3s-site, the ROCm GPU device plugin/labeller, an NFS provisioner, or a
  JupyterHub values.yaml / Helm chart for this project. Covers both the
  PXE-diskless topology and the SSH-preinstalled multi-node topology. Do not
  use for the single-node "./auplc-installer install" flow, for building
  notebook images, or for non-AUPLC JupyterHub or k3s installs.
---

# Deploy AUP Learning Cloud

Stand up AUP Learning Cloud on a multi-node k3s cluster: build the cluster with
Ansible, expose AMD GPUs, provide shared storage, and deploy the JupyterHub
chart with Helm so users can log in and spawn GPU notebooks.

This skill is written for any coding agent. Run the commands and edit the files
as described; the full, copy-runnable command sequence and the troubleshooting
table live in **[reference.md](reference.md)**.

## Prerequisites

- A checkout of `aup-learning-cloud` on the operator/service machine.
- The service machine runs Ubuntu 24.04 with a reserved/static IP and internet
  access.
- `ansible` on the operator machine; `kubectl` and `helm` for the cluster
  (reference.md has the Helm install command).
- For GPU scheduling: AMD GPU nodes with a working in-kernel NIC driver.
- The user supplies the physical hardware. **No site values (IPs, subnet, SSH
  keys, tokens) ship in the repo** — this skill generates them.

## Helper script paths

Resolve the deploy helpers before running the commands below. From any directory
in an AUP Learning Cloud checkout:

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
DEPLOY_SCRIPTS="$REPO_ROOT/skills/deploy-aup-learning-cloud/scripts"
```

When this skill is installed as a plugin rather than used from a checkout, set
`DEPLOY_SKILL_DIR` to the absolute directory containing the loaded `SKILL.md`,
then derive the helpers from that directory:

```bash
DEPLOY_SKILL_DIR="/absolute/path/to/deploy-aup-learning-cloud"
DEPLOY_SCRIPTS="$DEPLOY_SKILL_DIR/scripts"
```

## Phase 1 — Interview

Work through this in order. **The deployment-method choice (1a) is a hard gate:
ask it first and get an explicit answer before collecting anything else or
touching the machines.**

### Phase 1a — Choose the deployment method (ask first, always)

Ask the user to pick one. **Never assume or auto-select** — even when the
machines "look like" one case, present both options and let the user decide (you
may recommend, but you still need an explicit choice before continuing):

| Choose | When |
| --- | --- |
| **PXE Diskless Netboot** (`topology: pxe-diskless`) — one service machine netboots diskless agents | Agents have no OS installed; you want zero per-machine install; small teaching lab. This is the [3-node mini-cluster guide](https://amdresearch.github.io/aup-learning-cloud/installation/multi-node/multi-aipc-hardware-deployment.html). |
| **Multi Node SSH Installation** (`topology: ssh-preinstalled`) — every node already runs Ubuntu | Each node has an OS and is reachable over SSH; closer to a long-running lab. This is the [multi-node guide](https://amdresearch.github.io/aup-learning-cloud/installation/multi-node.html). |

The value in parentheses is the `topology` field for `gen_configs.py` (Phase 3)
and selects the matching section in [reference.md](reference.md).

### Phase 1b — Collect the rest (some items branch on the choice above)

Collect, and confirm back to the user, before touching anything:

1. **Courses** wanted — drives the `values.yaml` course keys + team mappings
   (full catalog setup lives in `configure-aup-learning-cloud-courses`).
2. **Node count** and which node is the controller/server, plus its static IP.
   - *SSH path only:* also the hostname + IP of every agent node, and confirm
     passwordless root SSH already reaches each one.
3. **GPU — do not ask the user to name the model.** Let the tooling find it: the
   detectors report the GPUs (`$DEPLOY_SCRIPTS/detect_hardware.sh` in Phase 2)
   and the real ROCm `amd.com/gpu.product-name` label
   (`$DEPLOY_SCRIPTS/detect_cluster.sh` in Phase 5). Then
   **confirm the detected GPU → accelerator-key mapping with the user** before it
   goes into the values file.
4. *PXE path only:* service-machine NIC, subnet (CIDR), gateway, and DNS servers
   (also auto-detected in Phase 2 and cross-checked), plus at least one SSH
   public key for the rootfs and the apache web port.

Login mode (`custom.authMode`) is unchanged — it stays at its `auto-login`
default; switch it later with `configure-aup-learning-cloud-auth` if needed. The
detailed steps for both paths are in [reference.md](reference.md).

## Phase 2 — Discover

On the service machine, run the bundled detector and cross-check its JSON
against the Phase 1 answers:

```bash
"$DEPLOY_SCRIPTS/detect_hardware.sh"   # JSON: nic, ip, subnet_cidr, gateway, dns_servers, gpus[]
```

It reports the default-route NIC, the service-machine IP + subnet CIDR, the
gateway, DNS servers, and each AMD GPU (`lspci`, vendor `1002`) with the bound
`kernel_driver`. If a GPU's `kernel_driver` is empty, note its module for
`pxe_initramfs_modules` (PXE path only). Empty fields come back in `warnings`
so you know exactly what to ask the operator for. The detected GPUs are the
source of truth for the accelerator mapping — Phase 1 does not ask the user to
name them, so surface the detected list and confirm it with the user.

## Phase 3 — Generate config

Drive `$DEPLOY_SCRIPTS/gen_configs.py` rather than hand-writing YAML — it keeps the
three artifacts consistent, mints the k3s token locally with a CSPRNG (never
printed), `chmod 600`s the inventory, and pins `pxe_k3s_version == k3s_version`.

```bash
python3 "$DEPLOY_SCRIPTS/gen_configs.py" --print-schema > spec.json   # fill from Phase 1 + 2
GENERATED_DIR="$REPO_ROOT/generated"
python3 "$DEPLOY_SCRIPTS/gen_configs.py" --spec spec.json --out-dir "$GENERATED_DIR"
```

It writes, into `--out-dir`:

1. `inventory.yml` — `server` host + `token` + `k3s_version` (agents empty for
   PXE; listed for SSH) plus the `pxe_controller` group for PXE.
2. `pb-pxe-controller.vars.yml` — PXE path only: extra vars passed to
   `deploy/ansible/playbooks/pb-pxe-controller.yml` with `-e @<absolute-path>` (`pxe_network_interface`,
   `pxe_subnet`, `pxe_gateway`, `pxe_dns_servers`, `pxe_controller_ip`,
   `pxe_k3s_server_ips`, `pxe_k3s_version`, `pxe_web_port`,
   `pxe_rootfs_password`, `pxe_rootfs_authorized_keys`).
3. `values-basic-example.yaml` — `custom.accelerators.*.nodeSelector` (matched
   to real GPU labels in Phase 5), `custom.resources.images`, the storage class
   (`nfs-client`), `custom.authMode`, and the proxy `NodePort` (e.g. 30890).

Review the artifacts, install the inventory and runtime overlay into the
checkout, and keep the PXE vars in the generated directory.
**Never commit `inventory.yml` — it holds the token.** Field-by-field guidance
is in [reference.md](reference.md).

Map the generated artifacts into the checkout before Phase 5 validation:

```bash
install -m 0600 "$GENERATED_DIR/inventory.yml" "$REPO_ROOT/deploy/ansible/inventory.yml"
install -m 0644 "$GENERATED_DIR/values-basic-example.yaml" "$REPO_ROOT/runtime/values-basic-example.yaml"

# PXE only: keep this generated secret in place and use its absolute path.
PXE_VARS="$(realpath "$GENERATED_DIR/pb-pxe-controller.vars.yml")"
chmod 0600 "$PXE_VARS"
```

The generated `gpu.acceleratorKeys` activates the selected accelerators only
for the generic GPU resource. Wire selected accelerators into course resources
separately with `configure-aup-learning-cloud-courses`.

## Phase 4 — Execute (with confirmation gates)

Run the install in order. **Pause for explicit user confirmation before each
risky/irreversible step** (see Safety). The PXE path is, in brief:

1. Install host packages on the service machine.
2. Run `pb-pxe-controller.yml -e @"$PXE_VARS"` to build the PXE/NFS rootfs,
   then verify the
   controller (dnsmasq, NFS, apache2, TFTP boot files).
3. `pb-base.yml` + `pb-k3s-site.yml` to install the single-node k3s server.
4. Publish the k3s token + kubeconfig for agents over the apache `/k3s/` endpoint.
5. Netboot the agents; watch them auto-join with `kubectl get nodes -o wide`.

Run the PXE controller step with the generated vars file:

```bash
cd "$REPO_ROOT/deploy/ansible"
ansible-playbook -i inventory.yml playbooks/pb-pxe-controller.yml -e @"$PXE_VARS"
```

The SSH path runs `pb-base.yml`, `pb-k3s-site.yml`, and `pb-rocm.yml` against
the inventory instead. Full commands for both paths are in [reference.md](reference.md).

## Phase 5 — GPU, storage, and chart

1. Install the AMD GPU device plugin + ROCm labeller, then read the **real**
   cluster state:

   ```bash
"$DEPLOY_SCRIPTS/detect_cluster.sh" > cluster.json   # nodes[], gpu_product_names[], storage_classes[]
   ```

   Confirm the detected GPU → accelerator-key mapping with the user, then patch
   `custom.accelerators.*.nodeSelector` so each `amd.com/gpu.product-name`
   matches a value in `gpu_product_names`. Gate the install on a clean
   pre-flight (exits non-zero on any mismatch):

   ```bash
# Set this to the topology selected in Phase 1a.
DEPLOY_TOPOLOGY=pxe-diskless
python3 "$DEPLOY_SCRIPTS/validate.py" --repo "$REPO_ROOT" --topology "$DEPLOY_TOPOLOGY" \
      --values runtime/values.yaml --values runtime/values-basic-example.yaml \
      --pxe-vars "$PXE_VARS" --cluster cluster.json --helm-dry-run
```

For the PXE path, the validator and Ansible receive the same generated vars
file. Omit `--pxe-vars "$PXE_VARS"` for the SSH path.

2. Create the notebook-PVC NFS export and install the `nfs-subdir-external-provisioner`
   (storage class `nfs-client`).
3. Deploy the chart:

```bash
helm upgrade --install jupyterhub ./runtime/chart \
  --namespace jupyterhub --create-namespace \
  -f runtime/values.yaml \
  -f runtime/values-basic-example.yaml
```

## Phase 6 — Validate end to end

```bash
kubectl get nodes -o wide          # server + agents Ready
kubectl get pods -A                # nothing CrashLoopBackOff/Pending/ImagePullBackOff
kubectl get storageclass           # nfs-client present
```

Then open the Hub (NodePort example: `http://<SERVICE_IP>:30890`), log in,
spawn a CPU notebook, confirm file persistence across a restart, then spawn a
GPU notebook and confirm its pod lands on a GPU node
(`kubectl get pods -n jupyterhub -o wide`).

## Safety

These steps are destructive or hard to reverse — **stop and get explicit user
confirmation before each one**, and never run them silently:

- Building/rebuilding the PXE rootfs (`pxe_rootfs_force_rebuild: true`).
- Editing `/etc/exports` and restarting `nfs-kernel-server`.
- `kubectl delete node <name>` (debugging only).
- `helm uninstall` or a cluster reset (`pb-k3s-reset.yml`).
- Changing firmware boot order / disabling Secure Boot on agents.

Never commit or push. Never write the k3s token, OAuth secrets, or SSH private
keys into tracked files. Preserve the four AUP Learning Cloud attribution
layers (see the project `AGENTS.md`) if any chart/Hub source is touched.

## Reference

Full step-by-step commands for both topologies, the GPU-label-to-accelerator
mapping, the `values.yaml` field guide, and the troubleshooting table:
[reference.md](reference.md).
