---
id: GOV-0038
title: The planner App writes the org Project's Spent field from `swarm spent` in its daily run
status: in-force
kind: ruling
question: "#731"
domain: security
shape: authoritative
classification:
  reversibility: one-way
  blast_radius: org
  nature: values
  knowledge: held
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-11
review_by: 2027-02-28
supersedes: []
applies_to:
  paths: []
  roles: [planner]
  situations:
    - writing the Spent field on the org Project's Mission, Goal or Area items
    - building or changing the planner's daily run so it sets Spent from `swarm spent`
    - proposing another identity, App or key to write the org Project's Spent field
---

## Ruling

The `productswarm-planner` App writes the org Project's Spent field, using the org Projects (read and write) permission it already holds. The planner sets Spent from `swarm spent` in its daily run. No new App and no new key go on the host for this.

## Applies when / does not apply when

- Applies when: setting Spent on the org Project's Mission, Goal and Area items, or building that step into the planner's daily run.
- Does not apply when: the engine or watcher writes anything to the Project. They get no Project write from this ruling; the VPS `GH_TOKEN` stays read-only and GOV-0025 still limits the local watcher to the `[watch]` issue body.
- Does not apply when: writing any Project field other than Spent. Other writes by the planner are not settled here.
- Spent is reporting only. It never holds a run (GOV-0033).

## Context

#662 asked the engine to write each run's cost to a `runs` ledger and to set the org Project's Spent field (a Number field). Nothing in the engine could write to the Project: the VPS watcher reads GitHub with a read-only `GH_TOKEN`, the local watcher may write only the `[watch]` issue body (GOV-0025), and the question took it that no swarm App held the org Projects permission. The builder raised #731 and, by its default, #662's PR (#732) built the ledger and `swarm spent`, which prints each Mission, Goal and Area's Spent value and writes nothing to the Project. Cost estimates are already public in heartbeat events (GOV-0002, GOV-0004), so the question was about the writer's identity and permission, not about exposing cost.

The owner answered on #731: "Option 1. productswarm-planner already holds org Projects read and write, so use that. No new App and no new key on the host: the planner sets Spent from `swarm spent` in its daily run." The owner added `Record: yes`, and the question is one-way.

## Options considered

1. **Org Projects permission on one existing App, the planner** (chosen): the planner, which already holds the permission, sets Spent.
2. **A dedicated `productswarm-engine` App** with only `organization_projects: write` and `metadata: read`, its key only on the host and held by no session, like the merger App (GOV-0028).
3. **Don't write Spent for now**: `swarm spent` prints the values and the lead copies them into the daily report.

## Deliberation

n/a. This is an authoritative decision by the owner, who chose option 1 in a comment on #731, against the question's recommendation of option 2.

## Consequences

- The planner's daily run gains a step: run `swarm spent` and set Spent on each Mission, Goal and Area item from it. That is a follow-up issue; this ruling builds nothing.
- A session (the planner) holds a Project write, unlike the merger App, whose key no session holds (GOV-0028). The team accepts that the planner can edit Project fields, as it already could.
- No key or App is added to `/etc/productswarm/secrets.env` or the host for Spent.
- Spent is updated once a day, so it lags the `runs` ledger by up to a day.
- A wrong or misused Project write by the planner, or a need for Spent fresher than daily, is the signal to ask again, for example about option 2.
