# Dependency Management

This repository uses several dependency ecosystems at the same time: Python,
pnpm, Docker images, Helm values, GitHub Actions, Kubernetes images, Jupyter
components, GPU runtime packages, and course images. The goal of dependency
management is to make updates visible, reviewable, and reproducible without
allowing automated upgrades to break user notebook environments.

## Policy

- Renovate opens dependency update pull requests; it must not merge them
  automatically by default.
- Dependency update PRs target the `develop` branch.
- New releases are held for at least seven days before Renovate proposes them.
- High-risk runtime stacks require manual validation before a PR is opened from
  the dependency dashboard or before it is merged.
- Docker image tags that affect runtime behavior should move toward explicit
  version tags or digests instead of mutable `latest` tags.
- Suppressed vulnerability alerts must include a reason and an expiry date in
  the tracking issue or security triage notes.

## Dependency Sources

| Area | Primary files | Notes |
| --- | --- | --- |
| Python installer | `pyproject.toml`, `requirements-installer.txt` | Installer and test helper dependencies. |
| Hub Python runtime | `runtime/hub/requirements.txt` | Installed into the Hub image at build time. |
| Frontend | `runtime/package.json`, `runtime/pnpm-workspace.yaml`, `runtime/pnpm-lock.yaml` | pnpm workspace with a checked-in lockfile. |
| JupyterLab extension | `runtime/notebook/jupyterlab-runtime-status/package.json`, `runtime/notebook/jupyterlab-runtime-status/pyproject.toml` | Must stay compatible with the JupyterLab app version in base images. |
| Base images | `dockerfiles/Base/Dockerfile.cpu`, `dockerfiles/Base/Dockerfile.rocm` | Pins JupyterHub, JupyterLab, Notebook, ipywidgets, ipykernel, and GPU runtime packages. |
| Hub image | `dockerfiles/Hub/Dockerfile` | Pins the upstream JupyterHub Kubernetes Hub image and pnpm version. |
| Code image | `dockerfiles/Code/Dockerfile`, `dockerfiles/Code/scripts/*.sh` | Pins code-server, pnpm, Node tooling, Pixi, and extension installation flow. |
| Course images | `dockerfiles/Courses/*/Dockerfile` | Inherit base images and may install course-specific packages. |
| Helm chart | `runtime/chart/Chart.yaml`, `runtime/chart/values.yaml`, `runtime/values.yaml` | Pins chart metadata, JupyterHub component images, and AUPLC runtime images. |
| CI | `.github/workflows/*.yml`, `.github/build-config.json` | Pins GitHub Actions versions and build matrix inputs. |

## Risk Tiers

### Low risk

- GitHub Actions patch and minor updates.
- Frontend dev dependency patch updates.
- Lockfile-only pnpm patch updates.
- Lint and formatting tool patch updates.

These updates can be grouped and reviewed together. Automerge may be considered
later if CI is stable, but it is intentionally disabled in the initial setup.

### Medium risk

- Docker base image patch updates.
- Helm component image patch updates.
- Frontend runtime minor updates.
- Python helper dependency updates.

These updates require normal review and passing CI/build validation.

### High risk

- JupyterHub, JupyterLab, Notebook, Jupyter Server, ipywidgets, and ipykernel.
- ROCm, PyTorch, torchvision, torchaudio, and GPU-related packages.
- JupyterHub Helm chart component upgrades.
- code-server and preinstalled code-server extensions.
- Course image runtime packages.

These updates require manual validation in a staging environment. Renovate may
open PRs for them, but maintainers should not merge them from CI alone.

## Renovate Setup

The repository uses self-hosted Renovate instead of the Renovate GitHub App.
The workflow in `.github/workflows/renovate.yml` runs Renovate on a schedule and
can also be triggered manually.

Required secret:

- `RENOVATE_TOKEN`: a fine-grained token or machine-user token with the minimum
  permissions needed to create branches, issues, and pull requests.

Recommended token permissions for this repository:

- Contents: read/write
- Pull requests: read/write
- Issues: read/write
- Workflows: read/write only if Renovate should update workflow files

