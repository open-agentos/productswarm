---
id: GOV-0010
title: swarm watch starts at most 2 sessions at once, checks every 5 minutes, and starts only roles with a spend cap
status: in-force
kind: ruling
question: "#88"
domain: spend
shape: authoritative
classification:
  reversibility: costly
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
    - building or changing how `swarm watch` starts sessions (W2, #90)
    - changing the loop's interval, concurrency ceiling or cap rule in `swarm.toml`
    - the loop has a trigger for a role that has no `spend_cap_usd`
---

## Ruling

Limit the sessions `swarm watch` starts with three settings in `swarm.toml`:

- **Interval:** 5 minutes between reads of GitHub and heartbeat state.
- **Concurrency ceiling:** at most 2 live loop-started sessions at once. At the ceiling, the loop holds further triggers, lists them in `swarm inbox`, and starts them once a slot frees up.
- **Cap requirement:** the loop starts only roles that have a `spend_cap_usd` in `swarm.toml`, and says why it skipped any other.

Sessions the owner starts by hand (`swarm up`, `swarm launch`) don't count towards the ceiling and aren't affected. Changing any of these numbers in `swarm.toml` is itself a `spend` change.

## Applies when / does not apply when

- Applies when: `swarm watch` starts a session for real (not `--dry-run`), or someone changes the loop's limits.
- Does not apply when: the owner starts a session by hand, or deciding whether to stop a session. GOV-0008 still holds: the cap only warns, and the loop never stops a session.

## Context

GOV-0009 (#87) made v2 a wake-up loop that starts sessions while nobody is watching, and named the interval and concurrency ceiling as a separate `spend` question to settle first. Nothing limited that spend: the per-session cap is optional (#45) and warn-only (GOV-0008), `swarm.toml` set no cap on any role, and nothing limited how many sessions start or how often. A burst of PR pushes or a batch of `ready` labels would have started one session per trigger. The planner raised #88. The owner answered "Option 1" in a comment, and later asked for this record.

## Options considered

1. **Small fixed limits, set in `swarm.toml`** (chosen): interval 5 minutes, at most 2 live loop-started sessions, and only roles with a `spend_cap_usd`.
2. **Ceiling only:** the same interval and ceiling, no cap required. Simpler, but an uncapped session can run unflagged.
3. **One at a time:** at most 1 live loop-started session, cap required. Cheapest, but a review then waits behind a builder session.
4. **No limits:** start on every trigger and rely on the warn-only cap. Nothing bounds the spend.

## Deliberation

n/a. This is an authoritative decision by the owner, matching the planner's recommendation.

## Consequences

- #90 (W2) builds the real starts within these limits, and `launcher/README.md` cites this record.
- Two live sessions lets one reviewer pass and one builder or docs session run side by side, which covers the common case (a PR lands while an issue is being built).
- Requiring a cap means every loop-started session can show "over cap" in `swarm inbox`, the only spend signal v1 has (GOV-0008). Until `swarm.toml` sets a `spend_cap_usd` for a role, the loop starts no sessions for that role.
- Keeping the numbers in `swarm.toml` means they change only through a reviewed file, not an ad hoc flag.
- Revisit if held triggers often wait long enough to slow the owner down, or if spend from loop-started sessions is higher than expected.
