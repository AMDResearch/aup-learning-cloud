# Build AUP Learning Cloud images — Reference

Target list, tag scheme, push/pull flows, and troubleshooting for
`./auplc-installer img build`. Workflow and the attribution rules are in
[SKILL.md](SKILL.md).

## Source

- Repo README "Available Notebook and Coding Environments" + `./auplc-installer help`.
- `auplc_installer/catalog.py` (course → image basename + make target).
- `dockerfiles/` (the actual build context, incl. `dockerfiles/Code/extensions.txt`).

## Target → image map

| `img build` target | Image basename | GPU-tagged | Make target |
| --- | --- | --- | --- |
| `hub` | `auplc-hub` | no | (hub) |
| `base-cpu` | `auplc-default` | no | `base-cpu` |
| `base-rocm` | `auplc-base` | yes | `base-rocm` |
| `code-cpu` | `auplc-code-cpu` | no | `code-cpu` |
| `code-gpu` | `auplc-code-gpu` | yes | `code-gpu` |
| `cv` | `auplc-cv` | yes | `cv` |
| `dl` | `auplc-dl` | yes | `dl` |
| `llm` | `auplc-llm` | yes | `llm` |
| `physim` | `auplc-physim` | yes | `physim` |
| `all` | hub + selected courses | mixed | — |
| `code` | both code-server images | — | — |

## Tag scheme

- Plain (non-GPU) images: `:<IMAGE_TAG>` (default `IMAGE_TAG=latest`).
- GPU images: `:<IMAGE_TAG>-<gpu_target>` — the GPU suffix is appended
  automatically from `--gpu` (e.g. `auplc-base:latest-gfx1151` for strix-halo).
- Registry prefix: `--image-registry` / `IMAGE_REGISTRY`
  (default `ghcr.io/amdresearch`).

## Build examples

```bash
./auplc-installer img build hub
./auplc-installer img build base-rocm --gpu=strix
./auplc-installer img build cv dl llm physim --gpu=strix-halo
./auplc-installer img build --image-tag=develop base-rocm --gpu=strix-halo
./auplc-installer img build all --gpu=strix-halo            # hub + all courses
```

Relevant global flags (see install skill for the full table): `--gpu`,
`--image-tag`, `--image-registry`, `--mirror=`, `--mirror-pip=`, `--mirror-npm=`,
`-v/--verbose`.

## Push to a registry

```bash
docker login ghcr.io
docker push ghcr.io/amdresearch/auplc-hub:latest
docker push ghcr.io/amdresearch/auplc-default:latest
docker push ghcr.io/amdresearch/auplc-base:latest-gfx1151
docker push ghcr.io/amdresearch/auplc-cv:latest-gfx1151
```

Then point `custom.resources.images` (and `prePuller.extraImages` if used) at
the pushed tags — see configure-aup-learning-cloud-courses.

## Offline: pull external images

```bash
./auplc-installer img pull        # fetch external (non-custom) images for offline use
```

For a full air-gapped bundle (custom + external + installer), use
`./auplc-installer pack` (see install-aup-learning-cloud-single-node).

## code-server images

The `code-cpu` / `code-gpu` images launch `code-server --auth none` on port
**8888**, safe only behind the JupyterHub proxy auth boundary — never expose
that port directly. Built-in extensions come from
`dockerfiles/Code/extensions.txt` plus local `.vsix` packages (e.g. the AUPLC
Back-to-Hub extension). Confirm extension licenses / marketplace terms before
adding any.

## Troubleshooting

| Symptom | Likely cause | First checks |
| --- | --- | --- |
| Build fails pulling base layers | Network / mirror | `--mirror=`, `--mirror-pip=`, retry; check Docker daemon proxy |
| `no space left on device` | GPU/course images are large | Free disk, build fewer targets, prune `docker image prune` |
| Wrong gfx kernels at runtime | Built for the wrong `--gpu` target | Rebuild with the correct `--gpu`; for Phoenix note `HSA_OVERRIDE_GFX_VERSION` |
| Pushed image not used by Hub | `custom.resources.images` tag not updated | Update the overlay + `rt upgrade`/`helm upgrade` |
| Attribution check fails in review | A Hub-source edit dropped a layer | Restore all four `AGENTS.md` layers + file copyright headers |

## Out of scope

Installing/deploying a cluster, editing the values course catalog, and authoring
new course curricula (notebooks). This skill builds and publishes the images.
