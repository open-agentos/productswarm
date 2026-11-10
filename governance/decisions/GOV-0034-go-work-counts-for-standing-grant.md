---
id: GOV-0034
title: Any issue that is go under GOV-0031 counts as approved for GOV-0027's standing grant
status: in-force
kind: ruling
question: "#696"
domain: security
shape: authoritative
classification:
  reversibility: one-way
  blast_radius: repo
  nature: values
  knowledge: held
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-09
review_by: 2027-01-31
supersedes: []
applies_to:
  paths: ["launcher/merger.py", "launcher/test_merger.py", "launcher/README.md", ".github/"]
  roles: []
  situations:
    - deciding whether a PR's issue counts as "under an approved milestone" for GOV-0027's standing grant
    - building or changing the merger's standing-grant check or its shadow run
---

## Ruling

For GOV-0027's standing grant, an issue counts as approved when it is go under GOV-0031, by either route:

- it is go under GOV-0031's Goal or Area rule: a swarm App or the owner opened it, it sits under an open Goal or Area the owner opened, it's a Task, Bug, Feature or untyped issue, none of its blocked-by issues is open, and the owner hasn't vetoed it (`hold`, close or comment); or
- the owner added its most recent `ready` label.

The standing grant's other conditions are unchanged: the reviewer approved at the PR's current head, `tests` passes, there's no `Overstep:` finding, it touches no protected path, and it's under the size limit.

Before the merger merges anything under this reading, it runs its own shadow: it posts "would merge (standing grant)" on 10 PRs or for one day, whichever comes first, as GOV-0027 set for the first shadow. Then it goes live.

## Applies when / does not apply when

- Applies when: the merger, or anyone changing it, decides whether a PR's issue counts as approved for the standing grant.
- Amends GOV-0027: "under an approved milestone" now means "go under GOV-0031", replacing GOV-0027's pointer to GOV-0026 (superseded by GOV-0031).
- Does not change: GOV-0027's approved asks, its excluded paths (`GOVERNANCE.md`, `governance/jurisdictions.yml`, workflows), GOV-0028's App permissions, or which issues are go (GOV-0031).
- Does not let any Claude session merge, and an approval still means only that the rubric passed (GOV-0011).

## Context

GOV-0027 merges a PR without the owner's click only if it closes an issue "under an approved milestone", and left which issues those are to GOV-0026. GOV-0031 superseded GOV-0026: from 2026-11-16 13:54 UTC the `**Milestone:**` lines stop counting, and the go is an open Goal or Area the owner opened (#682, #691) or the owner's `ready`. After that date no PR could qualify for the standing grant.

It already missed most builder work: the merger's shadow verdicts left builder PRs on `ready` issues for the owner ("not under an approved milestone"), because GOV-0027 didn't count `ready`. No PR had a standing-grant "would merge", and the owner merged all 100 PRs merged in the week before #696. The owner raised #696 and answered "Option 3".

## Options considered

1. **Do nothing:** only milestone issues count, so the standing grant stops applying once GOV-0031's week ends.
2. **Goal or Area go counts:** an issue that is go under GOV-0031's Goal or Area rule counts as approved; the owner's `ready` alone does not.
3. **Any GOV-0031 go counts** (chosen): option 2, and an issue whose most recent `ready` the owner added counts too.

In options 2 and 3, the other standing-grant conditions stay and the new reading gets its own shadow first.

## Deliberation

n/a. This is an authoritative decision by the owner, who answered "Option 3" on #696.

## Consequences

- One owner act (opening a Goal or Area, or adding `ready`) both approves the work and, with the reviewer's approval at head and the other conditions, lets its PR merge. The owner no longer clicks merge on builder PRs that pass.
- Builder work follows by its own issue: the merger's standing-grant check (`launcher/merger.py` and its tests) reads GOV-0031's go instead of `PLAN.md` milestones, and the new shadow runs before it goes live.
- Until that change ships and its shadow passes, the merger stays in shadow and the owner merges builder PRs by hand.
- Revisit if the new shadow shows wrong "would merge (standing grant)" calls, or if a PR merged under this reading has to be reverted.
