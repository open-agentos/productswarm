# Governance index

Case law for this repository. **Agents: scan this table before opening a `gov:question`.** Only `in-force` rows whose `review_by` date has not passed count as precedent.

Phase 0: this file is maintained by hand. Every ruling PR adds or updates a row here.

| ID | Ruling (one line) | Domain | Shape | Status | Review by |
|---|---|---|---|---|---|
| [GOV-0001](decisions/GOV-0001-adopt-governance.md) | Follow GOVERNANCE.md for any decision outside your task | governance | authoritative | in-force | 2027-01-31 |
| [GOV-0002](decisions/GOV-0002-heartbeat-capture.md) | Heartbeat events: minimal fields, tool names, token counts; prompt text local-only, redacted, truncated | security | authoritative | in-force | 2026-11-30 |
| [GOV-0003](decisions/GOV-0003-heartbeat-storage.md) | Heartbeat events go to comments on a per-session tracking issue (interim; prompt text stays local) | architecture | authoritative | in-force | 2026-11-30 |
| [GOV-0004](decisions/GOV-0004-heartbeat-public-repo.md) | GOV-0002 and GOV-0003 hold unchanged for a public repo; everything posted to GitHub is public | security | authoritative | in-force | 2026-11-30 |
| [GOV-0005](decisions/GOV-0005-v1-local-launcher.md) | v1 is a lightweight local launcher (manifest, up/ls/stop, issue handoff, spend cap, needs-you list, reviewer by default) | product-scope | authoritative | in-force | 2027-01-31 |
| [GOV-0006](decisions/GOV-0006-triage-labels.md) | Owner-applied `gov:ruled` = decided, `ready` = go; sessions take only `ready` issues; labels count only if the owner added them | governance | authoritative | in-force | 2027-01-31 |
| [GOV-0007](decisions/GOV-0007-docs-opens-ruling-prs.md) | When the owner adds `gov:ruled` to a question needing a record, docs opens the ruling PR; the owner merges | governance | authoritative | in-force | 2027-01-31 |
| [GOV-0008](decisions/GOV-0008-spend-cap-warn-only.md) | v1 spend cap is warn-only: flag "over cap" in `swarm ls` and the needs-you list; the launcher never stops a session without the owner | security | authoritative | in-force | 2027-01-31 |
| [GOV-0009](decisions/GOV-0009-v2-wake-up-loop.md) | v2 is `swarm watch`: a local, foreground, start-only loop that starts the right session on owner-applied `ready`/`gov:ruled` and new PR heads; never stops, labels, merges or comments | product-scope | authoritative | in-force | 2027-01-31 |
| [GOV-0010](decisions/GOV-0010-swarm-watch-spend-limits.md) | `swarm watch` checks every 5 minutes, runs at most 2 loop-started sessions at once, and starts only roles with a `spend_cap_usd`; limits live in `swarm.toml` | spend | authoritative | in-force | 2027-01-31 |
| [GOV-0011](decisions/GOV-0011-bounded-review-loop.md) | Reviewer uses request-changes / comment / approve (approve = rubric passed, never a merge decision); `swarm watch` starts the builder on requested changes, at most 2 rounds per PR, then the owner | product-scope | authoritative | in-force | 2027-01-31 |
| [GOV-0012](decisions/GOV-0012-loop-hard-budget.md) | Runs `swarm watch` starts get `--max-budget-usd` from the role's `spend_cap_usd` plus a `--max-turns` ceiling, and end at either; owner-started sessions stay warn-only (GOV-0008) | security | authoritative | in-force | 2027-01-31 |
| [GOV-0013](decisions/GOV-0013-headless-run-permissions.md) | Headless runs `swarm watch` starts use `--permission-mode auto` plus `--disallowedTools` for `gh pr merge` and label edits; owner-started sessions unchanged | security | authoritative | in-force | 2027-01-31 |
| [GOV-0014](decisions/GOV-0014-one-shot-loop-runs.md) | Sessions `swarm watch` starts run one-shot (`claude -p`) with a Stop hook on a per-role done-condition and record their cost in `watch.json`; owner-started sessions stay interactive | architecture | authoritative | in-force | 2027-01-31 |
| [GOV-0015](decisions/GOV-0015-v3-scope-staged.md) | v3 is quality evals (B) → needs-you digest (F) → GitHub Actions runs (C, reviewer first); plan only B for now, C sub-questions when their stage is next, F and C after the owner reviews B | product-scope | authoritative | in-force | 2027-01-31 |
| [GOV-0016](decisions/GOV-0016-actions-reviewer-log.md) | A reviewer run in GitHub Actions prints only `result`, `subtype`, `num_turns` and `total_cost_usd` to the public job log; no transcript, no artifact | security | authoritative | in-force | 2027-01-31 |
| [GOV-0017](decisions/GOV-0017-actions-reviewer-triggers.md) | Actions reviewer runs start only on `pull_request` for same-repo, non-draft PRs by a swarm App or the owner; a no-secrets check job gates the job with secrets; never `pull_request_target`, `issue_comment` or `workflow_run` on untrusted input | security | authoritative | in-force | 2027-01-31 |
| [GOV-0018](decisions/GOV-0018-reviewer-app-key-in-actions.md) | The reviewer App's key moves to secrets of a default-branch-only Actions environment; the job mints a repo-only token with `pull_requests: write`, `contents: read`, `issues: read`; rotate if anyone but the owner changes the environment or workflow | security | authoritative | in-force | 2027-01-31 |
