# Configuration Reference: runtime/values.yaml

This page describes how to configure the main deployment file **`runtime/values.yaml`**. This file is the environment-specific override used when deploying with Helm; all available options and defaults are defined in **`runtime/chart/values.yaml`**.

:::{important}
**File location**: The primary configuration file is **`runtime/values.yaml`** (in the repo under the `runtime/` directory; there is no `runtime/core/values.yml` path — the "core" config is this file). The Helm chart defaults live in **`runtime/chart/values.yaml`**. When you run `helm install` or `helm upgrade`, you pass `-f values.yaml` from the `runtime/` directory.
:::

## Quick reference

```bash
# Deploy from repository root (develop branch)
cd runtime
helm install jupyterhub ./chart -n jupyterhub --create-namespace -f values.yaml

# Upgrade after editing values
helm upgrade jupyterhub ./chart -n jupyterhub -f values.yaml
```

---

## 1. `custom` — AUP-specific configuration

All AUP Learning Cloud–specific behavior is under **`custom`**. These values are passed to the hub pod and used by the custom JupyterHub image.

### 1.1 `custom.authMode`

Authentication mode for the hub.

| Value | Description |
|-------|-------------|
| `auto-login` | No credentials; everyone is logged in as a single user (e.g. `student`). Best for single-node dev/demo. |
| `dummy` | Accept any username/password. For testing only. |
| `github` | GitHub OAuth only. |
| `multi` | GitHub OAuth + local (native) accounts on one login page. |

**Example:**

```yaml
custom:
  authMode: "auto-login"   # or "github", "multi", "dummy"
```

### 1.2 `custom.adminUser`

Optionally create an admin user and credentials on first install.

```yaml
custom:
  adminUser:
    enabled: false   # Set true to auto-create admin + jupyterhub-admin-credentials secret
```

When `enabled: true`, a random admin password and API token are stored in the `jupyterhub-admin-credentials` secret. See [Authentication Guide](authentication-guide.md).

### 1.3 `custom.gitClone` — Git repository cloning

Controls optional Git URL on the spawn form; the repo is cloned into the user's home at container start via an init container.

**Private repo access (two options, can be combined):**

- **GitHub App** (`githubAppName`): For GitHub OAuth users; token comes from OAuth. Requires migrating from OAuth App to GitHub App (see comments in `runtime/values.yaml`).
- **Default access token** (`defaultAccessToken`): A single PAT used for all users (including auto-login). Good for classroom/single-node when everyone needs the same private repos.

**Token priority:** OAuth token (GitHub App) &gt; `defaultAccessToken` &gt; none (public only).

```yaml
custom:
  gitClone:
    githubAppName: ""           # e.g. "aup-learning-cloud" — GitHub App slug
    defaultAccessToken: ""      # Bot PAT for all users (K8s Secret created by Helm)
    allowedProviders:
      - github.com
      - gitlab.com
      - bitbucket.org
    maxCloneTimeout: 300
    initContainerImage: "alpine/git:2.47.2"
```

### 1.4 `custom.accelerators` — GPU/NPU node types

Defines accelerator types shown in the spawn UI and used for scheduling and quota.

Each key (e.g. `strix-halo`, `dgpu`) is an accelerator **key**. Each entry can set:

- **displayName**, **description**: Shown in the UI.
- **nodeSelector**: Must match node labels so user pods land on the right hardware.
- **env**: Environment variables for the user container (e.g. `HSA_OVERRIDE_GFX_VERSION`).
- **quotaRate**: Quota consumed per minute when using this accelerator.

**Example:**

```yaml
custom:
  accelerators:
    strix-halo:
      displayName: "AMD Radeon™ 8060S (Strix Halo iGPU)"
      description: "RDNA 3.5 (gfx1151) | Compute Units 40 | 64GB LPDDR5X"
      nodeSelector:
        node-type: strix-halo
      env: {}
      quotaRate: 3
    dgpu:
      displayName: "AMD Radeon™ 9070XT (Desktop GPU)"
      description: "RDNA 4.0 (gfx1201) | ..."
      nodeSelector:
        node-type: dgpu
      env: {}
      quotaRate: 4
```

Ensure your nodes are labeled (e.g. `kubectl label nodes <name> node-type=strix-halo`).

### 1.5 `custom.resources` — Course images and options

