# Launcher

The v1 local launcher (GOV-0005). It starts sessions through `ops/swarm-session` unchanged, using the manifest (L1), `swarm up / ls / stop` (L2) and `swarm launch` (L3).

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

`swarm-session` is unchanged. It passes the extra args on to `claude`, so the session still acts as its role's App. The launcher picks the session ID itself, which is how it matches a window to that session's heartbeat tracking issue. Sessions are named `<role>-<n>`, numbered within the role. `up` starts only the names that aren't already running and lists the rest, so running it twice starts nothing new. If you raise a role's count, `up` starts the extra sessions. If you remove a role from the manifest, `up` leaves its running sessions alone. `--dry-run` prints the commands without running them. The first `up` may ask you to let Terminal be controlled by your terminal app. If the heartbeat hook isn't installed, `up` warns you, because `ls` can't see sessions without it.

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

If nothing is waiting, it says "Nothing is waiting on you."

### Local state

Nothing new is posted to GitHub. What the launcher started is recorded under `~/.productswarm/launcher/` (or `$PRODUCTSWARM_HOME/launcher/`):

- `sessions.json` holds each session's name, role, model, session ID and start time.
- `<session-id>.pid` is written by the window's shell before it hands over to `swarm-session`, so the PID it holds is Claude Code's.

A PID counts only while that process's command line still contains `--session-id <its id>`. A reused PID is never mistaken for a session, and is never sent a signal. If a session exits by itself, `up` and `ls` remove it from the state file.

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
