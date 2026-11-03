# Launcher

The v1 local launcher (GOV-0005). It starts sessions through `ops/swarm-session` unchanged. It covers the manifest (L1), `swarm up / ls / stop` (L2), `swarm launch` (L3), the warn-only spend cap (L4) and `swarm inbox` (L5). `swarm watch` is v2, the wake-up loop (GOV-0009). The reviewer runs by default (L6) because `swarm.toml` lists it, so `up` starts it like any other role.

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
| 2 | Open `gov:question`s nobody is blocked on, with their time to live | oldest first |
| 3 | Open PRs that aren't drafts, waiting for review or merge | oldest first |
| 4 | Idle sessions: no event within the idle threshold | longest idle first |
| 5 | Sessions over their role's spend cap (warn only, GOV-0008) | furthest over first |

If nothing is waiting, it says "Nothing is waiting on you."

Below the list, `inbox` adds what `swarm watch` is holding or skipping, with the reason and when it last checked (see below). That part comes from local state, so the dashboard doesn't show it.

### Local state

Nothing new is posted to GitHub. What the launcher started is recorded under `~/.productswarm/launcher/` (or `$PRODUCTSWARM_HOME/launcher/`):

- `sessions.json` holds each session's name, role, model, session ID and start time.
- `.worktrees/<session-id>/` in this checkout is the session's working tree (see `up`).
- `<session-id>.pid` is written by the window's shell before it hands over to `swarm-session`, so the PID it holds is Claude Code's.
- `watch.json` holds what `swarm watch` has acted on, and what it is holding or skipping (see below).

A PID counts only while that process's command line still contains `--session-id <its id>`. A reused PID is never mistaken for a session, and is never sent a signal. If a session exits by itself, `up` and `ls` remove it from the state file.

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
| `[answer]` A `gov:question` whose most recent `ready` was added by the owner | the role in its "Raised by" field, on the question |
| `[respond]` An open, non-draft PR whose latest `productswarm-reviewer[bot]` review at its current head is "changes requested", and whose **Authority** line isn't `fail`, for at most 2 rounds (GOV-0011) | `builder` on the PR, as `swarm launch builder --issue N --pr M` would, where #N is the one issue the PR closes |

`[respond]` is GOV-0011's bounded review loop. The builder's push starts a fresh `[review]`, and if the reviewer requests changes again, a fresh `[respond]`:

- **Round bound.** The loop counts the reviewer's "changes requested" reviews on the PR, on any head, from GitHub's review history, so the count holds across restarts and machines. At the third, it starts nothing, and `swarm inbox` and the dashboard list the PR as "changes requested 3 times: needs the owner".
- **Oversteps.** If the reviewer's latest review at the head has `- **Authority:** fail` (the rubric line in `roles/reviewer.md`), whatever its state, the loop starts nothing, and the PR is listed as "overstep: needs the owner".
- A comment or an approval at the head, or a request on an older head, starts nothing. A PR that doesn't close exactly one issue is logged as skipped.
- `[respond]` starts count toward `max_live` and need the builder's `spend_cap_usd`, like any loop start. Its refusal checks run on the issue the PR closes.

`swarm launch builder --issue N --pr M` starts the same session by hand. `--pr` only changes the opener, which names the PR and the issue; the refusal checks are still on #N.

Each start is a fresh session in a new Terminal window, as `swarm launch` makes. The loop never re-prompts a running session. `--dry-run` prints `would start …` for each trigger and starts nothing. It keeps its memory only while it runs and writes nothing to disk.

### Limits

These are GOV-0010, the owner's answer on #88. They live in `swarm.toml`'s `[watch]` table, so changing them is a reviewed change and a `spend` decision:

```toml
[watch]
interval_minutes = 5   # how often it checks
max_live = 2           # the most live sessions swarm watch may have started at once
```

- **Ceiling.** Only sessions the loop started count toward `max_live`. Sessions you start with `swarm up` or `swarm launch` don't. At the ceiling, further triggers are **held**: `swarm inbox` lists them, and they start in the order they were first held once a loop-started session stops.
- **Cap required.** The loop starts only roles that set `spend_cap_usd` in `swarm.toml`. A trigger for any other role is **skipped**: `swarm inbox` lists it with the reason, and it starts on a later check once the role has a cap. Every role in `swarm.toml` sets a cap (since #110), so the loop can start any of them. The cap is still warn-only (GOV-0008).
- **Interval.** `interval_minutes` sets how often it checks. `--interval` works only with `--dry-run`, so the real interval can't be changed by a flag.
- `swarm.toml` is read again on every check, so a new cap or limit applies without a restart. Without a `[watch]` table, `swarm watch` refuses to start anything, but `--dry-run` still works and checks every 5 minutes.

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
- **Skipped for good.** If a question's "Raised by" names no known role, or more than one, the trigger is logged as skipped and is done.
- **Failed starts.** If a window can't be opened, the trigger is held, listed in `swarm inbox`, and tried again on the next check.
- **Records it can't see.** GOV-0007 also counts a question as needing a record when the owner says so in the answer. That's a comment the loop can't read reliably, so only the body's ratings trigger `[record]`: domain `governance`, `one-way`, or blast radius `external`.

### What it never does

It never stops a session (GOV-0008). It never adds or removes labels, and never comments, approves or merges. Its only GitHub calls are reads. Sessions it starts are recorded with `by: watch` in `sessions.json`, and `swarm ls` shows them as `running, by watch`. To end one, run `swarm stop <name>` yourself. If GitHub can't be read, or `swarm.toml` is invalid, it says so and tries again on the next check.

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

From Python, `manifest.load()` returns a list of `Session(role, index, model, spend_cap_usd)` or raises `ManifestError`.

## Tests

```bash
python3 -m unittest discover -s launcher
```
