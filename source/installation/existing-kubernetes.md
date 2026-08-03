# Deploy AUP Learning Cloud On Kubernetes

This guide starts with an **existing, working Kubernetes cluster**. Cluster and node provisioning, cloud resource lifecycle, and provider-specific networking are outside its scope.

Use this path when the cluster is already operated for you and you need to make it ready for AUP Learning Cloud, prepare deployment values, install the chart, and validate the result. If you still need to build a multi-node K3s cluster, follow [Multi-Node Cluster Deployment](multi-node.md) first, then return here when the cluster is ready.

:::{seealso}
For AUP configuration details, see [Configuration Reference](../jupyterhub/configuration-reference.md) and [Authentication Guide](../jupyterhub/authentication-guide.md).
:::

## Prerequisites

- A Kubernetes cluster at version **1.28 or later**, as required by `runtime/chart/Chart.yaml`.
- A `kubectl` context with the cluster-scoped and namespaced permissions required by the chart.
- Helm 3.
- A checkout of the AUP Learning Cloud repository.
- AMD GPU nodes with a supported host operating system and driver stack.
- A CSI driver and StorageClass suitable for the cluster topology.
- Access to the configured container registries, including credentials for private images.

The AUP chart's Kubernetes requirement does not replace AMD's requirements. Also honor the compatibility matrix for the AMD GPU management path and version you choose.

Complete Steps 1 through 7 in order. Unless noted otherwise, run commands on the **operator machine** that holds the repository checkout, `kubectl` context, and Helm configuration. Run blocks marked **GPU node** through the site's approved node-access method. Replace `<repository-root>`, `<selected-storage-class>`, `<gpu-node>`, `<pod-name>`, `<configured-url>`, and other angle-bracketed placeholders with values from your environment. Stop and fix any failed gate before continuing.

(existing-kubernetes-preflight)=

## 1. Run Cluster Preflight Checks

Confirm that `kubectl` points to the intended cluster and that its API and workers are ready:

```bash
kubectl config current-context
kubectl cluster-info
kubectl version
kubectl get --raw='/readyz?verbose'
kubectl get nodes -o wide
```

The context and API endpoint must identify the intended cluster, the server version must be at least 1.28, `/readyz` must succeed, and every worker intended for AUP must report `Ready`. Stop here if any of those checks fails.

Run representative permission checks next:

```bash
kubectl auth can-i create namespaces
kubectl auth can-i create clusterroles.rbac.authorization.k8s.io
kubectl auth can-i create clusterrolebindings.rbac.authorization.k8s.io
kubectl auth can-i create deployments.apps --namespace jupyterhub
kubectl auth can-i create statefulsets.apps --namespace jupyterhub
kubectl auth can-i create persistentvolumeclaims --namespace jupyterhub
kubectl auth can-i create services --namespace jupyterhub
```

For the normal cluster-administrator flow, every command must print `yes`. These are smoke checks, not a complete permissions proof. Helm also needs the appropriate `get`, `list`, `watch`, `create`, `patch`, `update`, and `delete` lifecycle permissions for every rendered resource. Depending on enabled features, that includes namespaced RBAC, ServiceAccounts, Secrets, ConfigMaps, NetworkPolicies, Jobs, DaemonSets, and PodDisruptionBudgets.

If cluster-scoped access cannot be delegated, use this namespace-only model:

1. Ask a cluster administrator to pre-create the `jupyterhub` namespace.
2. Set `scheduling.userScheduler.enabled: false` so the release renders no user-scheduler cluster RBAC.
3. Keep `rbac.create: true` so the chart creates its required namespaced RBAC.
4. Omit `--create-namespace` from the Helm command in Step 5.

The delegated identity still needs full lifecycle permissions for all rendered namespaced resources. A more restrictive `rbac.create: false` requires a cluster administrator to pre-provision **all** rendered namespaced and cluster-scoped RBAC, not only scheduler objects. Both models require approved values and review of the rendered manifest.

Check Helm and discover the available StorageClasses:

```bash
helm version
kubectl get storageclass
```

Helm must report version 3, and at least one candidate StorageClass must be available for Step 3.

:::{warning}
AUP's pinned Z2JH 4.3.3 default is:

```yaml
singleuser.cloudMetadata.blockWithIptables: true
```

