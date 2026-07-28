# Helper scripts

These dependency-light helpers support the multi-node deployment skill. See
[deploy/README.md](../../../deploy/README.md) for the authoritative command
sequence and argument paths.

| Script | Purpose |
| --- | --- |
| `detect_hardware.sh` | Reports controller network details and local AMD PCI devices as JSON. |
| `detect_cluster.sh` | Reports Kubernetes nodes, AMD GPU labels, storage classes, and GPU DaemonSet state as JSON. |
| `gen_configs.py` | Prints the current spec schema, discovers live GPU state, and directly publishes canonical topology-specific deployment artifacts. |
| `validate.py` | Checks the selected topology against canonical inventory, GPU resolution, values overlays, and PXE vars when applicable. |

## Generator contract

The SSH topology discovers GPU hosts from managed-host evidence. Users don't
provide a GPU host list. The PXE topology has one GPU policy input:
`pxe.diskless_agents_have_amd_gpus`.

Generate specs from fresh `--print-schema` output. Both topologies write their
canonical artifacts immediately. For PXE, review and validate those files, then
run the controller playbook with the generated `inventory.yml` and
`pb-pxe-controller.vars.yml`. The files express desired inputs; their existence
does not prove the PXE rootfs was provisioned successfully.

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
