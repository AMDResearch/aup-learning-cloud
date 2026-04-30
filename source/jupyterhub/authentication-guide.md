# Authentication Guide

This guide describes the current authentication behavior of AUP Learning Cloud, including auth modes, GitHub team sync, native accounts, and admin bootstrap.

## Overview

Authentication is controlled by `custom.authMode`.

Supported modes:

| Mode | Meaning |
|------|---------|
| `auto-login` | Shared local mode with no credentials |
| `dummy` | Testing mode that accepts any username/password |
| `github` | GitHub OAuth only |
| `multi` | GitHub OAuth plus native local accounts |

The current checked-in single-node defaults use `auto-login`.

## Admin Bootstrap

Admin bootstrap is optional.

```yaml
custom:
  adminUser:
    enabled: true
```

When enabled, the Hub creates the `jupyterhub-admin-credentials` secret and bootstraps the `admin` user.

Retrieve credentials with:

```bash
kubectl -n jupyterhub get secret jupyterhub-admin-credentials \
  -o jsonpath='{.data.admin-password}' | base64 -d && echo

kubectl -n jupyterhub get secret jupyterhub-admin-credentials \
  -o jsonpath='{.data.api-token}' | base64 -d && echo
```

## GitHub OAuth

GitHub OAuth configuration lives under `hub.config.GitHubOAuthenticator`.

```yaml
custom:
  githubOrgName: "your-github-org"

hub:
  config:
    GitHubOAuthenticator:
      oauth_callback_url: "https://your.domain.com/hub/github/oauth_callback"
      client_id: "TODO"
      client_secret: "TODO"
      allowed_organizations:
        - your-github-org
      scope:
        - read:user
        - read:org
```

### GitHub Team Sync

In GitHub-backed deployments, the Hub can:

- fetch the user's team memberships during login
- refresh team memberships again at spawn time
- map those teams into JupyterHub groups
- use group membership to control visible resources

The org name used for synchronization comes from `custom.githubOrgName`.

## GitHub App Integration For Repositories

GitHub App integration is optional and is related to private repository cloning, not to basic OAuth login itself.

```yaml
custom:
  gitClone:
    githubAppName: "your-app-slug"
```

When configured, GitHub-authenticated users can install or authorize the app and use repo-picker flows on the spawn page.

For setup instructions, see [GitHub App Setup](github-oauth-setup.md).

## Native Accounts

Native accounts are used in `multi` mode.

Important behavior:

- users cannot self-register arbitrarily
- admins can create users from the web admin console or CLI scripts
- native passwords can be reset by admins
- users can be forced to change password on next login

## Group-Based Resource Access

Resource visibility is controlled by `custom.teams.mapping`.

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

GitHub-synced groups and system-managed groups have protection rules in the admin surface.

## Recommended Operational Flow

### Single-Node

After editing auth-related values, redeploy with:

```bash
sudo ./auplc-installer rt upgrade
```

### Manual / Multi-Node Helm

```bash
cd runtime
helm upgrade --install jupyterhub ./chart \
  -n jupyterhub --create-namespace \
  -f values-multi-nodes.yaml
```

## Troubleshooting

### GitHub Users Do Not See Expected Resources

Check:

- `custom.githubOrgName`
- `hub.config.GitHubOAuthenticator.allowed_organizations`
- `custom.teams.mapping`

### No Admin User Was Created

Confirm that `custom.adminUser.enabled: true` is set, then restart or upgrade the runtime.

### Native Users Cannot Log In

Confirm the deployment is using `multi` mode and that the user was created by an administrator.

## Related Documentation

- [GitHub App Setup](github-oauth-setup.md)
- [User Management Guide](user-management.md)
- [Configuration Reference](configuration-reference.md)
