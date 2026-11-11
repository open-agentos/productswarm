"""The owner's acts per working day (#771): readiness checks 1 and 2 (M4, #686).

Check 1 is under 5 owner acts on each of 10 working days in a row; check 2 is that every one
of them is C-team work. GitHub's events API keeps 300 events, so one busy day pushes earlier
ones out (dashboard/activity.py). This keeps its own record in swarm.db instead, in two steps:

1. **Leads, from webhooks.** For each delivery that could be an owner act, the receiver
   (webhooks.py) stores a pointer in `act_leads`: delivery id, event, action, repo, number,
   the object to read back (a comment or review id, or a label's name) and the sender's login.
   Nothing else from the payload, and no comment or issue body (GOV-0002, GOV-0004).
2. **Acts, read back from GitHub.** `sync()` reads each unread lead whose sender is the owner
   back from GitHub, the way the watcher reads everything else (a payload is never trusted
   for who did what), and stores the act in `acts`: when, act, kind, a short label, repo,
   number and a link. A body read to classify an act is never stored. The receiver holds only
   WEBHOOK_SECRET, so it can't read GitHub itself: `swarm acts` runs sync() before it prints.

Each role App delivers the same event, so one act has several leads; an act's key is its
GitHub object (a comment id, review id, issue event id, or a merge or open of repo#n), so it
is stored once.

What counts (check 1):
    label    the owner added or removed a label on an issue or PR (issue events, by id)
    comment  an issue or PR conversation comment
    review   a PR review, including an approval that is an approved ask (GOV-0027); an
             inline comment or reply makes a review too, so they aren't counted again
    merge    the owner merged a PR, including a protected-path merge
    open     the owner opened an issue other than a Goal or Area
What doesn't: opening or editing a Goal or Area (labels on one are edits to it), closing an
issue (a merge closes its issue as the owner), reading the report or the Desk.

Kind (check 2): `plan` (on a Mission, Goal or Area, or a `hold` veto, GOV-0031), `report`
(on the report issue: replies, asks and `Ask:` one-on-ones), `ask` (on a `gov:question`, or
approving a protected-path PR at head, GOV-0027), `protected-merge` (merging a PR that touches
a protected path) and `other`, which fails check 2: a `ready` on a Task, a dispatching
comment, a merge of an ordinary PR.

Limits: an act the receiver missed (it was down, or the App isn't subscribed to the event)
has no lead; an object deleted before sync() reads it is lost; Discussion comments aren't
read. Back-room repairs leave no record at all (the checklist has the owner self-report them).
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path
from typing import Callable

import statedb

LIMIT = 5                       # check 1: under 5 acts a day
SCOPE_TYPES = ("Mission", "Goal", "Area")
EXEMPT_TYPES = ("Goal", "Area")  # opening or editing one is plan approval, not an act
KINDS = ("plan", "report", "ask", "protected-merge", "other")
HOLD = "hold"                   # the owner's veto (GOV-0031)
GOV_QUESTION = "gov:question"

SCHEMA = """
CREATE TABLE IF NOT EXISTS act_leads (
    delivery TEXT PRIMARY KEY, event TEXT NOT NULL, action TEXT, repo TEXT NOT NULL,
    number INTEGER NOT NULL, ref TEXT, sender TEXT, received_at TEXT NOT NULL, read_at TEXT
);
CREATE TABLE IF NOT EXISTS acts (
    key TEXT PRIMARY KEY, at TEXT NOT NULL, act TEXT NOT NULL, kind TEXT NOT NULL,
    what TEXT, repo TEXT NOT NULL, number INTEGER NOT NULL, url TEXT
);
CREATE INDEX IF NOT EXISTS acts_at ON acts (at);
"""


# ---------------------------------------------------------------- leads (from the receiver)

def lead(event: str, payload: object) -> tuple[str, str, int, str | None, str | None] | None:
    """(action, repo, number, ref, sender) for a delivery that could be an owner act, else None.
    Read from the payload only to know what to read back; never acted on."""
    if not isinstance(payload, dict):
        return None
    action = payload.get("action")
    repo = (payload.get("repository") or {}).get("full_name") if isinstance(
        payload.get("repository"), dict) else None
    sender = (payload.get("sender") or {}).get("login") if isinstance(payload.get("sender"), dict) else None
    if not isinstance(action, str) or not isinstance(repo, str):
        return None
    obj = payload.get("pull_request" if event in ("pull_request", "pull_request_review") else "issue")
    number = obj.get("number") if isinstance(obj, dict) else None
    if not isinstance(number, int):
        return None

    def field(key: str, name: str) -> str | None:
        v = payload.get(key)
        v = v.get(name) if isinstance(v, dict) else None
        return str(v)[:100] if isinstance(v, (str, int)) and not isinstance(v, bool) else None

    ref: str | None = None
    if event in ("issues", "pull_request") and action in ("labeled", "unlabeled"):
        ref = field("label", "name")
        if ref is None:
            return None
    elif event == "issues" and action == "opened":
        pass
    elif event == "pull_request" and action == "closed" and obj.get("merged") is True:
        action = "merged"
    elif event == "issue_comment" and action == "created":
        ref = field("comment", "id")
    elif event == "pull_request_review" and action == "submitted":
        ref = field("review", "id")
    else:
        return None
    if event in ("issue_comment", "pull_request_review") and ref is None:
        return None
    return action, repo[:140], number, ref, sender[:64] if isinstance(sender, str) else None


def record_lead(db: sqlite3.Connection, delivery: str, event: str, found: tuple,
                now: dt.datetime) -> None:
    """Store one lead; the caller holds the transaction (the receiver's delivery insert)."""
    db.execute("INSERT OR IGNORE INTO act_leads (delivery, event, action, repo, number, ref, sender, "
               "received_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
               (delivery, event, *found, now.isoformat(timespec="seconds")))


# ---------------------------------------------------------------- reading back

def connect(state_dir: Path) -> sqlite3.Connection:
    db = statedb.connect(state_dir / statedb.DB_FILE)
    db.executescript(SCHEMA)
    return db


def not_found(e: Exception) -> bool:
    return "Not Found" in str(e) or "404" in str(e)


def login(o: object) -> str | None:
    return (o or {}).get("login") if isinstance(o, dict) else None


class Reader:
    """Reads acts back from GitHub, caching each issue and PR's files for one sync."""

    def __init__(self, owner: str, report: tuple[str, int] | None, gh_json: Callable,
                 gh_items: Callable, protected: Callable[[str], bool]):
        self.owner, self.report = owner, report
        self.gh_json, self.gh_items, self.protected = gh_json, gh_items, protected
        self._issues: dict[tuple[str, int], dict] = {}
        self._files: dict[tuple[str, int], bool] = {}

    def issue(self, repo: str, n: int) -> dict:
        if (repo, n) not in self._issues:
            self._issues[(repo, n)] = self.gh_json("api", f"repos/{repo}/issues/{n}") or {}
        return self._issues[(repo, n)]

    def touches_protected(self, repo: str, n: int) -> bool:
        if (repo, n) not in self._files:
            files = self.gh_items(f"repos/{repo}/pulls/{n}/files?per_page=100")
            self._files[(repo, n)] = any(self.protected(f.get("filename") or "") for f in files)
        return self._files[(repo, n)]

    def where(self, repo: str, n: int) -> str | None:
        """The kind any act on this issue has: plan, report or ask; None if it depends on the act."""
        if self.report == (repo, n):
            return "report"
        it = self.issue(repo, n)
        if ((it.get("type") or {}).get("name")) in SCOPE_TYPES:
            return "plan"
        if GOV_QUESTION in {(l or {}).get("name") for l in it.get("labels") or []}:
            return "ask"
        return None

    def exempt(self, repo: str, n: int) -> bool:
        return ((self.issue(repo, n).get("type") or {}).get("name")) in EXEMPT_TYPES

    def read(self, event: str, action: str, repo: str, n: int, ref: str | None) -> list[dict]:
        """The owner's acts this lead points at, read from GitHub ([] if none)."""
        page = f"https://github.com/{repo}/issues/{n}"
        act = {"repo": repo, "number": n}
        if action in ("labeled", "unlabeled"):
            if self.exempt(repo, n):
                return []
            out = []
            for e in self.gh_items(f"repos/{repo}/issues/{n}/events?per_page=100"):
                name = (e.get("label") or {}).get("name")
                if (e.get("event") in ("labeled", "unlabeled") and login(e.get("actor")) == self.owner
                        and e.get("id") is not None and e.get("created_at") and name):
                    verb = "labelled" if e["event"] == "labeled" else "unlabelled"
                    kind = self.where(repo, n) or ("plan" if name == HOLD else "other")
                    out.append({**act, "key": f"{repo}:event:{e['id']}", "at": e["created_at"],
                                "act": "label", "kind": kind, "what": f"{verb} {name}", "url": page})
            return out
        if action == "opened":
            it = self.issue(repo, n)
            if login(it.get("user")) != self.owner or self.exempt(repo, n) or not it.get("created_at"):
                return []
            kind = self.where(repo, n) or "other"
            what = f"opened {(it.get('type') or {}).get('name') or 'issue'}"
            return [{**act, "key": f"{repo}#{n}:open", "at": it["created_at"], "act": "open",
                     "kind": kind, "what": what, "url": it.get("html_url") or page}]
        if action == "merged":
            pr = self.gh_json("api", f"repos/{repo}/pulls/{n}") or {}
            if login(pr.get("merged_by")) != self.owner or not pr.get("merged_at"):
                return []
            kind = "protected-merge" if self.touches_protected(repo, n) else "other"
            return [{**act, "key": f"{repo}#{n}:merge", "at": pr["merged_at"], "act": "merge",
                     "kind": kind, "what": "merged", "url": pr.get("html_url") or page}]
        if event == "issue_comment":
            c = self.gh_json("api", f"repos/{repo}/issues/comments/{ref}") or {}
            if login(c.get("user")) != self.owner or not c.get("created_at"):
                return []
            return [{**act, "key": f"{repo}:comment:{ref}", "at": c["created_at"], "act": "comment",
                     "kind": self.where(repo, n) or "other", "what": "commented",
                     "url": c.get("html_url") or page}]
        if event == "pull_request_review":
            r = self.gh_json("api", f"repos/{repo}/pulls/{n}/reviews/{ref}") or {}
            state = r.get("state") or ""
            if login(r.get("user")) != self.owner or not r.get("submitted_at") or state == "PENDING":
                return []
            kind = ("ask" if state == "APPROVED" and self.touches_protected(repo, n)
                    else self.where(repo, n) or "other")
            return [{**act, "key": f"{repo}:review:{ref}", "at": r["submitted_at"], "act": "review",
                     "kind": kind, "what": f"reviewed: {state.lower().replace('_', ' ')}",
                     "url": r.get("html_url") or page}]
        return []


def sync(state_dir: Path, owner: str, report: tuple[str, int] | None, gh_json: Callable,
         gh_items: Callable, protected: Callable[[str], bool],
         now: dt.datetime | None = None) -> list[str]:
    """Read every unread lead the owner sent back from GitHub and store its acts. Leads from
    anyone else are marked read without a call. Returns the errors; a lead that failed stays unread
    for the next sync, and one whose object is gone (404) is marked read."""
    now = now or dt.datetime.now(dt.timezone.utc)
    stamp = now.isoformat(timespec="seconds")
    reader = Reader(owner, report, gh_json, gh_items, protected)
    errors: list[str] = []
    db = connect(state_dir)
    try:
        db.execute("UPDATE act_leads SET read_at = ? WHERE read_at IS NULL "
                   "AND (sender IS NULL OR sender != ?)", (stamp, owner))
        groups = db.execute(
            "SELECT event, action, repo, number, ref FROM act_leads WHERE read_at IS NULL "
            "GROUP BY event, action, repo, number, ref ORDER BY MIN(received_at)").fetchall()
        for event, action, repo, n, ref in groups:
            try:
                found = reader.read(event, action, repo, n, ref)
            except RuntimeError as e:
                if not not_found(e):
                    errors.append(f"{event} {action} {repo}#{n}: {e}")
                    continue
                found = []
            db.execute("BEGIN IMMEDIATE")
            db.executemany("INSERT OR IGNORE INTO acts (key, at, act, kind, what, repo, number, url) "
                           "VALUES (:key, :at, :act, :kind, :what, :repo, :number, :url)", found)
            db.execute("UPDATE act_leads SET read_at = ? WHERE read_at IS NULL AND event = ? AND "
                       "action IS ? AND repo = ? AND number = ? AND ref IS ?",
                       (stamp, event, action, repo, n, ref))
            db.execute("COMMIT")
    finally:
        db.close()
    return errors


# ---------------------------------------------------------------- per day

def stored(state_dir: Path) -> list[dict]:
    """Every act in swarm.db, oldest first."""
    if not (state_dir / statedb.DB_FILE).exists():
        return []
    db = connect(state_dir)
    try:
        db.row_factory = sqlite3.Row
        return [dict(r) for r in db.execute("SELECT * FROM acts ORDER BY at, key")]
    finally:
        db.close()


def per_day(acts: list[dict], days: list[dt.date], tz: dt.tzinfo | None = None) -> list[dict]:
    """One entry per day, in the order given: {day, count, other, under_limit, c_team, acts},
    each act with its local time. Days are local (tz, or this machine's)."""
    by: dict[dt.date, list[dict]] = {d: [] for d in days}
    for a in acts:
        at = dt.datetime.fromisoformat(a["at"].replace("Z", "+00:00"))
        at = at.astimezone(tz) if tz else at.astimezone()
        if at.date() in by:
            by[at.date()].append({"at": at.isoformat(timespec="seconds"), "act": a["act"],
                                  "kind": a["kind"], "what": a["what"], "repo": a["repo"],
                                  "number": a["number"], "url": a["url"]})
    out = []
    for d in days:
        items = sorted(by[d], key=lambda a: a["at"])
        other = sum(a["kind"] == "other" for a in items)
        out.append({"day": d.isoformat(), "count": len(items), "other": other,
                    "under_limit": len(items) < LIMIT, "c_team": other == 0, "acts": items})
    return out


def text(rows: list[dict], owner: str, repo: str | None = None) -> str:
    """`swarm acts`'s output: each day newest first, its count and each act."""
    out = [f"Owner acts by @{owner} (local time; check 1: under {LIMIT} a day, check 2: none 'other'):"]
    for r in rows:
        d = dt.date.fromisoformat(r["day"])
        verdict = []
        if not r["under_limit"]:
            verdict.append(f"{LIMIT} or more")
        if not r["c_team"]:
            verdict.append(f"{r['other']} not C-team")
        out.append(f"  {d:%a %Y-%m-%d}  {r['count']} act{'' if r['count'] == 1 else 's'}"
                   + (f"  ({', '.join(verdict)})" if verdict else ""))
        for a in r["acts"]:
            ref = f"#{a['number']}" if a["repo"] == repo else f"{a['repo']}#{a['number']}"
            out.append(f"    {a['at'][11:16]}  {a['kind']:<15}  {a['what']} on {ref}  {a['url']}")
    return "\n".join(out)
