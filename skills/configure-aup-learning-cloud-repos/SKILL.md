---
name: configure-aup-learning-cloud-repos
description: >-
  Group: Course & other editor. Configures per-user Git repository cloning: the
  custom.gitClone block (githubAppName repo picker, defaultAccessToken for
  private repos, allowedProviders, maxCloneTimeout, defaultPersistence,
  allowPersistenceChoice) and the per-resource metadata.allowGitClone gate that
  clones a repo into a user's workspace at spawn time. Use when the user wants
  to let learners clone a Git repo on startup, enable the spawn-form repo
  URL/branch field or GitHub repo picker, give access to a private repo (bot PAT
  or GitHub App token), choose whether cloned repos persist, allow
  GitLab/Bitbucket, or debug "Repository URL ignored" or a failed clone init
  container. Triggers include custom.gitClone, allowGitClone, githubAppName,
  defaultAccessToken, allowedProviders, init-clone-repo. Do not use to set up
  GitHub login itself (configure-aup-learning-cloud-auth), to publish a course
  to the catalog (configure-/develop-aup-learning-cloud-courses), or to build
  images (build-aup-learning-cloud-images).
---

# Configure AUP Learning Cloud repository cloning

Enable the runtime, per-user feature where a learner pastes a Git URL on the
spawn form (or picks a private repo) and the Hub clones it into their home PVC
via an init container. This is **not** how you publish a course to the catalog
(that is develop-/configure-courses); it brings *each user's own* repo into
*their own* workspace.

Edit a **values overlay** and re-apply. The token model, the persistence rules,
and the GitHub App requirement are subtle and partly silent — read the gates
below. Full details and troubleshooting are in **[reference.md](reference.md)**.

## Prerequisites

- A checkout of `aup-learning-cloud` and a running (or about-to-deploy) Hub;
  `helm` + `kubectl` or `./auplc-installer`.
- For private repos via GitHub App: the App configured in the auth skill
  (`hub.config.GitHubOAuthenticator` + `custom.githubOrgName`).
- For private repos via a shared token: a read-only bot/service-account PAT.

## The two gates (both required, one is silent)

A repo URL is only cloned when **both** are true:

1. `custom.gitClone` is configured (at minimum the feature is on; private repos
   need a token source).
2. The **selected resource** has `custom.resources.metadata.<key>.allowGitClone:
   true`.

If `allowGitClone` is false for the chosen resource, the Hub **silently drops**
the repo URL (it logs a warning but shows no user error). Always set both.

## Token priority (private repos)

`OAuth token (GitHub App) > defaultAccessToken > none (public only)`

- `githubAppName` — enables the repo picker + automatic per-repo OAuth token,
  but **only for GitHub-App users**. No effect for auto-login/native users.
- `defaultAccessToken` — a bot PAT applied transparently to **all** users
  (including auto-login); right for single-node/classroom shared private repos.
  Helm base64s it into the `jupyterhub-git-default-token` secret.

## Workflow

1. **Read current state.** Inspect `custom.gitClone` and which
   `metadata.<key>.allowGitClone` are already true.
2. **Turn on cloning** in the overlay; set `allowedProviders` (defaults
   `github.com`, `gitlab.com`, `bitbucket.org`) and `maxCloneTimeout` as needed.
3. **Open the gate per resource.** Set `allowGitClone: true` on each course/env
   that should accept a user repo (configure-courses owns the rest of that
   metadata block).
4. **Private repos (optional).** Pick a token source:
   - GitHub App: ensure the auth skill's App is set, then
     `custom.gitClone.githubAppName: "<app-slug>"`.
   - Shared PAT: `custom.gitClone.defaultAccessToken: "<read-only PAT>"` (keep
     it out of tracked files — see Safety).
5. **Persistence policy.** Decide `defaultPersistence` (default `true`; cloned
   repos survive server stop, no auto-pull after first clone) and whether to let
   users choose with `allowPersistenceChoice`.
6. **Pre-flight + apply.** `helm template …` must succeed; then
   `./auplc-installer rt upgrade` (single) or `helm upgrade --install …`
   (multi).
7. **Verify.** On the spawn page for an allowed resource, the repo URL/branch
   field (and picker, if `githubAppName`) appears; launch with a repo and
   confirm `init-clone-repo` succeeds and the repo lands under
   `/home/jovyan/<repo>`.

## Safety

- **`defaultAccessToken` is a secret.** It is base64'd into a K8s secret — never
  commit it in a tracked values file. Scope the PAT **read-only** to the
  specific repos to limit blast radius.
- **Persistence has destructive edges.** Ephemeral mode deletes the clone via a
  `preStop` hook; the script refuses to touch a directory it didn't create and
  refuses to replace a persistent clone for an ephemeral request. Don't flip
  `defaultPersistence` casually on a class with in-progress work.
- **Provider allowlist is a security control.** Only add providers you trust;
  cloning runs inside the user's pod.
- A `helm upgrade` restarts the Hub pod (brief login blip).

## Reference

Every `custom.gitClone` field, the init-container/token mechanics, the
persistence state machine, the `allowGitClone` gate, and troubleshooting:
[reference.md](reference.md).
