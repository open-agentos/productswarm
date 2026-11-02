---
id: GOV-0007
title: The docs role opens ruling PRs from the owner's answers
status: in-force
kind: ruling
question: "#57"
domain: governance
shape: authoritative
classification:
  reversibility: costly
  blast_radius: repo
  nature: values
  knowledge: shared
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-02
review_by: 2027-01-31
supersedes: []
applies_to:
  paths:
    - governance/decisions/**
    - governance/INDEX.md
  roles: [docs]
  situations:
    - the owner has added gov:ruled to a gov:question that needs a record
    - writing or opening a decision record PR
---

## Ruling

When the owner adds `gov:ruled` to a `gov:question` that needs a record, the **docs** role opens the ruling PR. Docs copies the asker's draft record if the question has one, or writes one from the owner's answer using `GOV-0000-template.md`. The PR adds the record and its `INDEX.md` row, closes the question, and lists every way the record differs from the draft or the answer. The owner's merge is still the only ratification.

## Applies when / does not apply when

- Applies when the question has an owner-applied `gov:ruled` (per GOV-0006) and needs a record. A question needs a record when:
  - the owner says so in the answer, or
  - it is rated `one-way` or `external`, or
  - it is in the `governance` domain.
- Does not apply when:
  - an answer needs no record. Per GOV-0006 it stays direction for that question only, not precedent.
  - deciding what a ruling means. Docs transcribes and never chooses wording that changes the meaning. If the owner's answer is ambiguous for a one-way or external decision, docs asks back on the question instead of guessing.

## Context

Records were written by the owner or by sessions using the owner's `gh` login (GOV-0002 to GOV-0005). For GOV-0006 the planner drafted the record, but its App has `contents: read`, so the owner had to push the branch and open PR #55 by hand. The Phase 0 log noted that a drafting App identity would keep authorship honest. Only the docs and builder Apps have `contents: write`. CODEOWNERS requires the owner's review on `/governance/`, so a role-opened PR can't become a ruling without the owner's merge.

## Options considered

1. **Docs opens ruling PRs** (chosen): it can write contents, owns the `docs` domain and asks the fewest questions.
2. **The builder does it**: it raises most questions, so it would often write up rulings on its own questions.
3. **A new dedicated role**: clean separation, but it needs a new App and a `jurisdictions.yml` change.
4. **Do nothing**: the owner keeps pushing and opening ruling PRs.

## Deliberation

n/a. This is an authoritative decision by the owner, who chose option 1 ("Option 1, docs.") in a comment on #57, matching the planner's recommendation.

## Consequences

- `roles/docs.md` describes the job, and step 3 of the manual loop in `governance/PHASE0.md` has docs open the PR and the owner merge it.
- The reviewer should check each ruling PR against the owner's answer on its question.
- After merging, the owner still comments the one-line ruling on the question (§6).
- This record itself was drafted by the planner and pushed by the owner, because docs could only take on the job once this merges.
- Revisit if docs ruling PRs often need correction, or if a docs session is rarely running when rulings arrive.
