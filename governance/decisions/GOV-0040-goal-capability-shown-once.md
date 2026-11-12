---
id: GOV-0040
title: The goal is done when each open Goal's capability is shown once; owner acts are counted, never a gate
status: in-force
kind: ruling
question: "#867"
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
review_by: 2027-02-28
supersedes: []
applies_to:
  paths: ["PRODUCT.md", "launcher/acts.py", "launcher/swarm.py", "roles/"]
  roles: []
  situations:
    - deciding when the department goal is done, or measuring progress towards it
    - reporting owner acts, a 10-day streak or the day-30 checks in the daily report, `swarm acts`, `swarm daily` or `swarm trouble`
    - writing a Goal's done test or a scripted drill in the scratch repo
---

## Ruling

The department goal's done test is **each open Goal's capability shown once**, either on real work or in a scripted drill in the scratch repo (option 1 of #867). The 10-working-day window, the budget of under 5 owner acts a day and the Dec 4 day-30 checks are dropped. Owner acts are counted and reported, never a gate. The readiness review for the first outside project (GOV-0035) still ends the goal.

## Applies when / does not apply when

- Applies when: an agent states, measures or reports the goal's done test or progress towards it, or writes a Goal's done test.
- It amends GOV-0030: its "Done when" (10 working days in a row under 5 owner acts a day) and its Consequences' "On track at day 30 (Dec 4)" checks no longer hold; read this record's done test instead. GOV-0030's other parts are unchanged: the goal, the order (A, then the outside project, then B once a named peer asks), governance as infrastructure, and work citing a Goal or Area (per GOV-0031).
- Does not decide: what each Goal's capability or drill is (the owner opens and edits Goals, per GOV-0031), when the readiness review is held, or which project is the first outside one (GOV-0035).

## Context

The owner asked on #249 ([comment](https://github.com/open-agentos/productswarm/issues/249#issuecomment-6807069438)) for a `gov:question` to amend GOV-0030's "Done when" and day-30 checks; the planner raised #867. The open Goals had already moved away from GOV-0030: M4 (#686) asks for one scripted drill in the scratch repo instead of the 10-day window and counts owner acts with `swarm acts` with no budget. `PRODUCT.md`, `swarm acts`, `swarm daily` and `swarm trouble` (`launcher/acts.py`, `DAILY_DAYS` in `launcher/swarm.py`) still measured a 10-day streak and a limit of 5. GOV-0035 had left GOV-0030's done test unchanged.

## Options considered

1. **Amend GOV-0030 as the owner asked** (chosen): drop the 10-day window, the under-5-acts budget and the Dec 4 checks; done when each open Goal's capability is shown once, on real work or in a scratch-repo drill; owner acts counted and reported, never a gate; the readiness review still ends it.
2. **Keep the day-30 checks as a dated progress report only, and change just "Done when":** less churn, but keeps a Dec 4 date and an acts number no Goal uses.
3. **Do nothing:** GOV-0030 and `PRODUCT.md` keep a done test the Goals don't use.

## Deliberation

n/a. This is an authoritative decision by the owner, who answered on #867: "Option 1. The follow-up work the question lists is go once the record merges." with `Record: yes`. The planner recommended option 1: a 10-day window passes only if the right events happen by chance on each day, while a shown capability, or a drill that plants those events, can be checked and re-run after each fix. Counting owner acts without a limit keeps the signal without making a number the test, as GOV-0033 does for spend.

## Consequences

- Follow-up work, each its own issue under the Goal it serves, is go once this record merges (per the owner's answer on #867): `PRODUCT.md`'s "Done when" and "On track at day 30" are rewritten; `swarm acts` drops its limit of 5 and its 10-day check; `swarm daily` and `swarm trouble` stop reporting a 10-day streak as progress.
- GOV-0030's "Revisit if owner acts a day don't fall by Dec 4" no longer applies; owner acts stay in the daily report as a signal.
- The team accepts that a capability shown once in a drill is weaker evidence of sustained running than a 10-day window.
- Revisit if a Goal's capability, once shown, fails on real work, or at the readiness review.
