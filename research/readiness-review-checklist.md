# Brief: the readiness review checklist (M4)

**Question (#692):** what should the M4 readiness review check, to decide whether productswarm takes on the finance and scenario planner? One line per check, with its measure and where the evidence comes from. Start from PRODUCT.md's day-30 checks and the done test, then add what a second, outside project needs.

**Answer first:** the review needs 20 checks. Checks 1–8 are the done test and the day-30 scorecard; they decide whether productswarm runs like a department. Checks 9–20 decide whether it can carry a second repo. Each is a **gate** (a fail means no-go) or a **follow-up** (the review can pass, and the fix becomes an issue under the planner's Goal). Three gates have no tool to measure them yet: owner acts per day (1, 2), a second repo end to end (9), and the reviewer catching a planted defect (13). Those need issues now if the review is to have evidence on 2026-12-04.

Written 2026-11-09 against `main` at d7b062d. Rulings cited are in force on that date.

## What changed since the checks were written

- **The plan is no longer `PLAN.md`.** GOV-0031 retired it: the plan is the owner-opened Goal and Area issues on the org Project. M4 is Goal #686. "Cites a milestone" (day-30 check 4) now means "closes an issue under an owner-opened Goal or Area". The `**Milestone:**` body line counted only for one week after GOV-0031 merged (2026-11-07).
- **The engine is moving off the owner's Mac** (GOV-0032: hosted watcher, dispatcher, merger and Desk on a VPS by Dec 4). That makes Q5 (where the daily run happens) moot if the VPS is live, and makes engine uptime a check.
- **The 10-day window must start by Thursday 2026-11-20** to end on Wednesday 2026-12-03, the day before the review (Mon–Fri working days: Nov 20, 21, 24–28, Dec 1–3). If any day in it fails, the done test can't pass by Dec 4 unless the window restarts and the review moves.

## The checklist

### A. Runs like a department (the done test and day-30 scorecard)

| # | Check | Measure | Evidence from | Gate? |
|---|---|---|---|---|
| 1 | Owner acts under 5 a day | Under 5 owner acts on each of 10 consecutive working days. **Counts:** labels, merges, issue and PR comments, reviews, issues opened other than Goals and Areas, approved asks and protected-path merges. **Doesn't count:** opening or editing a Goal or Area (plan approval), reading the report or the Desk. | The owner's GitHub events per day. **No tool yet:** `dashboard/activity.py` only finds the owner's last act, and the events API keeps 300 events, so one busy day can push earlier ones out. The daily report should record the previous day's count so the evidence exists when the review needs it. | Gate |
| 2 | Owner acts only as the C-team | Every owner act in the 10 days is plan, report, ask or protected merge. No `ready` labels on Tasks, no dispatching comments, no repairs from the back room. | Same daily list as 1, each act tagged by kind. Back-room repairs are self-reported by the owner (no record exists). | Gate |
| 3 | Down from about 40 | Mean owner acts a day over the window, set beside the ~40 baseline from #526 §7. | Same count as 1. | Follow-up (it is reported, not passed or failed) |
| 4 | A daily report every working day, none started by the owner | 10 of 10 working days have a report comment on the pinned report issue, posted by the lead's App, started by `[daily]` (GOV-0029) or the hosted engine, not by an owner `Ask:` or a hand launch. Monday check-ins on Nov 24 and Dec 1. | Report issue comments (author and timestamp); watcher run log for what started each run. M1 (#683) is this check. | Gate |
| 5 | Over half of merges without the owner's click | Share of PRs merged in the window whose `mergedBy` is `productswarm-merger`, over 50%. | `gh pr list --state merged --search "merged:2026-11-20..2026-12-03" --json number,mergedBy`. M2 is this check. | Gate |
| 6 | No unreviewed revert | Zero merged reverts in the window without the reviewer's approval at head, and zero pushes to `main` outside a PR. | Merged PRs titled `Revert` with their reviews; `main`'s commit list against merged PRs. | Gate |
| 7 | Every merged PR sits in the plan | 100% of merged PRs close an issue under an owner-opened Goal or Area (GOV-0031), or touch only a protected path the owner approved at head (GOV-0027's approved asks). | Merger decision comments (GOV-0034's standing-grant check records the Goal it found); sub-issue links on each closed issue. | Gate |
| 8 | The Desk is enough | The owner runs a working week without opening Claude Code to find the state (M3's done test). | Owner's word in the review record. No tool can measure this; say so in the record. | Follow-up |

The fifth day-30 check (the review is scheduled, with its checklist in the plan) is met once this brief merges and the review is on #686.

### B. Can take on a second, outside project

| # | Check | Measure | Evidence from | Gate? |
|---|---|---|---|---|
| 9 | A second repo works end to end | One dry-run Task in a scratch repo (or the planner repo) under an owner-opened Goal is found as go, dispatched, built, reviewed, merged by the merger, and shows on the Desk and in the report, with no owner act but opening the Goal. | That issue's timeline and PR. **No tool or issue yet:** the launcher and merger read one repo today. GitHub sub-issues can sit in another repo of the org, up to 100 per parent and 8 levels deep ([GitHub docs](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/adding-sub-issues), independent, read 2026-11-09). | Gate |
| 10 | The Apps and merge path are set up there | Each role App and `productswarm-merger` is installed on the planner repo; its ruleset gives the merger the bypass GOV-0028 sets and nothing wider; `tests` is a required check. | Repo settings, read with `gh api` and quoted in the record. | Gate |
| 11 | The planner repo has a test gate worth trusting | `tests` runs on every PR and covers the money maths (balances, scenario totals) with fixed cases. GOV-0027's standing grant trusts `tests` passing. | The planner repo's CI config and test list. | Gate |
| 12 | Its governance is decided | A merged ruling says whether productswarm's `GOVERNANCE.md`, `jurisdictions.yml` and records apply to the planner repo, or which ones it has of its own. Nothing currently says. | `governance/INDEX.md`. Needs a `gov:question` in the `governance` domain. | Gate |
| 13 | The reviewer blocks a real defect | The reviewer requests changes on most planted defects in a seeded sample (for example, a wrong rounding rule, or an off-by-one in a scenario's month count). B4's result was inconclusive because its sample had no real defect (`evals/results.md`). For a finance app, standing-grant merges depend on this more than they did here. | A seeded-defect eval run, reported like B4. **No issue yet;** the owner's decision on how to test it is still open (PRODUCT.md, Stage B). | Gate |
| 14 | No private data leaves the owner | No real financial data in the repo, issues, PRs, logs, prompts or the public Desk. Fixtures are synthetic. Secret scanning and push protection are on. The Desk stays public and read-only until Google login (GOV-0032), so anything it shows from the planner must be safe to publish. | Repo security settings; a search of issues and fixtures; the Desk page for the planner. | Gate |
| 15 | The engine runs without the owner's Mac | The hosted watcher, dispatcher and merger ran every working day of the window (GOV-0032), or Q5 is answered. | Engine run log; check 4's start records. | Gate |
| 16 | The owner-act budget holds across two repos | The under-5 count in check 1 includes both repos. A projection: owner acts on productswarm in the window plus the acts the dry run in 9 took. | Same as 1 and 9. | Follow-up |
| 17 | Spend is visible per product | Cost per merged PR and per mission shows by product (the org Project's Product field), inside GOV-0032's per-run and per-mission caps; GOV-0033 sets no daily total. | `swarm cost` or its engine successor, split by repo. | Follow-up |
| 18 | The roles aren't productswarm-shaped | The role prompts and launcher name no productswarm-only paths or rulings that would mislead a planner session; or the planner repo has its own versions. | A read of `roles/` and `launcher/` for hard-coded repo names, done by the reviewer or a call-in. | Follow-up |
| 19 | One switch stops the planner's work | Pausing dispatch and merges for one repo, without stopping productswarm, is tested once. | The pause command and a record of the test. | Gate |
| 20 | The report covers both | The daily report and Monday check-in show the planner's Goal beside productswarm's, with asks for each. | A report from the dry run in 9. | Follow-up |

## How to hold the review

- **Pass:** every gate passes. **Fail:** any gate fails; the record says which, and the lead opens an issue for each under #686 or a successor Goal.
- **Record:** on #686, one line per check: pass, fail or not measured, with a link to its evidence. "Not measured" counts as a fail for a gate.
- **The other half of M4:** #686 also asks for an analyst brief on what the finance planner will demand. That brief should set the planner-specific bars in checks 11, 13 and 14; until it exists, the measures above are a floor.

## So what

- **Copy:** Google SRE's Production Readiness Review has the same shape: a service-specific checklist, analysed before handover, with each gap turned into an agreed fix before the team takes on the service ([Site Reliability Engineering, ch. 32](https://sre.google/sre-book/evolving-sre-engagement-model/), independent, read 2026-11-09). Its areas (dependencies, monitoring, emergency response, capacity, change management) map to checks 9, 4, 19, 17 and 5–7. Taking on its "gaps become filed issues" rule makes a failed review a plan, not a dead end.
- **Threat:** checks 1, 9 and 13 have no tool or issue today. If nobody builds the owner-act count before Nov 20, the review has no evidence for the done test, and that is the goal's headline number.
- **Opening:** GitHub's cross-repo sub-issues already support GOV-0031's "any repo of the org", so check 9 is launcher and merger work, not a platform gap.
- **Avoid:** counting only productswarm's own acts. A second repo adds the owner's acts there too; check 16 keeps the budget honest.

-- analyst (claude-opus-5-5)
