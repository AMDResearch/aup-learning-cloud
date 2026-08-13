---
name: configure-aup-learning-cloud-auth
description: >-
  Group: Maintain AUP Learning Cloud. Configures authentication for AUP Learning
  Cloud with custom.auth provider flags for auto-login, dummy, native, GitHub,
  or native plus GitHub. Covers GitHub App OAuth and team sync, native accounts,
  password policy, forced first-login change, and custom.adminUser bootstrap.
  Use for custom.auth, GitHubOAuthenticator, custom.githubOrgName,
  oauth_callback_url, allowed_organizations, jupyterhub-admin-credentials,
  login 404s, OAuth callback errors, or "Resource not accessible by
  integration". Do not use for resource-to-group mapping
  (configure-aup-learning-cloud-courses), bulk users
  (manage-aup-learning-cloud-users), or private-repo cloning
  (configure-aup-learning-cloud-repos).
---

# Configure AUP Learning Cloud authentication

Choose and wire the Hub's providers with `custom.auth`, set up the GitHub App
and/or native accounts, and optionally bootstrap the first administrator. Then
re-apply with the installer or Helm.

Edit a supported, manually managed values overlay and never hardcode secrets
into tracked files. Don't manually edit installer-generated
`runtime/values.local.yaml`: it is operational output, receives no preservation
guarantee, and may be silently overwritten by upgrade or reinstall. Use
installer flags for that profile or maintain a separate Helm overlay. The full
GitHub App walkthrough, value blocks, and troubleshooting are in
**[reference.md](reference.md)**.

## Prerequisites

- A checkout of `aup-learning-cloud`; a running (or about-to-deploy) Hub.
- `helm` + `kubectl` against the cluster, or `./auplc-installer` on a
  single-node box.
- For GitHub or native plus GitHub: a GitHub **organization** you own (the App is created
  under the org, not a personal account) and admin access to its settings.

## Pick the provider combination

| `custom.auth` flags | When to use | Notes |
| --- | --- | --- |
| `autoLogin: true` | Shared demo session | No credentials. |
| `dummy: true` | Throwaway testing only | Accepts any user/password; not for real use. |
| `native: true` | Managed native accounts | No GitHub setup required. |
| `github: true` | Org-backed SSO | GitHub App and team sync. |
| `native: true`, `github: true` | Both login methods | Combined login page. |

Exactly one row is valid. Confirm the provider combination before changing a
live Hub. Set `custom.runtimeLimitEnabled` and `custom.quota.enabled` explicitly;
neither is inferred from the providers.

## Workflow

1. **Read current state.** Check `custom.auth`, `custom.adminUser.enabled`,
   `custom.githubOrgName`, and `hub.config.GitHubOAuthenticator` in the active
   overlay.
2. **Set the providers** in the overlay. For auto-login or dummy you are done with
   credentials; skip to step 6.
3. **GitHub App.** Create the App under the org with the callback URL required
   by the selected provider combination and `Members: Read-only` + `Contents: Read-only`
   permissions, then fill `hub.config.GitHubOAuthenticator` (`app_id`,
   `client_id`, `client_secret`, `private_key_file`, `allowed_organizations`,
   `scope: []`) and `custom.githubOrgName`. Step-by-step in
   [reference.md](reference.md).
   - **Callback URL must match the providers:** native plus GitHub uses
     `…/hub/github/oauth_callback`; GitHub-only uses `…/hub/oauth_callback`.
4. **Team sync.** Team-to-group sync uses the App installation token; the org
   teams are intersected with `custom.teams.mapping`. Mapping *which resource* a
   group sees stays in the configure-courses skill — this skill only makes the
   groups exist. All provider combinations use this mapping and the existing
   fallback groups for resource visibility.
5. **Native accounts.** Native and native plus GitHub use the same first-use
   authenticator. It has
   `create_users = False`, so accounts must be created by an admin before login
   (see manage-users skill). Password policy: ≥8 chars with upper, lower, digit,
   and special; users can be forced to change on first login.
6. **Admin bootstrap (native providers only).** Set
   `custom.adminUser.enabled: true` with a canonical `custom.adminUser.username`.
   Leave `existingSecret` empty to have the chart generate
   `jupyterhub-admin-credentials`, or name an external Secret with
   `admin-password` and optional `api-token` keys. The `admin-password` seeds
   only a missing password row. An existing database hash is authoritative, so
   changing the Secret doesn't rotate or reconcile the password. The separate
   `api-token` key supplies API access for scripts and isn't password bootstrap.
7. **Pre-flight the render.** `helm template jupyterhub ./runtime/chart -f
   runtime/values.yaml -f <overlay>` must succeed.
8. **Apply.** Single-node: `./auplc-installer rt upgrade`. For a direct Helm
   deployment with an external Secret, create the configured Secret, then run
   `helm upgrade --install jupyterhub ./runtime/chart -n jupyterhub -f
   runtime/values.yaml -f <overlay>`. Native-enabled deployments can use
   chart-generated credentials when no existing Secret is configured.
9. **Verify.** Load the Hub: the expected login page appears, a GitHub user
   lands in the right groups, and (if bootstrapped) the admin can log in. Read
   the secret with the commands in [reference.md](reference.md).

If a Helm install/upgrade fails, inspect `helm status jupyterhub -n jupyterhub`
before retrying. On a single-node install, `./auplc-installer rt upgrade` or
`./auplc-installer rt reinstall` reuses `jupyterhub-admin-credentials`. This
doesn't change an existing database password.

## Safety

- **Secrets never go in tracked files.** `client_secret`, the App private key,
  and `jupyterhub-admin-credentials` must come from a mounted K8s secret or an
  untracked overlay. Never commit them.
- **Avoid `dummy` outside isolated testing** — it accepts any credentials.
- **Switching providers is disruptive.** Moving from auto-login to GitHub or
  native plus GitHub forces
  every user through login and changes who can spawn; confirm timing for a live
  class.
- A `helm upgrade` / `rt upgrade` restarts the Hub pod (brief auth blip).
- If Hub source is touched, preserve the four attribution layers and per-file
  copyright headers (see the project `AGENTS.md`).

## Reference

GitHub App creation walkthrough, every `GitHubOAuthenticator` field, the
OAuth-App→GitHub-App migration, native-account/password details, admin Secret
retrieval, and the troubleshooting table: [reference.md](reference.md).
