# Launcher

The v1 local launcher (GOV-0005). It starts sessions through `ops/swarm-session` unchanged. It covers the manifest (L1), `swarm up / ls / stop` (L2), `swarm launch` (L3), the warn-only spend cap (L4) and `swarm inbox` (L5). `swarm watch --dry-run` is the first part of v2. The reviewer runs by default (L6) because `swarm.toml` lists it, so `up` starts it like any other role.

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

**Each session gets its own worktree** (#93). Before opening the window, the launcher runs `git fetch origin main` and then `git worktree add --detach .worktrees/<session id> origin/main` in this checkout. The window runs that worktree's `ops/swarm-session`, unchanged, which `cd`s to the worktree. Sessions therefore never share a working tree: one session switching branches or leaving edits changes nothing under another, and git refuses to check out one branch in two worktrees. The launcher also writes the heartbeat hook entries into the worktree's `.claude/settings.local.json`, keeping any other settings from this checkout's copy, so every launcher session has the heartbeat without a separate install. `.worktrees/` is gitignored. `--dry-run` prints the `worktree add` it would run and creates nothing.

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

### Local state

Nothing new is posted to GitHub. What the launcher started is recorded under `~/.productswarm/launcher/` (or `$PRODUCTSWARM_HOME/launcher/`):

- `sessions.json` holds each session's name, role, model, session ID and start time.
- `.worktrees/<session-id>/` in this checkout is the session's working tree (see `up`).
- `<session-id>.pid` is written by the window's shell before it hands over to `swarm-session`, so the PID it holds is Claude Code's.

A PID counts only while that process's command line still contains `--session-id <its id>`. A reused PID is never mistaken for a session, and is never sent a signal. If a session exits by itself, `up` and `ls` remove it from the state file.

## swarm watch --dry-run: what the wake-up loop would start

```bash
launcher/swarm watch --dry-run                # check every 5 minutes; Ctrl-C to stop
launcher/swarm watch --dry-run --interval 1
```

This is the first part of v2, the wake-up loop (#87, option 1; W1 is #89). It runs in the foreground. On every check it reads the same GitHub and heartbeat state as `swarm inbox` and prints one line for each **new** trigger, with what it would start. **It starts nothing.** It never stops a session, never adds or removes labels, and never comments, approves or merges. Starting sessions for real waits on the spend limits in #88 (W2, #90), so `swarm watch` without `--dry-run` refuses.

| Trigger | Would start |
|---|---|
| `[review]` An open, non-draft PR whose current head `productswarm-reviewer[bot]` hasn't reviewed (the check in `roles/reviewer.md` step 2) | a reviewer pass |
| `[build]` An open issue whose most recent `ready` label was added by the owner (GOV-0006) | `swarm launch builder --issue N` |
| `[record]` A `gov:question` whose most recent `gov:ruled` was added by the owner and that needs a record (GOV-0007), with no open PR closing it | `swarm launch docs --issue N` |
| `[answer]` A `gov:question` whose most recent `ready` was added by the owner | `swarm launch <role> --issue N`, where the role comes from its "Raised by" field |

- **No session already on it.** An issue or question with a live session prints nothing, by the same rule `swarm launch` refuses on. It can print later, once that session stops.
- **Each trigger prints once.** A trigger is identified by the PR's head SHA, or by the id of the owner's label event. A new push to a reviewed PR, or the owner adding `ready` again, is a new trigger. The memory lasts only as long as the process, and nothing is written to disk.
- **Skipped, with a reason.** If "Raised by" names no known role, or more than one, the trigger is printed as skipped and says why.
- **Records it can't see.** GOV-0007 also counts a question as needing a record when the owner says so in the answer. That's a comment the loop can't read reliably, so only the body's ratings trigger `[record]`: domain `governance`, `one-way`, or blast radius `external`.
- **What it reads.** The PR and question lists come from `needs_you()` (the same list as `swarm inbox`), sessions come from the dashboard's heartbeat reader, and the live-session and label checks are `swarm launch`'s own. If GitHub can't be read, it says so and tries again on the next check.

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
