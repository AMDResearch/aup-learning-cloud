# Manage AUP Learning Cloud users — Reference

Env setup, the built-in user-management script surface, roster file formats,
the admin console views, the `refreshRules` schema, and troubleshooting.
Workflow and gates are in [SKILL.md](SKILL.md).

## Source guides

- User Management Guide: <https://amdresearch.github.io/aup-learning-cloud/jupyterhub/user-management.html>
- User Quota System: <https://amdresearch.github.io/aup-learning-cloud/jupyterhub/quota-system.html>

The live `scripts/generate_users_template.py` and `scripts/manage_users.py` in
`aup-learning-cloud` are the source of truth; verify subcommands/flags against
`--help` before large batches.

```bash
python scripts/generate_users_template.py --help
python scripts/manage_users.py --help
python scripts/manage_users.py set-passwords --help
python scripts/manage_users.py set-quota --help
```

## API environment

`manage_users.py` checks the Hub API before executing any subcommand. Set
`JUPYTERHUB_URL` and `JUPYTERHUB_TOKEN`; the token comes from the
admin-credentials secret (requires `custom.adminUser.enabled`):

```bash
export JUPYTERHUB_URL="http://localhost:30890"
export JUPYTERHUB_TOKEN=$(kubectl -n jupyterhub get secret jupyterhub-admin-credentials \
  -o jsonpath='{.data.api-token}' | base64 -d)
```

