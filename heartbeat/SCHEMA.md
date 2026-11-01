# Heartbeat event schema (v1)

**Status: proposed.** What an event may capture is pending #15 (security, blocking for #3). Where events are stored is pending #14 (architecture). Nothing emits events until both are ruled and #3 lands.

A heartbeat event is one JSON object describing one thing that happened in one agent session. Events are append-only and stored one per line (JSON Lines). The dashboard derives everything else (status, idle time, current issue, spend) from the event stream plus GitHub state.

The machine-readable schema is [`event.schema.json`](event.schema.json) (JSON Schema 2020-12). Examples are in [`examples/`](examples/).

## Fields

| Field | Type | Required | Meaning |
|---|---|---|---|
| `v` | integer | yes | Schema version. Always `1` for this document. |
| `ts` | string | yes | When the event happened, RFC 3339 in UTC, e.g. `2026-11-01T18:30:05Z`. |
| `session_id` | string | yes | The Claude Code session id the hook receives. Groups events into sessions. |
| `repo` | string | yes | `owner/name` the session works on. Makes issue and PR numbers unambiguous. |
| `role` | string | yes | The swarm role, e.g. `builder`. Matches `roles/<role>.md`. |
| `model` | string | yes | Model id, e.g. `claude-opus-5-5`. |
| `event` | string | yes | One of the event types below. |
| `issue` | integer or null | no | The issue the session is working on, if known. |
| `pr` | integer or null | no | The PR the event refers to. |
| `gov_question` | integer or null | no | The `gov:question` issue the session is blocked on. |
| `cost_usd` | number or null | no | Rough **cumulative** cost of the session so far, in USD. `null` when unknown. How it is estimated is #6. |

No other fields are allowed (`additionalProperties: false`). In particular an event never carries prompt text, tool inputs or outputs, file paths, working directory, environment variables, hostnames or credentials. See #15.

`cost_usd` is cumulative rather than a delta so that a lost or duplicated event doesn't corrupt spend: the dashboard takes the latest value per session.

## Event types

| `event` | When | Fields that must be set |
|---|---|---|
| `session_started` | the session starts | — |
| `working_on` | the session picks up an issue | `issue` |
| `pr_opened` | the session opens a PR | `pr`, and `issue` it closes |
| `blocked` | the session stops work waiting on a ruling | `gov_question` |
| `heartbeat` | periodic liveness while working, rate-limited by the hook | — |
| `stopped` | the session ends | — |

Optional fields not listed may still be set when known (e.g. `issue` on a `heartbeat`), so the latest event alone tells the dashboard what a session is on.

## How the dashboard reads status

- **stopped**: the session's latest event is `stopped`.
- **blocked**: the latest non-`heartbeat` event is `blocked` and its `gov_question` is still open.
- **idle**: no event for longer than a threshold (set in #4).
- **active**: otherwise.

## Example

```json
{"v":1,"ts":"2026-11-01T18:42:10Z","session_id":"0b6c2f0e-3d1a-4c55-9a7e-5f1d2b8e9c41","repo":"open-agentos/productswarm","role":"builder","model":"claude-opus-5-5","event":"pr_opened","issue":2,"pr":16,"gov_question":null,"cost_usd":1.84}
```

A full session is in [`examples/session.jsonl`](examples/session.jsonl).

## Storage

Pending #14. Until it is ruled, the interim location (the question's default) is a local file per session:

```
~/.productswarm/events/<session_id>.jsonl
```

Nothing leaves the machine. Readers should rely only on "one JSONL file per session", so moving the files later doesn't change the format.

## Changing the schema

Adding an optional field is a new minor revision of this document and keeps `v: 1`. Removing or renaming a field, or changing a meaning, bumps `v`. Any new field is a capture change and needs a `security` ruling first.
