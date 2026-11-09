---
id: GOV-0031
title: An open Goal or Area the owner opened is the go for the work under it; PLAN.md is retired
status: in-force
kind: ruling
question: "#651"
domain: governance
shape: authoritative
classification:
  reversibility: costly
  blast_radius: org
  nature: values
  knowledge: held
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-07
review_by: 2027-02-28
supersedes: [GOV-0026]
applies_to:
  paths: ["launcher/", "roles/", "PRODUCT.md", "PLAN.md"]
  roles: []
  situations:
    - choosing which issue to work on
    - deciding whether an issue without `ready` is go because of the scope it sits under
    - opening or ordering a mission's or an area's Tasks (lead)
    - proposing a change to the plan
    - starting a `[build]` session on an issue (`swarm watch`, launcher)
---

## Ruling

PLAN.md is retired. The plan is the set of open Goal and Area issues the owner opened, shown on the org Project. Missions sit under them. Milestones carry release dates only.

An implementation issue is go when all of these hold:

- a swarm App or the owner opened it;
- it sits under an open Goal or Area issue the owner opened, at any depth of sub-issues, in any repo of the org;
- none of its blocked-by issues is open;
- the owner hasn't vetoed it: a `hold` label, a close, or a comment.

An owner-applied `ready` stays a go. `gov:question`s keep `ready` and `gov:ruled` as GOV-0006 sets out.

The owner approves a Goal or Area by opening it, and ends it by closing it. The lead proposes plan changes in Discussions › Strategy, and the owner applies them by editing the issue. A Goal or Area opened by anyone else does not count, and the report flags any edit to one by anyone but the owner.

## Applies when / does not apply when

- Supersedes GOV-0026. Amends GOV-0027 (`PLAN.md` stays a protected path until it is deleted, #652) and GOV-0030 (the plan is the owner's Goals and Areas, not `PLAN.md`).
- For one week after this merges, the `**Milestone:** M<n>` and `**Waits on:**` body lines also count, read against `PLAN.md` as GOV-0026 did. After that, only sub-issue and blocked-by links count.
- Does not decide: merging (GOV-0011, GOV-0022, GOV-0027), hosting, the org Project or the reporting contracts (#651's architecture answer), or spend caps.

## Context

GOV-0026 made the owner's merge of `PLAN.md` the go. `PLAN.md` was not a protected path, so once the merger went live an agent PR could have added a milestone and made its own issues go (closed by #652). An issue's author cannot be forged by an App, so tying the go to an owner-opened issue makes approval one act instead of a reviewed PR. A Goal can also roll up areas and missions across teams, products and repos, which neither `PLAN.md` nor a repo milestone can do. Design: operating model v2 (#651).

## Options considered

1. **Keep GOV-0026**: `PLAN.md` stays the plan, protected by path; approval stays a reviewed PR, and nothing spans repos.
2. **Owner-opened Goal or Area is the go** (chosen): approval is opening an issue; the go reaches across repos through sub-issues.
3. **Only `ready` is the go**: back to GOV-0006 alone; the owner labels every issue, about 40 acts a day.

## Deliberation

n/a (authoritative).

## Consequences

- Builder work follows in two PRs: the launcher (`swarm.py`, `watch.py`, `stophook.py` and their tests) reads Goal and Area issues and their sub-issue and blocked-by links; then the six role prompts, `roles/planner.md`, `PRODUCT.md` and `launcher/README.md` change and `PLAN.md` is deleted.
- Needs the Goal and Area issue types and the owner's M1–M4 Goal issues before the launcher change can go live.
- Revisit if an App-opened issue is ever counted as a Goal or Area, or if cross-repo sub-issues turn out not to work in the org.
