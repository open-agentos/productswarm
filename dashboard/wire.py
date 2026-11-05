"""The wire: today's governance events as one-line news items, newest first (#405, part 6 of #397).

Every item is a template filled from fields (a time, a number, a record ID), never a summary
of anyone's text. "Today" is the UTC day of the build. The kinds, and where each comes from:

  kind       | what                                         | events (activity.py)              | fallback (already fetched)
  -----------|----------------------------------------------|-----------------------------------|---------------------------------
  opened     | a gov:question opened                        | IssuesEvent opened, labelled      | questions.py: created today
             |                                              | gov:question                      |
  ruled      | the owner adds gov:ruled                     | IssuesEvent labeled gov:ruled     | questions.py: LabeledEvent today
  lapsed     | the owner adds gov:lapsed                    | IssuesEvent labeled gov:lapsed    | questions.py: LabeledEvent today
  record     | a PR adding a GOV record merges              | IssuesEvent closed on a question  | questions.py: ClosedEvent today
             |                                              | with a record in the checkout     |
  red        | the reviewer requests changes on a PR        | PullRequestReviewEvent,           | the reviewer's reviews of open PRs
             |                                              | changes_requested                 |
  convened   | the owner's "Convening a committee" comment  | (not used)                        | committees.py, its only source

Record merged: the events API's merge event carries no title or files, so the wire reads the
record's merge from the question closing (the record PR's `Closes #N`), and only counts it
when the checkout has a record whose front matter `question:` is that question. The item
links the record file and the question.

Planted defect caught (#397) is left out: no gate issue posts a fixed result line yet.

Each source is merged and an item is kept once per kind and number, at its earliest time
today. No API calls of its own. Stdlib only.
"""
from __future__ import annotations

import datetime as dt

from layout import esc

REVIEWER = "productswarm-reviewer[bot]"
QUESTION = "gov:question"
KINDS = ("opened", "ruled", "lapsed", "record", "red", "convened")
QUIET = "Quiet so far today."


def midnight(now: dt.datetime) -> dt.datetime:
    d = now.astimezone(dt.timezone.utc).date()
    return dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc)


def parse_ts(s) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat((s or "").replace("Z", "+00:00"))
    except (TypeError, ValueError, AttributeError):
        return None


def login(x) -> str:
    return ((x or {}).get("login") or "").lower()


def item(kind: str, t: dt.datetime, n: int, base: str, record: dict | None = None,
         link: str | None = None) -> dict:
    """One item: its kind, time, number, sentence and link. `text` is the plain sentence."""
    issue = f"{base}/issues/{n}"
    if kind == "opened":
        text, link = f"Question #{n} opened", link or issue
    elif kind == "ruled":
        text, link = f"Owner ruled on #{n}", link or issue
    elif kind == "lapsed":
        text, link = f"Question #{n} lapsed", link or issue
    elif kind == "record":
        text = f"{record['id']} merged, answering #{n}"
        link = f"{base}/blob/main/governance/decisions/{record['file']}"
    elif kind == "red":
        text, link = f"Reviewer requested changes on PR #{n}", link or f"{base}/pull/{n}"
    else:   # convened
        text, link = f"Committee convened on #{n}", link or issue
    out = {"kind": kind, "time": t, "number": n, "text": text, "link": link}
    if kind == "record":
        out["record"] = record["id"]
    return out


def from_events(events, owner, records, base, since) -> list[dict]:
    """Items from the repo's events (activity.fetch)."""
    out = []
    for e in events or []:
        t = parse_ts(e.get("created_at"))
        if t is None or t < since:
            continue
        typ, p = e.get("type"), e.get("payload") or {}
        action, owner_did = p.get("action"), bool(owner) and login(e.get("actor")) == owner.lower()
        if typ == "IssuesEvent":
            issue = p.get("issue") or {}
            n = issue.get("number")
            labels = {lb.get("name") for lb in issue.get("labels") or [] if isinstance(lb, dict)}
            if not isinstance(n, int) or "pull_request" in issue:
                continue
            added = (p.get("label") or {}).get("name")
            if action == "opened" and QUESTION in labels:
                out.append(item("opened", t, n, base, link=issue.get("html_url")))
            elif action == "labeled" and owner_did and added == "gov:ruled":
                out.append(item("ruled", t, n, base, link=issue.get("html_url")))
            elif action == "labeled" and owner_did and added == "gov:lapsed":
                out.append(item("lapsed", t, n, base, link=issue.get("html_url")))
            elif action == "closed" and QUESTION in labels and n in records:
                out.append(item("record", t, n, base, records[n]))
        elif typ == "PullRequestReviewEvent":
            r = p.get("review") or {}
            n = (p.get("pull_request") or {}).get("number")
            if (r.get("state") or "").lower() == "changes_requested" and login(r.get("user")) == REVIEWER.lower() \
                    and isinstance(n, int):
                out.append(item("red", parse_ts(r.get("submitted_at")) or t, n, base, link=r.get("html_url")))
    return out


