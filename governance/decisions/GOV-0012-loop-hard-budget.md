---
id: GOV-0012
title: Runs that swarm watch starts end at their spend cap; owner-started sessions stay warn-only
status: in-force
kind: ruling
question: "#126"
domain: security
shape: authoritative
classification:
  reversibility: one-way
  blast_radius: repo
  nature: values
  knowledge: held
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-03
review_by: 2027-01-31
supersedes: []
applies_to:
  paths:
    - launcher/**
    - swarm.toml
  roles: []
  situations:
    - building or changing how `swarm watch` starts a headless run
    - a loop-started run reaches its `spend_cap_usd` or its turn ceiling
    - deciding whether a session may be ended automatically at its cap
---

## Ruling

For runs that `swarm watch` starts, the role's `spend_cap_usd` in `swarm.toml` becomes `--max-budget-usd`, and `--max-turns` sets a turn ceiling. When a run reaches either limit, Claude Code ends it. Caps stay warn-only for every session the owner starts (`swarm up`, `swarm launch`), as GOV-0008 says.

## Applies when / does not apply when

- Applies when: `swarm watch` starts a run for real (not `--dry-run`). This only matters for headless (`claude -p`) runs, because `--max-budget-usd` and `--max-turns` are headless-mode flags (#125).
- Does not apply when: the owner starts a session by hand. GOV-0008 still holds for those: the cap only warns, and the launcher never stops them.
- It sets no daily total for loop-started runs (option 3 on #126). Adding one is a separate `spend` change.

## Context

GOV-0008 made the spend cap warn-only and said any automatic stop "needs a new `security` question". GOV-0009 made v2 a loop that starts sessions while nobody is watching, and #125 (Q1) asked whether those runs should be headless; a headless run gives the owner no window to watch it, so a warn-only cap is the weakest spend position. The planner raised #126 (Q2) at the owner's request, limited to runs the loop starts. Today's caps are planner 5, builder 15, reviewer 5 and docs 5 (#110), and GOV-0010 requires a `spend_cap_usd` for every role the loop starts, so every loop-started run has a budget. The `security` domain is `always_one_way`, so the question was rated one-way and blocking. The owner answered "Option 2" in a comment on #126.

## Options considered

1. **Do nothing:** caps stay warn-only for every session (GOV-0008 as is). A loop-started run can go past its cap with nobody watching.
2. **Hard per-run budget for loop-started runs only** (chosen): `spend_cap_usd` becomes `--max-budget-usd`, plus a `--max-turns` ceiling. Owner-started sessions stay warn-only.
3. **Option 2 plus a daily total for the loop in `[watch]`:** when the day's recorded loop spend reaches the total, the loop holds every further trigger until the next day.
4. **Hard stop for all sessions,** including owner-started ones. Listed to show the boundary; not recommended.

## Deliberation

n/a. This is an authoritative decision by the owner, who chose option 2 in a comment on #126, matching the planner's recommendation.

## Consequences

- GOV-0008 is amended for loop-started runs only; it stays in force for every session the owner starts.
- The loop itself still never stops a session (GOV-0009): Claude Code ends its own run at the budget it was started with.
- When a run ends mid-task, the work in its worktree is kept (`tidy()` removes only worktrees that are clean and have no unpushed commits), the trigger is marked done in `watch.json` so the loop doesn't start it again by itself, and the "needs you" list shows "ended at cap" for that trigger so the owner decides whether to restart it.
- This ruling does not set the turn ceiling's value.
- The planner's recommendation suggested adding the daily total (option 3) later, as a separate `spend` change, once a week of per-run cost records exists. That is not approved here.
