# Configure AUP Learning Cloud courses — Reference

The course-key map, every field under `custom.resources`, the accelerator and
team blocks, and the quota knobs, as they appear in `runtime/values.yaml`.
Workflow and gates are in [SKILL.md](SKILL.md).

## Source guides

- Configuration Reference (`runtime/values.yaml`): <https://amdresearch.github.io/aup-learning-cloud/>
- Overview (resource selection, teams, quota): <https://amdresearch.github.io/aup-learning-cloud/introduction/overview.html>

The live `runtime/values.yaml` is the source of truth; verify keys against it.

## Course catalog (default keys)

| Key | Default image | HW | Notes |
| --- | --- | --- | --- |
| `cpu` | `ghcr.io/amdresearch/auplc-default:latest` | CPU | Basic Python notebook |
| `gpu` | `ghcr.io/amdresearch/auplc-base:latest` | GPU | Basic GPU notebook |
| `code-cpu` | `ghcr.io/amdresearch/auplc-code-cpu:latest` | CPU | code-server (`launchMode: code-server`) |
| `code-gpu` | `ghcr.io/amdresearch/auplc-code-gpu:latest` | GPU | code-server |
| `Course-CV` | `ghcr.io/amdresearch/auplc-cv:latest` | GPU | Computer Vision |
| `Course-DL` | `ghcr.io/amdresearch/auplc-dl:latest` | GPU | Deep Learning |
| `Course-LLM` | `ghcr.io/amdresearch/auplc-llm:latest` | GPU | LLM from scratch |
| `Course-PhySim` | `ghcr.io/amdresearch/auplc-physim:latest` | GPU | Genesis physics sim |

These keys must match across `custom.resources.{images,requirements,metadata}`
and be referenced by `custom.teams.mapping`. The installer mirrors this in
`auplc_installer/catalog.py`; keep both consistent if you add a course used by
`./auplc-installer --courses`.

## custom.resources.requirements.<key>

```yaml
gpu:
  cpu: "0"          # "0" = no explicit request/limit (best-effort)
  memory: "0Gi"
  amd.com/gpu: "1"  # present only for GPU courses
```

## custom.resources.metadata.<key>

```yaml
Course-CV:
  group: "TEACHING LABS"          # spawn-UI grouping (see groupOrder)
  description: "Computer Vision Course"
  subDescription: "Suitable for CV experiments with GPU"
  accelerator: "GPU"              # "" for CPU courses
  acceleratorKeys:                # which custom.accelerators entries apply
    - strix-halo
  allowGitClone: true
  launchMode: "code-server"       # only for browser-IDE resources; omit for notebooks
  resourceType: "notebook"        # or "browser-ide"
  # acceleratorOverrides:         # optional per-accelerator image/env override
  #   9070xt:
  #     image: "ghcr.io/your-org/auplc-cv:<tag-for-9070xt>"
```

`custom.resources.groupOrder` is a list controlling spawn/Home group order
(e.g. `TEACHING LABS`, `DEVELOPMENT ENVIRONMENT`, `CUSTOM REPOS`). Unlisted
groups follow alphabetically.

## custom.accelerators.<key>

```yaml
strix-halo:
  displayName: "AMD Radeon™ 8060S (Strix Halo iGPU)"
  description: "RDNA 3.5 (gfx1151) | Compute Units 40 | 64GB LPDDR5X"
  nodeSelector:
    amd.com/gpu.product-name: "AMD_Radeon_8060S_Graphics"   # MUST match a real node label
  env: {}                  # e.g. HSA_OVERRIDE_GFX_VERSION for Phoenix (phx)
  quotaRate: 3             # quota consumed per hour when this accelerator is used
```

Default accelerator keys → product label:

| Key | `amd.com/gpu.product-name` |
| --- | --- |
| `phx` | `AMD_Radeon_780M_Graphics` (sets `HSA_OVERRIDE_GFX_VERSION: 11.0.0`) |
| `strix` | `AMD_Radeon_890M_Graphics` |
| `strix-halo` | `AMD_Radeon_8060S_Graphics` |
| `9070xt` | `AMD_Radeon_RX_9070_XT` |
| `r9700` | `AMD_Radeon_AI_PRO_R9700` |

If your fleet normalizes a product name differently, change the `nodeSelector`
to the exact string from `kubectl describe node`.

## custom.teams.mapping.<team>

A team name maps to the list of course keys its members can launch. Built-in
teams seen in defaults include `cpu`, `gpu`, `official`, `AUP`, `native-users`,
`github-users`. In GitHub auth, GitHub team membership syncs into these groups.

```yaml
teams:
  mapping:
    gpu:
      - code-gpu
      - Course-CV
      - Course-DL
      - Course-LLM
      - Course-PhySim
```

When the installer is run with `--courses=<subset>`, each team's list is
rewritten as the intersection with the selection, so unselected courses
disappear from the UI.

## custom.quota

```yaml
quota:
  enabled: null         # null = auto (disabled for auto-login/dummy unless set true)
  cpuRate: 1            # quota/hour for CPU-only sessions
  minimumToStart: 10    # min balance required to spawn anything
  defaultQuota: 0       # initial allocation for new users (0 = none)
  refreshRules: {}      # each rule becomes a K8s CronJob that tops up balances
```

Per-accelerator consumption is `custom.accelerators.<key>.quotaRate`.

## Apply and verify

```bash
# render check
helm template jupyterhub ./runtime/chart -f runtime/values.yaml -f <overlay> >/dev/null

# single-node
./auplc-installer rt upgrade
# multi-node / manual
helm upgrade --install jupyterhub ./runtime/chart -n jupyterhub \
  -f runtime/values.yaml -f <overlay>

kubectl rollout status -n jupyterhub deploy/hub
```

Reload the spawn page: the course shows in its `group` for mapped teams only;
a launched pod gets the declared `requirements` and lands on a node matching
the accelerator `nodeSelector`.

## Troubleshooting

| Symptom | Likely cause | First checks |
| --- | --- | --- |
| Course missing from spawn UI | Key absent from `metadata`/`images`, or team mapping | Confirm the key in all four places + `teams.mapping` |
| GPU course Pending | `acceleratorKeys` → `nodeSelector` label mismatch | `kubectl describe node | grep amd.com/gpu.product-name` |
| code-server resource opens as a notebook | `launchMode`/`resourceType` not set | `launchMode: code-server`, `resourceType: browser-ide` |
| Quota blocks all spawns | `minimumToStart` too high or `defaultQuota: 0` | Review `custom.quota`, grant balance via Admin console |
| `helm upgrade` schema error | Value violates `values.schema.json` | Read the error; fix the offending key's type |