def from_questions(raw, owner, records, base, since) -> list[dict]:
    """Items from questions.py's raw history: questions created in the window, and their
    label and close events."""
    out = []
    raw = raw or {}
    for it in raw.get("issues") or []:
        n = it.get("number")
        t = parse_ts(it.get("created_at"))
        if isinstance(n, int) and t and t >= since:
            out.append(item("opened", t, n, base, link=it.get("html_url")))
    for n, nodes in (raw.get("timelines") or {}).items():
        try:
            n = int(n)
        except (TypeError, ValueError):
            continue
        for node in nodes or []:
            t = parse_ts(node.get("createdAt"))
            if t is None or t < since:
                continue
            name = (node.get("label") or {}).get("name")
            if node.get("__typename") == "LabeledEvent" and owner and login(node.get("actor")) == owner.lower() \
                    and name in ("gov:ruled", "gov:lapsed"):
                out.append(item("ruled" if name == "gov:ruled" else "lapsed", t, n, base))
            elif node.get("__typename") == "ClosedEvent" and n in records:
                out.append(item("record", t, n, base, records[n]))
    return out


def from_reviews(reviews, base, since) -> list[dict]:
    """Red items from the reviewer's reviews of open PRs, which generate.fetch reads anyway."""
    out = []
    for n, rs in (reviews or {}).items():
        for r in rs or []:
            t = parse_ts(r.get("submitted_at"))
            if t and t >= since and r.get("state") == "CHANGES_REQUESTED" and login(r.get("user")) == REVIEWER.lower():
                out.append(item("red", t, int(n), base, link=r.get("html_url")))
    return out


def from_committees(comms, base, since) -> list[dict]:
    """Convened items: the owner's convening comment on each committee's question."""
    out = []
    for c in (comms or {}).get("committees") or []:
        conv = (c.get("owner_comments") or {}).get("convening")
        t = (conv or {}).get("ts")
        if isinstance(c.get("question"), int) and t and t >= since:
            out.append(item("convened", t, c["question"], base, link=conv.get("url")))
    return out


def build(activity: dict | None, questions_raw: dict | None, reviews: dict | None,
          comms: dict | None, records: dict[int, dict], owner: str | None, repo: str,
          now: dt.datetime) -> dict:
    """{"day", "items": [...] newest first, "events": bool}. `events` says whether the repo's
    events could be read; the fallbacks fill in either way."""
    base, since = f"https://github.com/{repo}", midnight(now)
    events = (activity or {}).get("events")
    found = (from_events(events, owner, records, base, since)
             + from_questions(questions_raw, owner, records, base, since)
             + from_reviews(reviews, base, since)
             + from_committees(comms, base, since))
    first: dict[tuple[str, int], dict] = {}
    for i in found:
        if i["time"] > now:
            continue
        k = (i["kind"], i["number"])
        if k not in first or i["time"] < first[k]["time"]:
            first[k] = i
    items = sorted(first.values(), key=lambda i: (i["time"], KINDS.index(i["kind"]), i["number"]),
                   reverse=True)
    return {"day": since.date(), "items": items, "events": events is not None}


def render(w: dict | None) -> str:
    """The desk's wire panel."""
    if w is None:
        return ""
    if w["items"]:
        rows = "".join(
            f'<li class="{esc(i["kind"])}"><time datetime="{i["time"].strftime("%Y-%m-%dT%H:%M:%SZ")}">'
            f'{i["time"].strftime("%H:%M")}</time> <a href="{esc(i["link"])}">{esc(i["text"])}</a></li>'
            for i in w["items"])
        body = f'<ol class="wire">{rows}</ol>'
    else:
        body = f'<p class="muted">{QUIET}</p>'
    note = ("Today in UTC, newest first: questions opened, the owner's rulings and lapses, records "
            "merged, the reviewer's requested changes and committees convened.")
    if not w["events"]:
        note += " The repo's events couldn't be read, so this is from the other data the page reads."
    return f'<h2>The wire</h2>{body}<p class="muted method">{esc(note)}</p>'


def state(w: dict | None) -> dict | None:
    """state.json's `wire`."""
    if w is None:
        return None
    return {"day": w["day"], "events": w["events"], "items": w["items"]}
