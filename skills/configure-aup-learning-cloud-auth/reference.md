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

## 1. Auth modes (`custom.authMode`)

```yaml
custom:
  authMode: "auto-login"   # auto-login | dummy | github | local | multi
```

- `auto-login` — shared, no credentials. Quota auto-disables unless explicitly
  enabled. Checked-in single-node default.
- `dummy` — accepts any username/password. Testing only.
- `github` — GitHub App only. `oauth_callback_url` ends in `/hub/oauth_callback`.
- `local` — closed, administrator-managed local accounts. It requires
  `custom.adminUser.enabled: true` and a canonical username. The chart can
  create credentials or use an external Secret with `admin-password` and an
  optional `api-token`; the username always comes from
  `custom.adminUser.username`.
- `multi` — GitHub App + native accounts on one page. `oauth_callback_url` ends
  in `/hub/github/oauth_callback`.

## 2. Admin bootstrap (`custom.adminUser`)

```yaml
custom:
  adminUser:
    enabled: true
```

Without `existingSecret`, the chart creates `jupyterhub-admin-credentials` and
bootstraps the configured administrator. The installer creates and validates the
same Secret for its local lifecycle. With `existingSecret`, the external Secret
is never created or rotated by the chart and must contain `admin-password`; an
`api-token` is optional for legacy two-key Secrets. Retrieve chart-created
credentials:

```bash
kubectl -n jupyterhub get secret jupyterhub-admin-credentials \
  -o jsonpath='{.data.admin-password}' | base64 -d && echo
kubectl -n jupyterhub get secret jupyterhub-admin-credentials \
  -o jsonpath='{.data.api-token}' | base64 -d && echo
```

## 3. GitHub App — create it (github/multi)

1. **Create the App under the organization** (not a personal account):
   `https://github.com/organizations/<ORG>/settings/apps/new`.
2. **Basic info:** name (e.g. `auplc-hub`), Homepage = Hub URL, **Callback URL**
   matching the mode:
   - `multi`: `https://<domain>/hub/github/oauth_callback`
   - single `github`: `https://<domain>/hub/oauth_callback`
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

```yaml
custom:
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

## 5. Team-to-group sync

The Hub lists actual org teams, intersects them with `custom.teams.mapping`,
and batches member lookups through GitHub GraphQL using the App installation
token. Team keys correspond to GitHub team slugs (e.g. `AUP` is queried as
`aup`, but the JupyterHub group stays `AUP`). Missing teams are logged and
skipped rather than failing the whole sync. Assigning *resources* to those
groups is the configure-courses skill.

GitHub users without a matched team fall into a `github-users` fallback group;
native users can be assigned `native-users`.

## 6. Native accounts (multi)

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

On a single-node host, `rt upgrade` and `rt reinstall` retain the installer
Secret. Do not delete it unless intentionally resetting the local administrator
credentials.

## Troubleshooting

| Symptom | Likely cause | First checks |
| --- | --- | --- |
| Login 404 / no login page | `authMode: dummy`, or wrong mode for the deploy | Set `github`/`multi`/`auto-login`; re-apply |
| OAuth callback error | `oauth_callback_url` mismatch (mode or http/https) | Match the App's Callback URL exactly to the mode |
| `Resource not accessible by integration` | App missing `Members: Read-only` | Add the org permission; an org owner must approve the updated install |
| GitHub users see no/wrong resources | `githubOrgName`, `allowed_organizations`, `teams.mapping`, or team membership | Verify all four; confirm the user's GitHub teams |
| Configured team skipped in sync | Team doesn't exist on GitHub | The Hub only syncs teams that exist; create it or fix the key |
| Installation token unavailable | `app_id`/`private_key_file` wrong or App not installed on org | Verify both and the org installation |
| No admin user created | `custom.adminUser.enabled` not true | Set it, re-apply, `kubectl logs … | grep -i admin` |
| Native user can't log in | Not `multi`, user not pre-created, or no local password | Confirm mode + that an admin created the account |
| Password change keeps failing | New password fails the strength policy | Re-check length + upper/lower/digit/special |
