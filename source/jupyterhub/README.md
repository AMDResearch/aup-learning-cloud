# JupyterHub Configuration Guide

## Documentation

- [Authentication Guide](./authentication-guide.md) - Authentication modes, GitHub org sync, native accounts, and admin bootstrap
- [User Management Guide](./user-management.md) - Admin console and CLI-based user operations
- [User Quota System](./quota-system.md) - Quota balances, rates, refresh rules, and admin actions
- [Monitoring Deployment Guide](./monitoring.md) - Prometheus, Grafana, ServiceMonitor, dashboard, and alert setup
- [GitHub App Setup](./github-oauth-setup.md) - Optional GitHub App integration for private repository access
- [Configuration Reference](./configuration-reference.md) - Detailed `runtime/values.yaml` and chart configuration

---

## Configuration Files Overview

The Hub runtime is configured through layered Helm values.

| File | Purpose |
|------|---------|
| `runtime/chart/values.yaml` | Chart defaults and schema source |
| `runtime/values.yaml` | Current single-node oriented deployment defaults in this repository |
| `runtime/values.local.yaml` | Optional local overrides (typically gitignored) |
| `runtime/values-multi-nodes.yaml.example` | Standalone multi-node example values file |

### Helm Merge Behavior

- **Maps / objects** are merged.
- **Arrays / lists** are replaced.

That means overriding `custom.teams.mapping.gpu` replaces the whole list, not just one item.

---

## Current Platform Surfaces

### Authentication

The current Hub supports four auth modes via `custom.authMode`:

- `auto-login` - Automatically logs everyone in as a shared user for simple installs
- `dummy` - Accepts any username/password for testing only
- `github` - GitHub OAuth only
- `multi` - GitHub OAuth plus native local accounts on a single login page

In GitHub-backed modes, the Hub can also sync GitHub team membership into JupyterHub groups and use those groups for resource visibility.

### Spawn Experience

The spawn page is no longer just an image chooser. It can present:

- grouped resources from `custom.resources.metadata`
- accelerator-specific options from `custom.accelerators`
- team-filtered resource visibility from `custom.teams.mapping`
- quota-aware runtime limits
- optional Git URL validation and clone-at-start behavior
- GitHub App repo picker support when `custom.gitClone.githubAppName` is configured

### Admin Console

The React admin console under `/hub/admin` has three main areas:

- **Users** - Create users, reset passwords, edit quota, start/stop servers, inspect usage
- **Groups** - Manage manually controlled groups, inspect GitHub-synced groups, review resource mappings
- **Dashboard** - View summary cards, resource usage, top users, active sessions, and pending spawns

The native JupyterHub group APIs are also wrapped so GitHub-synced or otherwise protected groups cannot be modified the same way as ordinary manual groups.

### Announcements and Onboarding

Announcements can be injected through `hub.extraFiles.announcement.txt`. The home page also includes a dismissible onboarding flow backed by Hub APIs.

### Monitoring

The chart supports Prometheus metrics, ServiceMonitor, PrometheusRule, and Grafana dashboard installation through the `monitoring.*` values.

---

## Current Deployment Defaults In This Repository

The checked-in `runtime/values.yaml` currently describes a simple local deployment:

- `proxy.service.type: NodePort`
- `proxy.service.nodePorts.http: 30890`
- `ingress.enabled: false`
- `hub.db.pvc.storageClassName: local-path`
- `singleuser.storage.dynamic.storageClass: local-path`
- `prePuller.hook.enabled: false`
- `prePuller.continuous.enabled: false`

So the default local workflow in this repository is HTTP + NodePort + local-path storage, not ingress + TLS + NFS.

---

## Common Configuration Areas

### Resources And Accelerators

The main resource model spans four related sections:

- `custom.accelerators`
- `custom.resources.images`
- `custom.resources.requirements`
- `custom.resources.metadata`

In practice:

- accelerators define selectable hardware classes and node selectors
- images define notebook images
- requirements define resource requests and limits
- metadata controls how entries appear on the spawn page

### Team-Based Access Control

`custom.teams.mapping` decides which groups can see which resources.

Typical sources of groups are:

- `github-users` for GitHub-authenticated users
- GitHub team names synchronized from `custom.githubOrgName`
- `native-users` for local users in `multi` mode
- manual groups created by administrators

### Quota And Runtime Controls

Quota behavior is driven by `custom.quota` and per-accelerator `quotaRate` fields.

The current implementation supports:

- automatic enable/disable defaults based on auth mode
- per-resource cost estimation before spawn
- `minimumToStart`
- `defaultQuota`
- scheduled refresh rules through CronJobs
- unlimited users

See [User Quota System](./quota-system.md) for the operational details.

### Git Clone At Spawn Time

When a resource metadata entry enables `allowGitClone`, users can provide a repository URL on the spawn page.

`custom.gitClone` controls:

- allowed providers
- clone timeout
- init container image
- optional GitHub App support
- optional default access token for shared private-repo access

---

## Common Workflows

### Apply Configuration Changes

**Single-node:**

```bash
sudo ./auplc-installer rt upgrade
```

**Multi-node / manual Helm:**

```bash
cd runtime
helm upgrade --install jupyterhub ./chart \
  -n jupyterhub --create-namespace \
  -f values-multi-nodes.yaml
```

### Edit Login / Home Announcement

```yaml
hub:
  extraFiles:
    announcement.txt:
      mountPath: /usr/local/share/jupyterhub/static/announcement.txt
      stringData: |
        <div class="announcement-box">
          <h3>Welcome</h3>
          <p>Your announcement here.</p>
        </div>
```

### Enable Git Clone With GitHub App Support

```yaml
custom:
  gitClone:
    githubAppName: "your-app-slug"
    allowedProviders:
      - github.com
      - gitlab.com
      - bitbucket.org
```

For GitHub App setup details, see [GitHub App Setup](./github-oauth-setup.md).

### Verify Hub State After A Change

```bash
kubectl get pods -n jupyterhub
kubectl logs -n jupyterhub deployment/hub --tail=100
```

If quota refresh rules are enabled, also check:

```bash
kubectl get cronjobs -n jupyterhub -l app.kubernetes.io/component=quota-refresh
```

---

## Recommended Reading Order

1. Start with [Configuration Reference](./configuration-reference.md)
2. Then read [Authentication Guide](./authentication-guide.md)
3. For operator tasks, use [User Management Guide](./user-management.md)
4. For quota-enabled deployments, read [User Quota System](./quota-system.md)
5. For private repository flows, read [GitHub App Setup](./github-oauth-setup.md)
