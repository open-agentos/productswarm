---
id: GOV-0046
title: The Effort mix cache carries each PR's Goal, resolved once by the classifier
status: in-force
kind: ruling
question: "#1021"
domain: architecture
shape: authoritative
classification:
  reversibility: two-way
  blast_radius: repo
  nature: preference
  knowledge: shared
decided_by: owner (mattmcalister), on #1021
ratified_by: humans.owner
date: 2026-11-14
review_by: 2027-02-28
supersedes: []
applies_to:
  paths:
    - classify/**
    - dashboard/**
  roles: []
  situations:
    - setting or changing the shape of `classify/cache/effort.json` (schema 1)
    - adding another classifier cache under `classify/cache/`
    - a Desk page needing plan context (Goal or Area) for a merged PR
---

## Ruling

`classify/cache/effort.json` carries each PR's `goal`, resolved once by the writer (`swarm classify run`) and stored; the Desk reads it and makes no new API calls. `goal` is the open Goal or Area above the PR's closing issue at classification time, as `owner/repo#N` (or a bare number in this repo), and may be null. Areas count as well as Goals, as `scope_goal` does. `goal` is not part of the classification: changing it never triggers a relabel, and only `hash` decides that. Later classifier caches under `classify/cache/` follow the same pattern: plan context the readers need is resolved once by the writer and stored, never re-resolved by a page at build time.

## Applies when / does not apply when

- Applies when: a writer or reader of a cache under `classify/cache/` handles plan context for a PR, or the cache's schema changes.
- Does not apply when: the data is not plan context (labels, hashes and timestamps are the writer's own business). It does not set where `classify/` lives (GOV-0044), the spec bridge (GOV-0042) or the classifier's model calls (GOV-0045).

## Context

PR #1019 (closing #1013, FEAT-4 under Goal #987) sets schema 1 of `classify/cache/effort.json`, the interface between #1012 (FEAT-3, the writer) and #1013 (the Desk, the reader). It adds a `goal` field to each PR entry. The reviewer flagged it as an overstep: `architecture` has `decide: []` and GOV-0044 places `classify/` but not the cache's shape. #1012's spec snapshot said only "keyed by PR number and content hash". Raised as #1021; the owner answered Option 1 with the conditions in the issue and asked for a record.

## Options considered

1. **The writer resolves `goal` (schema 1 as in #1019).** One resolution per PR, reusing `swarm.scope_goal` and `trouble.py`'s `pr_goal`. The Desk stays a pure reader and history survives a Goal closing or an issue moving. Chosen.
2. **The cache holds labels only; the Desk resolves PR → Goal at build time.** Tens of extra calls per build against #1013's "no network beyond what they read today", and PRs drop out of past weeks when their Goal closes.
3. **Do nothing:** #1019 stays blocked on the overstep and M7's Desk work waits.

## Deliberation

n/a (authoritative). The owner chose Option 1 with the recommendation's four conditions.

## Consequences

#1012 builds schema 1 with `goal` and #1019 can cite this record. FEAT-3 in Notion gains the `goal` field (the owner's edit); the planner reconciles the snapshot on the next `swarm specs pull`. The writer takes a little more work, and a stored `goal` can be stale if an issue later moves; that is accepted. Revisit if a reader needs the current Goal rather than the one at classification time.
