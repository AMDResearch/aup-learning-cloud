---
name: upgrade-aup-learning-cloud
description: >-
  Group: Maintain AUP Learning Cloud. Upgrades a running AUP Learning Cloud
  deployment: the JupyterHub Helm
  release/chart and values, and the underlying k3s cluster. Use when the user
  wants to upgrade, update, bump, or roll out a new version of AUPLC, the Hub
  image, the chart, or k3s on an already-installed cluster; mentions helm
  upgrade, ./auplc-installer rt upgrade / rt reinstall, pb-k3s-upgrade,
  bumping k3s_version / pxe_k3s_version, or applying a values change to a live
  Hub. Covers both single-node (installer) and multi-node (Ansible + Helm)
  paths, and the safe ordering of cluster vs chart upgrades. Do not use for the
  first install (install-/deploy-aup-learning-cloud), for building images
  (build-aup-learning-cloud-images), or for routine course edits
  (configure-aup-learning-cloud-courses) unless a version bump is involved.
---

# Upgrade AUP Learning Cloud

Move a live deployment to new versions without losing user data: apply chart /
values / image changes, and (separately, more carefully) upgrade k3s. Two
independent axes — **the Hub (Helm)** and **the cluster (k3s)** — upgraded in a
safe order. Commands per topology and the rollback notes are in
**[reference.md](reference.md)**.

## Prerequisites

- A running cluster and a checkout of `aup-learning-cloud` matching (or ahead
  of) what is deployed.
- `helm` + `kubectl` (multi-node) or `./auplc-installer` (single-node).
- Know what is changing: values only, Hub image tag, chart version, and/or k3s
  version. Each has a different, least-disruptive path.

## Decide the smallest sufficient action

| Change | Path |
| --- | --- |
| values.yaml / overlay only | `helm upgrade` (multi) or `./auplc-installer rt upgrade` (single) |
| New Hub/notebook image tag | bump `custom.resources.images`, then the same upgrade; single-node image swap: `rt reinstall` |
| Chart bump | `helm upgrade --install` with the new chart |
| k3s version | Ansible `pb-k3s-upgrade.yml` (multi) — separate, gated step |

Prefer the narrowest path. A values/image change does **not** require a k3s
upgrade.

## Workflow

1. **Snapshot state.** `kubectl get nodes -o wide`, `helm list -n jupyterhub`,
   `kubectl get pods -n jupyterhub`. Note the current chart + k3s versions and
   that nothing is already broken.
2. **Pre-flight the render.** `helm template jupyterhub ./runtime/chart -f
   runtime/values.yaml -f <overlay>` must succeed before any apply.
3. **Upgrade the Hub (Helm).** Apply the chart/values change; watch the
   rollout. This restarts the Hub pod (brief login blip); running user servers
   are generally unaffected.
4. **Upgrade k3s only if needed** (gated — see Safety). Multi-node uses
   `pb-k3s-upgrade.yml`. **Keep `pxe_k3s_version` (PXE rootfs) in sync with the
   server `k3s_version`** — agents must not be newer than the server.
5. **Verify end to end.** Nodes `Ready`, no `CrashLoopBackOff`/`ImagePullBackOff`,
   the Hub loads, an existing user can log in, and a fresh spawn (CPU then GPU)
   works.

## Safety

Stop and get explicit confirmation before:

- **A k3s upgrade** — it restarts the kubelet/control plane and can disrupt
  running pods; do it in a maintenance window, server before agents.
- **`pb-k3s-reset.yml`** (whole cluster or `--limit <node>`) — destructive.
- **`helm uninstall`** or any change that recreates the Hub DB PVC — data loss.
- **A Hub image tag bump during a live class** — schedule the restart.

Never commit changes, and never bump `pxe_k3s_version` above the server
`k3s_version`. If a chart upgrade misbehaves, `helm rollback jupyterhub <rev>`
(see reference) before experimenting further.

## Reference

Per-topology commands (single-node installer, multi-node Helm, k3s playbooks),
version-pin locations, `helm history`/`rollback`, and troubleshooting:
[reference.md](reference.md).
