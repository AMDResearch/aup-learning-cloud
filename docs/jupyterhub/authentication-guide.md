# Authentication Guide

This guide covers the dual authentication system and user management for AUP Learning Cloud.

## Table of Contents

- [Overview](#overview)
- [Authentication Methods](#authentication-methods)
- [Configuration](#configuration)
- [Admin Management](#admin-management)
- [User Management](#user-management)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)

## Overview

AUP Learning Cloud supports **dual authentication** to accommodate different user types:

1. **GitHub OAuth**: For technical teams and organization members
2. **Native Authenticator**: For students and external users (admin-managed accounts)

### Key Features

- **Auto-admin on install**: Initial admin created automatically with random password
- **No self-registration**: Only admins can create native accounts
- **Individual passwords**: Each user has their own password (can be changed)
- **Unified admin panel**: All users managed in `/hub/admin`
- **Batch operations**: CSV/Excel-based bulk user management
- **Script-based admin management**: Use `set-admin` command

## Authentication Methods

### Comparison

| Feature | GitHub OAuth | Native Authenticator |
|---------|--------------|---------------------|
| **User Type** | Technical teams, org members | Students, external users |
| **Account Creation** | GitHub organization invite | Admin creates manually |
| **Password** | Managed by GitHub | User-defined (changeable) |
| **Access Control** | Based on GitHub teams | Based on username patterns or groups |
| **Best For** | Staff, developers, researchers | Course students, temporary users |

### Login Flow

Users see a combined login page with GitHub OAuth button and native login form:

```
┌─────────────────────────────────┐
│  JupyterHub Login               │
├─────────────────────────────────┤
│  [ Sign in with GitHub ]        │ ← GitHub OAuth
│                                 │
│  ─── Or use local account ───   │
│                                 │
│  Username: [____________]       │
│  Password: [____________]       │ ← Native Auth
│  [ Sign In ]                    │
└─────────────────────────────────┘
```

## Configuration

### Enable Auto-Admin (Recommended)

In `runtime/values.yaml` or `runtime/values-local.yaml`:

```yaml
custom:
  adminUser:
    enabled: true    # Auto-create admin on helm install
```

This automatically:
1. Generates random API token and admin password
2. Creates `jupyterhub-admin-credentials` secret
3. Configures `admin` user with admin privileges on hub startup

The API token is associated with the `admin` user for script operations.

### Get Credentials After Install

```bash
# Get admin password
kubectl -n jupyterhub get secret jupyterhub-admin-credentials \
  -o go-template='{{index .data "admin-password" | base64decode}}'

# Get API token for scripts
export JUPYTERHUB_TOKEN=$(kubectl -n jupyterhub get secret jupyterhub-admin-credentials \
  -o go-template='{{index .data "api-token" | base64decode}}')
```

### Resource Access Mapping

Configure which resources different user groups can access in `jupyterhub_config.py`:

```python
TEAM_RESOURCE_MAPPING = {
    "cpu": ["cpu"],
    "gpu": ["Course-CV","Course-DL","Course-LLM"],
    "official": ["cpu", "Course-CV","Course-DL","Course-LLM"],
    "AUP": ["Course-CV","Course-DL","Course-LLM"],
    "native-users": ["Course-CV","Course-DL","Course-LLM"]
}
```

### Native Authenticator Settings

The `CustomFirstUseAuthenticator` class settings:

```python
class CustomFirstUseAuthenticator(FirstUseAuthenticator):
    service_name = "Native"
    create_users = False  # Only admin-created users can login
```

**Important**: `create_users = False` prevents users from creating accounts themselves. Users must be created by an admin first.

## Admin Management

### Initial Admin

Created automatically on `helm install` when `custom.adminUser.enabled: true`.

### Adding More Admins

Use the `set-admin` command (NOT config files):

```bash
# Grant admin to users
python scripts/manage_users.py set-admin teacher01 teacher02

# Grant admin from file
python scripts/manage_users.py set-admin -f new_admins.csv

# Revoke admin
python scripts/manage_users.py set-admin --revoke student01
```

Or via Admin Panel (`/hub/admin`):
1. Click username
2. Check "Admin" checkbox
3. Save

### Admin Users Summary

| Method | When to Use |
|--------|-------------|
| `custom.adminUser.enabled: true` | Initial admin on install |
| `manage_users.py set-admin` | Add/remove admins later |
| Admin Panel `/hub/admin` | Quick single-user changes |

## User Management

### Prerequisites

Install required dependencies:

```bash
pip install pandas openpyxl requests
```

Set environment variables:

```bash
export JUPYTERHUB_URL="http://localhost:30890"  # Or your hub URL
export JUPYTERHUB_TOKEN=$(kubectl -n jupyterhub get secret jupyterhub-admin-credentials \
  -o go-template='{{index .data "api-token" | base64decode}}')
```

### Batch User Operations

For detailed batch user management, see [User Management Guide](user-management.md).

**Quick Reference**:

```bash
# Generate user template
python scripts/generate_users_template.py --prefix student --count 50 --output users.csv

# Create users from file
python scripts/manage_users.py create users.csv

# List all users
python scripts/manage_users.py list

# Grant admin privileges
python scripts/manage_users.py set-admin teacher01 teacher02

# Revoke admin privileges
python scripts/manage_users.py set-admin --revoke student01

# Export/backup users
python scripts/manage_users.py export backup.xlsx

# Delete users
python scripts/manage_users.py delete remove_list.csv
```

### Manual User Management

Via JupyterHub Admin Panel (`/hub/admin`):

1. **Add single user**: Click "Add Users" button
2. **Delete user**: Click username → "Delete User"
3. **Make admin**: Click username → Check "Admin" → "Save"
4. **Stop user server**: Click "Stop Server" button

## Deployment

### 1. Update Hub Image

The Hub Docker image must include the `jupyterhub-nativeauthenticator` dependency.

**File**: `dockerfiles/Hub/Dockerfile`

```dockerfile
RUN pip install jupyterhub-multiauthenticator jupyterhub-nativeauthenticator
```

### 2. Rebuild Hub Image

```bash
cd dockerfiles/Hub
./build.sh

# Or manually:
docker build -t ghcr.io/amdresearch/aup-jupyterhub-hub:v1.4.0-dual-auth .
docker push ghcr.io/amdresearch/aup-jupyterhub-hub:v1.4.0-dual-auth
```

### 3. Update Helm Values

**File**: `runtime/values.yaml`

```yaml
custom:
  adminUser:
    enabled: true

hub:
  image:
    name: ghcr.io/amdresearch/aup-jupyterhub-hub
    tag: v1.4.0-dual-auth
```

### 4. Deploy or Upgrade

**Production (K3s)**:

```bash
cd runtime
bash scripts/helm_upgrade.bash
```

**Local Development (Docker Desktop)**:

```bash
cd runtime
helm upgrade jupyterhub ./chart --namespace jupyterhub -f values-local.yaml
```

### 5. Verify Deployment

```bash
# Check hub pod is running
kubectl --namespace=jupyterhub get pods

# Check hub logs for admin setup
kubectl --namespace=jupyterhub logs deployment/hub | grep -i admin

# Get admin password
kubectl -n jupyterhub get secret jupyterhub-admin-credentials \
  -o jsonpath='{.data.admin-password}' | base64 -d && echo
```

## Troubleshooting

### Issue: "Module 'nativeauthenticator' not found"

**Cause**: Hub image doesn't have `jupyterhub-nativeauthenticator` installed.

**Solution**:
```bash
# Rebuild Hub image with updated Dockerfile
cd dockerfiles/Hub
./build.sh
```

### Issue: Users can self-register

**Cause**: `create_users` is not set to `False`.

**Solution**: Verify in `jupyterhub_config.py`:
```python
class CustomFirstUseAuthenticator(FirstUseAuthenticator):
    create_users = False
```

### Issue: API token authentication fails

**Symptoms**:
```
❌ Connection failed with status 403
```

**Solutions**:

1. **Verify secret exists**:
   ```bash
   kubectl -n jupyterhub get secret jupyterhub-admin-credentials
   ```

2. **Check token is loaded**:
   ```bash
   kubectl -n jupyterhub logs deployment/hub | grep "API token"
   ```

3. **Regenerate credentials**:
   ```bash
   kubectl -n jupyterhub delete secret jupyterhub-admin-credentials
   helm upgrade jupyterhub ./chart -n jupyterhub -f values-local.yaml
   ```

### Issue: Admin not created on install

**Symptoms**: No admin user after helm install.

**Solutions**:

1. **Verify config**:
   ```yaml
   custom:
     adminUser:
       enabled: true  # Must be true
   ```

2. **Check hub logs**:
   ```bash
   kubectl -n jupyterhub logs deployment/hub | grep -i "admin"
   ```

3. **Restart hub**:
   ```bash
   kubectl -n jupyterhub rollout restart deployment/hub
   ```

### Issue: Wrong resource permissions

**Symptoms**: User sees courses they shouldn't access, or missing expected courses.

**Solution**: Check resource mapping in `jupyterhub_config.py`:

```python
# Verify user's group assignment in CustomFirstUseAuthenticator
async def authenticate(self, handler, data):
    result = await super().authenticate(handler, data)
    if result:
        username = result.get("name", "").strip().upper()
        if "AUP" in username:
            result["group"] = "AUP"
        # ...

# Verify group has correct resources
TEAM_RESOURCE_MAPPING = {
    "AUP": ["Course-CV","Course-DL","Course-LLM"],
    # ...
}
```

### Issue: Users created but can't login

**Cause**: Native users must set password on first login.

**Solution**:

1. User should go to login page
2. Enter username created by admin
3. Enter desired password
4. Password is saved for future logins

**Alternative**: Set passwords via script:
```bash
python scripts/manage_users.py set-passwords users.csv --generate
```

### Issue: Batch script fails to connect

**Symptoms**:
```
❌ Connection error: Connection refused
```

**Solutions**:

1. **Verify JupyterHub URL**:
   ```bash
   # For local dev
   export JUPYTERHUB_URL="http://localhost:30890"

   # For production
   export JUPYTERHUB_URL="https://your-domain.com"
   ```

2. **Check if hub is accessible**:
   ```bash
   curl $JUPYTERHUB_URL/hub/api/
   ```

3. **Verify namespace and port forwarding** (if using kubectl):
   ```bash
   kubectl --namespace=jupyterhub port-forward service/hub 8081:8081
   export JUPYTERHUB_URL="http://localhost:8081"
   ```

## Security Best Practices

1. **Protect API tokens**:
   - Tokens are stored in Kubernetes secrets
   - Never commit tokens to git
   - Rotate tokens by deleting and recreating the secret

2. **User password policy**:
   - Encourage strong passwords
   - Consider adding password complexity requirements

3. **Admin accounts**:
   - Limit number of admin users
   - Use `set-admin` command to manage (auditable)
   - Review admin list regularly

4. **GitHub App**:
   - Create the App under the organization, not a personal account
   - Keep GitHub organization membership updated
   - Review team permissions regularly
   - Set `scope: []` — permissions are configured in the App settings

## Additional Resources

- [User Management Guide](user-management.md) - Batch user operations and scripts
- [JupyterHub Documentation](https://jupyterhub.readthedocs.io/)
- [NativeAuthenticator Documentation](https://native-authenticator.readthedocs.io/)
- [JupyterHub REST API](https://jupyterhub.readthedocs.io/en/stable/reference/rest-api.html)
- [OAuthenticator Documentation](https://oauthenticator.readthedocs.io/)
