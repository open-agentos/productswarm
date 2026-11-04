# Swarm dashboard

A read-only page showing what every agent session is doing. Built by `generate.py`: Python stdlib only, one static HTML file, no JavaScript (option 1 in gov question #26, which the owner chose).

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

## Needs you

The page opens with one ordered list of everything waiting on the owner (L5). `launcher/swarm inbox` prints the same list. Both come from `needs_you()` in `generate.py`, so the page and the command always show the same items in the same order.

| Order | What | Within the kind |
|---|---|---|
| 1 | Sessions blocked on a `gov:question`, with the question | longest blocked first |
| 2 | Open `gov:question`s nobody is blocked on, with their time to live | oldest first |
| 3 | Open PRs that aren't drafts, waiting for review or merge | oldest first |
| 4 | Idle sessions: no event within the idle threshold | longest idle first |
| 5 | Sessions over their role's spend cap (warn only, GOV-0008) | furthest over first |

Each item links to its question, PR or session tracking issue. An empty list says "Nothing is waiting on you." The list is built only from the GitHub data below, so it shows nothing that isn't already public (GOV-0002, GOV-0004).

## Digest

`dashboard/digest.py` renders the same list as short Markdown for a pinned GitHub issue that the owner reads on GitHub mobile (v3 F2, GOV-0015):

```bash
python3 dashboard/digest.py --print                       # prints the issue body; read-only
python3 dashboard/digest.py --update --repo OWNER/REPO     # writes it into the pinned issue
```

It starts with a hidden `<!-- productswarm-digest -->` marker and a count, then one heading per kind that has items, in the order above. Each bullet is the `#N` or `PR #N` reference, the title cut to about 60 characters, and the same detail and age as `swarm inbox`. Session items link to their tracking issue. It ends with the update time and the dashboard's Pages URL. It uses no tables, so nothing scrolls sideways on a phone. It reuses `fetch()`, `build()` and `needs_you()`, so it can't disagree with the page or `swarm inbox`, and like them it shows no local-only state (`watch.json` runs, held triggers, run cost). `--print` never writes to GitHub.

### Keeping the pinned issue current

`--update` (v3 F3) finds the one **open** issue whose body starts with `<!-- productswarm-digest -->` and replaces its body with the digest. Its only write is that one `PATCH repos/OWNER/REPO/issues/N`. It never creates, pins, labels, closes or comments on an issue. If there's no marked issue, or more than one, it says so and exits 1 without writing.

It edits only when the list changed. The comparison ignores the "Updated" line and the ages (`5m ago`, `just now`), which change with the clock alone, so a run where only time passed leaves the issue alone. Ages in the issue are therefore as of its "Updated" time. Editing an issue body sends no notification. It uses whatever `gh` is signed in as (`GH_TOKEN`); in the workflow that's the job's `GITHUB_TOKEN`, whose edits don't start other workflows.

Set the issue up once, by hand:

1. Open an issue titled, say, "Needs you", whose body starts with the marker line:

   ```
   <!-- productswarm-digest -->
   ```

   The rest of the body doesn't matter: the first `--update` replaces it.
2. Pin it (issue page → "Pin issue").
3. Run `python3 dashboard/digest.py --update --repo OWNER/REPO` once to fill it.

The digest issue isn't a `[heartbeat]` tracking issue or a `gov:question`, so it never appears in the needs-you list itself.

## What it reads

- **Sessions:** `[heartbeat]` tracking issues (GOV-0003). An issue counts only if its body starts with the heartbeat marker and it was opened by a `productswarm-<role>[bot]` App. Events are read from the first `jsonl` fence of comments **by that same App**; events whose `session_id`, `role` or `repo` don't match the issue, or that carry fields outside the remote schema (such as `prompt`), are dropped. The local spool is never read, so prompt text never reaches the page (GOV-0002).
- **Open PRs** and the issues they close.
- **`gov:question` issues**: the open ones, with the sessions blocked on each, and `gov:lapsed` ones closed within `--days`.
- **`governance/INDEX.md`**, from the checkout the page is built in (`dashboard.yml` checks out `main`).

## Governance

`governance.py` builds this section (#355). It replaced the page's old "Open gov questions" table and still shows everything that table did.

- **Recent decision records:** the 8 newest rows of `governance/INDEX.md`, newest first. Each row shows the ID (linked to its file), the one-line ruling, domain, shape, status and review-by date. A record whose review-by date has passed is marked "review date passed", because it is not precedent until someone re-affirms it (GOVERNANCE.md §6). One due within 30 days is marked "review due soon". Older records that are past or due get one line under the table, so no flag is hidden. The full index is a link.
- **Open gov questions:** a line of counts by shape and by domain, then one row per question. Each row shows its labels, its domain (`### Domain` in the template body), and its shape: an owner's `gov:shape/*` label if there is one, otherwise the body's `### Suggested shape`, marked "suggested". It also shows whether the question is blocking (the `gov:blocking` label or a "yes" under `### Blocking?`), its age, its time to live with days left or "past TTL", and the sessions waiting on it.
- **Lapsed questions:** questions labelled `gov:lapsed`, open, or closed within `--days`, each with its time to live. A muted line notes that a lapsed default is not precedent (GOVERNANCE.md §8).

The needs-you list and its past-TTL flag don't change. This section is for reading, not for acting on. It needs no new token permission: the index comes from the checkout, and the questions come from the issues the page already fetches.

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

Each session's spend, today's total and the last 7 UTC days are an **API list-price equivalent**, per the method in gov question #28. The owner asked for tokens to be split by payment plan if a session can tell. It can't without a new heartbeat field (#31), so every session is priced at list price whatever its plan. `spend.py` multiplies each session's latest cumulative `token_counts` by the model's list price. Cache writes are priced at the 1-hour rate. A non-null `cost_usd` on an event wins over the estimate. Per day is each session's increase in cost within that UTC day. This isn't what was billed: sessions on a subscription aren't charged per token.

Prices are in `spend.PRICES`, copied from the [pricing page](https://platform.claude.com/docs/en/about-claude/pricing) on the date in `PRICES_AS_OF`, which the page shows. When prices change, update both. Sessions with no token counts, or on a model missing from the table, show "—", are left out of totals, and are listed under the method note.

## Tests

```bash
python3 -m unittest discover -s dashboard
```

They use canned data and a fake `gh`, and never touch GitHub.
