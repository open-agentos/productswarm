---
id: GOV-0041
title: The planner closes the issues a merger-merged PR left open; the merger keeps `issues: read`
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
date: 2026-11-11
review_by: 2027-02-28
supersedes: []
applies_to:
  paths: []
  roles: [planner, builder]
  situations:
    - a merged PR's closing issues are still open after the merger App merged it
    - building or changing the planner's daily run to close those issues
    - proposing that the merger App, or any other identity, close the issues its merges name
---

## Ruling

The `productswarm-planner` App closes the issues a merged PR names as closing and left open, during its daily run, with the `issues: write` it already holds. The `productswarm-merger` App's rights stay as GOV-0028 sets them: it gets no `issues: write`.

## Applies when / does not apply when

- Applies when: a PR merged by the merger App (or anyone whose merge didn't close its issues) names closing issues that are still open.
- Applies when: building or changing the planner's daily run so it finds and closes those issues.
- Does not apply when: the issue was reopened after the merge. Closing it again is not settled here.
- Does not apply when: closing any other issue. This ruling gives the planner no new reason to close issues beyond a merged PR's own closing issues.
- Does not apply when: changing the merger App's permissions. GOV-0028 still governs them, and a need for another right is a new `security` question.

## Context

#806 (under M2, #684) found six issues still open after the merger App merged the PRs that close them (#663, #746, #766, #767, #772, #680), while the two PRs the owner merged that day closed theirs. GitHub closes a PR's closing issues as the actor who merged it, and only if that actor may close them. The merger's token holds `issues: read` (GOV-0028), so the merge goes through and the close is silently dropped. Until then the planner or the owner closed these issues by hand.

The builder raised #812, recommending option 1 with option 2 as the fallback if the owner wanted GOV-0028's five rights unchanged. The owner answered on #812: "Option 2. Record: yes". The question is one-way, in the `security` domain, which has no `decide` role.

## Options considered

1. **Grant the merger `issues: write`**: the owner adds it to the App and to `merger.yml`'s token, amending GOV-0028, and `merger.py` closes each merged PR's closing issues. Fixes it at merge time, but the merger key could then edit, label and close any issue, including `ready` and `gov:ruled` labels.
2. **Another App closes them** (chosen): the planner, which already holds `issues: write`, sweeps merged PRs in its daily run and closes their still-open closing issues. The merger's rights stay unchanged; issues stay open until the next sweep, and the planner gains a step.
3. **Do nothing**: the planner or the owner keeps closing them by hand, each one an owner or lead act, and go and blocked-by checks (GOV-0031) keep seeing stale open issues.

## Deliberation

n/a. This is an authoritative decision by the owner, who chose option 2 in a comment on #812, against the question's recommendation of option 1.

## Consequences

- #816 built it (closes #806): `swarm daily` lists each still-open closing issue of a PR merged in the last 10 working days, leaving out issues reopened since, and `roles/planner.md` has the daily run close them before it posts the report and list them under "Under delegated authority".
- The merger key stays narrow: it cannot edit, label or close issues, so it cannot touch `ready` or `gov:ruled` (GOV-0006).
- An issue the merger's merge should have closed stays open until the planner's next daily run, up to a working day. Go and blocked-by checks (GOV-0031) may see it as open in that window, so work blocked by it may start up to a day late.
- Each close is the planner's act under delegated authority and shows in the daily report.
- A missed daily run, a lag that holds up real work, or the planner closing an issue it shouldn't is the signal to ask again, for example about option 1.
