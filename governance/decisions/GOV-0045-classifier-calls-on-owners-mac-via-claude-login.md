---
id: GOV-0045
title: Classifier model calls run on the owner's Mac through the Claude Code login, capped per run
status: in-force
kind: ruling
question: "#992"
domain: security
shape: authoritative
classification:
  reversibility: one-way
  blast_radius: external
  nature: values
  knowledge: held
decided_by: owner (mattmcalister), on #992
ratified_by: humans.owner
date: 2026-11-13
review_by: 2027-02-28
supersedes: []
applies_to:
  paths: []
  roles: []
  situations:
    - model calls that classify merged PRs for the Effort mix classifier (Goal #987)
    - live eval runs of the classifier on the owner's held-out set
    - choosing the credential, host, model or per-run cap for those calls
---

## Ruling

Classifier calls run on the owner's Mac through the existing Claude Code login (`claude -p`), with no new credential; `swarm watch`'s daily run starts them. Pin the model in `swarm.toml`, Haiku-class unless the eval shows it fails the pass mark. Cap every call with `--max-budget-usd`: $0.25 per PR classified and $5 per live eval run. Send only public PR text. Don't add an API key under this ruling.

## Applies when / does not apply when

- Applies when: a command or role makes a model call to classify a merged PR, or runs the classifier's live eval.
- Does not apply when: the eval needs sampling control that `claude -p` can't give (FEAT-1's 3-sample agreement may). Raise a new question for option 2 (a dedicated key) then. Also does not cover where recorded-replay tests live (C1), or the Actions reviewer's key (GOV-0018).

## Context

R5 of Goal #987 (M7), raised by the planner on #992. Two things call a model: classifying each merged PR (small, ongoing) and live eval runs on the owner's held-out set (larger, occasional). Tests replay recordings and call nothing. Per-run caps are already the only limit (GOV-0012, GOV-0033); no ruling set a credential or amounts for these runs.

## Options considered

1. **Owner's Mac, existing Claude Code login.** Chosen. No new credential; less control over sampling settings.
2. **Owner's Mac, a dedicated API key** in a 0600 file read only by `swarm classify`, with a workspace spend limit. Full sampling control; one new secret.
3. **GitHub Actions on merge**, key in a default-branch-only environment (GOV-0018 pattern). Labels land without the Mac; a new CI secret and an owner-merged workflow.
4. **Do nothing.** No model calls; `paths` baseline only.

## Deliberation

n/a (authoritative). The owner ruled on #992: "option 1, as recommended", with the details above.

## Consequences

- No new secret anywhere; the same cap mechanism as every other run.
- Classification runs only when the owner's Mac runs `swarm watch`; labels don't land while it is off.
- Sampling settings are whatever `claude -p` offers. Revisit with a new question for option 2 if the eval needs more.
- Revisit if the cap amounts prove wrong or the eval fails the pass mark with the pinned model.

-- docs (claude-sonnet-5-5)
