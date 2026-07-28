# Deploy AUP Learning Cloud Reference

The authoritative procedure, command lines, generated file list, and failure
guidance live in [deploy/README.md](../../deploy/README.md). Don't copy those
commands into this reference.

## Topology contract

| Topology | Generator behavior |
| --- | --- |
| `ssh-preinstalled` | Connects to every managed host, discovers GPU hardware, and publishes canonical files when discovery is consistent. |
| `pxe-diskless` | Uses `pxe.diskless_agents_have_amd_gpus` as its sole GPU policy input and publishes canonical desired-input files before the controller playbook runs. Their existence does not prove rootfs provisioning succeeded. |

Don't hand-author generated GPU policy. Create deployment specs from the current
`--print-schema` output.

## Canonical validation inputs

Use the validator command from [deploy/README.md](../../deploy/README.md). It
passes:

- repository root with `--repo`
- selected topology with `--topology`
- installed inventory with `--inventory`
- generated GPU resolution report with `--gpu-resolution`
- base and generated overlays as two `--values` arguments
- canonical PXE vars with `--pxe-vars` for PXE only

Generation and validation must finish before Ansible or Helm changes are made.

## GPU permission contract

- Installer, Ansible, and PXE provisioning install AMD's
  `amdgpu-insecure-instinct-udev-rules` package at version
  `30.30.4.0-2341068.24.04`.
- The package sets mode `0666` only on `/dev/kfd` and DRM
  `/dev/dri/renderD*` nodes.
- The package does not change `/dev/dri/card*`. Card nodes retain normal system
  policy, observed as `root:video 0660`.
- AUPLC Hub adds no GPU supplemental group. No GPU group is required for the
  tested ROCm compute path.
- AMD device-plugin allocation is the visibility boundary. Only Pods requesting
  `amd.com/gpu` receive GPU device nodes; the plugin does not change host inode
  ownership or mode.
- `singleuser.fsGid: 100` controls shared storage ownership only.

Operator evidence from SHC showed `rocminfo` reporting `gfx1151` and `gfx1200`
on the two GPU nodes from UID `12345` Pods with only supplemental GID `100`.
Their `card*` nodes remained inaccessible at mode `0660`.

The infrastructure owner deploys and maintains the AMD device plugin and ROCm
node labeller outside AUPLC. Before Helm, use the readiness and capacity checks
in [deploy/README.md](../../deploy/README.md); do not install these privileged
components as part of the AUPLC procedure.

## Operator gates

Keep the topology choice explicit. Confirm network, node, storage, course, and
access details with the user. For PXE, also confirm the GPU-agent boolean and a
rootfs SSH public key. For SSH, verify passwordless root access to every managed
host.

Require confirmation before rootfs rebuilds, NFS export changes, firmware boot
changes, cluster resets, node deletion, or Helm uninstall. Keep generated
secrets out of version control.
