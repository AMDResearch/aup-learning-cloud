# Admin Manual — JupyterHub Components and Workflows

This page describes advanced implementation details and workflows. For day-to-day configuration (auth, images, quotas, storage), use the [Configuration Reference](../jupyterhub/configuration-reference.md) and [Single-Node Deployment](../installation/single-node.md). Single-node deployments can use `sudo ./auplc-installer rt upgrade` from the repo root; multi-node or custom Helm deployments use `bash scripts/helm_upgrade.bash` from the **repo root**.

## Multi-login Authenticator

The multi-login system uses `MultiAuthenticator` to combine multiple authentication methods on a single login page:

```python
c.MultiAuthenticator.authenticators = [
    {
        "authenticator_class": CustomGitHubOAuthenticator,
        "url_prefix": "/github",
    },
    {
        "authenticator_class": CustomFirstUseAuthenticator,
        "url_prefix": "/local",
    },
]
```

- `CustomGitHubOAuthenticator` handles GitHub OAuth login
- `CustomFirstUseAuthenticator` handles local account login (each user has their own password)
- The `url_prefix` distinguishes login methods, and the callback URL is `/hub/<method>/oauth_login`

To enable multi-login, set `custom.authMode: "multi"` in `runtime/values.yaml`. The Hub image includes `jupyterhub-multiauthenticator` and `jupyterhub-firstuseauthenticator` as dependencies.

## RemoteLabSpawner

The spawner allocates resources based on user permissions (e.g., GitHub team membership). It generates a resource selection page where users choose their environment. The spawn page is a React application located at `runtime/hub/frontend/apps/spawn/`.

# Workflows

## Workflow 1: Apply config changes

1. Edit `runtime/values.yaml`
2. From the **repo root**, run one of:
   ```bash
   # Single-node (with auplc-installer)
   sudo ./auplc-installer rt upgrade

   # Multi-node / custom Helm
   bash scripts/helm_upgrade.bash
   ```
3. Check status with `k9s` or `kubectl get pods -n jupyterhub`

## Workflow 2: Add a new resource image

1. Create a new folder under `dockerfiles/`, e.g., `dockerfiles/Courses/NewImage/`
2. Create a `Dockerfile` and `build.sh`. The base image is typically `ubuntu:24.04` with a tarball ROCm install (see `dockerfiles/Base/` for reference).
3. Build and test the image locally before pushing:
   ```bash
   docker build -f dockerfiles/Courses/NewImage/Dockerfile -t ghcr.io/amdresearch/auplc-newimage:latest .
   ```
4. Push to the container registry (requires push permissions to `ghcr.io/amdresearch`).
5. Add the new image to `runtime/values.yaml`:
   ```yaml
   custom:
     resources:
       images:
         NewImage: "ghcr.io/amdresearch/auplc-newimage:latest"
       requirements:
         NewImage:
           cpu: "4"
           memory: "16Gi"
           amd.com/gpu: "1"
     teams:
       mapping:
         gpu:
           - NewImage  # Add to appropriate team(s)
   ```
6. Add the image as a prepuller in `runtime/values.yaml`:
   ```yaml
   prePuller:
     extraImages:
       auplc-newimage:
         name: ghcr.io/amdresearch/auplc-newimage
         tag: latest
   ```
7. Deploy:
   ```bash
   sudo ./auplc-installer rt upgrade
   # or: bash scripts/helm_upgrade.bash  (from repo root)
   ```
8. For new images, prepulling may take time depending on network speed. Monitor with `k9s`. If a node halts, delete and restart prepuller pods. If problems persist, SSH into the node and restart K3s.
9. If timeout causes `pending-upgraded` failure, check past versions with `helm history jupyterhub -n jupyterhub`, rollback with `helm rollback jupyterhub <version> -n jupyterhub`, then redeploy.

## Workflow 3: Update an existing image

1. Update the image tag in `build.sh` and `runtime/values.yaml` (under `custom.resources.images` and `prePuller.extraImages`).
2. Build and push to the registry.
3. Deploy:
   ```bash
   sudo ./auplc-installer rt upgrade
   ```
   If there are problems, refer to steps 8-9 in Workflow 2.

## Workflow 4: Edit resource limits or team permissions

1. Edit `runtime/values.yaml`:
   - `custom.resources.requirements` — CPU, memory, GPU limits per resource
   - `custom.teams.mapping` — which teams can access which resources
2. Deploy:
   ```bash
   sudo ./auplc-installer rt upgrade
   ```

## Workflow 5: Change login settings

1. Set `custom.authMode` in `runtime/values.yaml`:
   - `"auto-login"` — no credentials required (single-node dev)
   - `"dummy"` — any username/password accepted (testing)
   - `"github"` — GitHub OAuth only
   - `"multi"` — GitHub OAuth + local accounts
2. For GitHub OAuth, configure `hub.config.GitHubOAuthenticator` in `runtime/values.yaml`. See [GitHub App Setup](../jupyterhub/github-oauth-setup.md).
3. For local accounts, each user has their own password (set on first login or via batch scripts). See [Authentication Guide](../jupyterhub/authentication-guide.md).
4. Deploy:
   ```bash
   sudo ./auplc-installer rt upgrade
   ```

## Workflow 6: Change announcement on login page

1. Edit the announcement HTML in `runtime/values.yaml` under `hub.extraFiles.announcement.txt.stringData`.
2. Deploy:
   ```bash
   sudo ./auplc-installer rt upgrade
   ```
