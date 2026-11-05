"""The `gov:question` history over the page's window, gathered once per build (#406).

The desk's "What the numbers say" (trends.py, #406) reads it, and "How the questions went"
(#407) reuses it. It holds:

  - every `gov:question` created in the window, open or closed, and when each was decided:
    the first time the owner added `gov:ruled` or `ready`, or else when it was closed;
  - when each PR merged in the window was merged;
  - each GOV record's front-matter `date:`, read from the checkout.

API calls per build (#392): the questions list (one REST call per 100 questions updated in
the window), one search call per 100 merged PRs (search has its own rate limit), and one
GraphQL query per TIMELINE_BATCH questions for their label and close events.
Stdlib only.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import ghql

LABEL = "gov:question"
DECIDING_LABELS = ("gov:ruled", "ready")   # the owner adding either one decides the question
DECISIONS = Path(__file__).resolve().parent.parent / "governance" / "decisions"

TIMELINE_BATCH = 25   # questions per GraphQL query, as generate.COMMENTS_BATCH
# The first 100 events are the oldest, so they hold the first deciding label or close of any
# question with a plausible history; a question with more is read from those 100 alone.
TIMELINE_FIELD = (
    "i%d: issue(number: %d) { timelineItems(first: 100, itemTypes: [LABELED_EVENT, CLOSED_EVENT]) "
    "{ nodes { __typename ... on LabeledEvent { createdAt label { name } actor { login } } "
    "... on ClosedEvent { createdAt } } } }")


def parse_ts(s: str | None) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat((s or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def window_start(now: dt.datetime, days: int) -> dt.datetime:
    """Midnight UTC starting the window's first day: `days` whole UTC days, today the last,
    so each sparkline point is one full day."""
    first = now.astimezone(dt.timezone.utc).date() - dt.timedelta(days=days - 1)
    return dt.datetime(first.year, first.month, first.day, tzinfo=dt.timezone.utc)


def fetch(repo: str, now: dt.datetime, days: int, gh_items) -> dict:
    """The raw history. `gh_items(path, jq)` is generate.gh_items: every item of a paginated
    `gh api` read, picked out by `jq`."""
    start = window_start(now, days)
    since = start.strftime("%Y-%m-%dT%H:%M:%SZ")
    # `since` filters on updated_at, so this also returns older questions touched lately;
    # build() keeps only those created in the window.
    issues = [it for it in gh_items(f"repos/{repo}/issues?labels={LABEL}&state=all"
                                    f"&since={since}&per_page=100", ".[]")
              if "pull_request" not in it and (parse_ts(it.get("created_at")) or now) >= start]
    timelines = ghql.batched(repo, [it["number"] for it in issues], TIMELINE_FIELD,
                             TIMELINE_BATCH) if issues else {}
    merged = gh_items(f"search/issues?q=repo:{repo}+is:pr+is:merged+merged:>={start.date()}"
                      "&per_page=100", ".items[]")
    return {"issues": issues,
            "timelines": {n: ((t or {}).get("timelineItems") or {}).get("nodes") or []
                          for n, t in timelines.items()},
            "merged": [(m.get("pull_request") or {}).get("merged_at") or m.get("closed_at")
                       for m in merged],
            "records": record_dates()}


FM_RE = re.compile(r"\A---\n(.*?)\n---", re.S)
DATE_RE = re.compile(r"^date:\s*[\"']?(\d{4}-\d{2}-\d{2})", re.M)


def record_dates(path: Path = DECISIONS) -> list[dt.date]:
    """Each GOV record's front-matter `date:`, oldest first. The template and a record with
    no date (or one that doesn't parse) are left out."""
    out = []
    for f in sorted(path.glob("GOV-*.md")):
        if f.name.startswith("GOV-0000"):
            continue
        try:
            fm = FM_RE.match(f.read_text(encoding="utf-8"))
        except OSError:
            continue
        m = DATE_RE.search(fm.group(1)) if fm else None
        try:
            out.append(dt.date.fromisoformat(m.group(1)) if m else None)
        except ValueError:
            pass
    return sorted(d for d in out if d)


def decided(nodes: list[dict], owner: str | None) -> tuple[dt.datetime | None, str | None]:
    """When and how a question was decided: the owner's first `gov:ruled` or `ready`
    ("label"), or else its first close ("closed"), or (None, None) if neither."""
    labels = [parse_ts(n.get("createdAt")) for n in nodes
              if n.get("__typename") == "LabeledEvent"
              and (n.get("label") or {}).get("name") in DECIDING_LABELS
              and owner and (n.get("actor") or {}).get("login") == owner]
    labels = [t for t in labels if t]
    if labels:
        return min(labels), "label"
    closes = [t for t in (parse_ts(n.get("createdAt")) for n in nodes
                          if n.get("__typename") == "ClosedEvent") if t]
    return (min(closes), "closed") if closes else (None, None)


def build(data: dict, now: dt.datetime, days: int, owner: str | None) -> dict:
    """The history the panels read: questions (number, created, decided, decided_by, hours),
    merged-PR times and record dates, each inside the window."""
    start = window_start(now, days)
    qs = []
    for it in data.get("issues") or []:
        created = parse_ts(it.get("created_at"))
        if created is None or created < start:
            continue
        when, how = decided(data.get("timelines", {}).get(it["number"]) or [], owner)
        qs.append({"number": it["number"], "title": it.get("title", ""),
                   "url": it.get("html_url"), "state": it.get("state"), "created": created,
                   "decided": when, "decided_by": how,
                   "hours": (when - created).total_seconds() / 3600 if when else None})
    qs.sort(key=lambda q: q["number"])
    merged = sorted(t for t in (parse_ts(s) for s in data.get("merged") or []) if t and t >= start)
    return {"start": start, "now": now, "days": days, "questions": qs, "merged": merged,
            "records": [d for d in data.get("records") or [] if start.date() <= d <= now.date()],
            "last_record": max(data.get("records") or [], default=None)}
