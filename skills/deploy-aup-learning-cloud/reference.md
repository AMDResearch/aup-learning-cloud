# Deploy AUP Learning Cloud Reference

The complete generator-first command sequences and generated file list live in
the [skill scripts guide](scripts/README.md). Human direct-edit deployment,
operational background, and failure guidance live in
[deploy/README.md](../../deploy/README.md). Don't copy those commands into this
reference.

## Topology contract

| Topology | Generator behavior |
| --- | --- |
| `ssh-preinstalled` | Connects to every managed host, discovers GPU hardware, and publishes canonical files when discovery is consistent. |
| `pxe-diskless` | Uses `pxe.diskless_agents_have_amd_gpus` as its sole GPU policy input and publishes canonical desired-input files before the controller playbook runs. Their existence does not prove rootfs provisioning succeeded. |

The skill is generator-first for both topologies. Don't hand-author generated
GPU policy, including for SSH. Create deployment specs from the current
`--print-schema` output. Generation resolves hosts to strict `true` or `false`
values and never writes `auto`.

## One-release generator auth migration

`gen_configs.py` temporarily accepts `auth_mode` as a one-release compatibility
input for generator specs. It isn't a Helm value. Generated overlays always use
canonical `custom.auth` flags.

| Temporary `auth_mode` input | Generated `custom.auth` flags |
| --- | --- |
| `auto-login` | `autoLogin: true` |
| `dummy` | `dummy: true` |
| `github` | `github: true` |
| `local` | `native: true` |
| `multi` | `native: true`, `github: true` |

## Values field guide

| Field | Purpose |
| --- | --- |
| `custom.auth` | Select exactly one supported combination: auto-login, dummy, native, GitHub, or native plus GitHub. |
| `custom.runtimeLimitEnabled` | Enforce the selected session timer. Generated multi-node overlays set this to `true`. |
| `custom.quota.enabled` | Enforce credit balances. Generated multi-node overlays set this to `true`. |
| `custom.githubOrgName`, `hub.config.GitHubOAuthenticator` | Configure GitHub OAuth when GitHub is selected. |
| `custom.adminUser` | Name the Hub administrator. |
| `custom.accelerators.*.nodeSelector` | Match the AMD GPU labels found through discovery and confirmed by the user. |
| `custom.resources.images` | Define CPU, GPU, and course notebook images. |
| `custom.resources.requirements`, `custom.teams.mapping`, `custom.quota` | Define per-team resources and quotas. |
| `hub.db.pvc.storageClassName`, `singleuser.storage.dynamic.storageClass` | Select shared storage, normally `nfs-client` for multi-node deployments. |
| `proxy.service`, `ingress` | Expose the Hub through a NodePort or ingress. |

Authentication doesn't select runtime limits, quota, or resource visibility.
Every provider combination uses `custom.teams.mapping` and its existing
fallback groups to resolve visible resources.

## Canonical validation inputs

Use the topology's validator command from the
[skill scripts guide](scripts/README.md). It passes:

- repository root with `--repo`
- selected topology with `--topology`
- installed inventory with `--inventory`
- generated GPU resolution report with `--gpu-resolution`
- base and generated overlays as two `--values` arguments
- canonical PXE vars with `--pxe-vars` for PXE only

For a human direct inventory, `--inventory` alone accepts exactly one unquoted
`auto`, `true`, or `false` value for `auplc_gpu_access_enabled` on every managed
host. `--gpu-resolution` requires `--inventory`; supplying both checks generated
artifacts and requires strict booleans in the inventory and resolution report.
The skill supplies both because its workflow is generator-first. Generation and
validation must finish before Ansible or Helm changes are made.

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

Operator evidence from representative GPU nodes showed `rocminfo` reporting
`gfx1151` and `gfx1200` from UID `12345` Pods with only supplemental GID `100`.
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
