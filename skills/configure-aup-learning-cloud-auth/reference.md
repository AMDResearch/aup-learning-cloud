# Configure AUP Learning Cloud authentication — Reference

Full GitHub App setup, every `GitHubOAuthenticator` field, the OAuth-App →
GitHub-App migration, native accounts, admin bootstrap, and troubleshooting.
Workflow and gates are in [SKILL.md](SKILL.md).

## Source guides

- Authentication Guide: <https://amdresearch.github.io/aup-learning-cloud/jupyterhub/authentication-guide.html>
- GitHub App Setup: <https://amdresearch.github.io/aup-learning-cloud/jupyterhub/github-app-setup.html>
- Configuration Reference: <https://amdresearch.github.io/aup-learning-cloud/jupyterhub/configuration-reference.html>

The live `runtime/values.yaml` and `runtime/chart/values.schema.yaml` are the
source of truth; verify keys against them.

## 1. Provider combinations (`custom.auth`)

Choose exactly one document below. Omitted provider keys are false.

<!-- auplc-auth-examples: canonical -->
```yaml
custom:
  auth:
    autoLogin: true
---
custom:
  auth:
    dummy: true
---
custom:
  auth:
    native: true
---
custom:
  auth:
    github: true
---
custom:
  auth:
    native: true
    github: true
```

- Auto-login provides a shared session with no credentials.
- Dummy accepts any username/password and is for testing only.
- Native provides administrator-managed accounts.
- GitHub uses the GitHub App at `/hub/github/oauth_callback` in both GitHub-only
  and native-plus-GitHub modes.

GitHub users always have the local AUP Learning Cloud username
`github:<normalized-login>` in both GitHub-only and native-plus-GitHub modes.
Native users remain unprefixed. Configure GitHub `allowed_users`, `admin_users`,
`blocked_users`, and `allowed_organizations` with raw GitHub logins and
organizations, not the local `github:` username.

All five combinations use `custom.teams.mapping` and the existing fallback
groups for resource visibility. Provider selection doesn't change that policy.

## Runtime timer and credit enforcement

`custom.runtimeLimitEnabled: true` enforces each selected session duration and
automatically shuts down the session when its timer expires. `false` disables
automatic runtime shutdown. `custom.quota.enabled` controls credit enforcement
only: `true` enforces credit balances and `false` disables credit enforcement.
It never enables or disables the session timer.

The pair order below is always runtime limit first, quota second. The installer
`personal` and `local` profiles use `false/false`. Online deployment examples
use `true/true`. `true/false` keeps the timer without credit enforcement.
`false/true` is rejected by both the chart schema and Hub parser.

<!-- auplc-runtime-quota-matrix: canonical -->
```yaml
controls:
  runtimeLimitEnabled:
    true: enforce-session-timer
    false: disable-session-timer
  quota.enabled:
    true: enforce-credits
    false: disable-credit-enforcement
runtimeQuotaPairs:
  - runtimeLimitEnabled: true
    quotaEnabled: true
    valid: true
    examples: [online]
  - runtimeLimitEnabled: true
    quotaEnabled: false
    valid: true
    examples: []
  - runtimeLimitEnabled: false
    quotaEnabled: false
    valid: true
    examples: [installer-personal, installer-local]
  - runtimeLimitEnabled: false
    quotaEnabled: true
    valid: false
    examples: []
```

## 2. Admin bootstrap (`custom.adminUser`)

```yaml
custom:
  adminUser:
    enabled: true
```

Native and native plus GitHub accept the same contract. Leave `existingSecret` empty for
the chart-created `jupyterhub-admin-credentials`, or create the named external
Secret before Helm runs. An external Secret must contain `admin-password`; an
`api-token` is optional for direct Helm startup. The installer creates and
retains its external Secret for explicit local installs.
Retrieve chart-created credentials:

```bash
kubectl -n jupyterhub get secret jupyterhub-admin-credentials \
  -o jsonpath='{.data.admin-password}' | base64 -d && echo
kubectl -n jupyterhub get secret jupyterhub-admin-credentials \
  -o jsonpath='{.data.api-token}' | base64 -d && echo
```

The `admin-password` is first-run bootstrap input. It seeds a password only
when the administrator has no password row. Once that row exists, its database
hash is authoritative. Changing the Secret doesn't rotate, overwrite, or
reconcile the existing password. The separate `api-token` key delivers an API
token for scripts and isn't used by password bootstrap.

## 3. GitHub App setup

1. **Create the App under the organization** (not a personal account):
   `https://github.com/organizations/<ORG>/settings/apps/new`.
2. **Basic info:** name (e.g. `auplc-hub`), Homepage = Hub URL, **Callback URL**
   = `https://<domain>/hub/github/oauth_callback`.
3. Check **Expire user authorization tokens** and **Request user authorization
   (OAuth) during installation**. Uncheck **Webhook → Active**.
4. **Permissions:**
   - Repository → `Contents`: Read-only (private-repo cloning), `Metadata`:
     Read-only (default).
   - Organization → `Members`: **Read-only** (required for team sync/group
     mapping — without it the Hub logs `Resource not accessible by
     integration`).
5. **Installation scope:** Any account. Create the App.
6. Record **App ID**, **Client ID** (`Iv23li…`, different from App ID),
   generate a **Client secret**, and generate a **private key** (`.pem`). Mount
   the `.pem` into the Hub pod and record the path.
