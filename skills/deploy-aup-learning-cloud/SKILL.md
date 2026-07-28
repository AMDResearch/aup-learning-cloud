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

Use the [skill scripts guide](scripts/README.md) as the source of truth for the
complete generator-first command sequences and generated files. Use
[deploy/README.md](../../deploy/README.md) for the human direct-edit workflow,
operational background, and troubleshooting. This skill defines the interview
and safety gates around the generated procedure.

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
3. For SSH, every managed hostname and IP. Don't ask for a GPU host list;
   generation discovers GPU hosts over SSH.
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
publishes canonical artifacts after GPU evidence is consistent.

For PXE, generation writes the canonical inventory, PXE vars, runtime overlay,
and GPU resolution report directly as desired deployment inputs. Their existence
does not prove rootfs provisioning succeeded. Review, install, and validate those
files, then run the controller playbook with the canonical inventory and PXE
vars; the playbook must complete successfully before proceeding.

Follow the complete topology command sequence in the
[skill scripts guide](scripts/README.md). Don't substitute the human direct-edit
SSH workflow from `deploy/README.md`; the skill's SSH path remains
generator-first and discovers GPU policy from managed-host evidence.

## Phase 3: Validate and execute

Install the canonical generated inventory and runtime overlay into the checkout,
then run the topology's exact validator command from the
[skill scripts guide](scripts/README.md). The validator inputs are:

- `--repo`
- `--topology`
- `--inventory` to validate explicit host booleans
- `--gpu-resolution` with `--inventory` for generated-artifact consistency
- both `--values` files
- `--pxe-vars` for PXE only

An inventory can be validated without a GPU resolution report. A resolution
report requires an inventory. Supply both in this generator-first workflow so
the validator also checks their consistency.

Stop on validation failure. After a clean result, continue with the topology's
Ansible, device plugin, and Helm commands in the skill scripts guide. Treat the
AMD device plugin and ROCm node labeller as infrastructure prerequisites owned
outside AUPLC. Verify both existing DaemonSets and advertised GPU capacity
before Helm; do not install these privileged components as part of the AUPLC
procedure.

Keep the GPU contract distinct from storage configuration. The installer,
Ansible role, and PXE controller install AMD's
`amdgpu-insecure-instinct-udev-rules` package at the pinned version
`30.30.4.0-2341068.24.04`. Its rule sets mode `0666` only on `/dev/kfd` and DRM
`renderD*` nodes. It does not change `card*`, which retains normal system policy,
observed as `root:video 0660`.

Device-plugin allocation is a separate visibility layer. Only `amd.com/gpu`
requests receive allocated GPU devices, and the plugin does not change Unix
inode permissions. AUPLC Hub adds no GPU supplemental group; none is required
for the tested ROCm compute path. `singleuser.fsGid: 100` is for shared storage
only.

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

- [Complete skill command sequences](scripts/README.md)
- [Human deployment and troubleshooting](../../deploy/README.md)
- [Skill-specific summary](reference.md)
