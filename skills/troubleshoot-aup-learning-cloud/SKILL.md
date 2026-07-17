---
name: troubleshoot-aup-learning-cloud
description: >-
  Group: Maintain AUP Learning Cloud. Diagnoses a broken AUP Learning Cloud
  deployment against a known list of
  causes: PXE/netboot failures, agent nodes not joining, GPU notebooks stuck
  Pending or ROCm labels missing, NFS/PVC storage provisioning failures, and
  login/authentication problems. Use when the user reports that AUPLC is broken,
  a node won't join, a pod is Pending / CrashLoopBackOff / ImagePullBackOff, the
  GPU isn't scheduling, storage won't bind, PXE agents won't boot, the Hub login
  404s, or asks to debug/diagnose/figure out why something failed. Evidence-first
  and read-only: gather state, identify the cause, then hand off the fix to the
  matching deploy/install/configure/upgrade skill. Do not use to perform a fresh
  install or a routine config change when nothing is actually failing.
---

# Troubleshoot AUP Learning Cloud

Find the root cause of a failing deployment from runtime evidence, name it, and
point at the fix — without thrashing. Gather state first, match the symptom to
a known cause, change one thing, re-check. The full symptom → cause → checks
matrices live in **[reference.md](reference.md)**.

## Prerequisites

- Access to the cluster (`kubectl`, the right `KUBECONFIG`) and/or the service
  machine (for PXE/host issues).
- A checkout of `aup-learning-cloud` for config cross-checks.
- The deploy skill's `scripts/detect_cluster.sh` is a fast way to snapshot
  nodes, GPU labels, storage classes, and the device plugin/labeller state.

## Method (don't thrash)

1. **Scope it.** Which layer is failing — netboot, node join, GPU scheduling,
   storage, or auth? One layer at a time.
2. **Gather evidence before acting.**

   ```bash
   kubectl get nodes -o wide
   kubectl get pods -A | grep -Ev 'Running|Completed'
   kubectl describe pod -n jupyterhub <pod>     # Events explain Pending/ImagePull
   scripts/detect_cluster.sh                     # from the deploy skill
   ```

3. **Match to a cause** using the [reference.md](reference.md) matrices.
4. **Change one thing**, then re-check the same evidence. Do not stack
   speculative changes. After ~4 failed attempts with no new evidence, stop and
   report what you observed and the most likely next step.
5. **Hand off the fix** to the right skill (below) rather than improvising.

## Where each fix lives

| Failing layer | Fix with |
| --- | --- |
| PXE rootfs vars / rebuild, agent netboot, NFS rootfs, k3s token publish | deploy-aup-learning-cloud |
| Single-node install / GPU detect / `localhost:30890` | install-aup-learning-cloud-single-node |
| `nodeSelector` ↔ GPU label, course/team/quota, auth mode | configure-aup-learning-cloud-courses |
| Image tag / `ImagePullBackOff` from a missing build | build-aup-learning-cloud-images |
| Version mismatch after a bump, chart rollback | upgrade-aup-learning-cloud |

## First checks by layer

- **Netboot:** `systemctl status dnsmasq nfs-kernel-server apache2`,
  `journalctl -u dnsmasq`, firmware boot order + Secure Boot, TFTP files in
  `/srv/tftp`.
- **Node join:** `systemctl status k3s-agent`, `journalctl -u k3s-agent`,
  hostname/`api_endpoint`/token, `curl http://<SERVICE_IP>:8080/k3s/token`.
- **GPU:** `kubectl get ds -A | grep amd`,
  `kubectl describe node <n> | grep amd.com/gpu`, then compare to
  `custom.accelerators.*.nodeSelector`.
- **Storage:** `kubectl get pvc -A`, provisioner logs, `showmount -e <NFS>`,
  `/etc/exports`.
- **Auth:** Hub logs (`kubectl logs -n jupyterhub deploy/hub`), `custom.authMode`
  (avoid `dummy`, whose login 404s), GitHub OAuth callback URL.

## Safety

Evidence-first and read-only by default. Stop and get explicit confirmation
before any state change, especially:

- `kubectl delete node <name>` (clears a stale node object — debugging only).
- `helm uninstall`, `helm rollback`, or recreating any PVC (data loss).
- `pb-k3s-reset.yml` (whole cluster or `--limit <node>`).
- Rebuilding the PXE rootfs under running agents (`pxe_rootfs_force_rebuild`).

Never commit changes or write secrets (k3s token, OAuth secrets, SSH keys) into
tracked files while debugging.

## Reference

Full symptom → cause → first-checks matrices for netboot, node join, GPU,
storage, auth, and kubeconfig, plus the reset/escape hatches:
[reference.md](reference.md).
