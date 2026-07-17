# Install AUP Learning Cloud (single node) — Reference

Full flag table, offline flow, subcommands, and troubleshooting for the
`./auplc-installer` single-node path. Workflow and gates are in
[SKILL.md](SKILL.md).

## Source guides

- Quick Start / Single-Node: <https://amdresearch.github.io/aup-learning-cloud/installation/>
- Repo README "Quick Start" section.

Treat the installer's `--help` and the live docs as the source of truth for
flags and version pins; this file condenses the opinionated path.

## Prerequisite commands

```bash
# Ryzen AI APU only: ROCm OEM kernel (reboot afterwards)
sudo apt update && sudo apt install linux-image-6.14.0-1018-oem

# Docker (rootless usage)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER" && newgrp docker
sudo apt install build-essential

# Interactive TUI deps (system Python)
sudo apt install python3-questionary python3-prompt-toolkit
```

## Commands

| Command | What it does |
| --- | --- |
| `./auplc-installer` | Launch the interactive TUI (when a real terminal is attached). |
| `./auplc-installer install [--pull]` | Full install: k3s + images + runtime. Default pulls pre-built images. |
| `./auplc-installer install --dry-run` | Print the Configuration summary and exit. No sudo, no changes. |
| `./auplc-installer uninstall` | Remove everything (k3s + runtime). **Destructive.** |
| `./auplc-installer install-tools` | Install `helm` + `k9s` only. |
| `./auplc-installer detect-gpu` | Show the detected GPU configuration. |
| `./auplc-installer img build [target...]` | Build images (see build-aup-learning-cloud-images). |
| `./auplc-installer img pull` | Pull external images for offline use. |
| `./auplc-installer pack [--local]` | Create an offline deployment bundle. |
| `./auplc-installer rt install\|reinstall\|upgrade\|remove` | Runtime (Hub) only — for image/values changes without touching k3s. |
| `./auplc-installer dev [deploy\|upgrade\|reinstall]` | Dev cycle: rebuild hub image + restart, with a dev overlay (student=admin, pullPolicy=Never). |

## Flags

| Flag | Values / default | Notes |
| --- | --- | --- |
| `--gpu=TYPE` | `auto` (default), `phx`, `strix`, `strix-halo`, `9070xt`, `r9700`, `9600gre`, `rdna4`/`dgpu`, `gfxNNNN` | Auto-detect via rocminfo/KFD. Env `GPU_TYPE`. |
| `--courses=SPEC` | `all` (default), `basic`, `none`, or `cpu,gpu,Course-CV,...` | Restricts image build/pull **and** hides unselected courses in the spawn UI. Env `AUPLC_COURSES`. |
| `--image-source=SRC` | `pull` (default) or `build` | `pull` = registry; `build` = local from `dockerfiles/`. |
| `--image-registry=PREFIX` | default `ghcr.io/amdresearch` | Env `IMAGE_REGISTRY`. |
| `--image-tag=TAG` | default `latest` | GPU suffix appended automatically. Env `IMAGE_TAG`. Use `develop` for the preview UI. |
| `--runtime=MODE` | `docker` (default) or `containerd` | `docker` makes images visible to k3s immediately; `containerd` exports for offline. |
| `--courses`, `--mirror=`, `--mirror-pip=`, `--mirror-npm=` | — | Registry / PyPI / npm mirrors for restricted networks. |
| `-y`, `--yes` | — | Assume yes (scripted/CI). Env `AUPLC_YES=1`. |
| `--dry-run` (`--try-run`) | — | Preview only. |
| `-v`, `--verbose` | — | Stream every subprocess line. Env `AUPLC_VERBOSE=1`. |

### Examples

```bash
./auplc-installer install --dry-run
./auplc-installer install --image-source=pull --image-tag=develop
./auplc-installer install --gpu=strix-halo --courses=basic
./auplc-installer install --runtime=containerd --image-source=build
./auplc-installer install --mirror=mirror.example.com
```

## What a successful install looks like

```
  ✓ [1/8] Detecting GPU
  ✓ [2/8] Generating values overlay (initial)
  ✓ [3/8] Installing helm + k9s
  ✓ [4/8] Installing K3s (single-node)
  ✓ [5/8] Pulling custom + external images
  ✓ [6/8] Deploying ROCm GPU device plugin + node labeller
  ✓ [7/8] Refreshing values overlay from node labels
  ✓ [8/8] Deploying JupyterHub runtime (helm install + wait)

  Open in your browser: http://localhost:30890
  (auto-logged-in as 'student' — no login needed)
```

## Default deployment facts

The checked-in defaults describe a local deployment: NodePort **30890**,
`local-path` storage, ingress **disabled**, prePuller **disabled**, and
`custom.authMode: auto-login`. To change auth, courses, or accelerators, layer
a values overlay (see configure-aup-learning-cloud-courses) and
`./auplc-installer rt upgrade`.

## Offline / air-gapped (pack)

On a machine with Docker + internet:

```bash
./auplc-installer pack --gpu=strix-halo          # pull pre-built images into a bundle
./auplc-installer pack --gpu=strix-halo --local  # or build locally first
```

Transfer the bundle, then on the air-gapped box:

```bash
tar xzf auplc-bundle-gfx1151-*.tar.gz
cd auplc-bundle-gfx1151-*
sudo ./auplc-installer install
```

## Troubleshooting

| Symptom | Likely cause | First checks |
| --- | --- | --- |
| `detect-gpu` shows the wrong/no GPU | ROCm not seeing the device, wrong kernel | OEM kernel installed + rebooted (`uname -r`), `rocminfo`, pass `--gpu=` explicitly |
| Install fails pulling images | Registry/network or wrong tag | `--image-tag`, `--mirror=`, or `--image-source=build` |
| Hub pod `ImagePullBackOff` | Tag mismatch between overlay and registry | `kubectl describe pod -n jupyterhub`, align `--image-tag` |
| GPU notebook stays Pending | Device plugin/labeller not ready or label mismatch | `kubectl get ds -A | grep amd`, `kubectl describe node | grep amd.com/gpu` |
| `localhost:30890` refused | Proxy not up or NodePort changed | `kubectl get svc -n jupyterhub`, `kubectl get pods -n jupyterhub` |
| `docker` permission denied | User not in docker group | re-run `usermod -aG docker $USER` then re-login / `newgrp docker` |
| Need to re-apply values only | Changed the overlay, not images | `./auplc-installer rt upgrade` (don't reinstall k3s) |

## Out of scope

Multi-node / PXE clusters (use deploy-aup-learning-cloud), GitHub OAuth and
production TLS/ingress hardening, image authoring, and course-catalog edits
(those are their own skills). This skill targets the one-box install.
