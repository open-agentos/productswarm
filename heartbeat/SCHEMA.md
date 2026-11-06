# Heartbeat event schema (v1)

What an event may capture is set by [GOV-0002](../governance/decisions/GOV-0002-heartbeat-capture.md). Where events are stored is set by [GOV-0003](../governance/decisions/GOV-0003-heartbeat-storage.md) (interim). Both are reviewed by 2026-11-30.

A heartbeat event is one JSON object describing one thing that happened in one agent session. Events are append-only. The dashboard derives everything else (status, idle time, current issue, spend) from the event stream plus GitHub state.

The machine-readable schema is [`event.schema.json`](event.schema.json) (JSON Schema 2020-12). Validate local spool lines against the root schema and anything sent to GitHub against `#/$defs/remote`. Examples are in [`examples/`](examples/).

## Fields

| Field | Type | Required | Leaves the machine? | Meaning |
|---|---|---|---|---|
| `schema_version` | integer | yes | yes | Always `1` for this document. |
| `ts` | string | yes | yes | When the event happened, RFC 3339 in UTC, e.g. `2026-11-01T18:30:05Z`. |
| `session_id` | string | yes | yes | The Claude Code session id the hook receives. Groups events into sessions. |
| `repo` | string | yes | yes | `owner/name` the session works on. Makes issue and PR numbers unambiguous. |
| `role` | string | yes | yes | The swarm role, e.g. `builder`. Matches `roles/<role>.md`. |
| `model` | string | yes | yes | Model id, e.g. `claude-opus-5-5`. |
| `event` | string | yes | yes | One of the event types below. |
| `issue` | integer or null | no | yes | The issue the session is working on, if known. Never the tracking issue. |
| `pr` | integer or null | no | yes | The PR the event refers to. |
| `gov_question` | integer or null | no | yes | The `gov:question` issue the session is blocked on. |
| `cost_usd` | number or null | no | yes | Rough **cumulative** cost of the session so far, in USD. `null` when unknown. How it is estimated is #6. |
| `token_counts` | object or null | no | yes | **Cumulative** tokens for the session so far: `input`, `output`, `cache_read`, `cache_creation` (non-negative integers, all required when the object is present). |
| `tools` | array of strings or null | no | yes | Names of tools used since the session's previous event, e.g. `["Bash", "Edit"]`. Names only, never inputs or outputs. |
| `prompt` | string or null | no | **no** | The prompt text, redacted and truncated to 2,000 characters. Only on `prompt_submitted`. **Local spool only.** |

No other fields are allowed (`additionalProperties: false`). An event never carries tool inputs or outputs, file contents, file paths, `cwd`, environment variables, hostnames or credentials (per GOV-0002).

`cost_usd` and `token_counts` are cumulative rather than deltas, so a lost or duplicated event doesn't corrupt spend: the dashboard takes the latest value per session.

### Prompt text

Per GOV-0002, the hook must, in this order, before writing `prompt` anywhere:

1. **Redact** GitHub tokens (`ghp_`, `ghs_`, `gho_`, `github_pat_`), `sk-` style API keys, PEM blocks, and `NAME=value` pairs where the name contains `KEY`, `TOKEN`, `SECRET` or `PASSWORD`.
2. **Truncate** to at most 2,000 characters.
3. Write it **only** to the local spool. The copy of the event sent to GitHub drops the `prompt` field. The `prompt_submitted` event itself is still sent, so the dashboard sees the activity without the text.