The Renovate config intentionally sets:

- `automerge: false`
- `baseBranchPatterns: ["develop"]`
- `minimumReleaseAge: 7 days`
- `prConcurrentLimit: 5`
- `prHourlyLimit: 2`
- dependency dashboard enabled
- high-risk stacks gated with `dependencyDashboardApproval`

## Managing Bare Version Pins

Some dependencies are written directly in Dockerfiles, shell scripts, or Helm
templates instead of standard manifests. Renovate can manage these with custom
regex managers when the version line is annotated.

Use this pattern for Docker `ARG` or `ENV` pins:

```dockerfile
# renovate: datasource=pypi depName=jupyterhub versioning=pep440
ARG JUPYTERHUB_VERSION="5.4.4"

# renovate: datasource=pypi depName=jupyterlab versioning=pep440
ARG JUPYTERLAB_VERSION="4.5.6"

# renovate: datasource=npm depName=pnpm versioning=npm
ARG PNPM_VERSION="10.27.0"
```

Use this pattern for shell pins:

```bash
# renovate: datasource=github-releases depName=coder/code-server
CODE_SERVER_VERSION="4.96.4"
```

Use this pattern for image tags in YAML when Renovate does not detect the image
with a built-in manager:

```yaml
# renovate: datasource=docker depName=curlimages/curl versioning=docker
image: curlimages/curl:8.5.0
```

Prefer annotations close to the version line. This keeps the source of truth
visible to maintainers and prevents the Renovate config from becoming a hidden
map of unrelated regular expressions.

## Jupyter Upgrade Validation

JupyterHub and JupyterLab updates are feasible, but they must be coordinated
across base images, Hub images, chart metadata, and the JupyterLab extension.

Current key pins:

- `JUPYTERHUB_VERSION="5.4.4"` in `dockerfiles/Base/Dockerfile.cpu` and
  `dockerfiles/Base/Dockerfile.rocm`.
- `JUPYTERLAB_VERSION="4.5.6"` in `dockerfiles/Base/Dockerfile.cpu` and
  `dockerfiles/Base/Dockerfile.rocm`.
- `appVersion: 5.4.4` in `runtime/chart/Chart.yaml`.
- JupyterLab extension packages in
  `runtime/notebook/jupyterlab-runtime-status/package.json`.

Validation checklist for Jupyter stack PRs:

1. Build the CPU base image.
2. Build the ROCm base image if GPU packages changed.
3. Build the Hub image.
4. Render the Helm chart with project values.
5. Deploy to staging.
6. Log in to the Hub.
7. Spawn a CPU notebook server.
8. Spawn a GPU notebook server when GPU packages changed.
9. Open JupyterLab and confirm the runtime-status extension loads.
10. Create and run a notebook cell.
11. Stop and restart the server.
12. Review Hub logs for version mismatch warnings.

## Alert Triage

Handle dependency alerts by impact and fix path:

| Alert type | Preferred action |
| --- | --- |
| pnpm transitive vulnerability | Let Renovate update the lockfile and run frontend validation. |
| direct frontend dependency | Review Renovate PR and run frontend validation. |
| Hub Python runtime vulnerability | Update with constraints or direct pins and build the Hub image. |
| Docker OS package vulnerability | Rebuild the affected image and scan the result. |
| Jupyter stack vulnerability | Use a dedicated Jupyter stack PR and staging validation. |
| GPU runtime vulnerability | Validate on GPU nodes before merging. |
| unreachable or test-only vulnerability | Suppress only with documented reason and expiry. |

## Recommended Validation Commands

Use the narrowest validation that covers the changed dependency, then widen when
needed.

```bash
# Frontend dependencies
cd runtime && pnpm install --frozen-lockfile && pnpm run build

# Helm rendering
helm template jupyterhub runtime/chart -f runtime/values.yaml

# Hub image
docker build -f dockerfiles/Hub/Dockerfile -t auplc-hub:dependency-test .
```

For image security scanning, use the scanner approved by the deployment
environment. Trivy, Grype, or OSV Scanner are common choices, but the scanner
choice should match organizational policy.
