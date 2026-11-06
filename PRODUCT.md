# Product brief: productswarm

**Owner:** @mattmcalister · **Status:** goal set: the department that reports to you (#526) · Q2–Q5 rulings to come · v0–v3 shipped or in progress (History)

This brief follows the owner's direction on #526 (Option 2). That question is `gov:ruled` with no merged record, so it is direction for #526 only, not precedent (GOV-0006). Every in-force record still holds, and GOV-0015 still sets v3's order. Where this brief describes something a later ruling must allow, it says which one.

## Problem

An owner can't run an AI team the way they run a department (setting direction, letting it work, and hearing back) without dispatching every step.

v0–v3 solved "I can't see my sessions". The owner still directs the swarm one instruction at a time: about 40 labels and merges a day over the repo's first 6 days, and 85% of owner-opened issues were about process (#526 §7).

## Users

- **Now:** the owner, as the team's C-team.
- **Next:** consultants delivering software with agent teams.
- **Later:** their clients, who will want private reports. Design for that; don't build it yet.

## Goal

**An AI team run like a department.** A lead agent keeps a milestone plan with the owner. The swarm works that plan under authority the owner delegates, not with the owner approving each issue or merge. The lead reports daily and checks in against the plan weekly, with the owner as its C-team.

**Done when:** productswarm runs itself that way for 10 working days in a row, with the owner acting only as the C-team (plan, report, asks, protected merges) and under 5 owner acts a day, down from about 40. It ends in a readiness review for the first outside project, the finance and scenario planner.

**After that:** the outside project (C in #526) is this goal's finish line. A consultant's kit (B) follows once a named peer asks for it.

### On track at day 30 (Dec 4) if

- [ ] a daily report on every working day, with none started by the owner
- [ ] owner acts under 5 a day, not counting plan approval and reading reports
- [ ] more than half of merges made without the owner's click, and no unreviewed revert
- [ ] every merged PR cites a milestone
- [ ] the readiness review for the finance planner is scheduled, with its checklist in the plan

## Operating model

**One lead, the planner promoted, is the owner's direct report.** It owns the plan and the daily report, and it runs the other roles. Everything below goes through it except one-on-ones, which the owner can hold with any role. Its role prompt is #529.

| Habit | What it is | Who runs it | Needs |
|---|---|---|---|
| **Milestone plan** | [`PLAN.md`](PLAN.md) holds the goal and its milestones. Each has an outcome, a hard date or "when ready", a done test and an owner role. The lead proposes changes as PRs; the owner approves them. The lead replans within the milestones. | Lead | [`PLAN.md`](PLAN.md) |
| **Weekly check-in** | Each Monday, per milestone: moved, at risk or slipped; what changes; asks. A `PLAN.md` PR comes with any milestone change. | Lead | Q4 for the trigger; by hand until then |
| **Daily report** | Comment-sized, on the pinned report issue: done against the milestones, next, risks and mitigations, what agents did under delegated authority, and asks (at most 5). It replaces the digest's content (#249). | Lead | Q4 for the trigger, Q5 for where it runs; by hand until then |
| **Delegated authority** | Standing grants (what `jurisdictions.yml` and the rulings already allow, listed in one place) and approved asks (a role asks, the owner approves, and the approval lets that role act with the owner's authority). Every use shows in the daily report. | Any role asks; the lead batches | Q3. Until then, GOV-0006, GOV-0011 and GOV-0022 decide who gives "go" and who merges |
| **One-on-ones** | `Ask: <role>: <question>` on the report issue starts that role once, and it answers in plain words. Extends GOV-0023's call-in. | Any role | Q4 |
| **Call-ins** | `Call in: <roles>: <why>` on a milestone-linked issue; the roles answer once and the lead folds the outcome into the plan. | Lead convenes | Q4. GOV-0023 call-ins work today, on `ready` issues |
| **Research** | `Research: <question>`, plus the briefs the plan asks for at each milestone. Findings go in `research/` and feed the plan. | Analyst | Q4 for the trigger |
| **Plan alignment** | Every issue and PR names its milestone. | Lead keeps it; the reviewer checks it | Q2 |

**Rulings still needed** (#526 §3). None of these is in force:

- **Q2:** an approved milestone in a merged `PLAN.md` replaces per-issue `ready`, and the lead opens and orders its issues. Amends GOV-0006. Until it merges, the owner labels issues `ready`.
- **Q3:** the delegation model. Standing grants merge a reviewer-approved, tested PR that touches no protected path, shadow first. Approved asks let an agent merge a protected-path PR the owner approved at its head. Amends GOV-0022 and GOV-0011's "only the owner merges". Until it merges, merging stays with the owner, apart from GOV-0022's `merge:agent`.
- **Q4:** triggers: `[daily]` for the daily report and the Monday check-in, `Ask:` and `Research:`, and call-ins on milestone-linked issues. Amends GOV-0009's trigger table and GOV-0023.
- **Q5:** where the daily run happens when the owner's Mac is off: local `swarm watch`, or a scheduled Actions run. Asked only if Q4's local run misses days.
- **Later:** whether agents may merge `GOVERNANCE.md` and `jurisdictions.yml` after the owner approves, whether the Apps may push workflows, and whether a reply by message or through the owner's AI assistant may approve. Only after Q3 has run cleanly.

**What the owner keeps:** setting milestones, granting standing authority, approving asks, reading the report, and approving protected paths (`governance/`, `ops/`, workflows, `jurisdictions.yml`).

**Where it happens.** The owner looks at the desk (read-only: milestones, today's report, who is on what, grants in use) and acts on GitHub (the pinned report issue and PRs). Messaging and the owner's own AI assistant come later. Claude Code and the `swarm` terminal are the back room: agents run there, and the owner goes there only for repairs. Every read and act is a `swarm` command first; the desk, comments and any later interface are thin layers over those commands.

**Week 1 proves the rituals by hand; week 2 automates the ones that worked.** Nothing new is built until its manual version has run at least twice (#526 §5).

## Non-goals now

- Governance as the product. Governance is infrastructure: it is how the lead knows what it may decide without the owner.
- A second user before the readiness review.
- SaaS.
- New desk panels outside the plan.

## History

v0–v3 are the infrastructure the department goal stands on.

- **v0, swarm dashboard (done).** A heartbeat hook in every session records role, model, issue and rough cost (GOV-0002 to GOV-0004). The dashboard joins it with GitHub state to show each session, open PRs, `gov:question`s and spend.
- **v1, local launcher (done, GOV-0005).** `swarm.toml` lists roles, models and spend caps. `swarm up / ls / stop / launch` start and hand off sessions; `swarm inbox` is the ordered needs-you list; the reviewer runs by default. Caps only warn (GOV-0008).
- **v2, wake-up loop (done, GOV-0009).** `swarm watch` starts the right session on owner signals: `[review]`, `[build]`, `[record]`, `[answer]` and `[respond]`. Limits: GOV-0010 (interval, concurrency, caps), GOV-0011 and GOV-0021 (the bounded review loop), GOV-0012 (hard budget), GOV-0013 (headless permissions) and GOV-0014 (one-shot runs).
- **v3, evals, digest and Actions (in progress, GOV-0015).** Its stages are below.

## v3: evals, digest and Actions

GOV-0015 makes v3 three stages, in order: **B** quality evals, then **F** a phone-friendly "needs you" digest, then **C stage 1**, the reviewer running in GitHub Actions. C stage 2 (builders and docs in Actions) comes after these and is not planned. #526 defers C stage 2, except the lead's daily run if Q5 calls for it, and repurposes the digest as the daily report. The desk's v3 progress panel reads these tables.

### Stage B: evals (done)

B is read-only: it scores past PRs against a rubric and checks the reviewer against a bar for C stage 2 that the owner set.

| # | Issue | What | PR |
|---|---|---|---|
| B1 | #172 | Eval rubric and the pre-registered bar for C stage 2 (`evals/README.md`) | #197 |
| B2 | #173 | `evals/gather.py` picks the PR sample and gathers its issues, records and reviews | #181 |
| B3 | #174 | Score the sampled PRs against the rubric (`evals/results.md`) | #200 |
| B4 | #175 | Reviewer calibration and the result against the bar | #202 |
| B5 | #176 | `swarm cost` prints cost per merged PR from `watch.json` (local only) | #185 |

Result (`evals/results.md`, #202): **inconclusive, not passed.** The eval and the reviewer agreed on all 15 reviewed PRs, but the sample held no real defect, so the "misses" line of the bar wasn't tested. C stage 2 stays gated. The owner decides separately how to test whether the reviewer blocks a real defect.

### Stage F: needs-you digest

| # | Issue | What | PR |
|---|---|---|---|
| F1 | #210 | Needs you: flag `gov:question`s past their time to live | |
| F2 | #211 | `dashboard/digest.py`: render the needs-you list as phone-friendly Markdown | |
| F3 | #212 | `dashboard/digest.py --update`: keep the pinned digest issue current | |
| F4 | #213 | Digest workflow: propose `.github/workflows/digest.yml` for the owner to commit | |

### Stage C1: reviewer in Actions

| # | Issue | What | PR |
|---|---|---|---|
| C1.1 | #214 | `launcher/actions_review.py check`: should this PR event start a reviewer run? Retired by #262: the reconciler's `plan` replaced it | |
| C1.2 | #215 | `launcher/actions_review.py run`: one reviewer pass in Actions with GOV-0012, GOV-0013 and GOV-0014 limits | |
| C1.3 | #216 | `swarm watch`: a `review_in_actions` switch so the local loop leaves `[review]` to Actions | |
| C1.4 | #217 | Reviewer workflow: propose `.github/workflows/reviewer.yml` for the owner to commit | |
| C1.5 | #257 | Reconciler: `actions_review.py plan` lists the open PRs needing a review now (GOV-0020) | #269 |
| C1.6 | #258 | Reconciler: `plan` skips heads already in flight or already attempted, from the Actions run history | #275 |
| C1.7 | #259 | Reconciler workflow: the scheduled `reviewer.yml`, committed by the owner | #279 |
| C1.8 | #262 | Retire `actions_review.py check`; the launcher README and this brief describe the reconciler | |
| C1.9 | #260 | Reconciler switch-over: `review_in_actions` on locally; a bot PR reviewed by the reconciler alone | |

C1.5 to C1.9 are the reconciler (#255 stage 1, GOV-0020). Actions reviews now start from a sweep on `main` every 5 minutes, not from PR events, so one can lag a push by a few minutes or more. To review a PR now, or retry a failed one, the owner dispatches the workflow with its number (`gh workflow run reviewer.yml -f pr=N`). To fall back to local reviews, set `review_in_actions = false` and run `swarm watch` (`launcher/README.md`). #261 (PR pushes nudge an early sweep) is optional and comes after.

Order: B → F → C stage 1. C stage 2 is not planned.

v3's decisions are in GOV-0016 to GOV-0020 and GOV-0024 (the Actions reviewer's log, triggers, App key, workflow, reconciler and trusted authors). #208 (the model credential for Actions runs) is open; the owner's direction on it is a Claude subscription token for now. Workflow files stay the owner's: the swarm proposes them, and the owner commits them.
