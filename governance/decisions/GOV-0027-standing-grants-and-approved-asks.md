---
id: GOV-0027
title: The merger merges milestone PRs under standing grants, and protected-path PRs the owner approved at head
status: in-force
kind: ruling
question: "#576"
domain: security
shape: authoritative
classification:
  reversibility: one-way
  blast_radius: repo
  nature: values
  knowledge: held
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-06
review_by: 2027-01-31
supersedes: []
applies_to:
  paths: [".github/", "launcher/", "swarm.toml", "CODEOWNERS", ".github/CODEOWNERS", "PLAN.md"]
  roles: []
  situations:
    - deciding whether, or how, a PR may merge without the owner pressing the merge button
    - building or changing the merger, its conditions, its shadow run or its `swarm.toml` switch
    - a PR on a protected path that the owner has approved
---

## Ruling

GOV-0022's merger stays: plain code in the Actions reconciler, using a `productswarm-merger` App that no Claude session holds. No Claude session merges. What unlocks a merge changes, by option 2 of #576:

- **Standing grant.** A PR that closes an issue under an approved milestone merges once all of these pass: the reviewer approved at its current head, `tests` passes, there's no `Overstep:` finding, it touches no protected path (GOV-0022's list), and it's under the size limit. No per-issue label is needed.
- **Approved ask.** A PR on a protected path merges once the owner has approved it at its current head. `GOVERNANCE.md`, `governance/jurisdictions.yml` and workflow files are excluded: the owner still merges those.
- **Shadow.** The merger first posts "would merge" for one day or 10 PRs, whichever comes first, while the owner still merges. Then it goes live.
- Every merge is listed in the daily report, and a `swarm.toml` switch turns it all off.

Any miss leaves the PR for the owner, as under GOV-0022.

## Applies when / does not apply when

- Applies when: any role proposes, builds or changes a way for a PR to merge without the owner's click.
- It amends GOV-0022: an approved milestone replaces the owner's per-issue `merge:agent` label, the shadow is one day or 10 PRs instead of a week, and protected-path PRs the owner approved at head may merge through the merger. GOV-0022's other conditions are unchanged.
- It amends GOV-0011 and CLAUDE.md's "Never merge a PR" for the merger App only. An approval still means only that the rubric passed at that head.
- It replaces decision 1 of #572 (skip the week in shadow). Decision 2 of #572 (native auto-merge) is not decided here.
- Does not apply when: the owner merges a PR by hand, which stays allowed. It doesn't let any Claude session merge.
- Does not decide: which issues are "under an approved milestone" (that is GOV-0026); the merger App's permissions; the size limit's value; whether agents may merge `GOVERNANCE.md`, `jurisdictions.yml` or workflows after owner approval (the "Later" row in #526).

## Context

#526's direction (its Q3) replaces per-PR owner merges with delegated authority. The owner had merged all 128 PRs, median 20 minutes after opening (#526 §7). GOV-0022 allowed merges without the owner's click only through a per-issue `merge:agent` label, after a week in shadow. The planner raised #576 at the owner's request; the owner answered "Confirmed. Option 2."

## Options considered

1. **Do nothing:** GOV-0022 as staged: per-issue `merge:agent`, a week in shadow, and the owner merges everything else.
2. **Grants and asks** (chosen): standing grants for milestone PRs off protected paths; approved asks for protected-path PRs the owner approved at head; a one-day or 10-PR shadow.
3. **Grants only:** standing grants as in option 2; the owner still merges every protected-path PR.

## Deliberation

n/a. This is an authoritative decision by the owner, who answered "Confirmed. Option 2." on #576.

## Consequences

- PRs under an approved milestone can land without the owner reading them first, bounded by the reviewer's approval at head, `tests`, the protected paths and the size limit. The owner's control moves to the milestone plan, the merger's code on `main`, owner approvals on protected paths, and the off switch.
- Nothing goes live before #572's owner steps: the ruleset's required `tests` check and stale-approval dismissal.
- CLAUDE.md, the role prompts and `PRODUCT.md` still say only the owner merges. This record doesn't edit them; that is follow-up work, by its own issue.
- Revisit if the shadow shows wrong "would merge" calls, if a merged PR has to be reverted, or before agents may merge `GOVERNANCE.md`, `jurisdictions.yml` or workflows.
