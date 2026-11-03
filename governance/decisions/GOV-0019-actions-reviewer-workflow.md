---
id: GOV-0019
title: The Actions reviewer workflow runs per PR on push events, never on its own output, and a swarm.toml switch hands it the [review] trigger
status: in-force
kind: ruling
question: "#209"
domain: ci-and-workflows
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
  paths: [".github/workflows/reviewer.yml", "launcher/", "swarm.toml"]
  roles: [reviewer, builder, planner]
  situations:
    - designing or changing the events, concurrency or skip rule of the GitHub Actions reviewer workflow (v3 C stage 1)
    - deciding whether `swarm watch` handles `[review]` while the Actions reviewer is on
    - proposing or committing `.github/workflows/reviewer.yml`
---

## Ruling

The Actions reviewer is one workflow, `.github/workflows/reviewer.yml`:

- **Events:** `pull_request` (`opened`, `synchronize`, `reopened`, `ready_for_review`), plus `workflow_dispatch` with a PR number for re-runs.
- **Concurrency:** group `reviewer-pr-<number>` with `cancel-in-progress: true`, so a new push replaces a review of a stale head. There is no cross-PR ceiling; each run is bounded by GOV-0012's budget and turns.
- **No self-triggering:** the workflow does not listen to `pull_request_review` or `issue_comment`, the events the reviewer's own output fires. A run skips if the reviewer has already reviewed the PR's current head (the same rule as the `[review]` trigger).
- **Coexistence:** a `swarm.toml` switch (for example `[watch] review_in_actions = true`) makes `swarm watch` leave `[review]` to Actions. Turning it off, or disabling the workflow, puts the local loop back in charge. `[respond]`, `[build]`, `[answer]` and `[record]` stay local.
- **Who writes it:** the builder proposes the YAML on its issue; the owner commits `.github/workflows/reviewer.yml`, since the Apps have no `workflows` permission (as on #32).

## Applies when / does not apply when

- Applies when: building, proposing or changing the Actions reviewer workflow's triggers, concurrency or skip rule, or the `swarm watch` switch that defers `[review]` to it (C stage 1, GOV-0015).
- Does not apply when: deciding which authors and events are trusted (prompt injection), which secrets the job gets, or what the job log shows. GOV-0017 covers trusted authors and events, GOV-0018 the secrets, and GOV-0016 the log.
- Does not apply when: builder or docs runs move to Actions, or `[respond]` and `[record]` run there (C stage 2). That needs its own question.
- It does not change `swarm watch` for any trigger but `[review]`, GOV-0010's limits on loop-started runs, or `ops/`.

## Context

GOV-0015 makes C stage 1 the reviewer running in GitHub Actions on events, and names trigger design as one of its sub-questions. The owner's direction on #167 was that the reviewer runs on events, not polling, and that `swarm watch` stays as the fallback.

The planner raised #209 to settle the workflow's mechanics: which events it listens to, what concurrency replaces `max_live` for these runs, how a run is kept from re-triggering itself, how it coexists with the local loop's `[review]` trigger, and who writes the file. It assumed the trusted-authors question's answer and left stage 2 aside.

The planner recommended option 1: per-PR concurrency fits "one reviewer pass per push", and the explicit switch avoids double runs while leaving the fallback one line away, which keeps the local launcher working as the owner asked on #167.

The owner answered on #209: "Option 1".

## Options considered

1. **One workflow, per-PR concurrency, local loop defers**: events, concurrency, skip rule, `swarm.toml` switch and authorship as in the ruling (chosen).
2. **As 1, but a global ceiling**: one concurrency group `reviewer` across the repo, queued; fewer parallel runs, slower when several PRs land at once.
3. **As 1, but the local loop keeps `[review]` too**: no switch; whichever reviewer reaches a head first wins. Simpler, but both can start on the same head before a review is posted, doubling spend.
4. **Do nothing**: no Actions reviewer runs.

## Deliberation

n/a. This is an authoritative decision by the owner, matching the planner's recommendation.

## Consequences

- The builder may build the `swarm watch` switch and propose `reviewer.yml` on its issue to this ruling; the owner commits the workflow.
- GOV-0009 holds: `swarm watch` stays local and start-only, and only stops starting `[review]` runs while the switch is on. GOV-0010's interval and `max_live` keep covering loop-started runs; Actions reviewer runs are limited by their concurrency group instead.
- GOV-0011's one pass per head holds through the skip rule and `cancel-in-progress`.
- The team accepts that several PRs pushed at once start several reviewer runs in parallel, each within GOV-0012's budget.
- Revisit if parallel runs cost more than expected, if the switch and the workflow drift out of step and double runs appear, or for C stage 2.
