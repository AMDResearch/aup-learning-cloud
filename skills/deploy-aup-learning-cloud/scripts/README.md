# Helper scripts

These dependency-light helpers support the multi-node deployment skill. See
[deploy/README.md](../../../deploy/README.md) for the authoritative command
sequence and argument paths.

| Script | Purpose |
| --- | --- |
| `detect_hardware.sh` | Reports controller network details and local AMD PCI devices as JSON. |
| `detect_cluster.sh` | Reports Kubernetes nodes, AMD GPU labels, storage classes, and GPU DaemonSet state as JSON. |
| `gen_configs.py` | Prints the current spec schema, discovers SSH GPU state, and generates topology-specific deployment artifacts. PXE GPU bootstrap files remain private until the controller playbook finalizes them automatically. |
| `validate.py` | Checks the selected topology against canonical inventory, GPU resolution, values overlays, and PXE vars when applicable. |

## Generator contract

The SSH topology discovers GPU hosts and their shared `render` group ID. Users
don't provide either value. The PXE topology has one GPU policy input:
`pxe.diskless_agents_have_amd_gpus`.

Generate specs from fresh `--print-schema` output. Don't hand-edit generated GPU
policy or add a separate PXE completion step.

## Validator contract

Use the exact validator command in
[deploy/README.md](../../../deploy/README.md). Its canonical inputs are
`--repo`, `--topology`, `--inventory`, `--gpu-resolution`, two `--values`
arguments, and `--pxe-vars` for PXE only.

## Conventions

- Detection data goes to stdout as JSON. Diagnostics go to stderr.
- Exit code `0` means success, `1` means validation failed, and `2` means usage
  or required tooling is wrong.
- Generated secrets stay off stdout and out of version control.
- Python helpers use the standard library only.
