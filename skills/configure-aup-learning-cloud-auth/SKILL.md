---
name: configure-aup-learning-cloud-auth
description: >-
  Group: Maintain AUP Learning Cloud. Configures authentication for AUP Learning
  Cloud: auth modes (auto-login/dummy/github/local/multi), GitHub App / OAuth, GitHub
  team-to-group sync, native local accounts, password policy and forced
  first-login change, and admin bootstrap. Use when the user wants to set or
  switch custom.authMode, enable GitHub login, create or migrate a GitHub
  App, set oauth_callback_url / client_id / client_secret / app_id /
  private_key_file, sync GitHub teams into JupyterHub groups, enable native
  accounts, bootstrap the initial admin (custom.adminUser), or debug "Resource
  not accessible by integration", a login 404, or OAuth callback errors.
  Triggers include custom.authMode, GitHubOAuthenticator, custom.githubOrgName,
  allowed_organizations, jupyterhub-admin-credentials. Do not use to map which
  resources a group sees (configure-aup-learning-cloud-courses), to
  bulk-manage users (manage-aup-learning-cloud-users), or to configure
  private-repo cloning (configure-aup-learning-cloud-repos).
---

# Configure AUP Learning Cloud authentication

Choose and wire the Hub's login path: pick the `custom.authMode`, set up the
GitHub App (OAuth + server-to-server team sync) and/or native local accounts,
and bootstrap the initial admin — then re-apply with the installer or Helm.

Edit a **values overlay** (`runtime/values.yaml`, `values-multi-nodes.yaml`, or
`values.local.yaml`), never hardcode secrets into tracked files. The full
GitHub App walkthrough, value blocks, and troubleshooting are in
**[reference.md](reference.md)**.

## Prerequisites

- A checkout of `aup-learning-cloud`; a running (or about-to-deploy) Hub.
- `helm` + `kubectl` against the cluster, or `./auplc-installer` on a
  single-node box.
- For `github` / `multi`: a GitHub **organization** you own (the App is created
  under the org, not a personal account) and admin access to its settings.

## Pick the auth mode

| Mode | When to use | Notes |
| --- | --- | --- |
| `auto-login` | Local demo / single dev box | No credentials; quota auto-disabled unless forced. The checked-in default. |
| `dummy` | Throwaway testing only | Accepts any user/password; not for real use; its login can 404 in normal setups. |
| `github` | Org-backed SSO | GitHub App only; team membership syncs into Hub groups. |
| `local` | Closed single-node or standalone local auth | Administrator-managed local accounts only; no GitHub setup. |
| `multi` | GitHub + local accounts | Combined login page; native accounts for users without GitHub. |

`custom.authMode` is the single switch. Confirm the target mode with the user
before changing a live Hub (a `helm upgrade` restarts the Hub pod, a brief
login blip).

## Workflow

1. **Read current state.** Check `custom.authMode`, `custom.adminUser.enabled`,
   `custom.githubOrgName`, and `hub.config.GitHubOAuthenticator` in the active
   overlay.
2. **Set the mode** in the overlay. For `auto-login`/`dummy` you are done with
   credentials; skip to step 6.
3. **GitHub App (github/multi).** Create the App under the org with the exact
   callback URL for the mode and `Members: Read-only` + `Contents: Read-only`
   permissions, then fill `hub.config.GitHubOAuthenticator` (`app_id`,
   `client_id`, `client_secret`, `private_key_file`, `allowed_organizations`,
   `scope: []`) and `custom.githubOrgName`. Step-by-step in
   [reference.md](reference.md).
   - **Callback URL must match the mode exactly:** `multi` uses
     `…/hub/github/oauth_callback`; single `github` uses `…/hub/oauth_callback`.
4. **Team sync.** Team-to-group sync uses the App installation token; the org
   teams are intersected with `custom.teams.mapping`. Mapping *which resource* a
   group sees stays in the configure-courses skill — this skill only makes the
   groups exist.
5. **Native accounts (local/multi).** The first-use authenticator has
   `create_users = False`, so accounts must be created by an admin before login
   (see manage-users skill). Password policy: ≥8 chars with upper, lower, digit,
   and special; users can be forced to change on first login.
6. **Admin bootstrap (optional).** Set `custom.adminUser.enabled: true` with a
   canonical `custom.adminUser.username`. Without `existingSecret`, the chart
   creates `jupyterhub-admin-credentials`; with `existingSecret`, it uses the
   named external Secret and never rotates it. The single-node installer creates
   and validates its lifecycle Secret before Helm runs.
7. **Pre-flight the render.** `helm template jupyterhub ./runtime/chart -f
   runtime/values.yaml -f <overlay>` must succeed.
8. **Apply.** Single-node: `./auplc-installer rt upgrade`. Multi/manual:
   `helm upgrade --install jupyterhub ./runtime/chart -n jupyterhub -f
   runtime/values.yaml -f <overlay>`.
9. **Verify.** Load the Hub: the expected login page appears, a GitHub user
   lands in the right groups, and (if bootstrapped) the admin can log in. Read
   the secret with the commands in [reference.md](reference.md).

If a Helm install/upgrade fails, inspect `helm status jupyterhub -n jupyterhub`
before retrying. On a single-node install, `./auplc-installer rt upgrade` or
`./auplc-installer rt reinstall` preserves `jupyterhub-admin-credentials`; do
not delete that Secret unless intentionally resetting credentials.

## Safety

- **Secrets never go in tracked files.** `client_secret`, the App private key,
  and `jupyterhub-admin-credentials` must come from a mounted K8s secret or an
  untracked overlay. Never commit them.
- **Avoid `dummy` outside isolated testing** — it accepts any credentials.
- **Switching modes is disruptive.** `auto-login` → `github`/`multi` forces
  every user through login and changes who can spawn; confirm timing for a live
  class.
- A `helm upgrade` / `rt upgrade` restarts the Hub pod (brief auth blip).
- If Hub source is touched, preserve the four attribution layers and per-file
  copyright headers (see the project `AGENTS.md`).

## Reference

GitHub App creation walkthrough, every `GitHubOAuthenticator` field, the
OAuth-App→GitHub-App migration, native-account/password details, admin secret
retrieval, and the troubleshooting table: [reference.md](reference.md).