The schema enforces the length limit and, via `#/$defs/remote`, the absence of `prompt`. Redaction can't be checked by a schema; it is the hook's job (#3).

## Event types

| `event` | When | Fields that must be set |
|---|---|---|
| `session_started` | the session starts | — |
| `prompt_submitted` | a prompt is submitted to the session | — (carries `prompt` in the local spool only) |
| `working_on` | the session picks up an issue | `issue` |
| `pr_opened` | the session opens a PR | `pr`, and `issue` it closes |
| `blocked` | the session stops work waiting on a ruling | `gov_question` |
| `heartbeat` | periodic liveness while working, rate-limited by the hook | — |
| `stopped` | the session ends, or a later session of the same role on the same machine finds it gone without having ended (heartbeat/README.md) | — |

`prompt` is allowed only on `prompt_submitted`. Other optional fields may be set on any event when known (e.g. `issue` on a `heartbeat`), so the latest event alone tells the dashboard what a session is on.

## How the dashboard reads status

- **stopped**: the session's latest event is `stopped`.
- **blocked**: the latest event other than `heartbeat`, `prompt_submitted` is `blocked`, and its `gov_question` is still open.
- **idle**: no event for longer than a threshold (set in #4).
- **active**: otherwise.

## Example

Local spool line:

```json
{"schema_version":1,"ts":"2026-11-01T18:42:10Z","session_id":"0b6c2f0e-3d1a-4c55-9a7e-5f1d2b8e9c41","repo":"open-agentos/productswarm","role":"builder","model":"claude-opus-5-5","event":"pr_opened","issue":2,"pr":16,"cost_usd":1.84,"token_counts":{"input":41200,"output":9800,"cache_read":512000,"cache_creation":38000},"tools":["Bash","Write"]}
```

A full session is in [`examples/session.jsonl`](examples/session.jsonl) (local spool) and [`examples/tracking-comment.md`](examples/tracking-comment.md) (what reaches GitHub).

## Storage

Per GOV-0003 (interim), each event is written to two places.

### Local spool

```
~/.productswarm/events/<session_id>.jsonl
```

One event per line, every field including `prompt`. Never leaves the machine.

### Tracking issue on GitHub

The session's role App opens **one issue per session** in `repo`:

- **Title:** `[heartbeat] <role> <session_id>`
- **Body:** starts with the marker `<!-- productswarm-heartbeat schema_version=1 session_id=<session_id> -->`, which is how the dashboard finds tracking issues (with the author being a `productswarm-*[bot]` App).
- **Labels:** none. Never `status:` or `gov:` labels (GOV-0003), and new issues are created unlabelled anyway (CLAUDE.md).
- The issue is closed after the `stopped` event is posted, so the open issue list only shows live sessions. The dashboard reads open and closed tracking issues alike.

Each **comment** carries one or more events, without `prompt`, as a fenced `jsonl` block, one event per line, in time order. The comment ends with the usual signature line, which readers ignore.

When the batch holds a `working_on` or `pr_opened` event, the comment starts with a line per event naming its issue in prose, above the fence: `builder session working on #N` or `builder opened PR #P for #N`. GitHub turns each `#N` into a "mentioned this" reference on issue N's timeline, so the issue shows the session working on it (#453). `working_on` is named only the first time the session works on that issue, so each issue's timeline gets one reference, not one per batch. The lines add no captured field: `issue` and `pr` are already in the event (GOV-0002). Readers ignore them like any other text outside the fence:

````
builder session working on #3

```jsonl
{"schema_version":1,"ts":"...","event":"heartbeat",...}
{"schema_version":1,"ts":"...","event":"working_on",...}
```

-- builder (claude-opus-5-5)
````

Readers take the first `jsonl` fence in each comment and parse each line against `#/$defs/remote`; anything else in the comment is ignored. The hook should batch events into one comment and post on state changes rather than every tool call, to stay well under GitHub's content-creation limits (about 80 a minute, 500 an hour).

The dashboard and future triage must ignore tracking issues when listing work issues.

## Changing the schema

Adding an optional field is a new minor revision of this document and keeps `schema_version: 1`. Removing or renaming a field, or changing a meaning, bumps `schema_version`. Any new field is a capture change and needs a `security` ruling first (GOV-0002). A new store needs a ruling that supersedes GOV-0003.
