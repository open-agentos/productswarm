---
id: GOV-0005
title: v1 is a lightweight local launcher for starting, assigning and stopping sessions
status: in-force
kind: ruling
question: "#41"
domain: product-scope
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
    - planning or building anything after v0
    - deciding whether launcher work is in scope
---

## Ruling

v1 is a lightweight launcher that runs on the owner's machine: a swarm manifest, `swarm up / ls / stop`, issue handoff, a spend cap, a "needs you" list, and the reviewer running by default (L1–L6 in #41). It calls `ops/swarm-session` unchanged and reuses the heartbeat and dashboard. The v0 non-goal "starting, stopping or steering sessions" no longer applies.

## Applies when / does not apply when

- Applies when: opening, ordering or building L1–L6.
- Does not apply when: anything listed as a v1 non-goal in #41: other repos, new roles, cloud or unattended runs, workflow changes, editing from the dashboard. Each of those needs its own `product-scope` question.
- It approves the scope only. The design questions #41 names (session runtime, manifest format, spend-cap defaults, whether the launcher may stop a session without the owner) are separate questions.

## Context

v0 (heartbeat and dashboard, #1–#6) is done. Asked to plan what comes next, the planner raised #41 instead of opening issues, because `PRODUCT.md` listed the launcher as a v0 non-goal. Its evidence: the bottleneck is now the owner starting and routing every session by hand, not visibility, and the reviewer has never run. The owner chose option 1 in a comment on #41.

## Options considered

1. **A lightweight local launcher** (chosen).
2. **A kit for any product repo**, with non-code roles: bigger reach, but it multiplies a manual start process.
3. **Unattended or cloud sessions**: most autonomous, but changes `ci-and-workflows`, `security` and `spend` at once.
4. **Do nothing**: keep starting sessions by hand.

## Deliberation

n/a. This is an authoritative decision by the owner, matching the planner's recommendation.

## Consequences

- The planner opens L1–L6 unlabelled for triage, plus the design questions up front, in the order L1 → L2 → L3, then L5 and L6, then L4.
- The launcher lives outside `ops/`, which agents may not edit.
- `PRODUCT.md` still lists the launcher as a v0 non-goal. It should gain a v1 section; that edit is the planner's or docs role's to propose.
- Options 2 and 3 are candidates for v2 and v3, each a later `product-scope` question.
