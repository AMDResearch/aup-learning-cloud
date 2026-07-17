---
name: skill-template
description: >-
  One- to three-sentence routing description in the third person. State WHAT
  this skill produces and WHEN an agent should use it, and list the trigger
  words a user is likely to say (product names, file names, commands, error
  messages). Keep under 1024 characters. Add negative triggers if the
  boundary is easily crossed (e.g. "Do not use for the single-node installer
  flow"). Replace this entire block when you copy the template.
---

# Skill title

One paragraph: what this skill does and the single, measurable outcome it
drives toward.

## Prerequisites

- List the tools, access, and state the agent must have before starting
  (e.g. `kubectl` + `helm` on the operator machine, SSH access, a checkout of
  `aup-learning-cloud`).

## Workflow

Describe the ordered steps. Use exact commands for fragile operations and
plain instructions for steps with acceptable variation. Keep the body under
500 lines; move long reference material into a sibling `reference.md` and link
to it one level deep.

1. Step one.
2. Step two.

## Safety

Enumerate the risky or irreversible actions that REQUIRE explicit user
confirmation before running. Never commit, push, or write real secrets into
tracked files.

## Reference

Link to sibling files such as [reference.md](reference.md).
