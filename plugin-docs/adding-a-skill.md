# Adding a skill

This catalog is designed to grow. Each capability for working with AUP Learning
Cloud (deploying, course configuration, image building, upgrades, troubleshooting)
is its own self-contained skill folder under `skills/`. Adding one is a fixed,
five-step procedure.

## 1. Copy the template

```bash
cp -r templates/skill-template skills/<your-skill-name>
```

Use a `lowercase-with-hyphens` name tied to the outcome (e.g.
`configure-aup-learning-cloud-courses`, `build-aup-learning-cloud-images`,
`upgrade-aup-learning-cloud`). Avoid generic names like `helper` or `utils`.

## 2. Write `SKILL.md`

- Set `name:` in the frontmatter to **exactly** the directory name.
- Write a `description:` in the third person that states **what** the skill
  produces and **when** an agent should reach for it, including the trigger
  words a user is likely to say. Keep it under 1024 characters.
- **Assign a category.** Pick exactly one group from
  [skill-categories.md](skill-categories.md) and **prepend its `Group:` tag** to
  the start of the `description` (e.g. `Group: Maintain AUP Learning Cloud.`).
  This is what lets an agent route to the right group first.
- Keep the body under 500 lines. Push long reference material into sibling
  files (`reference.md`, `examples.md`, ...) linked one level deep.

See [CONTRIBUTING.md](../CONTRIBUTING.md) for the full authoring conventions.

## 3. Write `skill-card.md`

Fill in the `## Description` and `## Owner` sections. See
[skill-cards.md](skill-cards.md).

## 4. List the skill in the catalog

The repo ships as a single bundled plugin (`source: "./"`), so the plugin
manifests do **not** need a per-skill entry — dropping the folder under
`skills/` is enough for every install method to pick it up. Add a row to the
catalog table in the [skills README](../README-SKILL.md) **under the skill's group section**,
list it under that group in [skill-categories.md](skill-categories.md) so people
can discover it, then keep the Cursor manifests in sync:

```bash
./.github/scripts/publish.sh   # regenerates .cursor-plugin/ from the canonical sources
```

## 5. Validate

```bash
./.github/scripts/check.sh     # same command CI runs
```

CI runs the same validation on every pull request via
`.github/workflows/validate-skills.yml`, fanning out one job per skill so a single
broken skill is easy to spot.

## Ideas for future skills

The catalog now covers install, deploy, configure (courses), build, upgrade,
and troubleshoot, plus auth, user/quota management, monitoring, network/storage
exposure, per-user repo cloning, and course authoring (see the
[skills README](../README-SKILL.md)). Natural next additions, each following the same
procedure:

| Skill | Outcome |
| --- | --- |
| `backup-aup-learning-cloud` | Back up and restore the Hub DB PVC and user home data (snapshot, off-cluster copy, restore drill). |
| `offline-aup-learning-cloud` | Drive the air-gapped `pack`/`pack --local` bundle workflow end to end, including registry/PyPI/npm mirrors. |
| `tune-aup-learning-cloud-resources` | Right-size per-course CPU/memory/GPU requirements, prePuller, and node scheduling for a given fleet. |
