# Helper scripts

Deterministic helpers the deploy skill runs instead of generating commands ad
hoc. They are dependency-light (`bash` + `python3`, plus the obvious system
tools) and agent-agnostic, and follow the script conventions in
[../../../CONTRIBUTING.md](../../../CONTRIBUTING.md). Each emits JSON or a clear
report and uses exit codes the agent can branch on.

| Script | Run when | What it does |
| --- | --- | --- |
| `detect_hardware.sh` | Phase 2, on the service machine | Detects the default-route NIC, IPv4 + subnet CIDR, gateway, DNS servers, and AMD GPUs (`lspci`, vendor `1002`) with their kernel driver. Emits JSON for filling PXE / network vars. Read-only. |
| `detect_cluster.sh` | After k3s + the device plugin are up | `kubectl get` of nodes, real `amd.com/gpu.*` labels, storage classes, and whether the ROCm device plugin + labeller DaemonSets are running. Emits JSON. Read-only. |
| `gen_configs.py` | Phase 3 | From a small cluster-spec (`--print-schema`), writes `inventory.yml`, `pb-pxe-controller.vars.yml` (PXE only), and `values-basic-example.yaml`. Generates the k3s token locally with `secrets` (never printed), `chmod 600` on the inventory, and pins `pxe_k3s_version == k3s_version`. |
| `validate.py` | Before each `ansible-playbook` / `helm` run | For `pxe-diskless`, checks required PXE vars and `k3s_version == pxe_k3s_version`; for both topologies, checks GPU labels only for active resource `acceleratorKeys` (when given `detect_cluster.sh` output), and optionally runs a `helm template` dry-run. Exit 1 on any failure. |

## Quick reference

From any directory in a checkout, resolve helpers with:

```bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
DEPLOY_SCRIPTS="$REPO_ROOT/skills/deploy-aup-learning-cloud/scripts"
```

For an installed plugin, set `DEPLOY_SKILL_DIR` to the absolute directory
containing the loaded `SKILL.md`, then use:

```bash
DEPLOY_SKILL_DIR="/absolute/path/to/deploy-aup-learning-cloud"
DEPLOY_SCRIPTS="$DEPLOY_SKILL_DIR/scripts"
```

```bash
# Phase 2 — discover the host
"$DEPLOY_SCRIPTS/detect_hardware.sh"                 # JSON: nic, ip, subnet_cidr, gateway, dns, gpus[]

# Phase 3 — generate config from a spec
python3 "$DEPLOY_SCRIPTS/gen_configs.py" --print-schema > spec.json   # then edit spec.json
GENERATED_DIR="$REPO_ROOT/generated"
python3 "$DEPLOY_SCRIPTS/gen_configs.py" --spec spec.json --out-dir "$GENERATED_DIR"
install -m 0600 "$GENERATED_DIR/inventory.yml" "$REPO_ROOT/deploy/ansible/inventory.yml"
install -m 0644 "$GENERATED_DIR/values-basic-example.yaml" "$REPO_ROOT/runtime/values-basic-example.yaml"
# PXE only: keep the generated secret in place and resolve its absolute path.
PXE_VARS="$(realpath "$GENERATED_DIR/pb-pxe-controller.vars.yml")"
chmod 0600 "$PXE_VARS"
cd "$REPO_ROOT/deploy/ansible"
ansible-playbook -i inventory.yml playbooks/pb-pxe-controller.yml -e @"$PXE_VARS"

# Phase 5 — after k3s + device plugin are up
"$DEPLOY_SCRIPTS/detect_cluster.sh" > cluster.json   # JSON: nodes[], gpu_product_names[], storage_classes[]

# Before running playbooks / helm (set to the selected topology)
DEPLOY_TOPOLOGY=pxe-diskless
python3 "$DEPLOY_SCRIPTS/validate.py" --repo "$REPO_ROOT" --topology "$DEPLOY_TOPOLOGY" \
  --values runtime/values.yaml --values runtime/values-basic-example.yaml \
  --pxe-vars "$PXE_VARS" --cluster cluster.json --helm-dry-run
```

Omit `--pxe-vars "$PXE_VARS"` for `ssh-preinstalled`. For `pxe-diskless`, the
validator and Ansible must receive the same generated file.

Generated `gpu.acceleratorKeys` wires the selected accelerators to the generic
GPU resource. Use `configure-aup-learning-cloud-courses` to wire course
resources separately.

## Conventions

- **JSON to stdout, diagnostics to stderr.** `detect_*.sh` always print a JSON
  object; partial detection is reported via empty fields + a `warnings` array
  rather than failing, so the agent can decide what to ask the operator.
- **Exit codes mean something.** `0` success (warnings allowed), `1` a real
  validation failure, `2` a usage / missing-tooling error.
- **Secrets never touch stdout or VCS.** `gen_configs.py` mints the k3s token
  with a CSPRNG, writes it only into `inventory.yml`, and `chmod 600`s it.
- **No third-party Python.** `gen_configs.py` / `validate.py` use the stdlib
  only (no PyYAML), so they run on a bare operator machine. YAML is emitted
  from templates and parsed with targeted scanning.
