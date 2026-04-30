# Admin Manual

This page summarizes the current administrator-facing workflows.

For value-by-value configuration, use the [Configuration Reference](../jupyterhub/configuration-reference.md).

## Admin Surfaces

### Web Admin Console

The web admin console lives at `/hub/admin` and includes:

- **Users** - create users, edit admin status, reset passwords, set quotas, start/stop servers, inspect usage
- **Groups** - review group members, manage manual groups, inspect protected GitHub/system groups, review resource mappings
- **Dashboard** - usage charts, active sessions, pending spawns, and top-user/resource views

### CLI / API-Oriented Scripts

The repository still includes script-based user management for batch workflows. Use these when you need spreadsheet-driven or repeatable operations.

## Daily Operations

### Apply Configuration Changes

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

### Rebuild Images After Image Changes

```bash
sudo ./auplc-installer img build
sudo ./auplc-installer rt reinstall
```

## Common Admin Tasks

### Create Native Users

Use the **Users** page in `/hub/admin`, or use the existing CLI scripts for bulk import.

### Reset Passwords

Native-user passwords can be reset from the admin console. This is a web UI feature now, not only a script workflow.

### Manage Groups

The **Groups** page distinguishes among:

- manually managed groups
- system-managed groups
- GitHub-synced groups

GitHub-synced and system-managed groups have protection rules; treat them differently from ad hoc manual groups.

### Manage Quota

If quota is enabled, administrators can:

- edit user balances inline
- batch update balances
- grant unlimited quota
- inspect usage detail from the admin UI

See [User Quota System](../jupyterhub/quota-system.md) for details.

### Update Login / Home Announcement

Edit `hub.extraFiles.announcement.txt.stringData` in your values file, then redeploy.

## Operational Notes

- The default checked-in single-node values use `auto-login`; many auth and admin behaviors become more relevant once you switch to `github` or `multi` mode.
- Admin bootstrap is optional; it only happens if `custom.adminUser.enabled` is turned on.
- Multi-node deployments should use the standalone `values-multi-nodes.yaml` file rather than assuming the single-node defaults apply.