Three sub-sections: **images**, **requirements**, **metadata**.

**`custom.resources.images`**  
Maps logical names (e.g. `cpu`, `Course-CV`) to container images.

```yaml
custom:
  resources:
    images:
      cpu: "ghcr.io/amdresearch/auplc-default:latest"
      gpu: "ghcr.io/amdresearch/base-gfx1151:v0.1-full"
      Course-CV: "ghcr.io/amdresearch/auplc-cv:latest"
      Course-DL: "ghcr.io/amdresearch/auplc-dl:latest"
      Course-LLM: "ghcr.io/amdresearch/auplc-llm:latest"
      Course-PhySim: "ghcr.io/amdresearch/auplc-physim:latest"
```

**`custom.resources.requirements`**  
Kubernetes resource requests/limits per profile (same keys as `images`).

```yaml
custom:
  resources:
    requirements:
      cpu:
        cpu: "2"
        memory: "4Gi"
        memory_limit: "6Gi"
      gpu:
        cpu: "4"
        memory: "16Gi"
        memory_limit: "24Gi"
        amd.com/gpu: "1"
      Course-CV:
        cpu: "4"
        memory: "16Gi"
        memory_limit: "24Gi"
        amd.com/gpu: "1"
      # ... same pattern for other courses
      none:
        cpu: "2"
        memory: "4Gi"
        memory_limit: "6Gi"
```

**`custom.resources.metadata`**  
UI text and behavior for each profile (group, description, which accelerators, allow Git clone).

```yaml
custom:
  resources:
    metadata:
      cpu:
        group: "CUSTOM REPO"
        description: "Basic Python Environment"
        subDescription: "CPU Only Environment"
        accelerator: ""
        acceleratorKeys: []
        allowGitClone: true
      Course-CV:
        group: "COURSE"
        description: "Computer Vision Course"
        subDescription: "Suitable for CV experiments with GPU"
        accelerator: "GPU"
        acceleratorKeys:
          - strix-halo
        allowGitClone: true   # if applicable
```

### 1.6 `custom.teams.mapping` — Team → course access

Maps **team names** (from auth, e.g. GitHub teams or native groups) to a list of **resource keys** (from `custom.resources.images` / `metadata`).

```yaml
custom:
  teams:
    mapping:
      cpu:
        - cpu
      gpu:
        - Course-CV
        - Course-DL
        - Course-LLM
        - Course-PhySim
      official:
        - cpu
        - gpu
        - Course-CV
        - Course-DL
        - Course-LLM
        - Course-PhySim
      AUP:
        - Course-CV
        - Course-DL
        - Course-LLM
        - Course-PhySim
      native-users:
        - Course-CV
        - Course-DL
        - Course-LLM
```

Users in a team only see and can spawn the listed profiles.

### 1.7 `custom.quota` — Quota system

See [User Quota System](quota-system.md) for full detail. Summary:

```yaml
custom:
  quota:
    enabled: null        # null = auto (on for github/multi, off for auto-login/dummy)
    cpuRate: 1           # Quota per minute for CPU-only
    minimumToStart: 10   # Minimum balance to start any container
    defaultQuota: 0      # Initial quota for new users (0 = none)
    refreshRules: {}     # CronJobs for periodic top-up/reset (see quota-system.md)
```

---

## 2. `hub` — JupyterHub pod

### 2.1 Database and image

```yaml
hub:
  db:
    pvc:
      storageClassName: local-path   # Use K3s local-path (single-node) or your StorageClass
  image:
    name: ghcr.io/amdresearch/auplc-hub
    tag: latest
    pullPolicy: IfNotPresent
```

### 2.2 `hub.extraConfig`

Additional Python config (snippets) executed after the core setup. Use for one-off JupyterHub/traitlets settings.

```yaml
hub:
  extraConfig: {}
  # Example:
  # extraConfig:
  #   myconfig: |
  #     c.JupyterHub.some_setting = "value"
```

### 2.3 `hub.extraFiles`

Inject files into the hub container (e.g. announcement HTML, custom templates).

```yaml
hub:
  extraFiles:
    announcement.txt:
      mountPath: /usr/local/share/jupyterhub/static/announcement.txt
      stringData: |
        <div class="announcement-box">...</div>
```

### 2.4 `hub.config` — JupyterHub and authenticator config

