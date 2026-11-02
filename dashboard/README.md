# Swarm dashboard

A read-only page showing what every agent session is doing. Built by `generate.py`: Python stdlib only, one static HTML file, no JavaScript (the default in gov question #26, pending a ruling).

## Generate it

```bash
python3 dashboard/generate.py            # writes dashboard/out/index.html (git-ignored)
open dashboard/out/index.html
```

Options: `--repo owner/name` (default: this checkout's `origin`), `--out PATH`, `--days N` (include sessions that stopped in the last N days, default 14), `--idle-minutes N` (default 15).

It reads GitHub through `gh api`, so inside a swarm session it acts as the role's App. Scheduled regeneration and hosting are #5; spend is #6.

## What it reads

- **Sessions:** `[heartbeat]` tracking issues (GOV-0003). An issue counts only if its body starts with the heartbeat marker and it was opened by a `productswarm-<role>[bot]` App. Events are read from the first `jsonl` fence of comments **by that same App**; events whose `session_id`, `role` or `repo` don't match the issue, or that carry fields outside the remote schema (such as `prompt`), are dropped. The local spool is never read, so prompt text never reaches the page (GOV-0002).
- **Open PRs** and the issues they close.
- **Open `gov:question` issues**, with the sessions blocked on each.

## Status

Per [heartbeat/SCHEMA.md](../heartbeat/SCHEMA.md):

| Status | When |
|---|---|
| stopped | latest event is `stopped`, or the tracking issue is closed |
| blocked | latest event other than `heartbeat`/`prompt_submitted` is `blocked`, and its gov question is still open |
| idle | no event for more than 15 minutes |
| active | otherwise |

A session's current issue is the most recent `issue` any of its events carried.

## Tests

```bash
python3 -m unittest discover -s dashboard
```

They use canned data and a fake `gh`, and never touch GitHub.
