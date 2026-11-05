"""Precedent in use: how often each GOV record is cited, by record and UTC day (#408, part 9
of #397).

A citation is a `GOV-NNNN` mention in an issue or PR body, an issue or PR comment, a PR
review, or a PR review comment, created in the page's window. Each text cites a record at
most once, however often it names it. A mention counts only on or after the record's
front-matter `date:` (a record can't be precedent before it was made), and only for a
record that exists in governance/decisions/. Left out:
  - signature lines (`-- builder (claude-opus-5-5)`), which name a role, not a record;
  - tracking issues (heartbeat events) and the pinned digest issue, which repeat other text;
  - review comments on files under governance/, which are the records being written.

Who: agents are `productswarm-*[bot]`, the owner is humans.owner in jurisdictions.yml, and
the reviewer (`productswarm-reviewer[bot]`, one of the agents) has its own column.

Cost (#392): this is the page's costliest panel. Bodies come free with generate.fetch()'s
issue list. Comments are `issues/comments?since=` and `pulls/comments?since=` at 100 a page,
and reviews one GraphQL query per REVIEWS_BATCH PRs. To keep a build near CARRY_PAGES REST
calls, the per-day counts are carried forward from the last published state.json (read from
the Pages URL, not the API), and only the days from its build day onwards are read again.
With no usable published copy, the whole window is read.

Findings are templates filled from the counts (#397), never written by a model.
Stdlib only, no JavaScript.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import urllib.request
from pathlib import Path

DECISIONS = Path(__file__).resolve().parent.parent / "governance" / "decisions"
VERSION = 1                 # of the `precedent` block in state.json; another can't be carried
REVIEWER = "productswarm-reviewer[bot]"
AGENT_RE = re.compile(r"\Aproductswarm-[a-z0-9-]+\[bot\]\Z")
CITE_RE = re.compile(r"\bGOV-(\d{4})\b")
# `-- <role> (<model>)`, the line CLAUDE.md asks every agent to end with.
SIGNATURE_RE = re.compile(r"^\s*--\s+[A-Za-z][\w-]*\s*\([^)\n]*\)\s*$", re.M)
ISSUE_NUM_RE = re.compile(r"/(?:issues|pulls)/(\d+)\Z")
REVIEWS_BATCH = 25
REVIEWS_FIELD = ("p%d: pullRequest(number: %d) { reviews(first: 100) "
                 "{ totalCount nodes { body submittedAt author { login __typename } } } }")
WHO = ("n", "agents", "owner", "reviewer")


# ---------------------------------------------------------------- records

FRONT_RE = re.compile(r"\A---\n(.*?)\n---", re.S)


def front_matter(text: str) -> dict[str, str]:
    """Top-level `key: value` lines of a record's YAML front matter (no nesting needed)."""
    m = FRONT_RE.match(text or "")
    out = {}
    for line in (m.group(1) if m else "").splitlines():
        k, sep, v = line.partition(":")
        if sep and k and not k[0].isspace():
            out[k.strip()] = v.strip().strip('"\'')
    return out


def load_records(folder: Path = DECISIONS) -> dict[str, dict]:
    """Each record by id: its `date:` and `status:`. The template and records with no
    parsable date are left out, since a citation of them can't be placed after it."""
    out = {}
    for f in sorted(folder.glob("GOV-*.md")):
        fm = front_matter(f.read_text(encoding="utf-8"))
        try:
            made = dt.date.fromisoformat(fm.get("date", ""))
        except ValueError:
            continue
        if CITE_RE.fullmatch(fm.get("id", "")):
            out[fm["id"]] = {"id": fm["id"], "date": made, "status": fm.get("status", ""),
                            "file": f.name}
    return out


# ---------------------------------------------------------------- reading GitHub

def pages_state_url(repo: str) -> str:
    owner, name = repo.split("/", 1)
    return f"https://{owner.lower()}.github.io/{name}/state.json"


