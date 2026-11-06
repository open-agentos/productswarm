# Plan: productswarm

**Goal:** an AI team run like a department (`PRODUCT.md`, "Goal").

**Done when:** productswarm runs itself that way for 10 working days in a row, with the owner acting only as the C-team and under 5 owner acts a day, ending in the readiness review for the finance and scenario planner (M4).

**Scorecard:** the 30-day checks in `PRODUCT.md`, ["On track at day 30"](PRODUCT.md#on-track-at-day-30-dec-4-if).

The owner approves this plan, and each change to it, by merging.

## M1: Daily report runs without the owner

- **Outcome:** the lead posts the daily report every working day and the check-in every Monday, on the pinned report issue.
- **Date:** when ready.
- **Done test:** 5 working days in a row with a report the owner didn't start.
- **Owner role:** planner.
- **Needs:** Q4 (`[daily]`); by hand until then.

## M2: Merges under delegation

- **Outcome:** PRs inside a milestone merge under standing grants; protected paths merge under approved asks; each use is in the report.
- **Date:** when ready.
- **Done test:** over half of a week's merges without the owner's click, and no unreviewed revert.
- **Owner role:** builder.
- **Needs:** Q3, GOV-0022's stages.

## M3: The desk shows the plan and the report

- **Outcome:** the desk shows milestones and status, today's report, who is on what, and grants in use.
- **Date:** when ready.
- **Done test:** the owner runs a working week without opening Claude Code to find the state.
- **Owner role:** designer.
- **Needs:** M1's report format.

## M4: Readiness review

- **Outcome:** a review decides whether productswarm takes on the finance and scenario planner.
- **Date:** **2026-12-04**.
- **Done test:** the review is held against a checklist in this file, and its result is recorded.
- **Owner role:** planner.
- **Needs:** M1–M3; an analyst brief on what the planner will demand.

## Changing this plan

Changes come as PRs to this file, one change per PR, with why in the first line (`roles/planner.md`).
