# Helper scripts

These dependency-light helpers support the multi-node deployment skill. This
file is the source of truth for the complete skill command sequences: artifact
generation and installation, validation, Ansible, device plugin readiness, and
Helm. For human direct-edit deployment, operational background, and
troubleshooting, see [deploy/README.md](../../../deploy/README.md).

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

Generation resolves every host to `true` or `false`; it never writes `auto`.
Generated inventory and GPU resolution entries are strict booleans so their
consistency can be checked.

Generate specs from fresh `--print-schema` output. Both topologies write their
canonical artifacts immediately. For PXE, review and validate those files, then
run the controller playbook with the generated `inventory.yml` and
`pb-pxe-controller.vars.yml`. The files express desired inputs; their existence
does not prove the PXE rootfs was provisioned successfully.

## SSH-preinstalled commands

Run these commands from a clean checkout. Fill the generated `spec.json` with
the SSH topology, network settings, and every managed host. Don't add a GPU host
list. The generator discovers GPU policy over passwordless root SSH.

```bash
cd /path/to/aup-learning-cloud
REPO_ROOT="$(pwd)"
DEPLOY_SCRIPTS="$REPO_ROOT/skills/deploy-aup-learning-cloud/scripts"
python3 "$DEPLOY_SCRIPTS/gen_configs.py" --print-schema > spec.json
# Edit spec.json: choose ssh-preinstalled and fill the node and network fields.
GENERATED_DIR="$REPO_ROOT/generated"
python3 "$DEPLOY_SCRIPTS/gen_configs.py" --spec spec.json --out-dir "$GENERATED_DIR"

install -m 0600 "$GENERATED_DIR/inventory.yml" "$REPO_ROOT/deploy/ansible/inventory.yml"
install -m 0644 "$GENERATED_DIR/values-basic-example.yaml" "$REPO_ROOT/runtime/values-basic-example.yaml"

python3 "$DEPLOY_SCRIPTS/validate.py" --repo "$REPO_ROOT" --topology ssh-preinstalled \
  --inventory "$REPO_ROOT/deploy/ansible/inventory.yml" \
  --gpu-resolution "$GENERATED_DIR/gpu-access-resolution.json" \
  --values "$REPO_ROOT/runtime/values.yaml" \
  --values "$REPO_ROOT/runtime/values-basic-example.yaml"
```

After validation passes, run Ansible, check the infrastructure-owned GPU
components, and install the chart with the generated overlay:

```bash
cd "$REPO_ROOT/deploy/ansible"
sudo ansible-playbook -i inventory.yml playbooks/pb-base.yml
sudo ansible-playbook -i inventory.yml playbooks/pb-k3s-site.yml
sudo ansible-playbook -i inventory.yml playbooks/pb-rocm.yml

kubectl rollout status -n kube-system daemonset/amdgpu-device-plugin-daemonset --timeout=5m
kubectl rollout status -n kube-system daemonset/amdgpu-labeller-daemonset --timeout=5m
kubectl get nodes -o 'custom-columns=NAME:.metadata.name,AMD_GPU:.status.allocatable.amd\.com/gpu'

cd "$REPO_ROOT"
helm upgrade --install jupyterhub ./runtime/chart \
  --namespace jupyterhub --create-namespace \
  -f runtime/values.yaml \
  -f runtime/values-basic-example.yaml
```

## PXE-diskless commands

Fill the generated `spec.json` with the PXE topology and all controller,
network, and rootfs fields. Set `pxe.diskless_agents_have_amd_gpus` explicitly.

```bash
cd /path/to/aup-learning-cloud
REPO_ROOT="$(pwd)"
DEPLOY_SCRIPTS="$REPO_ROOT/skills/deploy-aup-learning-cloud/scripts"
python3 "$DEPLOY_SCRIPTS/gen_configs.py" --print-schema > spec.json
# Edit spec.json: choose pxe-diskless and fill the node, network, and PXE fields.
GENERATED_DIR="$REPO_ROOT/generated"
python3 "$DEPLOY_SCRIPTS/gen_configs.py" --spec spec.json --out-dir "$GENERATED_DIR"

install -m 0600 "$GENERATED_DIR/inventory.yml" "$REPO_ROOT/deploy/ansible/inventory.yml"
install -m 0644 "$GENERATED_DIR/values-basic-example.yaml" "$REPO_ROOT/runtime/values-basic-example.yaml"

python3 "$DEPLOY_SCRIPTS/validate.py" --repo "$REPO_ROOT" --topology pxe-diskless \
  --inventory "$REPO_ROOT/deploy/ansible/inventory.yml" \
  --gpu-resolution "$GENERATED_DIR/gpu-access-resolution.json" \
  --values "$REPO_ROOT/runtime/values.yaml" \
  --values "$REPO_ROOT/runtime/values-basic-example.yaml" \
  --pxe-vars "$GENERATED_DIR/pb-pxe-controller.vars.yml"

cd "$REPO_ROOT/deploy/ansible"
sudo ansible-playbook \
  -i "$GENERATED_DIR/inventory.yml" \
  playbooks/pb-pxe-controller.yml \
  -e @"$GENERATED_DIR/pb-pxe-controller.vars.yml"

kubectl rollout status -n kube-system daemonset/amdgpu-device-plugin-daemonset --timeout=5m
kubectl rollout status -n kube-system daemonset/amdgpu-labeller-daemonset --timeout=5m
kubectl get nodes -o 'custom-columns=NAME:.metadata.name,AMD_GPU:.status.allocatable.amd\.com/gpu'

cd "$REPO_ROOT"
helm upgrade --install jupyterhub ./runtime/chart \
  --namespace jupyterhub --create-namespace \
  -f runtime/values.yaml \
  -f runtime/values-basic-example.yaml
```

The controller playbook must finish successfully before the remaining cluster
and Helm steps begin. A fresh rootfs receives the pinned GPU access package. A
retained rootfs must pass the package version, package-owned rule, and legacy
rule safety checks described in the deployment guide.

## Validator contract

The exact topology commands above pass `--repo`, `--topology`, `--inventory`,
`--gpu-resolution`, two `--values` arguments, and `--pxe-vars` for PXE only.
For direct validation, `--inventory` alone accepts exactly one unquoted `auto`,
`true`, or `false` value for `auplc_gpu_access_enabled` on every managed host.
`--gpu-resolution` requires `--inventory`; supplying both switches to generated
consistency validation, where inventory and resolution values must be strict
booleans. The generator-first skill workflow supplies both and never generates
`auto`.

## Conventions

- Detection data goes to stdout as JSON. Diagnostics go to stderr.
- Exit code `0` means success, `1` means validation failed, and `2` means usage
  or required tooling is wrong.
- Generated secrets stay off stdout and out of version control.
- Python helpers use the standard library only.
