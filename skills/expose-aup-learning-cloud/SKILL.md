---
name: expose-aup-learning-cloud
description: >-
  Group: Maintain AUP Learning Cloud. Configures how AUP Learning Cloud is
  exposed and stored for a real
  deployment: the proxy service type (NodePort vs LoadBalancer/ingress), ingress
  hostname and TLS, external-TLS handling (custom.security.publicScheme), CORS
  origins (custom.hub/notebook.allowedOrigins), and
  the shared NFS storage class for the Hub DB and user PVCs. Use when the user
  wants to put the Hub behind a domain, enable HTTPS/TLS/certificates, set up
  ingress, change the NodePort, move storage from local-path to NFS
  (nfs-client / nfs-subdir-external-provisioner), fix mixed-content / _xsrf
  cookie issues behind a reverse proxy, or allow embedding/CORS. Triggers
  include ingress.enabled, proxy.service.type, nodePorts.http, publicScheme,
  allowedOrigins, storageClassName, nfs-client, TLS, cert-manager. Do not use
  for the first cluster build (deploy-/install-aup-learning-cloud), the GitHub
  OAuth callback URL (configure-aup-learning-cloud-auth), or course/quota config
  (configure-aup-learning-cloud-courses).
---

# Expose AUP Learning Cloud

Take a deployment from the local NodePort/`local-path` defaults to a real
network and storage posture: choose how the proxy is reached (NodePort,
LoadBalancer, or ingress + TLS), tell the Hub about externally-terminated TLS,
set CORS origins, and move persistent data onto shared NFS.

Edit a **values overlay** and re-apply with Helm / the installer. NFS, ingress,
and TLS are opt-in — the checked-in defaults are a plain HTTP NodePort. The full
value blocks, the NFS provisioner setup, and troubleshooting are in
**[reference.md](reference.md)**.

## Prerequisites

- A running AUP Learning Cloud and `helm` + `kubectl` (or `./auplc-installer`).
- For ingress/TLS: an ingress controller in the cluster, a DNS record for the
  hostname, and a certificate source (cert-manager issuer or a TLS secret).
- For NFS storage: an NFS server/export reachable from every node.

## The defaults you are changing

The checked-in `runtime/values.yaml` is local-oriented: `proxy.service.type:
NodePort` on `30890`, `ingress.enabled: false`, `hub.db.pvc.storageClassName:
local-path`, `singleuser.storage.dynamic.storageClass: local-path`. Treat NFS,
ingress, and TLS as deliberate additions.

## Pick the exposure path

| Path | When | Key values |
| --- | --- | --- |
| **NodePort** (default) | Lab on a known node IP | `proxy.service.type: NodePort`, `nodePorts.http` |
| **LoadBalancer** | Cloud / MetalLB | `proxy.service.type: LoadBalancer` |
| **Ingress + TLS** | Real domain, HTTPS | `ingress.enabled: true`, host, TLS secret/issuer |

## Workflow

1. **Read current state.** Note `proxy.service`, `ingress`, the two
   `storageClassName`s, and whether TLS is terminated by the chart or upstream.
2. **Set exposure** in the overlay (one path above). For ingress, set the host
   and the TLS config; point DNS at the controller.
3. **Handle TLS termination.** If TLS terminates **outside** the chart (LB or
   external proxy), set `custom.security.publicScheme: "https"` so the Hub marks
   `_xsrf` cookies secure and builds correct https URLs.
4. **CORS / embedding (only if needed).** Add origins to
   `custom.hub.allowedOrigins` (Hub CORS) and/or `custom.notebook.allowedOrigins`
   (single-user server args). Leave empty unless something embeds the Hub.
5. **Storage (multi-node / production).** Move the Hub DB and user PVCs to
   `nfs-client`: install `nfs-subdir-external-provisioner` against your NFS
   export, then set both `storageClassName`s. Provisioner setup is in
   [reference.md](reference.md).
6. **Pre-flight the render.** `helm template jupyterhub ./runtime/chart -f
   runtime/values.yaml -f <overlay>` must succeed.
7. **Apply** with `helm upgrade --install … -n jupyterhub` (or `rt upgrade`
   single-node) and **verify**:

   ```bash
   kubectl get svc,ingress -n jupyterhub
   kubectl get storageclass
   kubectl get pvc -A
   ```

   Then load the public URL over HTTPS, log in, and confirm a spawned pod's PVC
   binds on the new storage class.

## code-server exposure safety

code-server resources run `code-server --auth none` on port `8888` and are safe
**only** behind the JupyterHub proxy's auth boundary. Never expose that pod port
directly via NodePort, LoadBalancer, or ingress. Only the JupyterHub proxy
service should be public.

## Safety

- **Changing storage class does not migrate existing data.** Switching
  `storageClassName` affects new PVCs; the Hub DB PVC and user homes do not move
  automatically. Plan a migration/backup before changing it on a live Hub —
  confirm with the user.
- **Editing `/etc/exports` + restarting `nfs-kernel-server`** is disruptive;
  gate it (see deploy/troubleshoot skills for the NFS host side).
- **Exposing to the internet raises the stakes** — pair with HTTPS, a real auth
  mode (configure-auth), and never expose code-server's raw port.
- A `helm upgrade` restarts the Hub pod (brief login blip).
- Never commit TLS private keys or put them in tracked values; use a K8s secret.

## Reference

NodePort/LoadBalancer/ingress value blocks, TLS + cert-manager options,
`publicScheme`/`allowedOrigins`, the NFS provisioner install and default-class
patch, and troubleshooting: [reference.md](reference.md).
