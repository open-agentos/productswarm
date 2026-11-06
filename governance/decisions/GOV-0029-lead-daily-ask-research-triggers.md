---
id: GOV-0029
title: swarm watch starts the lead's daily report, owner Asks, Research briefs and call-ins on milestone issues
status: in-force
kind: ruling
question: "#577"
domain: product-scope
shape: authoritative
classification:
  reversibility: two-way
  blast_radius: repo
  nature: preference
  knowledge: held
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-06
review_by: 2027-01-31
supersedes: []
applies_to:
  paths: ["launcher/", "swarm.toml"]
  roles: []
  situations:
    - building or changing the watcher's `[daily]`, `[ask]` or `[research]` trigger, or its call-in trigger
    - the owner posts `Ask: <role>: <question>` on the report issue
    - the owner or the planner posts `Research: <question>`
    - a role wants another role called in on an issue that has a milestone but no `ready`
---

## Ruling

`swarm watch` gets four more triggers (option 2 of #577):

- **`[daily]`:** once each working day, at a time set in `swarm.toml`, it starts the planner to write the daily report on the pinned report issue. On Mondays the planner also writes the weekly check-in.
- **`[ask]`:** an `Ask: <role>: <question>` comment on the report issue starts that role once, and it answers there. Only the owner's comments count.
- **`[research]`:** a `Research: <question>` comment from the owner or the planner starts the analyst once. The brief goes in `research/`.
- **Call-ins:** GOV-0023's `Call in:` lines also count on an issue under an approved milestone, not only on `ready` issues.

Each trigger has its own `swarm.toml` switch. Every run it starts stays inside GOV-0010's limits, GOV-0012's budgets and GOV-0013's denies. The loop itself still never merges, labels or comments; the sessions it starts post as their own Apps.

## Applies when / does not apply when

- Applies when: anyone builds or changes these triggers, or a session is started by one of them.
- It amends GOV-0009: its trigger table gains `[daily]`, `[ask]` and `[research]`, none of which is an owner label or a PR head.
- It amends GOV-0023: a call-in counts on an issue under an approved milestone as well as on a `ready` one. GOV-0023's other bounds (who may call, once per role, no self-call, 2 calls per issue per day, the off switch) are unchanged.
- Does not apply when: the owner starts a role by hand, which stays allowed.
- Does not decide: the switches' names or defaults, the `[daily]` time, which day counts as a working day, how the watcher parses the lines, which issue is the report issue, or where `[daily]` runs when the owner's Mac is off (Q5 in #526, asked only if the local run misses days).
- Does not change GOV-0025: only the watcher's own `[watch]` issue is written as the owner.

## Context

The owner's direction on #526 (Q4 in its §3) gives the lead's rituals their own starts. GOV-0009 starts sessions only on owner labels and PR heads, and GOV-0023 adds `Call in:` lines on `ready` issues, so the daily report, the Monday check-in, `Ask:` and `Research:` need the owner to start them by hand. The planner raised #577. Per the owner, the report and an `Ask:` run by hand first, after #529 and `PLAN.md` (#574) merge, and building waits for that.

## Options considered

1. **Do nothing:** the owner starts each run by hand.
2. **All four triggers** (chosen): `[daily]`, `[ask]`, `[research]`, and call-ins on milestone issues.
3. **`[daily]` only:** `Ask:`, `Research:` and call-ins stay by hand.

## Deliberation

n/a. This is an authoritative decision by the owner, who answered "Confirmed. Option 2." on #577, matching the planner's recommendation, and asked for a record (`Record: yes`). The bounds above are those the question gives for option 2.

## Consequences

- M1's done test, a report the owner didn't start, becomes possible once `[daily]` is built (#588). `[ask]` (#590), `[research]` (#591) and milestone call-ins (#594) follow, in that order, since they share `launcher/watch.py`.
- More runs start without the owner. Spend stays bounded by GOV-0010's ceiling and GOV-0012's per-run budgets, and each trigger can be switched off; turning one on is the owner's `spend` call.
- Role prompts need to say what a run started by these triggers does (#595).
- Revisit if `[daily]` misses days (then ask Q5), if `Ask:` or `Research:` runs crowd out builds under GOV-0010's ceiling, or if milestone call-ins add noise rather than help.
