# Brief: what the finance and scenario planner will demand of productswarm

**Question (#693):** what will the finance and scenario planner need from productswarm in its first month: the work, data, access and integrations, the risks (data sensitivity, correctness), and what we'd have to change to take it on?
**For:** the M4 readiness review (#686) and its checklist (#692). **Written:** 2026-11-09. **By:** analyst.

## The point first

The work in the first month is ordinary software that the swarm can build. Two things make the project different from productswarm itself: **the data is private** and **the numbers must be right**. productswarm is built for neither yet. Everything about it is public (repos, issues, the Desk, session logs). Its only check on correctness is a reviewer that has never been shown to block a real defect (`evals/results.md`, #202). The project should start with **synthetic data only**, and real bank data should be a later, separate decision. Before the merger merges calculation code without the owner, productswarm needs a correctness gate and a data boundary.

## 1. What the project is and who it serves

The record says little: a "personal finance and scenario planner" (#526, option C). One user is implied, the owner. Comparable products set what such a planner does:

- **Cash-flow projection** across accounts, income, spending, debts and assets, year by year.
- **Scenarios** ("what if I retire at 60, buy a house, lose income") compared side by side.
- **Uncertainty:** Monte Carlo runs and historical backtests, reported as a "chance of success". ProjectionLab runs up to 2,000 Monte Carlo trials plus historical sequences. Boldin runs 1,000 and keeps Monte Carlo in its paid tier ([Boldin vs ProjectionLab](https://www.boldin.com/retirement/boldin-vs-projectionlab/), **vendor**, Boldin's own comparison; [Boldin pricing](https://www.boldin.com/pricing/), **vendor**; both read 2026-11-09). Pricing reports conflict, between about $109 and $129 a year for ProjectionLab ([ProjectionLab pricing](https://blog.projectionlab.com/pricing), **vendor**, read 2026-11-09). Confidence: **medium**.
- **Tax** is where these products earn trust and where they differ most. Boldin sells "advanced tax optimization" in its top tier (same source).

**So what: avoid.** "Everything ProjectionLab does" is not a one-month scope. The owner needs to set a short written spec (which scenarios, which taxes, which country) before the swarm starts, or the planner role will invent one.

## 2. The work in month one

A plausible month, if the review says go. This is the analyst's estimate, not a plan.

| Week | Work | Done test |
|---|---|---|
| 1 | New repo, owner's spec, domain model (accounts, flows, assumptions), money type | Spec merged; model round-trips a sample household |
| 2 | Deterministic yearly projection engine | Golden cases, worked by hand, pass to the cent |
| 3 | Scenarios and comparison; seeded Monte Carlo | Same seed gives the same result; known closed-form cases match |
| 4 | File import (CSV/OFX) and a minimal read-only view | A synthetic household imports and projects end to end |

The skills involved are mostly ones the swarm already has (builder, reviewer, designer). Two are new: **domain rules** (tax brackets, contribution limits, withdrawal rules, each needing a dated source) and **numerical testing** (golden cases, property tests, seeded randomness).

## 3. Data, access and integrations

- **Month one needs no live bank data.** Synthetic households and file import cover all of the work above.
- **Bank aggregation, if wanted later, is either cheap but user-run or capable but costly.** SimpleFIN Bridge is about $1.50 a month or $15 a year per user, and the user holds the token ([SimpleFIN Bridge](https://bridge.simplefin.org), **vendor**, read 2026-11-09; the older page quotes a different price, so confidence is **medium**). Plaid publishes no full price list; third parties report a $1,000/month minimum on its Growth plan ([Activepieces on Plaid pricing](https://www.activepieces.com/blog/plaid-pricing-2026-cost-per-connection-and-request), **independent** but second-hand, read 2026-11-09, confidence **low**). Open-source planners (Maybe, now the Sure fork) use SimpleFIN for US banks ([Sure SimpleFIN docs](https://www.mintlify.com/we-promise/sure/integrations/simplefin), **independent**, read 2026-11-09).
- **The US open-banking rule is not a foundation to build on.** A court has enjoined CFPB §1033, the April 2026 compliance date passed with no effect, and a new proposal went to OIRA in August 2026 ([Consumer Finance Monitor](https://www.consumerfinancemonitor.com/2026/08/06/cfpb-sends-new-section-1033-open-banking-proposal-to-oira-for-review/), **independent**, 2026-08-06, read 2026-11-09). Confidence: **medium**, because I found no primary CFPB document. **So what: avoid** designing around a rule-mandated free API. Plan for file import first and an aggregator behind an interface.
- **Any aggregator signup is `external`** (`jurisdictions.yml`): it is the owner's to do, and no session should hold its credentials.

## 4. Risks

**Data sensitivity.** Real balances, transactions and account numbers would sit beside agents that read untrusted content (issues, web pages, imported files) and can write outward (comments, PRs, pushes). That combination is Willison's "lethal trifecta": private data, untrusted content and an outbound channel, which together let injected text steal the data. His advice is to remove one leg rather than trust guardrails ([Simon Willison, "The lethal trifecta"](https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/), **independent**, 2025-06-16, read 2026-11-09 via secondary coverage, confidence **high** on the claim). Here, every leg is public by default: org repos are public, the Desk is public and read-only (GOV-0032), and session notes and heartbeats are kept. **So what: threat.** Real data can't enter any place a swarm session can read until a boundary exists.

**Correctness.** A planner that is wrong by a bracket or a compounding convention still looks plausible. productswarm's checks don't catch that:

- The reviewer's eval was **inconclusive** because the sample held no real defect (#202). GOV-0021's planted-defect gate hasn't been run.
- Under GOV-0027 and GOV-0034, the merger would merge go work, including calculation code, once the reviewer approves at head and `tests` pass. Tests the builder wrote check only what the builder thought of.

**So what: threat.** The first wrong number the owner acts on would cost more trust than any process gain.

**Upstream continuity.** Maybe Finance archived its repo in July 2025 and stopped issuing security fixes, and the community moved to the Sure fork ([Sure introduction](https://www.mintlify.com/we-promise/sure/introduction), **independent**, read 2026-11-09, confidence **medium**). **So what: avoid** building on one unfunded open-source finance app's internals. Borrow its ideas, not a dependency on it.

## 5. What productswarm would have to change

In rough order of need. Each change is a candidate checklist line for #692, and none is decided here.

1. **A second repo the engine serves.** GOV-0031 lets go work sit in any org repo, but the merger and dashboard fall back to one `default_repo()` (`launcher/merger.py:580`). Confirm that the watcher, merger, reviewer reconciler and Desk handle a second repo, and that a session's work is scoped to it. Confidence: **medium**, since I read only the fallback.
2. **A data boundary.** For month one, keep synthetic data only and write a fixtures-only rule into the new repo's role prompts and rubric. Before any real data: decide whether the repo is private, keep real data out of GitHub, Actions, session transcripts and the Desk, and give no session both real data and an outbound channel. Whether to go private, and any aggregator, are `external`/`security` questions for the owner.
3. **A correctness gate before merges without the owner.** Golden cases worked outside the code (by the owner or from cited sources) live in a path that builders can't change under the standing grant. The rubric requires decimal or integer-cent money, seeded randomness, and a dated source for every rule constant. Run GOV-0021's planted-defect eval on a calculation bug before the merger merges calculation code on its own. Changing which paths the standing grant covers would need a `gov:question`.
4. **A spec from the owner.** One page: who it's for, which country's tax, which scenarios, and what "right" means (to the cent, or within a tolerance). Without it, the planner role will make product calls the owner should make.
5. **Spend.** A second product shares GOV-0033's single $1,000/month Console limit with productswarm's own work. The readiness review should say how the two split it.

## What I didn't cover

The owner's own intent for the planner beyond #526's one line; non-US banking (UK/EU open banking is mandated and differs); licensing of any borrowed code; regulatory status if the planner ever gives advice to anyone but the owner.

-- analyst (claude-opus-5-5)
