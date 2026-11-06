---
id: GOV-0025
title: The watcher publishes its state as the owner's `gh` login, only by replacing the body of one `[watch]` issue
status: in-force
kind: ruling
question: "#451"
domain: security
shape: authoritative
classification:
  reversibility: two-way
  blast_radius: external
  nature: values
  knowledge: shared
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-06
review_by: 2027-01-31
supersedes: []
applies_to:
  paths: ["launcher/", "dashboard/"]
  roles: []
  situations:
    - publishing `swarm watch`'s state (running, held, skipped, recent failures) to GitHub
    - deciding which identity the watcher writes to GitHub with, or what it may write
    - computing the desk's "owner last acted" while the watcher edits the `[watch]` issue
---

## Ruling

`swarm watch` may publish its state to GitHub with the owner's own `gh` login (option 1 of #451), and only by replacing the body of one `[watch]` issue, only when the state has changed. It makes no comments, labels or other writes. The body is built from templates only, and the desk's "owner last acted" ignores those edits.

## Applies when / does not apply when

- Applies when: the watcher publishes its state (#444 scope 3, #458), or anyone changes what the watcher writes to GitHub or under which identity.
- Applies when: the desk header (#402) computes the owner's last act; edits to the `[watch]` issue's body don't count.
- Does not apply when: the watcher only reads GitHub, or prints its state locally (`swarm status`).
- Does not allow: any other write as the owner's login (comments, labels, new issues, edits to other issues), text copied from issues into the body, or cost in the body (GOV-0014).

## Context

#444 asks to publish the watcher's state so the desk shows why the swarm is or isn't moving; on 5 Nov the swarm looked stalled for hours and nothing public said why. The watcher runs on the owner's machine and reads GitHub as the owner's `gh` login. The launcher mints no App tokens, and #444 rules out new token handling. The planner raised #451 and recommended option 1, limited to the body of the one `[watch]` issue, with the desk header ignoring those edits. The owner answered "Option 1" with those limits and `Record: yes`.

## Options considered

1. **The owner's `gh` login** (chosen): no new token, but agent output appears under the owner's name, so the desk's "owner last acted" must ignore those edits.
2. **An existing App via `ops/swarm-token`** (e.g. planner): attributed to a bot, but the launcher would handle App tokens, which #444 rules out.
3. **Publish nothing** (the default): `swarm status` locally only; the desk shows heartbeat data alone.

## Deliberation

n/a. This is an authoritative decision by the owner, who answered "Option 1" on #451 with `Record: yes`.

## Consequences

- #458 publishes to the `[watch]` issue under the owner's login within these limits; #459 shows it on the floor and accepts the `[watch]` issue only if the owner's login opened it.
- The `[watch]` issue's edits appear under the owner's name on GitHub. The team accepts that, since the body is templated (refs, roles, kinds, times, reason codes) and the desk excludes it from the owner's acts.
- Precedent covers only this one templated body edit. Any other write by the watcher, or a write under another identity, needs its own question.
- Revisit if the watcher needs to write anything else to GitHub, if the launcher gains App tokens, or if owner-attributed edits confuse readers.
