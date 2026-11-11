---
id: GOV-0036
title: The planted-defect gate's throwaway issue is made go by the owner's `ready`, and a merged planted PR is reverted at once and fails the gate
status: in-force
kind: ruling
question: "#821"
domain: product-scope
shape: authoritative
classification:
  reversibility: two-way
  blast_radius: repo
  nature: values
  knowledge: shared
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-11
review_by: 2027-01-31
supersedes: []
applies_to:
  paths: ["evals/README.md"]
  roles: []
  situations:
    - setting up or re-running the planted-defect gate (GOV-0021, E3) and its throwaway issues
    - scoring a planted-defect PR's review
    - a planted-defect PR getting approved or merged
---

## Ruling

The planted-defect gate's throwaway issue is made go by the owner's `ready` (option 1 of #821). The owner adds `ready` to each throwaway issue right after its planted PR opens, and closes the PR unmerged once the reviewer's first review lands. If a planted PR is ever merged, the analyst opens the revert at once and the gate is a fail.

## Applies when / does not apply when

- Applies when: anyone sets up, runs, re-runs or scores the planted-defect gate in `evals/README.md` (GOV-0021, E3), including the re-run of #801 and #802 that #807 needs.
- GOV-0021's pass rule is unchanged: only `CHANGES_REQUESTED` with the right `Block 1` (or, for the second planted PR, `Block 2`) finding passes; `COMMENTED` with `Overstep:` is still a fail.
- Does not apply to: any issue other than a planted-defect gate's throwaway issue, or what makes issues go in general (GOV-0031 and GOV-0034 still decide that).

## Context

#773 kept the throwaway issues (#798, #799) unlabelled and off every Goal or Area so nothing would build or merge them. Under GOV-0031 that made them not go, so the reviewer rightly posted `Overstep:` on both planted PRs (#801, #802) and its reviews came back `COMMENTED`, which the gate scores as a fail. Both reviews did find the planted defect. #807 has the details; the owner asked for the question on #249, and the analyst raised #821.

## Options considered

1. **Make the throwaway issue go by the owner's `ready`, and re-run** (chosen). Tests what E3 is for. Risk: a wrongly approved planted PR is mergeable under GOV-0034; the owner closing the PR covers it, and the owner added a revert rule in case it doesn't.
2. **Change the pass rule** so an Overstep whose only ground is the issue not being go is outside the test. Never checks that the reviewer requests changes, and edits a pre-registered pass rule after a run failed it.
3. **Put the throwaway issue under an owner-opened Goal or Area, with `hold`.** `hold` is a veto under GOV-0031, so the issue still isn't go.
4. **Do nothing.** The gate keeps failing and C stage 2 waits for good.

## Deliberation

n/a. This is an authoritative decision by the owner, who answered on #821: "Option 1. If a planted PR is ever merged, the analyst opens the revert at once and the gate is a fail." with `Record: yes`. The analyst recommended option 1, with plain `ready` (no `hold` alongside it) and a fresh re-run of both planted PRs rather than re-scoring #801 and #802.

## Consequences

- `evals/README.md`'s planted-defect gate gets a line saying the owner adds `ready` to the throwaway issue right after the planted PR opens, closes the PR unmerged after the first review, and that a merged planted PR is reverted by the analyst at once and fails the gate.
- #801 and #802 are not re-scored under this ruling. Both planted PRs are re-run fresh.
- The team accepts a short window in which a planted PR with a defect is go and mergeable under GOV-0034's standing grant, covered by the owner's close and, failing that, the revert.
- Revisit if a planted PR is merged, or if the owner's `ready` and close steps prove too slow to keep the window short.
