---
id: GOV-0001
title: Adopt GOVERNANCE.md as the decision process for agents and humans in this repo
status: in-force
kind: ruling
question: n/a
domain: governance
shape: authoritative
classification:
  reversibility: two-way
  blast_radius: repo
  nature: values
  knowledge: held
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-01
review_by: 2027-01-31
supersedes: []
applies_to:
  paths: []
  roles: []
  situations:
    - any decision not plainly inside an agent's assigned task
---

## Ruling

All agents and humans working in this repository make decisions according to `GOVERNANCE.md`. Agents check precedent and jurisdiction before acting, and ask through a `gov:question` issue when the decision is not theirs to make.

## Applies when / does not apply when

- Applies when: any agent or human faces a choice outside the plain scope of their task.
- Does not apply when: the choice is a one-off with no pattern-setting effect and sits inside the task.

## Context

Agent fleets need decision authority that is explicit, inspectable and steerable by humans. productswarm is the Phase 0 test bed for open-agentos/agent-governance: the convention is followed by hand to learn which questions agents actually raise before any automation is built.

## Options considered

1. **Adopt the convention by hand (Phase 0)**: cheap, reversible, generates real data about agent questions.
2. **Build the classifier and automation first**: risks encoding an imagined taxonomy.
3. **Do nothing**: agents keep deciding implicitly or blocking on humans ad hoc.

## Deliberation

n/a. This is a founding authoritative decision by the repository owner.

## Consequences

Agents will open more issues and some work will wait on rulings. That cost buys a record of which decisions recur, which feeds Phase 1. Revisit at `review_by` using the Phase 0 exit criteria in `governance/PHASE0.md`.
