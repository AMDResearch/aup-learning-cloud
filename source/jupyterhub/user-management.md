# User Management Guide

This guide covers the current user-management surfaces in AUP Learning Cloud.

There are now two real workflows:

- **Web admin console** at `/hub/admin`
- **CLI scripts** for spreadsheet-driven bulk operations

The web console is now the primary day-to-day interface.

## Admin Bootstrap

If you want the chart to create the initial admin credentials automatically:

```yaml
custom:
  adminUser:
    enabled: true
```

Then retrieve the credentials with:

```bash
kubectl -n jupyterhub get secret jupyterhub-admin-credentials \
  -o jsonpath='{.data.admin-password}' | base64 -d && echo

kubectl -n jupyterhub get secret jupyterhub-admin-credentials \
  -o jsonpath='{.data.api-token}' | base64 -d && echo
```

## Web Admin Console

Open `/hub/admin` after logging in as an admin user.

### Users View

The **Users** page supports:

- searching and paging users
- filtering to users with active servers
- inline quota editing when quota is enabled
- starting and stopping user servers
- creating native users
- editing user details
- resetting passwords for native users
- batch password reset for selected native users
- batch quota update for selected users
- batch delete for deletable users
- opening a per-user usage detail view

Important behavior from the current implementation:

- admin users and the currently logged-in admin are protected from deletion
- password reset actions apply only to native users
- unlimited quota can be entered with `-1`, `∞`, or `unlimited`

### Groups View

The **Groups** page distinguishes among:

- **GitHub-synced groups**
- **system-managed groups**
- **manual groups**

It supports:

- creating manual groups
- searching groups
- editing group properties
- reviewing group-to-resource mappings
- adding and removing users from editable groups
- manual GitHub sync through **Sync Now** when `custom.githubOrgName` is configured

Current protection model:

- **system-managed groups** are read-only for membership edits
- **GitHub-synced groups** are protected from deletion, but admins can still add extra users manually

### Dashboard View

The **Dashboard** page provides:

- total users
- active sessions
- total usage minutes
- active users this week
- usage trends
- resource distribution
- top-user views
- live active sessions
- pending spawns

Use this as the primary operational view for current platform usage.

## CLI Scripts

The repository still includes CLI tools for bulk management.

Common examples:

```bash
# Generate a CSV template
python scripts/generate_users_template.py --prefix student --count 50 --output users.csv

# Create users from a file
python scripts/manage_users.py create users.csv

# List users
python scripts/manage_users.py list

# Export users
python scripts/manage_users.py export backup.xlsx

# Promote admins
python scripts/manage_users.py set-admin teacher01 teacher02

# Revoke admin
python scripts/manage_users.py set-admin --revoke student01

# Set passwords from file
python scripts/manage_users.py set-passwords users.csv --generate -o passwords_output.csv

# Delete users
python scripts/manage_users.py delete remove_list.csv --yes
```

These scripts are still useful for class onboarding or spreadsheet-managed user lists.

## Recommended Operational Flow

### Single-Node

After config changes:

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

## Related Pages

- [Authentication Guide](authentication-guide.md)
- [User Quota System](quota-system.md)
- [Configuration Reference](configuration-reference.md)
