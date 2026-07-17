# Upgrade AUP Learning Cloud — Reference

Per-topology upgrade commands, version-pin locations, rollback, and
troubleshooting. Workflow and gates are in [SKILL.md](SKILL.md).

## Source guides

- Multi-Node "Apply Later Configuration Changes" + upgrade playbooks:
  <https://amdresearch.github.io/aup-learning-cloud/installation/multi-node.html>
- `scripts/helm_upgrade.bash` and `./auplc-installer help` (`rt`, `dev`).

## Version-pin locations

| Pin | File |
| --- | --- |
| k3s server version | `deploy/ansible/inventory.yml` → `k3s_version` |
| PXE agent rootfs k3s version | `deploy/ansible/playbooks/pb-pxe-controller.yml` → `pxe_k3s_version` |
| Hub image tag | `custom.resources.images` (values overlay) + `hub.image.tag` |
| Chart | `runtime/chart/Chart.yaml` |

Keep `pxe_k3s_version == k3s_version`. The deploy skill's
`scripts/validate.py` cross-checks this.

## Hub (Helm) upgrade — values / image / chart

Single-node (installer):

```bash
./auplc-installer rt upgrade       # values change on a running runtime
./auplc-installer rt reinstall     # container image change
./auplc-installer dev upgrade      # dev overlay (student=admin, pullPolicy=Never)
```

Multi-node / manual:

```bash
# pre-flight render
helm template jupyterhub ./runtime/chart -f runtime/values.yaml -f <overlay> >/dev/null

helm upgrade --install jupyterhub ./runtime/chart \
  -n jupyterhub \
  -f runtime/values.yaml -f <overlay>

kubectl rollout status -n jupyterhub deploy/hub
```

(`scripts/helm_upgrade.bash` runs the bare
`helm upgrade jupyterhub runtime/chart -n jupyterhub --values runtime/values.yaml`.)

## k3s upgrade (multi-node, gated)

```bash
cd deploy/ansible
# bump k3s_version in inventory.yml first (and pxe_k3s_version to match)
sudo ansible-playbook playbooks/pb-k3s-upgrade.yml
kubectl get nodes -o wide      # versions advance, nodes stay Ready
```

Upgrade the server first, then agents. For PXE diskless agents, bump
`pxe_k3s_version` and rebuild the rootfs (deploy skill) so netbooted agents
match.

## Install / refresh Helm itself

```bash
wget https://get.helm.sh/helm-v3.17.2-linux-amd64.tar.gz -O /tmp/helm.tar.gz
cd /tmp && tar -zxvf helm.tar.gz && sudo mv /tmp/linux-amd64/helm /usr/local/bin/helm
# or: ./auplc-installer install-tools   # helm + k9s
```

## Rollback

```bash
helm history jupyterhub -n jupyterhub
helm rollback jupyterhub <REVISION> -n jupyterhub
kubectl rollout status -n jupyterhub deploy/hub
```

k3s has no one-command rollback; pin back the version in inventory and re-run
the upgrade playbook, or restore from a node/etcd snapshot if you keep one.

## Troubleshooting

| Symptom | Likely cause | First checks |
| --- | --- | --- |
| Hub pod `CrashLoopBackOff` after upgrade | Bad values / incompatible chart | `kubectl logs -n jupyterhub deploy/hub`, `helm rollback` |
| `ImagePullBackOff` after image bump | Tag not pushed or wrong registry | `kubectl describe pod -n jupyterhub`, confirm the pushed tag |
| Agent fails to rejoin after k3s bump | Agent newer than server / rootfs not rebuilt | Align `pxe_k3s_version`, rebuild rootfs, `journalctl -u k3s-agent` |
| Quota CronJobs missing after upgrade | `custom.quota.refreshRules` changed | `kubectl get cronjob -n jupyterhub` |
| PVC lost / Hub DB reset | PVC recreated by an upgrade | Never delete the Hub DB PVC; restore from backup |

## Out of scope

First-time install/deploy, image authoring, and HA/external-DB migrations
(treat those as explicit operator projects). This skill upgrades an existing
deployment in place.
