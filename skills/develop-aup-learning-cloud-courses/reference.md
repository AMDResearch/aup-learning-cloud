# Develop AUP Learning Cloud courses — Reference

The new-course checklist, the directory layout, the `catalog.py` entry shape,
and troubleshooting. Workflow and gates are in [SKILL.md](SKILL.md).

## Source

- aup-teaching-labs: `projects/Template/README.md` (course layout, package
  rules, local builds) and `.github/build-config.json` (courses CI builds).
- This repo: `projects/aup-teaching-labs` (submodule),
  `projects/course-base-version.txt` (base release for every course),
  `dockerfiles/Makefile` (course targets), and `auplc_installer/catalog.py`
  (the course catalog source of truth).
- Build details: build-aup-learning-cloud-images. Values wiring:
  configure-aup-learning-cloud-courses.

## Directory layout

```
aup-teaching-labs/
  projects/<NAME>/               # copied from projects/Template
    course_data/                 # notebooks and materials, copied to /opt/workspace/<NAME>/
    requirements.txt             # pinned pip packages
    apt-packages.txt             # Ubuntu packages
    Dockerfile                   # FROM the base CI passes in BASE_IMAGE
  .github/build-config.json      # add the course to `courses`

aup-learning-cloud/
  projects/aup-teaching-labs     # submodule; bump to the commit with the course
  projects/course-base-version.txt
  dockerfiles/Makefile           # add a <name> target; add it to `courses`
  auplc_installer/catalog.py     # add a Course(...) to COURSE_CATALOG + team map
  runtime/values.yaml            # custom.resources.{images,requirements,metadata}
```

Existing courses to copy from (in aup-teaching-labs): `projects/CV` (8 labs),
`projects/DL` (12), `projects/LLM` (14), and
`projects/Physical-AI/Physical-Simulation/Genesis-Simulation` (6, Genesis
robotics). New courses start from `projects/Template`.

## build-config.json entry (aup-teaching-labs)

```json
"courses": [
  ...,
  {"name": "<NAME>", "image": "auplc-<name>", "context": "projects/<NAME>"}
]
```

Add `"disk_cleanup": true` if the image is too large for the default runner
disk. CI builds the course for every GPU target on the base selected in
`projects/course-base-version.txt` here, or on the release in
`projects/<NAME>/base-version.override.txt` if the course cannot use it yet.

## Makefile target (mirror cv/dl)

```make
courses: cv dl llm physim <name>

<name>:
	$(call build-course,<NAME>,auplc-<name>,projects/<NAME>)
```

The third argument is the context inside the submodule, the same as in
`build-config.json`. GPU course images are tagged `:<IMAGE_TAG>-<gpu_target>`
(e.g. `latest-gfx1151`). Local builds use `GPU_BASE_IMAGE`, which defaults to
`ghcr.io/amdresearch/auplc-base:latest`.

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

Add the key to the appropriate `BASE_TEAM_MAPPING` groups (e.g. `gpu`,
`official`, `AUP`, `native-users`, `github-users`). `COURSE_PRESET_BASIC` is
only `cpu, gpu, code-cpu, code-gpu`; new courses join `all`, not `basic`.

## Build and wire (hand-offs)

```bash
# build the new course image locally (build-images skill)
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
        defaultPath: "/opt/workspace/<NAME>"
  teams:
    mapping:
      gpu: [..., Course-<NAME>]
```

Keep `defaultPath` equal to the image `WORKDIR`; `make -C dockerfiles
verify-resource-contracts` checks the official images. Apply with
`./auplc-installer rt upgrade` (single) or `helm upgrade` (multi).

## Troubleshooting

| Symptom | Likely cause | First checks |
| --- | --- | --- |
| `unknown course key` from installer | Key missing from `catalog.py`, or key typo | Use the exact `Course-<NAME>` key in `COURSE_CATALOG` |
| `Dockerfile not found; run: git submodule update --init` | Submodule not checked out | Run it, then rebuild |
| Course image build fails | Missing base image or wrong context | Build `base-rocm` first; check the Makefile context matches `build-config.json` |
| CI does not build the course | Not listed in `build-config.json`, or submodule not bumped | Check the teaching-labs entry and the submodule commit |
| Notebooks missing in the pod | Materials outside `course_data/` | Keep materials in `course_data/`; check the image `WORKDIR` |
| Course not in spawn UI | Values catalog/team mapping incomplete | Add the key in all of images/requirements/metadata + `teams.mapping` |
| GPU course Pending | `acceleratorKeys` → node label mismatch | `kubectl describe node | grep amd.com/gpu.product-name` |
| Wrong gfx kernels at runtime | Built for the wrong `--gpu` | Rebuild with the correct target |
