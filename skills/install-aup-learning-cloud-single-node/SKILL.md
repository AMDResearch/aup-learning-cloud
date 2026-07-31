---
name: install-aup-learning-cloud-single-node
description: >-
  Group: Plan & deploy AUP Learning Cloud. Installs AUP Learning Cloud on a
  single machine with the ./auplc-installer
  flow (single-node k3s + JupyterHub for an AMD GPU/APU workstation). Use when
  the user wants to install, set up, try, or demo AUP Learning Cloud / AUPLC on
  one box, mentions ./auplc-installer, the installer TUI, "install" / "quick
  start" / "single-node", --gpu / --courses / --image-source flags, a Ryzen AI
  APU or Radeon dGPU dev box, localhost:30890, or uninstalling it. Also covers
  the OEM kernel + Docker prerequisites and offline (pack) bundles. Do not use
  for multi-node or PXE/netboot clusters (use deploy-aup-learning-cloud), for
  building images (build-aup-learning-cloud-images), or for editing courses
  (configure-aup-learning-cloud-courses).
---

# Install AUP Learning Cloud (single node)

Stand up AUP Learning Cloud on one machine using the project's own installer:
detect the GPU, install single-node k3s, pull images, deploy the ROCm device
plugin, and `helm install` the Hub so the user can open `localhost:30890` and
spawn notebooks. This is the "quick start / dev / demo" path.

The installer is the source of truth. Your job is to confirm prerequisites,
pick the right flags, run it (gating the risky steps), and verify. Full flag
table, offline flow, and troubleshooting are in **[reference.md](reference.md)**.

## Prerequisites

- A checkout of `aup-learning-cloud` (run from its root).
- Hardware: a supported **Ryzen AI 300-series+ APU** or **Radeon 9000-series**
  GPU; 32 GB+ RAM (64 GB recommended); 500 GB+ SSD.
- **Ubuntu 24.04**. Docker installed and usable without `sudo`
  (`docker run hello-world` as the user).
- **Ryzen AI APU only:** the ROCm OEM kernel
  (`sudo apt install linux-oem-6.14`) and a reboot. Radeon dGPU
  boxes typically use the stock kernel — confirm against ROCm docs.
- For the interactive TUI: `python3-questionary` + `python3-prompt-toolkit`
  (apt), or `pip install questionary prompt_toolkit` in a venv. The
  non-interactive `./auplc-installer install` does not need these.

## Phase 1 — Interview (keep it short)

1. **GPU**: let the installer auto-detect, or have the user name it so you can
   pass `--gpu` (`phx`, `strix`, `strix-halo`, `9070xt`, `r9700`, `9600gre`,
   `rdna4`). Confirm with `./auplc-installer detect-gpu`.
2. **Courses**: `all` (default), `basic` (cpu/gpu + code-server), `none`
   (Hub only), or an explicit list (`cpu,gpu,Course-CV`).
3. **Image source**: `pull` (default, from `ghcr.io/amdresearch`) or `build`
   (local from `dockerfiles/`). For a quick demo prefer `pull`.
4. **Online or offline**: a normal machine with internet, or an air-gapped one
   that needs a `pack` bundle (see reference).
5. **Access mode**: interactive and scripted installs default to the `personal`
   shared student session. Select local managed accounts explicitly with
   `--access-mode=local --admin-username=<name>`.

## Phase 2 — Verify the environment

```bash
docker run --rm hello-world            # docker works rootless
uname -r                               # OEM kernel on Ryzen AI APU
./auplc-installer detect-gpu           # installer agrees with the hardware
./auplc-installer install --dry-run    # prints the Configuration summary, no changes
```

Read the `--dry-run` summary back to the user and **get confirmation before the
real install** — it installs k3s system-wide and needs sudo.

## Phase 3 — Install (confirmation gate)

Default, opinionated path:

```bash
./auplc-installer install                       # auto GPU, all courses, pull images
# or pin choices:
./auplc-installer install --gpu=strix-halo --courses=basic --image-tag=develop
```

The installer runs 8 stages (detect GPU → values overlay → helm+k9s → k3s →
pull images → ROCm device plugin + labeller → refresh overlay from node labels
→ deploy Hub). It prompts for sudo once. Use `-y` only for scripted/CI runs.

## Phase 4 — Verify

```bash
kubectl get nodes                       # the node is Ready
kubectl get pods -n jupyterhub          # hub + proxy Running, no CrashLoop/ImagePull
```

Open `http://localhost:30890` — local interactive installs display a login form;
sign in with the configured administrator credentials. Scripted `personal`
installs retain the compatibility shared student session. The NodePort is 30890,
storage is `local-path`, and ingress is disabled. Spawn a CPU notebook, then a
GPU notebook, and confirm the GPU pod schedules.

If Helm fails, inspect `helm status jupyterhub -n jupyterhub` before retrying.
For a Hub-only retry, use `./auplc-installer rt upgrade` or
`./auplc-installer rt reinstall`; both retain `jupyterhub-admin-credentials`.
Do not delete the Secret unless intentionally resetting local credentials.

## Safety

Stop and get explicit confirmation before:

- The real `install` (installs k3s + a containerd/Docker runtime, needs sudo).
- `./auplc-installer uninstall` (removes k3s **and** the runtime; data loss).
- Switching `--runtime` (docker ↔ containerd) on an existing install.
- Any `--image-source=build` run on a slow/low-disk box (large local builds).

Never commit changes to the checkout. The installer writes a local values
overlay (e.g. `values.local.yaml`); do not commit it.

Local mode remains localhost-oriented MVP guidance only. It does not configure
TLS or restrict NodePort LAN reachability, so credentials are not a network
authorization boundary.

## Reference

Flag-by-flag table, the offline `pack`/air-gapped flow, `dev`/`rt`
subcommands, default-values facts, and troubleshooting: [reference.md](reference.md).
