---
name: develop-aup-learning-cloud-courses
description: >-
  Group: Course & other editor. Authors a new learning toolkit for AUP Learning
  Cloud end to end: create the course (notebooks, packages, Dockerfile) in the
  aup-teaching-labs repo from projects/Template, list it in that repo's
  .github/build-config.json, then in aup-learning-cloud bump the
  projects/aup-teaching-labs submodule, add a dockerfiles/Makefile target,
  register the course in auplc_installer/catalog.py (COURSE_CATALOG + team
  mapping), and hand off to values wiring. Use when an educator wants to add a
  new course or lab set, create a toolkit like CV/DL/LLM/PhySim, turn a
  notebook folder into a spawnable course, or add a course key to the catalog.
  Triggers include projects/aup-teaching-labs,
  projects/Template, build-config.json, COURSE_CATALOG, "add a
  course". Do not use to only build an existing image
  (build-aup-learning-cloud-images), to only edit the values catalog for an
  existing image (configure-aup-learning-cloud-courses), or to clone a user's
  repo at runtime (configure-aup-learning-cloud-repos).
---

# Develop AUP Learning Cloud courses

Create a brand-new course (a set of hands-on notebooks) and make it a spawnable
environment: author the course in aup-teaching-labs, pull it into this repo,
register the course key, then build and wire it into the spawn UI. This is the
author/educator workflow that *produces* what configure-courses later tunes.

Course content and its image build context live in
[aup-teaching-labs](https://github.com/AMDResearch/aup-teaching-labs), included
here as the `projects/aup-teaching-labs` submodule. This repo selects the base
release and builds and publishes the course images. Per-file conventions, the
new-course checklist, and the directory map are in
**[reference.md](reference.md)**.

## Prerequisites

- Checkouts of `aup-teaching-labs` and `aup-learning-cloud` (with
  `git submodule update --init`); Docker with enough disk (course images are
  large).
- Familiarity with the existing courses in aup-teaching-labs (`projects/CV`,
  `projects/DL`, `projects/LLM`,
  `projects/Physical-AI/Physical-Simulation/Genesis-Simulation`) and its
  `projects/Template` README.
- For the build + deploy hand-off: the build-images and configure-courses skills.

## Where a course lives (four coordinated places)

A new course `Course-<NAME>` must be consistent across:

1. **Course** — `aup-teaching-labs/projects/<NAME>/`: materials, package
   lists, and the Dockerfile, copied from `projects/Template`. Its entry in the
   teaching-labs `.github/build-config.json` `courses` list (name, image,
   context) is what CI builds.
2. **Submodule + Makefile** — the `projects/aup-teaching-labs` submodule
   pointer in this repo, and a `dockerfiles/Makefile` target that builds the
   same context for local builds.
3. **Catalog** — a `Course(...)` entry in `auplc_installer/catalog.py`
   `COURSE_CATALOG` (key, image basename, `gpu_required`, make target, display
   name), plus `BASE_TEAM_MAPPING`.
4. **Values** — `custom.resources.{images,requirements,metadata}.<key>` and
   `custom.teams.mapping` (this is the configure-courses skill).

## Workflow

1. **Create the course in aup-teaching-labs.** Copy `projects/Template` to
   `projects/<NAME>/` and follow its README: materials in `course_data/`,
   pinned packages in `requirements.txt` / `apt-packages.txt`. Keep the
   per-file `Copyright (C) … Advanced Micro Devices, Inc.` header (MIT). Build
   and test it locally with the template's `build.sh` / `build.ps1`.
2. **List it for CI.** Add `{"name": "<NAME>", "image": "auplc-<name>",
   "context": "projects/<NAME>"}` to `courses` in the teaching-labs
   `.github/build-config.json`, and merge the course there.
3. **Bump the submodule here.** Update `projects/aup-teaching-labs` to the
   teaching-labs commit with the course. The `build-courses` job in
   `.github/workflows/docker-build.yml` builds every listed course on the base
   in `projects/course-base-version.txt`.
4. **Add the Makefile target.** Add a `<name>` target in `dockerfiles/Makefile`
   that calls `build-course` with the same context, mirroring `cv`/`dl`, and
   add it to the `courses` aggregate.
5. **Register the course key.** Add a `Course("Course-<NAME>", "auplc-<name>",
   True, "<name>", "<Display Name>")` to `COURSE_CATALOG` in `catalog.py`, and
   add the key to the relevant `BASE_TEAM_MAPPING` groups.
6. **Build the image locally if needed** (hand off to build-images):

   ```bash
   ./auplc-installer img build <name> --gpu=<target>
   ```

7. **Wire it into values** (hand off to configure-courses): add the key under
   `custom.resources.images/requirements/metadata` and `custom.teams.mapping`,
   then `rt upgrade` / `helm upgrade`.
8. **Verify.** The course appears in its spawn-UI `group` for mapped teams, and
   a launched pod runs the new image and opens in the course directory.

## Safety

- **Large/slow builds.** Course images are big; confirm disk and time before a
  full build, and prefer building just the new `<name>` target.
- **Keep the contexts in sync.** The Makefile target, the teaching-labs
  `build-config.json` entry, and the `catalog.py` make target must name the
  same course, or local builds and CI produce different images.
- **Licensing.** Only bundle datasets, models, and third-party code whose
  licenses permit redistribution; keep AMD copyright headers on new source.
- **Attribution.** If any change touches Hub source (not typical for a course),
  preserve the four attribution layers from the project `AGENTS.md`.
- Never commit secrets or large binary blobs that belong in object storage.

## Reference

The new-course checklist, the repository layout, the `catalog.py` entry shape,
GPU-tag rules, and troubleshooting: [reference.md](reference.md).
