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

## When something looks wrong

The hook never prints to the session and always exits 0. Errors go to `~/.productswarm/heartbeat.log`. Per-session state is in `~/.productswarm/state/<session_id>.json`. Set `PRODUCTSWARM_HOME` to use a different directory.

## Tests

```bash
python3 -m unittest discover -s heartbeat
```

They use a fake `gh` and never touch GitHub. If `jsonschema` is installed, events are also validated against `event.schema.json`; it is not a dependency.
