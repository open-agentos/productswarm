---
id: GOV-0023
title: A swarm App or the owner may call other roles into a ready issue with a `Call in:` line
status: in-force
kind: ruling
question: "#498"
domain: product-scope
shape: authoritative
classification:
  reversibility: two-way
  blast_radius: repo
  nature: values
  knowledge: shared
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-06
review_by: 2027-01-31
supersedes: []
applies_to:
  paths: ["launcher/", "swarm.toml"]
  roles: []
  situations:
    - an agent's work on a `ready` issue needs another role's contribution
    - a role is started because it was called in, and wonders whether it may comment
    - building or changing the watcher's call-in trigger, its limits or its `swarm.toml` switch
---

## Ruling

Any swarm App or the owner may bring other roles into a `ready` issue by posting `Call in: <role>, <role>: <why>` on it (option 3 of #498). The watcher starts each named role once per call, within these bounds:

- a call counts only if a swarm App or the owner posted it;
- each named role is started once per call, and a role can't call itself in;
- at most 2 calls count per issue per day;
- every call-in run stays inside GOV-0010's limits and GOV-0012's budgets, with GOV-0013's denies;
- a `swarm.toml` switch turns call-ins off.

A called-in role counts as asked in for GOVERNANCE.md §8, and posts one comment on the issue.

## Applies when / does not apply when

- Applies when: an agent or the owner wants another role's contribution on a `ready` issue, or anyone builds or changes the watcher's call-in trigger.
- Does not apply when: an issue isn't `ready`; the work needs a committee with rounds (GOVERNANCE.md §7), which a call-in doesn't replace; or the owner launches a role by hand, which stays allowed.
- It doesn't let any role join an issue unasked (option 4), and doesn't amend §8: a called-in role is asked in by the call.
- Does not decide: the switch's name or default, how the watcher parses the line, or what counts as a "day". #498 doesn't set them.

## Context

The watcher starts one fixed role per trigger: the builder on `ready`, docs on a ruling, the asker (or the planner, #455 and #495) on `[answer]`. No agent can bring in another role, so the designer and analyst contribute only when the owner launches them by hand, and §8 keeps agents off `gov:` issues they weren't asked into. #464's answer asks for agents that work in a "collaborative, self-directed, collectively regulated" way. The owner raised #498 directly, following #464's answer and #491 (every swarm App is a trusted author), and answered "Confirmed, go with Option 3".

## Options considered

1. **Do nothing:** the owner launches extra roles by hand.
2. **Owner call-in only:** a `Call in:` line from the owner on a `ready` issue starts each named role once.
3. **Agents call in agents** (chosen): a swarm App or the owner posts `Call in:`; the watcher starts each named role once per call, and the called-in role counts as asked in and posts one comment.
4. **Open floor:** any role may join any issue unasked, which needs §8 amended.

## Deliberation

n/a. This is an authoritative decision by the owner, who answered "Confirmed, go with Option 3" on #498. The bounds are those of the question's recommendation, which was option 3.

## Consequences

- Agents can pull the designer, analyst or another role into a `ready` issue without the owner, so there are more runs. Spend stays bounded by GOV-0010's ceiling of 2 live runs and capped roles only, and by GOV-0012's per-run budgets.
- A call-in is lighter than a committee (#492): one comment per called-in role, no rounds.
- The watcher needs a new trigger and a `swarm.toml` switch; that is follow-up work, by its own issue.
- Revisit if call-ins crowd out builds under GOV-0010's ceiling, if called-in comments add noise rather than help, or if the per-issue limit is hit often.
