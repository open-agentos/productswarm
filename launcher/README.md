# Launcher

The v1 local launcher (GOV-0005). It starts sessions through `ops/swarm-session` unchanged. It covers the manifest (L1), `swarm up / ls / stop` (L2), `swarm launch` (L3), the warn-only spend cap (L4) and `swarm inbox` (L5). `swarm watch` is v2, the wake-up loop (GOV-0009). `swarm cost` (#176) prints the cost per PR of the runs `swarm watch` recorded, locally. The reviewer runs by default (L6) because `swarm.toml` lists it, so `up` starts it like any other role.

## swarm up / ls / stop

```bash
launcher/swarm up [--dry-run]   # start every manifest session that isn't running
launcher/swarm ls               # live sessions, from the heartbeat tracking issues
launcher/swarm stop builder-1   # end one session the launcher started (name or session id)
```

**`up`** opens one Terminal window per session (macOS; the owner's answer on #43). Each window runs:

```
ops/swarm-session <role> --model <model> --session-id <uuid> "<the usual opener prompt>"
```

`swarm-session` is unchanged. It passes the extra args on to `claude`, so the session still acts as its role's App. The launcher picks the session ID itself, which is how it matches a window to that session's heartbeat tracking issue. Sessions are named `<role>-<n>`, numbered within the role. `up` starts only the names that aren't already running and lists the rest, so running it twice starts nothing new. If you raise a role's count, `up` starts the extra sessions. If you remove a role from the manifest, `up` leaves its running sessions alone. `--dry-run` prints the commands without running them. The first `up` may ask you to let Terminal be controlled by your terminal app.

**Each session gets its own worktree** (#93). Before opening the window, the launcher runs `git fetch origin main` and then `git worktree add --detach .worktrees/<session id> origin/main` in this checkout. The window runs that worktree's `ops/swarm-session`, unchanged, which `cd`s to the worktree. Sessions therefore never share a working tree: one session switching branches or leaving edits changes nothing under another, and git refuses to check out one branch in two worktrees. The launcher also writes the heartbeat hook entries into the worktree's `.claude/settings.local.json`, keeping any other settings from this checkout's copy, so every launcher session has the heartbeat without a separate install. The entries point at the pinned copy of `main` in `~/.productswarm/runtime`, which `up` and `launch` refresh first, so only merged hook code runs (heartbeat/README.md). `.worktrees/` is gitignored. `--dry-run` prints the `worktree add` it would run and creates nothing.

**Worktrees are cleaned up without losing work.** Once a session has exited, `up`, `ls`, `launch` and `stop` remove its worktree if it is clean (nothing uncommitted or untracked) and its HEAD is on a remote branch. Otherwise the worktree is kept, and `ls` and `stop` print `worktree kept: <path> (uncommitted or unpushed work)`. Push or discard that work yourself, and the next run removes the worktree. Only `.worktrees/<session id>` directories are touched, never one made by hand.

Sessions you start by hand with `ops/swarm-session` still run in this checkout. CLAUDE.md asks them to do branch work in their own worktree and leave this checkout on `main`.

**`ls`** reads the tracking issues through the dashboard's reader (`dashboard/generate.py`), so status, current issue and last activity mean exactly what they mean on the dashboard. It shows every live session, including ones you started by hand (`PROCESS: not launcher`). A session the launcher just started appears as `no heartbeat yet` until its first event reaches GitHub.

**`stop`** sends SIGTERM. Claude Code runs its `SessionEnd` hook on SIGTERM, so the heartbeat records `stopped` and the dashboard shows the session as stopped. `stop` waits up to 20 seconds and then tells you whether the heartbeat recorded the stop. It only stops sessions the launcher started, and only you run it (GOV-0008: the launcher never stops a session on its own).

## swarm launch: start a session on one issue

```bash
launcher/swarm launch builder --issue 49            # model from swarm.toml's builder entry
launcher/swarm launch builder --issue 49 --model claude-sonnet-5-5 --dry-run
```

It starts one session in a new Terminal window, as `up` does. Its opener ends "…then work on issue #49.", so the heartbeat records `working_on` #49 with no change to the hook. The session is named `<role>-issue-<n>`, so it never takes a manifest slot from `up`.

It refuses, and says why, if:

- #N doesn't exist, is a pull request, or is closed;
- #N doesn't carry `ready`, or the most recent `ready` label was added by anyone other than the owner named in `governance/jurisdictions.yml` (per GOV-0006);
- a live session is already on #N. "Live" means a heartbeat session that isn't stopped and whose current issue is #N, or a session `launch` started on #N that hasn't sent a heartbeat yet. The refusal names the session.

`--force` overrides only the last of these. GOV-0006 says the launcher starts sessions only on `ready` issues, so no flag skips the label check. Add `ready` to the issue instead.

## Spend cap (warn only)

Set `spend_cap_usd` on a role in `swarm.toml`, and each session of that role gets that cap. There's no cap unless you set one (#45). A session is over cap when its estimated spend, from the dashboard's `spend.py` (API list-price equivalent, not what's billed), passes the cap.

- **`swarm ls`:** the SPEND column shows `$20.00 / $15.00 OVER CAP`.
- **`swarm inbox` and the dashboard:** the session is listed as `[over cap]`.
- **Nothing else happens.** Per GOV-0008, the launcher never stops a session. Run `swarm stop <name>` yourself, or raise the cap in `swarm.toml`, which takes effect on the next `ls`, `inbox`, or dashboard build.

Caps apply by role to every live session of that role, including ones you started by hand. The dashboard reads the same committed `swarm.toml`, so the public page and `swarm inbox` stay identical.

## swarm inbox: what needs you

```bash
launcher/swarm inbox
```

It prints one numbered list of everything waiting on you, most urgent first, each with its link. It's the same list, in the same order, as the "Needs you" section at the top of the dashboard: both come from `needs_you()` in `dashboard/generate.py`.

| Order | What | Within the kind |
|---|---|---|
| 1 | Sessions blocked on a `gov:question`, with the question | longest blocked first |
| 2 | Open `gov:question`s nobody is blocked on and the owner hasn't labelled `gov:ruled`, with their time to live | oldest first |
| 3 | Open PRs that aren't drafts, waiting for review or merge | oldest first |
| 4 | Sessions over their role's spend cap (warn only, GOV-0008) | furthest over first |

Idle sessions aren't listed: `swarm ls` and the floor show them. A ruled question's next step is docs or the planner, so it's left out too; a record PR for it still shows as a PR (#469).

If nothing is waiting, it says "Nothing is waiting on you."

Below the list, `inbox` adds what `swarm watch` is holding or skipping, with the reason and when it last checked, and the runs it started that ended at cap, plus each recorded run's cost (see "How each run ended" below). That part comes from local state, so the dashboard doesn't show it.

If `swarm.toml` sets `review_in_actions = true` (see "Leaving reviews to Actions" below), `inbox` also says that `swarm watch` leaves `[review]` to the GitHub Actions reviewer, so you know the local fallback for reviews is off. `inbox --manifest PATH` reads another manifest.

### Local state

Nothing new is posted to GitHub. What the launcher started is recorded under `~/.productswarm/launcher/` (or `$PRODUCTSWARM_HOME/launcher/`):

- `sessions.json` holds each session's name, role, model, session ID and start time. Every `swarm` process that changes it first takes a lock on `sessions.lock`, and each write goes through its own temp file, so a `swarm launch` during a `swarm watch` check isn't lost (#272). A session is recorded before its window opens. If a `.pid` file belongs to a running session that has no entry, `live()` (used by `ls`, `stop`, `launch` and `watch`) rebuilds the entry from the process's command line as `<role>-recovered-<id>` and says so once. `swarm stop` then works on it again.
- `.worktrees/<session-id>/` in this checkout is the session's working tree (see `up`).
- `<session-id>.pid` is written by the window's shell before it hands over to `swarm-session`, so the PID it holds is Claude Code's.
- `watch.json` holds what `swarm watch` has acted on, what it is holding or skipping, and how each run it started ended (see below).
- `watch.lock` is locked by the running `swarm watch` and holds its pid, so a second one refuses to start (see "One watcher at a time" below).
- `<session-id>.stop.json` counts how many times the Stop hook has blocked a run `swarm watch` started, and `stophook.log` says why (see below).
- `<session-id>.result.json` is a headless run's output (see "Headless runs" below). Its first line is `ops/swarm-session`'s banner (`swarm-session: <role> as …`), and its last line is the JSON result from `claude -p --output-format json`.

A PID counts only while that process's command line still contains `--session-id <its id>`. A reused PID is never mistaken for a session, and is never sent a signal. If a session exits by itself, `up` and `ls` remove it from the state file.

## swarm cost: cost per PR (local only)

```bash
launcher/swarm cost [--repo owner/name]
```

It reads the `runs` that `swarm watch` recorded in `watch.json` (see "How each run ended" below) and adds up each run's `cost_usd` by the PR the run served (#176):

- `[review]` and `[respond]` runs count towards their trigger's PR.
- `[build]`, `[record]` and `[answer]` runs count towards the PR that closes their issue. If more than one PR closes it, a merged PR wins, then an open one, then a closed one. If no PR closes it yet, the run gets its own `#N (no PR)` row.

For each PR it prints the number, whether it is merged, open or closed, the number of runs, their total cost and how many runs have no cost recorded. A run has no cost if it is still running or left no result. Then it prints the total, the dates the runs cover, and the PRs merged in that time that have no run recorded:

```
PR            STATE   RUNS  COST (EST.)  NO COST
PR #70        merged  3     $6.50        0
PR #72        open    2     -            2
#90 (no PR)   -       1     $3.00        0

total: $9.50 over 6 runs, runs started 2026-11-01 to 2026-11-03; 2 runs with no cost recorded (still running, or no result)
1 PR merged since 2026-11-01 has no run recorded: #80
```

Its only GitHub call is a read: `gh pr list --state all`, to find each PR's state and the issues it closes.

Limits. These are stated in the output too, and this command doesn't fix them:

- **Only loop-started runs have a cost.** Sessions you start with `swarm up` or `swarm launch` have none, because the heartbeat's `cost_usd` is always null. A PR they worked on shows up only in the "merged … no run recorded" line, or with fewer runs than it really took.
- **`watch.json` keeps runs for 7 days** (`watch.RUNS_DAYS`). Older runs are gone, so run `swarm cost` within a week of the work you want costed.
- **The cost is Claude Code's local estimate** (`total_cost_usd`).

**It stays local.** `swarm cost` only prints. Nothing is written to GitHub or the repo, and no cost figure goes into `evals/` or a PR. GOV-0014 keeps run costs local, and GOV-0002, GOV-0003 and GOV-0004 govern what reaches GitHub. Publishing cost would need a `security` question.

## swarm watch: the wake-up loop

```bash
launcher/swarm watch                          # start sessions on triggers; Ctrl-C to stop
launcher/swarm watch --dry-run                # print what it would start; start nothing
launcher/swarm watch --dry-run --interval 1
```

This is v2 (GOV-0009; #89 is `--dry-run`, #90 the real starts, #113 adds `[respond]` from GOV-0011). It runs in the foreground. On every check it reads the same GitHub and heartbeat state as `swarm inbox` and works out each **new** trigger:

| Trigger | Starts |
|---|---|
| `[review]` An open, non-draft PR whose current head `productswarm-reviewer[bot]` hasn't reviewed (the check in `roles/reviewer.md` step 2) | a reviewer pass: one reviewer session with its usual opener |
| `[build]` An open issue whose most recent `ready` label was added by the owner (GOV-0006), with no open PR closing it | `builder` on #N, as `swarm launch builder --issue N` would |
| `[record]` A `gov:question` whose most recent `gov:ruled` was added by the owner and that needs a record (GOV-0007), with no open PR closing it | `docs` on the question |
| `[answer]` A `gov:question` whose most recent `ready` was added by the owner, and again when the owner then adds `gov:ruled` (#495) | the role in its "Raised by" field, on the question. If the field starts with `owner` or the owner's login, `planner` (#455) |
| `[respond]` An open, non-draft PR that `productswarm-builder[bot]` opened, whose latest `productswarm-reviewer[bot]` review at its current head is "changes requested", and whose **Authority** line isn't `fail`, for at most 2 rounds (GOV-0011) | `builder` on the PR, as `swarm launch builder --issue N --pr M` would, where #N is the one issue the PR closes |

`[respond]` is GOV-0011's bounded review loop. The builder's push starts a fresh `[review]`, and if the reviewer requests changes again, a fresh `[respond]`:

- **Round bound.** The loop counts the reviewer's "changes requested" reviews on the PR, on any head, from GitHub's review history, so the count holds across restarts and machines. At the third, it starts nothing, and `swarm inbox` and the dashboard list the PR as "changes requested 3 times: needs the owner".
- **Oversteps.** If the reviewer's latest review at the head has `- **Authority:** fail` (the rubric line in `roles/reviewer.md`), whatever its state, the loop starts nothing, and the PR is listed as "overstep: needs the owner".
- **Other authors' PRs.** The builder responds only on its own PR (GOV-0011). Requested changes on a PR another App or a person opened, such as a docs ruling PR, start nothing, and the PR is listed as "changes requested on a docs PR: needs the owner" (#178).
- A comment or an approval at the head, or a request on an older head, starts nothing. A PR that doesn't close exactly one issue is logged as skipped.
- `[respond]` starts count toward `max_live` and need the builder's `spend_cap_usd`, like any loop start. Its refusal checks run on the issue the PR closes.

`swarm launch builder --issue N --pr M` starts the same session by hand. `--pr` only changes the opener, which names the PR and the issue; the refusal checks are still on #N.

Each start is a fresh **headless** run in a new Terminal window (see below). The loop never re-prompts a running session. `--dry-run` prints `would start …` for each trigger, then the full headless command it would run on the next line, indented, and starts nothing. If there is no command to show (the role has no `spend_cap_usd`, or `[watch]` has no `max_turns`), that line says why. It keeps its memory only while it runs and writes nothing to disk.

**One watcher at a time** (#273). Without `--dry-run`, `swarm watch` holds an exclusive lock on `~/.productswarm/launcher/watch.lock` (`fcntl.flock`, non-blocking) for as long as it runs, and writes its pid into the file. A second `swarm watch` exits at once with `refused: another swarm watch is already running (pid N; …)`. Two watchers would both act on the same triggers, because `watch.json`'s once-per-trigger memory assumes one. The kernel releases the lock when the process ends, on Ctrl-C, a crash or `kill`, so there is never a stale lock to clean up. Leave `watch.lock` in place: the pid in it matters only while a watcher holds the lock. `--dry-run` takes no lock and writes no `watch.json`, so it is safe to run beside a running watcher.

### Headless runs

Every session `swarm watch` starts is a one-shot `claude -p` run (#147, from the owner's answer on #125, GOV-0012 and GOV-0013). It ends when it is done, or when it reaches its budget or its turn ceiling, whichever comes first. Sessions you start with `swarm up` and `swarm launch` stay interactive and don't change.

The launcher adds these to the usual `ops/swarm-session <role> --model <model> --session-id <id>` call (`ops/` passes them on to `claude` unchanged):

| Flag | Value | Why |
|---|---|---|
| `-p` | the usual opener, as the prompt | headless, one shot (#125) |
| `--permission-mode` | `auto` | the mode interactive sessions use (GOV-0013) |
| `--disallowedTools` | the patterns in `swarm.DENY` (below) | a backstop for merging and label edits (GOV-0013) |
| `--max-budget-usd` | the role's `spend_cap_usd` | Claude Code ends the run at it (GOV-0012) |
| `--max-turns` | `[watch] max_turns` | catches a run that is looping (GOV-0012) |
| `--output-format` | `json` | stdout goes to `~/.productswarm/launcher/<session-id>.result.json` |

The run still opens in its own Terminal window, so the pid file, `swarm ls` and `swarm stop` work as before, and the heartbeat hook still records `started` and `stopped`. Before the run starts, the window prints one line saying it is headless and where its result goes. After that the window shows only stderr. The loop reads the result file once the run has ended (see "How each run ended" below).

The deny patterns back up auto mode's classifier for the two rules governance cares about most: agents never merge (GOV-0011), and agents never add or remove labels such as `ready` and `gov:ruled` (GOV-0006):

```
Bash(gh pr merge *)
Bash(gh issue edit * --add-label *)    Bash(gh issue edit * --remove-label *)
Bash(gh issue edit * --add-label=*)    Bash(gh issue edit * --remove-label=*)
Bash(gh pr edit * --add-label *)       Bash(gh pr edit * --remove-label *)
Bash(gh pr edit * --add-label=*)       Bash(gh pr edit * --remove-label=*)
Bash(gh label *)
Bash(gh api *labels*)                  Bash(gh api *merge*)
```

As GOV-0013 accepts, this is a backstop and not a complete fence. The `=` forms are there because `--add-label=ready` doesn't match `--add-label *`. `gh api *merge*` also denies reads that mention "merge", such as `gh api repos/…/pulls/5 --jq .merged`. `gh pr view --json mergeable` and `gh issue view --json labels` still work.

### How each run ended

Once a run the loop started is no longer live, the next check reads its result file and records, against the trigger, in `"runs"` in `watch.json` (#149):

```json
"build:49:11": {"session_id": "…", "name": "builder-issue-49", "kind": "build", "ref": "#49",
                "started": "2026-11-03T12:00:00+00:00", "ended": "2026-11-03T12:45:00+00:00",
                "ending": "ended at cap", "detail": "budget (--max-budget-usd)",
                "cost_usd": 15.02, "subtype": "error_max_budget_usd"}
```

`ending` comes from the result's `subtype` (the `SDKResultMessage` type in the [Agent SDK reference](https://code.claude.com/docs/en/agent-sdk/typescript#sdkresultmessage), checked against real Claude Code 2.1.317 runs):

| `ending` | When |
|---|---|
| `done` | `subtype` is `success` and `is_error` is false |
| `ended at cap` | `subtype` is `error_max_budget_usd` (`--max-budget-usd`) or `error_max_turns` (`--max-turns`) |
| `limited` | a usage or rate limit: `api_error` is `usage_limit_reached` or `api_error_status` is 429 (#489); `detail` holds the result's message, for example "You've hit your 5-hour limit · resets 12pm (Europe/London)" |
| `error` | any other `subtype`, or `success` with `is_error` set; `detail` holds the result's `errors` |
| `no result` | no result file, a file that can't be read, or no JSON result on its last line, for example after `swarm stop` |

`cost_usd` is the result's `total_cost_usd`: Claude Code's client-side estimate. It stays on this machine. GOV-0002, GOV-0003 and GOV-0004 still govern what reaches GitHub, and nothing new is posted.

- **The trigger stays done.** The loop never restarts a run by itself (GOV-0012), unless it was `limited`.
- **A `limited` run is tried again after the hold (#489).** Claude Code reports a usage limit as `subtype` `success` with `is_error` set, after a second or two and at $0.00: the run never started work. Its trigger leaves `"acted"`, along with any review triggers its reviewer pass covered, so it fires again with no label change. The record gets an `"until"` time: the next time the result's "resets 12pm (Europe/London)" names (in that zone, or this machine's if it names none), or 30 minutes after the run ended (`watch.LIMIT_HOLD`) if there's no reset time the loop can read. The limit is account-wide, so until then the loop holds **every** start, says so once, and lists each held trigger in `swarm inbox` as `held: usage limit (until HH:MM)`, in this machine's time. Triggers that start nothing (skipped, refused, covered) are not held. Other errors behave as before.
- **`swarm inbox` lists a run that ended at cap**, with its ref, which limit it reached and its cost, so you can decide whether to restart it, for example by adding `ready` again. It drops off the list once a later run on the same ref has started, or after 7 days (`watch.RUNS_DAYS`).
- **`swarm inbox` lists each recorded run's cost** from the last 7 days, newest first. Records older than that are dropped from `watch.json`.
- **Unpushed work is kept.** As for any session, `tidy()` keeps an exited run's worktree if it has uncommitted or unpushed work, and `swarm ls` names it.
- **The dashboard doesn't show these.** It is built and published by a GitHub Action, which can't read this machine's `watch.json`, and publishing the costs would send them to GitHub.

### Limits

These are GOV-0010, the owner's answer on #88. They live in `swarm.toml`'s `[watch]` table, so changing them is a reviewed change and a `spend` decision:

```toml
[watch]
interval_minutes = 5   # how often it checks
max_live = 2           # the most live sessions swarm watch may have started at once
max_turns = 200        # the turn ceiling for each headless run (#147, GOV-0012)
```

- **Ceiling.** Only sessions the loop started count toward `max_live`. Sessions you start with `swarm up` or `swarm launch` don't. At the ceiling, further triggers are **held**: `swarm inbox` lists them, and they start in the order they were first held once a loop-started session stops.
- **Cap required.** The loop starts only roles that set `spend_cap_usd` in `swarm.toml`. A trigger for any other role is **skipped**: `swarm inbox` lists it with the reason, and it starts on a later check once the role has a cap. Every role in `swarm.toml` sets a cap (since #110), so the loop can start any of them. For a run the loop starts, the cap is also its `--max-budget-usd`, so Claude Code ends the run there (GOV-0012). For sessions you start, it is still warn-only (GOV-0008).
- **Turn ceiling.** `max_turns` is the `--max-turns` for every headless run. The budget is the main bound; the ceiling only catches a run that is looping. Setting the number is the owner's call (a `spend` change, GOV-0010); 200 is the planner's suggestion. It must be a whole number of at least 1.
- **Interval.** `interval_minutes` sets how often it checks. `--interval` works only with `--dry-run`, so the real interval can't be changed by a flag.
- `swarm.toml` is read again on every check, so a new cap or limit applies without a restart. Without a `[watch]` table, or with one that has no `max_turns`, `swarm watch` refuses to start anything, but `--dry-run` still works (with no `[watch]` table, it checks every 5 minutes). `swarm up` and `swarm launch` don't need `max_turns`.
- **A bad `[[session]]` entry is skipped (#487).** If one entry is invalid (say it names a role with no `roles/<role>.md` yet), the loop starts from the other entries and prints each problem on every check, prefixed `swarm.toml:`. A trigger for the skipped role waits as if the role weren't in `swarm.toml`. A bad `[watch]` table, or a file that isn't valid TOML, still starts nothing (GOV-0010, GOV-0012).
- `roles/` is read again on every check too, so a role file added while `swarm watch` runs counts from the next check.

### Leaving reviews to Actions

The reviewer also runs in GitHub Actions (`.github/workflows/reviewer.yml`), as a reconciler on `main` (GOV-0020, from #255): every 5 minutes it sweeps the open PRs and reviews each unreviewed head. A PR push doesn't start it, so an Actions review can lag a push by a few minutes, or more when GitHub starts scheduled runs late. So that the Actions reviewer and `swarm watch` don't both review the same head, a switch in `[watch]` hands `[review]` to Actions (#216, GOV-0019):

```toml
[watch]
review_in_actions = true   # optional; default false
```

- **On.** Every `[review]` trigger is logged once per head as `skipped: left to Actions …` and starts nothing, in `--dry-run` too (with no headless command under it). `swarm inbox` says the switch is on. `[respond]`, `[build]`, `[answer]` and `[record]` are unchanged, and still run locally.
- **Off or missing.** `swarm watch` starts reviewer passes as before. This is the default, so the switch changes nothing until you turn it on.
- **Re-running one PR.** To review a PR now instead of waiting for the next sweep, or to retry a head whose run failed or ended at its budget, dispatch the workflow with its number: `gh workflow run reviewer.yml -f pr=N` (or **Run workflow** in the Actions tab). See [actions_review.py](#actions_reviewpy-the-reviewer-in-github-actions-v3-c-stage-1) below.
- **Falling back.** If the Actions reviewer is down or you want reviews local again, set `review_in_actions = false` (or delete the line) and run `swarm watch`. If you also want Actions to stop reviewing, disable the workflow (`gh workflow disable reviewer.yml`, or in the Actions tab); otherwise both review each new head. Skipped reviews are not recorded in `watch.json`, so on the next check the loop reviews any open PR whose head is still unreviewed.
- Changing the switch is a `ci-and-workflows` call for the owner (GOV-0019), not a `spend` one. It must be `true` or `false`; anything else is an error.
- `swarm.toml` is read on every check, so the switch applies without a restart.

### Overlapping builds

Builders on issues from the same ruling usually change the same files, so their PRs conflict or one undoes the other. A `[build]` trigger is **held** while other work from the same GOV record is in flight. This is #136, which builds the owner's answer on #127. That answer is direction for #127, not a ruling.

- **An issue's GOV records** are the `GOV-NNNN` ids in its **title**, e.g. `GOV-0011 R3: …`. Ids cited only in the body don't count, because bodies cite rulings in passing. An issue whose title cites no GOV id is never held by this rule.
- A build for #N is held while N's title shares a GOV id with the title of:
  - another issue a **live builder** is on: a heartbeat `builder` session that isn't stopped, or a launcher builder entry with no heartbeat yet. This includes builders you started by hand, which don't count toward `max_live` but still write to the same files, and a builder the loop started earlier in the same check;
  - an issue that an **open PR**, draft or not, closes.
- `swarm inbox` lists the hold with what it waits on, e.g. `held: #113 shares GOV-0011 with live builder-issue-112 (on #112) / open PR #120 (#127)`. It is logged once per reason. Held triggers start held-longest-first once the overlap clears: on the first check after the builder stops and the PR is merged or closed.
- `[respond]` is never held: a builder responding on its own PR is the same work (GOV-0011). `[review]`, `[record]` and `[answer]` are never held either.
- `--dry-run` doesn't show these holds, as it doesn't show the ceiling's.

### What it does on each trigger

- **Once per trigger, across restarts too.** A trigger is identified by the PR and its head SHA (`[review]`, `[respond]`) or by the id of the owner's label event. What the loop has acted on is kept in `~/.productswarm/launcher/watch.json`, so restarting `swarm watch` starts nothing twice. A new push, or the owner adding the label again, is a new trigger.
- **No session already on it.** An issue or question with a live session gets no trigger, by the same rule `swarm launch` refuses on. Once that session stops, the trigger can fire.
- **Refusal checks again.** Just before each start, it runs `swarm launch`'s refusal checks on fresh GitHub data: the issue is open, the owner added the label most recently (`gov:ruled` for `[record]`, `ready` otherwise), and no live session is on it. If a check refuses, for example because someone started a session on the issue by hand, the loop logs the refusal and the trigger is done.
- **Reviews.** One reviewer pass covers every review trigger present when it starts, because the pass reviews every open PR. While a reviewer that `swarm watch` started is live, review triggers wait: that pass may have listed the PRs before the latest push. Reviewers you start yourself (`swarm up`, `swarm launch`) don't hold reviews up: an idle one at its prompt is yours to steer, and GOV-0010 already leaves sessions you start out of the loop's counts. The loop does the polling. The reviewer still runs one pass and stops, as `roles/reviewer.md` says.
- **Who asked.** The asker is the first word of a question's "Raised by" field, or the role in a leading `-- role` signature: "planner, on #167 (...)" starts the planner. A role named later in the text isn't the asker (#271), so "owner, after the first Actions reviewer test on #251" doesn't start the reviewer. A question the owner raised (the field starts with `owner` or the owner's login, with or without `@`) starts the planner, which reads the answer and does what it directs (#455). If the answer convenes a committee, the planner acts as convener: it posts the convening comment with a `swarm launch <role> --issue N` command per seat, opens the Discussion and stops, and you start each round's seats by hand. The loop has no committee trigger. When the field starts with neither a known role nor the owner, the trigger is logged once as skipped and `swarm inbox` lists it with the reason until the owner closes the question or removes `ready`.
- **A ruling starts the work.** When you add `gov:ruled` to a question that is already `ready`, `[answer]` fires again, keyed on your `gov:ruled` event (`answer:N:<event id>`), so the asker acts on the ruling without you taking `ready` off and putting it back (#495). The key is whichever of your two label events is later, and `ready` must still be yours (GOV-0006). On an owner-raised question the planner turns the ruling into task issues: one unlabelled issue for each stage that can start now, and a comment on the question saying which stages wait and on what. If `[record]` is also due on the question, docs goes first: `[answer]` is held (and listed in `swarm inbox`) until `[record]` has started or been refused, then waits until docs has stopped. `--dry-run` marks that `[answer]` line `once docs has stopped ([record] first)`.
- **Failed starts.** If a window can't be opened, the trigger is held, listed in `swarm inbox`, and tried again on the next check.
- **Which questions need a record.** GOV-0007 counts a question as needing one when its body rates it domain `governance`, `one-way`, or blast radius `external`, or when the owner says so in the answer. The loop reads the owner's answer as a comment **by the owner** on the question with a line `Record: yes` on its own (any case), and logs the reason as `the owner asked in the answer` (#501). The same line from anyone else, an App included, starts nothing. The key is still the ruling's (`record:N:<gov:ruled event id>`), so a line you post after `gov:ruled` starts docs on the next check if `[record]` hasn't fired for that ruling yet, and a second line never starts it again.

### Done-conditions: the Stop hook on runs it starts

A run that `swarm watch` starts keeps going until its role has done its job (#148, from the owner's answer on #125). The launcher writes a Stop hook (`launcher/stophook.py`) into that run's worktree `.claude/settings.local.json`. It runs from the pinned copy of `main` in `~/.productswarm/runtime`, as the heartbeat hook does, so only merged code runs as a hook. Sessions you start with `swarm up` or `swarm launch` don't get it.

When the run is about to stop, the hook reads GitHub as the run's App (only reads) and checks:

| Run | Done when |
|---|---|
| builder on an issue (`[build]`) | a PR, open or merged, closes the issue |
| builder on a PR (`[respond]`) | the reviewer's latest review at the PR's head isn't "changes requested" (a push moved the head, or there was nothing to respond to); or the run commented on the PR; or the PR is closed |
| reviewer | every open, non-draft PR that existed when the run started has a reviewer review at its current head, or one posted since the run started |
| docs on a `gov:ruled` question (`[record]`) | a PR, open or merged, closes the question |
| anything else, e.g. an `[answer]` run | always |

These also count as done, because a run can stop for good reasons without a PR:

- since it started, the run opened or commented on a `gov:question` that names its issue or PR as `#N`. Every session of a role acts as the same App, so the `#N` is how the hook tells this run's question from another session's;
- since it started, the run commented on its own issue naming another open issue as `#M` (not a PR): it's blocked on an unfinished prerequisite, e.g. a `[build]` whose file another issue creates (#184). Only a comment on the run's own issue counts, so another session's comment elsewhere doesn't;
- the issue fails `swarm launch`'s refusal checks: it's closed, or its latest `ready` (`gov:ruled` for `[record]`) wasn't added by the owner (GOV-0006);
- a PR, open or merged, already closes the issue.

If the condition isn't met, the hook blocks the stop and gives a short reason naming what's missing, and the run continues. It allows the stop whenever `stop_hook_active` is set (a hook is already continuing the run), after 3 blocks in one run (counted in `~/.productswarm/launcher/<session id>.stop.json`), and whenever GitHub can't be read or anything else fails. It never fails closed: the run's budget (GOV-0012) is what bounds spend. What it blocked, and any read that failed, go to `~/.productswarm/launcher/stophook.log`.

### What it never does

It never stops a session itself (GOV-0008): a headless run ends at its budget or turn ceiling because Claude Code ends it (GOV-0012). It never adds or removes labels, and never comments, approves or merges. Its only GitHub calls are reads. Sessions it starts are recorded with `by: watch` in `sessions.json`, and `swarm ls` shows them as `running, by watch`. To end one, run `swarm stop <name>` yourself. If GitHub can't be read, or `swarm.toml` is invalid, it says so and tries again on the next check.

## The swarm manifest

`swarm.toml` at the repo root lists the sessions to run. It is TOML, read with stdlib `tomllib` (Python 3.11+), per the owner's answer on #44.

```toml
[[session]]
role = "builder"          # required: needs roles/builder.md
count = 2                 # required: at least 1
model = "claude-opus-5-5" # required
spend_cap_usd = 15        # optional, per session; no cap if left out (#45)
```

- Each role gets one `[[session]]` table. Use `count` to run more than one session of a role.
- Any other key is an error, so a typo fails loudly instead of being ignored.
- The spend cap is warn-only: the launcher never stops a session (GOV-0008).
- Changing a role's model changes cost per run. That is a `spend` decision for the owner.

Check the manifest and see what it would start:

```bash
python3 launcher/manifest.py            # or: python3 launcher/manifest.py path/to/swarm.toml
```

It prints one line per session (`builder-1  claude-opus-5-5  no cap`). If the manifest is bad, it exits 1 and lists every problem it found.

From Python, `manifest.load()` returns a list of `Session(role, index, model, spend_cap_usd)` or raises `ManifestError`. `manifest.load_all()`, which `swarm watch` uses, returns `(sessions, watch limits, problems)`: the sessions from the valid entries, and one problem per bad one (#487). It raises `ManifestError` only if the file can't be read, isn't TOML, or has a bad `[watch]` table.

## Tests

```bash
python3 -m unittest discover -s launcher
```

## actions_review.py: the reviewer in GitHub Actions (v3 C stage 1)

The Actions reviewer is a reconciler on `main` (GOV-0020, from #255). `.github/workflows/reviewer.yml` wakes every 5 minutes (and on `workflow_dispatch`), runs `plan` in a secret-free job to list the PRs to review, then runs one `review` job per listed PR, each calling `run`. No PR event starts a run: every run starts from `main`, so GOV-0018's main-only environment accepts it. The cost is speed: a review can lag a push by a few minutes or more.

`python3 launcher/actions_review.py plan [--pr N]` (#257, #258) is the first job. It asks "which open PRs need a review now?" from repo state:

- **What it reads.** The open PRs, and the reviews on each eligible one, with the job's default token. It keeps a PR only if it is open, not a draft, opened by a swarm App or the owner (#206), with its head in this repo, not a fork (GOV-0017's rules, now the reconciler's policy per GOV-0020), and its head SHA not yet reviewed by the reviewer. That last rule is `watch.reviewed_heads()`, the one `swarm watch`'s `[review]` trigger uses, so the two agree (#209). The swarm Apps are every login under `identities.agents` in `governance/jurisdictions.yml`, and the owner is `humans.owner` there (#491, #506). Plan reads that file from its checkout of `main`, so a PR can't change who is trusted, and a role added there is trusted with no code change. If the file is missing or that block can't be read, plan trusts only the owner and says so in one log line.
- **The limit.** At most `[watch] actions_max_reviews` PRs go in per sweep, lowest number (oldest) first; the rest wait for the next sweep. With the key unset, `plan` lists nothing and says so, as a missing `max_turns` starts nothing (GOV-0012). Setting it is the owner's `spend` call.
- **In-flight and attempted heads** (#258). From this workflow's run history, not a local file, it leaves out a head whose newest `review` job is queued or in progress, so GOV-0019's cancel-in-progress never cancels a live review. It also leaves out one whose newest attempt completed with any conclusion but `cancelled` (for example, it ended at its budget), so a failing head isn't retried every sweep. It finds attempts by the `review` job's name, `review #<pr> <head sha>` (`REVIEW_JOB`), which the workflow must keep. The read is bounded: runs created since the head's commit, newest first, and at most 50 runs' jobs per sweep; a head it can't resolve within that is held, never started twice.
- **Re-running one PR.** `gh workflow run reviewer.yml -f pr=N` (or **Run workflow** in the Actions tab) runs `plan --pr N`: only PR N, under the same rules. It still skips a reviewed head or one being reviewed now, but retries a completed attempt, so this is how you restart a failed or capped review. Leave `pr` empty to sweep now.

It writes `prs=<JSON list of {"pr": N, "head": "<sha>"}>` and `any=true|false` to `$GITHUB_OUTPUT`, ints and hex SHAs only, and prints one `in:` or `out:` line per PR with the rule that decided it, never PR text. It reads no secrets and writes nothing to GitHub. If it can't decide (GitHub unreadable, a bad `swarm.toml`), it writes `any=false`, `prs=[]` and exits 1.

`python3 launcher/actions_review.py run --pr N` (#215) is the `review` job: one reviewer pass on PR N, with the same limits as a run `swarm watch` starts. Its `claude` argv is `swarm.headless_flags()`, the flags `Launcher.headless_args()` uses: `--permission-mode auto` and the `--disallowedTools` denies (GOV-0013), `--max-budget-usd` from the reviewer's `spend_cap_usd` and `--max-turns` from `[watch] max_turns` (GOV-0012), and `--output-format json`. On top of `swarm.DENY`, a reviewer run in Actions also denies creating issues (`actions_review.REVIEWER_DENY`, #389):

```
Bash(gh issue create *)                gh's own command, which calls GraphQL createIssue
Bash(gh api graphql *createIssue*)     the mutation, called directly
Bash(gh api *repos/*/issues)           a REST create with the path last: gh api -X POST repos/o/r/issues
Bash(gh api *repos/*/issues *)         a REST create with flags after the path (-X, --method, -f, -F, --input)
```

Why: #384's log line showed the reviewer token is granted only `issues: read`, yet earlier Actions runs opened `[heartbeat]` issues with it, which points to GraphQL `createIssue` accepting the token (#364). #366 removed the code that did it, but a reviewer misled by a prompt injection could still try. Like `swarm.DENY`, this is a backstop and not a fence: a GraphQL query read from a file (`-F query=@q.graphql`) gets past it. The REST patterns also deny reads of the issues collection that pass flags after the path, such as `gh api repos/o/r/issues --jq …`; `gh issue list` and `gh issue view` still work, and so do comments (`…/issues/N/comments`). Only reviewer runs in Actions get these: `swarm.DENY` and the runs `swarm watch` starts are unchanged, since the planner opens issues as its job. The opener asks for PR N only, one pass, then stop. It writes the reviewer's Stop hook (`stophook.py`, as `by="actions"`, checking only PR N) into the checkout's `.claude/settings.local.json`. The heartbeat is off in Actions (#307): its hooks aren't installed (any already there are removed) and `SWARM_ROLE` is unset in `claude`'s environment, so `heartbeat/hook.py` does nothing and posts nothing to GitHub. Before #307 each run opened a `[heartbeat] reviewer` tracking issue and then left it empty and open. Actions runs don't appear on the dashboard; the job log (GOV-0016) and the Actions tab are their record. It needs `CLAUDE_CODE_OAUTH_TOKEN` or `ANTHROPIC_API_KEY` (either; the owner's direction on #208) and the reviewer App token in `GH_TOKEN` (#207), and refuses outside GitHub Actions.

Per GOV-0016, claude's stdout and stderr go to files in a fresh directory under `$RUNNER_TEMP`, with the heartbeat's local spool, and the job log gets only `result`, `subtype`, `num_turns` and `total_cost_usd`, one JSON-encoded line each. Exit 0 is done, 3 ended at its budget or turn ceiling, 1 an error, 2 refused. `--dry-run` prints the command and starts nothing, anywhere:

    python3 launcher/actions_review.py run --pr 70 --dry-run
