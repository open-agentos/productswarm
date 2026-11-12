---
id: GOV-0041
title: The planner closes issues a merger-merged PR left open; the merger keeps `issues: read`
status: in-force
kind: ruling
question: "#812"
domain: security
shape: authoritative
classification:
  reversibility: one-way
  blast_radius: repo
  nature: values
  knowledge: shared
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-12
review_by: 2027-02-28
supersedes: []
applies_to:
  paths: [".github/workflows/merger.yml", "roles/planner.md"]
  roles: [planner]
  situations:
    - an issue stays open after the merger App merged the PR that closes it
    - proposing `issues: write` or any other issue right for the merger App
    - building or changing the planner's daily step that closes issues merged PRs left open
---

## Ruling

The merger App's rights stay as GOV-0028 sets them, including `issues: read`. The planner, which already holds `issues: write`, closes the still-open closing issues of merged PRs in its daily run.

## Applies when / does not apply when

- Applies when: a PR the merger merged leaves one of its closing issues open, or someone proposes giving the merger `issues: write` so that it closes them.
- Does not apply when: an issue was reopened after its PR merged. The planner leaves those open.
- Does not apply when: the owner merged the PR. GitHub closes those issues itself.

## Context

#806 (under M2, #684) found six issues still open after the merger App merged the PRs that close them (#663, #746, #766, #767, #772, #680), while the owner's merges that day closed theirs. The likely cause: GitHub closes a PR's closing issues as the actor who merged it, and only if that actor may close issues. The merger's token holds `issues: read` (GOV-0028), so the merge succeeds and the close is dropped. The builder raised #812, since the security domain has no `decide` role and GOV-0028 asks to be revisited if the merger needs another right.

The owner answered on #812: "Option 2. Record: yes", and added `gov:ruled`. The builder built option 2 in #816 (merged, closes #806): `swarm daily` lists the open closing issues of PRs merged in the last 10 working days, and `roles/planner.md` has the planner close them before it posts the report.

## Options considered

1. **Grant the merger `issues: write`** and have `merger.py` close a merged PR's closing issues: fixes it at merge time, but the merger key could then edit, label and close any issue, including `ready` and `gov:ruled` labels.
2. **The planner closes them** in its daily run (chosen): the merger's rights stay unchanged; issues stay open until the next daily run.
3. **Do nothing**: the planner or owner closes them by hand, and GOV-0031's go and blocked-by checks keep seeing stale open issues.

## Deliberation

n/a. This is an authoritative decision by the owner, who chose option 2 in a comment on #812, against the question's recommendation of option 1.

## Consequences

- GOV-0028's five rights for the merger are unchanged. No change to the App or to `merger.yml`.
- An issue a merger merge closes can stay open for up to a day, until the planner's next daily run. Go and blocked-by checks (GOV-0031) may see it open in that time.
- The planner lists the issues it closes under "Under delegated authority" in its daily report.
- Revisit, for example with option 1, if the lag blocks work in practice or if the planner's sweep misses issues.
