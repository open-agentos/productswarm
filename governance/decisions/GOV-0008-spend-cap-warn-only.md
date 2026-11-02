---
id: GOV-0008
title: In v1 the launcher only warns when a session passes its spend cap; it never stops one on its own
status: in-force
kind: ruling
question: "#46"
domain: security
shape: authoritative
classification:
  reversibility: one-way
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
    - building or changing the launcher's spend cap (L4, #52)
    - a launcher-started session's estimated spend passes its cap
    - deciding whether the launcher may stop a session without the owner
---

## Ruling

For v1, the spend cap is warn-only. When a session's estimated spend passes its cap, the launcher flags it "over cap" in `swarm ls` and in the "needs you" list (L5), and the owner decides whether to run `swarm stop`. The launcher never stops a session without the owner.

## Applies when / does not apply when

- Applies when: building L4 (#52), or anything in the launcher that reacts to a session passing its spend cap.
- Does not apply when: the owner runs `swarm stop <session>` themselves. That is the owner's own act and was never in question.
- It covers v1 only. Any automatic stop, with or without a grace period (options 2 and 3), needs a new `security` question.

## Context

GOV-0005 approves a spend cap (L4) and names "whether the launcher may stop a session without the owner" as a separate question. The planner raised it in #46. Today only the owner starts and stops sessions, so an automatic stop would be new authority over running sessions, and stopping one mid-task can lose its work in progress. The `security` domain is `always_one_way`, so the question was rated one-way and blocking. The owner answered "Option 1 for v1" in a comment on #46.

## Options considered

1. **Warn only** (chosen for v1): the session is flagged "over cap" in `swarm ls` and the "needs you" list; the owner decides whether to stop it.
2. **Automatic stop, launcher's own sessions only**: the launcher ends the session it started with a graceful signal, so the heartbeat records `stopped`, and the "needs you" list says why.
3. **Automatic stop with a grace period**: flag first, stop after N minutes unless the owner raises the cap.
4. **Do nothing**: drop L4.

## Deliberation

n/a. This is an authoritative decision by the owner, who chose option 1 for v1 in a comment on #46, matching the planner's recommendation.

## Consequences

- #52 builds L4 warn-only. Per #45, there is no default cap; a session has a cap only if the manifest sets one.
- Every stop stays an owner act, so an over-cap session keeps spending until the owner acts. The "needs you" list is what keeps the warning hard to miss.
- The planner's recommendation suggested moving to option 2 once warn-only has run for a while. That move is not approved here; revisit with a new question once there is evidence on whether caps fire on sessions that should keep going.
