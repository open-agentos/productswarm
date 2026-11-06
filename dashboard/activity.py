"""The repo's public events, and when the owner last acted (#402, part 3 of #397).

`fetch()` reads `repos/{repo}/events`, 100 a page, newest first, up to the 3 pages (300
events) the API keeps. It stops at the first page with an event by the owner, unless given
`since`: then it also reads on until a page ends before `since`. The wire (#405) passes UTC
midnight, so it gets all of today's events (within those 300) from the same read. `owner_last_acted()` picks the
owner's newest event from them; `header()` draws it for the masthead on every page.

What the events API does here (checked 2026-11-05 against this repo):
  - a new event shows up about 30 seconds after it happens;
  - the list is in event-id order, not quite time order: a few events arrive late with their
    original time (pushes and branch creations from two days earlier, among today's events).
    So the owner's newest event is the latest `created_at` on the page, not the first listed;
  - labels show up as `IssuesEvent` `labeled` with the label's name; `unlabeled` carries no
    label (`label` is null);
  - merges show up as `PullRequestEvent` with action `merged` (not `closed` + `merged`), and
    their actor is the PR's author, not who merged it. So the owner merging an agent's PR is
    not an owner event; the `IssuesEvent` `closed` by the owner that `Closes #N` makes right
    after it is.

Stdlib only.
"""
from __future__ import annotations

import datetime as dt
import subprocess

from layout import esc

PER_PAGE = 100
MAX_PAGES = 3          # the events API keeps 300 events
UNREADABLE = "can't read the repo's events"
# The [watch] issue's marker (launcher/watch.py's WATCH_MARKER, #458). swarm watch edits that
# issue's body as the owner's own `gh` login, so those edits are the watcher's, not the owner's.
WATCH_MARKER = "<!-- productswarm-watch -->"

# IssuesEvent actions, as the header says them.
VERBS = {"labeled": "labelled", "unlabeled": "unlabelled", "opened": "opened", "closed": "closed",
         "reopened": "reopened", "assigned": "assigned", "unassigned": "unassigned"}


def fetch(repo: str, gh_json, owner: str | None, since: dt.datetime | None = None) -> dict:
    """{"events": [...], "pages": n} newest first, or {"events": None, "error": ...} if they
    can't be read. Never raises for an API failure: the page builds without them."""
    found = False
    events: list[dict] = []
    pages = 0
    try:
        for page in range(1, MAX_PAGES + 1):
            got = gh_json("api", f"repos/{repo}/events?per_page={PER_PAGE}&page={page}")
            if not isinstance(got, list):
                raise ValueError("events: not a list")
            pages += 1
            events += [e for e in got if isinstance(e, dict)]
            found = found or any(by(e, owner) and not watcher_edit(e) for e in got)
            # The list is in id order, so its last event says how far back the page reaches.
            last = parse_ts((got[-1] if got and isinstance(got[-1], dict) else {}).get("created_at"))
            reached = since is None or last is None or last < since
            if len(got) < PER_PAGE or (found and reached):
                break
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError, TypeError):
        return {"events": None, "error": UNREADABLE}
    return {"events": events, "pages": pages}


def watcher_edit(e: dict) -> bool:
    """An edit of the [watch] issue (#458): swarm watch publishing its state, not the owner."""
    p = e.get("payload") or {}
    issue = p.get("issue") or {}
    return (e.get("type") == "IssuesEvent" and p.get("action") == "edited"
            and (issue.get("body") or "").lstrip().startswith(WATCH_MARKER))


def by(e: dict, owner: str | None) -> bool:
    login = ((e.get("actor") or {}).get("login") or "")
    return bool(owner) and login.lower() == owner.lower()


