<!-- Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.  Portions of this notebook consist of AI-generated content. -->
<!--
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
-->



# JupyterHub Configuration Guide

## Documentation

- [Authentication Guide](./authentication-guide.md) - Setup GitHub OAuth and native authentication
- [User Management Guide](./user-management.md) - Batch user operations with scripts
- [User Quota System](./quota-system.md) - Resource usage tracking and quota management
- [GitHub OAuth Setup](./github-oauth-setup.md) - Step-by-step OAuth configuration

---

# How to set up runtime/values.yaml

The main deployment configuration file is **`runtime/values.yaml`** (in the repository root under the `runtime/` directory). For a complete field-by-field reference of every section, see [Configuration Reference: runtime/values.yaml](configuration-reference.md).

## PrePuller settings

Example:
```yml
prePuller:
  extraImages:
    aup-cpu-notebook:
      name: ghcr.io/amdresearch/aup-cpu-notebook
      tag: v1.0
    ...

    #for frontpage
    aup-jupyterhub-hub:
      name: ghcr.io/amdresearch/aup-jupyterhub-hub
      tag: v1.3.5-multilogin
```

It is recommended to include as many images as you plan to deploy. This section ensures that all images are pre-downloaded on each node, preventing delays during container startup due to image downloads.

## Network settings

Two access methods are supported:

1. NodePort access via `<ip>:<port>` (port > 30000)
2. Domain access (Default) `<Your.domain>`

Example NodePort setup. With this configuration, ingress should be disabled.

```yml
proxy:
  service:
    type: NodePort
    nodePorts:
      http: 30890
  chp:
    networkPolicy:
      enabled: false
ingress:
  enabled: false
  # Explicitly set the ingress class to traefik
  ingressClassName: traefik
  hosts:
  tls:
    - hosts:
      # Let K3s/Traefik auto-generate certificates with Let's Encrypt
      secretName: 
```

Example Domain setup. Note that you should obtain the domain from your IT department.
```yml
proxy:
  service:
    type: ClusterIP
# Add Ingress configuration specifically for K3s
ingress:
  enabled: true
  # Explicitly set the ingress class to traefik
  ingressClassName: traefik
  hosts:
    - <Your.domain>
  tls:
    - hosts:
        - <Your.domain>
      # Let K3s/Traefik auto-generate certificates with Let's Encrypt
      secretName: jupyter-tls-cert
```

## Hub image setup

Update this section with your built Docker image.
```yml
  image:
    name: ghcr.io/amdresearch/aup-jupyterhub-hub
    tag: v1.3.5-multilogin
    pullPolicy: IfNotPresent
    pullSecrets:
      - github-registry-secret
```

## Update Announcement on login page

Edit the stringData section with HTML content to display announcements on the login page.
```yml
  extraFiles:
    announcement.txt:
      mountPath: /usr/local/share/jupyterhub/static/announcement.txt
      stringData: |
          <div class="announcement-box" style="padding: 1em; border: 1px solid #ccc; border-radius: 6px; background-color: #f8f8f8;">
          <h3>Welcome to AUP Remote Lab!</h3>
          <p>This is a <strong>dynamic announcement</strong>.</p>
          <p>My location is on <code>runtime/values.yaml</code></p>
          <p>You can edit this via <strong>ConfigMap</strong> without rebuilding the image.</p>
          </div>
```

## Provide Github OAuth Credentials

Refer to this [article](https://discourse.jupyter.org/t/github-authentication-for-organization-teams/1209/4) for information on setting up GitHub OAuth with GitHub Organizations. 

Fill in this section with credentials from your organization's OAuth app. Please note that the `oauth_callback_url` should match your actual deployment. For a simple GitHub OAuth-only solution, use `https://<Your.domain>/hub/oauth_callback`. Since we are using `MultiAuth`, we need `github` to identify that we are using `GitHubOAuth`.
```yml
    GitHubOAuthenticator:
      oauth_callback_url: "https://<Your.domain>/hub/github/oauth_callback"
      client_id: "AAAA"
      client_secret: "BBB"
      allowed_organizations:
        - <YOUR-ORG-NAME>
      scope:
        - read:user
        - read:org
```

## NFS storage (multi-node)

For multi-node clusters using NFS, set the singleuser storage class in `runtime/values.yaml` and ensure your cluster has an NFS provisioner and StorageClass (e.g. `nfs-client`). See [Configuration Reference](configuration-reference.md) → `singleuser.storage`.

```yaml
singleuser:
  storage:
    dynamic:
      storageClass: nfs-client
```

## After

Apply changes by running from the `runtime/` directory:

```bash
helm upgrade jupyterhub ./chart -n jupyterhub -f values.yaml
```

On the develop branch, you can also use `bash scripts/helm_upgrade.bash` if available.
