---
id: GOV-0016
title: A reviewer run in GitHub Actions prints only its final result to the job log and keeps nothing else
status: in-force
kind: ruling
question: "#205"
domain: security
shape: authoritative
classification:
  reversibility: one-way
  blast_radius: external
  nature: values
  knowledge: held
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-03
review_by: 2027-01-31
supersedes: []
applies_to:
  paths: []
  roles: [reviewer]
  situations:
    - building or changing a GitHub Actions job that runs the reviewer (v3 C stage 1)
    - deciding what a reviewer run in Actions may print to its job log or upload as an artifact
---

## Ruling

A reviewer run in GitHub Actions captures `claude -p --output-format json` to a file on the runner and prints only `result`, `subtype`, `num_turns` and `total_cost_usd` to the job log. It uploads no transcript and keeps no artifact. The heartbeat hook posts its usual remote fields (GOV-0002) and spools nothing, since the runner is thrown away.

## Applies when / does not apply when

- Applies when: a reviewer runs in GitHub Actions (C stage 1, GOV-0015).
- Does not apply when: builder or docs runs in Actions (C stage 2). They may need a different answer, since they run commands and read more; that is left for stage 2.
- Does not apply when: sessions run on the owner's Mac. GOV-0002, GOV-0004 and GOV-0014 apply there unchanged.
- It does not rule on the other C sub-questions GOV-0015 names (prompt injection and secrets, App private keys in Actions secrets, model billing, trigger design).

## Context

GOV-0015 makes C stage 1 the reviewer running in GitHub Actions on pull-request events, and names public Actions logs as its first sub-question. This repo is public, so every Actions job log is public and anyone can download it for the retention period.

GOV-0002 keeps prompt text local only, redacted and truncated, and GOV-0004 says that holds unchanged on a public repo. A runner has no "local". Unless told otherwise, a reviewer run would print whatever `claude -p` writes to stdout and stderr, which, depending on the flags, can be the full transcript, tool inputs and outputs, and file contents the reviewer read.

The planner raised #205. Its recommendation was option 1: the review on the PR is the output that matters, cost and turns are numbers rather than prompt text, and a bad run is debugged by re-running the same PR locally with `swarm launch reviewer`, where GOV-0002 already applies. The recommendation added that the job should mask the App token and the model credential (`::add-mask::`), with sub-questions on secrets covering the rest.

The owner answered on #205: "Option 1".

## Options considered

1. **Final result only, nothing else kept**: print `result`, `subtype`, `num_turns` and `total_cost_usd`; no transcript, no artifact (chosen).
2. **Final result in the log, transcript as a 1-day artifact**: artifacts on a public repo can be downloaded by anyone logged in to GitHub, so this publishes the transcript and conflicts with GOV-0002.
3. **Full output in the log**: easiest to debug; publishes the transcript and conflicts with GOV-0002 and GOV-0004.
4. **Do nothing**: no Actions reviewer runs; C stage 1 stops.

## Deliberation

n/a. This is an authoritative decision by the owner, matching the planner's recommendation.

## Consequences

- The C stage 1 runner may be built to this ruling. GOV-0002, GOV-0003 and GOV-0004 hold unchanged: nothing a reviewer run posts to GitHub includes prompt text or a transcript.
- On a runner there is no local `watch.json` (GOV-0014); the job log's four fields take its place for result and cost.
- The team accepts that a bad Actions run can't be debugged from its log; it is reproduced locally instead.
- Revisit for C stage 2, or if local re-runs prove unable to reproduce Actions failures.
