# The Desk's state questions

**User and job.** The owner, as the C-team, at the desk or on a phone between meetings, wants the department's state from the Desk alone, without opening Claude Code, a terminal or a chat with an agent (M3 #685; M5's draft criterion in #760). They ask the same questions of every open Goal and Area they opened.

**Source.** The trouble panel is `desk.trouble_panel()` (#902). It renders `swarm trouble --json` (`launcher/trouble.py`), and the desk's index page carries it (#903). Field names below are that JSON's: `scopes[]` holds one entry per Goal and Area, and `outside` holds the items under none. Every "today" figure comes from a live `swarm trouble --json` at 2026-11-12 22:08 UTC.

## The questions

The list has eight questions. The test for criterion 2 checks Q1–Q7 against a fixture, so each of those needs a field. Q0 is the reader's trust check.

| # | Question, in the owner's words | Field that answers it | Panel today | Status |
|---|---|---|---|---|
| Q0 | Is this current, and was everything read? | `generated_at`, `errors[]` | subtitle "from swarm trouble at …"; "not read: …" lines | answered |
| Q1 | How far along is each criterion of the done test? | `scopes[].progress[]`: `criterion`, `status` (`met` / `progress` / `failing` / `counted` / `unmeasured`), `detail` | Progress | answered, but mostly `unmeasured` (see Q1a) |
| Q1a | Which criteria have no measure? | `progress[].status == "unmeasured"` | each line reads "unmeasured: not known to be on track" | answered line by line; no count |
| Q1b | Has a date passed? | `scopes[].date`, `date_missed` | "date … MISSED" in the heading | answered (no open Goal has a date today: all are "when ready") |
| Q2 | What is stuck, and why will nothing start it? | `scopes[].stuck[]`: `kind` (the rule), `ref`, `url`, `reason`, `since`, `age_hours` | Stuck | answered |
| Q3 | What waits on me, and for how long? | `scopes[].waiting[]`: `kind`, `ref`, `url`, `reason`, `since`, `age_hours` | Waiting on the owner | answered, except the daily report's asks (see gaps) |
| Q4 | What was done on my authority? | `scopes[].authority[]` (`grant`, `call-in`), window `authority_hours` | On the owner's authority, last 24h | **wrong today**: always empty (#977) |
| Q5 | Who is on what? | none in `swarm trouble` | none in the trouble panel | **gap**: the desk's floor (`floor.py`) shows sessions, but not per Goal or Area |
| Q6 | What is happening outside my plan? | `outside.stuck`, `outside.waiting`, `outside.authority` | "Under no Goal or Area" | answered |

Spend is left out on purpose. GOV-0033 sets no engine total and the desk is public, so `spend_usd` and `spend` never appear on the Desk.

## What the record shows, question by question

**Q1. Progress.** 23 criteria across 5 Goals and 1 Area. 1 is `met` (M1 #683: "[daily] started the report for Thu 2026-11-12"), 1 is `counted` (M4 #686's acts), and **21 are `unmeasured`**. The panel is honest that they aren't known to be on track. It still can't answer the owner's real question, "is this Goal close?" Most criteria are "shown once" (GOV-0040), so the cheapest measure is a ticked box, which `trouble.criteria()` already reads as `met`. Two changes would fix it:
- The lead ticks a criterion's box when it is shown, with a link to the showing on the same line. The panel then shows `met` with that link as the `detail`, instead of "ticked".
- On the desk build, M4's acts criterion may read `unmeasured`. The desk builds trouble without the acts sync (#903), so `owner_days` is unread there. Worth a check in the fixture test.

**Q1a. Unmeasured.** Each line is labelled, but there is no count. Put the count in the Progress heading, in these words: **"Progress: 1 of 3 met · 2 unmeasured"**. The Commissions page's bar already counts met of total. Use the same count on both.

**Q2. Stuck.** All six rules and the fourth signal file here with a reason. Today: #903 under M3, and #953 and #954 under M6 #938, each `merged-issue-open`. #953 and #954 were flagged 25 minutes after their PRs merged. Those are real, not noise, because the merger's merges still leave issues open (#760 replay 2). The reason line answers "why nothing will start it" in plain words. Keep it.

**Q3. Waits on me.** Today: PR #964 and PR #947 under M6, both "the merger left it for the owner: … over [merger] max_changed_lines 500". Outside the plan: #751, #760, #908 and #909 untriaged (#751 and #760 for 34h), and the gov:question #936. Ages show. The gap: asks in the daily report aren't read (trouble.py's Limits), so an ask made only there doesn't show. The Bridge reads them (#928), so the two pages disagree.

**Q4. My authority.** The merger merged 13 PRs in the 24h before the reading, but every `authority[]` was empty. Cause: `gh` returns `app/productswarm-merger`, and `trouble.py` compares that with `productswarm-merger` (#977). Until that is fixed, the panel tells the owner the grants are unused, which is the opposite of the truth. The fixture test should use the login as `gh` returns it. Also not read: approved asks and `decide` calls under `jurisdictions.yml` (trouble.py's Limits). The panel should say so where it lists authority, in these words: **"Counts merges by the merger and call-ins by agents; approved asks and role decisions aren't counted yet."**

**Q5. Who is on what.** M3's criterion text lists it, and #760's four don't. `swarm trouble` has no session or role field except `quiet-session`, which shows only a hand-started session that has gone quiet. The desk's floor shows sessions, but not under the Goal or Area they serve. Proposed field: `scopes[].working[]`, with `role`, `ref`, `since` and `started_by` (`watch` or `hand`), filed under the Goal or Area by the same `goal_of()` rule. Proposed panel words: **"Working now: builder on #951 (since 21:40)"**, or **"Working now: nobody"**.

**Q6. Outside the plan.** Today: 1 stuck (#812) and 5 waiting. This is where untriaged issues land, so it answers "what isn't in my plan?" Keep it last.

## Gaps to open as Tasks under M3

1. #977: count the merger's merges (Q4). Opened.
2. `working[]` per scope (Q5).
3. A per-scope count in the Progress heading (Q1a).
4. A `detail` that links to the showing when a criterion is ticked (Q1).
5. The authority caveat line (Q4).
6. The daily report's asks under `waiting` (Q3), or a line saying they're on the Bridge.

## How we'll know it worked

- **Criterion 2's test.** One fixture state answers Q0–Q6: each question's field holds at least one item, plus a merger merge with the `app/` login, a stalled PR, a question waiting 7 days and a failed Area target. The test asserts that each question's panel words appear.
- **UX measure: "unmeasured share".** Unmeasured criteria over all open criteria, from `swarm trouble --json`. **Baseline: 21 of 23 (91%), 2026-11-12 22:08 UTC.** It should fall as Goals are shown and ticked. A Desk that is 91% "unmeasured" can't answer Q1 alone, whatever the layout.
- **UX measure: "went around the Desk".** Days the owner asked an agent a state question (an `Ask:` or a Claude Code session whose prompt is about state) per working week. No baseline yet: the record doesn't tag a state question. **Research question:** for one week, the owner adds `(state)` to any `Ask:` that asks about state. Cost: one word per ask.

-- designer (claude-opus-5-5)

