# Configure AUP Learning Cloud repository cloning — Reference

Every `custom.gitClone` field, the init-container/token mechanics, the
persistence state machine, and troubleshooting. Workflow and gates are in
[SKILL.md](SKILL.md).

## Source guides

- Configuration Reference (section 4, custom.gitClone): <https://amdresearch.github.io/aup-learning-cloud/jupyterhub/configuration-reference.html>
- Authentication Guide (GitHub App for repos): <https://amdresearch.github.io/aup-learning-cloud/jupyterhub/authentication-guide.html>

The live `runtime/values.yaml` (`custom.gitClone`) and
`runtime/hub/core/scripts/git-clone.sh` are the source of truth.

## custom.gitClone fields

```yaml
custom:
  gitClone:
    # -- Private repo access --
    githubAppName: ""          # GitHub App slug; enables repo picker + OAuth token.
                               # Only effective for GitHub-App users.
    defaultAccessToken: ""     # Bot/service-account PAT for ALL users (incl. auto-login).
                               # Helm creates secret jupyterhub-git-default-token from it.
    # -- Clone behavior --
    allowedProviders:          # subdomains of these are also accepted
      - github.com
      - gitlab.com
      - bitbucket.org
    maxCloneTimeout: 300        # seconds per clone/fetch
    initContainerImage: "alpine/git:2.47.2"   # must contain git + sh
    # -- Persistence --
    defaultPersistence: true    # keep clones after the server stops
    allowPersistenceChoice: false  # expose a per-user persist toggle on the spawn form
```

## The per-resource gate

```yaml
custom:
  resources:
    metadata:
      gpu:
        allowGitClone: true     # REQUIRED for this resource to accept a repo URL
```

If the selected resource's `allowGitClone` is false, the spawner discards the
submitted `repo_url` and logs `Repository URL ignored … does not allow git
cloning` — no user-visible error. This metadata block otherwise belongs to the
configure-courses skill; this skill only flips the clone gate.

## Token model

Priority: **OAuth (GitHub App) > defaultAccessToken > none (public only)**.

- The spawner injects the chosen token as `GIT_ACCESS_TOKEN` into the
  `init-clone-repo` container via a `secretKeyRef`.
- `git-clone.sh` rewrites the HTTPS remote to
  `https://x-access-token:<token>@<host>/…`, so any provider/token type works.
- `githubAppName` users authorize specific private repos through the GitHub App
  UI on the spawn page; the token comes from their OAuth session.
- `defaultAccessToken` is applied transparently to everyone — ideal for a shared
  classroom private repo with no GitHub login.

## Persistence state machine

`git-clone.sh` writes repo-external metadata under `~/.auplc/git-clones` and:

- **persistent** (default): reuses a compatible existing clone; **does not
  auto-pull/reset/sync** after the first successful clone.
- **ephemeral**: a `preStop` hook `rm -rf`s the clone when the session ends.
- Refuses to modify a directory lacking compatible AUPLC metadata (won't clobber
  a user's own folder).
- Refuses to replace a persistent managed clone for an ephemeral request.

`allowPersistenceChoice: true` exposes the choice to users; otherwise
`defaultPersistence` is enforced.

## Branch selection

Users can pass a branch, or paste a `/tree/<branch>` URL — the spawner extracts
the branch from `https://host/owner/repo/tree/<branch>`. `git-clone.sh` does a
`--depth 1` clone of that branch (or the default branch).

## Apply and verify

```bash
helm template jupyterhub ./runtime/chart -f runtime/values.yaml -f <overlay> >/dev/null
sudo ./auplc-installer rt upgrade        # single-node
helm upgrade --install jupyterhub ./runtime/chart -n jupyterhub \
  -f runtime/values.yaml -f <overlay>    # multi-node

# after a user spawns with a repo:
kubectl get pods -n jupyterhub -o wide
kubectl logs -n jupyterhub <user-pod> -c init-clone-repo
```

The repo URL/branch field (and picker if `githubAppName`) shows on the spawn
page for allowed resources; a successful spawn has the repo under
`/home/jovyan/<repo>`.

## Troubleshooting

| Symptom | Likely cause | First checks |
| --- | --- | --- |
| Repo field absent on spawn | `allowGitClone` not true for that resource | Set `metadata.<key>.allowGitClone: true`, re-apply |
| "Repository URL ignored" in Hub logs | Same gate — resource disallows cloning | Same as above |
| Private clone fails (auth) | No usable token for that user | GitHub-App user must authorize the repo; or set `defaultAccessToken` |
| Clone fails ("could not be cloned") | Bad URL/branch, provider not allowed, timeout | Check URL, `allowedProviders`, raise `maxCloneTimeout`; read `init-clone-repo` logs |
| Server fails to start, `repo_clone_failed` | Init container clone error | `kubectl logs … -c init-clone-repo`; verify repo access/network |
| "Refusing to modify existing directory" | Target dir exists without AUPLC metadata | User has a same-named folder; choose another path or remove it |
| Changes to persistence not taking | Switched mode under a managed clone | Persistent↔ephemeral has refusal rules; clear the clone or keep the mode |
