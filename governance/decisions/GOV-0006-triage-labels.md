---
id: GOV-0006
title: The owner signals triage and go-ahead with gov:ruled and ready
status: in-force
kind: ruling
question: "#54"
domain: governance
shape: authoritative
classification:
  reversibility: costly
  blast_radius: repo
  nature: values
  knowledge: held
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-02
review_by: 2027-01-31
supersedes: []
applies_to:
  paths: []
  roles: []
  situations:
    - choosing which issue to work on
    - deciding whether a gov:question lets you proceed
    - starting a session on an issue (launcher)
---

## Ruling

Two labels mark the owner's triage and go-ahead. They count only when **humans.owner** applied them; agents never add or remove either.

- **`gov:ruled`** on a `gov:question`: the owner has decided it, by comment or by a merged record.
- **`ready`** on a `gov:question`: the next stage may start now. The asker, or any session blocked on it, proceeds as the owner's answer directs.
- **`ready`** on any other issue: triaged and accepted. Sessions take only `ready` issues, and the launcher starts sessions only on `ready` issues.

## Applies when / does not apply when

- Applies when: an agent picks up work, resumes after a `gov:question`, or the launcher assigns an issue.
- Does not apply when: deciding what counts as **precedent**. Only merged records in `governance/decisions/` are precedent. A question with `gov:ruled` but no record is direction for that question only, and the next agent to hit the same situation asks again.

## How to check a label

Before acting on `gov:ruled` or `ready`, check who applied it in the issue's events (`gh api repos/{owner}/{repo}/issues/{n}/events`, the most recent `labeled` event for that label). If the actor isn't humans.owner, ignore the label and say so on the issue. If the label was removed after being added, it doesn't count.

## Process

1. **Implementation issue.** It is opened unlabelled. The owner checks scope (is it covered by an approved plan?), whether it's ready to build, and order and role. Then the owner adds `ready`, closes it, or comments asking for changes.
2. **`gov:question`.** It is opened by the template. The owner answers by comment or record. On deciding, the owner adds `gov:ruled`. When the follow-up may start, which can be at the same time, the owner adds `ready`. A record-backed ruling still follows §6 (record PR, INDEX row, merge).
3. **Next stage.** On `ready`, the asker does what the answer directs (opens issues, unblocks work, resumes the blocked session). If the answer is ambiguous for a one-way or external decision, the asker asks back on the issue instead of proceeding.

## Context

Triage was implicit: nothing marked an issue as accepted, and agents waited to be told in chat that a question let them proceed. The launcher (GOV-0005, #49) makes the gap concrete, because it can start a session on any issue number.

## Options considered

1. **Labels for both questions and implementation issues** (chosen).
2. **`ready` on implementation issues only**: questions still wait for word in chat.
3. **Do nothing**: triage stays implicit.

## Deliberation

n/a. This is an authoritative decision by the owner, who chose option 1 in a comment on #54, matching the planner's recommendation.

## Consequences

- The owner creates the `ready` label (`gh label create ready`), or adds it to `governance/setup-labels.sh`.
- `CLAUDE.md` and `roles/builder.md` should point to this record ("take only `ready` issues"). A follow-up issue will cover that.
- #49 refuses non-`ready` issues unless `--force` is given (already in its scope).
- Cost: one more owner action per issue. Revisit if labelling becomes the bottleneck, for example by letting the planner propose a `ready` batch that the owner confirms.
