---
id: GOV-0002
title: Heartbeat events capture minimal fields, tool names and token counts; prompt text stays local, redacted and truncated
status: in-force
kind: ruling
question: "#15"
domain: security
shape: authoritative
classification:
  reversibility: one-way
  blast_radius: repo
  nature: values
  knowledge: shared
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-02
review_by: 2026-11-30
supersedes: []
applies_to:
  paths: ["heartbeat/**", "ops/**"]
  roles: []
  situations:
    - designing or changing the heartbeat event schema
    - implementing or changing the heartbeat hook
    - syncing or publishing heartbeat events anywhere
---

## Ruling

A heartbeat event may capture exactly these fields:

- schema version, timestamp, session id, repo, role, model, event type;
- issue, PR or gov-question number;
- nullable cumulative cost in USD;
- token counts;
- tool names (names only: `Bash`, `Edit` and so on, never their inputs or outputs);
- prompt text.

Prompt text has three extra conditions:

1. **Redact before writing.** Mask known secret patterns: GitHub tokens (`ghp_`, `ghs_`, `gho_`, `github_pat_`), `sk-` style API keys, PEM blocks, and `NAME=value` pairs where the name contains `KEY`, `TOKEN`, `SECRET` or `PASSWORD`.
2. **Truncate** to at most 2,000 characters per event.
3. **Keep it local.** Prompt text is written only to the local spool on the machine running the session. Any event sent off the machine, including to GitHub under GOV-0003, carries every field above **except** prompt text.

Nothing else may be captured: no tool inputs or outputs, file contents, file paths, `cwd`, environment variables, hostnames or credentials.

## Applies when / does not apply when

- Applies when: defining the event schema (#2), building the hook (#3), or moving events anywhere (GOV-0003, #5).
- Does not apply when: a session reads its own transcript locally to compute cost or token counts. That's allowed, as long as nothing beyond the fields above is copied into an event.

## Context

Raised by the builder in #15 while working on #2. The builder recommended minimal fields only. The owner widened that in a comment on #15 to add prompt text, tool requests and token counts. When asked, he narrowed "tool requests" to tool names only and chose redaction, local-only storage and truncation as safeguards for prompt text.

## Options considered

1. **Minimal fields only** (the builder's recommendation): nothing to leak, but the dashboard can't show what a session was asked to do.
2. **Minimal fields plus a free-text note**: more useful, with leak risk from free text.
3. **Minimal fields plus tool names**: low risk, more activity detail.
4. **Do nothing**: #3 stays blocked.

The ruling takes option 3, plus token counts and prompt text with safeguards.

## Deliberation

n/a. This is an authoritative decision by the owner. It departs from the builder's recommendation by adding prompt text: the owner wants to see what sessions are asked to do, and accepts the risk under the three conditions.

## Consequences

- The schema in #2 (PR #16) needs `token_counts`, `tool` and a local-only `prompt` field, and must mark which fields may leave the machine.
- The hook (#3) must redact and truncate before it writes anything, and must strip `prompt` from anything it sends to GitHub.
- Redaction by pattern is best-effort. A secret in an unusual format can still reach the local spool. That's accepted because the spool stays on the owner's machine.
- Revisit if prompt text is ever needed off the machine, for example on a hosted dashboard (#5). Doing so needs a new ruling.