def parse_ts(s) -> dt.datetime | None:
    try:
        return dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def describe(e: dict, repo: str) -> dict:
    """An event as {"kind", "text", "ref", "extra", "link"}: what the owner did, in words.
    `text` is the plain sentence (`labelled #397 ready`); `ref` and `extra` let the header
    link the number and set the label in code."""
    t, p = e.get("type") or "", e.get("payload") or {}
    action = p.get("action") or ""
    base = f"https://github.com/{repo}"
    kind, verb, ref, extra, link = action or t, "", "", "", base
    if t == "IssuesEvent":
        n = (p.get("issue") or {}).get("number")
        verb, ref = VERBS.get(action, action), f"#{n}"
        link = (p.get("issue") or {}).get("html_url") or f"{base}/issues/{n}"
        if action == "labeled":
            extra = (p.get("label") or {}).get("name") or ""
    elif t == "IssueCommentEvent":
        n = (p.get("issue") or {}).get("number")
        kind, verb, ref = "commented", "commented on", f"#{n}"
        link = (p.get("comment") or {}).get("html_url") or f"{base}/issues/{n}"
    elif t == "PullRequestEvent":
        n = p.get("number") or (p.get("pull_request") or {}).get("number")
        verb, ref, link = f"{action} PR", f"#{n}", f"{base}/pull/{n}"
    elif t in ("PullRequestReviewEvent", "PullRequestReviewCommentEvent"):
        n = (p.get("pull_request") or {}).get("number")
        kind = "reviewed" if t == "PullRequestReviewEvent" else "review_commented"
        verb = "reviewed PR" if kind == "reviewed" else "commented on PR"
        ref, link = f"#{n}", f"{base}/pull/{n}"
    elif t == "PushEvent":
        branch = (p.get("ref") or "").removeprefix("refs/heads/")
        kind, verb, extra = "pushed", "pushed to", branch
        link = f"{base}/commit/{p['head']}" if p.get("head") else f"{base}/commits/{branch}"
    elif t in ("CreateEvent", "DeleteEvent"):
        kind = "created" if t == "CreateEvent" else "deleted"
        verb, extra = f"{kind} {p.get('ref_type') or ''}".strip(), p.get("ref") or ""
        if t == "CreateEvent" and p.get("ref_type") == "branch" and p.get("ref"):
            link = f"{base}/tree/{p['ref']}"
    else:
        verb = (t.removesuffix("Event") or "acted").lower()
        kind = action or verb
    text = " ".join(x for x in (verb, ref, extra) if x)
    return {"kind": kind, "text": text, "verb": verb, "ref": ref, "extra": extra, "link": link}


def owner_last_acted(activity: dict | None, owner: str | None, repo: str,
                     now: dt.datetime) -> dict:
    """{"status": "acted", "kind", "text", "time", "link"} for the owner's newest event;
    {"status": "none", "days"} when none of the events read is theirs; {"status": "unknown"}
    when the owner or the events can't be read."""
    events = (activity or {}).get("events")
    if not owner or events is None:
        return {"status": "unknown"}
    mine = [(t, e) for e in events
            if by(e, owner) and not watcher_edit(e) and (t := parse_ts(e.get("created_at")))]
    if mine:
        t, e = max(mine, key=lambda x: x[0])
        d = describe(e, repo)
        return {"status": "acted", "kind": d["kind"], "text": d["text"], "time": t,
                "link": d["link"], "verb": d["verb"], "ref": d["ref"], "extra": d["extra"]}
    # How far back the events read reach. Not the oldest time: a few late arrivals carry
    # times days older than the rest, so skip the oldest tenth to stay on the safe side.
    times = sorted(t for e in events if (t := parse_ts(e.get("created_at"))))
    oldest = times[len(times) // 10] if times else now
    return {"status": "none", "days": max(1, -(-int((now - oldest).total_seconds()) // 86400))}


def header(o: dict | None, now: dt.datetime, ago) -> str:
    """The masthead's owner line, as HTML."""
    o = o or {"status": "unknown"}
    if o["status"] == "acted":
        what = esc(o["verb"])
        if o["ref"]:
            what += f' <a href="{esc(o["link"])}">{esc(o["ref"])}</a>'
        if o["extra"]:
            extra = f"<code>{esc(o['extra'])}</code>"
            what += " " + (extra if o["ref"] else f'<a href="{esc(o["link"])}">{extra}</a>')
        elif not o["ref"]:
            what = f'<a href="{esc(o["link"])}">{what}</a>'
        when = o["time"].strftime("%Y-%m-%d %H:%M UTC")
        return (f'<span class="owner">Owner last acted <span title="{esc(when)}">'
                f'{esc(ago(o["time"], now))}</span>: {what}</span>')
    if o["status"] == "none":
        n = o["days"]
        return f'<span class="owner">Owner: no activity in the last {n} day{"s" if n != 1 else ""}</span>'
    return '<span class="owner">Owner: unknown</span>'


def state(o: dict | None) -> dict:
    """state.json's `owner_last_acted`: the status, and kind, text, time and link if acted."""
    o = o or {"status": "unknown"}
    keep = ("status", "kind", "text", "time", "link", "days")
    return {k: o[k] for k in keep if k in o}
