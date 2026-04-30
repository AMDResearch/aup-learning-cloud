# Configuration Reference: `runtime/values.yaml`

This page describes the main configuration surfaces used by AUP Learning Cloud.

The most important distinction is:

- `runtime/chart/values.yaml` defines chart defaults and the full supported schema
- `runtime/values.yaml` provides the repository's current deployment defaults
- `runtime/values-multi-nodes.yaml.example` is a standalone starting point for multi-node installs

## Quick Reference

### Single-Node Runtime Update

```bash
sudo ./auplc-installer rt upgrade
```

### Direct Helm Upgrade

```bash
cd runtime
helm upgrade --install jupyterhub ./chart \
  -n jupyterhub --create-namespace \
  -f values.yaml
```

---

## 1. `custom.authMode`

```yaml
custom:
  authMode: "auto-login"
```

Supported values:

| Value | Meaning |
|------|---------|
| `auto-login` | Shared no-credential local mode |
| `dummy` | Testing-only any-user mode |
| `github` | GitHub OAuth only |
| `multi` | GitHub OAuth plus native accounts |

## 2. `custom.adminUser`

```yaml
custom:
  adminUser:
    enabled: false
```

If enabled, the chart creates the `jupyterhub-admin-credentials` secret and bootstraps the `admin` user. This is optional and currently disabled in the checked-in defaults.

## 3. `custom.githubOrgName`

```yaml
custom:
  githubOrgName: "your-github-org"
```

Used by the Hub's GitHub team synchronization logic. This is especially relevant in `github` and `multi` auth modes.

## 4. `custom.gitClone`

```yaml
custom:
  gitClone:
    githubAppName: ""
    defaultAccessToken: ""
    allowedProviders:
      - github.com
      - gitlab.com
      - bitbucket.org
    maxCloneTimeout: 300
    initContainerImage: "alpine/git:2.47.2"
```

Key behavior:

- `githubAppName` enables GitHub App install / repo picker flows for GitHub-authenticated users
- `defaultAccessToken` provides a fallback private-repo token for all users
- token priority is GitHub OAuth token first, then `defaultAccessToken`
- a resource must also opt in with `metadata.allowGitClone: true`

## 5. `custom.accelerators`

```yaml
custom:
  accelerators:
    r9700:
      displayName: "AMD Radeon™ AI Pro R9700 (Workstation GPU)"
      description: "RDNA 4.0 (gfx1201) | Compute Units 64 | 32GB GDDR6"
      nodeSelector:
        amd.com/gpu.product-name: "AMD_Radeon_AI_PRO_R9700"
      env: {}
      quotaRate: 4
```

Supported fields:

- `displayName`
- `description`
- `nodeSelector`
- `env`
- `quotaRate`

Current checked-in values use ROCm labeller keys such as `amd.com/gpu.product-name` rather than a separate legacy `node-type` label model.

## 6. `custom.resources`

### Images

```yaml
custom:
  resources:
    images:
      cpu: "ghcr.io/amdresearch/auplc-default:latest"
      gpu: "ghcr.io/amdresearch/auplc-base:latest"
      Course-CV: "ghcr.io/amdresearch/auplc-cv:latest"
```

### Requirements

```yaml
custom:
  resources:
    requirements:
      gpu:
        cpu: "0"
        memory: "0Gi"
        amd.com/gpu: "1"
```

Recognized fields include:

- `cpu`
- `memory`
- `memory_limit`
- `amd.com/gpu`
- `amd.com/npu`

### Metadata

```yaml
custom:
  resources:
    metadata:
      gpu:
        group: "CUSTOM REPO"
        description: "Basic GPU Environment"
        subDescription: "GPU Accelerated Environment"
        accelerator: "GPU"
        acceleratorKeys:
          - strix-halo
        allowGitClone: true
        env: {}
```

Supported metadata fields:

- `group`
- `description`
- `subDescription`
- `accelerator`
- `acceleratorKeys`
- `allowGitClone`
- `env`
- `acceleratorOverrides`

`acceleratorOverrides` can override images per accelerator key, and may also override env when a deployment needs that level of control:

```yaml
custom:
  resources:
      metadata:
        Course-CV:
          acceleratorOverrides:
            r9700:
              image: "ghcr.io/your-org/auplc-cv:<tag-for-r9700>"
```

## 7. `custom.teams.mapping`

```yaml
custom:
  teams:
    mapping:
      github-users:
        - cpu
        - gpu
      native-users:
        - cpu
        - Course-CV
```

This mapping controls which resources a user can see, based on JupyterHub group membership.

## 8. `custom.quota`

```yaml
custom:
  quota:
    enabled: null
    cpuRate: 1
    minimumToStart: 10
    defaultQuota: 0
    refreshRules: {}
```

Important behavior:

- when `enabled` is `null`, quota auto-disables for `auto-login` and `dummy`
- accelerator-specific `quotaRate` values come from `custom.accelerators.*`
- `refreshRules` create CronJob-based balance refresh behavior

## 9. `custom.hub.allowedOrigins` and `custom.notebook.allowedOrigins`

```yaml
custom:
  hub:
    allowedOrigins: []
  notebook:
    allowedOrigins: []
```

- `custom.hub.allowedOrigins` adds Hub CORS headers
- `custom.notebook.allowedOrigins` is applied to notebook server startup arguments

## 10. `custom.security.publicScheme`

When TLS is terminated outside the chart, you can tell the Hub to treat the public origin as HTTPS:

```yaml
custom:
  security:
    publicScheme: "https"
```

This affects secure handling of `_xsrf` cookies.

## 11. `hub.extraFiles`

```yaml
hub:
  extraFiles:
    announcement.txt:
      mountPath: /usr/local/share/jupyterhub/static/announcement.txt
      stringData: |
        <div class="announcement-box">Notice</div>
```

Used for login / home announcements and other injected files.

## 12. `monitoring`

```yaml
monitoring:
  enabled: false
  hubMetrics:
    enabled: false
    allowUnauthenticatedScrape: false
  serviceMonitor:
    enabled: false
  grafana:
    dashboard:
      enabled: false
  prometheusRule:
    enabled: false
```

This controls Prometheus scraping and optional Grafana / alerting resources.

## 13. Local Deployment Defaults In `runtime/values.yaml`

The repository's current local defaults are:

```yaml
hub:
  db:
    pvc:
      storageClassName: local-path

singleuser:
  storage:
    dynamic:
      storageClass: local-path

proxy:
  service:
    type: NodePort
    nodePorts:
      http: 30890

ingress:
  enabled: false

prePuller:
  hook:
    enabled: false
  continuous:
    enabled: false
```

Treat NFS, ingress, TLS, and pre-pulling as opt-in deployment features unless you explicitly configure them.
