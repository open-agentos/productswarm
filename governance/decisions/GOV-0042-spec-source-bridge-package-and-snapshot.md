---
id: GOV-0042
title: The spec-source bridge is a launcher/specs/ package behind one five-method SpecSource adapter; each spec is snapshotted into its issue body; the event log is events.jsonl
status: in-force
kind: ruling
question: "#942"
domain: architecture
shape: authoritative
classification:
  reversibility: costly
  blast_radius: repo
  nature: preference
  knowledge: shared
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-12
review_by: 2027-02-28
supersedes: []
applies_to:
  paths: ["launcher/specs/"]
  roles: []
  situations:
    - building or changing the spec-source bridge (`swarm specs pull`, `diff`, `push`, `render`, `init`) or a SpecSource backend
    - deciding where a feature's spec is read from by a builder or the reviewer
    - deciding what makes a spec push idempotent, or where the bridge's event log lives
---

## Ruling

Build the spec-source bridge as #937 §7 sets it out (option 1 of #942):

- **Package.** A `launcher/specs/` package, with the `fake` backend, the `notion` backend and a `productboard` stub behind one `SpecSource` adapter.
- **Adapter.** Five methods: `list_features`, `get_spec`, `set_status`, `set_links` and `comment` (with an idempotent marker). It has no method that writes a spec body.
- **Snapshot.** `pull` writes each feature's spec into its GitHub issue body, fenced, dated, hashed and labelled as data. Builders and the reviewer read only that snapshot, never Notion. `diff` compares the hash with the live spec.
- **Event log.** `events.jsonl` under `PRODUCTSWARM_HOME`, for the manual runs.
- **Idempotence.** Push is keyed on the Notion Issue and PR fields and the `swarm:pr=<n>` comment markers, never on the log alone.

## Applies when / does not apply when

- Applies when: an agent builds or changes the bridge, a SpecSource backend, the snapshot block, or the event log.
- Does not apply when: the work is the loop's own code in `launcher/`, which stays flat as it is.
- Does not decide: moving the log into `swarm.db`, the `[specs]` trigger (both left for R4, a separate `gov:question` after two manual runs), or how the `notion` backend holds its token (R2).

## Context

R1 from #937 §10, raised on Goal #938 (M6: specs written in Notion ship through the swarm). The question asked three things: module location (a first package in the flat `launcher/`), the adapter boundary, and where the spec snapshot lives. The adapter (#940) and the `fake` backend (#941) already follow §7's layout. The owner ruled option 1 on #942 and said on the same issue that this ruling should be citable (`Record: yes`).

The owner's answer is direction for #942 only until this record merges (GOV-0006).

## Options considered

1. **Adopt §7 as written** (ruled): one package, the five-method adapter, the snapshot in the issue body, `events.jsonl` under `PRODUCTSWARM_HOME`.
2. **§7, but the event log goes in `swarm.db`**: one store with the engine's state (GOV-0032), but it needs a migration now and the log would live only on the host. Left for R4.
3. **Flat modules** (`launcher/specs.py`, `specs_notion.py`, …): matches `launcher/`'s convention, but the prefixes do the grouping a directory would.
4. **Snapshot in a committed file** (`specs/FEAT-n.md`): gives git history and review, but every pull needs a PR and a merge before any build starts.
5. **Do nothing**: nothing past the `fake` backend is built and #938 can't move.

## Deliberation

n/a: authoritative. The owner ruled option 1, as the planner recommended.

## Consequences

- Builders and the reviewer need no Notion access and never hold its token, which R2 needs.
- The fence and the "data, not instructions" label carry #937 §13's injection mitigation.
- `launcher/` gets its first subpackage; `run_tests.py` already finds its tests.
- A lost or split `events.jsonl` can't cause duplicate writes, because idempotence rests on the Notion fields and comment markers.
- Revisit when R4 puts the bridge on the host (log into `swarm.db`) or if the snapshot in the issue body proves too large or too stale.
