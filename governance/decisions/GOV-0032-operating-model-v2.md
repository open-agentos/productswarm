---
id: GOV-0032
title: Adopt operating model v2 (hosted engine, org Project as the plan, learning loop)
status: in-force
kind: ruling
question: "#651"
domain: architecture
shape: authoritative
classification:
  reversibility: costly
  blast_radius: org
  nature: values
  knowledge: held
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-07
review_by: 2027-01-31
supersedes: []
applies_to:
  paths: []
  roles: []
  situations:
    - planning or building the engine, the Desk, the MCP server or the learning loop
    - deciding where the watcher, dispatcher or merger runs
    - deciding where the plan and work items live, and which issue types and links they use
    - deciding how Claude runs are authenticated and how their spend is capped
---

## Ruling

Adopt **operating model v2 in full** (option 2 of #651), as set out in the owner's [design doc](https://claude.ai/artifact/8qSqaCgjZ3xKeT4xWFzopN) of 2026-11-07:

- **GitHub is the record.** The owner works from the Desk and Claude; agents read only GitHub.
- **The engine moves to the owner's Hetzner VPS:** webhooks, an always-on watcher and dispatcher, the merger through a merge queue, a hosted Desk (public and read-only until Google login), and a remote MCP server for Claude.
- **One org Project is the source of truth**, with a Product field. It uses the issue types Goal, Area, Mission, Task, Brief, Question and Lesson, plus sub-issues, blocked-by links, signal labels and Discussions.
- **Work sits in three scopes inside products:** Area, Mission and Goal. Each carries a reporting contract.
- **A learning loop:** session notes, mission retros, and a new librarian role on a different model from the lead. Every lesson ships with an eval case.
- **Claude auth** uses a key from a dedicated Console workspace with a $1,000/month limit. The engine caps spend at about $45 per working day and $150 per mission by default, and stops dispatch at $900.

Build it in the order of the owner's Monday (information in, reports out, then directing) by the Dec 4 readiness review.

## Applies when / does not apply when

- Applies when: an agent plans or builds any part of v2 listed above, or chooses where the engine runs, where work is tracked, how Claude is authenticated or how spend is capped.
- Does not decide: retiring `PLAN.md`. That is a separate ruling, GOV-0031, which supersedes GOV-0026.
- Does not by itself change the terms of the records #651 checked as precedent (GOV-0009, GOV-0010, GOV-0014 for the local `swarm watch` loop; GOV-0022, GOV-0027, GOV-0028 for the merger and its App; GOV-0029 for triggers). They stay in force as written until a record amends or supersedes them.

## Context

GOV-0030 set the goal: a department that reports to the owner. On 2026-11-07 the owner directed operating model v2 and raised #651 to adopt it. Under the current model the watcher runs on the owner's Mac, `PLAN.md` is the plan, and Deploy and Steer stay manual. None of the in-force records covers hosting, the org Project or issue types.

## Options considered

1. **Do nothing:** the watcher stays on the Mac, `PLAN.md` stays the plan, and Deploy and Steer stay manual.
2. **Adopt v2 in full** (chosen): everything in the Ruling, built in the order of the owner's Monday by the Dec 4 readiness review.
3. **Hosting only:** the VPS engine, keeping `PLAN.md`, today's labels and the Mac-era loop. It removes the Mac dependency but leaves the owner dispatching by hand, and delivers none of the Monday rituals.

## Deliberation

n/a. This is an authoritative decision by the owner, who raised #651 and answered on it: "Confirmed. Option 2." with `Record: yes`.

## Consequences

- The v2 work that #651 blocked can go ahead.
- The engine, Desk and MCP server run on the owner's VPS, not the Mac. The Desk is public and read-only until Google login is added.
- The team accepts a dedicated Console workspace key with a $1,000/month limit, and engine caps of about $45 per working day and $150 per mission by default, with dispatch stopping at $900.
- A new librarian role is added, on a different model from the lead.
- The change is costly to undo and org-wide: it moves where the engine runs, where the plan lives and how Claude is paid for.
- Revisit if the hosted engine misses working days, if spend nears the $900 stop, or at the Dec 4 readiness review.
