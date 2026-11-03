---
id: GOV-0015
title: v3 is quality evals, a needs-you digest and event-triggered runs in GitHub Actions, staged; plan stage B only for now
status: in-force
kind: ruling
question: "#167"
domain: product-scope
shape: authoritative
classification:
  reversibility: costly
  blast_radius: external
  nature: values
  knowledge: held
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-03
review_by: 2027-01-31
supersedes: []
applies_to:
  paths: []
  roles: []
  situations:
    - planning or building anything after v2
    - deciding whether quality evals, a phone-friendly needs-you digest, or role runs in GitHub Actions are in scope
    - deciding when to raise a v3 sub-question
---

## Ruling

v3 is option 1 of #167, in this order: **B** (quality evals) → **F** (a phone-friendly "needs you" digest) → **C stage 1** (the reviewer runs in GitHub Actions on events) → **C stage 2** (builders and docs run in Actions).

For now, plan **stage B only**:

- Split B into small issues, each one PR, each with a "Done when", the files it touches, and its place in the order.
- The B issue pre-registers the bar C stage 2 must meet. The planner may suggest its form; the owner sets the number.
- Raise each C sub-question only when its stage is next, not up front.
- Open no F or C issues until the owner has reviewed B's results.

## Applies when / does not apply when

- Applies when: planning or building v3 work, or deciding which v3 stage or sub-question comes next.
- Does not apply when: any F or C work before the owner has reviewed B's results; this ruling does not let that start.
- It approves the direction only. #167 names five sub-questions (public Actions logs vs GOV-0002/0004; prompt injection and secrets; App private keys in Actions secrets, one-way; model billing in Actions; trigger design), plus smaller design calls (where B's report lives, F's form). Each is still its own question, raised when its stage is next. Nothing here rules on any of them.
- Option 2's launchd local loop (A) is not part of v3. A kit for other repos (D) and other model providers (E) stay deferred as #167 describes; this ruling does not decide them.

## Context

v2 (`swarm watch`, GOV-0009 to GOV-0014) is done. At the owner's request, the planner raised #167 to plan v3, because GOV-0005 and PRODUCT.md list cloud or unattended runs and a GitHub Actions trigger as non-goals that need their own `product-scope` question. #167 named three problems: the loop needs the owner's Mac and an open terminal tab; owner decisions stall when the owner is away; and nothing measures output quality (the reviewer had requested changes once in 20 reviews, never on a bot PR, so GOV-0011's `[respond]` path had never fired).

The owner answered on #167: "Option 1. Plan stage B only for now. Split it into small issues, each one PR, with a “Done when”, the files it touches, and an order. Raise each C sub-question only when its stage is next, not up front. Pre-register the bar for C stage 2 in the B issue, as you suggested; I’ll set the number. F and C issues come after I’ve reviewed B’s results."

## Options considered

1. **B + C (GitHub Actions, staged) + F**: evals first, then a digest that runs no model, then reviewer-only Actions runs, then builders and docs in Actions once B shows the review gate works (chosen, with planning limited to B for now).
2. **B + A (a launchd local loop) + F**: keeps the loop on the Mac but survives closed tabs; still polls, and does nothing while the owner is away.
3. **B only, decide the rest afterwards**: cheapest and best-informed, but the watcher problem stays for another round.
4. **Do nothing**: v2 stays as it is.

## Deliberation

n/a. This is an authoritative decision by the owner, matching the planner's recommendation, with planning limited to stage B until the owner has reviewed B's results.

## Consequences

- The planner may now open stage B issues, unlabelled for triage (GOV-0006).
- B is read-only: it changes no code and no process. Its results gate C stage 2 against the bar the owner sets.
- The costly and one-way parts of C (App private keys moving into Actions secrets, a public trigger surface, public job logs) wait for their own sub-questions. Until those are ruled, GOV-0002, GOV-0004, GOV-0010, GOV-0012 and GOV-0013 apply unchanged.
- Once C stage 2 runs while the owner is away, a `gov:question` can reach its time to live unanswered, so a lapse becomes possible for the first time. #167 suggests F list questions past their time to live so a lapse is visible and gets labelled `gov:lapsed`.
- `PRODUCT.md` should gain a v3 section; that edit is the planner's or docs role's to propose.
- Revisit if B shows the review gate does not work, or once the owner has reviewed B's results and is ready for F and C.
