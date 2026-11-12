# Product brief: productswarm

**Owner:** @mattmcalister · **Status:** goal set: the department that reports to you (#526), done test per GOV-0040 · Q2–Q4 in force (GOV-0031, GOV-0027, GOV-0029), outside project unnamed (GOV-0035), Q5 to come · v0–v3 shipped or in progress (History)

This brief follows the owner's direction on #526 (Option 2). That question is `gov:ruled` with no merged record, so it is direction for #526 only, not precedent (GOV-0006). Every in-force record still holds, and GOV-0015 still sets v3's order. Where this brief describes something a later ruling must allow, it says which one.

## Problem

An owner can't run an AI team the way they run a department (setting direction, letting it work, and hearing back) without dispatching every step.

v0–v3 solved "I can't see my sessions". The owner still directs the swarm one instruction at a time: about 40 labels and merges a day over the repo's first 6 days, and 85% of owner-opened issues were about process (#526 §7).

## Users

- **Now:** the owner, as the team's C-team.
- **Next:** consultants delivering software with agent teams.
- **Later:** their clients, who will want private reports. Design for that; don't build it yet.

## Goal

**An AI team run like a department.** A lead agent keeps the plan with the owner: the Goals and Areas the owner opens (GOV-0031). The swarm works that plan under authority the owner delegates, not with the owner approving each issue or merge. The lead reports daily and checks in against the plan weekly, with the owner as its C-team.

**Done when** (GOV-0040): each open Goal's capability is shown once, on real work or in a scripted drill in the scratch repo. Owner acts are counted and reported (`swarm acts`), never a gate. It ends in a readiness review for the first outside project, once the owner names one (GOV-0035).

**After that:** the first outside project, once the owner names one, is this goal's finish line. A consultant's kit (B) follows once a named peer asks for it.

### On track if

Each open Goal's own done test says when it is met: M1–M4 (#683–#686). GOV-0040 dropped the earlier day-30 checks.

## Operating model

**One lead, the planner promoted, is the owner's direct report.** It owns the plan and the daily report, and it runs the other roles. Everything below goes through it except one-on-ones, which the owner can hold with any role. Its role prompt is #529.

| Habit | What it is | Who runs it | Needs |
|---|---|---|---|
| **The plan** | The owner's open Goal and Area issues and their sub-issues, on the org Project (GOV-0031): today the M1–M4 Goals (#683–#686) and the Engine host Area (#687). Each Goal has an outcome, a hard date or "when ready", a done test and an owner role. The owner opens, edits and closes Goals and Areas; the lead proposes changes in Discussions › Strategy and replans within them. | Lead | GOV-0031 |
| **Weekly check-in** | Each Monday, per Goal and Area: moved, at risk or slipped; what changes; asks. A Strategy proposal comes with any change to a Goal. | Lead | GOV-0029: `swarm watch`'s `[daily]` (#588) |
| **Daily report** | Comment-sized, on the pinned report issue: done against the Goals and Areas, next, risks and mitigations, what agents did under delegated authority, and asks (at most 5). It replaces the digest's content (#249). | Lead | GOV-0029: `swarm watch`'s `[daily]` (#588); Q5 for where it runs |
| **Delegated authority** | Standing grants (what `jurisdictions.yml` and the rulings already allow, listed in one place) and approved asks (a role asks, the owner approves, and the approval lets that role act with the owner's authority). Every use shows in the daily report. | Any role asks; the lead batches | GOV-0027 (merges by the `productswarm-merger` App, GOV-0028); GOV-0031 for which issues are go, and GOV-0034 for which count for the standing grant |
| **One-on-ones** | `Ask: <role>: <question>` on the report issue starts that role once, and it answers in plain words. Extends GOV-0023's call-in. | Any role | GOV-0029: `swarm watch`'s `[ask]` (#590) |
| **Call-ins** | `Call in: <roles>: <why>` on an issue under a Goal or Area; the roles answer once and the lead folds the outcome into the plan. | Lead convenes | GOV-0029: call-ins count on go issues as well as `ready` ones (#594); GOV-0031 makes those the issues under a Goal or Area |
| **Research** | `Research: <question>`, plus the briefs the plan asks for under each Goal. Findings go in `research/` and feed the plan. | Analyst | GOV-0029: `swarm watch`'s `[research]` (#591) |
| **Plan alignment** | Every issue sits under a Goal or Area, and every PR names the one its issue is under. | Lead keeps it; the reviewer checks it | GOV-0031 |

**Rulings in force** (#526 §3):

- **Q2 is GOV-0031** (it superseded GOV-0026). An implementation issue is go when the owner labels it `ready`, or when a swarm App or the owner opened it, it sits under an open Goal or Area the owner opened (any depth of sub-issues, any org repo), none of its blocked-by issues is open and the owner hasn't vetoed it. The lead opens and orders the issues under them. `gov:question`s keep `ready` and `gov:ruled`. The milestone plan file is retired (#708). GOV-0034 counts the same go for GOV-0027's standing grant.
- **Q3 is GOV-0027.** Standing grants: the merger merges a PR whose issue is go under GOV-0031 (per GOV-0034) once the reviewer approved it at head, `tests` pass, there is no overstep, it touches no protected path and it is under the size limit. Approved asks: it merges a protected-path PR once the owner approved it at head, except `GOVERNANCE.md`, `jurisdictions.yml` and workflows. Shadow first, for one day or 10 PRs. GOV-0028 sets the `productswarm-merger` App's permissions. Amends GOV-0022 and GOV-0011.
- **Q4 is GOV-0029.** `swarm watch` starts the daily report and Monday check-in (`[daily]`, #588), an owner's `Ask:` (`[ask]`, #590) and a `Research:` line (`[research]`, #591), and counts call-ins on go issues (#594), which GOV-0031 makes the issues under a Goal or Area. Each has a `swarm.toml` switch. Amends GOV-0009 and GOV-0023.

**Rulings still needed.** None of these is in force:

- **Q5:** where the daily run happens when the owner's Mac is off: local `swarm watch`, or a scheduled Actions run. Asked only if `[daily]`'s local run misses days.
- **Later:** whether agents may merge `GOVERNANCE.md` and `jurisdictions.yml` after the owner approves, whether the Apps may push workflows, and whether a reply by message or through the owner's AI assistant may approve. Only after GOV-0027 has run cleanly.

**What the owner keeps:** opening, editing and closing Goals and Areas, granting standing authority, approving asks, reading the report, and approving protected paths (`governance/`, `ops/`, workflows, `jurisdictions.yml`).

**Where it happens.** The owner looks at the desk (read-only: the plan's Goals and Areas, today's report, who is on what, grants in use) and acts on GitHub (the pinned report issue and PRs). Messaging and the owner's own AI assistant come later. Claude Code and the `swarm` terminal are the back room: agents run there, and the owner goes there only for repairs. Every read and act is a `swarm` command first; the desk, comments and any later interface are thin layers over those commands.

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