7. **Install the App on the org** configured as `custom.githubOrgName`; pick the
   repos users may access if private cloning is used.

## 4. GitHub App — configure the Hub

Set `oauth_callback_url` to `https://<domain>/hub/github/oauth_callback` for
both GitHub-only and native-plus-GitHub deployments.

```yaml
custom:
  auth:
    native: true
    github: true
  githubOrgName: "<YOUR-ORG-NAME>"

  gitClone:
    githubAppName: "your-app-slug"   # only if private-repo cloning is wanted (see repos skill)

hub:
  config:
    GitHubOAuthenticator:
      oauth_callback_url: "https://<domain>/hub/github/oauth_callback"
      app_id: "<GitHub App App ID>"
      installation_id: ""            # blank = auto-discover from the org installation
      private_key_file: "/path/to/mounted/github-app-private-key.pem"
      # private_key: ""              # alternative; prefer a mounted secret
      team_sync_ttl_seconds: 3600
      client_id: "<GitHub App Client ID>"
      client_secret: "<GitHub App Client Secret>"
      allowed_organizations:
        - <YOUR-ORG-NAME>
      scope: []                      # GitHub App uses App permissions, not OAuth scopes
```

`scope: []` is correct for a GitHub App. `installation_id` can stay blank when
the App is installed on the org (auto-discovered via `GET /orgs/{org}/installation`).
For GitHub-only, set `custom.auth.github: true` without `native`; keep the same
`https://<domain>/hub/github/oauth_callback` callback URL.

## 5. Team-to-group sync

The Hub lists actual org teams, intersects them with `custom.teams.mapping`,
and batches member lookups through GitHub GraphQL using the App installation
token. Team keys correspond to GitHub team slugs (e.g. `AUP` is queried as
`aup`, but the JupyterHub group stays `AUP`). Missing teams are logged and
skipped rather than failing the whole sync. Assigning *resources* to those
groups is the configure-courses skill.

GitHub users without a matched team fall into a `github-users` fallback group;
native users can be assigned `native-users`.

The same mapping and fallback resolver applies to auto-login, dummy, native,
GitHub, and native plus GitHub.

## 6. Native accounts

- The first-use authenticator sets `create_users = False` — accounts must exist
  before login (create them via the manage-users skill or `/hub/admin`).
- **Password policy:** ≥8 chars, ≥1 uppercase, ≥1 lowercase, ≥1 digit, ≥1
  special. Applies to admin-set and user-changed passwords.
- **Forced first-login change** uses `/auth/check-force-password-change` and
  `/auth/change-password`.

## 7. Migrating OAuth App → GitHub App

Keep `oauth_callback_url` and `allowed_organizations`. Change `client_id` /
`client_secret` to the App's, add `app_id`, `installation_id` (blank ok),
`private_key_file`, `team_sync_ttl_seconds`, set `scope: []`, and set
`gitClone.githubAppName`. Existing sessions keep working; new logins use the
App. Delete the old OAuth App after everyone has re-logged.

## 8. Apply and verify

```bash
# render check
helm template jupyterhub ./runtime/chart -f runtime/values.yaml -f <overlay> >/dev/null

# single-node
sudo ./auplc-installer rt upgrade
# multi-node / manual
helm upgrade --install jupyterhub ./runtime/chart -n jupyterhub \
  -f runtime/values.yaml -f <overlay>

kubectl rollout status -n jupyterhub deploy/hub
kubectl logs -n jupyterhub deployment/hub | grep -i -E 'admin|github|oauth'
```

If Helm reports a failed release, inspect it before retrying:

```bash
helm status jupyterhub -n jupyterhub
```

On a single-node host, `rt upgrade` and `rt reinstall` reuse the installer
Secret. Reusing or changing it doesn't replace an existing database password.

## One-release `authMode` migration

`custom.authMode` is accepted for one release as migration input. Don't combine
it with `custom.auth`. Translate legacy values as follows, then remove the
legacy field from the overlay:

| Legacy value | Canonical `custom.auth` |
| --- | --- |
| `auto-login` | `autoLogin: true` |
| `dummy` | `dummy: true` |
| `github` | `github: true` |
| `local` | `native: true` |
| `multi` | `native: true`, `github: true` |

```yaml
custom:
  authMode: multi
```

## Troubleshooting

| Symptom | Likely cause | First checks |
| --- | --- | --- |
| Login 404 / no login page | Dummy selected or providers don't match the deployment | Set the intended `custom.auth` flags; re-apply |
| OAuth callback error | `oauth_callback_url` mismatch | Match the App's Callback URL to GitHub-only or native plus GitHub |
| `Resource not accessible by integration` | App missing `Members: Read-only` | Add the org permission; an org owner must approve the updated install |
| GitHub users see no/wrong resources | `githubOrgName`, `allowed_organizations`, `teams.mapping`, or team membership | Verify all four; confirm the user's GitHub teams |
| Configured team skipped in sync | Team doesn't exist on GitHub | The Hub only syncs teams that exist; create it or fix the key |
| Installation token unavailable | `app_id`/`private_key_file` wrong or App not installed on org | Verify both and the org installation |
| No admin user created | `custom.adminUser.enabled` not true | Set it, re-apply, `kubectl logs … | grep -i admin` |
| Native user can't log in | Native isn't enabled, user not pre-created, or no password | Confirm `custom.auth.native: true` and that an admin created the account |
| Password change keeps failing | New password fails the strength policy | Re-check length + upper/lower/digit/special |
