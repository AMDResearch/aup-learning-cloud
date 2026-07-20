---
name: manage-aup-learning-cloud-users
description: >-
  Group: Maintain AUP Learning Cloud. Manages users, groups, passwords, admins,
  and quota balances day to day with the built-in AUP Learning Cloud scripts
  (scripts/generate_users_template.py and scripts/manage_users.py) plus the web
  admin console (/hub/admin). Use when the user wants to onboard a class,
  generate a roster CSV/Excel, bulk-create native users, export or back up users,
  generate/reset passwords, force or skip first-login password changes, grant or
  revoke admins, delete users, create or edit groups, run GitHub group sync, or
  set/add/list quota balances and scheduled quota refresh rules. Triggers include
  manage_users.py, generate_users_template.py, users.csv, passwords_output.csv,
  /hub/admin, jupyterhub-admin-credentials, JUPYTERHUB_URL, JUPYTERHUB_TOKEN,
  set-admin, set-passwords, set-quota, add-quota, list-quota, refreshRules,
  "onboard a class", and "bulk users". Do not use to choose auth mode, configure
  course visibility/quota rates, or install/deploy a cluster.
---

# Manage AUP Learning Cloud users

Run the day-2 people operations: create and onboard users (including a whole
class), set/reset passwords, manage admins and groups, and grant or refresh
quota balances. Prefer the repository's deterministic scripts for bulk work and
use the web console for interactive inspection or one-off admin edits.

The two built-in scripts are the primary automation surface:

- `scripts/generate_users_template.py` creates CSV/Excel rosters with the
  columns `manage_users.py` expects.
- `scripts/manage_users.py` performs API-backed user/admin/password work and
  quota commands.

Exact command variants, file formats, env setup, and the quota field guide are
in **[reference.md](reference.md)**.

## Prerequisites

- A running Hub and an **admin** account (or `custom.adminUser.enabled: true`
  and the bootstrapped `admin`).
- For CLI work: run from the `aup-learning-cloud` checkout and install
  `pandas`, `openpyxl`, and `requests` in the Python environment that runs the
  scripts.
- `manage_users.py` requires `JUPYTERHUB_URL` and `JUPYTERHUB_TOKEN` for every
  subcommand. The bundled `scripts/hub-api-env.sh` derives both from the
  `jupyterhub-admin-credentials` secret and checks reachability.
- Quota subcommands use the Hub admin API. `kubectl` is only needed to bootstrap
  an API token from `jupyterhub-admin-credentials` or inspect scheduled quota
  refresh CronJobs.
- Native-user creation/password reset requires `authMode: multi` (or another
  mode with native accounts). Password actions never apply to GitHub identities.

## Two surfaces

| Task | Best surface | Command |
| --- | --- | --- |
| Generate roster | CLI | `generate_users_template.py --prefix student --count 50 -o users.csv` |
| Create users | CLI for bulk, web for one-off | `manage_users.py create users.csv` |
| Passwords | CLI for bulk native-user resets | `manage_users.py set-passwords users.csv --generate -o passwords_output.csv` |
| Admins | CLI or web | `manage_users.py set-admin [--file admins.csv] [--revoke]` |
| Groups | Web console | `/hub/admin` Groups view, including Sync Now |
| Quota | CLI for repeatable grants, web for inspection | `set-quota` / `add-quota` / `list-quota` |
| Export/backup | CLI | `manage_users.py export backup.xlsx` |

Unlimited quota is entered as `-1`, `∞`, or `unlimited`. Admin users and the
current admin are protected from deletion.

## Workflow — onboard a class (most common)

1. **Confirm the live script surface.** The project can evolve; quickly check
   help before composing a large batch command:

   ```bash
   python scripts/generate_users_template.py --help
   python scripts/manage_users.py --help
   ```
2. **Set env** so `manage_users.py` can reach the Hub API:

   ```bash
   source skills/manage-aup-learning-cloud-users/scripts/hub-api-env.sh
   ```

   (Or export `JUPYTERHUB_URL`/`JUPYTERHUB_TOKEN` yourself — see reference.)
   Use `HUB_URL="https://hub.example.com"` and `HUB_NAMESPACE=<namespace>` when
   the Hub is not the default local NodePort in namespace `jupyterhub`.
3. **Generate a roster template**:

   ```bash
   python scripts/generate_users_template.py --prefix student --count 50 --output users.csv
   ```
4. **Inspect the roster.** Confirm the `username` and optional `admin` columns,
   and remember usernames are normalized to lowercase by `manage_users.py`.
5. **Create the users**:

   ```bash
   python scripts/manage_users.py create users.csv
   ```
6. **Issue passwords** (generated, forced change on first login by default):

   ```bash
   python scripts/manage_users.py set-passwords users.csv --generate -o passwords_output.csv
   ```
7. **Promote teaching staff** as needed:

   ```bash
   python scripts/manage_users.py set-admin teacher01 teacher02
   ```
8. **Grant starting quota** (if quota is enabled):

   ```bash
   python scripts/manage_users.py set-quota student01 student02 --amount 1000
   ```
9. **Deliver credentials securely** from `passwords_output.csv`, then verify in
    `/hub/admin` (users appear, groups correct, balances set).

## Quota operations

This skill owns quota **operations** (granting/refreshing balances, scheduled
refresh). Quota **rates and enable/disable knobs** (`custom.quota.*`,
`accelerators.*.quotaRate`) live in the configure-courses skill.

- One-off: `set-quota` (absolute) / `add-quota` (delta) / `list-quota`, or the
  inline/batch editors and global "Refresh Quota" in `/hub/admin`.
- File-driven: `set-quota --file quotas.csv` expects `username,quota` columns;
  `add-quota --file users.csv --amount 100` expects at least `username`.
- Scheduled: `custom.quota.refreshRules` become Kubernetes CronJobs. Verify with
  `kubectl -n jupyterhub get cronjobs -l app.kubernetes.io/component=quota-refresh`.
  The rule schema is in [reference.md](reference.md).

## Safety

- **Credentials are sensitive.** Generated passwords and `passwords_output.csv`
  must be delivered securely and never committed.
- **Check rosters before writes.** Generated users are easy to create in bulk;
  inspect the CSV/Excel and confirm count, prefix, admin flags, and target Hub
  before running `create`, `set-passwords`, `set-admin`, or quota commands.
- **Bulk delete is destructive.** `manage_users.py delete … --yes` removes
  accounts; confirm the list with the user first. Admins/current admin are
  protected, but data on user PVCs can still be orphaned.
- **`set-admin` grants full platform control** — confirm the target list.
- **Quota refresh rules apply broadly.** A global Refresh Quota or a broad
  `refreshRules` filter touches many users; confirm before applying.
- CLI quota commands call the Hub admin API; they need a valid API token and a
  reachable Hub, not `kubectl` access. Use `kubectl` only for the secret
  bootstrap or scheduled-refresh CronJob inspection described above.

## Reference

Env setup, every `manage_users.py` subcommand, the admin console views,
`refreshRules` schema, and troubleshooting: [reference.md](reference.md).
