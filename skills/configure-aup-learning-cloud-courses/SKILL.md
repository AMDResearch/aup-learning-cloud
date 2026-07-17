---
name: configure-aup-learning-cloud-courses
description: >-
  Group: Course & other editor. Edits the AUP Learning Cloud course catalog and
  access control in the
  JupyterHub values.yaml: course images, resource requirements, spawn-UI
  metadata, group ordering, GPU accelerator selectors, team-to-course mappings,
  and the quota knobs. Use when the user wants to add/remove a course or
  notebook environment, show/hide an option in the spawn picker, map a GitHub
  team or group to courses, set per-course CPU/memory/amd.com/gpu requirements,
  add or retune an accelerator (custom.accelerators), or configure quota
  (cpuRate, quotaRate, minimumToStart, refresh rules). Triggers include
  values.yaml, custom.resources.images, custom.teams.mapping,
  custom.accelerators, custom.quota, acceleratorKeys, launchMode. Do not use to
  build the images themselves (build-aup-learning-cloud-images) or to install a
  cluster (install-/deploy-aup-learning-cloud).
---

# Configure AUP Learning Cloud courses

Change what users can spawn and who can see it, by editing the `custom:` block
of the JupyterHub values and re-applying with Helm. One coherent surface:
course images, their resource requirements, the spawn-UI metadata, accelerator
selectors, team mappings, and quota.

Edit a **values overlay** (e.g. `runtime/values-basic-example.yaml` or
`values.local.yaml`), never the chart defaults blindly. The key map and the
full field guide are in **[reference.md](reference.md)**.

## Prerequisites

- A checkout of `aup-learning-cloud`; a running Hub (single- or multi-node).
- `helm` + `kubectl` against the cluster, or `./auplc-installer` on a
  single-node box.
- Know which keys already exist: `custom.resources.images` is the catalog;
  course keys are `cpu`, `gpu`, `code-cpu`, `code-gpu`, and `Course-CV`,
  `Course-DL`, `Course-LLM`, `Course-PhySim`.

## The four places a course lives

A course key must be consistent across **all** of these or the spawn UI breaks:

1. `custom.resources.images.<key>` — the container image.
2. `custom.resources.requirements.<key>` — `cpu`, `memory`, and `amd.com/gpu`.
3. `custom.resources.metadata.<key>` — spawn-UI `group`, `description`,
   `accelerator`, `acceleratorKeys`, `allowGitClone`, `launchMode`,
   `resourceType`.
4. `custom.teams.mapping.<team>` — the teams allowed to launch it.

## Workflow

1. **Read the current state.** Open `runtime/values.yaml` for the canonical
   shape, and the active overlay for what is deployed. Confirm the exact key
   you are changing.
2. **Make the edit in the overlay.** Add/modify the key in all four places
   above (or, for accelerators/quota, the relevant block). Keep `acceleratorKeys`
   pointing at real `custom.accelerators` keys (`phx`, `strix`, `strix-halo`,
   `9070xt`, `r9700`).
3. **Keep accelerator selectors honest.** Each `custom.accelerators.<key>.nodeSelector`
   must equal a real node label — confirm with
   `kubectl describe node <node> | grep amd.com/gpu.product-name`.
4. **Validate the render before applying.** `helm template jupyterhub
   ./runtime/chart -f runtime/values.yaml -f <overlay>` must succeed; the repo
   also ships `runtime/chart/values.schema.json`.
5. **Apply.** Single-node: `./auplc-installer rt upgrade`. Multi/manual:
   `helm upgrade --install jupyterhub ./runtime/chart -n jupyterhub -f
   runtime/values.yaml -f <overlay>`.
6. **Verify.** Reload the spawn page; the course appears in its `group` for the
   mapped teams only, and a launched pod gets the expected resources/node.

## Safety

- **Edit overlays, not secrets.** Never put OAuth secrets or tokens in tracked
  files. Never commit a `values.local.yaml` that carries site config.
- **Removing a course** hides it and can strand running servers on that image —
  confirm with the user and check for active spawns first.
- **Quota changes apply cluster-wide.** Lowering `minimumToStart` / `cpuRate`
  or editing `refreshRules` affects every user; confirm before applying.
- A `helm upgrade` restarts the Hub pod (brief auth blip). Confirm timing for a
  live class.

## Reference

Course-key map, every `metadata`/`requirements` field, the accelerator block,
team-mapping semantics, and the quota knobs: [reference.md](reference.md).
