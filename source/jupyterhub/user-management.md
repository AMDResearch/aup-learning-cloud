# User Management Guide

This guide covers user management via the Admin Panel (web interface) and CLI scripts.

## Prerequisites

```bash
# Install dependencies
pip install pandas openpyxl requests
```

## Initial Setup

### Auto-Admin on Helm Install

When `custom.adminUser.enabled: true` is set in values.yaml, helm install automatically:

1. Generates random API token and admin password
2. Creates `jupyterhub-admin-credentials` secret
3. Configures `admin` user with admin privileges on hub startup

The API token is associated with the `admin` user for script operations.

**Get credentials after install:**

```bash
# Get admin password
kubectl -n jupyterhub get secret jupyterhub-admin-credentials \
  -o go-template='{{index .data "admin-password" | base64decode}}'

# Get API token
export JUPYTERHUB_TOKEN=$(kubectl -n jupyterhub get secret jupyterhub-admin-credentials \
  -o go-template='{{index .data "api-token" | base64decode}}')
```

### Manual Setup (if auto-admin disabled)

If `custom.adminUser.enabled: false`, create credentials manually:

```bash
# Create secret with random token and password
kubectl -n jupyterhub create secret generic jupyterhub-admin-credentials \
  --from-literal=api-token=$(openssl rand -hex 32) \
  --from-literal=admin-password=$(openssl rand -base64 12)

# Restart hub to apply
kubectl -n jupyterhub rollout restart deployment/hub
```

## Daily Usage

### Set Environment Variables

```bash
# Get token from Kubernetes secret
export JUPYTERHUB_TOKEN=$(kubectl -n jupyterhub get secret jupyterhub-admin-credentials \
  -o go-template='{{index .data "api-token" | base64decode}}')
export JUPYTERHUB_URL="http://localhost:30890"  # Or your hub URL
```

Or add to your shell profile (~/.bashrc or ~/.zshrc):

```bash
alias jhtoken='export JUPYTERHUB_TOKEN=$(kubectl -n jupyterhub get secret jupyterhub-admin-credentials -o go-template="{{index .data \"api-token\" | base64decode}}")'
```

## Web Interface (Admin Panel)

Access the Admin Panel at `/hub/admin/users`.

<!-- TODO: Add screenshot of the Admin Panel user list -->
<!-- ![Admin Panel User List](./images/user-1-admin-panel.png) -->

### User Table

The user table displays:
- **Username** - Click to view user details
- **Admin** - Admin status badge
- **Quota** - Current quota balance (if quota system enabled)
- **Server** - Server status (Running/Stopped)
- **Last Activity** - Last login or activity time

### Create User

1. Click **"Create Users"** button
2. Enter usernames (one per line for batch creation)
3. Choose password option:
   - **Generate random passwords** (default) - Each user gets a unique password
   - **Set password** - Enter a password for all users
4. (Optional) Check **"Force password change on first login"**
5. (Optional) Check **"Grant admin privileges"**
6. Click **"Create Users"**
7. After creation, copy the username/password table to share with users

<!-- TODO: Add screenshot of Create User modal -->
<!-- ![Create User Modal](./images/user-2-create-modal.png) -->

### Edit User

1. Click the **pencil icon** on a user row to view user details
2. Click **"Edit User"** to enter edit mode
3. Available modifications:
   - **Username** - Rename the user (warning: user must login with new name)
   - **Admin status** - Grant or revoke admin privileges
   - **Groups** - Assign user to groups
4. Click **"Save Changes"**

### Set Password

1. Click the **key icon** on a user row
2. Enter new password, or click **"Generate"** for a random password
3. (Optional) Check **"Force password change on next login"**
4. Click **"Set Password"**
5. After success, copy the password to share with the user

<!-- TODO: Add screenshot of Set Password modal -->
<!-- ![Set Password Modal](./images/user-3-password-modal.png) -->

### Server Control

- **Stop**: Click the red stop button to stop a user's running server
- **Start**: Click the green play button to start a user's server

### Batch Operations

1. Select multiple users using checkboxes
2. Available batch actions:
   - **Start All Selected** - Start servers for selected users
   - **Stop All Selected** - Stop servers for selected users
   - **Set Quota** - Set quota for selected users (see [Quota System](./quota-system.md))

<!-- TODO: Add screenshot of batch operations with multiple users selected -->
<!-- ![Batch Operations](./images/user-4-batch-operations.png) -->

### Search and Filter

- Use the search box to filter users by username
- Toggle "Only Active Servers" to show only users with running servers
- Click column headers to sort by that column

### Manage Groups

Click **"Manage Groups"** to navigate to the group management page.

## Script Usage

### 1. Generate User Templates

Create user list templates for batch operations.

```bash
# Generate 50 students
python scripts/generate_users_template.py --prefix student --count 50 --output users.csv

# Generate AUP users (AUP01, AUP02, ...)
python scripts/generate_users_template.py --prefix AUP --count 30 --start 1 --output aup_users.xlsx

# Generate with 3-digit padding
python scripts/generate_users_template.py --prefix student --count 100 --digits 3 --output users.csv

# Custom usernames
python scripts/generate_users_template.py --names alice bob charlie --output custom.csv
```

