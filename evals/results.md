# Eval results: the sampled PRs scored against the rubric

Stage B3 of v3 (#174). Each PR in `evals/data/sample.json` is scored at its merge head (`head_sha`) using the rubric in `evals/README.md` (#172). The builder scored it, not the reviewer, so the reviewer doesn't grade its own work. #175 adds the reviewer calibration and compares the result with the bar.

How it was scored: each PR's merge head was checked out in a temporary `git worktree`, and `python3 -m unittest discover -s launcher` and `-s dashboard` were run there. The diff came from `gh pr diff`, the issue's "Done when" from `sample.json`, and the PR body from `gh pr view`. Nothing was changed, reopened or commented on. All 20 PRs were scored in one run.

Evidence names a test and says whether it passes at the merge head, or cites a file and line at the merge head, or a PR body section.

## Summary

Reviewer verdict: the state of the last `productswarm-reviewer[bot]` review before merge. "(head)" means that review was at the merge head, and "(older)" means it was on an earlier commit. No review in the sample has an `Overstep:` finding.

| PR | Issue | Done when | Records | Eval verdict | Reviewer verdict | Reviewer blocked | Agreement |
|---|---|---|---|---|---|---|---|
| [#64](https://github.com/open-agentos/productswarm/pull/64) | #47 | 2 met | 1 followed | would approve | none | no | n/a (unreviewed) |
| [#65](https://github.com/open-agentos/productswarm/pull/65) | #48 | 2 met, 2 unclear | 3 followed | would approve | none | no | n/a (unreviewed) |
| [#70](https://github.com/open-agentos/productswarm/pull/70) | #49 | 3 met | 4 followed | would approve | none | no | n/a (unreviewed) |
| [#71](https://github.com/open-agentos/productswarm/pull/71) | #50 | 3 met | 3 followed | would approve | none | no | n/a (unreviewed) |
| [#72](https://github.com/open-agentos/productswarm/pull/72) | #51 | 2 met | 1 followed | would approve | COMMENTED (older) | no | agree |
| [#74](https://github.com/open-agentos/productswarm/pull/74) | #52 | 3 met | 4 followed | would approve | none | no | n/a (unreviewed) |
| [#77](https://github.com/open-agentos/productswarm/pull/77) | #76 | 1 met (see note) | 1 n/a | would approve | COMMENTED (head) | no | agree |
| [#100](https://github.com/open-agentos/productswarm/pull/100) | #84 | 3 met | 1 followed | would approve | COMMENTED (head) | no | agree |
| [#103](https://github.com/open-agentos/productswarm/pull/103) | #91 | 2 met | 4 followed | would approve | COMMENTED (head) | no | agree |
| [#104](https://github.com/open-agentos/productswarm/pull/104) | #90 | 5 met | 2 followed, 1 n/a | would approve | COMMENTED (head) | no | agree |
| [#116](https://github.com/open-agentos/productswarm/pull/116) | #112 | 2 met | 2 followed | would approve | COMMENTED (head) | no | agree |
| [#117](https://github.com/open-agentos/productswarm/pull/117) | #111 | 2 met | 1 followed | would approve | COMMENTED (head) | no | agree |
| [#120](https://github.com/open-agentos/productswarm/pull/120) | #113 | 5 met | 3 followed | would approve | APPROVED (head) | no | agree |
| [#139](https://github.com/open-agentos/productswarm/pull/139) | #121 | 2 met | none cited | would approve | APPROVED (head) | no | agree |
| [#143](https://github.com/open-agentos/productswarm/pull/143) | #132 | 4 met, 1 unclear | 1 followed | would approve | APPROVED (head) | no | agree |
| [#144](https://github.com/open-agentos/productswarm/pull/144) | #136 | 8 met | 2 followed, 1 n/a | would approve | APPROVED (head) | no | agree |
| [#152](https://github.com/open-agentos/productswarm/pull/152) | #148 | 3 met | 2 followed | would approve | APPROVED (older) | no | agree |
| [#153](https://github.com/open-agentos/productswarm/pull/153) | #147 | 6 met | 5 followed, 1 n/a | would approve | APPROVED (head) | no | agree |
| [#156](https://github.com/open-agentos/productswarm/pull/156) | #149 | 5 met | 4 followed | would approve | APPROVED (head) | no | agree |
| [#164](https://github.com/open-agentos/productswarm/pull/164) | #160 | 3 met | 8 followed | would approve | APPROVED (head) | no | agree |

Every PR closes exactly one issue. No PR has a scope finding.

## Totals

Counted as `evals/README.md` defines them. N is the number of sampled PRs whose reviewer verdict isn't `none`: **N = 15** (20 sampled; #64, #65, #70, #71 and #74 have no reviewer review).

| Total | Count |
|---|---|
| agree | 15 of 15 |
| eval blocks | 0 |
| reviewer blocks | 0 |
| false blocks | 0 |
| misses | 0 |
| unreviewed defects | 0 (outside N) |

The eval found **no `unmet` item and no `broken` record** anywhere in the sample. Under the README's extra condition, that means misses = 0 hasn't been tested. #175 reports this against the bar.

## Disagreements

None. On all 15 reviewed PRs, neither the eval nor the reviewer blocked.

## Other observations

These don't change any mark, but #175 may want them.

- **The dashboard suite failed at five merge heads.** At #116, #117, #120, #143 and #144, `python3 -m unittest discover -s dashboard` has 1 failure: `test_cap.LoadCapsTest.test_repo_manifest_sets_no_caps_by_default` expects no caps, but `swarm.toml` has had per-role caps since `90804c9`, a direct commit to `main` at 2026-11-03T10:30Z. None of these PRs caused it, and no "Done when" item asks for the whole dashboard suite to pass. #139 fixed it (#121). The reviewer approved #120, #143 and #144 at heads where this test failed. #120 touches `dashboard/`. The launcher suite passes at all 20 heads.
- **Five PRs were never reviewed** (#64, #65, #70, #71, #74). That is v1, merged as admin before the reviewer ran (as `governance/PHASE0.md` notes in #77).
- **Two reviews were not at the merge head.** At #72, the review at `b14116a` found an unmet item and a pagination bug, and the builder fixed both in `f129c5f`, the merge head. At #152, the approval was at `67bd9e0`.
- **#156 narrows its issue's "What".** #149's "What" asks for the "ended at cap" item at the top of the dashboard too. The PR keeps it in `swarm inbox` only and says why (the published page can't read local `watch.json`, and costs must not reach GitHub). The "Done when" items ask only for `swarm inbox`, so all are met.

## Calibration

Stage B4 of v3 (#175). This section explains the reviewer's calibration from the scores above, and checks the totals against the bar that the owner set on #172 (`evals/README.md`, "Pre-registered bar for C stage 2"). It decides nothing, and nothing outside this file changes.

### Causes of disagreement

There are **no disagreements to explain**: the eval and the reviewer agree on all 15 reviewed PRs. Each of the cause categories from #175 is counted, and every count is 0.

| Cause | Count |
|---|---|
| A rule in the role prompt says comment where the rubric says block | 0 |
| A "Done when" item the reviewer didn't check | 0 |
| A review at a head that wasn't the merge head | 0 |
| No review at all (unreviewed defect, outside N) | 0 |
| Other | 0 |
| **Total** | **0** |

Two of the 15 agreements come from a review that wasn't at the merge head (#72, #152). Both agree because the eval found nothing at the merge head. This doesn't show what the reviewer would have done there.

**The 15 reviews came from two different prompts.** `roles/reviewer.md` had no way to block until #117 (GOV-0011) merged at 2026-11-03T11:30:07Z. Before that, it said to post only `--comment`, and only an `Overstep:` finding went to the owner.

- **7 PRs were reviewed under the comment-only prompt:** #72, #77, #100, #103, #104, #116 and #117. The last reviews on #116 and #117 were posted at 11:28, before #117 merged. On these PRs the reviewer could block only with an `Overstep:` finding, and it found none. So "reviewer blocks = 0" on them is what the prompt required, not a calibration result.
- **8 PRs were reviewed under the stoplight prompt:** #120, #139, #143, #144, #152, #153, #156 and #164. All 8 are `APPROVED`, and the eval says `would approve` on all 8.

On no PR in the sample was the reviewer able to block, and also faced a defect the eval would block at the merge head. So the sample doesn't test the stoplight's "request changes" side at all.

### Against the bar

N = 15, so line 1 needs at least 13 of 15 (85% of 15 is 12.75, rounded up, per `evals/README.md`).

| Bar line | Owner's number | Measured | Result |
|---|---|---|---|
| 1. Agreement | at least 13 of 15 (85% of N, rounded up) | 15 of 15 | pass |
| 2. Misses | 0 | 0 | not tested (see below) |
| 3. False blocks | at most 2 | 0 | pass |
| Extra condition: the eval finds at least one `unmet` item or `broken` record | at least 1 | 0 | not met |

**Result: inconclusive, not passed.** The eval found no `unmet` item and no `broken` record anywhere in the sample, so under the README's extra condition line 2 hasn't been tested. Whether C stage 2 goes ahead is the owner's call.

#### How the reviewer could be shown to block a real defect

The README asks #175 to say how this could be shown. These are options for the owner. None has been started.

1. **A planted defect.** Open a non-draft PR that closes a throwaway issue and leaves one "Done when" item `unmet`. Let one loop-started reviewer pass run on it, record the review state, then close the PR unmerged. A pass means `CHANGES_REQUESTED`, or `COMMENTED` with an `Overstep:` finding. Planting a `broken` record as well, in a second PR, would test the records side separately.
2. **Replay real defects under the current prompt.** Two earlier heads in this sample had defects that the reviewer itself found while it could only comment (see cases 1 and 2 below): #72 at `b14116a`, where a "Done when" item was unmet, and #104 at `48ab1fd`, where `[build]` started a second builder on finished work. Running the current `roles/reviewer.md` against those heads would show whether the stoplight prompt now blocks them. These PRs are merged, so this needs a way to review a past head outside the normal loop.
3. **Wait for a real defect.** Re-run #173–#175 on a later sample that includes a PR where the eval blocks. This costs nothing, but has no end date.

### Inputs for a committee

#167 asks: "What should make the reviewer request changes rather than comment?" These are the cases from this sample that such a ruling would decide. Each is a real review. Cases 1 and 2 were reviewed under the comment-only prompt. The others were reviewed under the current stoplight prompt or still bear on it. This list convenes nothing and proposes no change to `roles/reviewer.md`. That would be a separate issue.

| # | PR, head | What the reviewer found | What it posted | What the case would decide |
|---|---|---|---|---|
| 1 | #72, `b14116a` (not the merge head) | "Done when" item 2 "not met yet" (the dry-run link was "To follow"). Also a minor bug: no `--paginate` | `COMMENTED` (comment-only prompt). Both were fixed by the merge head | An unmet "Done when" item that the builder can fix. The current prompt's "bugs … the builder can fix" seems to cover it, but nothing in the sample tests this |
| 2 | #104, `48ab1fd` (not the merge head) | A bug: `[build]` fires on a `ready` issue that an open PR already closes, confirmed by a live dry run. Also a minor point: `[build]` always starts `builder` | `COMMENTED` (comment-only prompt). The bug was fixed by `30d6f84`. The minor point became #108 | A behaviour bug that no "Done when" item names. The eval can't block it, because the rubric scores only "Done when" items and records |
| 3 | #103, `c008365` (the merge head) | `PRODUCT.md` presents open questions #101 and #102 as answered. Its Order line ("W2 waits on #88") contradicts its own design-decisions list | `COMMENTED` (comment-only prompt). Merged unchanged: lines 103, 124 and 126 at `c008365` | A factual error in a docs PR whose "Done when" items are all met. Should inaccuracy block when no "Done when" item covers it? |
| 4 | #120, #143, #144 (each at the merge head) | The dashboard suite has 1 failure (`test_repo_manifest_sets_no_caps_by_default`). The same failure is on `main`, so the PR didn't cause it | `APPROVED`, each noting the failure (#143 and #144 point to #121) | A pre-existing test failure on `main`. The prompt asks "do the tests pass?" without saying which tests, or whether a failure inherited from `main` counts |
| 5 | #120, `3a26b07` (the merge head) | `class RespondTest` comes after `unittest.main()`, so running the file directly skips 9 tests. `discover` runs them | `APPROVED`, as a note "no change needed" | A test layout fault that hides tests under one documented way of running them but not the other |
| 6 | #152, `67bd9e0` (not the merge head) and #153, `ac4bb04` | Once both merge, one test fails and `launcher/README.md` conflicts. Whichever merges second needs a rebase | `APPROVED` on both, with merge-order notes | A known break that appears only when two separately correct PRs are combined. Does it block either one, and does a rebased head need a new review? |
| 7 | #156, `70aa4ff` (the merge head) | The dashboard part of #149's Scope isn't built. "Done when" asks only for `swarm inbox` | `APPROVED`, calling it "the right call, not an overstep" | A PR that does less than its issue's Scope or "What", but meets every "Done when" item |
| 8 | #143, `40c0ec5` (the merge head) | Nothing. The eval marks one item `unclear`: a `[review]` trigger has no `swarm launch` command, so the item's wording can't be met literally | `APPROVED`, without mentioning the wording | A "Done when" item that can't be met as written. Does that block, or does a reasonable reading pass? |
| 9 | #104 at `30d6f84`, #116, #117 | The rubric passed | `COMMENTED`, because the prompt then still said comment-only | A gap between a merged ruling (GOV-0011) and a role prompt that hasn't caught up. Does the reviewer follow the ruling or the prompt? |

Cases 1 and 2 are the closest the sample comes to a miss: real defects that got a non-blocking review. Neither counts as one, because the eval scores only the merge head and both were fixed by then.

## Per PR

### #64: Launcher: swarm manifest and loader (closes #47)

Merge head `df8dbd2`. Reviewer: none.

| Done when | Mark | Evidence |
|---|---|---|
| `python3 -m unittest discover -s launcher` passes | met | 20 tests, OK at the merge head |
| A bad manifest (unknown role, unknown key, count 0) fails with a message that names the problem | met | `launcher/test_manifest.py`: `test_unknown_role_names_the_role`, `test_unknown_key_names_the_key`, `test_count_zero_negative_or_not_whole`, `test_cli` (prints `unknown role 'nobody'`). All pass |

| Record | Mark | Evidence |
|---|---|---|
| GOV-0005 | followed | The manifest is in `launcher/` and `swarm.toml`, outside `ops/` |

Scope: closes one issue, yes. Stays inside it, yes.

### #65: Launcher: swarm up / ls / stop (closes #48)

Merge head `074fcc5`. Reviewer: none.

| Done when | Mark | Evidence |
|---|---|---|
| With the default manifest, `swarm up` opens the expected sessions, each acting as its role's App | unclear | `test_calls_swarm_session_unchanged_with_model_session_id_and_opener` (passes) shows each window runs `ops/swarm-session <role>`, which sets the App. But no real `swarm up` was run: the PR's "Not verified here" section leaves that to the owner |
| `swarm ls` shows them within one heartbeat interval | unclear | `test_rows_join_heartbeat_with_launcher_state` (passes) covers the join. The PR says `ls` listed 4 hand-started sessions, but launcher-started ones weren't observed |
| `swarm stop` ends one, and the dashboard shows it `stopped` | met | `test_pid_chain_and_stop` (passes) ends a real process through the window command. The PR body's "Graceful stop: verified" section shows SIGTERM fires `SessionEnd`, which records `stopped` |
| Tests cover planning with a fake runtime; no test opens real sessions | met | `test_plan_is_the_shortfall_by_name`, `test_up_starts_everything_then_nothing`, `test_up_restarts_only_what_exited` and others use a fake runtime. All pass |

| Record | Mark | Evidence |
|---|---|---|
| GOV-0002 | followed | The heartbeat hook is unchanged. Sessions are tied to it by `--session-id` |
| GOV-0004 | followed | Nothing new is posted to GitHub. State is local under `~/.productswarm/launcher/` |
| GOV-0005 | followed | `ops/swarm-session` is called unchanged (`launcher/swarm.py`, `command()`) |

Scope: closes one issue, yes. Stays inside it, yes.

### #70: Launcher: swarm launch <role> --issue N (closes #49)

Merge head `a73141b`. Reviewer: none.

| Done when | Mark | Evidence |
|---|---|---|
| `swarm launch builder --issue N` starts a builder whose heartbeat shows #N as its current issue | met | `test_starts_with_the_issue_in_the_opener` and `test_opener_matches_the_heartbeat_working_on_rule` (passes; runs the opener through the hook's own regex) |
| A second launch on #N is refused while the first is live | met | `test_refused_while_a_live_session_has_the_issue`, `test_second_launch_refused_before_its_heartbeat_arrives`. Both pass |
| Tests cover the refusal rules against canned heartbeat data | met | Same tests plus `test_stopped_or_other_issue_sessions_dont_count`, `test_launcher_session_is_named_in_the_refusal`. All pass |

| Record | Mark | Evidence |
|---|---|---|
| GOV-0002 | followed | The hook is unchanged. The issue reaches the heartbeat through the opener text |
| GOV-0004 | followed | Nothing new is posted to GitHub |
| GOV-0005 | followed | Issue handoff (L3) as listed |
| GOV-0006 | followed | `--force` doesn't override the owner-added `ready` check (`test_force_does_not_override_issue_rules`, passes), and the PR flags its departure from the issue text |

Scope: closes one issue, yes. Stays inside it, yes. (The diff includes #65's commit because the branch was stacked; the L3 change is `a73141b`.)

### #71: Needs-you list: swarm inbox and the top of the dashboard (closes #50)

Merge head `ff96607`. Reviewer: none.

| Done when | Mark | Evidence |
|---|---|---|
| `swarm inbox` and the top of the dashboard show the same items in the same order | met | `dashboard/test_needs.py` `test_first_section_matches_the_list`. `launcher/test_swarm.py:365` compares `inbox_text()` with the page's `<ol class="inbox">` for the same data. All pass |
| Empty state says plainly that nothing is waiting | met | `dashboard/generate.py:287` `NEEDS_EMPTY = "Nothing is waiting on you."`. `test_empty` and `launcher/test_swarm.py:386` both pass |
| Tests cover the ordering with canned data | met | `test_order` (passes) |

| Record | Mark | Evidence |
|---|---|---|
| GOV-0002 | followed | `needs_you()` reads only `build()`'s model, never the local spool |
| GOV-0004 | followed | The page shows only public GitHub data |
| GOV-0005 | followed | The needs-you list (L5) as listed |

Scope: closes one issue, yes. Stays inside it, yes.

### #72: Reviewer runs by default and reviews each open PR once per push (closes #51)

Merge head `f129c5f`. Reviewer: COMMENTED at `b14116a` (older), no `Overstep:`.

| Done when | Mark | Evidence |
|---|---|---|
| The default manifest starts a reviewer | met | `launcher/test_manifest.py:139` `test_repo_manifest_runs_a_reviewer_by_default` (passes) |
| The dry run's reviews are linked from the PR | met | PR body "Dry run" section links review 5741681112 |

| Record | Mark | Evidence |
|---|---|---|
| GOV-0005 | followed | The reviewer runs by default (L6) |

Scope: closes one issue, yes. Stays inside it, yes.

### #74: Spend cap, warn only (closes #52)

Merge head `0ded27f`. Reviewer: none.

| Done when | Mark | Evidence |
|---|---|---|
| A session over its manifest cap shows as over cap in `swarm ls` and `swarm inbox` | met | `launcher/test_swarm.py` `test_over_cap_from_canned_tokens_in_ls_and_inbox`, `dashboard/test_cap.py` `test_in_needs_you_last_and_furthest_over_first`. Both pass |
| No code path stops a session automatically | met | `test_only_stop_signals_a_session` (passes) parses `swarm.py` and fails if any function other than `stop` signals |
| Tests use canned token counts | met | `dashboard/test_cap.py` and `test_over_cap_from_canned_tokens_in_ls_and_inbox` use canned tokens |

| Record | Mark | Evidence |
|---|---|---|
| GOV-0002 | followed | Caps come from the committed `swarm.toml`. No local data reaches the page |
| GOV-0004 | followed | Same as above |
| GOV-0005 | followed | Spend cap (L4) |
| GOV-0008 | followed | Warn only. See the `test_only_stop_signals_a_session` evidence above |

Scope: closes one issue, yes. Stays inside it, yes.

### #77: Phase 0 log: v1 launcher round (closes #76)

Merge head `e8944ed`. Reviewer: COMMENTED at head, no `Overstep:`.

#76 has no "Done when" section (`done_when` is null in `sample.json`). Its whole body is one ask, so that ask is scored as the one item.

| Done when | Mark | Evidence |
|---|---|---|
| Log #36's ruling, #41, #43–#46, #54, #57 and the v1 round's observations in `governance/PHASE0.md` | met | The diff fills in the #36 row, adds rows for #41, #43, #44, #45, #46, #54 and #57, and adds "Observations (2026-11-02, v1 launcher)" |

| Record | Mark | Evidence |
|---|---|---|
| GOV-0006 | n/a | Cited in the log text. The change is a log entry, not triage |

Scope: closes one issue, yes. Stays inside it, yes.

### #100: PRODUCT.md: mark v1 (local launcher) done (closes #84)

Merge head `9f5e337`. Reviewer: COMMENTED at head, no `Overstep:`.

| Done when | Mark | Evidence |
|---|---|---|
| The status line reads `v0 (swarm dashboard) done · v1 (local launcher) done` | met | `PRODUCT.md:3` in the diff |
| The v1 table gets a PR column | met | The diff adds a PR column: #64, #65, #70, #74, #71, #72 |
| No other content changes | met | The diff has only those two hunks |

| Record | Mark | Evidence |
|---|---|---|
| GOV-0005 | followed | v1 items match GOV-0005's list |

Scope: closes one issue, yes. Stays inside it, yes.

### #103: PRODUCT.md: add the v2 section (closes #91)

Merge head `c008365`. Reviewer: COMMENTED at head, no `Overstep:`.

| Done when | Mark | Evidence |
|---|---|---|
| `PRODUCT.md` has the v2 section, and its issue numbers match the open v2 issues | met | The diff adds `## v2: wake-up loop` with what it is, the four triggers, a W1 #89 / W2 #90 table, goals, non-goals and design questions. #89 had closed, and the row says "merged in #94", as the PR explains |
| Nothing outside `PRODUCT.md` changes | met | The PR changes only `PRODUCT.md` |

| Record | Mark | Evidence |
|---|---|---|
| GOV-0006 | followed | The triggers act only on owner-added labels |
| GOV-0007 | followed | #88 is cited as direction because it has no record |
| GOV-0008 | followed | Non-goal: no automatic stop |
| GOV-0009 | followed | The section's scope and triggers match GOV-0009 |

Scope: closes one issue, yes. Stays inside it, yes.

### #104: swarm watch: start sessions within the #88 limits (closes #90)

Merge head `30d6f84`. Reviewer: COMMENTED at head, no `Overstep:`.

| Done when | Mark | Evidence |
|---|---|---|
| Each trigger starts exactly one session, and a restart starts none | met | `launcher/test_watch.py` `test_each_trigger_starts_one_session_and_a_restart_starts_none` (passes) |
| The ceiling holds: an extra trigger waits, appears in `swarm inbox`, and starts once a loop-started session stops | met | `test_ceiling_holds_then_starts_in_order_when_a_slot_frees` (passes) checks the held lines in `inbox` and the start after `exit()` |
| A role with no `spend_cap_usd` is skipped, with the reason in `swarm inbox` | met | `test_a_role_with_no_cap_is_skipped_and_listed_until_it_has_one` (passes) |
| The loop never signals a session and never calls a GitHub write | met | `test_never_signals_and_only_reads_github` (passes) runs the real readers over a fake `gh`, and asserts no signals and no write flags |
| `launcher/README.md` documents `swarm watch` and its limits, citing the #88 record | met | `launcher/README.md:110` cites GOV-0010, the record for #88 |

| Record | Mark | Evidence |
|---|---|---|
| GOV-0007 | n/a | Cited for the `[record]` trigger, which this PR doesn't change |
| GOV-0008 | followed | No signals (the `test_never_signals_and_only_reads_github` evidence above) |
| GOV-0010 | followed | 5-minute interval, `max_live = 2`, capped roles only. `test_repo_manifest_has_the_limits_from_88` passes |

Scope: closes one issue, yes. Stays inside it, yes. `manifest.py` and `swarm.py` change only for the `[watch]` table and `by="watch"` entries.

### #116: roles/builder.md: respond to requested changes on own PR (closes #112)

Merge head `79fb7a7`. Reviewer: COMMENTED at head, no `Overstep:`.

| Done when | Mark | Evidence |
|---|---|---|
| `roles/builder.md` has the step and cites GOV-0011 | met | `roles/builder.md:9-19`: "Responding to requested changes", which reads, responds, doesn't widen scope, leaves `Overstep:` findings to the owner and stops. It cites GOV-0011 at lines 11 and 18 |
| "Never merge or approve PRs" stays in the builder prompt | met | `roles/builder.md:7` |

| Record | Mark | Evidence |
|---|---|---|
| GOV-0009 | followed | Step 5 relies on the PR-head trigger and doesn't ask for a review |
| GOV-0011 | followed | The builder acts only on "changes requested" at the head, and leaves `Overstep:` findings to the owner |

Scope: closes one issue, yes. Stays inside it, yes.

### #117: Reviewer posts request-changes / comment / approve, with rubric lines (closes #111)

Merge head `8471704`. Reviewer: COMMENTED at head, no `Overstep:`.

| Done when | Mark | Evidence |
|---|---|---|
| `roles/reviewer.md` and CLAUDE.md say the above, and cite GOV-0011 | met | `roles/reviewer.md:7` (approve means the rubric passed) and `:21-32` (the three states, rubric lines in the exact form, the approval text). `CLAUDE.md:10`. All cite GOV-0011 |
| No other role prompt changes | met | The PR changes only `CLAUDE.md` and `roles/reviewer.md` |

| Record | Mark | Evidence |
|---|---|---|
| GOV-0011 | followed | Stoplight states. Approve isn't a merge decision. An `Overstep:` gets `--comment` |

Scope: closes one issue, yes. Stays inside it, yes.

### #120: swarm watch: [respond] starts the builder on requested changes, at most 2 rounds (closes #113)

Merge head `3a26b07`. Reviewer: APPROVED at head.

| Done when | Mark | Evidence |
|---|---|---|
| `CHANGES_REQUESTED` at the head starts one builder, and a restart starts none | met | `launcher/test_watch.py` `test_changes_requested_at_head_starts_one_builder_and_a_restart_starts_none` (passes) |
| The third request lists the PR as needing the owner and starts nothing | met | `test_second_round_starts_then_third_request_lists_the_pr_and_starts_nothing`, `dashboard/test_needs.py` `test_third_request_needs_the_owner`. Both pass |
| Authority: fail starts nothing and lists the PR | met | `test_overstep_starts_nothing_and_lists_the_pr`, `test_overstep_at_head_needs_the_owner_whatever_the_state`. Both pass |
| A `COMMENTED` or `APPROVED` review starts nothing | met | `test_comment_or_approve_starts_nothing`, `test_comment_or_approve_is_not_the_owners`. Both pass |
| `launcher/README.md`'s trigger table gains `[respond]` and cites GOV-0011 | met | `launcher/README.md:105` |

| Record | Mark | Evidence |
|---|---|---|
| GOV-0009 | followed | Start-only. The new trigger only starts sessions |
| GOV-0010 | followed | `launcher/README.md:112`: `[respond]` counts toward `max_live` and needs a cap |
| GOV-0011 | followed | At most 2 rounds, then the owner. Authority fail goes to the owner |

Scope: closes one issue, yes. Stays inside it, yes. See "Other observations" for the unrelated dashboard test failure at this head.

### #139: test_cap and launcher README: swarm.toml sets per-role spend caps (closes #121)

Merge head `9a8cbbf`. Reviewer: APPROVED at head.

| Done when | Mark | Evidence |
|---|---|---|
| The test checks that the repo manifest's caps load (or asserts the current values) | met | `dashboard/test_cap.py` `test_repo_manifest_caps_load` (passes). The dashboard suite is OK at this head |
| The README line describes the caps as set | met | The `launcher/README.md` "Cap required" bullet now says every role sets a cap (since #110) |

No records cited.

Scope: closes one issue, yes. Stays inside it, yes.

### #143: swarm watch: only loop-started reviewers keep [review] triggers quiet (closes #132)

Merge head `40c0ec5`. Reviewer: APPROVED at head.

| Done when | Mark | Evidence |
|---|---|---|
| With an idle owner-started reviewer live, a new PR head produces a `[review]` trigger, and `--dry-run` prints its `swarm launch` command | unclear | `test_an_idle_owner_started_reviewer_doesnt_keep_reviews_quiet` (passes): the trigger fires and dry-run prints `-> would start a reviewer pass`. A review trigger has no `swarm launch` command (`launcher/watch.py:181`, `command="a reviewer pass"`), so the item's wording can't be met literally |
| With a loop-started reviewer live, the `[review]` trigger stays quiet | met | `test_a_live_loop_started_reviewer_keeps_reviews_quiet` (passes) |
| `triggers()` and `refusal()` use the same rule | met | Both go through the reviewer check in `launcher/watch.py:250-252`. `test_refusal_waits_only_for_a_loop_started_reviewer` and `test_an_owner_started_reviewer_doesnt_hold_reviews` pass |
| The `watch.py` docstring and `launcher/README.md` describe the new rule | met | `launcher/watch.py:32-35`, plus the `launcher/README.md` "Reviews" bullet |
| Tests cover both cases | met | The four tests above |

| Record | Mark | Evidence |
|---|---|---|
| GOV-0010 | followed | Owner-started sessions stay out of the loop's counts, which is the reason for the rule |

Scope: closes one issue, yes. Stays inside it, yes. See "Other observations" for the unrelated dashboard test failure at this head.

### #144: swarm watch: hold a [build] while a live builder or open PR shares its GOV record (closes #136)

Merge head `9fe7555`. Reviewer: APPROVED at head.

| Done when | Mark | Evidence |
|---|---|---|
| Two new `[build]`s sharing a GOV id in one check: the first starts and the second is held | met | `test_two_new_builds_sharing_an_id_in_one_check_start_one_and_hold_the_other` (passes) |
| Held while a live builder (heartbeat, or launcher entry with no heartbeat yet) shares an id; starts after it stops | met | `test_a_heartbeat_builder_started_by_hand_holds_until_it_stops`, `test_a_launcher_builder_with_no_heartbeat_yet_holds`. Both pass |
| Held while an open PR, draft or not, closes a sharing issue; starts once it's merged or closed | met | `test_an_open_pr_holds_draft_or_not_until_it_closes` (passes; subtests for draft and not) |
| No shared id, no id, or an id only in the body runs side by side | met | `test_no_shared_id_or_no_id_or_an_id_only_in_the_body_runs_side_by_side` (passes) |
| `[respond]`, `[review]`, `[record]`, `[answer]` are never held | met | `test_review_record_and_answer_are_never_held`, `test_respond_is_never_held`. Both pass |
| The hold shows in `swarm inbox` with its reason | met | `test_the_reason_names_every_builder_and_pr_it_waits_on` (passes) asserts against `self.inbox()` (`launcher/test_watch.py:692`) |
| The `watch.py` docstring and `launcher/README.md` describe the rule | met | `launcher/watch.py:48-54`, `launcher/README.md:137-141` |
| Tests cover each case; `triggers()` stays pure | met | The tests above, plus `test_overlap_is_pure` (passes) |

| Record | Mark | Evidence |
|---|---|---|
| GOV-0006 | n/a | Cited for the owner's direction on #127, which isn't a ruling. The change doesn't touch labels |
| GOV-0010 | followed | The hold is listed in `swarm inbox` the same way as GOV-0010's ceiling holds |
| GOV-0011 | followed | `[respond]` is never held |

Scope: closes one issue, yes. Stays inside it, yes. See "Other observations" for the unrelated dashboard test failure at this head.

### #152: swarm watch: Stop hook keeps loop-started runs going until their role is done (closes #148)

Merge head `5770e72`. Reviewer: APPROVED at `67bd9e0` (older).

| Done when | Mark | Evidence |
|---|---|---|
| Tests for each role's done-condition, each "also counts as done" case, the `stop_hook_active` guard, the N-block guard and a failed GitHub read, on canned data | met | `launcher/test_stophook.py`: `BuilderTest`, `RespondTest`, `ReviewerTest`, `DocsTest`, `OtherRolesTest` (role conditions, plus a gov question, `ready` not added by the owner, a closed issue or an existing PR counting as done); `GuardTest.test_stop_hook_active_allows`, `test_allows_after_max_blocks`, `test_failed_github_read_allows`. All pass with a `FakeGitHub` |
| Owner-started worktrees get no Stop hook (test) | met | `SettingsTest.test_owner_started_worktrees_get_no_stop_hook`, `test_launch_worktrees_get_no_stop_hook`. Both pass |
| `launcher/README.md` documents the done-conditions | met | `launcher/README.md:190` "Done-conditions: the Stop hook on runs it starts" |

| Record | Mark | Evidence |
|---|---|---|
| GOV-0006 | followed | A `ready` not added by the owner counts as done (`test_ready_not_added_by_the_owner_is_done`) |
| GOV-0012 | followed | The hook allows the stop on a failed read and after N blocks, so the budget stays the bound |

Scope: closes one issue, yes. Stays inside it, yes.

### #153: swarm watch: start loop-started runs headless (closes #147)

Merge head `ac4bb04`. Reviewer: APPROVED at head.

| Done when | Mark | Evidence |
|---|---|---|
| `swarm watch --dry-run` prints the full headless command for each trigger, with every flag | met | `test_dry_run_prints_the_full_headless_command_under_each_trigger` (passes) |
| `swarm up` and `swarm launch` commands are byte-for-byte unchanged | met | `test_up_and_launch_commands_are_byte_for_byte_unchanged` (passes). The existing tests pass too |
| `command()` with `by="watch"` tests: each flag, budget from `spend_cap_usd`, `max_turns` from `swarm.toml` | met | `test_a_run_swarm_watch_starts_is_headless`, `test_headless_budget_and_turns_come_from_the_entry`, `test_deny_patterns_cover_merge_and_label_edits`, `test_each_run_is_headless_with_its_roles_budget_and_the_turn_ceiling`. All pass |
| `manifest.py` tests for `max_turns` missing, zero, negative, non-integer | met | `test_max_turns_must_be_a_positive_whole_number`, `test_max_turns_missing_is_fine_for_up_but_not_for_watch`. Both pass |
| Docstrings and `launcher/README.md` describe headless runs | met | The PR updates the `swarm.py`, `watch.py` and `manifest.py` docstrings and adds a README "Headless runs" section |
| The heartbeat still records `started` and `stopped`; the PR says how this was checked | met | PR body section "Heartbeat `started` / `stopped` for a headless run" |

| Record | Mark | Evidence |
|---|---|---|
| GOV-0006 | followed | Label edits are denied (`--disallowedTools`) |
| GOV-0007 | n/a | Cited for the #125 record. GOV-0014 merged at 13:14Z, before this PR at 13:15Z |
| GOV-0010 | followed | `max_turns` is in `swarm.toml` for the owner to set |
| GOV-0011 | followed | `gh pr merge` is denied |
| GOV-0012 | followed | `--max-budget-usd` from the role's cap, plus `--max-turns`. A run with neither never starts (`test_a_watch_run_with_no_budget_or_ceiling_never_starts`) |
| GOV-0013 | followed | `--permission-mode auto` plus the deny patterns |

Scope: closes one issue, yes. Stays inside it, yes.

### #156: swarm watch: record each headless run's cost and ending (closes #149)

Merge head `70aa4ff`. Reviewer: APPROVED at head.

| Done when | Mark | Evidence |
|---|---|---|
| Tests use canned result JSON for each ending: success, budget, turns, error, missing or unreadable file | met | `test_success_is_done`, `test_budget_reached_is_at_cap`, `test_turns_reached_is_at_cap`, `test_other_error_is_error_with_its_messages`, `test_missing_file_is_no_result`, `test_unreadable_or_partial_file_is_no_result`. All pass |
| `swarm inbox` shows "ended at cap"; `swarm ls` or `inbox` shows each cost | met | `test_inbox_lists_a_run_that_ended_at_cap_with_its_ref_and_cost_and_every_cost` (passes) |
| Nothing new reaches GitHub (test or note) | met | The PR extends `test_never_signals_and_only_reads_github` to assert no `gh` argument carries the cost or ending (passes). There's also a PR body note |
| `launcher/README.md` describes the record | met | README section "How each run ended" |
| Check the JSON fields for budget and turns against the headless docs and cite them | met | PR body "How endings map" cites `SDKResultMessage` (`error_max_budget_usd`, `error_max_turns`) and three real runs |

| Record | Mark | Evidence |
|---|---|---|
| GOV-0002 | followed | Cost stays in local `watch.json` |
| GOV-0003 | followed | Nothing is added to the tracking-issue comments |
| GOV-0004 | followed | Nothing new is public |
| GOV-0012 | followed | An ended-at-cap trigger stays done and isn't restarted by the loop (`test_each_ending_is_recorded_against_its_trigger_and_nothing_restarts`) |

Scope: closes one issue, yes. Stays inside it, yes. See "Other observations" for the dashboard item.

### #164: PRODUCT.md: bring the v2 section up to date (closes #160)

Merge head `eff6053`. Reviewer: APPROVED at head.

| Done when | Mark | Evidence |
|---|---|---|
| The v2 section matches what's on `main` and cites GOV-0009 to GOV-0014 | met | At the merge head, the v2 section cites each of GOV-0009 through GOV-0014. Its tables list the merged #94, #104, #116, #117, #120, #143, #144, #152, #153 and #156. That section is unchanged on `main` today |
| Nothing in it contradicts an in-force ruling | met | Triggers, limits, headless runs and non-goals match GOV-0009 to GOV-0014. #127 is marked as direction, not a ruling (GOV-0006) |
| Only `PRODUCT.md` changes | met | The PR changes only `PRODUCT.md` |

| Record | Mark | Evidence |
|---|---|---|
| GOV-0006, GOV-0008 to GOV-0014 | followed (each) | The text restates each ruling and doesn't contradict any |

Scope: closes one issue, yes. Stays inside it, yes.