This is the main place for **JupyterHub**, **Authenticator**, **KubeSpawner**, and **GitHub OAuth** settings. Keys are class names; values are traitlets.

**Typical sections:**

```yaml
hub:
  config:
    Authenticator:
      allow_all: true   # For dummy/auto-login
    GitHubOAuthenticator:
      oauth_callback_url: "https://<Your.domain>/hub/github/oauth_callback"
      client_id: "TODO"
      client_secret: "TODO"
      allowed_organizations:
        - <YOUR-ORG-NAME>
      scope: []  # GitHub App uses App-level permissions, not OAuth scopes
    KubeSpawner:
      image_pull_policy: IfNotPresent
```

See [GitHub OAuth Setup](github-oauth-setup.md) and [Authentication Guide](authentication-guide.md).

---

## 3. `singleuser` — User notebook pods

### 3.1 Storage

User home directory persistence. For single-node K3s, `local-path` is typical.

```yaml
singleuser:
  storage:
    dynamic:
      storageClass: local-path
```

For multi-node or NFS, set `storageClass` to your provisioner (e.g. `nfs-client`).

---

## 4. `proxy` — Access (NodePort or LoadBalancer)

**NodePort (single-node / dev):**

```yaml
proxy:
  service:
    type: NodePort
    nodePorts:
      http: 30890
```

Access at `http://<node-ip>:30890`.

**LoadBalancer / Ingress:** Use `type: LoadBalancer` or leave default and use `ingress` below.

---

## 5. `ingress`

For NodePort-only access, disable ingress:

```yaml
ingress:
  enabled: false
```

For domain-based access, enable and set hosts/TLS; see [README](README.md) network examples.

---

## 6. `prePuller` — Image pre-pulling

Pre-pulling can speed up first spawn; for dev it’s often disabled to speed up deploy.

```yaml
prePuller:
  hook:
    enabled: false
  continuous:
    enabled: false
```

To pre-pull images, set `hook.enabled` and/or `continuous.enabled` to `true` and (if needed) add `prePuller.extraImages` with the same image list you use in `custom.resources.images`.

---

## 7. Suggested workflow for editing `runtime/values.yaml`

1. **Auth**: Set `custom.authMode` and, for GitHub, `hub.config.GitHubOAuthenticator` (and optionally `custom.gitClone.githubAppName`).
2. **Admin**: Set `custom.adminUser.enabled` if you want auto-created admin credentials.
3. **Courses**: Add or change entries in `custom.resources.images`, `requirements`, and `metadata`, and ensure `custom.teams.mapping` grants the right teams access.
4. **Accelerators**: Match `custom.accelerators` to your node labels and quota; set `quotaRate` per accelerator.
5. **Quota**: Tune `custom.quota` and, if needed, `refreshRules` (see [quota-system](quota-system.md)).
6. **Storage**: Set `hub.db.pvc.storageClassName` and `singleuser.storage.dynamic.storageClass` (e.g. `local-path` for K3s).
7. **Access**: Choose NodePort (`proxy.service.type: NodePort`, `ingress.enabled: false`) or domain + ingress.
8. **Announcement / branding**: Edit `hub.extraFiles.announcement.txt` (or add more `extraFiles`).

After any change, run from `runtime/`:

```bash
helm upgrade jupyterhub ./chart -n jupyterhub -f values.yaml
```

---

## 8. Recommendations and best practices

- **Version images explicitly**: Prefer tags like `v1.0` over `latest` in `custom.resources.images` and `hub.image.tag` for reproducible deployments.
- **Secrets**: Do not commit real `client_secret`, `defaultAccessToken`, or passwords. Use a separate `values-local.yaml` or `--set` / sealed secrets / external secrets.
- **Quota**: For production with real users, enable quota (`custom.quota.enabled: true` if not using auto-login/dummy) and set `defaultQuota` or use `refreshRules` so users receive allocations.
- **Node labels**: Ensure every GPU/NPU node has the labels referenced in `custom.accelerators.*.nodeSelector` so scheduling works.
- **Teams**: Keep `custom.teams.mapping` in sync with your GitHub org/teams or native group naming so users see the correct course list.
- **Backup**: Back up the hub DB PVC (and any NFS storage) before major upgrades or config changes.

For more detail on auth, quotas, and OAuth, see the other guides in this section.