**Output format (CSV/Excel):**

```text
username,admin
student01,false
student02,false
student03,false
```

### 2. Manage Users

Perform batch operations via JupyterHub API.

```bash
# Create users from file
python scripts/manage_users.py create users.csv

# List all users
python scripts/manage_users.py list

# Export users to backup file
python scripts/manage_users.py export backup.xlsx

# Delete users (with confirmation)
python scripts/manage_users.py delete remove_list.csv

# Delete users (skip confirmation)
python scripts/manage_users.py delete remove_list.csv --yes
```

### 3. Manage Admin Privileges

Grant or revoke admin privileges for existing users.

```bash
# Grant admin to single user
python scripts/manage_users.py set-admin teacher01

# Grant admin to multiple users
python scripts/manage_users.py set-admin teacher01 teacher02 teacher03

# Grant admin from file
python scripts/manage_users.py set-admin -f admins.csv

# Revoke admin privileges
python scripts/manage_users.py set-admin --revoke student01

# Batch revoke
python scripts/manage_users.py set-admin --revoke -f demote_list.csv
```

### 4. Set Passwords

Set default passwords for users (requires kubectl access).

> **Note:** For quota management commands (`set-quota`, `add-quota`, `list-quota`), see the [User Quota System](./quota-system.md) documentation.

```bash
# Set passwords from file with password column
python scripts/manage_users.py set-passwords users_with_passwords.csv

# Generate random passwords for users
python scripts/manage_users.py set-passwords users.csv --generate -o passwords_output.csv

# Set same default password for all users
python scripts/manage_users.py set-passwords users.csv --generate --default-password "Welcome123"

# Set passwords without forcing change on first login
python scripts/manage_users.py set-passwords users.csv --no-force-change
```

## Common Workflows

### Create New Users

```bash
# Step 1: Generate template
python scripts/generate_users_template.py \
  --prefix student \
  --count 50 \
  --output new_students.csv

# Step 2: (Optional) Edit CSV to customize
# Edit new_students.csv if needed

# Step 3: Create users in JupyterHub
python scripts/manage_users.py create new_students.csv
```

**Expected output:**
```
✅ Connected to JupyterHub at http://localhost:30890
📄 Loaded 50 users from new_students.csv

🔄 Creating 50 users...
  ✅ Created user: student01 (admin=False)
  ✅ Created user: student02 (admin=False)
  ...

==================================================
📊 Results:
  ✅ Created: 50
  ⚠️  Already exist: 0
  ❌ Failed: 0
==================================================
```

### Promote Users to Admin

```bash
# Single user
python scripts/manage_users.py set-admin teacher01

# Multiple users
python scripts/manage_users.py set-admin teacher01 teacher02

# From file (any CSV with username column)
python scripts/manage_users.py set-admin -f new_admins.csv
```

### Backup Users

```bash
# Backup current users
python scripts/manage_users.py export users_backup_$(date +%Y%m%d).xlsx

# Later: restore users
python scripts/manage_users.py create users_backup_20260113.xlsx
```

### Remove Users

```bash
# Step 1: Export current users
python scripts/manage_users.py export all_users.csv

# Step 2: Edit CSV, keep only users to delete
# Create remove_list.csv with usernames to delete

# Step 3: Delete users
python scripts/manage_users.py delete remove_list.csv
```

## File Format

Both scripts support **CSV** and **Excel** (.xlsx) formats.

**Required column:**
- `username` - Username to create/delete

**Optional columns:**
- `admin` - Set to `true` for admin users (default: `false`)
- `password` - Password for set-passwords command

**Example CSV:**

```text
username,admin
student01,false
student02,false
teacher01,true
```

## Troubleshooting

### Connection Issues

**Symptom:** "Connection refused"

**Solutions:**
```bash
# Check hub is running
kubectl --namespace=jupyterhub get pods

# For local dev
export JUPYTERHUB_URL="http://localhost:30890"

# For production
export JUPYTERHUB_URL="https://your-domain.com"

# Test connection
curl $JUPYTERHUB_URL/hub/api/
```

### Authentication Issues

**Symptom:** "Authentication failed"

**Solutions:**
```bash
# Verify token is set
echo $JUPYTERHUB_TOKEN

# Test token
curl -X GET $JUPYTERHUB_URL/hub/api/ \
  -H "Authorization: token $JUPYTERHUB_TOKEN"
```

### Common Errors

**"User already exists"**
- This is just a warning, not an error
- The user is already in the system

**"File must contain 'username' column"**
- Ensure your file has a `username` column header

## Notes

- **Auto-Admin**: Initial admin is created automatically on helm install
- **Additional Admins**: Use `set-admin` command or Admin Panel
- **First Login**: Native users must set their password on first login
- **Safety**: Delete operations ask for confirmation (use `--yes` to skip)
- **Batch Size**: No limit, but larger batches (1000+) may be slow

## Help

Get detailed help for each script:

```bash
python scripts/generate_users_template.py --help
python scripts/manage_users.py --help
```
