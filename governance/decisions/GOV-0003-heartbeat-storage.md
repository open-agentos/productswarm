---
id: GOV-0003
title: Store heartbeat events as comments on a per-session tracking issue (interim)
status: in-force
kind: ruling
question: "#14"
domain: architecture
shape: authoritative
classification:
  reversibility: costly
  blast_radius: repo
  nature: values
  knowledge: held
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-02
review_by: 2026-11-30
supersedes: []
applies_to:
  paths: ["heartbeat/**", "ops/**"]
  roles: []
  situations:
    - deciding where the heartbeat hook writes events
    - reading heartbeat events for the dashboard
---

## Ruling

For now, heartbeat events are stored as comments on a **per-session tracking issue** in this repo:

- The session's own role App opens one issue per session and posts each event as a comment containing the event as JSON.
- Events posted to GitHub carry every GOV-0002 field **except** prompt text. Prompt text goes only to the local spool at `~/.productswarm/events/<session_id>.jsonl`.
- Tracking issues never carry `status:` or `gov:` labels.

This is an interim choice. Expect to migrate once hosting (#5) and real usage make the right store clearer.

## Applies when / does not apply when

- Applies when: building the hook (#3), the dashboard generator (#4) or regeneration (#5).
- Does not apply when: choosing a long-term store. That needs a new ruling, which should supersede this one.

## Context

Raised by the builder in #14 while working on #2. The builder recommended a local spool now and a sync to a git branch later (option 3). In a comment on #14 the owner chose option 4 instead, to try it and migrate later when the right approach is clearer.

## Options considered

1. **Local JSONL spool only**: zero infrastructure, but a scheduled Action can't read it.
2. **A dedicated, never-merged branch**: readable by Actions, but every role would need `contents: write`, and each event costs a push.
3. **Local spool plus a later sync** (the builder's recommendation): the hook stays offline, and the remote store is deferred to #5.
4. **Comments on a per-session tracking issue** (chosen): readable through the API with no git, and every role App already has `issues: write`.
5. **Do nothing**: #3 stays blocked.

## Deliberation

n/a. This is an authoritative decision by the owner. It departs from the builder's recommendation in favour of something readable immediately with no new permissions, accepting the noise.

## Consequences

- The hook needs network access and the role's App token, which it gets through `ops/swarm-token` inside a swarm session.
- Each session adds one issue and one comment per event to the repo. The issue list and notifications get noisier, so the owner may want to unwatch these issues or filter them out. The dashboard and future triage must ignore tracking issues.
- GitHub's limits on creating content (roughly 80 a minute and 500 an hour) cap the event rate. The hook should batch events or emit them only on state changes, not on every tool call.
- Migrating later means reading events back out of the comments. Keep the JSON in each comment machine-parseable and versioned (`schema_version`).
- Revisit by `review_by`, or sooner if the noise or the rate limits hurt.
