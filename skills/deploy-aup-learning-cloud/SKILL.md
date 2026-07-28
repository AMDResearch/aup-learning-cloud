---
name: deploy-aup-learning-cloud
description: >-
  Group: Plan and deploy AUP Learning Cloud. Use when the user wants to install
  the multi-node JupyterHub-on-k3s platform on physical hardware through either
  PXE-diskless or SSH-preinstalled nodes. Do not use for the single-node
  ./auplc-installer flow, notebook image builds, or unrelated JupyterHub and
  k3s installations.
---

# Deploy AUP Learning Cloud

Stand up a multi-node AUP Learning Cloud cluster with Ansible, AMD GPU access,
shared storage, and the JupyterHub Helm chart.

Use [deploy/README.md](../../deploy/README.md) as the source of truth for the
generator schema, commands, generated files, validation, and troubleshooting.
This skill defines the interview and safety gates around that procedure.

## Prerequisites

- A checkout of `aup-learning-cloud` on the operator machine.
- Ubuntu 24.04, a reserved controller IP, internet access, and Ansible.
- Physical node, network, storage, and authentication details from the user.
- Passwordless root SSH to every managed host in the SSH topology.

Site values and secrets don't ship in the repository. Generate them locally
and never put tokens, private keys, or credentials in tracked files.

## Phase 1: Interview

Ask for an explicit topology choice before collecting other details or touching
machines. Never infer the choice from the hardware.

| Choice | Use when |
| --- | --- |
| **PXE Diskless Netboot** (`pxe-diskless`) | A controller netboots diskless agents. |
| **Multi Node SSH Installation** (`ssh-preinstalled`) | Every node already runs Ubuntu and accepts root SSH. |

Then collect and confirm:

1. Courses and notebook resources.
2. Controller hostname, static IP, subnet, gateway, and DNS.
3. For SSH, every managed hostname and IP. Don't ask for a GPU host list or a
   shared GPU group ID. Generation discovers both over SSH.
4. For PXE, the controller NIC, web port, rootfs SSH public key, and whether
   diskless agents have AMD GPUs. This explicit yes or no is the sole PXE GPU
   policy input because agent hardware can't be inferred from the controller.
5. Shared storage location and the Hub access method.

Confirm detected GPU product labels before mapping them to accelerator keys in
the runtime values.

## Phase 2: Generate

Create a fresh schema and fill only its current fields. Run the generator rather
than writing inventory or GPU policy by hand.

For SSH, generation performs read-only discovery on every managed host and
publishes canonical artifacts only after GPU evidence and group IDs agree.

For PXE with GPU agents, initial generation creates private bootstrap inventory
and vars. Run the PXE controller playbook with those private files. A successful
rootfs build finalizes generation automatically and publishes the canonical
inventory, PXE vars, runtime overlay, and GPU resolution report.

Follow the exact generation, installation, and playbook commands in
[deploy/README.md](../../deploy/README.md). Don't invent a separate completion
step.

## Phase 3: Validate and execute

Install the canonical generated inventory and runtime overlay into the checkout,
then run the validator with the arguments shown in the deployment guide:

- `--repo`
- `--topology`
- `--inventory`
- `--gpu-resolution`
- both `--values` files
- `--pxe-vars` for PXE only

Stop on validation failure. After a clean result, follow the topology's Ansible,
storage, device plugin, and Helm sequence in
[deploy/README.md](../../deploy/README.md).

## Phase 4: Verify

Check that all expected nodes are Ready, the GPU labels and allocatable resources
match the generated policy, the storage class is available, and JupyterHub pods
are healthy. Open the Hub, start a CPU notebook, verify persistence, then start a
GPU notebook and confirm it schedules on a GPU node.

## Safety

Pause for explicit user confirmation before rebuilding a PXE rootfs, changing
NFS exports, changing firmware boot settings, resetting a cluster, deleting a
node, or uninstalling a Helm release.

Never commit or push deployment secrets. Preserve the four AUP Learning Cloud
attribution layers described in the project `AGENTS.md` if Hub or chart sources
are changed.

## Reference

- [Deployment commands and troubleshooting](../../deploy/README.md)
- [Skill-specific summary](reference.md)
