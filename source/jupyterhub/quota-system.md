# User Quota System

The quota system tracks usage sessions and can block new spawns when a user lacks enough balance.

## What Quota Controls

When quota is enabled, the current flow is:

1. a user chooses a resource and runtime on the spawn page
2. the Hub computes the estimated cost from the selected accelerator rate and runtime
3. the Hub blocks the spawn if the user cannot afford it
4. a usage session is recorded while the server runs
5. quota is deducted when the session ends

## Configuration

Quota is configured under `custom.quota`.

```yaml
custom:
  quota:
    enabled: null
    cpuRate: 1
    minimumToStart: 10
    defaultQuota: 0
    refreshRules: {}
```

### Field Meanings

| Field | Meaning |
|------|---------|
| `enabled` | Explicit on/off. When `null`, quota auto-disables for `auto-login` and `dummy` |
| `cpuRate` | Per-minute cost for CPU-only sessions |
| `minimumToStart` | Minimum balance required before any spawn can start |
| `defaultQuota` | Initial balance granted to new users when their quota record is created |
| `refreshRules` | Scheduled balance refresh rules implemented as CronJobs |

## Accelerator Rates

Accelerator-specific rates come from `custom.accelerators.*.quotaRate`.

```yaml
custom:
  accelerators:
    strix-halo:
      quotaRate: 3
    r9700:
      quotaRate: 4
```

The effective estimated cost is:

```text
quota cost = runtime_minutes × selected accelerator rate
```

If no accelerator is selected, the CPU rate is used.

## Auto-Enable Behavior

When `custom.quota.enabled` is left as `null`:

- `auto-login` and `dummy` default to quota disabled
- `github` and `multi` default to quota enabled

## Unlimited Quota

The platform supports unlimited users.

In the current admin UI, unlimited quota can be set by entering:

- `-1`
- `∞`
- `unlimited`

## Web Admin Operations

The current `/hub/admin/users` page supports:

- inline per-user quota editing
- batch quota updates for selected users
- toggling unlimited quota
- viewing current balances alongside server status

The admin UI also includes a **Refresh Quota** action that can apply a global add-or-set operation to all users.

## Scheduled Quota Refresh Rules

`refreshRules` allow periodic top-ups or resets.

Example:

```yaml
custom:
  quota:
    refreshRules:
      daily-topup:
        enabled: true
        schedule: "0 0 * * *"
        action: add
        amount: 100
        maxBalance: 500
        targets:
          includeUnlimited: false
          balanceBelow: 400
```

These rules create Kubernetes CronJobs during deployment.

Useful verification commands:

```bash
kubectl -n jupyterhub get cronjobs -l app.kubernetes.io/component=quota-refresh
kubectl -n jupyterhub get jobs -l app.kubernetes.io/component=quota-refresh
kubectl -n jupyterhub logs -l app.kubernetes.io/component=quota-refresh --tail=50
```

## Runtime Behavior Details

Current implementation details worth knowing:

- new users get a quota record on first use
- `defaultQuota` is applied at record creation time
- usage sessions are tracked even when quota deduction is disabled
- unlimited users skip balance deduction
- insufficient balance blocks spawn before the server starts

## Recommended Deployment Flow

After changing quota configuration:

**Single-node:**

```bash
sudo ./auplc-installer rt upgrade
```

**Manual / multi-node Helm:**

```bash
cd runtime
helm upgrade --install jupyterhub ./chart \
  -n jupyterhub --create-namespace \
  -f values-multi-nodes.yaml
```

## Related Pages

- [User Management Guide](user-management.md)
- [Configuration Reference](configuration-reference.md)
