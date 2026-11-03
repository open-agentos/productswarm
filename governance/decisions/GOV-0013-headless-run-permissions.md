---
id: GOV-0013
title: Headless runs that swarm watch starts use auto mode, with explicit denies for merging and label edits
status: in-force
kind: ruling
question: "#131"
domain: security
shape: authoritative
classification:
  reversibility: one-way
  blast_radius: repo
  nature: values
  knowledge: shared
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-03
review_by: 2027-01-31
supersedes: []
applies_to:
  paths:
    - launcher/**
  roles: []
  situations:
    - building or changing how `swarm watch` starts a headless (`claude -p`) run
    - choosing the permission mode or tool allow/deny rules for a loop-started run
---

## Ruling

When `swarm watch` starts a headless (`claude -p`) run, the launcher passes `--permission-mode auto`, the same mode interactive sessions run in today, plus `--disallowedTools` for `gh pr merge` and label edits as a backstop.

## Applies when / does not apply when

- Applies when: `swarm watch` starts a headless run for real (not `--dry-run`).
- Does not apply when: the owner starts a session with `swarm up` or `swarm launch`. Those stay interactive and unchanged.
- It does not change `ops/`. `ops/swarm-session` already passes extra arguments to `claude` unchanged.

## Context

On #125 the owner chose option 3: runs that `swarm watch` starts become one-shot `claude -p` runs with a Stop hook. On #126 the owner chose a hard per-run budget (GOV-0012). A `-p` run has nobody to answer a permission prompt, and in Manual mode it denies every tool call that needs approval. The worktree's `.claude/settings.local.json` has hooks but no allow rules, so a headless builder would be refused at `git push` or `gh pr create` and could never open its PR. The planner raised #131 to settle this before planning any issue for #125. The `security` domain is `always_one_way`, so the question was rated one-way and blocking. The owner answered "Option 3" in a comment on #131.

## Options considered

1. **Do nothing:** headless runs use the default mode and are refused at the first call that needs approval, so #125's option 3 can't be built.
2. **Per-role allowlist:** `--allowedTools` per role (file reads and edits, the `git`/`gh` commands that role needs) plus `--disallowedTools` for `gh pr merge` and label edits. Auditable in one file, but brittle: a run that needs an unlisted command is denied mid-task, and `gh api` can't be narrowed by pattern.
3. **Auto mode with explicit denies** (chosen): `--permission-mode auto` plus `--disallowedTools` for `gh pr merge` and label edits. Runs behave as interactive sessions already do; what is allowed depends on the classifier, not a readable list.
4. **Bypass permissions** (`bypassPermissions`): nothing is checked. Listed to show the boundary; not recommended.

## Deliberation

n/a. This is an authoritative decision by the owner, who chose option 3 in a comment on #131, matching the planner's recommendation.

## Consequences

- Headless runs act as interactive sessions already do; the only change is that nobody watches. The hard budget (GOV-0012) and the run's done-condition bound what an unwatched run can do.
- The rules that matter most to governance (agents never merge, per GOV-0011; agents never add or remove `ready` or `gov:ruled`, per GOV-0006) are denied mechanically rather than left to the classifier.
- The team accepts that other allows depend on the classifier, and that with nobody watching a wrong allow is noticed only afterwards.
- This ruling does not set the exact `--disallowedTools` patterns; the issue that builds the headless runs does.
