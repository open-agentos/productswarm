# Brief: the state questions the Desk must answer, per Goal and Area

**Question (#888):** what must the Desk answer alone, for each open Goal and Area, and which field of `swarm trouble --json` (rendered by the trouble panel, `desk.trouble_panel()`, #889/PR #902) answers each one today?
**For:** M3 (#685), criterion 1. **Written:** 2026-11-12. **By:** builder.

The owner's call-in asked the designer to write this Brief as a comment on #888. No designer comment had appeared by the time the owner made #888 `ready`, so the builder wrote it from the merged code. The designer or owner can correct any question with a follow-up PR.

## The point first

#760's four questions hold, and `swarm trouble --json` answers all four per Goal and Area. Two gaps remain:

1. **"Who is on what"**, which M3's own text lists, has no field. `swarm trouble` reads the running sessions only to flag quiet ones (rule 5), and never reports them.
2. **The panel isn't served.** `trouble_panel()` is merged but no Desk page calls it (PR #902, "Not in this PR"). Until a page does, none of these questions can be answered "from the Desk alone", even where the field exists.

Several questions are answered only in part. Each is marked below.

## How to read the table

Paths are into the dict `trouble.report()` returns (`swarm trouble --json`). `scopes[]` holds one entry per open Goal or Area the owner opened. `outside` has the same `stuck`/`waiting`/`authority` lists for items under no Goal or Area. Each item in those lists has `kind`, `ref`, `url`, `reason`, `since`, `age_hours`. "Panel" is the part of `trouble_panel()` that shows the field.

## The questions

| # | Question, per Goal and Area | Field today | Panel | Answered? |
|---|---|---|---|---|
| 1 | Which Goals and Areas are open, and what is each one for? | `scopes[].ref`, `.type`, `.title`, `.url` | scope heading | **Yes** |
| 2 | How does each criterion of its done test stand? | `scopes[].progress[]`: `criterion`, `status` (`met`, `progress`, `failing`, `counted`, `unmeasured`), `detail` | Progress | **Yes** |
| 3 | Which criteria are unmeasured? | `scopes[].progress[]` where `status == "unmeasured"` | Progress ("unmeasured: not known to be on track") | **Yes.** No separate count; the reader scans the list |
| 4 | Has its date passed? | `scopes[].date`, `scopes[].date_missed` | heading (MISSED) | **Yes** |
| 5 | What is stuck, why will nothing start it, and since when? | `scopes[].stuck[]`: `kind` is the rule (`changes-no-restart`, `merged-issue-open`, `waits-on-unplanned`, `unheard-command`, `conflict`, `quiet-session`, `stopped-no-issue`), `reason` says why nothing will start it, `since`, `age_hours` | Stuck | **Yes, for the seven rules.** A stall that fits none of them isn't flagged |
| 6 | What waits on the owner, and for how long? | `scopes[].waiting[]`: `kind` (`pr`, `question`), `reason`, `since`, `age_hours`; untriaged issues are always in `outside.waiting[]` (`kind: untriaged`) | Waiting on the owner | **Yes.** Not read: asks in the daily report, and `decide` calls under `jurisdictions.yml` (trouble.py "Limits"). A PR the merger hasn't judged at head yet isn't listed |
| 7 | What was done on the owner's authority, and when? | `scopes[].authority[]`: `kind` `grant` (merger merges under GOV-0027) or `call-in` (a swarm App's `Call in:`); window is `authority_hours` | On the owner's authority, last Nh | **In part.** Only merger merges and App call-ins. Not covered: issues the planner opens or closes under a Goal or Area (GOV-0031, GOV-0041), `[daily]` reports, `decide` calls, and any act older than the window |
| 8 | Who is on what? | none. `Data.sessions` is read for rule 5 only and isn't in the output | none | **No.** Gap |
| 9 | What has it spent? | `scopes[].spend_usd`; totals in `spend` | none | **In the JSON, not on the panel.** Reported only (GOV-0033) |
| 10 | What couldn't be read? | `errors[]` | "not read: …" | **Yes** |
| 11 | What is in trouble under no Goal or Area? | `outside.stuck[]`, `outside.waiting[]`, `outside.authority[]` | "Under no Goal or Area" | **Yes** |

Questions 1–7 and 11 are #760's four (2/3/4 progress, 5 stuck, 6 waiting, 7 authority) plus the "unmeasured" ask in #888, laid out per Goal and Area. Question 8 is from M3's own text ("who is on what"). Questions 9 and 10 are what the JSON already carries.

## What this confirms or corrects about #760's four

- **Confirmed:** progress per criterion, stuck with the reason nothing will start it, waiting on the owner with its age. The panel shows all three per scope.
- **Corrected, narrower than it reads:** "what was done on my authority" covers only merges and call-ins today (question 7). The panel heading says "last Nh", so it doesn't claim more, but the owner should not read an empty list as "nothing was done".
- **Added:** "who is on what" (question 8). M3's criterion text lists it, and nothing answers it yet.

## Gaps, for the planner to turn into Tasks if wanted

1. Serve the trouble panel on a Desk page (PR #902's "Not in this PR": running `swarm trouble` during the Desk build touches swarm.db and the host's token, so it may need an architecture or security question first).
2. Report who is on what: running sessions (hand-started and loop-started) with role, issue or PR, and start time, filed per Goal and Area.
3. Widen "on the owner's authority" past merges and call-ins, or say on the panel what it leaves out.
4. Show `spend_usd` on the panel (reported only, never flagged, GOV-0033).

M3's criterion 2 (a fixture test of this list) is partly met by `TroublePanelTest` (PR #902) for questions 2, 5 and 6. Questions 8 and the served page have no test because they have no code.