It dynamically injects `block-cloud-metadata` into each user Pod at spawn time. This init container is privileged, runs as root (UID 0), and has the `NET_ADMIN` capability. Its iptables rule drops TCP traffic with destination port 80 to `169.254.169.254`; it does not block every port or protocol. Helm can install successfully even when admission policy rejects the first user spawn.

Before installation, check Pod Security Admission, Gatekeeper, cloud-provider policy, and other site admission rules. Set the following only after a replacement control is enforced and empirically verified to block instance metadata access while preserving required DNS and Hub connectivity:

```yaml
singleuser.cloudMetadata.blockWithIptables: false
```

A NetworkPolicy object, CNI selection, or other configuration alone is not proof of enforcement.
:::

Continue only when the default init container is allowed or an approved replacement can meet the acceptance test in Step 7.

## 2. Provide AMD GPU Support

Use exactly one Kubernetes GPU management path. Do not install the GPU Operator and the standalone device plugin and node labeller together because they manage overlapping GPU discovery resources.

### Standalone Device Plugin And Node Labeller

This is the direct AUP-matching path when AMD host drivers are already installed and managed outside Kubernetes. The following block uses the same immutable upstream revision and manifest checksums pinned by AUP. It requires `curl` and `sha256sum` on the operator machine:

```bash
curl -fsSL \
  https://raw.githubusercontent.com/ROCm/k8s-device-plugin/dea1db13f05159e64d8114bca4c31f48c3cfcac6/k8s-ds-amdgpu-dp.yaml \
  -o /tmp/k8s-ds-amdgpu-dp.yaml

curl -fsSL \
  https://raw.githubusercontent.com/ROCm/k8s-device-plugin/dea1db13f05159e64d8114bca4c31f48c3cfcac6/k8s-ds-amdgpu-labeller.yaml \
  -o /tmp/k8s-ds-amdgpu-labeller.yaml

echo 'b751e467feecf6118bed1de8ba80b9abff01c1f52a6b0b8f31aca3609e6e9dbd  /tmp/k8s-ds-amdgpu-dp.yaml' \
  | sha256sum --check
echo 'c3e456967efdf14bcfeb97d8f87ca75a402cc6c7c8c6201a320efdd0370fa7aa  /tmp/k8s-ds-amdgpu-labeller.yaml' \
  | sha256sum --check
```

Both checksum commands must report `OK`. Stop and delete the downloaded files if either check fails. When both checks pass, apply the manifests:

```bash
kubectl apply -f /tmp/k8s-ds-amdgpu-dp.yaml
kubectl apply -f /tmp/k8s-ds-amdgpu-labeller.yaml

kubectl rollout status --namespace kube-system \
  daemonset/amdgpu-device-plugin-daemonset --timeout=5m
kubectl rollout status --namespace kube-system \
  daemonset/amdgpu-labeller-daemonset --timeout=5m

rm -f /tmp/k8s-ds-amdgpu-dp.yaml /tmp/k8s-ds-amdgpu-labeller.yaml
```

The apply commands are idempotent, and both DaemonSets must roll out successfully.

### AMD GPU Operator Alternative

