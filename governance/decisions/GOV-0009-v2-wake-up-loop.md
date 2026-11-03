---
id: GOV-0009
title: v2 is a local, start-only wake-up loop that starts the right session on owner labels and new PR pushes
status: in-force
kind: ruling
question: "#87"
domain: product-scope
shape: authoritative
classification:
  reversibility: costly
  blast_radius: external
  nature: values
  knowledge: held
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-03
review_by: 2027-01-31
supersedes: []
applies_to:
  paths: []
  roles: []
  situations:
    - planning or building anything after v1
    - deciding whether a launcher feature that starts sessions with nobody watching is in scope
---

## Ruling

v2 is a wake-up loop: `launcher/swarm watch`, which runs locally in the foreground and stops with Ctrl-C. Every few minutes it reads the same GitHub and heartbeat state as `swarm inbox` and starts the right session for each trigger below. It reuses `needs_you()`, `swarm launch` and the existing refusal checks, and it has `--dry-run`.

| Trigger | Session it starts |
|---|---|
| An open, non-draft PR whose head the reviewer hasn't reviewed | a reviewer pass |
| An issue whose latest `ready` the owner added (GOV-0006), with no live session on it | `swarm launch builder --issue N` (or the issue's role) |
| A `gov:question` the owner labelled `gov:ruled` that needs a record and has no ruling PR | docs, on that question (GOV-0007) |
| A `gov:question` the owner labelled `ready` | the role that asked it, on that question |

The loop **only starts sessions**. It never stops one (GOV-0008), never adds or removes labels, and never merges, approves or comments. It never acts on the same trigger twice. This ruling resolves the "unattended runs" non-goal of GOV-0005 for this loop only.

## Applies when / does not apply when

- Applies when: opening, ordering or building `swarm watch` as described above.
- Does not apply when: any trigger or action not in the table above, or a GitHub Actions or cloud trigger. Those were not offered in #87 and are still non-goals; each needs its own `product-scope` question.
- It approves the scope only. The three design questions #87 names are separate questions, to be asked before they are built:
  1. how a nudge reaches a session (starting a fresh session each time, or re-prompting an idle one);
  2. the interval and a ceiling on how many sessions run at once (a `spend` question);
  3. whether the reviewer's "don't poll on a timer" rule changes, or the loop takes over the polling (the sketch takes the second).

## Context

v1 (#47–#52) merged, but each owner signal still needs the owner to prod a session by hand: a new PR or push needs a reviewer pass, `ready` on an issue needs `swarm launch`, `gov:ruled` needs docs (GOV-0007), and `ready` on a `gov:question` needs the role that asked it. That is the bottleneck v1 set out to remove. At the owner's request, the planner raised #87, because GOV-0005 lists "cloud or unattended runs" as needing their own `product-scope` question, and a loop that starts sessions while nobody is watching is unattended. The owner answered "Option 1" in a comment on #87.

## Options considered

1. **Approve the wake-up loop as v2**, as sketched: local, foreground, start-only, triggered only by owner-applied labels and new PR pushes (chosen).
2. **A suggest-only loop**: `swarm watch` works out the same triggers but only prints the `swarm launch …` command, and the owner runs it. Safer on spend, but the owner still starts every session.
3. **Do nothing**: `swarm inbox` stays the only aid.

## Deliberation

n/a. This is an authoritative decision by the owner, matching the planner's recommendation.

## Consequences

- The planner may now open v2 issues, unlabelled for triage, and the three design questions above.
- The real risk is spend while nobody is watching. The planner recommended settling design question 2 before the loop starts anything for real, and making `--dry-run` the first deliverable. This ruling records that recommendation but does not make it a condition. Question 2 is a `spend` question and goes to the owner.
- The loop acts only on signals the owner gives on purpose (`ready`, `gov:ruled`, checked for who added them per GOV-0006) and on new PR heads the reviewer is meant to review anyway, so it makes no decisions of its own.
- `PRODUCT.md` lists "cloud or unattended runs" as a v1 non-goal. It should gain a v2 section; that edit is the planner's or docs role's to propose.