The bundled `scripts/hub-api-env.sh` does this and probes `/hub/api/`. Source
it (don't execute) so the exports land in your shell:

```bash
source skills/manage-aup-learning-cloud-users/scripts/hub-api-env.sh
# override the URL if not localhost:30890:
HUB_URL="https://hub.example.com" source skills/manage-aup-learning-cloud-users/scripts/hub-api-env.sh
```

CLI **quota** commands also use `kubectl exec` into `deployment/hub`, so they
need a working kube context + namespace in addition to the API token preflight.

## Python dependencies

```bash
pip install pandas openpyxl requests
```

## Generate roster templates

Use `generate_users_template.py` to create the input files that
`manage_users.py` consumes. It supports numbered users or explicit names, CSV or
Excel output, optional admin flags, custom starting numbers, and digit padding.

```bash
python scripts/generate_users_template.py --prefix student --count 50 --output users.csv
python scripts/generate_users_template.py --prefix AUP --count 30 --start 1 --output aup_users.xlsx
python scripts/generate_users_template.py --prefix student --count 100 --digits 3 --output users.csv
python scripts/generate_users_template.py --prefix admin --count 5 --admin --output admins.csv
python scripts/generate_users_template.py --names alice bob charlie --output custom_users.csv
```

Generated files contain at least:

```csv
username,admin
student01,false
student02,false
```

You can add a `password` column before `set-passwords`, and `set-quota --file`
can read a `quota` column.

## manage_users.py subcommands

```bash
# Users
python scripts/manage_users.py create users.csv
python scripts/manage_users.py list
python scripts/manage_users.py export backup.xlsx
python scripts/manage_users.py delete remove_list.csv --yes

# Admins
python scripts/manage_users.py set-admin teacher01 teacher02
python scripts/manage_users.py set-admin --file admins.csv
python scripts/manage_users.py set-admin --revoke student01

# Passwords (native users only)
python scripts/manage_users.py set-passwords users.csv --generate -o passwords_output.csv
python scripts/manage_users.py set-passwords users.csv --generate --default-password "Welcome123"
python scripts/manage_users.py set-passwords users.csv --no-force-change

# Quota
python scripts/manage_users.py set-quota user1 user2 --amount 1000   # absolute
python scripts/manage_users.py set-quota --file quotas.csv            # username,quota columns
python scripts/manage_users.py add-quota user1 user2 --amount 100    # delta
python scripts/manage_users.py add-quota --file users.csv --amount 100
python scripts/manage_users.py list-quota
```

Every command accepts `--url` and `--token`, but prefer exported env vars so
tokens do not appear in shell history:

```bash
python scripts/manage_users.py --url "$JUPYTERHUB_URL" --token "$JUPYTERHUB_TOKEN" list
```

### Command behavior notes

- Usernames are normalized to lowercase before API writes, matching JupyterHub's
  default behavior. Avoid rosters that depend on case-sensitive usernames.
- `create` reads `username` and optional `admin`; it does not set passwords.
  Run `set-passwords` after creating native users.
- `set-passwords` requires either a `password` column or `--generate`. Generated
  passwords can be saved with `--output`; that file is sensitive.
- `set-passwords` forces first-login password change unless
  `--no-force-change` is passed.
- `set-quota` with positional users requires `--amount`; with `--file`, the file
  can provide per-user `quota` values.
- `delete --yes` skips the interactive confirmation and should only be used
  after the exact roster has been reviewed.

## Web admin console (`/hub/admin`)

- **Users view:** search/page, filter to active servers, create native users
  (single or many, random or shared password, force change, optional admin),
  edit details, reset password (native), batch password reset, inline quota
  edit, batch quota update, start/stop servers, batch delete, per-user usage.
  Admins and the current admin are protected from deletion.
- **Groups view:** distinguishes GitHub-synced, system-managed, and manual
  groups; create manual groups, edit membership of editable groups, review
  group-to-resource mappings, and **Sync Now** (manual GitHub sync when
  `custom.githubOrgName` is set). System-managed groups are read-only;
  GitHub-synced groups are protected from deletion.
- **Dashboard view:** total users, active sessions, usage minutes, weekly active
  users, usage trends, resource distribution, top users, live sessions, pending
  spawns.

Admin quota API endpoints used by the UI: `GET/POST /admin/api/quota/`,
`POST /admin/api/quota/batch`, `POST /admin/api/quota/refresh`,
`GET /api/quota/rates`, `GET /api/quota/me`.

## Scheduled quota refresh (`refreshRules`)

Configured under `custom.quota.refreshRules`; each rule becomes a CronJob.

```yaml
custom:
  quota:
    refreshRules:
      daily-topup:
        enabled: true
        schedule: "0 0 * * *"      # cron
        action: add                # add | set
        amount: 100
        maxBalance: 500            # also: minBalance
        targets:
          includeUnlimited: false
          balanceBelow: 400        # also: balanceAbove, includeUsers,
                                   # excludeUsers, usernamePattern
```

Verify:

```bash
kubectl -n jupyterhub get cronjobs -l app.kubernetes.io/component=quota-refresh
kubectl -n jupyterhub get jobs -l app.kubernetes.io/component=quota-refresh
kubectl -n jupyterhub logs -l app.kubernetes.io/component=quota-refresh --tail=50
```

Changing rate/enablement knobs (`custom.quota.enabled`, `cpuRate`,
`minimumToStart`, `defaultQuota`, `accelerators.*.quotaRate`) is the
configure-courses skill; re-apply with `rt upgrade` / `helm upgrade`.

## Common runbooks

### Onboard 50 native students

```bash
pip install pandas openpyxl requests
source skills/manage-aup-learning-cloud-users/scripts/hub-api-env.sh
python scripts/generate_users_template.py --prefix student --count 50 --output users.csv
python scripts/manage_users.py create users.csv
python scripts/manage_users.py set-passwords users.csv --generate --output passwords_output.csv
python scripts/manage_users.py list
```

Review `passwords_output.csv`, distribute it through a secure channel, then
delete it when no longer needed.

### Add teaching assistants as admins

```bash
python scripts/generate_users_template.py --names ta01 ta02 --admin --output tas.csv
python scripts/manage_users.py create tas.csv
python scripts/manage_users.py set-passwords tas.csv --generate --output ta_passwords.csv
python scripts/manage_users.py set-admin --file tas.csv
```

### Grant class quota

```bash
python scripts/manage_users.py set-quota --file quotas.csv
python scripts/manage_users.py add-quota --file users.csv --amount 100
python scripts/manage_users.py list-quota
```

`quotas.csv` should contain `username,quota` when using `set-quota --file`.
`users.csv` only needs `username` for `add-quota --file`.

## Apply config changes

```bash
# single-node
sudo ./auplc-installer rt upgrade
# multi-node / manual
cd runtime && helm upgrade --install jupyterhub ./chart \
  -n jupyterhub --create-namespace -f values-multi-nodes.yaml
```

## Troubleshooting

| Symptom | Likely cause | First checks |
| --- | --- | --- |
| Script cannot connect to the Hub | `JUPYTERHUB_URL`/`JUPYTERHUB_TOKEN` wrong | Confirm both; `curl -H "Authorization: token $JUPYTERHUB_TOKEN" $JUPYTERHUB_URL/hub/api/` |
| Password reset fails | Target is a GitHub user, weak password, or session lacks perms | Native users only; meet the strength policy |
| Quota command passes API check but fails later | CLI uses `kubectl exec` into `deployment/hub` | Check kube context, namespace, and `kubectl -n jupyterhub get deploy/hub` |
| No api-token secret | `custom.adminUser.enabled: false` | Enable admin bootstrap, re-apply |
| Group membership can't be edited | System-managed or GitHub-synced group | Only manual/editable groups accept edits |
| Refresh rule didn't run | Rule disabled or absent from the applied values | `kubectl … get cronjobs -l …quota-refresh`; re-apply |
| Users log in with lowercase names | Script and JupyterHub normalize usernames | Keep rosters lowercase or communicate normalized usernames |
