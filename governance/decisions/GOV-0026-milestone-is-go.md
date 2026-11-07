---
id: GOV-0026
title: An approved milestone in PLAN.md is the go for its issues, with the owner's veto
status: superseded
kind: ruling
question: "#575"
domain: governance
shape: authoritative
classification:
  reversibility: costly
  blast_radius: repo
  nature: values
  knowledge: held
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-06
review_by: 2027-01-31
supersedes: []
applies_to:
  paths: ["PLAN.md", "launcher/"]
  roles: []
  situations:
    - choosing which issue to work on
    - deciding whether an issue without `ready` is go because of its milestone
    - opening or ordering a milestone's issues (lead)
    - starting a `[build]` session on an issue (`swarm watch`, launcher)
---

## Ruling

An approved milestone in `PLAN.md` is the go for its issues (option 2 of #575). The owner's merge of `PLAN.md` is the approval; the owner no longer labels each of its issues `ready`, and can veto any of them.

An implementation issue is go when all of these hold:

- a swarm App or the owner opened it, and its body has `**Milestone:** M<n>`;
- `M<n>` is in `PLAN.md` on `main` and not marked done;
- its `**Waits on:**` issues are closed (#490);
- the owner hasn't vetoed it: a `hold` label, a close, or a comment.

The lead opens and orders those issues, and `swarm watch` builds them as it builds `ready` ones today. An owner-applied `ready` stays a go too.

`gov:question`s keep `ready` and `gov:ruled` exactly as GOV-0006 sets out. Agents still never add or remove `ready` or `gov:ruled`.

## Applies when / does not apply when

- Applies when: a session picks up an implementation issue, the lead opens or orders a milestone's issues, or `swarm watch` or the launcher decides whether an issue may be built.
- It amends GOV-0006: for implementation issues, a milestone that passes the conditions above is a go alongside owner-applied `ready`. GOV-0006's part on `gov:question`s, and its rule on checking who applied a label, are unchanged.
- It amends GOV-0009: a go milestone issue is a source for `[build]` as well as `ready`.
- Does not apply when: the issue is a `gov:question`, or it has no `**Milestone:**` line, or its milestone isn't in `PLAN.md` on `main` or is marked done. Those still need the owner's `ready`.
- Does not decide: merging (Q3 in #526; GOV-0011 and GOV-0022 still hold), triggers for reports, asks or call-ins (Q4), or `PLAN.md`'s format (#574).

## Context

GOV-0006 makes the owner label every issue `ready`: 125 labels in 6 days (#526 §7), the per-issue dispatching the department goal removes. The owner's direction on #526 (Q2 in its §3) makes an approved milestone the go for its issues. `PLAN.md` (#574) will hold milestones the owner approves by merging. The planner raised #575 to ask whether that approval replaces per-issue `ready`.

## Options considered

1. **Do nothing:** the owner labels each issue `ready`; the lead asks for a milestone's issues in one batch.
2. **Milestone is go** (chosen): the owner's merge of `PLAN.md` is the go, with veto by `hold` or close.
3. **One `ready` per batch:** the lead lists a milestone's next issues on one tracking issue; one owner `ready` on it is go for each listed.

## Deliberation

n/a. This is an authoritative decision by the owner, who answered "Confirmed. Go with Option 2." on #575, matching the planner's recommendation. The conditions above are those the question gives for option 2.

## Consequences

- Building on this needs `PLAN.md` on `main` (#574) and the watcher reading it; until both exist, the owner's `ready` remains the only go in practice.
- The owner's control over implementation issues moves from each issue to the plan: the merge of `PLAN.md`, and the veto.
- CLAUDE.md's working rule ("Work only on issues labelled `ready`") and the role prompts that repeat it are out of date once this merges. This record doesn't edit them; CLAUDE.md is the owner's edit, and the role prompts are follow-up work by their own issue.
- The team accepts that the swarm may build an issue the owner hasn't read, bounded by the milestone, the issue's author and the veto.
- Revisit if the owner vetoes many milestone issues, or if an issue is built that the owner would not have labelled `ready`.
