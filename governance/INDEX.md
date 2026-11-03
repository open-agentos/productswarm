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
