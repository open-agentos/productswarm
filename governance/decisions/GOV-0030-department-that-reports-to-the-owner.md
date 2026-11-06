---
id: GOV-0030
title: productswarm's goal is an AI team run like a department that reports to the owner
status: in-force
kind: ruling
question: "#526"
domain: product-scope
shape: authoritative
classification:
  reversibility: two-way
  blast_radius: repo
  nature: values
  knowledge: held
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-06
review_by: 2027-01-31
supersedes: []
applies_to:
  paths: ["PRODUCT.md", "PLAN.md", "roles/"]
  roles: []
  situations:
    - deciding what productswarm is for, or whether work is in scope
    - planning or building anything after v0–v3
    - deciding whether process or tooling work may go ahead without a milestone
    - deciding when the outside project (the finance and scenario planner) or a consultant's kit starts
---

## Ruling

productswarm's goal is **an AI team run like a department that reports to the owner** (option 2 of #526). A lead agent (the planner, promoted) keeps a milestone plan (`PLAN.md`) with the owner. The swarm works that plan under authority the owner delegates, not with the owner approving each issue or merge. The lead reports daily and checks in against the plan weekly, with the owner as its C-team.

- **Done when:** productswarm runs itself that way for 10 working days in a row, with the owner acting only as the C-team (plan, report, asks, protected merges) and under 5 owner acts a day. It ends in a readiness review for the first outside project, the finance and scenario planner.
- **Order:** the department (A) comes first. The outside project (C) is its finish line, through that readiness review. A consultant's delivery kit (B) follows once a named peer asks for it.
- **Governance is infrastructure, not the product.** It is how the lead knows what it may decide without the owner.
- **Work cites the plan.** Every issue and PR names its milestone. New process or tooling work outside the plan stops.

## Applies when / does not apply when

- Applies when: an agent decides what productswarm is for, plans or opens work, or weighs a feature against the goal.
- It amends GOV-0015: v3's remaining work goes ahead only where a `PLAN.md` milestone takes it up. The needs-you digest (stage F, #249) becomes the daily report. C stage 2 is deferred, except a scheduled run for the lead's daily report if Q5 calls for it. GOV-0015's B → F → C order holds for whatever v3 work a milestone takes up.
- It amends GOV-0001's context: productswarm is no longer framed as the Phase 0 test bed for open-agentos/agent-governance. Governance is part of productswarm. GOV-0001's ruling (follow `GOVERNANCE.md`) is unchanged.
- Does not decide: which issues are go (GOV-0026), who merges (GOV-0027, GOV-0028), what triggers the daily report, `Ask:`, `Research:` and call-ins (GOV-0029), or where the daily run happens when the owner's Mac is off (Q5, not yet asked). Those are #526's Q2–Q5, each ruled separately.

## Context

v0–v3 solved "I can't see my sessions". The owner still directed the swarm one instruction at a time: about 40 labels and merges a day over the repo's first 6 days, and 85% of owner-opened issues were about process (#526 §7). #464's committee proposed "only what's yours"; the owner kept the desk and asked for a self-steering swarm, and withdrew "governance as the product". The owner raised #526, drafted in a planning session, to set a goal. The full proposal (operating model, interface, rulings needed, what stops, the first two weeks and the evidence) is in #526's body.

## Options considered

1. **Do nothing:** v3 as staged in GOV-0015. It ships, but still without a goal.
2. **A, the department that reports to the owner** (chosen): lead, milestone plan, delegated authority, daily report. Proved on productswarm itself.
3. **B, a consultant's delivery kit first:** a peer runs it on a client-style repo. Setup cost would swamp the month.
4. **C, an outside app first:** the swarm builds the finance and scenario planner now. Without A, it repeats today's dispatching on a new repo.

## Deliberation

n/a. This is an authoritative decision by the owner, who answered on #526: "Confirmed Option 2. C becomes its finish line (the readiness review), and B follows once a named peer asks." A later comment added `Record: yes` and compressed the rollout (see Consequences).

The proposal also ruled two earlier questions. On #464, it keeps the ceiling of 5 asks (now the daily report's limit), the desk as the control panel, and "don't put the latest feature front and centre". Messaging becomes a later stage of the report, notify only to start. It supersedes #439's desk ranking with one new panel: plan vs actual.

## Consequences

- `PRODUCT.md` is rewritten around this goal (#528), `roles/planner.md` makes the planner the lead (#529), and `PLAN.md` holds the milestones (#574). Before this record, they cited #526 as direction only; they can now cite GOV-0030.
- The owner keeps setting milestones, granting standing authority, approving asks, reading the report, and approving protected paths (`governance/`, `ops/`, workflows, `jurisdictions.yml`). The owner stops labelling each issue, pressing merge, starting sessions, running committees and relaying between roles, as GOV-0026, GOV-0027 and GOV-0029 allow.
- **Rollout, per the owner's later comment:** the proposal's two weeks are compressed. Q2, Q3 and Q4 were opened the same day (now GOV-0026, GOV-0027, GOV-0029). Q3's shadow runs one day or 10 PRs, whichever comes first, not two days. The first daily report and an `Ask:` run by hand as soon as #529 and `PLAN.md` merge, and are automated after that.
- **On track at day 30 (Dec 4) if:** a daily report every working day, none started by the owner; owner acts under 5 a day, not counting plan approval and reading reports; more than half of merges made without the owner's click, with no unreviewed revert; every merged PR cites a milestone; the finance planner's readiness review is scheduled, with its checklist in the plan.
- The team accepts that v3's unfinished stages, and tooling outside the plan, wait. Non-goals for now: governance as the product, a second user before the readiness review, SaaS, and desk panels outside the plan.
- Revisit if owner acts a day don't fall by Dec 4, if daily reports go unread or unacted on, or once the readiness review is passed.
