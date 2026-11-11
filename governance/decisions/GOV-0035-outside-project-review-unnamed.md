---
id: GOV-0035
title: The goal ends in a readiness review for the first outside project, unnamed until the owner names one
status: in-force
kind: ruling
question: "#758"
domain: product-scope
shape: authoritative
classification:
  reversibility: costly
  blast_radius: repo
  nature: values
  knowledge: held
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-11
review_by: 2027-01-31
supersedes: []
applies_to:
  paths: ["PRODUCT.md", "research/readiness-review-checklist.md", "research/finance-planner-demands.md", "roles/"]
  roles: []
  situations:
    - deciding what the goal's readiness review is for, or which project it readies productswarm to take on
    - planning or opening work under M4 (#686) or citing the finance and scenario planner as the finish line
    - deciding which readiness checks stay as the bar for an outside project
---

## Ruling

productswarm's goal still ends in a readiness review, but for **the first outside project**, unnamed until the owner names one, not for the finance and scenario planner (option 2 of #758). The readiness checklist's second-repo, private-data and correctness checks (9–20 in `research/readiness-review-checklist.md`) stay as the bar.

## Applies when / does not apply when

- Applies when: an agent plans, describes or measures the goal's finish line, the M4 readiness review (#686), or the day-30 check that the review is scheduled.
- It amends GOV-0030: where GOV-0030 names "the finance and scenario planner" (its Done when, Order, day-30 check and situations), read "the first outside project, unnamed until the owner names one". GOV-0030's done test (10 working days under 5 owner acts a day), its order (A, then the outside project, then B once a named peer asks) and everything else in it are unchanged.
- Does not decide: which project is the first outside one (the owner names it), when the review is held, or how M4 and its sub-issues change. The owner edits Goals (GOV-0031); the lead proposes changes in Discussions › Strategy (#761).

## Context

GOV-0030 set the goal's finish as a readiness review for the finance planner (C). PRODUCT.md's Done when and day-30 check 5, M4 (#686), `research/finance-planner-demands.md` and `research/readiness-review-checklist.md` rest on it. The owner later said the finance planner was a throwaway idea. The planner raised #758 from its Strategy proposal (#761), since only a new record can change GOV-0030.

## Options considered

1. **Do nothing:** GOV-0030 stands, and M4 reviews the finance planner on 2026-12-04.
2. **Amend GOV-0030: the review is for "the first outside project"** (chosen), unnamed until the owner names one; checks 9–20 stay as the bar.
3. **Amend GOV-0030: the goal ends at the 10-day done test.** No outside-project review; M4 closes.

## Deliberation

n/a. This is an authoritative decision by the owner, who answered on #758: "Option 2." with `Record: yes`. The planner recommended option 2: it keeps a useful bar (a second repo, private data, a correctness gate) without a project nobody wants.

## Consequences

- PRODUCT.md, M4's sub-issues and the research briefs may now drop the finance planner as the named finish line; #758's default held them unchanged until this ruling. Checks 9–20 that say "the planner repo" read as the outside project's repo.
- The day-30 check becomes: the readiness review for the first outside project is scheduled, with its checklist in the plan.
- The team accepts a review whose second-repo checks can't run against a real repo until the owner names one.
- Revisit when the owner names the first outside project, or if no project is named by the review date.
