# Expose AUP Learning Cloud — Reference

Exposure value blocks (NodePort / LoadBalancer / ingress + TLS), externally
terminated TLS, CORS origins, and the NFS storage setup. Workflow and gates are
in [SKILL.md](SKILL.md).

## Source guides

- Configuration Reference (sections 9, 10, 13): <https://amdresearch.github.io/aup-learning-cloud/jupyterhub/configuration-reference.html>
- Multi-Node Cluster Deployment (storage, ingress): <https://amdresearch.github.io/aup-learning-cloud/installation/multi-node.html>
- Single-Node Deployment (defaults): <https://amdresearch.github.io/aup-learning-cloud/installation/single-node.html>

The chart follows zero-to-jupyterhub conventions; the live
`runtime/chart/values.schema.yaml` is the source of truth.

## Local defaults (what you change)

```yaml
proxy:
  service:
    type: NodePort
    nodePorts:
      http: 30890
ingress:
  enabled: false
hub:
  db:
    pvc:
      storageClassName: local-path
singleuser:
  storage:
    dynamic:
      storageClass: local-path
```

## Exposure option A — NodePort

```yaml
proxy:
  service:
    type: NodePort
    nodePorts:
      http: 30890        # reach the Hub at http://<node-ip>:30890
```

## Exposure option B — LoadBalancer

```yaml
proxy:
  service:
    type: LoadBalancer   # cloud LB or MetalLB
    nodePorts:
      http: null
```

## Exposure option C — Ingress + TLS (production)

```yaml
proxy:
  service:
    type: ClusterIP      # ingress fronts the proxy
    nodePorts:
      http: null

ingress:
  enabled: true
  ingressClassName: traefik     # or nginx
  hosts:
    - your.domain.com
  tls:
    - hosts:
        - your.domain.com
      secretName: jupyter-tls-cert   # a K8s TLS secret, or one cert-manager creates
  # annotations:                     # e.g. cert-manager issuer
  #   cert-manager.io/cluster-issuer: letsencrypt-prod
```

Point a DNS record for `your.domain.com` at the ingress controller. Provide the
TLS secret directly, or let cert-manager mint it via the annotation + an Issuer
you manage.

## Externally terminated TLS

If TLS is terminated by something outside the chart (cloud LB, external ingress,
Cloudflare tunnel) rather than the chart's `proxy.https`, tell the Hub the
public scheme is https so `_xsrf` cookies are marked Secure and URLs are https:

```yaml
custom:
  security:
    publicScheme: "https"
```

## CORS / allowed origins

Defaults are permissive (`["*"]`); tighten them for a public deployment.

```yaml
custom:
  hub:
    allowedOrigins: ["https://portal.example.com"]   # Access-Control-Allow-Origin on Hub responses
  notebook:
    allowedOrigins: ["https://portal.example.com"]   # --ServerApp.allow_origin_pat (kernel WebSocket)
```

## Shared NFS storage

### 1. NFS server/export (on a storage/controller node)

```bash
sudo apt install nfs-kernel-server
sudo mkdir -p /nfs && sudo chown -R nobody:nogroup /nfs && sudo chmod 777 /nfs
echo "/nfs <subnet>/24(rw,sync,no_subtree_check,no_root_squash,insecure)" | sudo tee -a /etc/exports
sudo systemctl restart nfs-kernel-server
# worker nodes:
sudo apt install nfs-common
```

### 2. Provisioner (creates the `nfs-client` storage class)

```bash
helm repo add nfs-subdir-external-provisioner \
  https://kubernetes-sigs.github.io/nfs-subdir-external-provisioner/
helm repo update
helm install nfs-subdir-external-provisioner \
  nfs-subdir-external-provisioner/nfs-subdir-external-provisioner \
  --namespace nfs-provisioner --create-namespace \
  -f deploy/k8s/nfs-provisioner/values.yaml
# optional: make it default
kubectl patch storageclass nfs-client \
  -p '{"metadata":{"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'
```

### 3. Point the chart at it

```yaml
hub:
  db:
    pvc:
      storageClassName: nfs-client
singleuser:
  storage:
    dynamic:
      storageClass: nfs-client
```

Changing the class affects **new** PVCs only; existing Hub DB / user homes are
not migrated automatically.

## Apply and verify

```bash
helm template jupyterhub ./runtime/chart -f runtime/values.yaml -f <overlay> >/dev/null
helm upgrade --install jupyterhub ./runtime/chart -n jupyterhub \
  -f runtime/values.yaml -f <overlay>

kubectl get svc,ingress -n jupyterhub
kubectl get storageclass
kubectl get pvc -A
```

Load the public URL over HTTPS, log in, and confirm a spawned pod's PVC binds on
the intended storage class.

## Troubleshooting

| Symptom | Likely cause | First checks |
| --- | --- | --- |
| Ingress 404 / no route | Controller/class/host mismatch | `kubectl get ingress -n jupyterhub`; confirm `ingressClassName` + DNS |
| TLS cert not issued | cert-manager annotation/Issuer wrong, or secret missing | Describe the ingress + the Certificate; check the issuer |
| Login loops / `_xsrf` errors behind a proxy | External TLS without `publicScheme: https` | Set `custom.security.publicScheme: "https"`, re-apply |
| Mixed-content / blocked embed | `allowedOrigins` too strict/loose | Adjust `custom.hub`/`notebook.allowedOrigins` |
| PVC Pending | Storage class missing / NFS export wrong | `kubectl get storageclass`; provisioner logs; `showmount -e <nfs>` |
| code-server reachable without login | Pod port exposed directly | Only expose the JupyterHub proxy; never NodePort/ingress port `8888` |
