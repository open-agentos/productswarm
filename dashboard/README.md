# Swarm dashboard

Read-only pages showing what every agent session is doing and how the swarm is governed. Built by `generate.py`: Python stdlib only, static HTML files, no JavaScript (option 1 in gov question #26, which the owner chose).

## Generate it

```bash
python3 dashboard/generate.py            # writes dashboard/out/ (git-ignored)
open dashboard/out/index.html
```

Options: `--repo owner/name` (default: this checkout's `origin`), `--out PATH` (the desk page; the other pages and `fonts/` are written beside it), `--days N` (include sessions that stopped in the last N days, default 14), `--idle-minutes N` (default 15).

It reads GitHub through `gh api`, so inside a swarm session it acts as the role's App.

## Pages

One build writes three pages, and the fonts, into the `--out` page's directory (#401, part of #397):

| Page | What it shows |
|---|---|
| `index.html`, the **desk** | Open committees (the open part of [Committees](#committees)), [What the numbers say](#what-the-numbers-say), and a one-line pointer to the other pages. #397's later issues add the desk's other panels here. |
| `operations.html` | The [needs-you](#needs-you) list and its tiles, sessions, open PRs, the [Actions reviewer](#actions-reviewer) section, [v3 progress](#v3-progress) and [spend per day](#spend) |
| `decisions.html` | The [governance](#governance) section with the **full** decision log from `governance/INDEX.md`, open and lapsed gov questions, and ended committees as "Past committees" |

Every page carries `noindex`, reloads itself every 300 seconds, fits a phone's width (only `.scroll` boxes scroll sideways), and ends with a footer linking the three pages. The authority map (#410) joins the footer when it lands. `generate.render(model)` returns the pages by file name.

### Look

`layout.py` holds the look and the page shell every page uses, so colours and fonts are set in one place: paper `#F4F3EE`, ink, agents blue `#1F4FB8` (active sessions), owner amber `#A35A00` (what waits on the owner), and red `#C2361B` only for live marks and blocks (#397). Text is IBM Plex Sans, numbers, times and code Plex Mono, headings Plex Sans Condensed.

The fonts are **self-hosted**, so the public page loads nothing from a third party. `static/fonts/` holds the Latin-1 subset, as woff2, of only the four faces the CSS uses (Sans 400 and 600, Mono 400, Sans Condensed 600), from IBM's `@ibm/plex-sans` 1.1.0, `@ibm/plex-mono` 2.5.0 and `@ibm/plex-sans-condensed` 2.0.0 packages, with their SIL Open Font License. Together they add 82,776 bytes (87,232 with the licence) to the published site. `generate.py` copies them to `fonts/` beside the pages on every build, before writing the pages. A character outside Latin-1 (an arrow, say) falls back to the system font.

## Where it's published

`.github/workflows/dashboard.yml` regenerates the pages every 15 minutes (plus a manual run) and publishes it to GitHub Pages at <https://open-agentos.github.io/productswarm/>. It runs on a schedule only, never on issue, comment or PR events, and its token can read the repo but not write to it (`pages` and `id-token` are only for the deploy), per the owner's choice on #32.

GitHub runs that schedule hours apart here, so the nudge in `.github/workflows/digest-nudge.yml` (shared with the digest) dispatches `dashboard.yml` on `main` when something happens: an issue or PR is opened, closed, reopened or relabelled, a PR is pushed or reviewed, or a Discussion post or comment is created or edited (#351). The nudge passes no event data and holds no secrets; `dashboard.yml` itself still runs only on its schedule and dispatch, and the schedule stays as the safety net. An open page reloads itself every 300 seconds with a `<meta http-equiv="refresh">` tag (plain HTML, no script), so it picks up a rebuild within about five minutes.

### How often it rebuilds

The workflow's token (`GITHUB_TOKEN`) gets about 1,000 REST calls and 1,000 GraphQL points an hour, shared with the digest. When every nudge rebuilt the page at well over 100 calls each, a busy hour ran it out and every run failed (#392). So:

- **Nudged rebuilds are spaced.** A rebuild started by the nudge (a `workflow_dispatch` by `github-actions[bot]`) first looks for the last `dashboard.yml` run that published: it lists the newest 5 successful runs and reads their jobs, newest first, until one whose `deploy-pages` step succeeded (2 to 6 Actions API calls). A run that skipped also ends `success`, so it doesn't count. If the last publish was less than 5 minutes ago, it prints one line and exits 0 without publishing. The schedule and the next event catch up. A scheduled run and a person's manual dispatch always rebuild. So the page rebuilds at most about every 5 minutes from nudges, plus the schedule.
- **A rebuild costs about 23 REST calls and 19 GraphQL queries** (it was 258 calls on 2026-11-04). Tracking-issue comments, the reviewer section's reviews and commits, and the red check's reviews are read 20 or 25 issues or PRs to a GraphQL query (`ghql.py`); an issue or PR with more than 100 comments or reviews falls back to REST. The Actions reviewer section reads the newest 15 sweeps, one jobs call each.
- **A low allowance skips cleanly.** Before fetching, `generate.py` reads `gh api rate_limit`, which doesn't count against the allowance. If fewer than 80 REST calls or 50 GraphQL points are left (`PAGE_NEEDS`), it prints one line and exits 0 without publishing, so the last good page stays up and the run isn't a failure. `digest.py --update` does the same below 30 of each (`DIGEST_NEEDS`) and leaves the issue as it was.

When `generate.py` skips, it writes no page, so `dashboard.yml` must skip its upload and deploy steps for the run to end green: `if: hashFiles('_site/index.html') != ''` on both. That's a workflow change, so it's proposed in #392's PR for the owner to commit (#32); until then a skipped run fails at the upload step, and the last good page still stays up.

The page is **public**, because this repo is. It shows nothing that isn't already public in the repo's issues and comments, and it carries `noindex` so search engines skip it, per the owner's choice on #33. GitHub may delay scheduled runs, and disables them on public repos after 60 days without repo activity.

## state.json

Each build also writes `state.json` beside `index.html` (so `_site/state.json` on Pages): the data the page shows, as JSON, with no HTML (`state.py`, #400). It's written only when the page is, so a skipped build leaves both as they were. Timestamps are RFC 3339 in UTC (`2026-11-05T07:20:08Z`); dates are `YYYY-MM-DD`.

| Key | What |
|---|---|
| `schema` | `1` |
| `built_at`, `repo`, `idle_minutes` | when and for which repo it was built, and the idle threshold |
| `needs_you` | the needs-you list below, without over-cap items |
| `sessions` | each session's `session_id`, `role`, `model`, `status`, `issue`, `pr`, `gov_question`, `last_event`, `last_ts`, `started_ts` and `tracking_issue` |
| `prs` | open PRs: `number`, `title`, `url`, `author`, `draft`, `review`, `created_ts`, `closes`, `needs_owner` |
| `gov_questions` | open `gov:question`s with their fields, time to live and the `session_id`s waiting on them |
| `governance` | recent and flagged records, counts by shape and domain, lapsed questions |
| `committees`, `progress`, `reviewer_runs` | those sections' data; `reviewer_runs.unreviewed` is PR numbers |
| `trends` | [What the numbers say](#what-the-numbers-say): `days`, `first_day`, `min_count`, and each trend's `name`, `sentence`, `too_few` and `series` (one `{date, value}` per day; `value` is `null` on a day with no data) |

It carries **no cost**: no session cost, daily spend, cap, over-cap flag or spend totals (GOV-0014; #397). It's public like the page (#33), and sessions and PRs keep only the fields the page shows. Later panels add their slice to `state.py`.

## Needs you

The operations page opens with one ordered list of everything waiting on the owner (L5). `launcher/swarm inbox` prints the same list. Both come from `needs_you()` in `generate.py`, so the page and the command always show the same items in the same order.

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

## What the numbers say

The desk's trends (#406): each one is a sentence and a sparkline, never a bare count. `questions.py` gathers the `gov:question` history once per build (#407 reuses it); `trends.py` turns it into sentences and inline SVG.

| Trend | Sentence | Sparkline, one point per UTC day |
|---|---|---|
| Questions per merged PR | "0.8 questions per merged PR this week, down from 1.4 the week before." | questions asked that day ÷ PRs merged that day; a gap on a day nothing merged |
| Median hours to decide | "Median 6.2 hours to decide (14 questions; 2 not decided yet)." | the median hours of the questions decided that day; a gap on a day none was |
| Records a day | "1.3 records a day; none since 3 Nov." (or "the latest today") | records dated that day |

- **The window** is `--days` whole UTC days, today the last (14 by default). "This week" is the last 7 of them and "the week before" the 7 before. A question counts if it was **created** in the window, open or closed.
- **Decided** means the first time the owner (`humans.owner` in `jurisdictions.yml`) added `gov:ruled` or `ready`; failing that, the first time it was closed. Hours to decide run from creation to then. A label someone else added doesn't count (GOV-0006).
- **Sentences are templates filled from numbers** (#397). A direction word ("up from", "down from", "the same as") appears only when both weeks had at least 3 merged PRs, and is chosen from the two rounded figures.
- **"Too few to tell"** under 3 merged PRs this week, decided questions or records in the window. With one or two values a ratio or median moves by half or more when one more arrives, so it can't show a trend; 3 is the smallest count with a middle value. The trend's `too_few` is then true and its line is grey.
- **Sparklines** are inline SVG with no axes or labels, scaled to the series' own maximum. Each has `role="img"` and a `<title>` and `aria-label` listing every day's value as its text alternative.

**API calls added per build (#392):** 1 REST call per 100 questions updated in the window (the `issues?labels=gov:question&state=all&since=` list), 1 search call per 100 PRs merged in the window (`search/issues`, which has its own rate limit), and 1 GraphQL query per 25 questions for their label and close events (`timelineItems`). Record dates come from the checkout. Against this repo on 2026-11-05: 35 questions and 103 merged PRs in 14 days took 1 REST page, 2 search pages and 2 GraphQL queries, from 3 `gh` invocations (the whole rebuild: 47). Only the page reads these (`fetch(..., with_questions=True)`); `swarm inbox`, `swarm watch` and the digest don't.

## What it reads

- **Sessions:** `[heartbeat]` tracking issues (GOV-0003). An issue counts only if its body starts with the heartbeat marker and it was opened by a `productswarm-<role>[bot]` App. Events are read from the first `jsonl` fence of comments **by that same App**; events whose `session_id`, `role` or `repo` don't match the issue, or that carry fields outside the remote schema (such as `prompt`), are dropped. The local spool is never read, so prompt text never reaches the page (GOV-0002).
- **Open PRs** and the issues they close.
- **`gov:question` issues**: the open ones, with the sessions blocked on each, and `gov:lapsed` ones closed within `--days`.
- **The `gov:question` history** for [What the numbers say](#what-the-numbers-say): every question created in the window, its label and close events, PRs merged in the window, and each record's front-matter `date:` from the checkout.
- **`governance/INDEX.md`**, from the checkout the page is built in (`dashboard.yml` checks out `main`).
- **v3 progress:** see [v3 progress](#v3-progress).
- **Reviewer workflow runs and jobs** from the Actions API, and the reviews and commits of the PRs they reviewed (see [Actions reviewer](#actions-reviewer)). Never job logs.
- **Committee Discussions** (`committees.py`, #353): every Discussion in the "Committees" category, through `gh api graphql`, plus the `gov:question` each one serves (from a `<!-- productswarm-committee question=N -->` marker, else the `Committee for #N:` title) and that question's record in `governance/decisions/` (front matter `question: "#N"`). Members come from the `## Members` or `### Members` table, the post order from rule 1 under `Rules`, and round posts are top-level comments headed `Round N: <seat>` by that seat's App. From each post it keeps only the round, seat, author, time, link, signature model and the first bold phrase of its Recommendation. From the owner's comments on the question it keeps only whether the convening, summary and ruling comments exist, when, and their links, so no cost line or other text reaches the page. It derives status (convened, round N, summary, ratified, record), §7.2 diversity, the next seat, rounds used of 3 and posts per member per UTC day against §8's 6. A Discussion that doesn't match #314's layout shows as "unparsed". A token that can't read Discussions gives a note and the rest of the page still builds. Only the page reads these (`fetch(..., with_committees=True)` in `main()`); `swarm inbox`, `swarm watch` and the digest skip the GraphQL calls. The page shows them in the Committees section below.

## Governance

`governance.py` builds this section (#355). It replaced the page's old "Open gov questions" table and still shows everything that table did.

- **Decision log:** on the decisions page, every row of `governance/INDEX.md`, newest first (#401). (`governance.render(..., full=False)` gives the old 8 newest, with one line for older flagged records.) Each row shows the ID (linked to its file), the one-line ruling, domain, shape, status and review-by date. A record whose review-by date has passed is marked "review date passed", because it is not precedent until someone re-affirms it (GOVERNANCE.md §6). One due within 30 days is marked "review due soon". The index itself is a link.
- **Open gov questions:** a line of counts by shape and by domain, then one row per question. Each row shows its labels, its domain (`### Domain` in the template body), and its shape: an owner's `gov:shape/*` label if there is one, otherwise the body's `### Suggested shape`, marked "suggested". It also shows whether the question is blocking (the `gov:blocking` label or a "yes" under `### Blocking?`), its age, its time to live with days left or "past TTL", and the sessions waiting on it.
- **Lapsed questions:** questions labelled `gov:lapsed`, open, or closed within `--days`, each with its time to live. A muted line notes that a lapsed default is not precedent (GOVERNANCE.md §8).

The needs-you list and its past-TTL flag don't change. This section is for reading, not for acting on. It needs no new token permission: the index comes from the checkout, and the questions come from the issues the page already fetches.

## Committees

`committees.render()` draws the committees `committees.py` reads (#354). Open committees, with the unparsed and read-problem lines, are on the desk (`part="open"`). Committees that ended (record merged, or the question closed) are on the decisions page under "Past committees", in a collapsed "N ended" `<details>` (`part="ended"`). With no committees there's no section; with none ended, no "Past committees".

For each committee:

- **Header:** the question, linked with its title, and the Discussion, then the timeline: convened → round 1 … round N → summary → ratified → record GOV-NNNN. Each step reached is dated and linked to its comment, round post or record file. The current step is bold and the steps not reached yet are muted.
- **Members:** seat, role, model and evidence base from the Discussion's table, then "§7.2 diversity met: 2 models, 3 evidence bases" (or "not met").
- **Round grid:** a row per member and a column per round. Each cell links to the post, shows its time (UTC) and that post's recommendation phrase. If a post's signature names another model than the table, the cell says "signed <model>". The next empty cell says "waiting on <seat>", which can open a new round's column. Before a summary, a post the reader counts as missed says "missed". Once a summary exists, the cells of rounds that never ran say "stopped early" if rule 6 stopped the committee. Other empty cells stay blank. The grid scrolls in its own box at phone width.
- **Last line:** convergence ("all agree after round N" when every member's last-round phrase matches; otherwise "dissent: <seats>" for the seats whose latest phrase differs from the majority's, or "no majority"), "rounds used: N of 3" (§7.4), and "nobody over 6 posts a day" or a red "over 6 posts a day" with the seat, count and UTC day (§8).

Phrases are compared as text, ignoring case and spacing. So #314 shows "dissent: proposer": its round-2 phrase is "Option 3 as 3c" and the other two say "Option 3 as 3c+E".

Discussions that don't match #314's layout are listed as muted "Unparsed" links. Read problems ("can't read Discussions", a question that couldn't be read, a marker that disagrees with the title) go on one muted line. A repo with no Committees category shows nothing. The section shows no cost and no post or summary text beyond each recommendation phrase.

## v3 progress

A section from `progress.py` (#357) shows where v3 stands. Only the page shows it: `digest.py` and `swarm inbox` don't read it.

| Line | Where it comes from |
|---|---|
| One row per GOV-0015 stage (B, F, C stage 1) | the `### Stage …` tables in PRODUCT.md's v3 section in the checkout: "N of M issues closed" over the `#N`s in each table's `Issue` column, with the open ones linked. A heading's own "(done)" shows as done. Rows with no issue number are skipped. |
| C stage 2 | "not planned (GOV-0015)" while PRODUCT.md's v3 section says so |
| Eval bar | the `**Result: …**` line under "Against the bar" in `evals/results.md`, linked; "unknown" if there's no such line |
| Planted-defect gate | #331's state: "not run" while it's open, "done, see #331" once it's closed. The result comment has no fixed wording, so it isn't parsed. |
| Red check | `evals/red_check.py`'s own `fetch()`, `count()` and `summary()`: reds counted of the first 5, how many reached the 2-round bound, and whether to revisit (more than 2) once all 5 are settled. Before #329's PR merges it says so. No cost is shown (`evals/README.md`). |

The stage issues' states, and #331's, come from one GraphQL query, since closed issues may be older than `--days`. `red_check.py` imports `generate` at load, so `progress.py` imports it inside a function, not at load. Everything is read with the workflow's existing `issues: read` and `pull-requests: read`. If a read fails, that line says "couldn't read" and the rest of the page still publishes.

## Actions reviewer

`reviewer_runs.py` builds this section (#356). It covers the last 7 days:

- **Sweeps:** runs of `reviewer.yml` (the newest 15 at most, #392), each with when and how it started (`schedule`, `nudge` for a `workflow_dispatch` by `github-actions[bot]` from `reviewer-nudge.yml`, or `manual (<login>)` for a person's dispatch), its conclusion, and the `review #N <sha>` jobs it ran (`REVIEW_JOB` in `launcher/actions_review.py`). A successful sweep with no review jobs says "nothing to review".
- **Success rate:** "N of M review jobs succeeded", counting finished review jobs, not sweeps, and listing the ones that didn't succeed.
- **Commit to review:** for each head the reviewer App reviewed in the window, the time from that commit's committer date to the App's first review of it; the median and the longest. GitHub doesn't give push time, so this is commit time. A review counts for the commit it was made on, never for a later head.
- **Unreviewed builder heads:** a count of the builder PRs `unreviewed()` flags, linked. They're in the needs-you list too.

Only the page reads it (`fetch(..., with_actions=True)` in `main()`): `swarm ls`, `swarm inbox`, `swarm watch` and the digest make no Actions API calls. It reads run, job, review and commit metadata only. It **shows no cost** and never fetches job logs, where GOV-0016 puts `total_cost_usd` (#348). It needs `actions: read` on the workflow's token; without it the section shows one muted line ("can't read Actions runs: the token needs `actions: read`") and the rest of the page still builds.

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
