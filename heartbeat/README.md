# Heartbeat hook

Records what each agent session is doing, per [SCHEMA.md](SCHEMA.md). What it captures follows [GOV-0002](../governance/decisions/GOV-0002-heartbeat-capture.md); where events go follows [GOV-0003](../governance/decisions/GOV-0003-heartbeat-storage.md).

## Enable it (one step)

```bash
python3 heartbeat/install.py
```

This adds the hook to `.claude/settings.local.json` (per machine, not committed). It applies to sessions started afterwards. Disable it with `python3 heartbeat/install.py --uninstall`.

The hook does nothing unless the session was started with `ops/swarm-session`, which sets `SWARM_ROLE`. Your own sessions in this checkout are unaffected.

## What it records

| Claude Code hook | Event(s) |
|---|---|
| `SessionStart` | `session_started` (first time, or when a stopped session is resumed) |
| `UserPromptSubmit` | `prompt_submitted`; plus `working_on` when the prompt names exactly one issue (`issue 3`, `issue #3`) different from the current one |
| `PostToolUse` | collects tool names; `pr_opened` after `gh pr create` prints a PR URL; `blocked` after `gh issue create … gov:blocking` prints an issue URL |
| `Stop` / `PostToolUse` | `heartbeat` if nothing was recorded for 5 minutes |
| `SessionEnd` | `stopped` |
| `SessionStart` (another session) | `stopped` for this role's sessions on this machine that vanished without `SessionEnd` (below) |

To record a change by hand (the hook finds this role's most recent live session):

```bash
python3 heartbeat/hook.py emit working_on --issue 4
python3 heartbeat/hook.py emit blocked --gov-question 15
```

Token counts are read locally from the session transcript (cumulative, de-duplicated by message id). `cost_usd` is always `null` until #6 decides how to estimate it. Tool commands and outputs are read in memory only to find PR and issue numbers; they are never written anywhere.

## Where events go

- **Local spool:** `~/.productswarm/events/<session_id>.jsonl`, every field including the redacted, truncated `prompt`. Directory `0700`, files `0600`.
- **GitHub:** the same events without `prompt`, as comments on a `[heartbeat] <role> <session_id>` issue opened by the role's App through the `gh` shim. State changes post at once; other events are batched and post at least every 5 minutes. The issue is closed after `stopped`.

Posting runs in a detached process, so the session never waits on GitHub. If posting fails, events stay in `~/.productswarm/outbox/` and go out with the next flush.

## Sessions that vanish without `SessionEnd`

Closing a session's Terminal tab or window sends SIGHUP or kills it, so `SessionEnd` never runs and no `stopped` is posted (#75). To catch these, every new session sweeps this machine's other sessions **of the same role** that haven't stopped, and records `stopped` for any that are gone:

- **still running** if any process's command line contains its session id (launcher sessions carry `--session-id`, resumed ones `--resume`): left alone however long it has been quiet;
- **gone** if the launcher started it (its pid file is in `~/.productswarm/launcher/`) and no such process exists;
- **gone** otherwise once it has been silent for 6 hours (`STALE_AFTER`). Sessions started by hand don't name their id on the command line, so silence is all there is to go on.

The `stopped` event goes out through the normal flush, which closes the tracking issue. It is posted by the sweeping session's App, which is why only the same role is swept: the dashboard accepts a session's events only from its own role's App. If a swept session was only quiet, its next event posts `session_started` and reopens the issue.

To sweep without starting a session, run inside a swarm session of that role:

```bash
python3 heartbeat/hook.py sweep
```

## When something looks wrong

The hook never prints to the session and always exits 0. Errors go to `~/.productswarm/heartbeat.log`. Per-session state is in `~/.productswarm/state/<session_id>.json`. Set `PRODUCTSWARM_HOME` to use a different directory.

## Tests

```bash
python3 -m unittest discover -s heartbeat
```

They use a fake `gh` and never touch GitHub. If `jsonschema` is installed, events are also validated against `event.schema.json`; it is not a dependency.
