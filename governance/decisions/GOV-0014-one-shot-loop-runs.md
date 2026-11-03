---
id: GOV-0014
title: Sessions that swarm watch starts run one-shot (claude -p) and exit when they are done
status: in-force
kind: ruling
question: "#125"
domain: architecture
shape: authoritative
classification:
  reversibility: costly
  blast_radius: repo
  nature: values
  knowledge: shared
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-03
review_by: 2027-01-31
supersedes: []
applies_to:
  paths:
    - launcher/**
  roles: []
  situations:
    - building or changing how `swarm watch` starts a session for a trigger
    - deciding when a loop-started session is done and frees its `max_live` slot
    - recording what a loop-started run cost
---

## Ruling

`swarm watch` starts each trigger as a headless `claude -p` run that exits when it is done, so its `max_live` slot frees without anyone stopping it. The run uses `--output-format json`, and the loop records the run's `session_id` and `total_cost_usd` against the trigger in `watch.json`. A Stop hook keeps the run going until its role's done-condition is met, and allows the stop when `stop_hook_active` is true or after N blocks. Sessions the owner starts with `swarm up` or `swarm launch` stay interactive.

| Role | Done when |
|---|---|
| builder | it opened a PR |
| reviewer | it posted a review |
| docs | it opened a record PR |

## Applies when / does not apply when

- Applies when: `swarm watch` starts a session for a trigger for real (not `--dry-run`).
- Does not apply when: the owner starts a session with `swarm up` or `swarm launch`. Those stay interactive.
- It does not change `ops/`. `ops/swarm-session` already passes extra arguments to `claude` unchanged (`exec claude "$@"`).
- It does not change GOV-0010's numbers (interval, `max_live`, capped roles only) or the owner's direction on #101 (a fresh session per trigger).

## Context

`swarm watch` started each trigger as an interactive session in a new Terminal window (owner's answer on #43). A loop-started session did its job, then sat at the prompt; `max_live` (GOV-0010) counted it as live until its process ended, and the owner had to `swarm stop` finished builders before #113's trigger could start. Separately, an idle owner-started `reviewer-1` kept every `[review]` trigger quiet, so #116 and #117 waited about 20 minutes for review. The planner raised #125 (Q1) at the owner's request, alongside #126 (Q2, hard budget) and #127 (Q3, overlapping builders). The owner answered "Option 3" in a comment on #125, then commented "Needs a record (GOV-0007)".

## Options considered

1. **Do nothing:** runs stay interactive and the owner clears finished sessions with `swarm stop`. The queue stalls until the owner acts.
2. **One-shot runs only:** loop-started runs are `claude -p` with the Stop hook and JSON cost recording; caps stay warn-only. Spend per run is unbounded and nobody watches the run.
3. **One-shot runs plus a hard budget** (chosen): as option 2, plus `--max-budget-usd` and `--max-turns`, decided in #126.
4. **All three:** as option 3, plus overlapping builders held (#127).
5. **Keep interactive sessions and add a Notification `idle_prompt` hook** that tells the loop a session is done. It can fire falsely while a session waits on the owner, and done-but-open sessions pile up beyond `max_live`.

## Deliberation

n/a. This is an authoritative decision by the owner, who chose option 3 in a comment on #125, matching the planner's recommendation.

## Consequences

- A loop-started run frees its slot by exiting. The loop still only starts runs and never stops one (GOV-0008, GOV-0009); the Stop hook runs inside the session and is not the loop re-prompting it.
- The hard-budget half of option 3 is GOV-0012 (#126), and the permission setting headless runs need is GOV-0013 (#131). This record covers only how loop-started sessions run.
- The owner can no longer watch a loop-started run in an interactive window. Each run gets a per-run cost record it didn't have before; that cost is a client-side estimate, stays local, and GOV-0002 and GOV-0003 still govern what reaches GitHub.
- On SIGTERM Claude Code still runs `SessionEnd` hooks, so `swarm stop` on a headless run still records `stopped`.
- Reverting changes how `launcher/` starts sessions and is one PR.
- Not decided here: the reasons a run may stop without meeting its done-condition (blocked on a `gov:question`, `ready` not added by the owner, work already done), which the question flagged for the Stop-hook issue's acceptance criteria; the value of N; and the fix for idle owner-started reviewers blocking reviews, which the question flagged as a separate `watch.py` change (#132).
