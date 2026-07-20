# Skill cards

Every skill in this catalog ships a `skill-card.md` next to its `SKILL.md`. The card is a short, human-facing governance record: it tells a reviewer *what* the skill is and *who* owns it, without making them read the source first.

A `SKILL.md` is written for the agent (routing and instructions). A skill card is written for the people deciding whether to trust, install, or maintain the skill.

## Required sections

The card is intentionally minimal. Two sections are required, each a top-level `##` heading with non-empty body text:

| Section | Question it answers |
| --- | --- |
| Description | What does this skill do, in one sentence? |
| Owner | Who is accountable for maintaining it? |

The validator (`.github/scripts/validate_skills.py`) fails any skill whose card is missing or whose required sections are absent or empty.

## Template

Copy this into `skills/<your-skill>/skill-card.md`:

```markdown
# Skill Card

## Description

<one sentence: what the skill does, for whom>

## Owner

<team or org accountable for maintenance, e.g. AMD Research>
```

## Writing a good Description

Keep it to one sentence that states the outcome, matching the marketplace blurb. Avoid restating internal mechanics (that belongs in `SKILL.md`).

```
Good: Deploy AUP Learning Cloud onto a multi-AIPC PXE/k3s cluster end to end.
Bad:  Runs a series of Ansible playbooks and Helm commands in order.
```
