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
import html
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
            "merged_items": merged,   # the Bridge's Reports (bridge.py, #926)
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


RAISED_BY_RE = re.compile(r"^###\s*Raised by\s*\n+\s*(\S[^\n]*?)\s*$", re.M)


def raised_by(body: str | None) -> str | None:
    """The template's `### Raised by` answer, e.g. "builder, on #407"."""
    m = RAISED_BY_RE.search(body or "")
    return m.group(1) if m else None


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
                   "author": (it.get("user") or {}).get("login"),
                   "raised_by": raised_by(it.get("body")),
                   "labels": [lb.get("name") for lb in it.get("labels") or []
                              if isinstance(lb, dict)],
                   "decided": when, "decided_by": how,
                   "hours": (when - created).total_seconds() / 3600 if when else None})
    qs.sort(key=lambda q: q["number"])
    merged = sorted(t for t in (parse_ts(s) for s in data.get("merged") or []) if t and t >= start)
    return {"start": start, "now": now, "days": days, "questions": qs, "merged": merged,
            "records": [d for d in data.get("records") or [] if start.date() <= d <= now.date()],
            "last_record": max(data.get("records") or [], default=None)}


# ---------------------------------------------------------------- how the questions went (#407)
#
# Three breakdowns of the window's questions, each a templated sentence and a bar of counts.
# Reads build()'s history, the decision records (committees.records()) and which questions a
# committee Discussion serves; no API calls of its own.

AGENT_RE = re.compile(r"^productswarm-[a-z0-9-]+\[bot\]$")
ASKED = (("agents", "agents"), ("owner", "the owner"), ("other", "someone else"))
DECIDED = (("owner", "the owner"), ("committee", "a committee"), ("lapsed", "lapsed"),
           ("open", "still open"))
BECAME = (("record", "a record"), ("direction", "direction only"), ("nothing", "nothing yet"))


def asked_by(q: dict, owner: str | None) -> str:
    """"owner" if the owner opened it or its `### Raised by` starts with "owner" (or the
    owner's login), e.g. #396's "owner (drafted by the coordinator)"; else "agents" for a
    `productswarm-*[bot]` author; else "other"."""
    first = re.match(r"\W*@?([\w-]+)", q.get("raised_by") or "")
    named = first.group(1).lower() if first else ""
    if (owner and q.get("author") == owner) or named == "owner" or (owner and named == owner.lower()):
        return "owner"
    return "agents" if AGENT_RE.match(q.get("author") or "") else "other"


def decided_how(q: dict, record: dict | None, committee_qs: set[int]) -> str:
    """"committee" if a committee Discussion serves it or its record's shape is committee;
    else "owner" if the owner labelled it gov:ruled or ready, or it has a record; else
    "lapsed" for gov:lapsed; else "owner" if it was closed; else "open"."""
    if q["number"] in committee_qs or (record or {}).get("shape") == "committee":
        return "committee"
    if q["decided_by"] == "label" or record:
        return "owner"
    if "gov:lapsed" in (q.get("labels") or []):
        return "lapsed"
    return "owner" if q["decided_by"] == "closed" else "open"


def became(q: dict, record: dict | None) -> str:
    """"record" if a file in governance/decisions/ answers it; else "direction" if the owner
    labelled it gov:ruled or ready (direction for that question only, GOV-0006); else
    "nothing"."""
    if record:
        return "record"
    return "direction" if q["decided_by"] == "label" else "nothing"


def went(h: dict | None, records: dict[int, dict], committee_qs: set[int],
         owner: str | None) -> dict | None:
    """Counts for the three breakdowns, and each question's category for state.json."""
    if h is None:
        return None
    rows = []
    for q in h["questions"]:
        rec = records.get(q["number"])
        rows.append({"number": q["number"], "asked_by": asked_by(q, owner),
                     "decided_by": decided_how(q, rec, committee_qs), "became": became(q, rec)})

    def count(key, cats):
        return {k: sum(r[key] == k for r in rows) for k, _ in cats}

    return {"days": h["days"], "first_day": h["start"].date(), "total": len(rows),
            "asked_by": count("asked_by", ASKED), "decided_by": count("decided_by", DECIDED),
            "became": count("became", BECAME), "questions": rows}


def sentence(head: str, counts: dict[str, int], cats: tuple) -> str:
    parts = [f"{words} {counts[k]}" for k, words in cats if counts[k] or k != "other"]
    return f"{head}: {', '.join(parts)}."


def bar(counts: dict[str, int], cats: tuple, total: int) -> str:
    """A stacked bar, one segment per non-empty category, sized by its share. It repeats the
    sentence beside it, so screen readers skip it."""
    segs = "".join(f'<span class="{k}" style="flex:{counts[k]}"></span>'
                   for k, _ in cats if counts[k])
    return f'<span class="went-bar" aria-hidden="true">{segs if total else ""}</span>'


def render_went(w: dict | None) -> str:
    if w is None:
        return ""
    n = w["total"]
    rows = (("asked", "Asked by", w["asked_by"], ASKED),
            ("decided", "Decided by", w["decided_by"], DECIDED),
            ("became", "Became", w["became"], BECAME))
    items = "".join(f'<li class="{cls}">{bar(c, cats, n)}<span>{html.escape(sentence(head, c, cats))}'
                    f'</span></li>' for cls, head, c, cats in rows)
    intro = (f'{n} question{"s" if n != 1 else ""} asked in the last {w["days"]} days '
             f'(from {w["first_day"].day} {w["first_day"]:%b}).')
    note = ('Asked by the owner: the owner opened it, or its "Raised by" starts with "owner". '
            'Decided by a committee: a committee Discussion serves it or its record\'s shape is '
            'committee; by the owner: the owner added gov:ruled or ready, it has a record, or it '
            'was closed without gov:lapsed. Became a record: a file in governance/decisions/ '
            'answers it; direction only: ruled or ready with no record, which is not precedent '
            '(GOV-0006).')
    return (f'<h2>How the questions went</h2><p>{html.escape(intro)}</p>'
            f'<ul class="went">{items}</ul><p class="muted method">{html.escape(note)}</p>')
