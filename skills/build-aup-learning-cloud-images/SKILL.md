---
name: build-aup-learning-cloud-images
description: >-
  Group: Plan & deploy AUP Learning Cloud. Builds and publishes the AUP Learning
  Cloud Docker images — the Hub image and
  the CPU/GPU notebook and course images — with ./auplc-installer img build.
  Use when the user wants to build, rebuild, tag, or push AUPLC images, mentions
  img build / img pull, the dockerfiles/ directory, auplc-hub / auplc-base /
  auplc-default / auplc-cv / auplc-dl / auplc-llm / auplc-physim / code-cpu /
  code-gpu, a gfx-specific image tag, the GHCR registry, code-server VS Code
  extensions, or preparing images for an offline/registry deployment. Covers
  GPU-target tagging and pushing to a registry. Do not use to install or deploy
  a cluster (install-/deploy-aup-learning-cloud) or to edit the course catalog
  in values.yaml (configure-aup-learning-cloud-courses).
---

# Build AUP Learning Cloud images

Produce the container images the platform runs: the Hub image plus the notebook
and course images, GPU-tagged per accelerator family, and (optionally) pushed
to a registry for a multi-node or offline deployment.

`./auplc-installer img build` is the source of truth and wraps
`dockerfiles/`. Your job is to pick the right targets + GPU tag, run the build,
and (if asked) push. Target list, tag scheme, and the push flow are in
**[reference.md](reference.md)**.

## Prerequisites

- A checkout of `aup-learning-cloud`; Docker with enough disk (GPU images are
  large) and, for course images, network access to base layers.
- For pushing: `docker login` to the target registry (default
  `ghcr.io/amdresearch`).
- Know the **GPU target** for GPU images (`phx`, `strix`, `strix-halo`,
  `9070xt`, `r9700`, …) — GPU images are tagged `:<tag>-<gpu_target>`.

## Targets at a glance

| Target | Image | GPU-tagged? |
| --- | --- | --- |
| `hub` | `auplc-hub` | no (infra image) |
| `base-cpu` | `auplc-default` | no |
| `base-rocm` | `auplc-base` | yes |
| `code-cpu` / `code-gpu` | `auplc-code-cpu` / `auplc-code-gpu` | gpu only |
| `cv` / `dl` / `llm` / `physim` | `auplc-cv` / `-dl` / `-llm` / `-physim` | yes |
| `all` | hub + selected courses | mixed |

## Workflow

1. **Decide scope.** Which targets, and the GPU target for ROCm images. For a
   demo rebuild of one course, build just that target; avoid `all` unless
   needed.
2. **Build.**

   ```bash
   ./auplc-installer img build hub
   ./auplc-installer img build base-rocm --gpu=strix
   ./auplc-installer img build cv dl --gpu=strix-halo
   ./auplc-installer img build --image-tag=develop base-rocm --gpu=strix-halo
   ```

3. **(Optional) Push** to the registry referenced by `custom.resources.images`:

   ```bash
   docker push ghcr.io/amdresearch/auplc-hub:latest
   docker push ghcr.io/amdresearch/auplc-base:latest-gfx1151   # GPU-tagged example
   ```

4. **Wire the tag in.** If you changed the tag, update
   `custom.resources.images` (and `prePuller.extraImages` if used) — that's the
   configure-aup-learning-cloud-courses skill — then `rt upgrade` / `helm
   upgrade`.

## Editing the Hub image — preserve attribution

If a change touches Hub source, **all four attribution layers from the project
`AGENTS.md` must stay intact** (do not remove/rename any):

1. `X-Powered-By: AUP Learning Cloud` header in
   `runtime/hub/core/jupyterhub_config.py`.
2. `PlatformInfoHandler` (`/api/platform`, unauthenticated) in
   `runtime/hub/core/handlers.py`.
3. The `<footer id="auplc-powered-by-footer">` in
   `runtime/hub/frontend/templates/page.html` (kept outside all Jinja blocks).
4. `PLATFORM_NAME` / `PLATFORM_VENDOR` / `PLATFORM_WEBSITE` in
   `runtime/hub/frontend/packages/shared/src/branding.ts` (import, never
   hardcode the platform string).

Also keep the `Copyright (C) … Advanced Micro Devices, Inc.` header on every
source file (MIT requirement).

## Safety

- **Disk + time.** GPU/course image builds are large and slow — confirm before
  `all` or `--image-source=build` on a small box.
- **Pushing is publishing.** Confirm the registry, repo, and tag before any
  `docker push`; never push secrets baked into a layer.
- **code-server safety.** The code images run `code-server --auth none` on port
  8888; this is safe only behind the Hub proxy. Never expose that port via
  NodePort/LoadBalancer/ingress. Confirm VS Code/OpenVSX extension licenses
  before adding to `dockerfiles/Code/extensions.txt`.

## Reference

Full target list, the gfx tag scheme, `img pull` for offline, registry/mirror
flags, and troubleshooting: [reference.md](reference.md).