def published(repo: str, timeout: int = 20) -> dict | None:
    """The last published state.json, from the Pages site (no API call), or None."""
    try:
        with urllib.request.urlopen(pages_state_url(repo), timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except (OSError, ValueError):
        return None


def utc(s: str | None) -> dt.datetime | None:
    try:
        t = dt.datetime.fromisoformat((s or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else None


def day_start(d: dt.date) -> dt.datetime:
    return dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc)


def carry(prev: dict | None, start: dt.date, now: dt.datetime) -> tuple[dt.date, dict]:
    """From the last published state: the first day to read again, and the counts kept for
    the days before it. The build day itself is read again (it was only partly counted).
    A missing, older-version or too-short copy gives (start, {}): read the whole window."""
    p = (prev or {}).get("precedent") or {}
    built = utc((prev or {}).get("built_at"))
    try:
        covered = dt.date.fromisoformat(p.get("from") or "")
    except (TypeError, ValueError):
        covered = None
    if (p.get("version") != VERSION or not isinstance(p.get("counts"), dict) or built is None
            or covered is None or covered > start or built > now or built.date() <= start):
        return start, {}
    cut = built.date()
    kept: dict[str, dict[str, dict]] = {}
    for rec, days in p["counts"].items():
        for d, c in (days or {}).items():
            try:
                day = dt.date.fromisoformat(d)
            except ValueError:
                continue
            if start <= day < cut and isinstance(c, dict):
                kept.setdefault(rec, {})[d] = {k: int(c.get(k) or 0) for k in WHO}
    return cut, kept


def number(url: str | None) -> int | None:
    m = ISSUE_NUM_RE.search(url or "")
    return int(m.group(1)) if m else None


def texts(items: list[dict], comments: list[dict], review_comments: list[dict],
          reviews: dict[int, list[dict]], since: dt.datetime, skip: set[int]) -> list[dict]:
    """Every text created at or after `since` as {"ts", "login", "body"}, outside the
    `skip` issues and governance/ files. `items` are REST issues and PRs (bodies),
    `comments` REST issue comments, `review_comments` REST PR review comments, and
    `reviews` each PR's reviews as {"login", "body", "ts"}."""
    out = []

    def add(ts, login, body):
        t = utc(ts)
        if t and t >= since and body:
            out.append({"ts": t, "login": login or "", "body": body})

    for it in items:
        if it["number"] not in skip:
            add(it.get("created_at"), (it.get("user") or {}).get("login"), it.get("body"))
    for c in comments:
        if number(c.get("issue_url")) not in skip:
            add(c.get("created_at"), (c.get("user") or {}).get("login"), c.get("body"))
    for c in review_comments:
        if not (c.get("path") or "").startswith("governance/"):
            add(c.get("created_at"), (c.get("user") or {}).get("login"), c.get("body"))
    for n, rs in reviews.items():
        if n not in skip:
            for r in rs:
                add(r.get("ts"), r.get("login"), r.get("body"))
    return out


def window_reviews(repo: str, numbers: list[int], ghql, gh_items) -> dict[int, list[dict]]:
    """Each PR's reviews: one GraphQL query per REVIEWS_BATCH PRs; REST for a PR with more
    than 100 reviews or one the query didn't return."""
    out = {}
    for n, pr in ghql.batched(repo, numbers, REVIEWS_FIELD, REVIEWS_BATCH).items():
        nodes = ghql.complete((pr or {}).get("reviews"))
        if nodes is None:
            out[n] = [{"login": (r.get("user") or {}).get("login"), "body": r.get("body"),
                       "ts": r.get("submitted_at")}
                      for r in gh_items(f"repos/{repo}/pulls/{n}/reviews?per_page=100")]
        else:
            out[n] = [{"login": ghql.login(r.get("author")), "body": r.get("body"),
                       "ts": r.get("submittedAt")} for r in nodes]
    return out


def fetch(repo: str, now: dt.datetime, days: int, items: list[dict], skip: set[int],
          gh_items, ghql, owner: str | None, prev: dict | None) -> dict:
    """The panel's data. `items` are the REST issues and PRs generate.fetch() already read
    (open, and closed in the window), `skip` the tracking and digest issues, and `prev` the
    last published state.json (or None)."""
    start = now.date() - dt.timedelta(days=days - 1)
    first, kept = carry(prev, start, now)
    since = day_start(first)
    stamp = since.strftime("%Y-%m-%dT%H:%M:%SZ")
    comments = gh_items(f"repos/{repo}/issues/comments?since={stamp}&per_page=100")
    review_comments = gh_items(f"repos/{repo}/pulls/comments?since={stamp}&per_page=100")
    prs = sorted(it["number"] for it in items
                 if "pull_request" in it and (utc(it.get("updated_at")) or now) >= since)
    reviews = window_reviews(repo, prs, ghql, gh_items) if prs else {}
    return {"start": start, "first": first, "kept": kept, "owner": owner,
            "carried_from": prev.get("built_at") if prev and first > start else None,
            "texts": texts(items, comments, review_comments, reviews, since, skip),
            "calls": {"rest": pages(len(comments)) + pages(len(review_comments)),
                      "graphql": -(-len(prs) // REVIEWS_BATCH)}}


def pages(n: int) -> int:
    """REST calls a paginated read of n items took, at 100 a page (one even when empty)."""
    return max(1, -(-n // 100))


# ---------------------------------------------------------------- counting

def cited(body: str) -> set[str]:
    """The records one text cites, once each, with signature lines left out."""
    return {f"GOV-{n}" for n in CITE_RE.findall(SIGNATURE_RE.sub("", body or ""))}


def who(login: str, owner: str | None) -> tuple[str, ...]:
    """The columns a citation by `login` counts in, besides the total."""
    if login == REVIEWER:
        return ("agents", "reviewer")
    if AGENT_RE.match(login or ""):
        return ("agents",)
    if owner and login == owner:
        return ("owner",)
    return ()


def count(found: list[dict], records: dict[str, dict], owner: str | None,
          counts: dict | None = None) -> dict[str, dict[str, dict]]:
    """Add each text's citations to `counts` ({record: {day: {n, agents, owner, reviewer}}}),
    skipping records that don't exist and mentions dated before the record was made."""
    counts = {r: {d: dict(c) for d, c in days.items()} for r, days in (counts or {}).items()}
    for t in found:
        day = t["ts"].astimezone(dt.timezone.utc).date()
        for rec in cited(t["body"]):
            if rec not in records or day < records[rec]["date"]:
                continue
            c = counts.setdefault(rec, {}).setdefault(day.isoformat(), dict.fromkeys(WHO, 0))
            for k in ("n",) + who(t["login"], owner):
                c[k] += 1
    return counts


def totals(days: dict[str, dict]) -> dict[str, int]:
    return {k: sum(c.get(k, 0) for c in days.values()) for k in WHO}


# ---------------------------------------------------------------- findings

def pct(a: int, b: int) -> int:
    return round(100 * a / b) if b else 0


def findings(counts: dict, records: dict[str, dict], start: dt.date, days: int) -> list[str]:
    """Three sentences from templates: the newest record in use, the share of citations by
    agents, and the in-force records not cited in the window."""
    span = "today" if days == 1 else f"in the last {days} days"
    out = []
    in_force = [r for r in records.values() if r["status"] == "in-force"]
    if in_force:
        newest = max(in_force, key=lambda r: (r["date"], r["id"]))
        rid, made = newest["id"], newest["date"]
        mine = counts.get(rid, {})
        if made >= start:
            n = (mine.get(made.isoformat()) or {}).get("n", 0)
            out.append(f"{rid}, the newest record, was cited {n} time{'s' * (n != 1)} on its "
                       f"first day ({made.isoformat()})"
                       + (f" and {totals(mine)['n']} in all." if totals(mine)["n"] != n else "."))
        else:
            n = totals(mine)["n"]
            out.append(f"{rid}, the newest record, was cited {n} time{'s' * (n != 1)} {span}.")
    all_n = sum(totals(d)["n"] for d in counts.values())
    agents = sum(totals(d)["agents"] for d in counts.values())
    owner = sum(totals(d)["owner"] for d in counts.values())
    if all_n:
        out.append(f"{pct(agents, all_n)}% of citations are by agents ({agents} of {all_n}); "
                   f"{pct(owner, all_n)}% are by the owner.")
    else:
        out.append(f"No record was cited {span}.")
    quiet = sorted(r["id"] for r in in_force if not totals(counts.get(r["id"], {}))["n"])
    if quiet:
        out.append(f"Not cited {span}: {', '.join(quiet)}.")
    elif in_force:
        out.append(f"Every in-force record was cited {span}.")
    return out


# ---------------------------------------------------------------- model, page and state

def build(data: dict | None, records: dict[str, dict], now: dt.datetime, days: int) -> dict | None:
    if not data:
        return None
    counts = count(data["texts"], records, data.get("owner"), data["kept"])
    start = data["start"]
    # No citation can come before the first record, so the grid starts there if it's later.
    first = max([start] + [min(r["date"] for r in records.values())] * bool(records))
    window = [first + dt.timedelta(days=i) for i in range((now.date() - first).days + 1)]
    return {"version": VERSION, "from": start, "days": window, "counts": counts,
            "records": sorted(records.values(), key=lambda r: r["id"]),
            "totals": {r: totals(d) for r, d in counts.items()},
            "findings": findings(counts, records, start, days),
            "read": {"from": data["first"], "carried_from": data.get("carried_from"),
                     "calls": data.get("calls")}}


def esc(x) -> str:
    return html.escape("" if x is None else str(x))


def shade(n: int, top: int) -> str:
    """A cell's tint: agents blue, stronger with more citations; never dark enough to hide
    the number."""
    if not n or not top:
        return ""
    return f' style="background:rgba(31,79,184,{0.08 + 0.32 * n / top:.2f})"'


def render(p: dict | None, repo: str) -> str:
    """The grid (records down, days across, then totals) in its own scrolling box, and the
    findings above it."""
    if not p:
        return ""
    days, counts = p["days"], p["counts"]
    top = max((c["n"] for d in counts.values() for c in d.values()), default=0)
    head = ("<tr><th>Record</th>"
            + "".join(f'<th class="num" title="{d.isoformat()}">{d.strftime("%m-%d")}</th>'
                      for d in days)
            + '<th class="num">Total</th><th class="num">Agents</th><th class="num">Owner</th>'
            '<th class="num">By reviewer</th></tr>')
    rows = []
    for r in sorted(p["records"], key=lambda r: r["id"], reverse=True):
        mine, t = counts.get(r["id"], {}), p["totals"].get(r["id"]) or dict.fromkeys(WHO, 0)
        cells = []
        for d in days:
            n = (mine.get(d.isoformat()) or {}).get("n", 0)
            before = d < r["date"]
            cells.append(f'<td class="num{" muted" if before or not n else ""}"{shade(n, top)}>'
                         f'{"" if before else n or "·"}</td>')
        quiet = " muted" if r["status"] != "in-force" else ""
        url = f"https://github.com/{esc(repo)}/blob/main/governance/decisions/{esc(r.get('file', ''))}"
        rows.append(f'<tr><td class="id{quiet}"><a href="{url}">{esc(r["id"])}</a></td>'
                    + "".join(cells)
                    + "".join(f'<td class="num">{t[k]}</td>' for k in WHO) + "</tr>")
    note = ("A citation is a GOV-NNNN mention in an issue or PR body, comment or review, "
            "once per text, on or after the record's date. Signature lines, tracking issues, "
            "the digest issue and review comments on governance/ files don't count. "
            "Days are UTC; a blank cell is before the record was made.")
    findings_html = "".join(f"<li>{esc(f)}</li>" for f in p["findings"])
    return "\n".join([
        "<h2>Precedent in use</h2>",
        f'<ul class="findings">{findings_html}</ul>',
        f'<div class="scroll"><table class="precedent">{head}{"".join(rows)}</table></div>',
        f'<p class="muted method">{esc(note)}</p>'])


def state(p: dict | None) -> dict | None:
    """The block state.json carries, and the next build carries forward from."""
    if not p:
        return None
    return {"version": p["version"], "from": p["from"], "counts": p["counts"],
            "totals": p["totals"], "findings": p["findings"],
            "records": [{"id": r["id"], "date": r["date"], "status": r["status"]}
                        for r in p["records"]],
            "read": p["read"]}
