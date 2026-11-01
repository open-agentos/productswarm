---
id: GOV-NNNN
title: <short imperative title, e.g. "Use pytest fixtures, not setUp methods">
status: proposed            # proposed | in-force | superseded | expired | lapsed
kind: ruling                # ruling | moratorium
question: "#<issue number>" # the gov:question this resolves (omit for autonomous logs)
domain: <domain from governance/jurisdictions.yml>
shape: <precedent | authoritative | autonomous | empirical | advice | consent | committee | vote>
classification:
  reversibility: <two-way | costly | one-way>
  blast_radius: <task | repo | org | external>
  nature: <factual | values | preference>
  knowledge: <shared | held>
decided_by: <identity>      # who made the call (owner, committee, the vote, the experiment)
ratified_by: <identity>     # who merged it; filled at merge
date: YYYY-MM-DD
review_by: YYYY-MM-DD       # after this it is not precedent until re-affirmed
supersedes: []              # [GOV-NNNN, ...]
applies_to:                 # scope; precedent only covers what is listed here
  paths: []                 # globs, empty = whole repo
  roles: []                 # empty = all agents
  situations: []            # plain-language triggers an agent would recognise
---

## Ruling

<One or two sentences. Imperative. What agents must do (or not do) from now on.>

## Applies when / does not apply when

- Applies when: …
- Does not apply when: …

## Context

<Why the question came up. Link the issue and any runs, PRs or evidence.>

## Options considered

1. **<Option>**: <one line on consequences>
2. **<Option>**: …

## Deliberation

<Summary of the debate, or "n/a" for autonomous/authoritative. For committees: members and roles, rounds used, the recommendation, recorded dissent. For votes: eligible, cast, tally, quorum met y/n. For empirical: pre-registered criterion and result.>

## Consequences

<What changes. What the team accepts as a cost. What would make us revisit this.>
