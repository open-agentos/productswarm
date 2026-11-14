# Effort review: the owner's pass on the labelled set

Edit the four lines under each PR, then run `python3 classify/effort_data.py apply`.

- `label:` one of capability, upkeep, governance, knowledge.
- `fix:` `no`, or `#N` when the PR fixes PR #N, merged in the 14 days before it
  (`yes` if you don't know N).
- `hard:` blank, or the boundary rule this PR tests: feature-and-fix, role-prompt-capability, tests-only, ruling-implementation, brief-for-capability.
  A PR tagged `hard` moves to the test split.
- `reviewed:` `yes` makes your label and fix gold (`labelled_by: owner`). Leave it `no` and the
  draft stays a draft, which never counts.

Every test item needs `reviewed: yes` (#1011). Dev items are optional. The draft line is the
model's guess and its evidence: it is there to save time, not to agree with.

# Test split: 75 PRs, 0 reviewed

## pr-17 · test · 2026-W45

[#17](https://github.com/open-agentos/productswarm/pull/17) GOV-0002: Heartbeat capture rules  
Linked issue: #15 GOV-Q: What may a heartbeat event capture?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0002-heartbeat-capture.md  
> Ruling on #15, recording the owner's decision from the comment on #15 and the follow-up answers. Merging this PR ratifies it. **Captured:** schema version, timestamp, session id, repo, role, model, event type, issue/PR/gov number, nullable cost in USD, token counts and tool names (names only). **Pro …

Draft: governance, fix no. "Ruling on #15, recording the owner's decision from the comment on #15 and the follow-up answers. Merging this PR ratifies it."

label: governance
fix: no
hard:
reviewed: no

## pr-18 · test · 2026-W45

[#18](https://github.com/open-agentos/productswarm/pull/18) GOV-0003: Heartbeat event storage (interim)  
Linked issue: #14 GOV-Q: Where should heartbeat events be stored?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0003-heartbeat-storage.md  
> Ruling on #14, recording the owner's decision in the comment on #14 (option 4). Merging this PR ratifies it. - Each session's role App opens one tracking issue and posts each event as a JSON comment. - Prompt text stays in the local spool only, per GOV-0002. - Tracking issues never carry `status:` o …

Draft: governance, fix no. "Ruling on #14, recording the owner's decision in the comment on #14 (option 4). Merging this PR ratifies it."

label: governance
fix: no
hard:
reviewed: no

## pr-24 · test · 2026-W45

[#24](https://github.com/open-agentos/productswarm/pull/24) Heartbeat: Claude Code hook that emits session events  
Linked issue: #3 Heartbeat: Claude Code hook that emits session events  
Paths touched (5): .gitignore, heartbeat/README.md, heartbeat/hook.py, heartbeat/install.py, heartbeat/test_hook.py  
> Closes #3 ## What - `heartbeat/hook.py`: the hook. Stdlib Python only. - `heartbeat/install.py`: the one step to turn it on (`python3 heartbeat/install.py`). It writes the hooks into `.claude/settings.local.json`, which is now in `.gitignore`. Running it twice is harmless; `--uninstall` removes only …

Draft: capability, fix no. "Title: Heartbeat: Claude Code hook that emits session events"

label: capability
fix: no
hard:
reviewed: no

## pr-27 · test · 2026-W45

[#27](https://github.com/open-agentos/productswarm/pull/27) Dashboard: generator that renders sessions, PRs and gov questions  
Linked issue: #4 Dashboard: generator that renders sessions, PRs and gov questions  
Paths touched (4): .gitignore, dashboard/README.md, dashboard/generate.py, dashboard/test_generate.py  
> Closes #4 ## What `dashboard/generate.py` renders the swarm dashboard as one static HTML file: - **Sessions:** role, model, current issue, last activity and status (blocked / active / idle / stopped). Live sessions first, blocked at the top; stopped ones are folded away. - **Open PRs** with the issu …

Draft: capability, fix no. "`dashboard/generate.py` renders the swarm dashboard as one static HTML file:"

label: capability
fix: no
hard:
reviewed: no

## pr-39 · test · 2026-W45

[#39](https://github.com/open-agentos/productswarm/pull/39) GOV-0004: GOV-0002 and GOV-0003 hold for a public repo  
Linked issue: #36 GOV-Q: Do GOV-0002 and GOV-0003 still hold now that the repo is public?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0004-heartbeat-public-repo.md  
> Closes #36 Records the owner's ruling on #36 (option 1): GOV-0002 and GOV-0003 stay in force as written now that the repo is public. Merging ratifies it. 🤖 Generated with [Claude Code](https://claude.com/claude-code)

Draft: governance, fix no. "Records the owner's ruling on #36 (option 1): GOV-0002 and GOV-0003 stay in force as written now that the repo is public."

label: governance
fix: no
hard:
reviewed: no

## pr-42 · test · 2026-W45

[#42](https://github.com/open-agentos/productswarm/pull/42) GOV-0005: v1 is a lightweight local launcher  
Linked issue: #41 GOV-Q: Should v1 be a lightweight local launcher for starting, assigning and stopping sessions?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0005-v1-local-launcher.md  
> Closes #41 Records the owner's ruling on #41 (option 1): v1 is the local launcher scoped as L1–L6. Scope only; the design questions the planner listed are separate. Merging ratifies it. 🤖 Generated with [Claude Code](https://claude.com/claude-code)

Draft: governance, fix no. "Records the owner's ruling on #41 (option 1): v1 is the local launcher scoped as L1–L6."

label: governance
fix: no
hard:
reviewed: no

## pr-60 · test · 2026-W45

[#60](https://github.com/open-agentos/productswarm/pull/60) GOV-0008: v1 spend cap is warn-only  
Linked issue: #46 GOV-Q: May the launcher stop a session that passes its spend cap without the owner?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0008-spend-cap-warn-only.md  
> Ruling PR for #46, written per GOV-0007 from the owner's answer ("Option 1 for v1"). The question had no draft record, so the record is built from `GOV-0000-template.md`. `gov:ruled` and `ready` were both added by @mattmcalister (checked in the issue's events, per GOV-0006). The question needs a rec …

Draft: governance, fix no. "Ruling PR for #46, written per GOV-0007 from the owner's answer ("Option 1 for v1")."

label: governance
fix: no
hard:
reviewed: no

## pr-64 · test · 2026-W45

[#64](https://github.com/open-agentos/productswarm/pull/64) Launcher: swarm manifest and loader (L1)  
Linked issue: #47 Launcher: swarm manifest and loader  
Paths touched (4): launcher/README.md, launcher/manifest.py, launcher/test_manifest.py, swarm.toml  
> Closes #47 ## What - **`swarm.toml`** at the repo root, per the owner's answer on #44 (option 1: TOML, stdlib `tomllib`). By default it runs one session each of planner, builder, reviewer and docs, with no spend caps (#45). L6 will tune the reviewer default. - **`launcher/manifest.py`** is a stdlib- …

Draft: capability, fix no. "Running `python3 launcher/manifest.py` prints what the manifest would start."

label: capability
fix: no
hard:
reviewed: no

## pr-71 · test · 2026-W45

[#71](https://github.com/open-agentos/productswarm/pull/71) Needs-you list: swarm inbox and the top of the dashboard (L5)  
Linked issue: #50 Launcher: "needs you" list in swarm inbox and at the top of the dashboard  
Paths touched (6): dashboard/README.md, dashboard/generate.py, dashboard/test_needs.py, launcher/README.md, launcher/swarm.py, launcher/test_swarm.py  
> Closes #50 ## What - **`needs_you(model)` in `dashboard/generate.py`** is the one function that builds the list. It reads only `build()`'s model, which comes from public GitHub data, never the local spool (GOV-0002, GOV-0004). Items, most urgent first: 1. sessions blocked on a `gov:question`, longes …

Draft: capability, fix no. "The dashboard shows it as its first section, "Needs you (N)", above the existing count tiles."

label: capability
fix: no
hard:
reviewed: no

## pr-104 · test · 2026-W45

[#104](https://github.com/open-agentos/productswarm/pull/104) swarm watch: start sessions within the #88 limits  
Linked issue: #90 v2 W2: `swarm watch` starts sessions, within the limits from #88  
Paths touched (6): launcher/README.md, launcher/manifest.py, launcher/swarm.py, launcher/test_watch.py, launcher/watch.py, swarm.toml  
> Closes #90 `launcher/swarm watch` without `--dry-run` now starts one fresh session (a new Terminal window, as `swarm launch` makes) for each new trigger from #89, within the limits the owner chose on #88 (option 1). ## What changed - **`swarm.toml` gets a `[watch]` table** with `interval_minutes = 5 …

Draft: capability, fix no. "`launcher/swarm watch` without `--dry-run` now starts one fresh session (a new Terminal window, as `swarm launch` makes) for each new trigger from #89"

label: capability
fix: no
hard:
reviewed: no

## pr-106 · test · 2026-W45

[#106](https://github.com/open-agentos/productswarm/pull/106) GOV-0010: spend limits for swarm watch (#88)  
Linked issue: #88 GOV-Q: What interval, concurrency ceiling and cap rule should limit the sessions `swarm watch` starts?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0010-swarm-watch-spend-limits.md  
> Closes #88 Ruling PR per GOV-0007. The owner answered "Option 1" on #88 and has since asked for a record. Adds `governance/decisions/GOV-0010-swarm-watch-spend-limits.md` and its `INDEX.md` row. There was no draft record on #88, so I wrote this one from the question and the owner's answer, using `GO …

Draft: governance, fix no. "Ruling PR per GOV-0007. The owner answered "Option 1" on #88 and has since asked for a record. Adds `governance/decisions/GOV-0010-swarm-watch-spend-limits.md` and its `INDEX.md` row."

label: governance
fix: no
hard:
reviewed: no

## pr-107 · test · 2026-W45

[#107](https://github.com/open-agentos/productswarm/pull/107) GOV-0011: bounded reviewer→builder review loop (#105)  
Linked issue: #105 GOV-Q: Should review states drive a bounded reviewer→builder loop in swarm watch (request-changes triggers the builder, 2 rounds, then the owner)?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0011-bounded-review-loop.md  
> Closes #105 Ruling PR per GOV-0007. The owner answered "Option 1" on #105 and has since asked for a record. Adds `governance/decisions/GOV-0011-bounded-review-loop.md` and its `INDEX.md` row. There was no draft record on #105, so I wrote this one from the question as edited (the planner's 09:47 comm …

Draft: governance, fix no. "Ruling PR per GOV-0007. The owner answered "Option 1" on #105 and has since asked for a record."

label: governance
fix: no
hard:
reviewed: no

## pr-110 · test · 2026-W45

[#110](https://github.com/open-agentos/productswarm/pull/110) swarm.toml: per-role spend caps for swarm watch  
Linked issue: none  
Paths touched (1): swarm.toml  
> Sets `spend_cap_usd` on every role so `swarm watch` can start sessions. Under GOV-0010 (#88) it starts only roles with a cap and skips the rest. | Role | Cap | Observed per session so far | |---|---|---| | planner | $5 | ~$0.6–$3 | | docs | $5 | ~$0.5–$1 | | reviewer | $5 | ~$0.3–$1.2 | | builder |  …

Draft: capability, fix no. "Sets `spend_cap_usd` on every role so `swarm watch` can start sessions."

label: capability
fix: no
hard:
reviewed: no

## pr-116 · test · 2026-W45

[#116](https://github.com/open-agentos/productswarm/pull/116) roles/builder.md: respond to requested changes on own PR  
Linked issue: #112 GOV-0011 R2: builder responds to requested changes on its own PR  
Paths touched (1): roles/builder.md  
> Closes #112 Adds a "Responding to requested changes" section to `roles/builder.md`, per GOV-0011 part 2: - acts only when the latest `productswarm-reviewer[bot]` review at the PR's current head is "changes requested"; - pushes fixes inside the PR's issue, or replies where it disagrees; - never widen …

Draft: governance, fix no. "Adds a "Responding to requested changes" section to `roles/builder.md`, per GOV-0011 part 2:"

label: governance
fix: no
hard: role-prompt-capability
reviewed: no

## pr-117 · test · 2026-W45

[#117](https://github.com/open-agentos/productswarm/pull/117) Reviewer posts request-changes / comment / approve, with rubric lines (GOV-0011 R1)  
Linked issue: #111 GOV-0011 R1: reviewer posts request-changes / comment / approve, with rubric lines  
Paths touched (2): CLAUDE.md, roles/reviewer.md  
> Closes #111 Per GOV-0011, first of three (R1 → #112 → #113). ## What changed - **`roles/reviewer.md` step 4:** one state per review, as a stoplight: - `--request-changes` for bugs or scope problems the builder can fix; - `--comment` for notes needing no change, and for any review with an `Overstep:` …

Draft: capability, fix no. "`--approve` only when all three rubric items pass at this head."

label: capability
fix: no
hard: role-prompt-capability
reviewed: no

## pr-135 · test · 2026-W45

[#135](https://github.com/open-agentos/productswarm/pull/135) GOV-0012: runs swarm watch starts end at their spend cap  
Linked issue: #126 GOV-Q: Should runs that swarm watch starts have a hard budget (--max-budget-usd from spend_cap_usd)?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0012-loop-hard-budget.md  
> Ruling PR for the `gov:question` #126 (per GOV-0007). The owner answered **"Option 2"** in a comment on #126. Adds `governance/decisions/GOV-0012-loop-hard-budget.md` and its row in `governance/INDEX.md`. ## Ruling For runs that `swarm watch` starts, the role's `spend_cap_usd` becomes `--max-budget- …

Draft: governance, fix no. "Ruling PR for the `gov:question` #126 (per GOV-0007). The owner answered **"Option 2"** in a comment on #126."

label: governance
fix: no
hard:
reviewed: no

## pr-139 · test · 2026-W45

[#139](https://github.com/open-agentos/productswarm/pull/139) test_cap and launcher README: swarm.toml sets per-role spend caps  
Linked issue: #121 test_cap and launcher/README.md still assume swarm.toml sets no spend caps (stale since #110)  
Paths touched (2): dashboard/test_cap.py, launcher/README.md  
> Closes #121 Since #110, `swarm.toml` sets `spend_cap_usd` on every role, which left two things stale on `main`: - `dashboard/test_cap.py`: `test_repo_manifest_sets_no_caps_by_default` asserted `load_caps() == {}` and failed. It is now `test_repo_manifest_caps_load`, which checks that `load_caps()` m …

Draft: upkeep, fix no. "`dashboard/test_cap.py`: `test_repo_manifest_sets_no_caps_by_default` asserted `load_caps() == {}` and failed."

label: upkeep
fix: no
hard: tests-only
reviewed: no

## pr-140 · test · 2026-W45

[#140](https://github.com/open-agentos/productswarm/pull/140) GOV-0013: headless runs swarm watch starts use auto mode with explicit denies  
Linked issue: #131 GOV-Q: How should headless runs that swarm watch starts get tool permissions?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0013-headless-run-permissions.md  
> Ruling PR for #131, per GOV-0007. The owner answered "Option 3" in a comment, then added `gov:ruled` and `ready`. `security` is `always_one_way`, so it needs a record. Adds `governance/decisions/GOV-0013-headless-run-permissions.md` and its row in `governance/INDEX.md`. ## How the record differs fro …

Draft: governance, fix no. "Ruling PR for #131, per GOV-0007. The owner answered "Option 3" in a comment, then added `gov:ruled` and `ready`."

label: governance
fix: no
hard:
reviewed: no

## pr-143 · test · 2026-W45

[#143](https://github.com/open-agentos/productswarm/pull/143) swarm watch: only loop-started reviewers keep [review] triggers quiet  
Linked issue: #132 swarm watch: only reviewers the loop started keep [review] triggers quiet  
Paths touched (3): launcher/README.md, launcher/test_watch.py, launcher/watch.py  
> Closes #132 ## What changes `reviewers()` in `launcher/watch.py` now counts only reviewers that `swarm watch` started: live launcher entries with `by == "watch"` and `role == "reviewer"`. One counts while it has no heartbeat yet, or while its heartbeat isn't `stopped`. Reviewers the owner started (` …

Draft: upkeep, fix no. "Reviewers the owner started (`swarm up`, `swarm launch`) no longer keep `[review]` triggers quiet."

label: upkeep
fix: no
hard:
reviewed: no

## pr-185 · test · 2026-W45

[#185](https://github.com/open-agentos/productswarm/pull/185) v3 B5: swarm cost prints cost per PR from watch.json (local only)  
Linked issue: #176 v3 B5: swarm cost prints cost per merged PR from watch.json (local only)  
Paths touched (5): launcher/README.md, launcher/swarm, launcher/swarm.py, launcher/test_cost.py, launcher/watch.py  
> Closes #176 ## What `launcher/swarm cost [--repo owner/name]` reads the `runs` that `swarm watch` recorded in `watch.json`. It groups each run's `cost_usd` by the PR the run served: - for `[review]` and `[respond]`, the trigger's PR; - for `[build]`, `[record]` and `[answer]`, the PR that closes the …

Draft: capability, fix no. "`launcher/swarm cost [--repo owner/name]` reads the `runs` that `swarm watch` recorded in `watch.json`."

label: capability
fix: no
hard:
reviewed: no

## pr-226 · test · 2026-W45

[#226](https://github.com/open-agentos/productswarm/pull/226) GOV-0018: reviewer App key in a protected Actions environment (#207)  
Linked issue: #207 GOV-Q: Should the reviewer App's private key move into Actions secrets, and with what scope?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0018-reviewer-app-key-in-actions.md  
> Ruling PR for #207 (per GOV-0007). The owner answered "Option 1" and added `gov:ruled` and `ready`. The question is `security`, one-way and external, so it needs a record. Adds `governance/decisions/GOV-0018-reviewer-app-key-in-actions.md` and its row in `governance/INDEX.md`. **Ruling:** store `pro …

Draft: governance, fix no. "Ruling PR for #207 (per GOV-0007). The owner answered "Option 1" and added `gov:ruled` and `ready`."

label: governance
fix: no
hard:
reviewed: no

## pr-230 · test · 2026-W45

[#230](https://github.com/open-agentos/productswarm/pull/230) Needs you: flag gov questions past their time to live (v3 F1)  
Linked issue: #210 Needs you: flag gov questions past their time to live (v3 F1)  
Paths touched (2): dashboard/generate.py, dashboard/test_needs.py  
> Closes #210 ## What In `dashboard/generate.py`, `needs_you()` now reads the "Time to live" answer as a date. If that date is before today (UTC), the question's detail starts with **"past time to live (YYYY-MM-DD)"** instead of "time to live YYYY-MM-DD". Past-TTL questions sort first among questions, …

Draft: capability, fix no. "The dashboard's Needs-you section and `swarm inbox` both render `needs_line()`, so both show it."

label: capability
fix: no
hard:
reviewed: no

## pr-266 · test · 2026-W45

[#266](https://github.com/open-agentos/productswarm/pull/266) governance: GOV-0020, a reconciler on main starts Actions reviewer runs (#255)  
Linked issue: #255 GOV-Q: How should a PR event reach the reviewer's main-only Actions environment?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0020-reviewer-reconciler.md  
> Ruling PR for #255, per GOV-0007. The owner added `gov:ruled` and `ready` and ruled "option 5, stage 1" in a comment. The question is in `security` and amends two in-force records, so it needs one. Adds `governance/decisions/GOV-0020-reviewer-reconciler.md` and its row in `governance/INDEX.md`. ## H …

Draft: governance, fix no. "Ruling PR for #255, per GOV-0007."

label: governance
fix: no
hard:
reviewed: no

## pr-279 · test · 2026-W45

[#279](https://github.com/open-agentos/productswarm/pull/279) Update reviewer.yml  
Linked issue: none  
Paths touched (1): .github/workflows/reviewer.yml  
> In response to https://github.com/open-agentos/productswarm/issues/259

Draft: upkeep, fix no. "Title: Update reviewer.yml"

label: upkeep
fix: no
hard:
reviewed: no

## pr-282 · test · 2026-W45

[#282](https://github.com/open-agentos/productswarm/pull/282) swarm.toml: actions_max_reviews = 2 (#257)  
Linked issue: none  
Paths touched (1): swarm.toml  
> Sets `[watch] actions_max_reviews = 2`, the most open PRs one reconciler sweep lists for the Actions reviewer (#257). No issue: an owner `spend` setting. **Why now:** with the key unset, every `actions_review.py plan` sweep logs "nothing listed" and reviews nothing, which blocks #260's switch-over ( …

Draft: upkeep, fix no. "with the key unset, every `actions_review.py plan` sweep logs "nothing listed" and reviews nothing"

label: upkeep
fix: no
hard:
reviewed: no

## pr-305 · test · 2026-W45

[#305](https://github.com/open-agentos/productswarm/pull/305) Launcher tests no longer depend on the owner's swarm.toml switches  
Linked issue: #285 launcher tests fail on main: 4 tests read the real swarm.toml, which now sets review_in_actions = true  
Paths touched (2): launcher/test_manifest.py, launcher/test_watch.py  
> Closes #285 ## What On `main`, 4 launcher tests fail because they read the repo's own `swarm.toml`, where the owner set `review_in_actions = true` and `actions_max_reviews = 2` (#257, #260). - `test_watch.WatchTest`: `setUp` now writes a fixture manifest (every role capped, `max_live = 2`, no `revie …

Draft: upkeep, fix yes. "Closes #285 launcher tests fail on main: 4 tests read the real swarm.toml, which now sets review_in_actions = true"

label: upkeep
fix: yes
hard: tests-only
reviewed: no

## pr-310 · test · 2026-W45

[#310](https://github.com/open-agentos/productswarm/pull/310) swarm watch: write watch.json through a temp file of its own  
Linked issue: #296 swarm watch: watch.json is written through a shared watch.tmp, so two watchers can crash  
Paths touched (2): launcher/test_watch.py, launcher/watch.py  
> Closes #296 `save_state()` in `launcher/watch.py` wrote `watch.json` through a fixed `watch.tmp`. Two writers could rename each other's temp file, and one would crash with `FileNotFoundError`. It now writes through `tempfile.mkstemp(dir=..., prefix=".watch.", suffix=".tmp")` and `os.replace`, and re …

Draft: upkeep, fix yes. "`save_state()` in `launcher/watch.py` wrote `watch.json` through a fixed `watch.tmp`. Two writers could rename each other's temp file, and one would crash with `FileNotFoundError`."

label: upkeep
fix: #295
hard:
reviewed: no

## pr-341 · test · 2026-W45

[#341](https://github.com/open-agentos/productswarm/pull/341) evals: red cost check, the first 5 builder-App reds and the 2-round bound  
Linked issue: #329 roles/reviewer.md: request changes only on a numbered block finding with evidence (#311 part 2); #330 Red cost check: count the first 5 builder-App reds and how many reach the 2-round bound (#311 part 3)  
Paths touched (4): dashboard/generate.py, evals/README.md, evals/red_check.py, evals/test_red_check.py  
> Closes #330 Part C of the owner's ruling on #311 (cited until #326 / GOV-0021 merges): after the first 5 builder-App reds under the new reviewer rule, revisit it if more than 2 reach the 2-round bound. ## What - `evals/red_check.py`: `python3 evals/red_check.py [--repo owner/name]`. Stdlib only; pub …

Draft: capability, fix no. "- `evals/red_check.py`: `python3 evals/red_check.py [--repo owner/name]`. Stdlib only; public GitHub data only."

label: capability
fix: no
hard:
reviewed: no

## pr-375 · test · 2026-W45

[#375](https://github.com/open-agentos/productswarm/pull/375) Dashboard committees, part 1: read committee Discussions and their gov:question  
Linked issue: #353 Dashboard committees, part 1: read committee Discussions and their gov:question  
Paths touched (4): dashboard/README.md, dashboard/committees.py, dashboard/generate.py, dashboard/test_committees.py  
> Closes #353 ## What - **`dashboard/committees.py` (new).** `fetch()` reads every Discussion in the `committees` category through `gh api graphql`, paging past 100 for Discussions and for comments. It then reads each linked question's issue and comments over REST. `build()` turns this into one commit …

Draft: capability, fix no. "The model gets a `committees` key, which #354 will render. Nothing on the page changes yet."

label: capability
fix: no
hard:
reviewed: no

## pr-384 · test · 2026-W45

[#384](https://github.com/open-agentos/productswarm/pull/384) reviewer.yml: print the reviewer token's granted permissions (#364)  
Linked issue: #364 Reviewer Actions token opened issues despite issues: read (found in #307)  
Paths touched (1): .github/workflows/reviewer.yml  
> Closes #364 The builder's patch from #364, committed by the owner (workflow files are the owner's, #32). The `review` job keeps the access-token response, takes the token from it, and prints one line, `token permissions: {...}`, from its `.permissions`. The response itself is never printed, and the  …

Draft: upkeep, fix no. "The `review` job keeps the access-token response, takes the token from it, and prints one line, `token permissions: {...}`, from its `.permissions`."

label: upkeep
fix: no
hard:
reviewed: no

## pr-387 · test · 2026-W45

[#387](https://github.com/open-agentos/productswarm/pull/387) Committee Discussion form with a question marker (#371)  
Linked issue: #371 Committee Discussion form with a question marker (per #352, option 3)  
Paths touched (2): .github/DISCUSSION_TEMPLATE/committees.yml, dashboard/test_committees.py  
> Closes #371 Adds `.github/DISCUSSION_TEMPLATE/committees.yml`, a Discussion form for the `committees` category that keeps #314's layout and adds the question marker (#352, option 3). **Marker: one prefilled textarea.** It's the first field, prefilled with `<!-- productswarm-committee question=NNN -- …

Draft: capability, fix no. "Adds `.github/DISCUSSION_TEMPLATE/committees.yml`, a Discussion form for the `committees` category"

label: capability
fix: no
hard:
reviewed: no

## pr-413 · test · 2026-W45

[#413](https://github.com/open-agentos/productswarm/pull/413) Dashboard: publish state.json beside the page (#400)  
Linked issue: #400 Dashboard desk 1: publish state.json beside the page (#397)  
Paths touched (5): dashboard/README.md, dashboard/generate.py, dashboard/state.py, dashboard/test_generate.py, dashboard/test_state.py  
> Each build now writes `state.json` next to `index.html`: the data the page shows, with no HTML and no cost. - `dashboard/state.py` (new): `state(model)` takes what `generate.build()` returns. Top-level keys are `schema: 1`, `built_at` (RFC 3339 UTC), `repo`, `idle_minutes`, then `needs_you`, `sessio …

Draft: capability, fix no. "Each build now writes `state.json` next to `index.html`: the data the page shows, with no HTML and no cost."

label: capability
fix: no
hard:
reviewed: no

## pr-427 · test · 2026-W45

[#427](https://github.com/open-agentos/productswarm/pull/427) Dashboard desk: past committees as cards (#409)  
Linked issue: #409 Dashboard desk 10: past committees as cards (#397)  
Paths touched (6): dashboard/README.md, dashboard/committees.py, dashboard/generate.py, dashboard/layout.py, dashboard/state.py, dashboard/test_committees.py  
> Closes #409 ## Stacked on #421 (and through it, #413 and #416) #409 waits on #404 (PR #421), which hasn't merged. #421 is itself stacked on #413 and #416. This branch is #421's branch plus one commit. **This PR's own change is the last commit, 6dbfc98.** Please merge #413, #416 and #421 first. I'll  …

Draft: capability, fix no. "The desk gains **Past committees**: one card per ended committee (record merged, or question closed), newest Discussion first."

label: capability
fix: no
hard:
reviewed: no

## pr-442 · test · 2026-W45

[#442](https://github.com/open-agentos/productswarm/pull/442) Desk: the wire, today's governance events (#405)  
Linked issue: #405 Dashboard desk 6: the wire, today's governance events (#397)  
Paths touched (7): dashboard/README.md, dashboard/activity.py, dashboard/generate.py, dashboard/layout.py, dashboard/state.py, dashboard/test_wire.py, dashboard/wire.py  
> Closes #405 Adds **the wire** under the floor on the desk: today's (UTC) governance events as templated one-line items with a time and a link, newest first, or "Quiet so far today." (`dashboard/wire.py`). Items go into `state.json` as `wire`. **Which kind uses which source** | Kind | Events (`activi …

Draft: capability, fix no. "Adds **the wire** under the floor on the desk: today's (UTC) governance events as templated one-line items with a time and a link"

label: capability
fix: no
hard:
reviewed: no

## pr-479 · test · 2026-W45

[#479](https://github.com/open-agentos/productswarm/pull/479) Add the analyst role  
Linked issue: #473 Add an analyst role to the swarm  
Paths touched (3): README.md, research/landscape.md, roles/analyst.md  
> Adds `roles/analyst.md`, `research/landscape.md` (entry format, no entries) and lists all six roles in `README.md`. Closes #473 ## Sixth role: what works as-is - **Dashboard:** yes. The floor, session cards and PR rows take the role from heartbeat events and the App login (`pr_role`), with no fixed  …

Draft: capability, fix no. "Adds `roles/analyst.md`, `research/landscape.md` (entry format, no entries) and lists all six roles in `README.md`."

label: capability
fix: no
hard: role-prompt-capability
reviewed: no

## pr-484 · test · 2026-W45

[#484](https://github.com/open-agentos/productswarm/pull/484) Add merge-automation entries to research/landscape.md  
Linked issue: #482 Add merge-automation entries to research/landscape.md  
Paths touched (1): research/landscape.md  
> Closes #482 Adds one entry per product cited in the #480 brief, in the file's format, with the brief's sources (read 2026-11-05; re-checked 2026-11-06): - **Similar products:** Copilot coding agent and Agent Merge (Agent Merge at medium confidence: one week-old vendor changelog). - **Competitive and …

Draft: knowledge, fix no. "Adds one entry per product cited in the #480 brief, in the file's format, with the brief's sources"

label: knowledge
fix: no
hard: brief-for-capability
reviewed: no

## pr-514 · test · 2026-W45

[#514](https://github.com/open-agentos/productswarm/pull/514) swarm watch: retry a run that hit the usage limit instead of marking it done  
Linked issue: #489 swarm watch: retry a run that hit the usage limit instead of marking it done  
Paths touched (3): launcher/README.md, launcher/test_watch.py, launcher/watch.py  
> Closes #489 ## What changes - **New ending, `limited`.** `read_result()` gives this ending when the result has `api_error` `usage_limit_reached` or `api_error_status` 429. Claude Code reports these as `subtype` `success` with `is_error` set, so until now they were recorded as `error (subtype success …

Draft: capability, fix yes. "- **New ending, `limited`.** `read_result()` gives this ending when the result has `api_error` `usage_limit_reached` or `api_error_status` 429."

label: capability
fix: yes
hard: feature-and-fix
reviewed: no

## pr-516 · test · 2026-W45

[#516](https://github.com/open-agentos/productswarm/pull/516) swarm watch: hold a [build] until the issues it waits on are closed  
Linked issue: #490 swarm watch: hold a [build] until the issues it waits on are closed  
Paths touched (5): launcher/README.md, launcher/test_watch.py, launcher/watch.py, roles/builder.md, roles/planner.md  
> Closes #490 ## What `[build]` now reads the issue body's `**Waits on:**` line. While any issue on it is still open, the trigger is held and starts nothing. It starts on the first check after every listed issue is closed, so the owner no longer has to take `ready` off and put it back. - `watch.waits_ …

Draft: capability, fix no. "`[build]` now reads the issue body's `**Waits on:**` line. While any issue on it is still open, the trigger is held and starts nothing."

label: capability
fix: no
hard:
reviewed: no

## pr-532 · test · 2026-W45

[#532](https://github.com/open-agentos/productswarm/pull/532) swarm watch: count always_one_way domains as needing a record (GOV-0007)  
Linked issue: #519 swarm watch: count always_one_way domains as needing a record (GOV-0007)  
Paths touched (3): launcher/README.md, launcher/test_watch.py, launcher/watch.py  
> Closes #519 **What changed** - `launcher/watch.py`: new `one_way_domains()` reads the domains `governance/jurisdictions.yml` marks `always_one_way: true` through `dashboard/authority.py`'s reader (the one `actions_review.py` already uses, not a second parser). `needs_record()` takes those domains an …

Draft: capability, fix no. "Title: swarm watch: count always_one_way domains as needing a record (GOV-0007)"

label: capability
fix: no
hard:
reviewed: no

## pr-537 · test · 2026-W45

[#537](https://github.com/open-agentos/productswarm/pull/537) Rewrite roles/planner.md as the lead (#529)  
Linked issue: #529 Rewrite roles/planner.md as the lead (#526)  
Paths touched (1): roles/planner.md  
> Rewrites `roles/planner.md` so the planner acts as the lead, following #526's direction. That question is `gov:ruled` with no record, so it is direction for #526 only (GOV-0006). The App, identity and opening line stay the same, so nothing in `ops/` or `launcher/` changes. - **New:** the lead's duti …

Draft: governance, fix no. "Rewrites `roles/planner.md` so the planner acts as the lead, following #526's direction."

label: governance
fix: no
hard: role-prompt-capability
reviewed: no

## pr-552 · test · 2026-W45

[#552](https://github.com/open-agentos/productswarm/pull/552) Sessions that never acted leave the floor, needs-you list and swarm ls (#454)  
Linked issue: #454 Live activity 3: hide sessions that never acted from the floor and swarm ls (#444)  
Paths touched (7): dashboard/floor.py, dashboard/generate.py, dashboard/test_floor.py, dashboard/test_needs.py, launcher/README.md, launcher/swarm.py, launcher/test_swarm.py  
> Closes #454 ## What - `generate.derive()` marks a session `never_acted` when it has no events, isn't stopped, and its tracking issue is older than the idle threshold (`created_at` is now read in `tracking_issues()`). Status stays `idle`. - `floor.build()` leaves those out of the cards and the idle l …

Draft: capability, fix no. "`swarm ls` skips them; `swarm ls --all` lists them as `idle, never acted`."

label: capability
fix: no
hard:
reviewed: no

## pr-556 · test · 2026-W45

[#556](https://github.com/open-agentos/productswarm/pull/556) swarm watch publishes its state to the [watch] issue (#458)  
Linked issue: #458 Live activity 7: publish swarm watch's state to a [watch] issue (#444)  
Paths touched (6): dashboard/activity.py, dashboard/test_activity.py, launcher/README.md, launcher/swarm.py, launcher/test_watch.py, launcher/watch.py  
> Closes #458 `swarm watch` now publishes `watch-public.json` (#456) to the one `[watch]` issue, so the desk can show it. ## What changed - **`launcher/watch.py`:** after each real tick, `Watch.publish()` compares the public state, leaving out `checked`, with the last one it published. If they differ, …

Draft: capability, fix no. "`swarm watch` now publishes `watch-public.json` (#456) to the one `[watch]` issue, so the desk can show it."

label: capability
fix: no
hard:
reviewed: no

## pr-560 · test · 2026-W45

[#560](https://github.com/open-agentos/productswarm/pull/560) swarm watch: retry runs that never started, re-hold builds that wait, restart on new launcher code  
Linked issue: #550 swarm watch: retry runs that did nothing, re-hold builds that waited, and restart on new launcher code  
Paths touched (5): launcher/README.md, launcher/swarm.py, launcher/test_swarm.py, launcher/test_watch.py, launcher/watch.py  
> Closes #550 ## The cause of "no result (no result file)" I found it in the Terminal window that #454's 12:27 run opened, which is still open. The window shows the typed command cut off at **exactly 1024 bytes** (`… 'Bash(gh pr edit * --add-label *`), with the shell left waiting on an open quote. Ter …

Draft: upkeep, fix yes. "Fix: `Launcher.start()` writes the command to `~/.productswarm/launcher/<sid>.window.sh` and types only `exec /bin/sh <file> --session-id <sid>`, about 170 bytes."

label: upkeep
fix: yes
hard: feature-and-fix
reviewed: no

## pr-570 · test · 2026-W45

[#570](https://github.com/open-agentos/productswarm/pull/570) GOV-0022 stage 1: run_tests.py and a proposed tests.yml (#521)  
Linked issue: #521 GOV-0022 stage 1: a required test check on main  
Paths touched (3): README.md, launcher/test_watch.py, run_tests.py  
> Adds `run_tests.py`, the test check for GOV-0022 stage 1, and below is `.github/workflows/tests.yml` for the owner to commit, as #217 did. Closes #521 ## What changed - **`run_tests.py`** runs every `test_*.py` under `launcher/`, `dashboard/`, `evals/` and `heartbeat/`. Each directory runs in its ow …

Draft: upkeep, fix yes. "two tests (`test_never_signals_and_only_reads_github`, `test_gather_reads_the_comments_of_ready_issues`) faked `generate.subprocess` but not `ghql.subprocess`, the path #392 added"

label: upkeep
fix: yes
hard: tests-only
reviewed: no

## pr-571 · test · 2026-W45

[#571](https://github.com/open-agentos/productswarm/pull/571) Create tests.yml  
Linked issue: none  
Paths touched (1): .github/workflows/tests.yml  
> In response to https://github.com/open-agentos/productswarm/pull/570

Draft: upkeep, fix no. "Title: Create tests.yml"

label: upkeep
fix: no
hard: tests-only
reviewed: no

## pr-579 · test · 2026-W45

[#579](https://github.com/open-agentos/productswarm/pull/579) GOV-0026: an approved milestone in PLAN.md is the go for its issues  
Linked issue: #575 GOV-Q: Does an approved milestone in PLAN.md replace per-issue ready as the go for its issues?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0026-milestone-is-go.md  
> Ruling record for #575, transcribed from the owner's answer ("Go with Option 2") and the question's option 2 (per GOV-0007). Merging it ratifies. Closes #575 **Adds** - `governance/decisions/GOV-0026-milestone-is-go.md` - its row in `governance/INDEX.md` **Where the record differs from the question  …

Draft: governance, fix no. "Ruling record for #575, transcribed from the owner's answer ("Go with Option 2") and the question's option 2 (per GOV-0007)."

label: governance
fix: no
hard:
reviewed: no

## pr-585 · test · 2026-W45

[#585](https://github.com/open-agentos/productswarm/pull/585) GOV-0027: standing grants and approved asks for the merger  
Linked issue: #576 GOV-Q: May the merger merge milestone PRs under standing grants, and protected-path PRs the owner approved at head?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0027-standing-grants-and-approved-asks.md  
> Ruling record for #576, transcribed from the owner's answer ("Confirmed. Option 2.") and the question's option 2 (per GOV-0007). Merging it ratifies. Closes #576 **Adds** - `governance/decisions/GOV-0027-standing-grants-and-approved-asks.md` - its row in `governance/INDEX.md` **Where the record diff …

Draft: governance, fix no. "Ruling record for #576, transcribed from the owner's answer"

label: governance
fix: no
hard:
reviewed: no

## pr-600 · test · 2026-W45

[#600](https://github.com/open-agentos/productswarm/pull/600) Launcher: an issue under an open PLAN.md milestone is go (GOV-0026)  
Linked issue: #582 Launcher: an issue under an open PLAN.md milestone is go (GOV-0026)  
Paths touched (5): launcher/README.md, launcher/stophook.py, launcher/swarm.py, launcher/test_stophook.py, launcher/test_swarm.py  
> Closes #582 Stage 1 of GOV-0026: one shared go check, used by `swarm launch` and the stop hook. ## What changed - **`launcher/swarm.py`**: `go_refusals(n, issue, events, owner, agents, reader)` sits next to `issue_refusals`. An issue is go when the owner's `ready` passes (GOV-0006, checked first, un …

Draft: capability, fix no. "Stage 1 of GOV-0026: one shared go check, used by `swarm launch` and the stop hook."

label: capability
fix: no
hard: ruling-implementation
reviewed: no

## pr-610 · test · 2026-W45

[#610](https://github.com/open-agentos/productswarm/pull/610) Role prompts: the merger App merges under GOV-0027  
Linked issue: #593 Role prompts: the merger merges under GOV-0027  
Paths touched (6): roles/analyst.md, roles/builder.md, roles/designer.md, roles/docs.md, roles/planner.md, roles/reviewer.md  
> Closes #593 Per GOV-0027, the merger App merges milestone PRs under standing grants and protected-path PRs under approved asks. The role prompts still said only the owner merges. This updates them. - `roles/planner.md`: removes Q3 from "What is not yours yet". The daily report's "Under delegated aut …

Draft: capability, fix no. "The daily report's "Under delegated authority" now lists each merge by the merger with a link"

label: capability
fix: no
hard: ruling-implementation
reviewed: no

## pr-611 · test · 2026-W45

[#611](https://github.com/open-agentos/productswarm/pull/611) Update swarm.toml  
Linked issue: none  
Paths touched (1): swarm.toml  
> Add the merger agent

Draft: capability, fix no. "Add the merger agent"

label: capability
fix: no
hard:
reviewed: no

## pr-622 · test · 2026-W45

[#622](https://github.com/open-agentos/productswarm/pull/622) swarm watch: [ask] starts a role on the owner's Ask: line (GOV-0029)  
Linked issue: none  
Paths touched (9): launcher/README.md, launcher/manifest.py, launcher/stophook.py, launcher/swarm.py, launcher/test_manifest.py, launcher/test_stophook.py, launcher/test_swarm.py, launcher/test_watch.py, launcher/watch.py  
> **Milestone:** M1 (daily report runs without the owner). #590 names none, and rides with M1's report issue. Builds `[ask]` per GOV-0029 (#577, option 2). Its blocker #588 is merged, and the owner added `ready`. ## What changed - **Setting** (`launcher/manifest.py`): `asks` in `[watch]`, true or fals …

Draft: capability, fix no. "Builds `[ask]` per GOV-0029 (#577, option 2)."

label: capability
fix: no
hard:
reviewed: no

## pr-625 · test · 2026-W45

[#625](https://github.com/open-agentos/productswarm/pull/625) Role prompts: [daily], Ask:, Research: and milestone call-in runs (GOV-0029)  
Linked issue: #595 Role prompts: the [daily], Ask: and milestone call-in runs (#577)  
Paths touched (6): roles/analyst.md, roles/builder.md, roles/designer.md, roles/docs.md, roles/planner.md, roles/reviewer.md  
> Closes #595 Brings the role prompts in line with GOV-0029 and the triggers shipped so far. **`roles/planner.md`** - Removes the **Q4** bullet from "What is not yours yet". Q2 stays. - **Daily report** and **Monday check-in:** `[daily]` starts these runs each working day once its `daily` switch is on …

Draft: governance, fix no. "Brings the role prompts in line with GOV-0029 and the triggers shipped so far."

label: governance
fix: no
hard: role-prompt-capability
reviewed: no

## pr-626 · test · 2026-W45

[#626](https://github.com/open-agentos/productswarm/pull/626) Role prompts: a milestone is go alongside ready (GOV-0026)  
Linked issue: #584 Role prompts: milestone go alongside ready (GOV-0026)  
Paths touched (6): roles/analyst.md, roles/builder.md, roles/designer.md, roles/docs.md, roles/planner.md, roles/reviewer.md  
> Role prompts now say an implementation issue is go when the owner labelled it `ready` or GOV-0026's milestone conditions hold. Questions keep `ready` and `gov:ruled`. **Milestone:** no milestone yet (`PLAN.md`, #574, isn't on `main`). ## What changed - **All six prompts** (`builder`, `designer`, `do …

Draft: governance, fix no. "Role prompts now say an implementation issue is go when the owner labelled it `ready` or GOV-0026's milestone conditions hold."

label: governance
fix: no
hard: ruling-implementation
reviewed: no

## pr-634 · test · 2026-W45

[#634](https://github.com/open-agentos/productswarm/pull/634) swarm watch: [research] starts the analyst on a Research: line (GOV-0029)  
Linked issue: #591 swarm watch: [research] starts the analyst on a Research: line from the owner or planner (#577)  
Paths touched (11): launcher/README.md, launcher/manifest.py, launcher/stophook.py, launcher/swarm.py, launcher/test_manifest.py, launcher/test_stophook.py, launcher/test_swarm.py, launcher/test_watch.py, launcher/watch.py, roles/analyst.md, roles/planner.md  
> Builds the `[research]` trigger, per GOV-0029: a `Research: <question>` line from the owner or the planner starts the analyst once, and the brief goes in `research/`. **Milestone:** none yet (`PLAN.md`, #574, isn't on `main`); M4's analyst brief is the first planned use. ## What - **Switch:** `[watc …

Draft: capability, fix no. "Builds the `[research]` trigger, per GOV-0029: a `Research: <question>` line from the owner or the planner starts the analyst once, and the brief goes in `research/`."

label: capability
fix: no
hard:
reviewed: no

## pr-648 · test · 2026-W45

[#648](https://github.com/open-agentos/productswarm/pull/648) Turn on the GOV-0029 switches; stop tests pinning the repo manifest  
Linked issue: #647 swarm.toml: turn on the GOV-0029 switches, and stop tests pinning the repo manifest's values  
Paths touched (3): launcher/test_manifest.py, launcher/test_watch.py, swarm.toml  
> Closes #647 This re-applies #640's `[watch]` lines, which #646 reverted, with the test changes the reviewer's Block 3 on #640 asked for: - **`swarm.toml`:** `report_issue = 249`, `daily = true`, `daily_at = "08:30"`, `asks = true`, `research = true`, `call_ins = true`. These are the owner's `spend`  …

Draft: capability, fix no. "This re-applies #640's `[watch]` lines, which #646 reverted, with the test changes the reviewer's Block 3 on #640 asked for:"

label: capability
fix: no
hard: tests-only
reviewed: no

## pr-682 · test · 2026-W46

[#682](https://github.com/open-agentos/productswarm/pull/682) Launcher: an owner-opened Goal or Area is the go (GOV-0031)  
Linked issue: #681 Launcher: an owner-opened Goal or Area is the go (GOV-0031)  
Paths touched (8): launcher/README.md, launcher/stophook.py, launcher/swarm.py, launcher/test_goal.py, launcher/test_stophook.py, launcher/test_swarm.py, launcher/test_watch.py, launcher/watch.py  
> Closes #681 GOV-0031's first builder change: the launcher reads the go from Goal and Area issues, so it doesn't depend on `PLAN.md` once the milestone week ends. **The rule.** An implementation issue without the owner's `ready` is go when all of these hold: - a swarm App or the owner opened it; - it …

Draft: capability, fix no. "The launcher reads the go from Goal and Area issues, so it doesn't depend on `PLAN.md` once the milestone week ends."

label: capability
fix: no
hard: ruling-implementation
reviewed: no

## pr-691 · test · 2026-W46

[#691](https://github.com/open-agentos/productswarm/pull/691) Launcher: only implementation issue types are go under a Goal or Area  
Linked issue: #690 Launcher: only implementation issue types are go under a Goal or Area  
Paths touched (3): launcher/README.md, launcher/swarm.py, launcher/test_goal.py  
> Closes #690 #682 made an issue go under an owner-opened Goal or Area without reading the issue's own type, so a Mission, Brief, Question or Lesson under a Goal would have got a builder. GOV-0031 says *implementation* issues. - `swarm.py`: the scope query reads the issue's `issueType` in the same Gra …

Draft: upkeep, fix no. "#682 made an issue go under an owner-opened Goal or Area without reading the issue's own type, so a Mission, Brief, Question or Lesson under a Goal would have got a builder."

label: upkeep
fix: no
hard:
reviewed: no

## pr-703 · test · 2026-W46

[#703](https://github.com/open-agentos/productswarm/pull/703) Brief: what the finance and scenario planner will demand (M4)  
Linked issue: #693 Brief: what the finance and scenario planner will demand (M4)  
Paths touched (1): research/finance-planner-demands.md  
> Closes #693 **Milestone:** M4, the readiness review (#686). Adds `research/finance-planner-demands.md`, the analyst brief that M4 asks for. It covers what the planner is and who it serves, a possible first month of work, data, access and integrations, the risks and what productswarm would have to ch …

Draft: knowledge, fix no. "Adds `research/finance-planner-demands.md`, the analyst brief that M4 asks for."

label: knowledge
fix: no
hard: brief-for-capability
reviewed: no

## pr-704 · test · 2026-W46

[#704](https://github.com/open-agentos/productswarm/pull/704) research: readiness review checklist for M4  
Linked issue: #692 Brief: the readiness review checklist (M4)  
Paths touched (1): research/readiness-review-checklist.md  
> Adds `research/readiness-review-checklist.md`, the M4 readiness review checklist under Goal #686: 20 checks, each with its measure, its evidence source and whether it is a gate. - Checks 1–8 come from PRODUCT.md's done test and day-30 scorecard, updated for GOV-0031 (the plan is now owner-opened Goa …

Draft: knowledge, fix no. "Adds `research/readiness-review-checklist.md`, the M4 readiness review checklist under Goal #686: 20 checks, each with its measure, its evidence source and whether it is a gate."

label: knowledge
fix: no
hard: brief-for-capability
reviewed: no

## pr-714 · test · 2026-W46

[#714](https://github.com/open-agentos/productswarm/pull/714) Merger: the standing grant reads GOV-0031's go (GOV-0034)  
Linked issue: #702 Merger: the standing grant reads GOV-0031's go (GOV-0034)  
Paths touched (3): launcher/README.md, launcher/merger.py, launcher/test_merger.py  
> Closes #702 The merger's standing grant now counts an issue as approved when it is go under GOV-0031, per GOV-0034. Before this, it counted only `PLAN.md` milestones. **Milestone:** none. #702 is under the owner's Goal #684 (M2: Merges under delegation). - **Go check (`grant_issue`):** calls `swarm. …

Draft: capability, fix no. "The merger's standing grant now counts an issue as approved when it is go under GOV-0031, per GOV-0034."

label: capability
fix: no
hard: ruling-implementation
reviewed: no

## pr-717 · test · 2026-W46

[#717](https://github.com/open-agentos/productswarm/pull/717) swarm merges: this week's merges by the merger and by the owner, and reverts  
Linked issue: #710 swarm merges: this week's merges by the merger and by the owner  
Paths touched (3): launcher/README.md, launcher/swarm.py, launcher/test_merges.py  
> Adds `swarm merges [--last]`. It splits a UTC week's merges into `main` into the merger App's and the owner's, then lists each revert and whether it was reviewed at head. This is M2's done test (#684) and section 4 of the daily report. **Milestone:** M2 (#684). Go per GOV-0031: the planner opened it …

Draft: capability, fix no. "Adds `swarm merges [--last]`."

label: capability
fix: no
hard:
reviewed: no

## pr-720 · test · 2026-W46

[#720](https://github.com/open-agentos/productswarm/pull/720) Desk layout spec: plan, today's report and grants in use  
Linked issue: #711 Desk layout spec: plan, today's report and grants in use  
Paths touched (1): dashboard/README.md  
> Closes #711 **Milestone:** M3: The Desk shows the plan and the report (#685). #711 is go under GOV-0031: the planner opened it as a Task under the owner's open Goal #685, nothing blocks it, and there's no veto. ## What This adds a new section, **Plan, report and grants: layout**, to `dashboard/READM …

Draft: knowledge, fix no. "It's a spec only; there's no code."

label: knowledge
fix: no
hard: brief-for-capability
reviewed: no

## pr-723 · test · 2026-W46

[#723](https://github.com/open-agentos/productswarm/pull/723) Planner reads the plan from Goals and Areas; retire PLAN.md (GOV-0031)  
Linked issue: #708 Planner reads the plan from Goals and Areas; retire PLAN.md (GOV-0031)  
Paths touched (10): PLAN.md, PRODUCT.md, launcher/README.md, launcher/test_swarm.py, roles/analyst.md, roles/builder.md, roles/designer.md, roles/docs.md, roles/planner.md, roles/reviewer.md  
> Closes #708 **Goal:** M1, Daily report runs without the owner (#683). #708 is a sub-issue of #683, so it is go per GOV-0031. **What changes** - **Role prompts.** The "Which issues are go" paragraph in all six role prompts (`analyst`, `builder`, `designer`, `docs`, `planner`, `reviewer`) now states G …

Draft: capability, fix no. "The report now opens with a **Plan** section: each open, owner-opened Goal and Area, with its open sub-issues."

label: capability
fix: no
hard: ruling-implementation
reviewed: no

## pr-727 · test · 2026-W46

[#727](https://github.com/open-agentos/productswarm/pull/727) Desk: grants-in-use panel  
Linked issue: #713 Desk: grants-in-use panel  
Paths touched (8): dashboard/README.md, dashboard/generate.py, dashboard/grants.py, dashboard/layout.py, dashboard/state.py, dashboard/test_grants.py, dashboard/test_live.py, dashboard/test_rate.py  
> Closes #713 **Milestone:** M3, the Desk shows the plan and the report (Goal #685). It is go under GOV-0031: the owner opened Goal #685 above it, and its blocker #711 is closed. ## What A **Grants in use** panel on the desk, as `dashboard/README.md`'s layout spec (#711) sets out. It shows the merger' …

Draft: capability, fix no. "A **Grants in use** panel on the desk, as `dashboard/README.md`'s layout spec (#711) sets out."

label: capability
fix: no
hard:
reviewed: no

## pr-741 · test · 2026-W46

[#741](https://github.com/open-agentos/productswarm/pull/741) Set the merger live  
Linked issue: #740 Set the merger live (swarm.toml [merger] mode)  
Paths touched (1): swarm.toml  
> Closes #740 Changes `swarm.toml`'s `[merger] mode` from `shadow` to `live`. That's the only change. - **Approved asks** (protected-path PRs you've approved at head) merge from the merger's next run: GOV-0027's first shadow is over. - **Standing grants** (builder PRs whose issue is go under GOV-0031) …

Draft: capability, fix no. "Changes `swarm.toml`'s `[merger] mode` from `shadow` to `live`. That's the only change."

label: capability
fix: no
hard:
reviewed: no

## pr-743 · test · 2026-W46

[#743](https://github.com/open-agentos/productswarm/pull/743) tests.yml: run on merge_group, ready for a merge queue  
Linked issue: #742 tests.yml: run on merge_group, ready for a merge queue  
Paths touched (1): .github/workflows/tests.yml  
> Closes #742 Step 1 of turning on a merge queue for `main` (#663). Two lines in `.github/workflows/tests.yml`: - **`merge_group:` added to the triggers.** A merge queue reruns the required checks on a temporary branch holding the queued PRs and waits for `tests` there. Without this trigger, every que …

Draft: upkeep, fix no. "With no merge queue configured, `merge_group` never fires, so this changes nothing today."

label: upkeep
fix: no
hard: tests-only
reviewed: no

## pr-764 · test · 2026-W46

[#764](https://github.com/open-agentos/productswarm/pull/764) GOV-0035: the goal's readiness review is for the first outside project  
Linked issue: #758 GOV-Q: Should productswarm's goal stop ending in a readiness review for the finance and scenario planner?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0035-outside-project-review-unnamed.md  
> Records the owner's answer on #758 (Option 2, `Record: yes`): the goal ends in a readiness review for the first outside project, unnamed until the owner names one, not the finance and scenario planner. Amends GOV-0030. Adds `governance/decisions/GOV-0035-outside-project-review-unnamed.md` and its ro …

Draft: governance, fix no. "Records the owner's answer on #758 (Option 2, `Record: yes`): the goal ends in a readiness review for the first outside project, unnamed until the owner names one, not the finance and scenario planner."

label: governance
fix: no
hard:
reviewed: no

## pr-778 · test · 2026-W46

[#778](https://github.com/open-agentos/productswarm/pull/778) Research briefs: retarget the M4 checklist to the first outside project (GOV-0035)  
Linked issue: #767 Research briefs: retarget the M4 checklist to the first outside project (GOV-0035)  
Paths touched (2): research/finance-planner-demands.md, research/readiness-review-checklist.md  
> Retargets the M4 readiness checklist from the finance and scenario planner to "the first outside project", per GOV-0035 (#758). - `research/readiness-review-checklist.md`: the question line, the follow-up line, checks 9–20 and the "other half of M4" note now say "the outside project" (or its repo) i …

Draft: knowledge, fix no. "Retargets the M4 readiness checklist from the finance and scenario planner to "the first outside project", per GOV-0035 (#758)."

label: knowledge
fix: no
hard: brief-for-capability
reviewed: no

## pr-790 · test · 2026-W46

[#790](https://github.com/open-agentos/productswarm/pull/790) Planner: Monday check-in carries a hand-made Trouble section (#760 stage 0)  
Linked issue: #774 Monday check-in: add the Trouble section from 2026-11-16 (#760 stage 0)  
Paths touched (1): roles/planner.md  
> Closes #774 Goal: M1 (#683). Direction: #760, stage 0. ## What Adds a **Trouble** paragraph to `roles/planner.md` under "Monday check-in". From Monday 2026-11-16 it comes after the per-Goal lines. For each open Goal and Area it gives: 1. progress toward each done test, criterion by criterion 2. what …

Draft: capability, fix no. "From Monday 2026-11-16 it comes after the per-Goal lines."

label: capability
fix: no
hard: role-prompt-capability
reviewed: no

## pr-833 · test · 2026-W46

[#833](https://github.com/open-agentos/productswarm/pull/833) swarm trouble: COMMENTED oversteps, every PR the merger left, restart roles from watch, M2/M4 measures, authority = merges + call-ins  
Linked issue: #828 swarm trouble: catch COMMENTED oversteps, all approved PRs left for the owner, real restart roles, M2/M4 from swarm merges/acts, authority = merges + call-ins  
Paths touched (4): launcher/README.md, launcher/test_trouble.py, launcher/trouble.py, launcher/watch.py  
> Closes #828 Goal: M1 (#683). This PR fixes `swarm trouble` (#803) before the daily report reads it (#804). **What changes** 1. **Oversteps.** An overstep is now the reviewer's review at head with `Authority: fail`, whatever its state. #679's was `COMMENTED`, which the old code missed. Before the own …

Draft: capability, fix no. "This PR fixes `swarm trouble` (#803) before the daily report reads it (#804)."

label: capability
fix: no
hard: feature-and-fix
reviewed: no

## pr-841 · test · 2026-W46

[#841](https://github.com/open-agentos/productswarm/pull/841) [respond] and [ruling] start the PR's author role, not only the builder  
Linked issue: #738 [respond] only restarts the builder: other roles' PRs stall after changes requested  
Paths touched (12): dashboard/generate.py, dashboard/test_needs.py, launcher/README.md, launcher/stophook.py, launcher/swarm.py, launcher/test_stophook.py, launcher/test_trouble.py, launcher/test_watch.py, launcher/watch.py, roles/analyst.md, roles/docs.md, roles/planner.md  
> Closes #738 Goal: M2 (#684). Direction: the owner's answer on #777 (Option 1, `Record: yes`). That question is `gov:ruled` and `ready`, but its record isn't merged yet: docs drafts it per GOV-0007, in its own PR, since this one closes only #738. Until it merges, this amends GOV-0011's "builder only" …

Draft: capability, fix no. "[respond] and [ruling] start the PR's author role, not only the builder"

label: capability
fix: no
hard: feature-and-fix
reviewed: no

## pr-846 · test · 2026-W46

[#846](https://github.com/open-agentos/productswarm/pull/846) swarm acts: a day with no recorded data reads "not counted", never 0; backfill from GitHub (M4 gates 1-2)  
Linked issue: #844 swarm acts: a day with no recorded data reads "not counted", never 0; count where webhooks land or backfill (M4 gates 1-2)  
Paths touched (6): launcher/README.md, launcher/acts.py, launcher/swarm.py, launcher/test_acts.py, launcher/test_trouble.py, launcher/trouble.py  
> Closes #844 Under Goal M4: Readiness review (#686), criterion "my acts are counted for each of the 10 working days" (checklist gates 1 and 2). ## Which option: backfill from GitHub Step 2 of the issue asks for one of two options. This PR **backfills a day's acts from GitHub**. It doesn't read the en …

Draft: capability, fix no. "backfills a day's acts from GitHub"

label: capability
fix: no
hard: feature-and-fix
reviewed: no

## pr-864 · test · 2026-W46

[#864](https://github.com/open-agentos/productswarm/pull/864) swarm trouble: approved-but-conflicting PRs, quiet sessions, stopped stages, and under 30 seconds  
Linked issue: #858 swarm trouble: approved-but-conflicting PRs, quiet sessions, stopped stages, and under 30 seconds  
Paths touched (5): launcher/README.md, launcher/acts.py, launcher/test_acts.py, launcher/test_trouble.py, launcher/trouble.py  
> Closes #858 Under M1 (#683): the daily report's Trouble section is built from `swarm trouble --json` (#804). ## Why it got slow (fault 4) The lead in the issue was right: it was the acts backfill #846 added. Each `gh` call takes about 0.8 s, and the backfill made every call one at a time: - **Findin …

Draft: capability, fix yes. "The lead in the issue was right: it was the acts backfill #846 added."

label: capability
fix: #846
hard: feature-and-fix
reviewed: no

## pr-902 · test · 2026-W46

[#902](https://github.com/open-agentos/productswarm/pull/902) Desk: read-only trouble panel per Goal and Area from swarm trouble --json (#889)  
Linked issue: #889 Desk: read-only trouble panel per Goal and Area from swarm trouble --json (M3)  
Paths touched (3): launcher/desk.py, launcher/test_desk.py, launcher/testdata/trouble.json  
> Closes #889 **What.** `desk.trouble_panel(report)` in `launcher/desk.py` turns the dict from `swarm trouble --json` into a read-only HTML `<section>` with one article per open Goal and Area. Each article answers #760's four questions: - **Progress:** one line per criterion. `unmeasured` shows as "un …

Draft: capability, fix no. "Desk: read-only trouble panel per Goal and Area from swarm trouble --json (#889)"

label: capability
fix: no
hard:
reviewed: no

## pr-976 · test · 2026-W46

[#976](https://github.com/open-agentos/productswarm/pull/976) Brief: the Desk's state questions per Goal and Area (#888)  
Linked issue: #888 Brief: the Desk's state questions per Goal and Area (M3)  
Paths touched (1): research/desk-state-questions.md  
> Closes #888 **What.** `research/desk-state-questions.md`: the designer's Brief on #888 (https://github.com/open-agentos/productswarm/issues/888#issuecomment-6837332161), everything below its `---` line, as written. It lists eight questions (Q0–Q6, with Q1a and Q1b) the Desk must answer per open Goal …

Draft: knowledge, fix no. "**What.** `research/desk-state-questions.md`: the designer's Brief on #888"

label: knowledge
fix: no
hard: brief-for-capability
reviewed: no

# Dev split: 178 PRs, 0 reviewed

## pr-7 · dev · 2026-W44

[#7](https://github.com/open-agentos/productswarm/pull/7) Bootstrap: product brief, governance kit and role prompts  
Linked issue: #1 Bootstrap productswarm: product brief, governance kit, role prompts  
Paths touched (15): .github/CODEOWNERS, .github/ISSUE_TEMPLATE/gov-question.yml, CLAUDE.md, GOVERNANCE.md, PRODUCT.md, governance/INDEX.md, governance/PHASE0.md, governance/decisions/GOV-0000-template.md, governance/decisions/GOV-0001-adopt-governance.md, governance/jurisdictions.yml, governance/setup-labels.sh, roles/builder.md, roles/docs.md, roles/planner.md, roles/reviewer.md  
> Sets up productswarm as the Phase 0 test bed for open-agentos/agent-governance. The workload is the swarm dashboard and session heartbeat. **What's in it** - `PRODUCT.md`: v0 brief. It's read-only and has no launcher, and it deliberately leaves storage, hosting, hook capture and cost estimation for  …

Draft: governance, fix no. "The governance kit from agent-governance PR #2: `GOVERNANCE.md`, `governance/`, the question template, and `CODEOWNERS` (@mattmcalister)."

label: governance
fix: no
hard:
reviewed: no

## pr-9 · dev · 2026-W44

[#9](https://github.com/open-agentos/productswarm/pull/9) Give each agent role its own GitHub App identity  
Linked issue: #8 Give each agent role its own GitHub App identity  
Paths touched (14): .github/CODEOWNERS, CLAUDE.md, governance/PHASE0.md, governance/jurisdictions.yml, ops/README.md, ops/__pycache__/create-apps.cpython-314.pyc, ops/create-apps.py, ops/shims/gh, ops/swarm-session, ops/swarm-token, roles/builder.md, roles/docs.md, roles/planner.md, roles/reviewer.md  
> Each role (planner, builder, reviewer, docs) becomes a GitHub App, and sessions start with `ops/swarm-session <role>` acting as `productswarm-<role>[bot]`. **What's in it** - `ops/create-apps.py` creates the four Apps through GitHub's manifest flow: one click per role, then install. Keys are saved t …

Draft: capability, fix no. "Each role (planner, builder, reviewer, docs) becomes a GitHub App, and sessions start with `ops/swarm-session <role>` acting as `productswarm-<role>[bot]`."

label: capability
fix: no
hard:
reviewed: no

## pr-11 · dev · 2026-W44

[#11](https://github.com/open-agentos/productswarm/pull/11) Remove committed bytecode and ignore __pycache__  
Linked issue: #10 Remove committed ops/__pycache__ and ignore Python bytecode  
Paths touched (2): .gitignore, ops/__pycache__/create-apps.cpython-314.pyc  
> Removes `ops/__pycache__/create-apps.cpython-314.pyc`, which PR #9 committed by accident, and adds a `.gitignore` for `__pycache__/` and `*.pyc`. Closes #10 🤖 Generated with [Claude Code](https://claude.com/claude-code)

Draft: upkeep, fix yes. "Removes `ops/__pycache__/create-apps.cpython-314.pyc`, which PR #9 committed by accident, and adds a `.gitignore` for `__pycache__/` and `*.pyc`."

label: upkeep
fix: #9
hard:
reviewed: no

## pr-13 · dev · 2026-W44

[#13](https://github.com/open-agentos/productswarm/pull/13) Fix swarm-session aborting on unbound GIT_AUTHOR_EMAIL  
Linked issue: #12 ops/swarm-session fails: GIT_AUTHOR_EMAIL unbound variable  
Paths touched (1): ops/swarm-session  
> Computes the bot email once and assigns both variables from it, rather than reading `GIT_AUTHOR_EMAIL` in the same `export` that defines it. **Tested end to end** with a stub `claude` on PATH. `ops/swarm-session planner` now reaches launch with: - the role's opener prompt; - `gh` resolving to the sh …

Draft: upkeep, fix yes. "Computes the bot email once and assigns both variables from it, rather than reading `GIT_AUTHOR_EMAIL` in the same `export` that defines it."

label: upkeep
fix: yes
hard:
reviewed: no

## pr-16 · dev · 2026-W45

[#16](https://github.com/open-agentos/productswarm/pull/16) Heartbeat: define event schema v1  
Linked issue: #2 Heartbeat: define the session event schema and where events are stored  
Paths touched (4): heartbeat/SCHEMA.md, heartbeat/event.schema.json, heartbeat/examples/session.jsonl, heartbeat/examples/tracking-comment.md  
> Closes #2 ## What Adds `heartbeat/` with: - `SCHEMA.md`: the v1 event (fields, which fields may leave the machine, seven event types, how the dashboard derives active / idle / blocked / stopped) and the storage format. - `event.schema.json`: JSON Schema 2020-12. The root schema validates local spool …

Draft: knowledge, fix no. "Adds `heartbeat/` with:"

label: knowledge
fix: no
hard:
reviewed: no

## pr-20 · dev · 2026-W45

[#20](https://github.com/open-agentos/productswarm/pull/20) Phase 0 log: first rulings and observations  
Linked issue: #19 Phase 0 observation log: first rulings (#14, #15)  
Paths touched (1): governance/PHASE0.md  
> Adds the first two rows to the observation log (#14 and #15, both ruled in about 13 hours with no deliberation rounds) and five process observations: - the planner deferred asking; - owners rule in comments; - ruling PRs show the owner as author; - model signatures disagree; - the H5 test on PR #16  …

Draft: knowledge, fix no. "Adds the first two rows to the observation log (#14 and #15, both ruled in about 13 hours with no deliberation rounds) and five process observations:"

label: knowledge
fix: no
hard:
reviewed: no

## pr-22 · dev · 2026-W45

[#22](https://github.com/open-agentos/productswarm/pull/22) Phase 0 log: H5 first pass and PR #16 observations  
Linked issue: #21 Phase 0 log: H5 result and PR #16 observations  
Paths touched (1): governance/PHASE0.md  
> Closes #21 Replaces the "H5 test pending" note with the result, and adds two observations from PR #16: the schema was accepted through PR review rather than a gov question, and auto mode blocked the builder's own PR housekeeping. 🤖 Generated with [Claude Code](https://claude.com/claude-code)

Draft: knowledge, fix no. "Replaces the "H5 test pending" note with the result, and adds two observations from PR #16: the schema was accepted through PR review rather than a gov question, and auto mode blocked the builder's own PR housekeeping."

label: knowledge
fix: no
hard:
reviewed: no

## pr-30 · dev · 2026-W45

[#30](https://github.com/open-agentos/productswarm/pull/30) Dashboard: rough spend per session and per day  
Linked issue: #6 Dashboard: rough spend per session and per day  
Paths touched (4): dashboard/README.md, dashboard/generate.py, dashboard/spend.py, dashboard/test_spend.py  
> Closes #6 ## What The dashboard now shows estimated spend: - a **Spend (est.)** column per session; - a **spent today (est.)** tile in the top strip; - a **Spend per day** table for the last 7 UTC days; - a **method note** under it: API list-price equivalent, the price-table date, and any sessions l …

Draft: capability, fix no. "The dashboard now shows estimated spend:"

label: capability
fix: no
hard:
reviewed: no

## pr-34 · dev · 2026-W45

[#34](https://github.com/open-agentos/productswarm/pull/34) Dashboard: scheduled regeneration and hosting  
Linked issue: #5 Dashboard: scheduled regeneration and hosting  
Paths touched (4): .github/workflows/dashboard.yml, dashboard/README.md, dashboard/generate.py, dashboard/test_generate.py  
> Closes #5 ## What - `dashboard/generate.py` adds `<meta name="robots" content="noindex, nofollow">`, since the page will be public (owner's choice on #33, "Option 1, with noindex"). - `dashboard/README.md` says where the page is published, how often, with what token, and who can see it. ## ⚠️ Needs  …

Draft: capability, fix no. "Title: Dashboard: scheduled regeneration and hosting"

label: capability
fix: no
hard:
reviewed: no

## pr-35 · dev · 2026-W45

[#35](https://github.com/open-agentos/productswarm/pull/35) Dashboard: don't show a session's old PR next to its new issue  
Linked issue: #29 Dashboard shows a session's old PR next to its new issue  
Paths touched (2): dashboard/generate.py, dashboard/test_generate.py  
> Closes #29 `derive()` took the latest event carrying any `pr`, so a session that opened PR #27 for #4 and then moved to #6 showed "#6 … · PR #27". It now shows a PR only when the event that carried it has the same `issue` as the session's current issue. That covers `pr_opened` (which always sets `is …

Draft: capability, fix yes. "It now shows a PR only when the event that carried it has the same `issue` as the session's current issue."

label: capability
fix: #27
hard:
reviewed: no

## pr-38 · dev · 2026-W45

[#38](https://github.com/open-agentos/productswarm/pull/38) Phase 0 log: dashboard-build questions and observations  
Linked issue: #37 Phase 0 log: dashboard-build questions and observations  
Paths touched (1): governance/PHASE0.md  
> Closes #37 Adds rows for #26, #28, #31, #32, #33 (answered by owner comment, no records) and #36 (open). New observations: comment rulings are the norm, merges approving undeclared calls, governance practice saved in agent memory, only the builder has run, and the public-repo change under GOV-0002/0 …

Draft: knowledge, fix no. "Adds rows for #26, #28, #31, #32, #33 (answered by owner comment, no records) and #36 (open)."

label: knowledge
fix: no
hard:
reviewed: no

## pr-55 · dev · 2026-W45

[#55](https://github.com/open-agentos/productswarm/pull/55) GOV-0006: owner signals triage and go-ahead with gov:ruled and ready  
Linked issue: #54 GOV-Q: Should gov:ruled and ready be the owner's signals for triage and go-ahead?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0006-triage-labels.md  
> Adds GOV-0006, the record for the owner's answer on #54 (option 1), and its row in `governance/INDEX.md`. - `gov:ruled` on a `gov:question` = decided; `ready` = the next stage may start. - `ready` on any other issue = triaged; sessions take only `ready` issues, and the launcher (#49) refuses others  …

Draft: governance, fix no. "Adds GOV-0006, the record for the owner's answer on #54 (option 1), and its row in `governance/INDEX.md`."

label: governance
fix: no
hard:
reviewed: no

## pr-58 · dev · 2026-W45

[#58](https://github.com/open-agentos/productswarm/pull/58) GOV-0007: the docs role opens ruling PRs from the owner's answers  
Linked issue: #57 GOV-Q: Should the docs role open ruling PRs from the owner's answers and draft records?  
Paths touched (4): governance/INDEX.md, governance/PHASE0.md, governance/decisions/GOV-0007-docs-opens-ruling-prs.md, roles/docs.md  
> Adds GOV-0007, the record for the owner's answer on #57 ("Option 1, docs."): when the owner adds `gov:ruled` to a question that needs a record, the docs role opens the ruling PR, and the owner's merge ratifies it. ## Files - `governance/decisions/GOV-0007-docs-opens-ruling-prs.md`: the record. - `go …

Draft: governance, fix no. "Adds GOV-0007, the record for the owner's answer on #57 ("Option 1, docs.")"

label: governance
fix: no
hard:
reviewed: no

## pr-61 · dev · 2026-W45

[#61](https://github.com/open-agentos/productswarm/pull/61) Point CLAUDE.md and role prompts at GOV-0006 (ready, gov:ruled)  
Linked issue: #56 Point CLAUDE.md and role prompts at GOV-0006 (ready and gov:ruled)  
Paths touched (5): CLAUDE.md, roles/builder.md, roles/docs.md, roles/planner.md, roles/reviewer.md  
> Points the working rules and every role prompt at GOV-0006. Wording only; it adds nothing beyond the record. `ready` was added by @mattmcalister (checked in the issue's events). ## Files changed - **`CLAUDE.md`** - Working rules: a new bullet. Work only on `ready` issues, and only if the owner added …

Draft: governance, fix no. "Points the working rules and every role prompt at GOV-0006. Wording only; it adds nothing beyond the record."

label: governance
fix: no
hard:
reviewed: no

## pr-62 · dev · 2026-W45

[#62](https://github.com/open-agentos/productswarm/pull/62) PRODUCT.md: add the v1 launcher section (GOV-0005)  
Linked issue: #53 PRODUCT.md: add the v1 launcher section (GOV-0005)  
Paths touched (1): PRODUCT.md  
> Adds the v1 launcher section to `PRODUCT.md`, per GOV-0005. Wording only; it adds no scope and cuts none. `ready` was added by @mattmcalister (checked in the issue's events). ## Changes - **Title and status.** "Product brief: swarm dashboard" becomes "Product brief: productswarm". The status now rea …

Draft: governance, fix no. "Adds the v1 launcher section to `PRODUCT.md`, per GOV-0005. Wording only; it adds no scope and cuts none."

label: governance
fix: no
hard:
reviewed: no

## pr-65 · dev · 2026-W45

[#65](https://github.com/open-agentos/productswarm/pull/65) Launcher: swarm up / ls / stop (L2)  
Linked issue: #48 Launcher: swarm up / ls / stop  
Paths touched (4): launcher/README.md, launcher/swarm, launcher/swarm.py, launcher/test_swarm.py  
> Closes #48 ## What `launcher/swarm` (a thin wrapper around `launcher/swarm.py`), stdlib only: - **`swarm up [--dry-run]`** opens one Terminal window per manifest session, per the owner's answer on #43 (option 1). Each window runs `ops/swarm-session <role> --model <model> --session-id <uuid> "<usual  …

Draft: capability, fix no. "`swarm up [--dry-run]` opens one Terminal window per manifest session"

label: capability
fix: no
hard:
reviewed: no

## pr-70 · dev · 2026-W45

[#70](https://github.com/open-agentos/productswarm/pull/70) Launcher: swarm launch <role> --issue N (L3)  
Linked issue: #49 Launcher: start a session on a given issue  
Paths touched (4): launcher/README.md, launcher/swarm, launcher/swarm.py, launcher/test_swarm.py  
> Closes #49 > **Stacked on #65 (L2).** This branch includes #65's commit, so until #65 merges, this diff shows it too. The L3 change is the last commit, `a73141b`. Merge #65 first. ## What `launcher/swarm launch <role> --issue N [--model M] [--force] [--dry-run]` starts one session on issue N, in a n …

Draft: capability, fix no. "`launcher/swarm launch <role> --issue N [--model M] [--force] [--dry-run]` starts one session on issue N, in a new Terminal window like `up` does (#43)."

label: capability
fix: no
hard:
reviewed: no

## pr-72 · dev · 2026-W45

[#72](https://github.com/open-agentos/productswarm/pull/72) Reviewer runs by default and reviews each open PR once per push (L6)  
Linked issue: #51 Launcher: reviewer runs by default and reviews each open PR once  
Paths touched (3): launcher/test_manifest.py, roles/reviewer.md, swarm.toml  
> Closes #51 ## What - **`swarm.toml`:** the default manifest already starts one reviewer (since #47). I added a comment saying it's on by default and where its loop is, plus a test that the default manifest includes a reviewer. - **`roles/reviewer.md`:** a new "Your loop" section. A reviewer session: …

Draft: upkeep, fix no. "I added a comment saying it's on by default and where its loop is, plus a test that the default manifest includes a reviewer."

label: upkeep
fix: no
hard:
reviewed: no

## pr-74 · dev · 2026-W45

[#74](https://github.com/open-agentos/productswarm/pull/74) Spend cap, warn only (L4)  
Linked issue: #52 Launcher: per-session spend cap  
Paths touched (6): dashboard/README.md, dashboard/generate.py, dashboard/test_cap.py, launcher/README.md, launcher/swarm.py, launcher/test_swarm.py  
> Closes #52 ## What - **Over cap:** a session is over cap when its estimated spend passes its role's `spend_cap_usd` in `swarm.toml`. The estimate is `spend.session_cost`, the dashboard's existing method: API list-price equivalent, not what's billed. A session exactly at its cap isn't over. A session …

Draft: capability, fix no. "- **`swarm ls`:** a new SPEND (EST.) column shows `$4.55`, or `$20.00 / $15.00 OVER CAP` when a cap is set and passed."

label: capability
fix: no
hard:
reviewed: no

## pr-77 · dev · 2026-W45

[#77](https://github.com/open-agentos/productswarm/pull/77) Phase 0 log: v1 launcher round  
Linked issue: #76 Phase 0 log: v1 launcher round  
Paths touched (1): governance/PHASE0.md  
> Closes #76 Fills in #36 and adds rows for #41, #43–#46, #54 and #57. New observations: the fleet proposed GOV-0006/0007 to fix earlier log findings; the planner asked first and up front; v1 merged mostly without review (owner bypass); closed tabs leave sessions open (#75). 🤖 Generated with [Claude C …

Draft: knowledge, fix no. "Fills in #36 and adds rows for #41, #43–#46, #54 and #57."

label: knowledge
fix: no
hard:
reviewed: no

## pr-85 · dev · 2026-W45

[#85](https://github.com/open-agentos/productswarm/pull/85) Heartbeat: stop sessions that vanish without SessionEnd  
Linked issue: #75 Heartbeat: sessions closed without SessionEnd stay open and idle forever  
Paths touched (4): heartbeat/README.md, heartbeat/SCHEMA.md, heartbeat/hook.py, heartbeat/test_hook.py  
> Closes #75 ## What When a session's Terminal tab is closed, Claude Code gets SIGHUP (or is killed) and `SessionEnd` never runs. No `stopped` is posted, so the tracking issue stays open and the session shows as idle in `swarm ls` and `swarm inbox` forever. Now every new session sweeps this machine's  …

Draft: upkeep, fix no. "Now every new session sweeps this machine's other sessions **of the same role** that haven't stopped (`heartbeat/hook.py`, `sweep()`), in a detached process so start-up isn't slowed."

label: upkeep
fix: no
hard:
reviewed: no

## pr-86 · dev · 2026-W45

[#86](https://github.com/open-agentos/productswarm/pull/86) Docs: top-level README and v1 catch-up  
Linked issue: #82 Docs: top-level README and v1 catch-up  
Paths touched (4): README.md, dashboard/README.md, heartbeat/README.md, launcher/README.md  
> Closes #82 **`README.md`** was a two-line stub. It now has: - a table of what's in the repo (`heartbeat/`, `dashboard/`, `launcher/`, `swarm.toml`, `ops/`, `roles/`, governance), each linked to its own docs; - a 7-step quickstart from a fresh checkout to a running swarm: create the Apps → install th …

Draft: knowledge, fix no. "Title: Docs: top-level README and v1 catch-up"

label: knowledge
fix: no
hard:
reviewed: no

## pr-92 · dev · 2026-W45

[#92](https://github.com/open-agentos/productswarm/pull/92) GOV-0009: v2 is a local, start-only wake-up loop  
Linked issue: #87 GOV-Q: Should v2 add a local wake-up loop that starts the right session when a PR opens or the owner labels an issue?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0009-v2-wake-up-loop.md  
> Closes #87 Adds `governance/decisions/GOV-0009-v2-wake-up-loop.md` and its row in `governance/INDEX.md`, per GOV-0007. Your merge ratifies it. **Source.** #87 had no draft record, so this record is built from your answer ("Option 1" in a comment on 2026-11-03), option 1, and the scope sketch in the  …

Draft: governance, fix no. "Adds `governance/decisions/GOV-0009-v2-wake-up-loop.md` and its row in `governance/INDEX.md`, per GOV-0007."

label: governance
fix: no
hard:
reviewed: no

## pr-94 · dev · 2026-W45

[#94](https://github.com/open-agentos/productswarm/pull/94) swarm watch --dry-run: print what the wake-up loop would start  
Linked issue: #89 v2 W1: `swarm watch --dry-run` prints what the wake-up loop would start  
Paths touched (5): dashboard/generate.py, launcher/README.md, launcher/swarm.py, launcher/test_watch.py, launcher/watch.py  
> Closes #89 ## What `launcher/swarm watch --dry-run [--interval MINUTES]` runs in the foreground until Ctrl-C. Every interval (5 minutes by default, until #88 sets one) it reads the same GitHub and heartbeat state as `swarm inbox` and prints one line per **new** trigger: ``` [review] PR #70 head aaaa …

Draft: capability, fix no. "`launcher/swarm watch --dry-run [--interval MINUTES]` runs in the foreground until Ctrl-C."

label: capability
fix: no
hard:
reviewed: no

## pr-95 · dev · 2026-W45

[#95](https://github.com/open-agentos/productswarm/pull/95) Sessions get their own worktree; hooks run from a pinned copy of main  
Linked issue: #93 Swarm sessions share one checkout, so one session's branch changes the hook and code under every other session  
Paths touched (9): .gitignore, CLAUDE.md, heartbeat/README.md, heartbeat/install.py, heartbeat/test_install.py, launcher/README.md, launcher/swarm.py, launcher/test_swarm.py, launcher/test_watch.py  
> Closes #93 Done in the order the owner gave on #93 (A, B, C), as three commits. Real starts from `swarm watch` (#90) can land after this. ## A: working rule (CLAUDE.md) New working rule: never switch branches or leave edits in the shared checkout. Do branch work in a `git worktree add` directory out …

Draft: upkeep, fix no. "Sessions get their own worktree; hooks run from a pinned copy of main"

label: upkeep
fix: no
hard:
reviewed: no

## pr-100 · dev · 2026-W45

[#100](https://github.com/open-agentos/productswarm/pull/100) PRODUCT.md: mark v1 (local launcher) done  
Linked issue: #84 PRODUCT.md: mark v1 (local launcher) done  
Paths touched (1): PRODUCT.md  
> Closes #84 - Status line: `v0 (swarm dashboard) done · v1 (local launcher) done`. - The v1 table gets a **PR** column: L1 #64, L2 #65, L3 #70, L4 #74, L5 #71, L6 #72. I checked each PR is merged and closes the issue in its row. - No other content changes. #75, the last open v1 bug, is closed. The v2 …

Draft: knowledge, fix no. "Status line: `v0 (swarm dashboard) done · v1 (local launcher) done`."

label: knowledge
fix: no
hard:
reviewed: no

## pr-103 · dev · 2026-W45

[#103](https://github.com/open-agentos/productswarm/pull/103) PRODUCT.md: add the v2 section (wake-up loop)  
Linked issue: #91 PRODUCT.md: add the v2 section (wake-up loop)  
Paths touched (1): PRODUCT.md  
> Closes #91 Adds `## v2: wake-up loop` after v1 in `PRODUCT.md`, in the same shape as v1's section. Nothing else changes. - **What it is:** `launcher/swarm watch`, local, foreground, start-only. Cites GOV-0009, since #87's record has merged. - **Triggers:** the four from GOV-0009, acting only on owne …

Draft: knowledge, fix no. "Adds `## v2: wake-up loop` after v1 in `PRODUCT.md`, in the same shape as v1's section. Nothing else changes."

label: knowledge
fix: no
hard:
reviewed: no

## pr-120 · dev · 2026-W45

[#120](https://github.com/open-agentos/productswarm/pull/120) swarm watch: [respond] starts the builder on requested changes, at most 2 rounds per PR (GOV-0011 R3)  
Linked issue: #113 GOV-0011 R3: swarm watch starts the builder on requested changes, at most 2 rounds per PR  
Paths touched (7): dashboard/generate.py, dashboard/test_needs.py, launcher/README.md, launcher/swarm.py, launcher/test_swarm.py, launcher/test_watch.py, launcher/watch.py  
> Closes #113 Adds GOV-0011's fifth `swarm watch` trigger, `[respond]`, with the round bound and the overstep hand-off. ## What changed - **Review data, once.** `dashboard/generate.py` `fetch()` now reads `pulls/N/reviews` for each open, non-draft PR. `build()` turns the reviewer App's reviews into a  …

Draft: capability, fix no. "Adds GOV-0011's fifth `swarm watch` trigger, `[respond]`, with the round bound and the overstep hand-off."

label: capability
fix: no
hard:
reviewed: no

## pr-144 · dev · 2026-W45

[#144](https://github.com/open-agentos/productswarm/pull/144) swarm watch: hold a [build] while a live builder or open PR shares its GOV record  
Linked issue: #136 swarm watch: hold a [build] trigger while a live builder or open PR shares its GOV record (#127)  
Paths touched (3): launcher/README.md, launcher/test_watch.py, launcher/watch.py  
> Closes #136 Builds the owner's answer on #127 (option 2: wait on live builders **and** open PRs). The owner added `ready` to #127 but not `gov:ruled`, so this is direction for that question, not precedent (GOV-0006). No decision record is added. ## What changes - `launcher/watch.py`: new `gov_ids()` …

Draft: capability, fix no. "`start_tick` calls it for `[build]` triggers only, after the cap checks and before the GOV-0010 ceiling check, and holds the trigger with a reason"

label: capability
fix: no
hard:
reviewed: no

## pr-152 · dev · 2026-W45

[#152](https://github.com/open-agentos/productswarm/pull/152) swarm watch: Stop hook keeps loop-started runs going until their role is done  
Linked issue: #148 Stop hook: loop-started headless runs keep going until their role's done-condition is met  
Paths touched (5): launcher/README.md, launcher/stophook.py, launcher/swarm.py, launcher/test_stophook.py, launcher/watch.py  
> Closes #148 ## What Runs that `swarm watch` starts (`by="watch"`) get a Stop hook, `launcher/stophook.py`. When a run is about to stop, the hook reads GitHub as the run's App and blocks the stop with `{"decision": "block", "reason": …}` until the role's done-condition is met. Sessions started with ` …

Draft: upkeep, fix no. "Runs that `swarm watch` starts (`by="watch"`) get a Stop hook, `launcher/stophook.py`."

label: upkeep
fix: no
hard:
reviewed: no

## pr-153 · dev · 2026-W45

[#153](https://github.com/open-agentos/productswarm/pull/153) swarm watch: start loop-started runs headless (claude -p) with auto mode, denies and a hard budget  
Linked issue: #147 swarm watch: start loop-started runs headless (claude -p) with auto mode, denies and a hard budget  
Paths touched (7): launcher/README.md, launcher/manifest.py, launcher/swarm.py, launcher/test_swarm.py, launcher/test_watch.py, launcher/watch.py, swarm.toml  
> Closes #147 ## What Runs that `swarm watch` starts (`by="watch"`) are now one-shot headless runs. `Launcher.command()` adds these to the unchanged `ops/swarm-session <role> --model … --session-id …` call: - `-p <opener>` - `--permission-mode auto` (per GOV-0013) - `--disallowedTools` with `swarm.DEN …

Draft: capability, fix no. "Runs that `swarm watch` starts (`by="watch"`) are now one-shot headless runs."

label: capability
fix: no
hard:
reviewed: no

## pr-156 · dev · 2026-W45

[#156](https://github.com/open-agentos/productswarm/pull/156) swarm watch: record each headless run's cost and ending; list runs that ended at cap in inbox  
Linked issue: #149 swarm watch: record each headless run's cost and ending; list runs that ended at cap in needs-you  
Paths touched (4): launcher/README.md, launcher/swarm.py, launcher/test_watch.py, launcher/watch.py  
> Closes #149 > **Stacked on #153 (#147).** This branch starts from `builder/147-headless-watch-runs`, so until #153 merges, this diff also shows #153's commit (`ac4bb04`). This PR's own change is the single commit `9a2d3ec`. Please merge #153 first. After that, the diff here is only #149. ## What Onc …

Draft: capability, fix no. ""swarm inbox" adds a "swarm watch runs that ended at cap" section with each run's ref, the limit it reached, its cost and when it ended."

label: capability
fix: no
hard:
reviewed: no

## pr-158 · dev · 2026-W45

[#158](https://github.com/open-agentos/productswarm/pull/158) GOV-0014: sessions swarm watch starts run one-shot and exit when done  
Linked issue: #125 GOV-Q: Should sessions that swarm watch starts run one-shot (claude -p) and exit when they are done?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0014-one-shot-loop-runs.md  
> Ruling PR for #125, per GOV-0007. The owner answered "Option 3" in a comment, commented "Needs a record (GOV-0007)", then added `gov:ruled` and `ready`. Adds `governance/decisions/GOV-0014-one-shot-loop-runs.md` and its row in `governance/INDEX.md`. ## How the record differs from the answer The ques …

Draft: governance, fix no. "Adds `governance/decisions/GOV-0014-one-shot-loop-runs.md` and its row in `governance/INDEX.md`."

label: governance
fix: no
hard:
reviewed: no

## pr-161 · dev · 2026-W45

[#161](https://github.com/open-agentos/productswarm/pull/161) Phase 0 log: v2 wake-up loop round  
Linked issue: none  
Paths touched (1): governance/PHASE0.md  
> Adds today's governance evidence to `governance/PHASE0.md`: - **10 question rows:** #83, #87, #88, #101, #102, #105, #125, #126, #127, #131. Each has its domain, hours to ruling and outcome. Seven were answered within about 15 minutes. Six got records (GOV-0009 to GOV-0014). - **Observations:** - wh …

Draft: knowledge, fix no. "Adds today's governance evidence to `governance/PHASE0.md`:"

label: knowledge
fix: no
hard:
reviewed: no

## pr-164 · dev · 2026-W45

[#164](https://github.com/open-agentos/productswarm/pull/164) PRODUCT.md: bring the v2 section up to date (GOV-0010 to GOV-0014)  
Linked issue: #160 PRODUCT.md: bring the v2 section up to date (GOV-0011 to GOV-0014)  
Paths touched (1): PRODUCT.md  
> Closes #160 Only `PRODUCT.md` changes, and only its v2 section. - **Triggers:** adds `[respond]` (GOV-0011) and names each trigger as `launcher/README.md` does. - **What we're building:** adds PR numbers for W1/W2, plus R1–R3 (GOV-0011: #111–#113 → #117, #116, #120), H1–H3 (GOV-0012/13/14: #147–#149 …

Draft: governance, fix no. "drops the "in #90's scope" notes, records the answers on #101 and #102, and adds GOV-0010 to GOV-0014"

label: governance
fix: no
hard:
reviewed: no

## pr-169 · dev · 2026-W45

[#169](https://github.com/open-agentos/productswarm/pull/169) GOV-0015: v3 is evals, digest and Actions runs, staged; plan B only  
Linked issue: #167 GOV-Q: Should v3 add quality evals, a phone-friendly needs-you digest, and event-triggered role runs in GitHub Actions?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0015-v3-scope-staged.md  
> Ruling PR for #167 (per GOV-0007). Adds `governance/decisions/GOV-0015-v3-scope-staged.md` and its row in `governance/INDEX.md`. The owner labelled #167 `gov:ruled` and `ready`; its blast radius is `external`, so it needs a record. Transcribed from the owner's answer on #167 ("Option 1. Plan stage B …

Draft: governance, fix no. "Adds `governance/decisions/GOV-0015-v3-scope-staged.md` and its row in `governance/INDEX.md`."

label: governance
fix: no
hard:
reviewed: no

## pr-181 · dev · 2026-W45

[#181](https://github.com/open-agentos/productswarm/pull/181) evals/gather.py: pick the eval PR sample and gather its issues, records and reviews  
Linked issue: #173 v3 B2: evals/gather.py picks the PR sample and gathers its issues, records and reviews  
Paths touched (3): evals/data/sample.json, evals/gather.py, evals/test_gather.py  
> Closes #173 ## What `evals/gather.py` (stdlib + `gh`, read-only) picks the eval sample and writes `evals/data/sample.json` for #174 to score. **Sampling rule** (in the docstring): 1. Every merged PR. 2. Keep it if `productswarm-reviewer[bot]` reviewed it, or if it closes one of the v1 issues #47–#52 …

Draft: upkeep, fix no. "`evals/gather.py` (stdlib + `gh`, read-only) picks the eval sample and writes `evals/data/sample.json` for #174 to score."

label: upkeep
fix: no
hard:
reviewed: no

## pr-188 · dev · 2026-W45

[#188](https://github.com/open-agentos/productswarm/pull/188) swarm watch: [respond] only on PRs the builder opened  
Linked issue: #178 swarm watch [respond] starts the builder on PRs it didn't open (e.g. docs ruling PR #169)  
Paths touched (5): dashboard/generate.py, dashboard/test_needs.py, launcher/README.md, launcher/test_watch.py, launcher/watch.py  
> `swarm watch`'s `[respond]` trigger started the builder on docs ruling PR #169, which the builder may not change: GOV-0011 says the builder responds to requested changes **on its own PR**. ## Change - `dashboard/generate.py`: `needs_owner()` now takes the PR's author. When the reviewer's latest revi …

Draft: capability, fix no. "`needs_you()` and `swarm inbox` list the PR for the owner, the same way they list oversteps."

label: capability
fix: no
hard:
reviewed: no

## pr-191 · dev · 2026-W45

[#191](https://github.com/open-agentos/productswarm/pull/191) Stop hook: let a run blocked on an unfinished prerequisite stop  
Linked issue: #184 Stop hook: a builder run blocked by an unfinished prerequisite issue has no way to finish  
Paths touched (3): launcher/README.md, launcher/stophook.py, launcher/test_stophook.py  
> Closes #184 ## What The Stop hook now lets a `[build]` (or `[record]`) run stop when the run has commented on its own issue since it started, naming another **open issue** (not a PR) as `#M`. That's the "blocked on a prerequisite" ending from option 1 on #184. The "No PR closes #N" block reason now  …

Draft: capability, fix no. "The Stop hook now lets a `[build]` (or `[record]`) run stop when the run has commented on its own issue since it started, naming another **open issue** (not a PR) as `#M`."

label: capability
fix: no
hard:
reviewed: no

## pr-197 · dev · 2026-W45

[#197](https://github.com/open-agentos/productswarm/pull/197) evals/README.md: eval rubric and the pre-registered bar for C stage 2  
Linked issue: #172 v3 B1: Eval rubric and the pre-registered bar for C stage 2  
Paths touched (1): evals/README.md  
> Closes #172 Adds `evals/README.md`. It holds the rubric #174 scores with and the bar #175 reports against (v3 stage B, GOV-0015). It adds no code and no scores. ## What it defines - **Scored on:** each "Done when" / "Acceptance" item (`met` / `unmet` / `unclear`, with evidence), each cited `GOV-NNNN …

Draft: knowledge, fix no. "Adds `evals/README.md`. It holds the rubric #174 scores with and the bar #175 reports against (v3 stage B, GOV-0015). It adds no code and no scores."

label: knowledge
fix: no
hard:
reviewed: no

## pr-200 · dev · 2026-W45

[#200](https://github.com/open-agentos/productswarm/pull/200) evals/results.md: score the sampled PRs against the rubric (B3)  
Linked issue: #174 v3 B3: Score the sampled PRs against the rubric (evals/results.md)  
Paths touched (1): evals/results.md  
> Closes #174 ## What `evals/results.md` scores all 20 PRs in `evals/data/sample.json` against #172's rubric (`evals/README.md`). Each PR was scored at its merge head. For each one the file has the eval verdict, the reviewer verdict, agree/disagree, a `met` / `unmet` / `unclear` mark with evidence for …

Draft: knowledge, fix no. "`evals/results.md` scores all 20 PRs in `evals/data/sample.json` against #172's rubric (`evals/README.md`)."

label: knowledge
fix: no
hard:
reviewed: no

## pr-202 · dev · 2026-W45

[#202](https://github.com/open-agentos/productswarm/pull/202) evals/results.md: reviewer calibration and the result against the bar (B4)  
Linked issue: #175 v3 B4: Reviewer calibration and the result against the bar  
Paths touched (1): evals/results.md  
> Closes #175 Adds a "Calibration" section to `evals/results.md`. No other file changes. ## What it says - **Causes of disagreement:** none to explain. #174 found 15 of 15 in agreement, so each cause category from #175 is counted and every count is 0. The section also notes that 7 of the 15 reviews (# …

Draft: knowledge, fix no. "Adds a "Calibration" section to `evals/results.md`. No other file changes."

label: knowledge
fix: no
hard:
reviewed: no

## pr-220 · dev · 2026-W45

[#220](https://github.com/open-agentos/productswarm/pull/220) GOV-0016: reviewer runs in Actions log only the final result  
Linked issue: #205 GOV-Q: What may a reviewer run in GitHub Actions put in its public job log?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0016-actions-reviewer-log.md  
> Ruling PR for #205 (per GOV-0007). The owner answered "Option 1" and added `gov:ruled` and `ready`. The question is `one-way` / `external` in the `security` domain, so it needs a record. Adds `governance/decisions/GOV-0016-actions-reviewer-log.md` and its row in `governance/INDEX.md`. **Ruling:** a  …

Draft: governance, fix no. "Adds `governance/decisions/GOV-0016-actions-reviewer-log.md` and its row in `governance/INDEX.md`."

label: governance
fix: no
hard:
reviewed: no

## pr-223 · dev · 2026-W45

[#223](https://github.com/open-agentos/productswarm/pull/223) GOV-0017: Actions reviewer triggers and secret guards (#206)  
Linked issue: #206 GOV-Q: Which pull-request events may start a reviewer run in Actions, and how are secrets kept from untrusted input?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0017-actions-reviewer-triggers.md  
> Ruling PR for #206 (per GOV-0007). The owner added `gov:ruled` and `ready` and answered "Option 2" in a comment. The question is `security`, one-way and external, so it needs a record. Adds `governance/decisions/GOV-0017-actions-reviewer-triggers.md` and its row in `governance/INDEX.md`. **Ruling:** …

Draft: governance, fix no. "Ruling PR for #206 (per GOV-0007). The owner added `gov:ruled` and `ready` and answered "Option 2" in a comment."

label: governance
fix: no
hard:
reviewed: no

## pr-229 · dev · 2026-W45

[#229](https://github.com/open-agentos/productswarm/pull/229) GOV-0019: Actions reviewer triggers and coexistence with swarm watch (#209)  
Linked issue: #209 GOV-Q: How is the Actions reviewer workflow triggered, and how does it coexist with swarm watch?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0019-actions-reviewer-workflow.md  
> Ruling PR for #209, per GOV-0007. The owner added `gov:ruled` and `ready` and answered "Option 1". The question is `costly` / `external`, so it needs a record. Adds `governance/decisions/GOV-0019-actions-reviewer-triggers.md` and its row in `governance/INDEX.md`. ## How the record differs from the a …

Draft: governance, fix no. "Ruling PR for #209, per GOV-0007. The owner added `gov:ruled` and `ready` and answered "Option 1"."

label: governance
fix: no
hard:
reviewed: no

## pr-233 · dev · 2026-W45

[#233](https://github.com/open-agentos/productswarm/pull/233) dashboard/digest.py: needs-you list as phone-friendly Markdown (v3 F2)  
Linked issue: #211 dashboard/digest.py: render the needs-you list as phone-friendly Markdown (v3 F2)  
Paths touched (3): dashboard/README.md, dashboard/digest.py, dashboard/test_digest.py  
> ## What v3 F2 (GOV-0015). `dashboard/digest.py --print` renders the needs-you list as short Markdown for the pinned digest issue that F3 will keep current. It only reads; it never writes to GitHub. - The first line has the hidden `<!-- productswarm-digest -->` marker, then the count ("**3 things nee …

Draft: capability, fix no. "`dashboard/digest.py --print` renders the needs-you list as short Markdown for the pinned digest issue that F3 will keep current."

label: capability
fix: no
hard:
reviewed: no

## pr-236 · dev · 2026-W45

[#236](https://github.com/open-agentos/productswarm/pull/236) launcher/actions_review.py check: should a PR event start a reviewer run? (#214)  
Linked issue: #214 launcher/actions_review.py check: should this PR event start a reviewer run? (v3 C stage 1, part 1)  
Paths touched (4): launcher/README.md, launcher/actions_review.py, launcher/test_actions_review.py, launcher/watch.py  
> Closes #214 ## What v3 C stage 1, part 1 (GOV-0015). `python3 launcher/actions_review.py check` is the secret-free first job of the reviewer workflow. It reads `$GITHUB_EVENT_PATH` as data and writes `run=true|false` and `pr=<N>` to `$GITHUB_OUTPUT`, plus one line saying why. It says **run** only wh …

Draft: capability, fix no. "the event is `pull_request`, or `workflow_dispatch` with a `pr` input"

label: capability
fix: no
hard:
reviewed: no

## pr-239 · dev · 2026-W45

[#239](https://github.com/open-agentos/productswarm/pull/239) swarm watch: review_in_actions switch leaves [review] to Actions (#216)  
Linked issue: #216 swarm watch: a review_in_actions switch so the local loop leaves [review] to Actions (v3 C stage 1, part 3)  
Paths touched (8): launcher/README.md, launcher/manifest.py, launcher/swarm.py, launcher/test_manifest.py, launcher/test_swarm.py, launcher/test_watch.py, launcher/watch.py, swarm.toml  
> Closes #216 Builds the `swarm.toml` switch from GOV-0019 (the owner's "Option 1" on #209), so the local loop and the Actions reviewer don't both review the same head. The switch is **off by default** and `swarm.toml` sets it to `false`, so merging this changes nothing until the owner turns it on. ## …

Draft: capability, fix no. "Builds the `swarm.toml` switch from GOV-0019 (the owner's "Option 1" on #209), so the local loop and the Actions reviewer don't both review the same head."

label: capability
fix: no
hard:
reviewed: no

## pr-240 · dev · 2026-W45

[#240](https://github.com/open-agentos/productswarm/pull/240) launcher/actions_review.py run: one reviewer pass in Actions with GOV-0012/0013/0014 limits (#215)  
Linked issue: #215 launcher/actions_review.py run: one reviewer pass in Actions with GOV-0012/0013/0014 limits (v3 C stage 1, part 2)  
Paths touched (6): launcher/README.md, launcher/actions_review.py, launcher/stophook.py, launcher/swarm.py, launcher/test_actions_review.py, launcher/test_stophook.py  
> Closes #215 **Rebased onto `main`** (owner, after #236 merged). It was stacked on #236; the diff against `main` is now only this issue's commit (`a5e1ff9`, was `8b0e384`), unchanged apart from its base. launcher, dashboard, evals and heartbeat tests pass at the new head. ## What `python3 launcher/ac …

Draft: capability, fix no. "runs one reviewer pass on PR N inside an Actions job"

label: capability
fix: no
hard:
reviewed: no

## pr-243 · dev · 2026-W45

[#243](https://github.com/open-agentos/productswarm/pull/243) PRODUCT.md: add the v3 section (GOV-0015)  
Linked issue: #218 PRODUCT.md: add a v3 section (GOV-0015)  
Paths touched (1): PRODUCT.md  
> ## What Adds `## v3: evals, digest and Actions` to `PRODUCT.md`, in the same shape as the v1 and v2 sections, and updates the Status line (v2 done, v3 in progress). Only `PRODUCT.md` changes. - **Stage B (done):** #172–#176 with their merged PRs, and the result from `evals/results.md` (#202): inconc …

Draft: governance, fix no. "Adds `## v3: evals, digest and Actions` to `PRODUCT.md`, in the same shape as the v1 and v2 sections, and updates the Status line (v2 done, v3 in progress). Only `PRODUCT.md` changes."

label: governance
fix: no
hard:
reviewed: no

## pr-247 · dev · 2026-W45

[#247](https://github.com/open-agentos/productswarm/pull/247) dashboard/digest.py --update: keep the pinned digest issue current (v3 F3)  
Linked issue: #212 dashboard/digest.py --update: keep the pinned digest issue current (v3 F3)  
Paths touched (3): dashboard/README.md, dashboard/digest.py, dashboard/test_digest.py  
> Closes #212 ## What `python3 dashboard/digest.py --update --repo OWNER/REPO` (v3 F3, GOV-0015): - Finds the one **open** issue (not a PR) whose body starts with `<!-- productswarm-digest -->`. If there are none or more than one, it prints why and exits 1 without writing. It gets the issue from the o …

Draft: capability, fix no. "`python3 dashboard/digest.py --update --repo OWNER/REPO` (v3 F3, GOV-0015):"

label: capability
fix: no
hard:
reviewed: no

## pr-250 · dev · 2026-W45

[#250](https://github.com/open-agentos/productswarm/pull/250) Create digest.yml  
Linked issue: none  
Paths touched (1): .github/workflows/digest.yml  
> (empty)

Draft: upkeep, fix no. "Title: Create digest.yml"

label: upkeep
fix: no
hard:
reviewed: no

## pr-263 · dev · 2026-W45

[#263](https://github.com/open-agentos/productswarm/pull/263) swarm.toml: review_in_actions = false until the reconciler lands (#255)  
Linked issue: none  
Paths touched (1): swarm.toml  
> Turns `review_in_actions` back off. No issue: an owner config fix. **Why:** the Actions reviewer can't start on PR events yet. The `reviewer` environment only accepts `main`, and a `pull_request` run uses `refs/pull/N/merge` (#251's run, #255). With the switch on, `swarm watch` leaves every `[review …

Draft: upkeep, fix no. "Turns `review_in_actions` back off. No issue: an owner config fix."

label: upkeep
fix: no
hard:
reviewed: no

## pr-269 · dev · 2026-W45

[#269](https://github.com/open-agentos/productswarm/pull/269) Reconciler: actions_review.py plan lists the open PRs needing a review now (#255 stage 1, part 1)  
Linked issue: #257 Reconciler: `actions_review.py plan` lists the open PRs needing a review now (#255 stage 1, part 1)  
Paths touched (6): launcher/actions_review.py, launcher/manifest.py, launcher/test_actions_review.py, launcher/test_manifest.py, launcher/test_watch.py, swarm.toml  
> ## What `launcher/actions_review.py plan [--pr N] [--manifest PATH]`: a secret-free command that answers "which open PRs need a reviewer run now?" from repo state, rather than "did this event ask for one?". It's the first part of stage 1 of the owner's ruling on #255 (option 5). This PR cites #255;  …

Draft: capability, fix no. "`launcher/actions_review.py plan [--pr N] [--manifest PATH]`: a secret-free command that answers "which open PRs need a reviewer run now?""

label: capability
fix: no
hard:
reviewed: no

## pr-275 · dev · 2026-W45

[#275](https://github.com/open-agentos/productswarm/pull/275) Reconciler: plan skips heads already in flight or already attempted (#255 stage 1, part 2)  
Linked issue: #258 Reconciler: `plan` skips heads already in flight or already attempted, from the Actions run history (#255 stage 1, part 2)  
Paths touched (2): launcher/actions_review.py, launcher/test_actions_review.py  
> Closes #258 ## What `actions_review.py plan` now fills part 1's `hold` seam with a `History` of this workflow's Actions runs, so a sweep doesn't restart a review that hit its budget, or start a second review of a head that's already being reviewed. - **Job-name contract:** `REVIEW_JOB = "review #{pr …

Draft: capability, fix no. "so a sweep doesn't restart a review that hit its budget, or start a second review of a head that's already being reviewed."

label: capability
fix: no
hard:
reviewed: no

## pr-284 · dev · 2026-W45

[#284](https://github.com/open-agentos/productswarm/pull/284) Reconciler: retire actions_review.py check; README and PRODUCT.md describe the reconciler (#255 stage 1, part 4)  
Linked issue: #262 Reconciler: retire `actions_review.py check`; update launcher/README.md and PRODUCT.md (#255 stage 1, part 4)  
Paths touched (5): PRODUCT.md, launcher/README.md, launcher/actions_review.py, launcher/test_actions_review.py, launcher/watch.py  
> Closes #262 ## What `.github/workflows/reviewer.yml` on `main` now runs only `plan` and `run` (GOV-0020, committed for #259), so `actions_review.py check` and its `pull_request` path are no longer used. - **`launcher/actions_review.py`**: removes `check`, `decide()`, `write_output()`, `EVENTS` and t …

Draft: upkeep, fix no. "`actions_review.py check` and its `pull_request` path are no longer used."

label: upkeep
fix: no
hard:
reviewed: no

## pr-293 · dev · 2026-W45

[#293](https://github.com/open-agentos/productswarm/pull/293) swarm watch: [answer] reads the asker from the start of "Raised by"  
Linked issue: #271 swarm watch: [answer] starts any role named anywhere in "Raised by"  
Paths touched (3): launcher/README.md, launcher/test_watch.py, launcher/watch.py  
> Closes #271 ## What changed - **`raised_by()`** (`launcher/watch.py`) takes the asker from the start of the "Raised by" field: its first word, or the role in a leading `-- role` signature, case-insensitively. A role named later in the text no longer counts. "owner, after the first Actions reviewer t …

Draft: capability, fix no. "Title: swarm watch: [answer] reads the asker from the start of "Raised by""

label: capability
fix: no
hard:
reviewed: no

## pr-295 · dev · 2026-W45

[#295](https://github.com/open-agentos/productswarm/pull/295) Lock the launcher state file; unique temp file per write (#272)  
Linked issue: #272 Launcher state file has no lock: a launch during a watcher tick is lost, and concurrent writes crash  
Paths touched (4): launcher/README.md, launcher/swarm.py, launcher/test_swarm.py, launcher/test_watch.py  
> Closes #272 ## What changed `launcher/swarm.py`: - **Lock.** `Launcher.locked()` holds `fcntl.flock(LOCK_EX)` on `~/.productswarm/launcher/sessions.lock`. Every read-change-write of `sessions.json` runs under it: `live()` (load, drop exited, recover, save), plus the new `add()` and `remove()`, which …

Draft: upkeep, fix no. "Lock the launcher state file; unique temp file per write (#272)"

label: upkeep
fix: no
hard:
reviewed: no

## pr-300 · dev · 2026-W45

[#300](https://github.com/open-agentos/productswarm/pull/300) swarm watch: refuse to start a second watcher (#273)  
Linked issue: #273 swarm watch: refuse to start a second watcher  
Paths touched (3): launcher/README.md, launcher/test_watch.py, launcher/watch.py  
> Closes #273 ## What - `watch.take_lock()` opens `~/.productswarm/launcher/watch.lock` without truncating it and takes `fcntl.flock(LOCK_EX | LOCK_NB)`. If it gets the lock, it writes its pid into the file. If another process holds the lock, it returns that process's pid. - `Watch.run()` takes the lo …

Draft: capability, fix no. "A second watcher prints `swarm watch: refused: another swarm watch is already running (pid N; lock …)` and returns 1 before it reads GitHub or touches `watch.json`."

label: capability
fix: no
hard:
reviewed: no

## pr-301 · dev · 2026-W45

[#301](https://github.com/open-agentos/productswarm/pull/301) Reconciler plan: hold heads while a run is between plan and review (#278)  
Linked issue: #278 Reconciler: plan can re-list a head whose review job hasn't been created yet  
Paths touched (2): launcher/actions_review.py, launcher/test_actions_review.py  
> Closes #278 ## What `History` (the `hold` that `plan` uses) now spots a **starting** run: one that is still in progress and whose only job is a `plan` that has succeeded. That is the gap after `reviewer-plan` is released and before GitHub creates the run's `review` matrix jobs. When a starting run i …

Draft: upkeep, fix yes. "Closes #278"

label: upkeep
fix: #70
hard:
reviewed: no

## pr-326 · dev · 2026-W45

[#326](https://github.com/open-agentos/productswarm/pull/326) governance: GOV-0021 when the reviewer requests changes (#311)  
Linked issue: #311 GOV-Q: What should make the reviewer request changes rather than comment or approve?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0021-when-the-reviewer-requests-changes.md  
> Ruling PR for #311, per GOV-0007. The owner added `gov:ruled` and `ready` and ratified the committee's recommendation, option 3 as "3c+E", with the cost-check defaults. The record amends GOV-0011, so it needs one. Adds `governance/decisions/GOV-0021-when-the-reviewer-requests-changes.md` and its row …

Draft: governance, fix no. "Ruling PR for #311, per GOV-0007. The owner added `gov:ruled` and `ready` and ratified the committee's recommendation"

label: governance
fix: no
hard:
reviewed: no

## pr-335 · dev · 2026-W45

[#335](https://github.com/open-agentos/productswarm/pull/335) evals: rubric for the reviewer's block list, beside the unchanged bar (#311 E1–E3)  
Linked issue: #328 Eval rubric for the reviewer's block list: new marks, reporting lines beside the unchanged bar, the planted-defect gate (#311 part 1, E1–E3)  
Paths touched (2): evals/README.md, evals/results.md  
> Closes #328 Item B of the owner's ruling on #311. The rubric can now score the reviewer's red rule (#329) without moving the C stage 2 bar. It cites GOV-0021 (merged in #326), the ruling on #311, and keeps #311 as the question. ## What changed **`evals/README.md`** - **E1:** adds the block numbers t …

Draft: upkeep, fix no. "Rubric text only, with no code changes. `python3 -m unittest discover -s <dir>`"

label: upkeep
fix: no
hard:
reviewed: no

## pr-336 · dev · 2026-W45

[#336](https://github.com/open-agentos/productswarm/pull/336) roles/reviewer.md: request changes only on a numbered block finding with evidence (#311 part 2)  
Linked issue: #329 roles/reviewer.md: request changes only on a numbered block finding with evidence (#311 part 2)  
Paths touched (2): roles/builder.md, roles/reviewer.md  
> Closes #329 Item **A** of the owner's ruling on #311 ("ratified as recommended, option 3 as 3c+E"). Cites #311, since docs' record (#326, GOV-0021) hasn't merged yet. ## Merge order **Merge with or after #328's PR** (the eval rubric, B). If this lands first, Block 6 reds score as false blocks. #328  …

Draft: governance, fix no. "ratified as recommended, option 3 as 3c+E"

label: governance
fix: no
hard:
reviewed: no

## pr-344 · dev · 2026-W45

[#344](https://github.com/open-agentos/productswarm/pull/344) needs_you: flag a builder PR with no reviewer review at its head (#332)  
Linked issue: #332 Review gate leaks: builder PRs merged with no reviewer review (#200, #269, #275); find why and flag it in needs-you  
Paths touched (2): dashboard/generate.py, dashboard/test_needs.py  
> ## What `needs_you()` now marks a non-draft PR opened by the builder App as **`no reviewer review at <sha7>`** when the reviewer App has no review at its current head. It reads `reviewer_state()`'s `at_head` from the reviews `fetch()` already gets, so there are no new GitHub calls. `swarm inbox`, th …

Draft: capability, fix yes. "`needs_you()` now marks a non-draft PR opened by the builder App as **`no reviewer review at <sha7>`**"

label: capability
fix: #275
hard:
reviewed: no

## pr-366 · dev · 2026-W45

[#366](https://github.com/open-agentos/productswarm/pull/366) Turn the heartbeat off for reviewer runs in Actions  
Linked issue: #307 Actions reviewer runs leave empty [heartbeat] tracking issues behind  
Paths touched (3): launcher/README.md, launcher/actions_review.py, launcher/test_actions_review.py  
> Closes #307 ## What changed `launcher/actions_review.py run` now runs the reviewer in Actions with the heartbeat turned off, rather than spool-only: - **The hook isn't installed.** `hook_settings()` strips any heartbeat entries from `.claude/settings.local.json` (`install.with_hooks(..., uninstall=T …

Draft: upkeep, fix yes. "Closes #307 Actions reviewer runs leave empty [heartbeat] tracking issues behind"

label: upkeep
fix: yes
hard:
reviewed: no

## pr-368 · dev · 2026-W45

[#368](https://github.com/open-agentos/productswarm/pull/368) GOVERNANCE.md: committees in Discussions, brevity limits, current enforcement and ruling flow  
Linked issue: none  
Paths touched (1): GOVERNANCE.md  
> Owner amendment (§9, §10). No issue: only the owner changes this file. - **§7 Committees:** adopts the Discussion pilot from #311 / #314. Convening names seat, role, model and evidence; rounds run in a Committees-category Discussion; fixed turn order and post heading; stop early when recommendations …

Draft: governance, fix no. "Owner amendment (§9, §10). No issue: only the owner changes this file."

label: governance
fix: no
hard:
reviewed: no

## pr-372 · dev · 2026-W45

[#372](https://github.com/open-agentos/productswarm/pull/372) Dashboard: governance section (recent records, open questions, lapsed)  
Linked issue: #355 Dashboard: governance section (recent records, open questions by shape and domain, lapsed)  
Paths touched (4): dashboard/README.md, dashboard/generate.py, dashboard/governance.py, dashboard/test_governance.py  
> Adds the dashboard's governance section (part 3 of #348). It replaces the old "Open gov questions" table and keeps everything that table showed (labels, sessions waiting, age). - **Recent records:** the 8 newest `governance/INDEX.md` rows, newest first (GOV-0021 today). Each ID links to its record f …

Draft: capability, fix no. "Adds the dashboard's governance section (part 3 of #348). It replaces the old "Open gov questions" table and keeps everything that table showed"

label: capability
fix: no
hard:
reviewed: no

## pr-378 · dev · 2026-W45

[#378](https://github.com/open-agentos/productswarm/pull/378) Dashboard: Actions reviewer section (sweeps, success rate, commit-to-review time, unreviewed heads)  
Linked issue: #356 Dashboard: Actions reviewer section (sweeps, success rate, commit-to-review time, unreviewed heads)  
Paths touched (5): dashboard/README.md, dashboard/generate.py, dashboard/reviewer_runs.py, dashboard/test_reviewer_runs.py, launcher/test_swarm.py  
> Closes #356 Adds `dashboard/reviewer_runs.py`, called from `generate.fetch()`, `build()` and `render()`. Over the last 7 days (newest 30 runs at most) it shows: - **Sweeps** of `reviewer.yml`: when each started, how (`schedule`, `nudge` for a dispatch by `github-actions[bot]`, `manual (<login>)`), i …

Draft: capability, fix no. "Adds `dashboard/reviewer_runs.py`, called from `generate.fetch()`, `build()` and `render()`."

label: capability
fix: no
hard:
reviewed: no

## pr-379 · dev · 2026-W45

[#379](https://github.com/open-agentos/productswarm/pull/379) Dashboard: v3 progress section (stages, eval bar, planted gate, red check)  
Linked issue: #357 Dashboard: v3 progress section (stages, eval bar, planted gate, red check)  
Paths touched (6): dashboard/README.md, dashboard/generate.py, dashboard/progress.py, dashboard/test_generate.py, dashboard/test_progress.py, evals/red_check.py  
> Adds the v3 progress section to the dashboard (part 5 of #348). - **`dashboard/progress.py` (new).** It reads each GOV-0015 stage from the `### Stage …` tables in PRODUCT.md's v3 section and shows "N of M issues closed" from the `Issue` column, with open issues linked. A heading's "(done)" shows as  …

Draft: capability, fix no. "Adds the v3 progress section to the dashboard (part 5 of #348)."

label: capability
fix: no
hard:
reviewed: no

## pr-383 · dev · 2026-W45

[#383](https://github.com/open-agentos/productswarm/pull/383) Dashboard: reload an open page every 300 seconds (meta refresh)  
Linked issue: #351 Dashboard: rebuild on activity (nudge) and reload an open page (meta refresh)  
Paths touched (3): dashboard/README.md, dashboard/generate.py, dashboard/test_generate.py  
> Closes #351 Part B of #351. Part A, the nudge workflow, is posted on the issue for the owner to commit (#32). - `render()` adds `<meta http-equiv="refresh" content="300">` to the head (`REFRESH_SECONDS`). It's plain HTML with no script, so #26 still holds. I picked 300 seconds: with the nudge, a reb …

Draft: capability, fix no. "- `render()` adds `<meta http-equiv="refresh" content="300">` to the head (`REFRESH_SECONDS`)."

label: capability
fix: no
hard:
reviewed: no

## pr-388 · dev · 2026-W45

[#388](https://github.com/open-agentos/productswarm/pull/388) Dashboard committees, part 2: status timeline, round grid and convergence  
Linked issue: #354 Dashboard committees, part 2: status timeline, round grid and convergence  
Paths touched (4): dashboard/README.md, dashboard/committees.py, dashboard/generate.py, dashboard/test_committees.py  
> Closes #354 Adds a **Committees** section to the page, drawn by `committees.render()` from what #353's reader (#375) returns. - **Where:** open committees sit right after the needs-you list and its tiles, before Sessions. Ended committees (record merged, or the question closed) go in a collapsed "N  …

Draft: capability, fix no. "Adds a **Committees** section to the page, drawn by `committees.render()` from what #353's reader (#375) returns."

label: capability
fix: no
hard:
reviewed: no

## pr-391 · dev · 2026-W45

[#391](https://github.com/open-agentos/productswarm/pull/391) Reviewer runs in Actions: deny creating issues (#389)  
Linked issue: #389 Reviewer runs in Actions: deny creating issues (#364)  
Paths touched (4): launcher/README.md, launcher/actions_review.py, launcher/swarm.py, launcher/test_actions_review.py  
> Closes #389 Reviewer runs in Actions (`actions_review.py run`) now pass extra `--disallowedTools` patterns on top of `swarm.DENY`, so a reviewer misled by a prompt injection can't open an issue with the reviewer token (#364: the token is granted `issues: read`, yet GraphQL `createIssue` accepted it) …

Draft: upkeep, fix no. "so a reviewer misled by a prompt injection can't open an issue with the reviewer token"

label: upkeep
fix: no
hard:
reviewed: no

## pr-394 · dev · 2026-W45

[#394](https://github.com/open-agentos/productswarm/pull/394) Dashboard: keep rebuilds inside the API rate limit (#392)  
Linked issue: #392 Dashboard: keep rebuilds inside the API rate limit (spacing, fewer calls, skip cleanly)  
Paths touched (10): dashboard/README.md, dashboard/digest.py, dashboard/generate.py, dashboard/ghql.py, dashboard/progress.py, dashboard/reviewer_runs.py, dashboard/test_digest.py, dashboard/test_rate.py, dashboard/test_reviewer_runs.py, evals/red_check.py  
> **One rebuild against this repo now makes 23 REST calls and 19 GraphQL queries, down from 258 and 9.** Nudged rebuilds are spaced 5 minutes apart, and a low allowance now makes a run exit 0 instead of failing. Closes #392 ## Calls per rebuild (live, 2026-11-04) | | Before | After | |---|---|---| | T …

Draft: upkeep, fix no. "One rebuild against this repo now makes 23 REST calls and 19 GraphQL queries, down from 258 and 9."

label: upkeep
fix: no
hard:
reviewed: no

## pr-416 · dev · 2026-W45

[#416](https://github.com/open-agentos/productswarm/pull/416) Dashboard: new look, and split the page into desk, operations and decisions (#401)  
Linked issue: #401 Dashboard desk 2: new look, and split the page into the desk, operations and decisions (#397)  
Paths touched (18): dashboard/README.md, dashboard/committees.py, dashboard/generate.py, dashboard/governance.py, dashboard/layout.py, dashboard/static/fonts/IBMPlexMono-Regular-Latin1.woff2, dashboard/static/fonts/IBMPlexSans-Regular-Latin1.woff2, dashboard/static/fonts/IBMPlexSans-SemiBold-Latin1.woff2, dashboard/static/fonts/IBMPlexSansCondensed-SemiBold-Latin1.woff2, dashboard/static/fonts/LICENSE.txt, dashboard/test_cap.py, dashboard/test_committees.py, dashboard/test_generate.py, dashboard/test_governance.py, dashboard/test_needs.py, dashboard/test_reviewer_runs.py, dashboard/test_spend.py, launcher/test_swarm.py  
> Closes #401 ## What changed - **`dashboard/layout.py` (new):** #397's look in one place: paper `#F4F3EE`, agents blue `#1F4FB8` (active sessions), owner amber `#A35A00` (what waits on the owner), red `#C2361B` only for blocks and live marks. Text is IBM Plex Sans, times, numbers and code Plex Mono,  …

Draft: capability, fix no. "Dashboard: new look, and split the page into desk, operations and decisions (#401)"

label: capability
fix: no
hard:
reviewed: no

## pr-418 · dev · 2026-W45

[#418](https://github.com/open-agentos/productswarm/pull/418) Dashboard: on the floor, a card per active agent from heartbeat events (#403)  
Linked issue: #403 Dashboard desk 4: On the floor, a card per active agent from heartbeat events (#397)  
Paths touched (22): dashboard/README.md, dashboard/committees.py, dashboard/floor.py, dashboard/generate.py, dashboard/governance.py, dashboard/layout.py, dashboard/state.py, dashboard/static/fonts/IBMPlexMono-Regular-Latin1.woff2, dashboard/static/fonts/IBMPlexSans-Regular-Latin1.woff2, dashboard/static/fonts/IBMPlexSans-SemiBold-Latin1.woff2, dashboard/static/fonts/IBMPlexSansCondensed-SemiBold-Latin1.woff2, dashboard/static/fonts/LICENSE.txt, dashboard/test_cap.py, dashboard/test_committees.py, dashboard/test_floor.py, dashboard/test_generate.py, dashboard/test_governance.py, dashboard/test_needs.py, dashboard/test_reviewer_runs.py, dashboard/test_spend.py, dashboard/test_state.py, launcher/test_swarm.py  
> Closes #403 ## Stacked on #413 and #416 #403 waits on #401 (PR #416) and adds to `state.py` from #400 (PR #413); neither has merged. This branch is #416's branch with #413's merged in (one small conflict in `generate.main()`, resolved in c14dab4 so both the pages and `state.json` are written). **Thi …

Draft: capability, fix no. "The desk now opens with **On the floor** (`dashboard/floor.py`):"

label: capability
fix: no
hard:
reviewed: no

## pr-421 · dev · 2026-W45

[#421](https://github.com/open-agentos/productswarm/pull/421) Dashboard: live committee desk while a committee is open (#404)  
Linked issue: #404 Dashboard desk 5: live committee desk while a committee is open (#397)  
Paths touched (6): dashboard/README.md, dashboard/committees.py, dashboard/generate.py, dashboard/layout.py, dashboard/state.py, dashboard/test_committees.py  
> Closes #404 ## Stacked on #413 and #416 #404 waits on #401 (PR #416) and adds to `state.py` from #400 (PR #413); neither has merged. This branch starts from c14dab4, the same #416 + #413 merge #418 builds on. **This PR's own change is the last commit, 9f7684c.** Please merge #413 and #416 first; I'l …

Draft: capability, fix no. "`committees.desk()` draws each open committee at the top of the desk:"

label: capability
fix: no
hard:
reviewed: no

## pr-425 · dev · 2026-W45

[#425](https://github.com/open-agentos/productswarm/pull/425) Dashboard desk: what the numbers say, trend sentences with sparklines (#406)  
Linked issue: #406 Dashboard desk 7: what the numbers say, trend sentences with sparklines (#397)  
Paths touched (8): dashboard/README.md, dashboard/generate.py, dashboard/layout.py, dashboard/questions.py, dashboard/state.py, dashboard/test_rate.py, dashboard/test_trends.py, dashboard/trends.py  
> Closes #406 ## Stacked on #413 and #416 #406 waits on #401 (PR #416) and adds to `state.py` from #400 (PR #413); neither has merged. Like #418 and #421, this branch starts from c14dab4, the #416 + #413 merge. **This PR's own change is the last commit, a06f3af.** Please merge #413 and #416 first; I'l …

Draft: capability, fix no. "- **`dashboard/trends.py` (new)** fills the templates from those numbers:"

label: capability
fix: no
hard:
reviewed: no

## pr-428 · dev · 2026-W45

[#428](https://github.com/open-agentos/productswarm/pull/428) Dashboard desk: precedent in use, GOV citations by record and day (#408)  
Linked issue: #408 Dashboard desk 9: precedent in use, GOV citations by record and day (#397)  
Paths touched (10): dashboard/README.md, dashboard/generate.py, dashboard/layout.py, dashboard/precedent.py, dashboard/state.py, dashboard/test_committees.py, dashboard/test_generate.py, dashboard/test_precedent.py, dashboard/test_rate.py, dashboard/test_state.py  
> Closes #408 ## Stacked on #413 and #416 #408 waits on #401 (PR #416) and adds to `state.py` from #400 (PR #413). Neither has merged. Like #418 and #421, this branch starts from c14dab4, which merges those two. **This PR's own change is the last commit, 07d4c02.** Please merge #413 and #416 first. I' …

Draft: capability, fix no. "**`dashboard/precedent.py` (new)**, shown on the desk under the committees:"

label: capability
fix: no
hard:
reviewed: no

## pr-433 · dev · 2026-W45

[#433](https://github.com/open-agentos/productswarm/pull/433) Desk: how the questions went, asked by, decided by, became (#407)  
Linked issue: #407 Dashboard desk 8: how the questions went, asked by, decided by, became (#397)  
Paths touched (8): dashboard/README.md, dashboard/committees.py, dashboard/generate.py, dashboard/layout.py, dashboard/questions.py, dashboard/state.py, dashboard/test_committees.py, dashboard/test_went.py  
> Closes #407 Adds **How the questions went** to the desk, right after What the numbers say. It shows three breakdowns of the questions created in the window. Each one is a templated sentence plus a stacked bar of counts. - **Asked by:** the owner if the owner opened the question, or if the first word …

Draft: capability, fix no. "Adds **How the questions went** to the desk, right after What the numbers say."

label: capability
fix: no
hard:
reviewed: no

## pr-434 · dev · 2026-W45

[#434](https://github.com/open-agentos/productswarm/pull/434) Dashboard header: LIVE mark, build time and the owner's last act (#402)  
Linked issue: #402 Dashboard desk 3: header with LIVE mark, build time and the owner's last act (#397)  
Paths touched (7): dashboard/README.md, dashboard/activity.py, dashboard/generate.py, dashboard/layout.py, dashboard/state.py, dashboard/test_activity.py, dashboard/test_rate.py  
> Closes #402 ## What Every page's masthead now shows a red **LIVE** mark, `built HH:MM UTC`, and the owner's last act in owner amber, with a link. Against this repo just now: > LIVE · built 10:31 UTC · Owner last acted 8m ago: labelled [#411](https://github.com/open-agentos/productswarm/issues/411) ` …

Draft: capability, fix no. "Every page's masthead now shows a red **LIVE** mark, `built HH:MM UTC`, and the owner's last act in owner amber, with a link."

label: capability
fix: no
hard:
reviewed: no

## pr-437 · dev · 2026-W45

[#437](https://github.com/open-agentos/productswarm/pull/437) Dashboard desk 11: authority map page from jurisdictions.yml (#410)  
Linked issue: #410 Dashboard desk 11: authority map page from jurisdictions.yml (#397)  
Paths touched (6): dashboard/README.md, dashboard/authority.py, dashboard/generate.py, dashboard/layout.py, dashboard/test_authority.py, dashboard/test_generate.py  
> Adds `authority.html`, linked from every page's footer. It has one row per domain in `governance/jurisdictions.yml`. - **Row:** domain name, description and note ("always one-way" where the file says so), who decides (agents blue, owner amber, "nobody: ask" when `decide` is empty), owner, ratify, vo …

Draft: capability, fix no. "Adds `authority.html`, linked from every page's footer."

label: capability
fix: no
hard:
reviewed: no

## pr-438 · dev · 2026-W45

[#438](https://github.com/open-agentos/productswarm/pull/438) Desk live refresh: redraw panels from state.json every 15 seconds (#411)  
Linked issue: #411 Dashboard desk 12: refresh the desk from state.json, only if #396 allows (#397)  
Paths touched (9): dashboard/README.md, dashboard/generate.py, dashboard/layout.py, dashboard/live.py, dashboard/poll.js, dashboard/state.py, dashboard/test_committees.py, dashboard/test_generate.py, dashboard/test_live.py  
> Closes #411 An open desk now redraws itself from `state.json` every 15 seconds, without a reload. This follows the owner's option 2 on #396. **How** - `live.py` turns each desk panel's HTML, and the masthead, into a node tree in `state.json["desk"]`, using allow lists for tags, attributes and links. …

Draft: capability, fix no. "An open desk now redraws itself from `state.json` every 15 seconds, without a reload."

label: capability
fix: no
hard:
reviewed: no

## pr-463 · dev · 2026-W45

[#463](https://github.com/open-agentos/productswarm/pull/463) Add the designer role prompt  
Linked issue: #460 Add a designer role to the swarm  
Paths touched (2): launcher/test_swarm.py, roles/designer.md  
> Closes #460 Adds `roles/designer.md`, shaped like the other role prompts: the opener line, what the role does, and the Governance block copied from `roles/planner.md`. The designer reviews what the owner sees (hierarchy, density, empty states, mobile, contrast, dark mode, and whether a page shows at …

Draft: capability, fix no. "Adds `roles/designer.md`, shaped like the other role prompts: the opener line, what the role does, and the Governance block copied from `roles/planner.md`."

label: capability
fix: no
hard:
reviewed: no

## pr-477 · dev · 2026-W45

[#477](https://github.com/open-agentos/productswarm/pull/477) Make the designer a stronger user-experience voice  
Linked issue: #474 Make the designer a stronger user-experience voice  
Paths touched (1): roles/designer.md  
> Rewrites `roles/designer.md` so the designer owns the user experience, not only a visual check after the fact. **Kept:** the opener, "doesn't build", PR comments that never set a review state, briefs, the committee seat, the §8 note and the Governance block. **Added**, as checklists: - **Who and wha …

Draft: capability, fix no. "Rewrites `roles/designer.md` so the designer owns the user experience, not only a visual check after the fact."

label: capability
fix: no
hard:
reviewed: no

## pr-493 · dev · 2026-W45

[#493](https://github.com/open-agentos/productswarm/pull/493) GOV-0022: a PR merges without the owner's click only via an owner label and a merger in code  
Linked issue: #480 GOV-Q: How may a PR merge without the owner pressing the button?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0022-owner-labelled-merger.md  
> Ruling PR for #480, per GOV-0007. The owner answered "Option 2" on #480 and added `gov:ruled` and `ready` (I checked the issue's events: both were added by the owner). - `governance/decisions/GOV-0022-owner-labelled-merger.md`: the record. - `governance/INDEX.md`: its row. There was no draft record, …

Draft: governance, fix no. "Ruling PR for #480, per GOV-0007. The owner answered "Option 2" on #480 and added `gov:ruled` and `ready`"

label: governance
fix: no
hard:
reviewed: no

## pr-494 · dev · 2026-W45

[#494](https://github.com/open-agentos/productswarm/pull/494) [answer] starts the planner on owner-raised questions  
Linked issue: #455 Live activity 4: [answer] starts the planner on owner-raised questions; committee rounds start by hand (#444)  
Paths touched (5): PRODUCT.md, launcher/README.md, launcher/test_watch.py, launcher/watch.py, roles/planner.md  
> Closes #455 ## What - `watch.raised_by()` takes the owner's login. A "Raised by" that starts with `owner` or the owner's login (any case, with or without `@`, or in the `-- owner` form) maps to `planner`. Role-first fields work as before. Other askers are still skipped, now with the reason `doesn't  …

Draft: capability, fix no. "`roles/planner.md` gains a "Questions the owner raised" section."

label: capability
fix: no
hard:
reviewed: no

## pr-497 · dev · 2026-W45

[#497](https://github.com/open-agentos/productswarm/pull/497) swarm watch: a ruling starts the work ([answer] on gov:ruled)  
Linked issue: #495 swarm watch: a ruling starts the work ([answer] on gov:ruled; the planner opens the ruling's task issues)  
Paths touched (4): launcher/README.md, launcher/test_watch.py, launcher/watch.py, roles/planner.md  
> Closes #495 ## What - **`[answer]` on a ruling** (`launcher/watch.py`): when the owner adds `gov:ruled` to a question that is already `ready`, `[answer]` fires again with key `answer:N:<ruled event id>`. The key is whichever owner label event is later, so if the ruling came before `ready`, the `read …

Draft: capability, fix no. "open one unlabelled issue for each stage that can start now"

label: capability
fix: no
hard:
reviewed: no

## pr-500 · dev · 2026-W45

[#500](https://github.com/open-agentos/productswarm/pull/500) GOV-0023: roles may call other roles into a ready issue  
Linked issue: #498 GOV-Q: How may a role call in other roles to contribute?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0023-agents-call-in-roles.md  
> Records the owner's answer on #498 ("Confirmed, go with Option 3") as GOV-0023, and adds its row to `governance/INDEX.md`. Closes #498 **Why a record:** #498 isn't `governance`, one-way or external, so the watcher's `[record]` check wouldn't flag it. It gets a record because the owner started docs o …

Draft: governance, fix no. "Records the owner's answer on #498 ("Confirmed, go with Option 3") as GOV-0023, and adds its row to `governance/INDEX.md`."

label: governance
fix: no
hard:
reviewed: no

## pr-503 · dev · 2026-W45

[#503](https://github.com/open-agentos/productswarm/pull/503) swarm watch: [record] fires when the owner's ruling asks for a record  
Linked issue: #501 swarm watch: [record] fires when the owner's ruling asks for a record  
Paths touched (4): launcher/README.md, launcher/test_watch.py, launcher/watch.py, roles/docs.md  
> Closes #501 ## What GOV-0007 counts a question as needing a record when the owner says so in the answer. `swarm watch` couldn't see that case, so a two-way ruling that asked for a record started nothing (#498 needed docs started by hand, PR #500). - `watch.needs_record(body, comments, owner)` also r …

Draft: capability, fix no. "`watch.needs_record(body, comments, owner)` also returns `the owner asked in the answer` when a comment **by the owner** has a line `Record: yes` on its own"

label: capability
fix: no
hard:
reviewed: no

## pr-505 · dev · 2026-W45

[#505](https://github.com/open-agentos/productswarm/pull/505) Record GOV-0024: every swarm App is a trusted author for the Actions reviewer  
Linked issue: #491 GOV-Q: Should the Actions reviewer review PRs from the analyst and designer Apps?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0024-every-swarm-app-trusted-author.md  
> Closes #491 Adds `governance/decisions/GOV-0024-every-swarm-app-trusted-author.md` and its row in `governance/INDEX.md`, from the owner's option 4 comment on #491 and "Confirmed, go with Option 4". There was no draft record. ## How the record differs from the answer - **Amends GOV-0017's trust list. …

Draft: governance, fix no. "Adds `governance/decisions/GOV-0024-every-swarm-app-trusted-author.md` and its row in `governance/INDEX.md`, from the owner's option 4 comment on #491"

label: governance
fix: no
hard:
reviewed: no

## pr-508 · dev · 2026-W45

[#508](https://github.com/open-agentos/productswarm/pull/508) Actions reviewer: read trusted PR authors from jurisdictions.yml  
Linked issue: #506 Actions reviewer: read trusted PR authors from jurisdictions.yml (#491, Option 4)  
Paths touched (3): launcher/README.md, launcher/actions_review.py, launcher/test_actions_review.py  
> Closes #506 ## What `plan` no longer uses a hard-coded `AUTHORS` set (planner, builder, docs). It trusts every login under `identities.agents` in `governance/jurisdictions.yml`, as #491 ruled (Option 4). PRs from the analyst and designer now get an Actions review. A role added to `identities.agents` …

Draft: upkeep, fix no. "`plan` no longer uses a hard-coded `AUTHORS` set (planner, builder, docs)."

label: upkeep
fix: no
hard:
reviewed: no

## pr-511 · dev · 2026-W45

[#511](https://github.com/open-agentos/productswarm/pull/511) swarm watch: skip a bad swarm.toml entry instead of starting nothing  
Linked issue: #487 swarm watch: skip a bad swarm.toml entry instead of starting nothing, and stop pinning the role list in tests  
Paths touched (7): launcher/README.md, launcher/actions_review.py, launcher/manifest.py, launcher/swarm.py, launcher/test_manifest.py, launcher/test_watch.py, launcher/watch.py  
> Closes #487 ## What changed - **`launcher/manifest.py`**: new `parse_valid()`; `load_all()` now returns `(sessions, limits, problems)`: the sessions from the valid `[[session]]` entries and one problem per bad entry. It still raises `ManifestError` if the file can't be read, isn't TOML, or has a bad …

Draft: capability, fix no. "each tick prints every problem, prefixed `swarm.toml:`, then carries on with the valid entries (dry run and real starts)"

label: capability
fix: no
hard:
reviewed: no

## pr-513 · dev · 2026-W45

[#513](https://github.com/open-agentos/productswarm/pull/513) swarm watch: list a trigger a live session holds, and say when it is stale  
Linked issue: #488 swarm watch: say when a live session holds a trigger, and warn when that session is stale  
Paths touched (4): launcher/README.md, launcher/manifest.py, launcher/test_watch.py, launcher/watch.py  
> Closes #488 ## What changed - **Held, not dropped.** `triggers()` used to leave out any `[record]`, `[answer]`, `[build]` or `[respond]` trigger on an issue a live session held. Now it returns the trigger with a `held` reason from the new pure `held_by()`, which reads the same sessions as `swarm.hol …

Draft: capability, fix no. "`swarm watch` (real) lists it in `swarm inbox` as a hold."

label: capability
fix: no
hard:
reviewed: no

## pr-523 · dev · 2026-W45

[#523](https://github.com/open-agentos/productswarm/pull/523) Needs you: leave out idle sessions and gov:ruled questions  
Linked issue: #469 Digest: 22 of 26 needs-you items are idle sessions, most with "no event since never"  
Paths touched (6): dashboard/README.md, dashboard/generate.py, dashboard/test_digest.py, dashboard/test_needs.py, launcher/README.md, launcher/watch.py  
> Closes #469 ## What changes `needs_you()` in `dashboard/generate.py` feeds the digest, the page and `swarm inbox`. It now: - **drops the `idle` kind.** Idle sessions belong in `swarm ls` and the floor. `blocked` and `over_cap` stay. - **leaves out questions the owner has labelled `gov:ruled`.** Thei …

Draft: upkeep, fix no. "drops the `idle` kind."

label: upkeep
fix: no
hard:
reviewed: no

## pr-534 · dev · 2026-W45

[#534](https://github.com/open-agentos/productswarm/pull/534) Rewrite PRODUCT.md around the department goal (#526)  
Linked issue: #528 Rewrite PRODUCT.md around the department goal (#526)  
Paths touched (1): PRODUCT.md  
> Closes #528 Rewrites `PRODUCT.md` around the owner's direction on #526 (Option 2, "the department that reports to you"). #526 is `gov:ruled` with no record, so the brief cites it as direction for that question only (GOV-0006) and says so at the top. **What's in it, per #528's scope:** - **Problem, u …

Draft: governance, fix no. "Each row says which ruling it still needs."

label: governance
fix: no
hard:
reviewed: no

## pr-539 · dev · 2026-W45

[#539](https://github.com/open-agentos/productswarm/pull/539) swarm watch: a [call-in] trigger for a "Call in:" line (GOV-0023)  
Linked issue: #520 swarm watch: a [call-in] trigger for a "Call in:" line (GOV-0023)  
Paths touched (9): launcher/README.md, launcher/manifest.py, launcher/stophook.py, launcher/swarm.py, launcher/test_manifest.py, launcher/test_stophook.py, launcher/test_swarm.py, launcher/test_watch.py, launcher/watch.py  
> Adds GOV-0023's `[call-in]` trigger to `swarm watch`. A `Call in: <role>, <role>: <why>` line on an owner-`ready` issue now starts each named role once. **Switch to commit (`swarm.toml` is yours):** I propose `call_ins` in `[watch]`, **default false**. Add `call_ins = true` to turn call-ins on. Off  …

Draft: capability, fix no. "Adds GOV-0023's `[call-in]` trigger to `swarm watch`. A `Call in: <role>, <role>: <why>` line on an owner-`ready` issue now starts each named role once."

label: capability
fix: no
hard:
reviewed: no

## pr-544 · dev · 2026-W45

[#544](https://github.com/open-agentos/productswarm/pull/544) Heartbeat comments name their issue so its timeline shows the session (#453)  
Linked issue: #453 Live activity 2: the heartbeat names its issue so the issue's timeline shows the session (#444)  
Paths touched (4): heartbeat/SCHEMA.md, heartbeat/examples/tracking-comment.md, heartbeat/hook.py, heartbeat/test_hook.py  
> Heartbeat comments now name their issue in prose above the `jsonl` fence, so the issue's timeline shows a "mentioned this" reference to the session's tracking issue. - `heartbeat/hook.py`: `flush()` adds `builder session working on #N` / `builder opened PR #P for #N` for `working_on` / `pr_opened` e …

Draft: capability, fix no. "Heartbeat comments now name their issue in prose above the `jsonl` fence, so the issue's timeline shows a "mentioned this" reference to the session's tracking issue."

label: capability
fix: no
hard:
reviewed: no

## pr-546 · dev · 2026-W45

[#546](https://github.com/open-agentos/productswarm/pull/546) swarm watch keeps a no-cost public form of its state (#456)  
Linked issue: #456 Live activity 5: swarm watch keeps a no-cost public form of its state (#444)  
Paths touched (3): launcher/README.md, launcher/test_watch.py, launcher/watch.py  
> Closes #456 `swarm watch` now writes `watch-public.json` beside `watch.json` after every check (not `--dry-run`), with the same atomic write. Nothing publishes it yet; that's a later issue under #444. - `watch.public_state(st, live, now)` is pure and returns `checked`, `running` (role, kind, ref, st …

Draft: capability, fix no. "`swarm watch` now writes `watch-public.json` beside `watch.json` after every check (not `--dry-run`), with the same atomic write."

label: capability
fix: no
hard:
reviewed: no

## pr-555 · dev · 2026-W45

[#555](https://github.com/open-agentos/productswarm/pull/555) swarm status: the watcher's state with cost, local and instant (#457)  
Linked issue: #457 Live activity 6: swarm status, the watcher's state with cost, local and instant (#444)  
Paths touched (5): launcher/README.md, launcher/swarm, launcher/swarm.py, launcher/test_swarm.py, launcher/watch.py  
> Closes #457 `launcher/swarm status` prints what `swarm watch` is doing, with cost, from local files only. It makes no GitHub call. On this machine it ran in 0.14s. - **First line:** whether a `swarm watch` holds `watch.lock`, and when it last checked. The check is marked `stale` once it is more than …

Draft: capability, fix no. "`launcher/swarm status` prints what `swarm watch` is doing, with cost, from local files only."

label: capability
fix: no
hard:
reviewed: no

## pr-564 · dev · 2026-W45

[#564](https://github.com/open-agentos/productswarm/pull/564) GOV-0025: watcher publishes as the owner's gh login, [watch] issue body only (#451)  
Linked issue: #451 GOV-Q: Which identity publishes swarm watch's state to GitHub?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0025-watcher-publishes-as-owner-login.md  
> Ruling record for #451, written from the owner's answer ("Option 1 … Record: yes"). The question had no separate draft record, so the record follows the question's options, its recommendation and the owner's answer. Adds `governance/decisions/GOV-0025-watcher-publishes-as-owner-login.md` and its row …

Draft: governance, fix no. "Ruling record for #451, written from the owner's answer ("Option 1 … Record: yes")."

label: governance
fix: no
hard:
reviewed: no

## pr-566 · dev · 2026-W45

[#566](https://github.com/open-agentos/productswarm/pull/566) The desk's floor shows swarm watch's state (#459)  
Linked issue: #459 Live activity 8: the desk's floor shows the watcher's state (#444)  
Paths touched (7): dashboard/README.md, dashboard/floor.py, dashboard/generate.py, dashboard/layout.py, dashboard/state.py, dashboard/test_floor.py, dashboard/test_state.py  
> Closes #459 The floor now has a "The watcher" block under the cards, drawn from the `[watch]` issue (#458): "builder on #405 since 11:09", "held: #407, 2 of 2 running", "skipped: #439, …", "failed: #51 build, at its cap, 10:02". - **No API calls.** The issue's body comes with the open-issue list the …

Draft: capability, fix no. "The floor now has a "The watcher" block under the cards, drawn from the `[watch]` issue (#458)"

label: capability
fix: no
hard:
reviewed: no

## pr-569 · dev · 2026-W45

[#569](https://github.com/open-agentos/productswarm/pull/569) Update GOVERNANCE.md  
Linked issue: #567 GOVERNANCE.md §6: a ruling that needs a record is a PR (owner step)  
Paths touched (1): GOVERNANCE.md  
> Closes #567 > A ruling that needs a record is a PR that adds governance/decisions/GOV-NNNN-<slug>.md (copied from GOV-0000-template.md), updates governance/INDEX.md, and closes the question issue. A question needs a record when it is in the governance domain, rated one-way or external, in a domain g …

Draft: governance, fix no. "Paths touched (1): GOVERNANCE.md"

label: governance
fix: no
hard:
reviewed: no

## pr-598 · dev · 2026-W45

[#598](https://github.com/open-agentos/productswarm/pull/598) Add PLAN.md: the goal and milestones M1–M4  
Linked issue: #574 Add PLAN.md: the goal and milestones M1–M4 (#526)  
Paths touched (2): PLAN.md, PRODUCT.md  
> Adds `PLAN.md` as #574 specifies: a header with the goal, its done line and a link to `PRODUCT.md`'s "On track at day 30" checks as the scorecard; M1–M4, each with **Outcome**, **Date**, **Done test**, **Owner role** and **Needs**, as in the issue's table; and the change rule. `PRODUCT.md`'s "Milest …

Draft: knowledge, fix no. "Adds `PLAN.md` as #574 specifies: a header with the goal, its done line"

label: knowledge
fix: no
hard:
reviewed: no

## pr-603 · dev · 2026-W45

[#603](https://github.com/open-agentos/productswarm/pull/603) Merger: decide merge or miss per PR under GOV-0027 (read-only)  
Linked issue: #589 Merger: decide merge or miss per PR under GOV-0027 (read-only)  
Paths touched (4): launcher/README.md, launcher/manifest.py, launcher/merger.py, launcher/test_merger.py  
> Closes #589 **Milestone:** M2 Adds `launcher/merger.py plan [--pr N] [--manifest PATH] [--repo OWNER/NAME]`: one line per open PR, `merge (standing grant)`, `merge (approved ask)` or `miss: <first failed condition>`. Read-only, in the shape of `actions_review.py plan` (GOV-0020); no comments, no mer …

Draft: capability, fix no. "Adds `launcher/merger.py plan [--pr N] [--manifest PATH] [--repo OWNER/NAME]`: one line per open PR, `merge (standing grant)`, `merge (approved ask)` or `miss: <first failed condition>`."

label: capability
fix: no
hard:
reviewed: no

## pr-605 · dev · 2026-W45

[#605](https://github.com/open-agentos/productswarm/pull/605) Add GOV-0028: merger App permissions and ruleset bypass (#601)  
Linked issue: #601 GOV-Q: What may the merger App do, and how does it get past the main ruleset?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0028-merger-app-bypass-actor.md  
> Records the owner's answer on #601 ("Confirmed. Option 1.") as GOV-0028, per GOV-0007. It is `one-way`, so it needs a record. - `governance/decisions/GOV-0028-merger-app-bypass-actor.md` - `governance/INDEX.md`: new row **How the record differs from the question's option 1** (there was no draft reco …

Draft: governance, fix no. "Records the owner's answer on #601 ("Confirmed. Option 1.") as GOV-0028, per GOV-0007."

label: governance
fix: no
hard:
reviewed: no

## pr-607 · dev · 2026-W45

[#607](https://github.com/open-agentos/productswarm/pull/607) Merger: shadow comments and live merges (GOV-0027, #592)  
Linked issue: #592 Merger: shadow comments and live merges (GOV-0027)  
Paths touched (3): launcher/README.md, launcher/merger.py, launcher/test_merger.py  
> Closes #592 Adds `python3 launcher/merger.py run [--dry-run]`: stage 2 of GOV-0027. It runs #589's `plan`, then acts on each decision per `[merger] mode`. ## What it does - **shadow:** on a merge, `Would merge (standing grant | approved ask) at <sha>.` once per head. On a miss for a PR the reviewer  …

Draft: capability, fix no. "Adds `python3 launcher/merger.py run [--dry-run]`: stage 2 of GOV-0027."

label: capability
fix: no
hard:
reviewed: no

## pr-612 · dev · 2026-W45

[#612](https://github.com/open-agentos/productswarm/pull/612) Update CLAUDE.md  
Linked issue: none  
Paths touched (1): CLAUDE.md  
> Accommodate the new merger agent

Draft: upkeep, fix no. "Accommodate the new merger agent"

label: upkeep
fix: no
hard:
reviewed: no

## pr-613 · dev · 2026-W45

[#613](https://github.com/open-agentos/productswarm/pull/613) Update README.md  
Linked issue: none  
Paths touched (1): README.md  
> remove reference to dead repo

Draft: knowledge, fix no. "remove reference to dead repo"

label: knowledge
fix: no
hard:
reviewed: no

## pr-615 · dev · 2026-W45

[#615](https://github.com/open-agentos/productswarm/pull/615) swarm watch: [build] on issues that are go by milestone (GOV-0026)  
Linked issue: #583 swarm watch: [build] on issues that are go by milestone (GOV-0026)  
Paths touched (3): launcher/README.md, launcher/test_watch.py, launcher/watch.py  
> Closes #583 **Milestone:** no milestone yet (`PLAN.md`, #574, isn't on `main`), as on #583. Stage 2 of GOV-0026: `swarm watch` starts `[build]` on an issue that is go by its `PLAN.md` milestone, as it does on a `ready` one (per GOV-0026, which amends GOV-0009). ## What changed - **`launcher/watch.py …

Draft: capability, fix no. "Stage 2 of GOV-0026: `swarm watch` starts `[build]` on an issue that is go by its `PLAN.md` milestone, as it does on a `ready` one"

label: capability
fix: no
hard:
reviewed: no

## pr-618 · dev · 2026-W45

[#618](https://github.com/open-agentos/productswarm/pull/618) GOV-0029: swarm watch triggers for daily report, Ask, Research and milestone call-ins (#577)  
Linked issue: #577 GOV-Q: Should swarm watch start the lead daily, and start roles on Ask:, Research: and milestone call-ins?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0029-lead-daily-ask-research-triggers.md  
> Ruling record for #577: GOV-0029, option 2 (all four triggers), per GOV-0007. The owner answered "Confirmed. Option 2." and `Record: yes`. Adds `governance/decisions/GOV-0029-lead-daily-ask-research-triggers.md` and its `governance/INDEX.md` row. There was no draft record, so it is written from the  …

Draft: governance, fix no. "Ruling record for #577: GOV-0029, option 2 (all four triggers), per GOV-0007."

label: governance
fix: no
hard:
reviewed: no

## pr-620 · dev · 2026-W45

[#620](https://github.com/open-agentos/productswarm/pull/620) swarm watch: [daily] starts the planner for the daily report (GOV-0029)  
Linked issue: #588 swarm watch: [daily] starts the planner for the daily report and Monday check-in (#577)  
Paths touched (10): launcher/README.md, launcher/manifest.py, launcher/stophook.py, launcher/swarm.py, launcher/test_manifest.py, launcher/test_stophook.py, launcher/test_swarm.py, launcher/test_watch.py, launcher/watch.py, swarm.toml  
> **Milestone:** M1 (daily report runs without the owner). This is M1's trigger. Builds `[daily]` per GOV-0029 (#577, option 2). Its blockers #574 and #577 are closed, and the owner added `ready`. ## What changed - **Settings** (`launcher/manifest.py`): three new optional keys in `[watch]`: - `daily`: …

Draft: capability, fix no. "Builds `[daily]` per GOV-0029 (#577, option 2)."

label: capability
fix: no
hard:
reviewed: no

## pr-631 · dev · 2026-W45

[#631](https://github.com/open-agentos/productswarm/pull/631) Update merger.yml  
Linked issue: #630 merger.yml: run the merger when a PR is approved or its Tests run finishes  
Paths touched (1): .github/workflows/merger.yml  
> Closes https://github.com/open-agentos/productswarm/issues/630

Draft: upkeep, fix no. "Closes https://github.com/open-agentos/productswarm/issues/630"

label: upkeep
fix: no
hard:
reviewed: no

## pr-636 · dev · 2026-W45

[#636](https://github.com/open-agentos/productswarm/pull/636) swarm watch: call-ins count on milestone issues, not only ready ones (#594)  
Linked issue: #594 swarm watch: call-ins count on milestone issues, not only ready ones (#577)  
Paths touched (3): launcher/README.md, launcher/test_watch.py, launcher/watch.py  
> Closes #594 Stage 4 of #577, per GOV-0029: `Call in:` lines now count on an issue under an open `PLAN.md` milestone as well as on a `ready` one. The rest of GOV-0023 is unchanged: who may call, no self-call, each role once per call, 2 calls per issue per UTC day, and the one `call_ins` switch. ## Wh …

Draft: capability, fix no. "`triggers()` still counts the owner's `ready` issues. It also counts an open, non-question, non-tracking issue that the new `call_milestone()` passes."

label: capability
fix: no
hard:
reviewed: no

## pr-638 · dev · 2026-W45

[#638](https://github.com/open-agentos/productswarm/pull/638) PRODUCT.md: Q2, Q3 and Q4 are in force (GOV-0026, GOV-0027, GOV-0029)  
Linked issue: #627 PRODUCT.md: Q2 is in force as GOV-0026  
Paths touched (1): PRODUCT.md  
> Closes #627 **Milestone:** none. This is a docs fix with no milestone in `PLAN.md`, and the owner labelled #627 `ready`. ## What `PRODUCT.md` still treated Q2, Q3 and Q4 as rulings to come. All three are in force now, so this PR updates the brief to match: - **Status line:** "Q2–Q5 rulings to come"  …

Draft: governance, fix no. "All three are in force now, so this PR updates the brief to match:"

label: governance
fix: no
hard:
reviewed: no

## pr-640 · dev · 2026-W45

[#640](https://github.com/open-agentos/productswarm/pull/640) Update swarm.toml  
Linked issue: none  
Paths touched (1): swarm.toml  
> Kicking off the auto-generating reports

Draft: capability, fix no. "Kicking off the auto-generating reports"

label: capability
fix: no
hard:
reviewed: no

## pr-643 · dev · 2026-W45

[#643](https://github.com/open-agentos/productswarm/pull/643) GOV-0030: productswarm's goal is the department that reports to the owner  
Linked issue: #526 GOV-Q: What is productswarm for, and how does the owner run the swarm?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0030-department-that-reports-to-the-owner.md  
> Ruling record for #526, transcribed from the owner's answers ("Confirmed Option 2. C becomes its finish line (the readiness review), and B follows once a named peer asks." and the later `Record: yes` comment) and the question's proposal (per GOV-0007). Merging it ratifies. Closes #526 **Milestone:** …

Draft: governance, fix no. "Ruling record for #526, transcribed from the owner's answers"

label: governance
fix: no
hard:
reviewed: no

## pr-645 · dev · 2026-W45

[#645](https://github.com/open-agentos/productswarm/pull/645) roles: drop the pending notes for [ask] and milestone call-ins  
Linked issue: #639 Role prompts and PLAN.md still say GOV-0029's triggers and Q3/Q4 are pending  
Paths touched (6): roles/analyst.md, roles/builder.md, roles/designer.md, roles/docs.md, roles/planner.md, roles/reviewer.md  
> Closes #639 `[ask]` (#590) and milestone call-ins (#594) are on `main`, so the role prompts no longer call them pending: - `analyst`, `builder`, `designer`, `docs`, `planner`, `reviewer`: "Until `[ask]` ships…" now says `[ask]` starts these runs, and the owner starts them by hand only with the `asks …

Draft: upkeep, fix no. "docs fix (as the issue says)"

label: upkeep
fix: no
hard:
reviewed: no

## pr-646 · dev · 2026-W45

[#646](https://github.com/open-agentos/productswarm/pull/646) Revert "Update swarm.toml"  
Linked issue: none  
Paths touched (1): swarm.toml  
> Reverts open-agentos/productswarm#640

Draft: upkeep, fix no. "Reverts open-agentos/productswarm#640"

label: upkeep
fix: no
hard:
reviewed: no

## pr-653 · dev · 2026-W45

[#653](https://github.com/open-agentos/productswarm/pull/653) Merger: treat PLAN.md as a protected path until it is retired  
Linked issue: #652 Merger: treat PLAN.md as a protected path until it is retired  
Paths touched (3): launcher/README.md, launcher/merger.py, launcher/test_merger.py  
> Closes #652 Adds `PLAN.md` to `PROTECTED_FILES` in `launcher/merger.py`. A PR that touches it now needs the owner's approval at head (an approved ask, GOV-0027) and can't merge under a standing grant. Without this, an agent PR that adds a milestone could make its own issues go under GOV-0026. - `lau …

Draft: upkeep, fix no. "Adds `PLAN.md` to `PROTECTED_FILES` in `launcher/merger.py`."

label: upkeep
fix: no
hard:
reviewed: no

## pr-655 · dev · 2026-W46

[#655](https://github.com/open-agentos/productswarm/pull/655) GOV-0032: adopt operating model v2  
Linked issue: #651 GOV-Q: Do we adopt operating model v2 (hosted engine, org Project as the plan, learning loop)?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0032-operating-model-v2.md  
> Records the owner's ruling on #651 ("Confirmed. Option 2." with `Record: yes`) as `governance/decisions/GOV-0032-operating-model-v2.md`, and adds its row to `governance/INDEX.md`. Closes #651 **Where the record differs from the question and the answer.** There was no draft record, so I wrote it from …

Draft: governance, fix no. "Records the owner's ruling on #651 ("Confirmed. Option 2." with `Record: yes`) as `governance/decisions/GOV-0032-operating-model-v2.md`, and adds its row to `governance/INDEX.md`."

label: governance
fix: no
hard:
reviewed: no

## pr-666 · dev · 2026-W46

[#666](https://github.com/open-agentos/productswarm/pull/666) swarm webhooks: verify, record and nudge on GitHub App webhooks  
Linked issue: #658 Webhook receiver: verify, dedupe, queue, nudge  
Paths touched (4): launcher/README.md, launcher/swarm.py, launcher/test_webhooks.py, launcher/webhooks.py  
> Closes #658 Adds `swarm webhooks`, the receiver for GitHub App webhooks on the engine host (operating model v2, #651). A webhook only nudges: the receiver checks the signature, records the delivery and touches `~/.productswarm/launcher/nudge`. It never trusts a payload for who did what and never sta …

Draft: capability, fix no. "Adds `swarm webhooks`, the receiver for GitHub App webhooks on the engine host (operating model v2, #651)."

label: capability
fix: no
hard:
reviewed: no

## pr-668 · dev · 2026-W46

[#668](https://github.com/open-agentos/productswarm/pull/668) GOV-0031: an owner-opened Goal or Area is the go; PLAN.md retired  
Linked issue: #667 Record GOV-0031: an owner-opened Goal or Area is the go; PLAN.md retired  
Paths touched (3): governance/INDEX.md, governance/decisions/GOV-0026-milestone-is-go.md, governance/decisions/GOV-0031-goal-or-area-is-go.md  
> Closes #667 Adds GOV-0031, the separate ruling #651 names for retiring `PLAN.md`. It is Draft B from the operating model v2 design, written by the owner, so there was no transcription from an answer. It sits beside docs' GOV-0032 (#655), which records #651's architecture answer and leaves this numbe …

Draft: governance, fix no. "Adds GOV-0031, the separate ruling #651 names for retiring `PLAN.md`."

label: governance
fix: no
hard:
reviewed: no

## pr-670 · dev · 2026-W46

[#670](https://github.com/open-agentos/productswarm/pull/670) GOV-0033: no daily, per-mission or monthly engine spend total for now  
Linked issue: #656 GOV-Q: Do we add daily, per-mission and monthly spend totals for the hosted engine?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0033-no-engine-spend-totals.md  
> Records the owner's answer on #656 ("Option 1 for now") as GOV-0033 and adds its row to `governance/INDEX.md`. It needs a record because the question is rated `external` (GOV-0007). Closes #656 **How the record differs from the answer.** There was no draft record, so this follows the owner's answer  …

Draft: governance, fix no. "Records the owner's answer on #656 ("Option 1 for now") as GOV-0033 and adds its row to `governance/INDEX.md`."

label: governance
fix: no
hard:
reviewed: no

## pr-672 · dev · 2026-W46

[#672](https://github.com/open-agentos/productswarm/pull/672) swarm watch keeps its state in swarm.db; swarm backup  
Linked issue: #659 Watcher state moves from watch.json to SQLite  
Paths touched (7): launcher/README.md, launcher/statedb.py, launcher/swarm.py, launcher/test_cost.py, launcher/test_statedb.py, launcher/test_watch.py, launcher/watch.py  
> Closes #659 `swarm watch`'s state moves from `watch.json` to tables in `~/.productswarm/launcher/swarm.db`, the database the webhook receiver (#658) already writes. The meaning is unchanged. This is the second step of the VPS engine (operating model v2, GOV-0032); #660 builds on it. **Changes** - `l …

Draft: upkeep, fix no. "The meaning is unchanged. This is the second step of the VPS engine (operating model v2, GOV-0032); #660 builds on it."

label: upkeep
fix: no
hard:
reviewed: no

## pr-675 · dev · 2026-W46

[#675](https://github.com/open-agentos/productswarm/pull/675) swarm watch --serve: check on each webhook nudge; the owner's swarm:halt  
Linked issue: #660 The watcher as an always-on service, woken by webhooks  
Paths touched (4): launcher/README.md, launcher/swarm.py, launcher/test_serve.py, launcher/watch.py  
> Closes #660 **Stacked on #672** (#659). The base is `owner/659-watch-sqlite`, so the diff shows only #660. Merge #672 first, and GitHub moves this PR's base to `main`. `swarm watch --serve` is the always-on watcher for the engine host (operating model v2, GOV-0032). It checks on each webhook nudge a …

Draft: capability, fix no. "`swarm watch --serve` is the always-on watcher for the engine host (operating model v2, GOV-0032)."

label: capability
fix: no
hard:
reviewed: no

## pr-677 · dev · 2026-W46

[#677](https://github.com/open-agentos/productswarm/pull/677) ops/vps: provisioning, Caddy and systemd units for the engine host  
Linked issue: #657 VPS provisioning scripts (owner commits under ops/)  
Paths touched (7): ops/vps/Caddyfile, ops/vps/README.md, ops/vps/provision.sh, ops/vps/systemd/productswarm-backup.service, ops/vps/systemd/productswarm-backup.timer, ops/vps/systemd/productswarm-watch.service, ops/vps/systemd/productswarm-webhooks.service  
> Closes #657

Draft: upkeep, fix no. "Title: ops/vps: provisioning, Caddy and systemd units for the engine host"

label: upkeep
fix: no
hard:
reviewed: no

## pr-679 · dev · 2026-W46

[#679](https://github.com/open-agentos/productswarm/pull/679) swarm watch --container: each run in its own container from a pinned image  
Linked issue: #661 Role sessions in containers  
Paths touched (6): launcher/README.md, launcher/container/Dockerfile, launcher/container/entrypoint.sh, launcher/swarm.py, launcher/test_swarm.py, launcher/watch.py  
> Closes #661 Part of operating model v2 (#651, GOV-0032). ## What it does `swarm watch --container IMAGE` starts each run in its own container instead of a Terminal window. It is meant for the engine host, with `--serve`. Runs started by `swarm up` and `swarm launch` are unchanged. - **Pinned image o …

Draft: capability, fix no. "`swarm watch --container IMAGE` starts each run in its own container instead of a Terminal window."

label: capability
fix: no
hard:
reviewed: no

## pr-689 · dev · 2026-W46

[#689](https://github.com/open-agentos/productswarm/pull/689) swarm desk: the Desk served live on the engine host  
Linked issue: #664 The Desk served live on the VPS  
Paths touched (7): dashboard/README.md, dashboard/generate.py, dashboard/test_generate.py, launcher/README.md, launcher/desk.py, launcher/swarm.py, launcher/test_desk.py  
> Closes #664 **Goal:** M3, The Desk shows the plan and the report (#685). Go per GOV-0031: owner-opened, under that open Goal, and blocker #657 closed. `swarm desk` serves the Desk on 127.0.0.1:8080, where Caddy already proxies (`ops/vps/Caddyfile`). - **Nudge only.** It runs `dashboard/generate.py`, …

Draft: capability, fix no. "`swarm desk` serves the Desk on 127.0.0.1:8080, where Caddy already proxies (`ops/vps/Caddyfile`)."

label: capability
fix: no
hard:
reviewed: no

## pr-699 · dev · 2026-W46

[#699](https://github.com/open-agentos/productswarm/pull/699) GOV-0034: work that is go under GOV-0031 counts for GOV-0027's standing grant  
Linked issue: #696 GOV-Q: Does work that is go under GOV-0031 count as approved for GOV-0027's standing grant?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0034-go-work-counts-for-standing-grant.md  
> Records the owner's ruling on #696 as `governance/decisions/GOV-0034-go-work-counts-for-standing-grant.md` and adds its row to `governance/INDEX.md`. The owner answered "Option 3" and added `gov:ruled`. The question is `one-way` in the `security` domain, so it needs a record. There was no draft reco …

Draft: governance, fix no. "Records the owner's ruling on #696 as `governance/decisions/GOV-0034-go-work-counts-for-standing-grant.md` and adds its row to `governance/INDEX.md`."

label: governance
fix: no
hard:
reviewed: no

## pr-718 · dev · 2026-W46

[#718](https://github.com/open-agentos/productswarm/pull/718) swarm daily: count the M1 streak from swarm.db  
Linked issue: #707 swarm daily: count the M1 streak from swarm.db  
Paths touched (3): launcher/README.md, launcher/swarm.py, launcher/test_daily.py  
> Closes #707 **Milestone:** M1, the daily report runs without the owner (#683). #707 is go under GOV-0031: the planner App opened it as a Task under the owner's open Goal #683, it has no blocked-by issues and no veto. ## What `launcher/swarm daily` prints, for each of the last 10 working days (Mon–Fr …

Draft: capability, fix no. "`launcher/swarm daily` prints, for each of the last 10 working days"

label: capability
fix: no
hard:
reviewed: no

## pr-724 · dev · 2026-W46

[#724](https://github.com/open-agentos/productswarm/pull/724) Daily report: name M1's working day and flag Goal edits not made by the owner  
Linked issue: #709 Daily report: name M1's working day and flag Goal edits not made by the owner  
Paths touched (5): launcher/README.md, launcher/swarm.py, launcher/test_daily.py, launcher/test_swarm.py, roles/planner.md  
> Closes #709 **Milestone:** M1, the daily report runs without the owner (#683). #709 is go under GOV-0031: the planner App opened it as a Task under the owner's open Goal #683, its one blocked-by issue (#707) is closed, and there's no veto. ## What `launcher/swarm daily` (#707) now ends with two more …

Draft: capability, fix no. "`launcher/swarm daily` (#707) now ends with two more parts. The planner reads both."

label: capability
fix: no
hard:
reviewed: no

## pr-729 · dev · 2026-W46

[#729](https://github.com/open-agentos/productswarm/pull/729) Desk: plan panel and today's-report panel  
Linked issue: #712 Desk: plan panel and today's-report panel  
Paths touched (9): dashboard/README.md, dashboard/generate.py, dashboard/layout.py, dashboard/plan.py, dashboard/report.py, dashboard/state.py, dashboard/test_plan.py, dashboard/test_rate.py, dashboard/test_report.py  
> Closes #712 Under M3, #685. Go per GOV-0031: a Task the planner opened under the owner's Goal #685, with its blocker #711 closed. ## What Two new desk panels from #711's spec (`dashboard/README.md`), drawn first, above the floor: - **Today's report** (`dashboard/report.py`). Reads the planner's newe …

Draft: capability, fix no. "Two new desk panels from #711's spec (`dashboard/README.md`), drawn first, above the floor:"

label: capability
fix: no
hard:
reviewed: no

## pr-732 · dev · 2026-W46

[#732](https://github.com/open-agentos/productswarm/pull/732) Runs ledger and swarm spent (#662)  
Linked issue: #662 Cost ledger and engine totals  
Paths touched (8): launcher/README.md, launcher/ledger.py, launcher/statedb.py, launcher/swarm.py, launcher/test_ledger.py, launcher/test_serve.py, launcher/test_watch.py, launcher/watch.py  
> Closes #662 **Plan:** #662 is go because the owner added `ready` to it (GOV-0006). It isn't a sub-issue of a Goal or Area. The closest one is the Engine host Area (#687). ## What it does - **`runs` ledger** (`launcher/ledger.py`, a new table in `swarm.db`). Each check, `swarm watch` adds every ended …

Draft: capability, fix no. "**`swarm spent`** prints:"

label: capability
fix: no
hard:
reviewed: no

## pr-745 · dev · 2026-W46

[#745](https://github.com/open-agentos/productswarm/pull/745) merger: enqueue instead of merging when main requires a merge queue  
Linked issue: #663 The merger goes through the merge queue  
Paths touched (3): launcher/README.md, launcher/merger.py, launcher/test_merger.py  
> Closes #663 Under M2: Merges under delegation (#684). ## What `launcher/merger.py run`, in `live`, now asks GitHub whether `main` requires a merge queue (GraphQL `repository.mergeQueue(branch: "main")`, set by a ruleset or branch protection), once per run and only if some PR would merge. - **Queue r …

Draft: capability, fix no. "Title: merger: enqueue instead of merging when main requires a merge queue"

label: capability
fix: no
hard:
reviewed: no

## pr-770 · dev · 2026-W46

[#770](https://github.com/open-agentos/productswarm/pull/770) PRODUCT.md: the readiness review is for the first outside project (GOV-0035)  
Linked issue: #766 PRODUCT.md: the readiness review is for the first outside project (GOV-0035)  
Paths touched (1): PRODUCT.md  
> Per GOV-0035, the goal's readiness review is for the first outside project, unnamed until the owner names one. `PRODUCT.md` no longer names the finance planner. - **Done when:** the review is "for the first outside project, once the owner names one (GOV-0035)". - **After that:** "the first outside p …

Draft: governance, fix no. "Per GOV-0035, the goal's readiness review is for the first outside project, unnamed until the owner names one."

label: governance
fix: no
hard:
reviewed: no

## pr-782 · dev · 2026-W46

[#782](https://github.com/open-agentos/productswarm/pull/782) Desk and swarm merges: count merges the merger enqueued (#746)  
Linked issue: #746 Desk and swarm merges: count merges the merger enqueued in the merge queue  
Paths touched (6): dashboard/README.md, dashboard/grants.py, dashboard/test_grants.py, launcher/README.md, launcher/swarm.py, launcher/test_merges.py  
> Closes #746. Under Goal #684 (M2: Merges under delegation). Under a merge queue (#663) the merger posts `Enqueued under <kind> (GOV-0027) at <sha>.` and GitHub merges later. Two readers now handle that: - **Desk grants panel** (`dashboard/grants.py`): a new Enqueued group. Once GitHub has merged the …

Draft: capability, fix no. "a new Enqueued group."

label: capability
fix: no
hard:
reviewed: no

## pr-785 · dev · 2026-W46

[#785](https://github.com/open-agentos/productswarm/pull/785) swarm acts: the owner's acts per working day, kept from webhooks (#771)  
Linked issue: #771 Owner acts per day: swarm acts --json, kept from webhooks (M4 gates 1-2)  
Paths touched (5): launcher/README.md, launcher/acts.py, launcher/swarm.py, launcher/test_acts.py, launcher/webhooks.py  
> Closes #771 Goal: M4 (#686), readiness checks 1 and 2. This issue is go per GOV-0031: a swarm App opened it, it sits under Goal #686, which the owner opened, and nothing blocks it. ## What it does `swarm acts [--day YYYY-MM-DD] [--json]` prints the owner's acts on each of the last 10 working days (o …

Draft: capability, fix no. "`swarm acts [--day YYYY-MM-DD] [--json]` prints the owner's acts on each of the last 10 working days (or one day)"

label: capability
fix: no
hard:
reviewed: no

## pr-787 · dev · 2026-W46

[#787](https://github.com/open-agentos/productswarm/pull/787) swarm watch and the merger work swarm.toml's [org] repos (M4 gate 9)  
Linked issue: #772 swarm watch and the merger work a second repo of the org (M4 gate 9)  
Paths touched (7): launcher/README.md, launcher/manifest.py, launcher/merger.py, launcher/test_manifest.py, launcher/test_merger.py, launcher/test_watch.py, launcher/watch.py  
> Closes #772 An optional `[org]` table in `swarm.toml` lists the org's other repos (`repos = ["open-agentos/scratch"]`). With it left out, both tools read this repo only and behave as before. - **`manifest.py`:** `repos_of()`, `load_repos()` and `others()`. A bad `[org]` table is reported like a bad  …

Draft: capability, fix no. "An optional `[org]` table in `swarm.toml` lists the org's other repos"

label: capability
fix: no
hard:
reviewed: no

## pr-793 · dev · 2026-W46

[#793](https://github.com/open-agentos/productswarm/pull/793) Container runs: host keeps a read-only token file fresh  
Linked issue: #680 Container runs: App token can expire mid-run  
Paths touched (6): launcher/README.md, launcher/container/Dockerfile, launcher/container/entrypoint.sh, launcher/container/gh, launcher/swarm.py, launcher/test_swarm.py  
> Closes #680 Under Area #687 (Engine host). The owner chose option 2 on #749, and this builds it. #749 is a `gov:question` with the owner's answer and `ready`, but there's no merged record for it yet. So it is direction for that question, not precedent (GOV-0006). ## What changes Before this change,  …

Draft: upkeep, fix no. "Before this change, a container run got the role App's token once, as `GH_TOKEN`."

label: upkeep
fix: no
hard:
reviewed: no

## pr-796 · dev · 2026-W46

[#796](https://github.com/open-agentos/productswarm/pull/796) swarm watch: [ruling] starts the builder on the owner's ruling after an overstep (#739)  
Linked issue: #739 After the owner rules on an Overstep:, nothing starts the fix run  
Paths touched (10): dashboard/generate.py, dashboard/test_needs.py, launcher/README.md, launcher/stophook.py, launcher/swarm.py, launcher/test_stophook.py, launcher/test_watch.py, launcher/watch.py, roles/builder.md, roles/reviewer.md  
> Closes #739 Implements Option 1 of the owner's answer on #781 ("Option 1. Record: yes"). That question is `ready` but not yet `gov:ruled` and has no merged record, so this follows it as direction for that question only (GOV-0006). The record that amends GOV-0011 and GOV-0029 is docs' job under GOV-0 …

Draft: capability, fix no. "swarm watch: [ruling] starts the builder on the owner's ruling after an overstep (#739)"

label: capability
fix: no
hard:
reviewed: no

## pr-810 · dev · 2026-W46

[#810](https://github.com/open-agentos/productswarm/pull/810) Planner: Trouble section by hand in every daily report until #804 merges  
Linked issue: #805 Planner: Trouble section by hand in every daily report until stage 2 merges  
Paths touched (1): roles/planner.md  
> Closes #805 Goal: M1 (#683). Direction: #760 ("Until stage 2 merges, write the Trouble section by hand in every daily report, not only on Mondays"). `roles/planner.md`: - The daily report gets a 7th item, **Trouble**: the Monday check-in's Trouble section, by hand, in every daily report until #804 m …

Draft: capability, fix no. "The daily report gets a 7th item, **Trouble**: the Monday check-in's Trouble section, by hand, in every daily report until #804 merges."

label: capability
fix: no
hard:
reviewed: no

## pr-813 · dev · 2026-W46

[#813](https://github.com/open-agentos/productswarm/pull/813) swarm trouble --json: per Goal and Area, progress, stuck work, what waits on the owner (#803)  
Linked issue: #803 swarm trouble --json: per Goal and Area, progress, stuck work, what waits on the owner (#760 stage 1)  
Paths touched (4): launcher/README.md, launcher/swarm.py, launcher/test_trouble.py, launcher/trouble.py  
> Closes #803 Goal: M1 (#683). Direction: #760, stage 1. ## What `swarm trouble [--json] [--hours 24]` (`launcher/trouble.py`) reports on each open Goal and Area the owner opened (GOV-0031), and puts anything under neither in `outside`: - **Progress** for each done-test criterion, meaning a Goal's che …

Draft: capability, fix no. "`swarm trouble [--json] [--hours 24]` (`launcher/trouble.py`) reports on each open Goal and Area the owner opened (GOV-0031)"

label: capability
fix: no
hard:
reviewed: no

## pr-816 · dev · 2026-W46

[#816](https://github.com/open-agentos/productswarm/pull/816) swarm daily lists issues a merged PR left open; the planner closes them (#806)  
Linked issue: #806 An issue stays open when the merger merges its PR  
Paths touched (4): launcher/README.md, launcher/swarm.py, launcher/test_daily.py, roles/planner.md  
> Closes #806 Goal: M2 (#684). Fix chosen by the owner's answer on #812: option 2, the planner closes them. **Cause:** GitHub closes a PR's closing issues as whoever merged it. The merger's token holds only `issues: read` (GOV-0028), so GitHub drops the close when the merger merges. The owner's merges …

Draft: capability, fix no. "`swarm daily` adds a section listing each open closing issue of a PR merged in the last 10 working days, with the PR and who merged it."

label: capability
fix: no
hard:
reviewed: no

## pr-817 · dev · 2026-W46

[#817](https://github.com/open-agentos/productswarm/pull/817) Daily report and Monday check-in read swarm trouble (#804)  
Linked issue: #804 Daily report and Monday check-in read swarm trouble (#760 stage 2)  
Paths touched (4): launcher/swarm.py, launcher/test_swarm.py, launcher/test_watch.py, roles/planner.md  
> Closes #804 Stage 2 of #760's direction, under Goal M1 (#683). ## What changes - **`[daily]` prompt** (`launcher/swarm.py`, `opener()`): after `launcher/swarm daily`, the planner runs `launcher/swarm trouble --json` (#803) and builds the Trouble section from it, not by hand. The same prompt serves t …

Draft: capability, fix no. "after `launcher/swarm daily`, the planner runs `launcher/swarm trouble --json` (#803) and builds the Trouble section from it, not by hand."

label: capability
fix: no
hard:
reviewed: no

## pr-824 · dev · 2026-W46

[#824](https://github.com/open-agentos/productswarm/pull/824) GOV-0036: one launcher for every repo of the org  
Linked issue: #820 GOV-Q: How should the launcher start sessions on work in another repo of the org?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0036-one-launcher-many-repos.md  
> Ruling record for #820, from the owner's answer ("Option 1. A bare #N keeps meaning this repo. Build it in the stages the question lists." with `Record: yes`). There was no draft record on the question, so it is written from the answer and the question's Options and Recommendation, using `GOV-0000-t …

Draft: governance, fix no. "Ruling record for #820, from the owner's answer"

label: governance
fix: no
hard:
reviewed: no

## pr-825 · dev · 2026-W46

[#825](https://github.com/open-agentos/productswarm/pull/825) GOV-0037: planted-defect gate's throwaway issue is go by the owner's ready  
Linked issue: #821 GOV-Q: How should the planted-defect gate's throwaway issue be made go, so the gate can pass?  
Paths touched (3): evals/README.md, governance/INDEX.md, governance/decisions/GOV-0037-planted-gate-issue-go-by-ready.md  
> Ruling PR for #821 (per GOV-0007). The owner added `gov:ruled` and `ready`, and answered "Option 1. If a planted PR is ever merged, the analyst opens the revert at once and the gate is a fail." with `Record: yes`. Plan: the planted-defect gate is part of C stage 2's gating under GOV-0021, raised for …

Draft: governance, fix no. "Ruling PR for #821 (per GOV-0007). The owner added `gov:ruled` and `ready`"

label: governance
fix: no
hard:
reviewed: no

## pr-834 · dev · 2026-W46

[#834](https://github.com/open-agentos/productswarm/pull/834) Launcher: repo-qualified issue refs and holders (#820 stage 1)  
Linked issue: #829 Launcher: repo-qualified issue refs and holders (#820 stage 1)  
Paths touched (3): launcher/README.md, launcher/swarm.py, launcher/test_swarm.py  
> Closes #829 Goal: M4 (#686), through #786 (M4 gate 9). Direction: the owner's ruling on #820 (Option 1), stage 1; record #824 (GOV-0036) not yet merged. ## What - `swarm launch <role> --issue` takes `N`, `#N` or `owner/name#N` (`swarm.parse_ref`). A bare `N`, `#N`, and this repo's own `owner/name#N` …

Draft: upkeep, fix no. "A bare `N`, `#N`, and this repo's own `owner/name#N` (any case) all mean this repo, so current commands and `swarm watch` are unchanged."

label: upkeep
fix: no
hard:
reviewed: no

## pr-839 · dev · 2026-W46

[#839](https://github.com/open-agentos/productswarm/pull/839) GOV-0038: planner App writes the org Project's Spent field (#731)  
Linked issue: #731 GOV-Q: Which identity may write the org Project's Spent field for the engine?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0038-planner-writes-project-spent.md  
> Ruling record for #731, transcribed from the owner's answer (Option 1, `Record: yes`; the question is one-way). Adds `governance/decisions/GOV-0038-planner-writes-project-spent.md` and its row in `governance/INDEX.md`. **How the record differs from the question and the answer** - **Number.** I used  …

Draft: governance, fix no. "Ruling record for #731, transcribed from the owner's answer (Option 1, `Record: yes`; the question is one-way)."

label: governance
fix: no
hard:
reviewed: no

## pr-856 · dev · 2026-W46

[#856](https://github.com/open-agentos/productswarm/pull/856) Launcher: a clone per org repo, with worktrees cut from it (#853)  
Linked issue: #853 Launcher: a clone per repo, with worktrees cut from it (#820 stage 2)  
Paths touched (3): launcher/README.md, launcher/swarm.py, launcher/test_swarm.py  
> Closes #853 Goal: M4 (#686), via #786. Stage 2 of #820, per GOV-0036 (one launcher, many repos; a bare `#N` still means this repo). ## What changed - **A clone per repo.** `Launcher.repo_clone(owner/name)` is `~/.productswarm/repos/<owner>/<name>`, in lower case because GitHub repo names ignore case …

Draft: capability, fix no. "`swarm launch --issue owner/name#N` still refuses** another repo's issue."

label: capability
fix: no
hard:
reviewed: no

## pr-861 · dev · 2026-W46

[#861](https://github.com/open-agentos/productswarm/pull/861) GOV-0039: launcher supplies our CLAUDE.md and role prompt in other org repos (#854)  
Linked issue: #854 GOV-Q: Where does a session in another org repo get its CLAUDE.md and role prompts?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0039-launcher-supplies-rules-in-other-repos.md  
> Ruling record for #854: the owner answered "Option 1 … where the two disagree, ours wins" with `Record: yes`, and added `gov:ruled` and `ready` (both by the owner, 2026-11-11). Adds `governance/decisions/GOV-0039-launcher-supplies-rules-in-other-repos.md` and its row in `governance/INDEX.md`. Closes …

Draft: governance, fix no. "Ruling record for #854: the owner answered "Option 1 … where the two disagree, ours wins" with `Record: yes`, and added `gov:ruled` and `ready`"

label: governance
fix: no
hard:
reviewed: no

## pr-869 · dev · 2026-W46

[#869](https://github.com/open-agentos/productswarm/pull/869) GOV-0040: goal done when each Goal's capability is shown once; owner acts never a gate (#867)  
Linked issue: #867 GOV-Q: Should GOV-0030's done test become each Goal's capability shown once, with owner acts counted but never a gate?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0040-goal-capability-shown-once.md  
> Records the owner's ruling on #867 (Option 1, `Record: yes`) as `governance/decisions/GOV-0040-goal-capability-shown-once.md`, and adds its row to `governance/INDEX.md`. It amends GOV-0030's "Done when" and day-30 checks. Closes #867 Go by the owner's `ready` and `gov:ruled` on #867 (per GOV-0006).  …

Draft: governance, fix no. "Records the owner's ruling on #867 (Option 1, `Record: yes`) as `governance/decisions/GOV-0040-goal-capability-shown-once.md`, and adds its row to `governance/INDEX.md`."

label: governance
fix: no
hard:
reviewed: no

## pr-878 · dev · 2026-W46

[#878](https://github.com/open-agentos/productswarm/pull/878) GOV-0041: the planner closes issues a merger-merged PR left open; the merger keeps issues: read (#812)  
Linked issue: #812 GOV-Q: May the merger App hold issues: write so the issues its merges close actually close?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0041-planner-closes-issues-merger-left-open.md  
> Ruling record for #812: the owner answered "Option 2. Record: yes" and added `ready` (2026-11-11) and `gov:ruled` (2026-11-12), both by the owner. The question is one-way. Adds `governance/decisions/GOV-0041-planner-closes-issues-merger-left-open.md` and its row in `governance/INDEX.md`. Closes #812 …

Draft: governance, fix no. "Ruling record for #812: the owner answered "Option 2. Record: yes" and added `ready` (2026-11-11) and `gov:ruled` (2026-11-12), both by the owner."

label: governance
fix: no
hard:
reviewed: no

## pr-881 · dev · 2026-W46

[#881](https://github.com/open-agentos/productswarm/pull/881) PRODUCT.md: the goal is done when each Goal's capability is shown once; owner acts never a gate (GOV-0040)  
Linked issue: #871 PRODUCT.md: the goal is done when each Goal's capability is shown once; owner acts never a gate (GOV-0040)  
Paths touched (1): PRODUCT.md  
> Closes #871 Serves M4 (#686). Per GOV-0040. **What changed in `PRODUCT.md`** - **Done when:** each open Goal's capability is shown once, on real work or in a scripted drill in the scratch repo; owner acts are counted and reported (`swarm acts`), never a gate; the readiness review for the first outsi …

Draft: governance, fix no. "Title: PRODUCT.md: the goal is done when each Goal's capability is shown once; owner acts never a gate (GOV-0040)"

label: governance
fix: no
hard:
reviewed: no

## pr-884 · dev · 2026-W46

[#884](https://github.com/open-agentos/productswarm/pull/884) swarm acts and swarm trouble: count owner acts with no limit and no 10-day check (GOV-0040)  
Linked issue: #872 swarm acts and swarm trouble: count owner acts with no limit and no 10-day check (GOV-0040)  
Paths touched (6): launcher/README.md, launcher/acts.py, launcher/swarm.py, launcher/test_acts.py, launcher/test_trouble.py, launcher/trouble.py  
> Closes #872 Serves M4 (#686). Per GOV-0040, owner acts are counted and reported, never a gate. **What changed** - `launcher/acts.py`: `LIMIT` and `under_limit` are gone. `swarm acts` prints each day's count and, as reported information, how many acts weren't C-team (`other`). It gives no "5 or more" …

Draft: capability, fix no. "`swarm acts` prints each day's count and, as reported information, how many acts weren't C-team (`other`)."

label: capability
fix: no
hard:
reviewed: no

## pr-896 · dev · 2026-W46

[#896](https://github.com/open-agentos/productswarm/pull/896) swarm daily and swarm trouble: no streak as progress; drop "M1: day N of 5" (#873)  
Linked issue: #873 swarm daily and swarm trouble: no streak as progress; drop "M1: day N of 5" (GOV-0040)  
Paths touched (7): launcher/README.md, launcher/swarm.py, launcher/test_daily.py, launcher/test_swarm.py, launcher/test_trouble.py, launcher/trouble.py, roles/planner.md  
> Closes #873 Under Goal M1 (#683). Per GOV-0040, a Goal's capability is shown once, so a streak no longer counts as progress. **What changes** - `launcher/swarm.py`: `daily_streak`, `M1_DAYS` and `m1_day` are gone. `swarm daily` still lists the last 10 working days' reports and who started each, the  …

Draft: upkeep, fix no. "Under Goal M1 (#683). Per GOV-0040, a Goal's capability is shown once, so a streak no longer counts as progress."

label: upkeep
fix: no
hard:
reviewed: no

## pr-905 · dev · 2026-W46

[#905](https://github.com/open-agentos/productswarm/pull/905) Pause one org repo: [org] paused stops watch starts and merges there (#892)  
Linked issue: #892 Pause one org repo alone: no dispatch and no merges there while the rest keeps working (M4 gate 19)  
Paths touched (9): launcher/README.md, launcher/manifest.py, launcher/merger.py, launcher/swarm.py, launcher/test_manifest.py, launcher/test_merger.py, launcher/test_swarm.py, launcher/test_watch.py, launcher/watch.py  
> Closes #892 **What.** `swarm.toml`'s `[org]` table now takes an optional `paused` list: ```toml [org] repos = ["open-agentos/scratch"] paused = ["open-agentos/scratch"] ``` When a repo is in `paused`: - **`swarm watch`** prints once that the repo is paused and starts nothing on its work. - Another r …

Draft: capability, fix no. "`swarm.toml`'s `[org]` table now takes an optional `paused` list:"

label: capability
fix: no
hard:
reviewed: no

## pr-907 · dev · 2026-W46

[#907](https://github.com/open-agentos/productswarm/pull/907) swarm watch: [conflict] starts the author role on a go PR that conflicts with its base  
Linked issue: #893 swarm watch starts the author role on a go PR that conflicts with its base (M2 criterion 3)  
Paths touched (5): dashboard/generate.py, launcher/README.md, launcher/swarm.py, launcher/test_watch.py, launcher/watch.py  
> Closes #893 Under Goal M2 (#684), criterion 3; also the merge-conflict event in the M4 drill. **What.** A new `swarm watch` trigger, `[conflict]`. Each check, an open, non-draft PR opened by a role's App counts when all of these hold: - GitHub reports it `CONFLICTING` with its base; - its one closin …

Draft: capability, fix no. "A new `swarm watch` trigger, `[conflict]`."

label: capability
fix: no
hard:
reviewed: no

## pr-915 · dev · 2026-W46

[#915](https://github.com/open-agentos/productswarm/pull/915) Merger: an [org] repo inherits the home repo's passed shadow (#913)  
Linked issue: #913 Merger: an [org] repo inherits the home repo's passed shadow (GOV-0027, M4 drill)  
Paths touched (3): launcher/README.md, launcher/merger.py, launcher/test_merger.py  
> Closes #913 An `[org]` repo now inherits the home repo's passed shadow (the owner's M4 drill direction in #913), so `productswarm-scratch` stops acting as shadow once productswarm's bar is met. **What changes in `launcher/merger.py`** - `run()` takes `home` (and an injectable `home_history`). `main( …

Draft: capability, fix no. "An `[org]` repo now inherits the home repo's passed shadow (the owner's M4 drill direction in #913), so `productswarm-scratch` stops acting as shadow once productswarm's bar is met."

label: capability
fix: no
hard:
reviewed: no

## pr-917 · dev · 2026-W46

[#917](https://github.com/open-agentos/productswarm/pull/917) Launcher: sessions in other org repos name the repo; swarm watch starts them (#820 stage 3)  
Linked issue: #912 Launcher: the opener and stop hook name the repo; swarm watch starts sessions in other org repos (#820 stage 3)  
Paths touched (7): launcher/README.md, launcher/stophook.py, launcher/swarm.py, launcher/test_stophook.py, launcher/test_swarm.py, launcher/test_watch.py, launcher/watch.py  
> Closes #912 Goal: M4 (#686), via #786 (gate 9). Stage 3 of #820 (GOV-0036), and the way GOV-0039 is applied. ## What changes **`swarm launch --issue owner/name#N`** no longer refuses another repo's issue. It runs the same go checks, read in that repo, then starts the session. A live session holds th …

Draft: capability, fix no. "**`swarm launch --issue owner/name#N`** no longer refuses another repo's issue."

label: capability
fix: no
hard:
reviewed: no

## pr-923 · dev · 2026-W46

[#923](https://github.com/open-agentos/productswarm/pull/923) evals/drills.md: the merger refuses an unreviewed revert in scratch (#890)  
Linked issue: #890 Drill: the merger refuses an unreviewed revert in productswarm-scratch (M2 criterion 4)  
Paths touched (1): evals/drills.md  
> Adds `evals/drills.md` with the M2 criterion 4 drill. The merger refused [productswarm-scratch#4](https://github.com/open-agentos/productswarm-scratch/pull/4), a revert of scratch's first commit that has no reviewer approval at head. It printed `miss: productswarm-reviewer[bot] hasn't approved at he …

Draft: knowledge, fix no. "Adds `evals/drills.md` with the M2 criterion 4 drill."

label: knowledge
fix: no
hard:
reviewed: no

## pr-925 · dev · 2026-W46

[#925](https://github.com/open-agentos/productswarm/pull/925) Desk: serve the trouble panel under the plan (#903)  
Linked issue: #903 Desk: serve the trouble panel (#889) on a Desk page  
Paths touched (8): dashboard/README.md, dashboard/generate.py, dashboard/test_rate.py, dashboard/test_trouble_panel.py, launcher/desk.py, launcher/test_desk.py, launcher/test_trouble.py, launcher/trouble.py  
> Closes #903 **Under:** #685 (M3: The Desk shows the plan and the report) Follows #903's stated default, since nobody said otherwise before the owner labelled it `ready`: generate.py calls the trouble report itself, without the acts sync, and puts the panel on the plan page. ## What changes - **`trou …

Draft: capability, fix no. "Desk: serve the trouble panel under the plan (#903)"

label: capability
fix: no
hard:
reviewed: no

## pr-929 · dev · 2026-W46

[#929](https://github.com/open-agentos/productswarm/pull/929) Desk: the Bridge page, read-only, after the v5 mock-up (#926)  
Linked issue: #926 Desk: the Bridge page, read-only, from the data the Desk already reads (M3)  
Paths touched (6): dashboard/README.md, dashboard/bridge.py, dashboard/generate.py, dashboard/layout.py, dashboard/test_bridge.py, dashboard/test_generate.py  
> Closes #926 Under **M3 (#685)**. Built in the owner's own session, at the owner's request. This replaces PR #928 for the same issue: it keeps the v5 mock-up's look and adds #928's decision sources. #928 should be closed unmerged. ## What `swarm desk` now serves `bridge.html`, the Bridge from the own …

Draft: capability, fix no. "`swarm desk` now serves `bridge.html`, the Bridge from the owner's "v5 · the bridge" mock-up."

label: capability
fix: no
hard:
reviewed: no

## pr-933 · dev · 2026-W46

[#933](https://github.com/open-agentos/productswarm/pull/933) Desk: the Commissions page, read-only, with a focus drawer (#931)  
Linked issue: #931 Desk: the Commissions page, read-only, with a focus drawer (M3)  
Paths touched (7): dashboard/README.md, dashboard/bridge.py, dashboard/commissions.py, dashboard/generate.py, dashboard/layout.py, dashboard/test_commissions.py, dashboard/test_generate.py  
> Closes #931 Under **M3 (#685)**. Built in the owner's own session, at the owner's request. ## What `commissions.html` is the Commissions page from the owner's "v5 · the bridge" mock-up. It's read-only and makes **no new API calls**: it uses the trouble report, the plan, and the closed issues `fetch( …

Draft: capability, fix no. "Desk: the Commissions page, read-only, with a focus drawer (#931)"

label: capability
fix: no
hard:
reviewed: no

## pr-934 · dev · 2026-W46

[#934](https://github.com/open-agentos/productswarm/pull/934) Desk: the Agents page, read-only, with a focus drawer (#932)  
Linked issue: #932 Desk: the Agents page, read-only, with a focus drawer (M3)  
Paths touched (9): dashboard/README.md, dashboard/agents.py, dashboard/bridge.py, dashboard/commissions.py, dashboard/generate.py, dashboard/layout.py, dashboard/test_agents.py, dashboard/test_commissions.py, dashboard/test_generate.py  
> Closes #932 Under **M3 (#685)**. Built in the owner's own session, at the owner's request. **Merge #933 first:** this branch is built on it, so until #933 merges this PR's diff includes #933's commit. Once #933 is in, only this page's commit is left here. ## What `agents.html` is the Agents page fro …

Draft: capability, fix no. "`agents.html` is the Agents page from the owner's "v5 · the bridge" mock-up. It's read-only and makes **no new API calls**."

label: capability
fix: no
hard:
reviewed: no

## pr-945 · dev · 2026-W46

[#945](https://github.com/open-agentos/productswarm/pull/945) Specs bridge: the SpecSource adapter and feature model (#940)  
Linked issue: #940 Specs bridge: the SpecSource adapter and feature model (#937 §7)  
Paths touched (3): launcher/specs/__init__.py, launcher/specs/source.py, launcher/specs/test_source.py  
> Closes #940 Serves M6 (#938). Spec: #937 §6, §7, §13. **What.** `launcher/specs/source.py`, the adapter boundary every spec backend implements. No backend, network or `swarm` subcommand. - `FeatureStatus`: the six §6 statuses spelled as in Notion. `BRIDGE_STATUSES` is the four the bridge may write.  …

Draft: upkeep, fix no. "No backend, network or `swarm` subcommand."

label: upkeep
fix: no
hard:
reviewed: no

## pr-947 · dev · 2026-W46

[#947](https://github.com/open-agentos/productswarm/pull/947) Specs bridge: the fake backend from JSON fixtures (#941)  
Linked issue: #941 Specs bridge: the fake backend from JSON fixtures (#937 §7)  
Paths touched (4): launcher/specs/__init__.py, launcher/specs/fake.py, launcher/specs/test_fake.py, launcher/specs/testdata/fake_initiative.json  
> Closes #941 **Plan:** under Goal M6 (#938). Go under GOV-0031: the planner App opened it under the owner's open Goal, and its blocker #940 is closed. **What.** `launcher/specs/fake.py` adds `FakeSource(path)`, a `SpecSource` (`name = "fake"`, `simulated = True`) that reads a JSON fixture in #937 §6' …

Draft: capability, fix no. "`launcher/specs/fake.py` adds `FakeSource(path)`, a `SpecSource` (`name = "fake"`, `simulated = True`) that reads a JSON fixture in #937 §6's layout."

label: capability
fix: no
hard:
reviewed: no

## pr-962 · dev · 2026-W46

[#962](https://github.com/open-agentos/productswarm/pull/962) Specs bridge: the events.jsonl event log (#954)  
Linked issue: #954 Specs bridge: the events.jsonl event log (#942)  
Paths touched (3): launcher/specs/__init__.py, launcher/specs/events.py, launcher/specs/test_events.py  
> Closes #954 Under Goal **M6** (#938). Ruling: #942 (R1). Spec: #937 §5.5, §7. **What** - `launcher/specs/events.py` - `path()`: `$PRODUCTSWARM_HOME/specs/events.jsonl`, with the same `~/.productswarm` default as `swarm.py`'s `home()`. - `append(kind, goal, feature, **fields)`: writes one JSON line w …

Draft: upkeep, fix no. "`append(kind, goal, feature, **fields)`: writes one JSON line with a UTC `ts`."

label: upkeep
fix: no
hard:
reviewed: no

## pr-963 · dev · 2026-W46

[#963](https://github.com/open-agentos/productswarm/pull/963) Specs bridge: the spec snapshot block for issue bodies (#953)  
Linked issue: #953 Specs bridge: the spec snapshot block for issue bodies (#942)  
Paths touched (3): launcher/specs/__init__.py, launcher/specs/snapshot.py, launcher/specs/test_snapshot.py  
> Closes #953 **Goal:** M6 (#938), "Specs written in Notion ship through the swarm". Ruling: #942 (R1, option 1). Spec: #937 §5.2, §5.3, §13. **What.** `launcher/specs/snapshot.py`: pure string functions for the spec snapshot block that `pull` writes into each feature's issue body. They use only the s …

Draft: capability, fix no. "`launcher/specs/snapshot.py`: pure string functions for the spec snapshot block that `pull` writes into each feature's issue body."

label: capability
fix: no
hard:
reviewed: no

## pr-964 · dev · 2026-W46

[#964](https://github.com/open-agentos/productswarm/pull/964) Specs bridge: the notion backend, token read from a 0600 file only (#951)  
Linked issue: #951 Specs bridge: the notion backend, token read from a 0600 file only (#943)  
Paths touched (3): launcher/README.md, launcher/specs/notion.py, launcher/specs/test_notion.py  
> Closes #951 Serves M6 (#938). Spec: #937 §5.4, §6, §7, §13. Direction: #943 (R2, Part A option 2; R3). **What.** `launcher/specs/notion.py`, the `notion` `SpecSource`. There's no `swarm specs` subcommand, no `[specs]` config and no event log. **Token custody (#943 Part A)** - `load_token(path=None)` …

Draft: capability, fix no. "`launcher/specs/notion.py`, the `notion` `SpecSource`. There's no `swarm specs` subcommand, no `[specs]` config and no event log."

label: capability
fix: no
hard:
reviewed: no

## pr-974 · dev · 2026-W46

[#974](https://github.com/open-agentos/productswarm/pull/974) GOV-0042: spec-source bridge package, adapter and issue-body snapshot (#942)  
Linked issue: #942 GOV-Q: Should the spec-source bridge be a launcher/specs/ package behind one SpecSource adapter, with the spec snapshot in the issue body (R1)?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0042-spec-source-bridge-package-and-snapshot.md  
> Closes #942 Transcribes the owner's ruling (option 1, `Record: yes`) into `governance/decisions/GOV-0042-spec-source-bridge-package-and-snapshot.md` and adds its INDEX row. No draft record existed, so it is written from the owner's answer and the planner's question. **Where the record differs from t …

Draft: governance, fix no. "Transcribes the owner's ruling (option 1, `Record: yes`) into `governance/decisions/GOV-0042-spec-source-bridge-package-and-snapshot.md` and adds its INDEX row."

label: governance
fix: no
hard:
reviewed: no

## pr-975 · dev · 2026-W46

[#975](https://github.com/open-agentos/productswarm/pull/975) GOV-0042: Notion token custody and publishing Ready specs  
Linked issue: #943 GOV-Q: Where is the Notion integration token held and who may use it, and is pulling private Notion specs into public issues external (R2, R3)?  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0043-notion-token-custody-and-publishing.md  
> Closes #943 Transcribes the owner's ruling on #943 (Part A option 2, Part B option 1). The question is one-way and external, so it needs a record. **Where the record differs from the draft or the answer** - The draft record: there was none, so I wrote it from the owner's answer and the question's op …

Draft: governance, fix no. "Transcribes the owner's ruling on #943 (Part A option 2, Part B option 1). The question is one-way and external, so it needs a record."

label: governance
fix: no
hard:
reviewed: no

## pr-982 · dev · 2026-W46

[#982](https://github.com/open-agentos/productswarm/pull/982) Specs bridge: the [specs] config and backend factory (#952)  
Linked issue: #952 Specs bridge: the [specs] config and backend factory (#942)  
Paths touched (5): launcher/manifest.py, launcher/specs/__init__.py, launcher/specs/config.py, launcher/specs/test_config.py, launcher/test_manifest.py  
> Closes #952 **What.** The `[specs]` table in `swarm.toml` and the one function that turns it into a `SpecSource`, per #942's ruling (#937 §7). - `launcher/manifest.py`: `[specs]` is now an allowed top-level table. The manifest checks only that it is a table; any other unknown table still fails. - `l …

Draft: capability, fix no. "`[specs]` is now an allowed top-level table."

label: capability
fix: no
hard:
reviewed: no

## pr-984 · dev · 2026-W46

[#984](https://github.com/open-agentos/productswarm/pull/984) Specs bridge: swarm specs pull against the fake backend (#955)  
Linked issue: #955 Specs bridge: swarm specs pull against the fake backend (#942)  
Paths touched (5): launcher/specs/__init__.py, launcher/specs/sync.py, launcher/specs/test_sync.py, launcher/swarm.py, launcher/test_swarm.py  
> Closes #955 Serves Goal **M6 (#938)**, criterion 1. Ruling: #942 (R1); #943 (R3, Part B). Spec: #937 §5.1, §5.2, §6, §8. ## What **`launcher/specs/sync.py`: `pull(goal, source, gh, today, dry_run, *, owner, backend, out)`** 1. **The link.** Reads the Goal through a small `GitHub` protocol and refuse …

Draft: capability, fix no. "Features. For Ready + unlinked + pullable it opens an issue titled after the feature."

label: capability
fix: no
hard:
reviewed: no

## pr-993 · dev · 2026-W46

[#993](https://github.com/open-agentos/productswarm/pull/993) Specs bridge: swarm specs push against the fake backend (#957)  
Linked issue: #957 Specs bridge: swarm specs push against the fake backend (#942)  
Paths touched (5): launcher/specs/__init__.py, launcher/specs/push.py, launcher/specs/test_push.py, launcher/swarm.py, launcher/test_swarm.py  
> Closes #957 Adds `swarm specs push <goal>` against the `fake` backend (#937 §5.4, phase 1 of §11), per #942's ruling (GOV-0042). **`launcher/specs/push.py`: `push(goal, source, gh, what_shipped, dry_run, *, owner, model)`** - **Goal checks** are pull's (`sync.check_goal`, `parse_link`, the backend s …

Draft: capability, fix no. "Adds `swarm specs push <goal>` against the `fake` backend (#937 §5.4, phase 1 of §11), per #942's ruling (GOV-0042)."

label: capability
fix: no
hard:
reviewed: no

## pr-994 · dev · 2026-W46

[#994](https://github.com/open-agentos/productswarm/pull/994) Specs bridge: swarm specs diff and the lead's drift decisions (#956)  
Linked issue: #956 Specs bridge: swarm specs diff and the lead's drift decisions, against the fake backend (#942)  
Paths touched (5): launcher/specs/__init__.py, launcher/specs/drift.py, launcher/specs/test_drift.py, launcher/swarm.py, launcher/test_swarm.py  
> Closes #956 Serves Goal **M6 (#938)**, criterion 2. Ruling: #942 (R1). Spec: #937 §5.3. ## What **`launcher/specs/drift.py`** 1. **`check(goal, source, gh, *, owner, backend, now)`** checks one Goal and writes nothing. The Goal must pass the same check as pull (`sync.check_goal`, `sync.parse_link` a …

Draft: capability, fix no. "**`launcher/swarm.py`:** `swarm specs diff [<goal>] [--json]` and `swarm specs diff <goal> --adopt|--defer|--ask FEAT …"

label: capability
fix: no
hard:
reviewed: no

## pr-1000 · dev · 2026-W46

[#1000](https://github.com/open-agentos/productswarm/pull/1000) Record GOV-0044: classifier in public top-level classify/ (#991)  
Linked issue: #991 GOV-Q: Should the Effort mix classifier be a new top-level classify/ module, with its data, recordings and reports in this public repo? (C1, #987)  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0044-classifier-top-level-classify-public.md  
> Closes #991 Transcribes the owner's ruling on #991 (option 1, `Record: yes`) into `governance/decisions/GOV-0044-classifier-top-level-classify-public.md` and adds its INDEX row. There was no asker draft record, so it is written from the owner's answer using the template. Differences from the answer: …

Draft: governance, fix no. "Transcribes the owner's ruling on #991 (option 1, `Record: yes`) into `governance/decisions/GOV-0044-classifier-top-level-classify-public.md` and adds its INDEX row."

label: governance
fix: no
hard:
reviewed: no

## pr-1001 · dev · 2026-W46

[#1001](https://github.com/open-agentos/productswarm/pull/1001) GOV-0044: classifier model calls run on the owner's Mac via the Claude Code login (#992)  
Linked issue: #992 GOV-Q: Which credential, where, which model and what per-run cap for the Effort mix classifier's model calls? (R5, #987)  
Paths touched (2): governance/INDEX.md, governance/decisions/GOV-0045-classifier-calls-on-owners-mac-via-claude-login.md  
> Closes #992 Ruling record transcribed from the owner's answer on #992 (option 1, as recommended). The question had no draft record. Differences from the answer: none in substance. I added the date (2026-11-13), `review_by` 2027-02-28 (as GOV-0040 to GOV-0043), the options list from the question, and …

Draft: governance, fix no. "Ruling record transcribed from the owner's answer on #992 (option 1, as recommended)."

label: governance
fix: no
hard:
reviewed: no

## pr-1009 · dev · 2026-W46

[#1009](https://github.com/open-agentos/productswarm/pull/1009) Specs bridge: wire the notion backend into [specs] and swarm.toml (#1007)  
Linked issue: #1007 Specs bridge: wire the notion backend into [specs] and swarm.toml  
Paths touched (4): launcher/specs/config.py, launcher/specs/test_config.py, launcher/test_swarm.py, swarm.toml  
> Closes #1007 **Plan:** M6 (#938), criterion 1; unblocks M7 (#987). **What changed** - `launcher/specs/config.py`: `source()` returns `NotionSource(cfg.parent_page)` for `backend = "notion"`. Without `parent_page` it refuses with `specs: backend "notion" needs 'parent_page'`. Nothing here reads the t …

Draft: capability, fix no. "- `launcher/specs/config.py`: `source()` returns `NotionSource(cfg.parent_page)` for `backend = "notion"`."

label: capability
fix: no
hard:
reviewed: no