Use the AMD GPU Operator instead when the site wants operator-owned GPU lifecycle and its Kubernetes version, node operating system, kernel, GPU, and ownership model are supported. Follow the official [AMD GPU Operator installation on Kubernetes](https://instinct.docs.amd.com/projects/gpu-operator/en/latest/installation/kubernetes-helm.html) and [GPU Operator compatibility matrix](https://instinct.docs.amd.com/projects/gpu-operator/en/latest/index.html#compatibility).

Installing the Operator controller alone does not deliver working GPU resources. The site-specific DeviceConfig must deliberately define driver ownership, node selectors, device plugin rather than DRA-only operation, kubelet socket, and operand images. Review privileged workloads, RBAC, and other cluster-scoped resources before applying them. AUP requires the traditional device-plugin contract; a DRA-only configuration is not compatible.

Whichever path you choose, verify the result:

```bash
kubectl get nodes -L amd.com/gpu.product-name,amd.com/gpu.family,amd.com/gpu.vram
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.allocatable.amd\.com/gpu}{"\n"}{end}'
kubectl get pods -A -o wide
```

At least one intended GPU node must have the expected `amd.com/gpu.product-name` label, a non-zero allocatable `amd.com/gpu` value, and healthy operands for the one selected path. Stop and repair GPU management if that contract is incomplete.

The device plugin allocates `/dev/kfd` and selected `/dev/dri/renderD*` and `/dev/dri/card*` devices to a GPU Pod and establishes device-cgroup access. It does not set the Unix mode or ownership of host device nodes.

On Ubuntu GPU nodes whose configured AMD package repository provides it, install the AUP-pinned permission policy:

**GPU node:**

```bash
sudo apt update
sudo apt install -y amdgpu-insecure-instinct-udev-rules
```

Other node operating systems or lifecycle systems need an approved equivalent host policy. It must set mode `0666` for `/dev/kfd` and `/dev/dri/renderD*`, keep `/dev/dri/card*` protected, and persist after node creation, replacement, reimage, and upgrade.

**GPU node:**

```bash
stat -c '%a %U %G %n' /dev/kfd /dev/dri/renderD*
stat -c '%a %U %G %n' /dev/dri/card*
```

Every listed KFD and render node must report mode `666`. Do not set card nodes to mode `666`; review them against the site's protected policy.

## 3. Select Storage

Use an existing named CSI StorageClass that supports the chart's default `ReadWriteOnce` claims. This guide does not prescribe a CSI driver or generic NFS installation.

```bash
kubectl get storageclass
kubectl get storageclass <selected-storage-class> -o yaml
```

Inspect the provisioner, `volumeBindingMode`, reclaim policy, allowed topologies, and mount options. Confirm from the CSI documentation and site policy that the class can dynamically provision RWO volumes and attach them where their Pods run. Stop if the class, provisioner health, topology, persistence, backup, or recovery ownership is unresolved.

The chart defaults are:

- Hub database: `sqlite-pvc`, `ReadWriteOnce`, 1 GiB, controlled by `hub.db.pvc.accessModes`.
- User homes: dynamic `ReadWriteOnce`, 10 GiB per user server. Configure their access modes with:

  ```yaml
  singleuser.storage.dynamic.storageAccessModes
  ```

RWO is suitable when the provisioner and topology permit reattachment to the scheduled node. RWX network storage is an alternative when homes must be accessible across nodes without reattachment or site policy requires it. See [dynamic volume provisioning](https://kubernetes.io/docs/concepts/storage/dynamic-provisioning/) and [PersistentVolumes and access modes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/).

`local-path` and direct `hostPath` bind data to a node and are not portable multi-node defaults. Use them only after accepting the node-loss, scheduling, mobility, backup, and recovery limits.

:::{warning}
Changing a StorageClass value does not migrate existing PVC data. Plan and test a separate backup and migration before changing an installed deployment.
:::

The default SQLite PVC is suitable for the base chart flow. External PostgreSQL or MySQL provisioning, migration, backup, and high availability are separate operator responsibilities.

## 4. Prepare AUP Values

Create a protected site file from the multi-node example without overwriting existing configuration:

:::{warning}
Site values may contain OAuth, administrator, registry, or other credentials. Prefer non-secret settings plus references to pre-created Kubernetes Secrets where supported. Never commit credentials, place them on command lines, or publish them in logs or artifacts.
:::

```bash
cd <repository-root>
cp --no-clobber \
  runtime/values-multi-nodes.yaml.example \
  runtime/values-existing-cluster.yaml
chmod 600 runtime/values-existing-cluster.yaml
ls -l runtime/values-existing-cluster.yaml
```

The file must show mode `-rw-------`. If it already existed, review it rather than overwriting it.

The example is not production-ready. It currently contains site-specific samples such as `nfs-client`, authentication placeholders, mutable image tags, and an example supplemental group. Find those defaults, then open the file and replace or remove them:

```bash
grep -nE 'nfs-client|:latest|supplementalGroups|TODO|<YOUR-|your\.domain\.com' \
  runtime/values-existing-cluster.yaml
nano runtime/values-existing-cluster.yaml
```

Collect the storage and GPU facts again while editing:

```bash
kubectl get storageclass <selected-storage-class> -o name
kubectl get nodes -L amd.com/gpu.product-name,amd.com/gpu.family,amd.com/gpu.vram
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.allocatable.amd\.com/gpu}{"\n"}{end}'
```

Map those observed and approved inputs to the values file:

| Input | Values to review |
| --- | --- |
| Identity provider, callback URL, administrators | Authentication and administrator settings from the [Authentication Guide](../jupyterhub/authentication-guide.md); use Secret references where supported. |
| GPU product labels and enabled offerings | `custom.accelerators` and `custom.accelerators.<key>.nodeSelector`. |
| Approved CPU and ROCm images | `custom.resources.images`, requirements, `custom.resources.metadata`, `acceleratorOverrides`, and `custom.resources.metadata.<resource>.acceleratorKeys`. |
| Teams and capacity | `custom.teams.mapping` and `custom.quota`; Helm replaces arrays rather than merging their entries. |
| Selected CSI class and modes | `hub.db.pvc.storageClassName`, `hub.db.pvc.accessModes`, `singleuser.storage.dynamic.storageClass`, and `singleuser.storage.dynamic.storageAccessModes`. |
| Volume ownership | `singleuser.extraPodConfig.securityContext`; use a storage `fsGid` only when required by the volume policy. |
| Metadata protection | `singleuser.cloudMetadata.blockWithIptables`; keep it `true` unless the replacement passed Step 1 and will be tested in Step 7. |
| Registry and artifacts | Pull Secret references, pull policy, resource images, accelerator overrides, and pre-puller images. |
| Access design | Proxy exposure, ingress, public scheme, TLS, DNS, callback URLs, and firewall or source restrictions. |

Remove the example GPU `supplementalGroups`. AUP does not manage GPU-specific supplemental groups under this contract. Device allocation and device-cgroup access come from the AMD device plugin, while host modes come from the Step 2 udev policy. A storage `fsGid` is separate and must not grant GPU access.

For every enabled GPU resource, align the actual `amd.com/gpu.product-name` label, its `nodeSelector`, the GPU architecture, and a ROCm image validated for that architecture. Pin reviewed image tags or digests instead of mutable tags such as `latest`, and align resource images, accelerator overrides, and pre-puller images.

The chart creates NetworkPolicy objects by default, but isolation exists only when the cluster network implementation enforces them. Verify enforcement rather than treating the objects as proof.

Keep the proxy private until production authentication is tested. Public exposure requires HTTPS with a valid certificate, correct callback URLs, working DNS, and approved firewall or source restrictions. Never expose development authentication to untrusted networks.

Do not render until credentials, selectors, storage, metadata controls, images, NetworkPolicy enforcement, and exposure have all been reviewed. See [Customizing a Single-Node Deployment](customizing-deployment.md) for the AUP resource model and the [Configuration Reference](../jupyterhub/configuration-reference.md) for field details.

## 5. Render And Install

Lint and privately inspect the exact site configuration from the repository root:

```bash
cd <repository-root>
helm lint runtime/chart \
  --namespace jupyterhub \
  -f runtime/values-existing-cluster.yaml

helm template jupyterhub runtime/chart \
  --namespace jupyterhub \
  -f runtime/values-existing-cluster.yaml | less
```

The rendered output can contain Secrets or derived sensitive values. Review it in the terminal; do not save, publish, or upload it.

Before installation, confirm:

- [ ] Images, digests or tags, pull Secrets, and pull policy match approved artifacts.
- [ ] GPU selectors and requests match the Step 2 labels and `amd.com/gpu` contract.
- [ ] Hub and user-home StorageClasses and access modes match Step 3.
- [ ] Metadata blocking and admission-sensitive Pod settings match Step 1.
- [ ] RBAC matches the cluster-admin or reviewed delegated model.
- [ ] Authentication, proxy, ingress, TLS, and exposure match the approved design.

Stop if lint fails or the render contains an unexpected resource, secret, selector, storage class, or exposure setting. Otherwise install or upgrade:

```bash
helm upgrade --install jupyterhub runtime/chart \
  --namespace jupyterhub \
  --create-namespace \
  -f runtime/values-existing-cluster.yaml \
  --wait \
  --timeout 10m
```

For the delegated namespace-only model from Step 1, omit `--create-namespace`. Keep `--wait` and the timeout. If Helm fails or times out, inspect Step 6 before retrying; do not begin user acceptance on a partial release.

## 6. Validate Infrastructure

Check the release and its cluster dependencies:

```bash
helm status jupyterhub --namespace jupyterhub
kubectl get pods,services,ingress --namespace jupyterhub -o wide
kubectl get pvc --namespace jupyterhub
kubectl get events --namespace jupyterhub --sort-by=.metadata.creationTimestamp
kubectl get nodes -L amd.com/gpu.product-name
kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.allocatable.amd\.com/gpu}{"\n"}{end}'
```

Do not continue until:

- [ ] Helm reports the release as deployed and required workloads are ready.
- [ ] No unresolved restart, scheduling, image-pull, or admission error remains.
- [ ] Hub and user PVCs created so far are `Bound`.
- [ ] The configured internal or external route resolves to the proxy.
- [ ] Intended GPU nodes retain their product label and non-zero `amd.com/gpu` value.
- [ ] Recent namespace events contain no unresolved AUP warning.

(existing-kubernetes-end-to-end-acceptance)=

## 7. Run End-To-End Acceptance

Complete every case through the user-facing interface and retain the Pod inspection output. Shared clusters can create several user Pods at once, so always select the test Pod by exact name. Never auto-select the newest Pod.

### Log In And Spawn A CPU Server

Open `<configured-url>`, log in with a non-administrator test user, choose a CPU resource, and wait for the environment to become ready. Identify that user's exact Pod:

```bash
kubectl get pods --namespace jupyterhub -l component=singleuser-server -o wide
CPU_USER_POD='<exact-cpu-user-pod-name>'
kubectl get pod --namespace jupyterhub "$CPU_USER_POD" -o wide
kubectl describe pod --namespace jupyterhub "$CPU_USER_POD"
```

Resolve login, spawn, scheduling, or Pod identity problems before continuing.

### Prove Metadata Protection

When the default metadata blocker remains enabled, verify the selected CPU Pod's init result:

```bash
kubectl get pod --namespace jupyterhub "$CPU_USER_POD" \
  -o jsonpath='{range .status.initContainerStatuses[*]}{.name}{"\t"}{.state.terminated.reason}{"\t"}{.state.terminated.exitCode}{"\n"}{end}'
```

`block-cloud-metadata` must report `Completed` with exit code `0`. When the field is `false`, retain approved empirical evidence that the replacement blocks instance metadata access while DNS and Hub connectivity still work. Use a site-approved probe or test harness; do not assume every user image contains `curl`.

### Prove Home Persistence

Create a file in the user's home:

```bash
kubectl exec --namespace jupyterhub "$CPU_USER_POD" -- \
  sh -c 'printf "%s\n" "AUP persistence acceptance" > "$HOME/aup-persistence-check.txt" && cat "$HOME/aup-persistence-check.txt"'
```

Stop the server through the interface, start the same CPU resource again, and manually set `CPU_USER_POD` to the exact restarted Pod:

```bash
kubectl get pods --namespace jupyterhub -l component=singleuser-server -o wide
CPU_USER_POD='<exact-restarted-cpu-user-pod-name>'
kubectl exec --namespace jupyterhub "$CPU_USER_POD" -- \
  sh -c 'cat "$HOME/aup-persistence-check.txt"'
```

The restarted server must print `AUP persistence acceptance`. Stop if the file is missing or the PVC was unexpectedly replaced.

### Spawn And Select A GPU Server

Stop the CPU server if quota requires it, choose an enabled GPU resource, and wait for it to become ready. Select the exact GPU Pod:

```bash
kubectl get pods --namespace jupyterhub -l component=singleuser-server -o wide
GPU_USER_POD='<exact-gpu-user-pod-name>'
kubectl get pod --namespace jupyterhub "$GPU_USER_POD" \
  -o jsonpath='{.spec.nodeName}{"\n"}{.spec.containers[0].resources}{"\n"}'
kubectl get nodes -L amd.com/gpu.product-name
```

The Pod must request `amd.com/gpu` and land on a node with the product label selected by its AUP resource. Resolve a missing request, selector mismatch, pending Pod, or wrong-node placement before continuing.

### Verify Host Device Modes

Connect to the node reported by the selected GPU Pod through the site's approved node-access method. There is no universal node-login command.

**GPU node:**

```bash
stat -c '%a %n' /dev/kfd /dev/dri/renderD*
stat -c '%a %n' /dev/dri/card*
```

KFD and every render node must report mode `666`; card nodes must remain protected. Repair the persistent host policy rather than weakening card-node permissions.

### Verify GPU Access In The Pod

```bash
kubectl exec --namespace jupyterhub "$GPU_USER_POD" -- rocminfo
```

`rocminfo` must exit successfully and report the expected AMD GPU. `amd-smi` or a basic operation in the installed GPU framework is a useful additional test, but it does not replace `rocminfo` here.

Acceptance is cumulative. Login, CPU spawn, metadata evidence, persistent home storage, host mode `666` for KFD and render nodes, non-zero allocatable `amd.com/gpu`, GPU scheduling, and in-Pod `rocminfo` must all succeed.

## Troubleshooting

(existing-kubernetes-metadata-troubleshooting)=

### User Spawn Fails At Admission Or During Metadata Blocking

If no user Pod is created, inspect Hub logs, namespace events, and admission labels:

```bash
kubectl logs --namespace jupyterhub deployment/hub --since=15m
kubectl get events --namespace jupyterhub --sort-by=.metadata.creationTimestamp
kubectl get namespace jupyterhub --show-labels
```

Look for `Forbidden`, `denied`, `PodSecurity`, `privileged`, `NET_ADMIN`, Gatekeeper, or another policy rejection. Helm success does not prove that user Pods pass admission.

If the Pod exists but remains in init, inspect its state, blocker logs, and events:

```bash
kubectl describe pod --namespace jupyterhub <user-pod>
kubectl get pod --namespace jupyterhub <user-pod> \
  -o jsonpath='{range .status.initContainerStatuses[*]}{.name}{"\t"}{.state}{"\n"}{end}'
kubectl logs --namespace jupyterhub <user-pod> --container block-cloud-metadata
kubectl logs --namespace jupyterhub <user-pod> --container block-cloud-metadata --previous
kubectl get events --namespace jupyterhub \
  --field-selector involvedObject.name=<user-pod> \
  --sort-by=.metadata.creationTimestamp
```

Repair the reported image-pull, iptables, capability, runtime, or admission problem. Do not disable metadata blocking as an immediate fix. Return to the {ref}`preflight decision <existing-kubernetes-preflight>` and disable it only after a replacement passes {ref}`end-to-end acceptance <existing-kubernetes-end-to-end-acceptance>`.

### GPU Resources Or Labels Are Missing

```bash
kubectl get pods -A | grep -E 'amd|gpu'
kubectl describe node <gpu-node> | grep -A12 'Allocatable'
kubectl get node <gpu-node> --show-labels | grep 'amd.com/gpu'
```

A healthy GPU node needs both a matching product label and non-zero allocatable `amd.com/gpu`. Repair the one selected management path and its host compatibility. Do not install the second path as a workaround or change selectors to labels the node does not report.

### PVCs Stay Pending

```bash
kubectl get storageclass
kubectl get pvc --namespace jupyterhub
kubectl describe pvc --namespace jupyterhub <pending-pvc>
```

Check the class name, provisioner events, access mode, topology, capacity, attachment, and mount errors with the storage operator. Changing the class does not migrate data; back up and plan a separate migration when required.

### Images Do Not Pull

```bash
kubectl describe pod --namespace jupyterhub <pod-name>
kubectl get secrets --namespace jupyterhub
```

Events distinguish invalid references, architecture mismatch, registry reachability, missing pull Secrets, and rejected credentials. Fix the approved image or Secret while keeping resource, accelerator, and pre-puller images aligned. Do not expose credentials or replace an immutable reference with a mutable tag as a shortcut.

### External Access Fails

```bash
kubectl get service,ingress --namespace jupyterhub -o wide
kubectl describe service --namespace jupyterhub proxy-public
kubectl get events --namespace jupyterhub --sort-by=.metadata.creationTimestamp
```

Inspect the proxy Service, ingress status, controller events, TLS Secret, hostname, DNS, and callback URL. Repair the site's load balancer, ingress controller, certificates, firewall, or DNS through its owning procedure. Keep the proxy private and development authentication unexposed until the production path works.
