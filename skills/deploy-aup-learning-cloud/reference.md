# Deploy AUP Learning Cloud Reference

The authoritative procedure, command lines, generated file list, and failure
guidance live in [deploy/README.md](../../deploy/README.md). Don't copy those
commands into this reference.

## Topology contract

| Topology | Generator behavior |
| --- | --- |
| `ssh-preinstalled` | Connects to every managed host, discovers GPU hosts and their shared `render` group ID, and publishes canonical files only when discovery is consistent. |
| `pxe-diskless` | Uses `pxe.diskless_agents_have_amd_gpus` as its sole GPU policy input. GPU-enabled first generation emits private bootstrap files; the PXE controller playbook finalizes canonical files after a successful rootfs build. |

Don't hand-author generated GPU policy. Old unshipped specs should be recreated
from the current `--print-schema` output.

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

## Operator gates

Keep the topology choice explicit. Confirm network, node, storage, course, and
access details with the user. For PXE, also confirm the GPU-agent boolean and a
rootfs SSH public key. For SSH, verify passwordless root access to every managed
host.

Require confirmation before rootfs rebuilds, NFS export changes, firmware boot
changes, cluster resets, node deletion, or Helm uninstall. Keep generated
secrets out of version control.
