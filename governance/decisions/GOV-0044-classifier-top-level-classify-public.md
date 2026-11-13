---
id: GOV-0044
title: The Effort mix classifier lives in a top-level public `classify/`, with its pass mark committed before the first live run
status: in-force
kind: ruling
question: "#991"
domain: architecture
shape: authoritative
classification:
  reversibility: costly
  blast_radius: external
  nature: values
  knowledge: held
decided_by: owner (mattmcalister), on #991
ratified_by: humans.owner
date: 2026-11-13
review_by: 2027-02-28
supersedes: []
applies_to:
  paths:
    - classify/**
  roles: []
  situations:
    - building or changing the Effort mix classifier (Goal #987, C1)
    - adding labelled data, recordings or reports for the classifier
    - the Desk reading effort labels
---

## Ruling

The Effort mix classifier lives in a top-level `classify/` beside `evals/`, holding its code, `data/` (the labelled set), `recordings/` and `reports/`, all public in this repo. The Desk reads its labels.

Two conditions are part of the ruling:

- The pass mark and the held-out set are committed before the first live run, and every report carries their hash, so the bar can't move after a result is known.
- Recordings hold only model replies to public PR text: no prompts beyond that, and no keys or session data (GOV-0002, GOV-0004).

## Applies when / does not apply when

- Applies when: adding or changing code, labelled data, recordings or reports for the Effort mix classifier.
- Does not apply when: deciding R5 (spend and security), which is a separate question; or any other eval, which stays under `evals/` (GOV-0015).

## Context

Goal #987 (M7) needed C1 ruled before its features could move to Ready and come in through `swarm specs pull` (GOV-0042, GOV-0043). The classifier labels each merged PR by effort, and a pre-registered pass mark on a held-out set the owner labelled decides whether it or the `paths` baseline is used. This repo is public, so the labelled set, pass mark and reports become public. Question: #991.

## Options considered

1. **Top-level `classify/`** with code, data, recordings and reports in this repo: one place, matches `evals/`.
2. **`launcher/classify/`** for code, with data and reports under `evals/`: one Python package, one feature split across two trees.
3. **A separate org repo**: can keep labels private; adds a second repo to run and review (GOV-0036, GOV-0039).
4. **Do nothing**: `paths` baseline only.

## Deliberation

n/a (authoritative). The owner chose option 1, as the planner recommended, with both conditions above.

## Consequences

The owner's labels and the pass mark become public. Later work under #987 builds in `classify/`. Revisit if the labels need to be private, or if R5 changes what recordings may hold.
