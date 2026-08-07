# Troubleshoot AUP Learning Cloud — Reference

Symptom → cause → first-checks matrices by layer, plus the escape hatches.
Method and safety gates are in [SKILL.md](SKILL.md).

## Source guides

- Multi-Node + 3-node mini-cluster troubleshooting sections:
  <https://amdresearch.github.io/aup-learning-cloud/installation/multi-node.html>
- The deploy skill's reference troubleshooting table (PXE/agent detail).

## PXE / netboot

| Symptom | Likely cause | First checks |
| --- | --- | --- |
| Playbook fails immediately on an assert | A required PXE var is empty | `pxe_controller_ip`, `pxe_subnet`, `pxe_network_interface`, `pxe_dns_servers`, `pxe_k3s_server_ips`, ≥1 SSH key |
| Agent never shows the PXE menu | Firmware boot order, netboot disabled, Proxy-DHCP not reaching client | Firmware, switch port, `systemctl status dnsmasq`, `journalctl -u dnsmasq` |
| Agent gets an IP but can't load boot files | TFTP blocked, missing files, Secure Boot on | `/srv/tftp`, firewall, Secure Boot disabled, dnsmasq logs |
| Agent has no network during netboot | NIC lacks an in-kernel driver in the initramfs | `lspci -nnk`, add the module to `pxe_initramfs_modules`, rebuild rootfs |
| Agent kernel boots but can't mount rootfs | NFS export / subnet ACL / wrong `pxe_controller_ip` | `showmount -e <SERVICE_IP>`, `/etc/exports`, rootfs kernel args |
| Agent waits for the k3s token | Token not published / apache ACL blocks subnet | `curl http://<SERVICE_IP>:8080/k3s/token`, apache config |
| Agent joins once but fails after reboot | Missing local k3s persistence / lost node password | `mount-local-disk`, `/var/lib/rancher/k3s/node-password`, `k3s-agent` logs |

## Node join (SSH topology)

| Symptom | Likely cause | First checks |
| --- | --- | --- |
| Agent node does not join | Hostname resolution, token, or `api_endpoint` mismatch | `systemctl status k3s-agent`, `journalctl -u k3s-agent -n 100`, `/etc/hosts`, `ping <server>` |
| Agent fails to join with a version error | Agent k3s newer than server | Align `pxe_k3s_version`/agent version with server `k3s_version` |

## GPU scheduling

| Symptom | Likely cause | First checks |
| --- | --- | --- |
| GPU notebook stays Pending | `nodeSelector` mismatch or GPUs exhausted | `kubectl describe pod -n jupyterhub <pod>` (Events), node labels |
| `amd.com/gpu` labels missing | Device plugin / labeller not running | `kubectl get ds -A | grep amdgpu`, `kubectl describe node | grep amd.com/gpu` |
| Label exists but selector doesn't match | Product-name normalized differently per fleet | Compare real `amd.com/gpu.product-name` to `custom.accelerators.*.nodeSelector` |
| GPU pod runs but ROCm errors | Wrong gfx image or missing `HSA_OVERRIDE_GFX_VERSION` (Phoenix) | Image gfx target, accelerator `env` |

## Storage

| Symptom | Likely cause | First checks |
| --- | --- | --- |
| PVC stays Pending | StorageClass name mismatch or provisioner can't mount | `kubectl get storageclass`, `kubectl get pvc -A`, provisioner logs |
| NFS provisioner crashing | Wrong `nfs.server`/`nfs.path` or export ACL | `kubectl logs -n nfs-provisioner deploy/nfs-subdir-external-provisioner`, `showmount -e <NFS>`, `/etc/exports` |
| Notebook data not persisting | Using `local-path` on multi-node, or wrong storageClass | `hub.db.pvc.storageClassName`, `singleuser.storage.dynamic.storageClass` = `nfs-client` |

## Authentication / login

| Symptom | Likely cause | First checks |
| --- | --- | --- |
| Login page 404s | Dummy provider selected or invalid provider combination | Check `custom.auth`; use exactly auto-login, dummy, native, GitHub, or native plus GitHub |
| GitHub login loops/fails | OAuth callback URL or org/team config | `hub.config.GitHubOAuthenticator`, `custom.githubOrgName`, callback URL matches host |
| User sees no courses | Team mapping empty for their group | `custom.teams.mapping`, group membership and existing fallback group in Admin console; providers don't bypass mapping |
| Can't reach admin console | Wrong admin user | `custom.adminUser`, `/hub/admin` |

## kubeconfig / access

| Symptom | Likely cause | First checks |
| --- | --- | --- |
| `permission denied` on `k3s.yaml` | kubeconfig not readable | `export KUBECONFIG=~/.kube/config`, or `--write-kubeconfig-mode=644` in inventory `extra_server_args` |
| `localhost:30890` refused (single-node) | Proxy down / NodePort changed | `kubectl get svc -n jupyterhub`, `kubectl get pods -n jupyterhub` |

## Escape hatches (gated — confirm with the user)

```bash
kubectl delete node <name>                       # clear a stale node object (debug only)
helm history jupyterhub -n jupyterhub            # then: helm rollback jupyterhub <rev>
cd deploy/ansible
sudo ansible-playbook playbooks/pb-k3s-reset.yml                 # whole cluster (DESTRUCTIVE)
sudo ansible-playbook playbooks/pb-k3s-reset.yml --limit <node>  # single node
```

After a reset, redeploy with deploy-aup-learning-cloud (multi-node) or
install-aup-learning-cloud-single-node.
