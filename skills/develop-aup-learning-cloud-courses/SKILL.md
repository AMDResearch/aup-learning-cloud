---
name: develop-aup-learning-cloud-courses
description: >-
  Group: Course & other editor. Authors a new learning toolkit for AUP Learning
  Cloud end to end: write the
  course notebooks under projects/<NAME>/, package them into a course Docker
  image (dockerfiles/Courses/<NAME>/ + a Makefile target on the ROCm GPU base),
  register the course in auplc_installer/catalog.py (COURSE_CATALOG + team
  mapping), then hand off to build + values wiring. Use when an educator wants
  to add a new course or lab set, create a toolkit like CV/DL/LLM/PhySim, turn a
  notebook folder into a spawnable course, add a Dockerfile/build.sh for a
  course, or add a course key to the catalog. Triggers include projects/CV,
  projects/DL, projects/LLM, projects/PhySim, dockerfiles/Courses,
  COURSE_CATALOG, "add a course", "new toolkit". Do not use to only build an
  existing image (build-aup-learning-cloud-images), to only edit the values
  catalog for an existing image (configure-aup-learning-cloud-courses), or to
  clone a user's repo at runtime (configure-aup-learning-cloud-repos).
---

# Develop AUP Learning Cloud courses

Create a brand-new course (a set of hands-on notebooks) and make it a spawnable
environment: author the curriculum, bake it into a course image, register the
course key, then build and wire it into the spawn UI. This is the
author/educator workflow that *produces* what configure-courses later tunes.

The notebooks and the image build context are the source of truth; the catalog
keeps keys consistent. Per-file conventions, the new-course checklist, and the
directory map are in **[reference.md](reference.md)**.

## Prerequisites

- A checkout of `aup-learning-cloud`; Docker with enough disk (course images are
  large); the ROCm GPU base image available (`auplc-base`, built by
  build-images or pulled).
- Familiarity with the existing toolkits under `projects/{CV,DL,LLM,PhySim}` as
  patterns.
- For the build + deploy hand-off: the build-images and configure-courses skills.

## Where a course lives (four coordinated places)

A new course `Course-<NAME>` must be consistent across:

1. **Curriculum** — `projects/<NAME>/` (the `.ipynb` labs, README, assets).
2. **Image build context** — `dockerfiles/Courses/<NAME>/` (Dockerfile +
   `build.sh`) layered on the GPU base, plus a `Makefile` target.
3. **Catalog** — a `Course(...)` entry in `auplc_installer/catalog.py`
   `COURSE_CATALOG` (key, image basename, `gpu_required`, make target, display
   name) and the mirrored bash `COURSE_CATALOG`, plus `BASE_TEAM_MAPPING`.
4. **Values** — `custom.resources.{images,requirements,metadata}.<key>` and
   `custom.teams.mapping` (this is the configure-courses skill).

## Workflow

1. **Author the curriculum.** Add the notebooks under `projects/<NAME>/`
   following the existing numbering/README pattern (e.g. `LLM01-…`). Keep the
   per-file `Copyright (C) … Advanced Micro Devices, Inc.` header (MIT).
2. **Create the image build context.** Add `dockerfiles/Courses/<NAME>/` with a
   `Dockerfile` + `build.sh` modeled on an existing course, `FROM` the GPU base
   (`BASE_IMAGE=ghcr.io/amdresearch/auplc-base:latest`), and `COPY` the
   `projects/<NAME>/` content into the image. Pin pip deps for reproducibility.
3. **Add the Makefile target.** Add a `<name>` target in `dockerfiles/Makefile`
   that builds, GPU-tags (`:latest-$(GPU_TARGET)`), and `save-image`s — mirror
   the `cv`/`dl` targets. Add it to the `courses` aggregate.
4. **Register the course key.** Add a `Course("Course-<NAME>", "auplc-<name>",
   True, "<name>", "<Display Name>")` to `COURSE_CATALOG` in `catalog.py`, keep
   the bash table byte-for-byte identical, and add the key to the relevant
   `BASE_TEAM_MAPPING` groups.
5. **Build the image** (hand off to build-images):

   ```bash
   ./auplc-installer img build <name> --gpu=<target>
   ```

6. **Wire it into values** (hand off to configure-courses): add the key under
   `custom.resources.images/requirements/metadata` and `custom.teams.mapping`,
   then `rt upgrade` / `helm upgrade`.
7. **Verify.** The course appears in its spawn-UI `group` for mapped teams, and
   a launched pod runs the new image with the notebooks present under the home
   tree.

## Safety

- **Large/slow builds.** Course images are big; confirm disk and time before a
  full build, and prefer building just the new `<name>` target.
- **Keep the catalog in sync.** `catalog.py` and the mirrored bash table must
  match exactly, or `--courses` selection/overlay generation breaks.
- **Licensing.** Only bundle datasets, models, and third-party code whose
  licenses permit redistribution; keep AMD copyright headers on new source.
- **Attribution.** If any change touches Hub source (not typical for a course),
  preserve the four attribution layers from the project `AGENTS.md`.
- Never commit secrets or large binary blobs that belong in object storage.

## Reference

The new-course checklist, the `projects/`/`dockerfiles/Courses/` layout, the
`catalog.py` entry shape, GPU-tag rules, and troubleshooting:
[reference.md](reference.md).
