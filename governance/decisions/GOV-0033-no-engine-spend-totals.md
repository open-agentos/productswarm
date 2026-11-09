---
id: GOV-0033
title: The hosted engine gets no daily, per-mission or monthly spend total for now; per-run caps and the Console limit stand
status: in-force
kind: ruling
question: "#656"
domain: spend
shape: authoritative
classification:
  reversibility: two-way
  blast_radius: external
  nature: values
  knowledge: held
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-09
review_by: 2027-01-31
supersedes: []
applies_to:
  paths: []
  roles: []
  situations:
    - building or changing how the hosted engine (#651) limits what its runs spend
    - proposing a daily, per-mission or monthly spend total for engine runs
    - deciding whether the engine may dispatch before such a total exists
---

## Ruling

Do not add a daily, per-mission or monthly spend total to the hosted engine for now. Its runs are limited only by each role's per-run cap (GOV-0012) and the concurrency ceiling (GOV-0010), and the dedicated Console workspace's $1,000 monthly limit is the only total.

## Applies when / does not apply when

- Applies when: building or changing the hosted engine's spend limits, or deciding whether it may dispatch without an engine-side total.
- Does not apply when: setting per-run caps or the concurrency ceiling (GOV-0012 and GOV-0010 still govern those), or sessions the owner starts by hand (GOV-0008).
- Adding any engine total later is a new `spend` question; this ruling does not approve one.

## Context

v2 moves the engine to the owner's VPS (#651). Its runs are billed per token to a dedicated Console workspace with a $1,000 monthly limit (owner's decision, 2026-11-07). Today's limits are per run only, and GOV-0012 left a daily total to a separate `spend` change. The owner raised #656 to settle it before the hosted engine dispatches; the Console limit is a backstop, but a swarm that hits it stalls mid-task instead of stopping cleanly. On 2026-11-06, 64 runs cost about $53 (Claude Code's estimate). The question was rated external and blocking, so it needs a record. The owner answered "Option 1 for now" in a comment on #656.

## Options considered

1. **Do nothing** (chosen): keep the per-run caps, and let the Console limit be the only total.
2. **Three engine totals:** about $45 per working day; each Mission's Budget field (default $150), past which the mission's runs are held; and a stop to all dispatch at $900 recorded in the month (90% of the Console limit). Holds show in the needs-you list and the daily report.
3. **Option 2 without the daily total:** totals per mission and per month only.

## Deliberation

n/a. This is an authoritative decision by the owner, who chose option 1 "for now" in a comment on #656, against the question's recommendation of option 2.

## Consequences

- #656 no longer blocks the hosted engine: it may dispatch with no engine-side total.
- GOV-0008, GOV-0010 and GOV-0012 are unchanged.
- The team accepts that a run of bad days can spend the month's budget early, and that reaching the Console limit stops runs mid-task rather than cleanly. Work left in a run's worktree is kept as GOV-0012 describes for runs ended at their cap.
- The owner chose this "for now". Spend near the Console limit, or a stall when it is hit, is the signal to ask again with a new `spend` question.
