# Develop AUP Learning Cloud courses — Reference

The new-course checklist, the directory layout, the `catalog.py` entry shape,
and troubleshooting. Workflow and gates are in [SKILL.md](SKILL.md).

## Source

- Repo README "Learning Solution" + `projects/{CV,DL,LLM,PhySim}/README.md`.
- `dockerfiles/Makefile` (course targets) and `dockerfiles/Courses/<NAME>/`.
- `auplc_installer/catalog.py` (the course catalog source of truth) and its
  mirrored bash `COURSE_CATALOG` / `BASE_TEAM_MAPPING`.
- Build details: build-aup-learning-cloud-images. Values wiring:
  configure-aup-learning-cloud-courses.

## Directory layout

```
projects/<NAME>/                 # curriculum: NN_*.ipynb labs, README.md, assets/
dockerfiles/Courses/<NAME>/      # Dockerfile + build.sh (FROM the GPU base)
dockerfiles/Makefile             # add a <name> target; add it to `courses`
auplc_installer/catalog.py       # add a Course(...) to COURSE_CATALOG + team map
runtime/values.yaml              # custom.resources.{images,requirements,metadata}
```

Existing toolkits to copy from: `projects/CV` (10 labs), `projects/DL` (12),
`projects/LLM` (9), `projects/PhySim` (Genesis robotics).

## Makefile target (mirror cv/dl)

```make
courses: cv dl llm physim <name>

<name>:
	cd Courses/<NAME> && BASE_IMAGE=$(GPU_BASE_IMAGE) bash ./build.sh
	docker tag ghcr.io/amdresearch/auplc-<name>:latest ghcr.io/amdresearch/auplc-<name>:latest-$(GPU_TARGET)
	$(MAKE) save-image IMAGE=ghcr.io/amdresearch/auplc-<name>:latest
```

GPU course images are tagged `:<IMAGE_TAG>-<gpu_target>` (e.g. `latest-gfx1151`).
`GPU_BASE_IMAGE` defaults to `ghcr.io/amdresearch/auplc-base:latest`.

## catalog.py entry

```python
COURSE_CATALOG: tuple[Course, ...] = (
    # ...existing entries...
    Course("Course-<NAME>", "auplc-<name>", True, "<name>", "<Display Name> Course"),
)
```

`Course(key, image_basename, gpu_required, make_target, display_name)`:

- `key` — matches `custom.resources.{images,requirements,metadata}` and
  `custom.teams.mapping` (convention: `Course-<NAME>`).
- `image_basename` — `auplc-<name>` (no registry/tag).
- `gpu_required` — `True` → GPU-tagged build; `False` → plain `:<tag>`.
- `make_target` — the `dockerfiles/Makefile` target.

Add the same row to the mirrored **bash** `COURSE_CATALOG` (byte-for-byte) and
add the key to the appropriate `BASE_TEAM_MAPPING` groups (e.g. `gpu`,
`official`, `AUP`, `native-users`, `github-users`). `COURSE_PRESET_BASIC` is
only `cpu, gpu, code-cpu, code-gpu`; new courses join `all`, not `basic`.

## Build and wire (hand-offs)

```bash
# build the new course image (build-images skill)
./auplc-installer img build <name> --gpu=<target>
# optional push for multi-node / offline
docker push ghcr.io/amdresearch/auplc-<name>:latest-<gpu_target>
```

Then, with configure-courses, add to the values overlay:

```yaml
custom:
  resources:
    images:
      Course-<NAME>: "ghcr.io/amdresearch/auplc-<name>:latest"
    requirements:
      Course-<NAME>: { cpu: "0", memory: "0Gi", amd.com/gpu: "1" }
    metadata:
      Course-<NAME>:
        group: "TEACHING LABS"
        description: "<Display Name> Course"
        accelerator: "GPU"
        acceleratorKeys: [strix-halo]
        allowGitClone: true
        resourceType: "notebook"
  teams:
    mapping:
      gpu: [..., Course-<NAME>]
```

Apply with `./auplc-installer rt upgrade` (single) or `helm upgrade` (multi).

## Troubleshooting

| Symptom | Likely cause | First checks |
| --- | --- | --- |
| `unknown course key` from installer | `catalog.py`/bash table out of sync, or key typo | Make both tables identical; use the exact `Course-<NAME>` key |
| Course image build fails | Missing base image or bad Dockerfile context | Build `base-rocm` first; verify `dockerfiles/Courses/<NAME>` paths |
| Notebooks missing in the pod | `COPY` path wrong in the course Dockerfile | Confirm `projects/<NAME>/` is copied into the image home tree |
| Course not in spawn UI | Values catalog/team mapping incomplete | Add the key in all of images/requirements/metadata + `teams.mapping` |
| GPU course Pending | `acceleratorKeys` → node label mismatch | `kubectl describe node | grep amd.com/gpu.product-name` |
| Wrong gfx kernels at runtime | Built for the wrong `--gpu` | Rebuild with the correct target |
