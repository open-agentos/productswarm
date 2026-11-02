# Swarm dashboard

A read-only page showing what every agent session is doing. Built by `generate.py`: Python stdlib only, one static HTML file, no JavaScript (the default in gov question #26, pending a ruling).

## Generate it

```bash
python3 dashboard/generate.py            # writes dashboard/out/index.html (git-ignored)
open dashboard/out/index.html
```

Options: `--repo owner/name` (default: this checkout's `origin`), `--out PATH`, `--days N` (include sessions that stopped in the last N days, default 14), `--idle-minutes N` (default 15).

It reads GitHub through `gh api`, so inside a swarm session it acts as the role's App.

## Where it's published

`.github/workflows/dashboard.yml` regenerates the page every 15 minutes (plus a manual run) and publishes it to GitHub Pages at <https://open-agentos.github.io/productswarm/>. It runs on a schedule only, never on issue, comment or PR events, and its token can read the repo but not write to it (`pages` and `id-token` are only for the deploy), per the owner's choice on #32.

The page is **public**, because this repo is. It shows nothing that isn't already public in the repo's issues and comments, and it carries `noindex` so search engines skip it, per the owner's choice on #33. GitHub may delay scheduled runs, and disables them on public repos after 60 days without repo activity.

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

## Spend

Each session's spend, today's total and the last 7 UTC days are an **API list-price equivalent**, per the default in gov question #28 (pending a ruling). `spend.py` multiplies each session's latest cumulative `token_counts` by the model's list price. Cache writes are priced at the 1-hour rate. A non-null `cost_usd` on an event wins over the estimate. Per day is each session's increase in cost within that UTC day. This isn't what was billed: sessions on a subscription aren't charged per token.

Prices are in `spend.PRICES`, copied from the [pricing page](https://platform.claude.com/docs/en/about-claude/pricing) on the date in `PRICES_AS_OF`, which the page shows. When prices change, update both. Sessions with no token counts, or on a model missing from the table, show "—", are left out of totals, and are listed under the method note.

## Tests

```bash
python3 -m unittest discover -s dashboard
```

They use canned data and a fake `gh`, and never touch GitHub.
