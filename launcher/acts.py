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

**A day is counted only once it is backfilled (#844).** Leads only exist where the receiver
runs (the engine host), and a receiver that was down leaves none, so a day with no stored acts
may simply have no data. `backfill()` reads each finished day's acts from GitHub instead, as
leads with the same keys, so an act seen both ways is stored once: the owner's label and merge
events from each org repo's issue events, their comments from each repo's comment list, and
their reviews and opened issues from search. Once every one of them is read back, the day's
window goes in `act_backfills`, and only then does the day count, even at 0 acts. Any other
day is `not counted` (never 0), and today is `in progress` until it ends. A day is backfilled
SETTLE after it ends (search lags), and only within BACKFILL_DAYS (its comment list is long).

Limits: an object deleted before it is read back is lost; Discussion comments aren't read; an
org repo the owner's token can't list isn't searched. Back-room repairs leave no record at all
(the checklist has the owner self-report them).
"""
from __future__ import annotations

import datetime as dt
import sqlite3
import urllib.parse
from pathlib import Path
from typing import Callable

import statedb

LIMIT = 5                       # check 1: under 5 acts a day
SCOPE_TYPES = ("Mission", "Goal", "Area")
EXEMPT_TYPES = ("Goal", "Area")  # opening or editing one is plan approval, not an act
KINDS = ("plan", "report", "ask", "protected-merge", "other")
HOLD = "hold"                   # the owner's veto (GOV-0031)
GOV_QUESTION = "gov:question"
SETTLE = dt.timedelta(hours=1)  # a day is backfilled this long after it ends (search lags)
BACKFILL_DAYS = 31              # older days aren't backfilled: not counted
COUNTED, NOT_COUNTED, IN_PROGRESS = "counted", "not counted", "in progress"

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
CREATE TABLE IF NOT EXISTS act_backfills (start TEXT NOT NULL, end TEXT NOT NULL, at TEXT NOT NULL);
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


# ---------------------------------------------------------------- backfill (#844)

def utc(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def bounds(d: dt.date, tz: dt.tzinfo | None = None) -> tuple[dt.datetime, dt.datetime]:
    """A local day's start and end (tz, or this machine's)."""
    def at(x: dt.date) -> dt.datetime:
        t = dt.datetime.combine(x, dt.time())
        return t.replace(tzinfo=tz) if tz else t.astimezone()
    return at(d), at(d + dt.timedelta(days=1))


def windows(db: sqlite3.Connection) -> list[tuple[dt.datetime, dt.datetime]]:
    """Every backfilled window, as (start, end)."""
    return [(dt.datetime.fromisoformat(a.replace("Z", "+00:00")),
             dt.datetime.fromisoformat(b.replace("Z", "+00:00")))
            for a, b in db.execute("SELECT start, end FROM act_backfills")]


def day_state(d: dt.date, now: dt.datetime, backfills: list, tz: dt.tzinfo | None = None
              ) -> tuple[str, str | None, bool]:
    """(status, why it isn't counted, whether to backfill it now) for one day."""
    start, end = bounds(d, tz)
    if now < start:
        return NOT_COUNTED, "the day hasn't started", False
    if now < end:
        return IN_PROGRESS, "the day isn't over", False
    if any(a <= start and b >= end for a, b in backfills):
        return COUNTED, None, False
    if now < end + SETTLE:
        return NOT_COUNTED, f"read back from GitHub {SETTLE.seconds // 3600}h after the day ends", False
    if now - end > dt.timedelta(days=BACKFILL_DAYS):
        return NOT_COUNTED, f"older than {BACKFILL_DAYS} days, never read back from GitHub", False
    return NOT_COUNTED, "not read back from GitHub yet", True


def scope_repos(repo: str, gh_items: Callable) -> tuple[str, list[str]]:
    """(search qualifier, repos) for repo's org, or for repo alone if its owner isn't an org."""
    org = repo.split("/")[0]
    try:
        names = {r.get("full_name") for r in gh_items(f"orgs/{org}/repos?per_page=100")}
    except RuntimeError as e:
        if not not_found(e):
            raise
        return f"repo:{repo}", [repo]
    return f"org:{org}", sorted({n for n in names if isinstance(n, str)} | {repo})


def recent_events(repo: str, since: str, gh_json: Callable) -> list[dict]:
    """repo's issue events created at or after `since`, a page at a time from the newest, so a
    busy repo's whole history isn't read. Raises RuntimeError if they aren't newest first."""
    out, page = [], 1
    while True:
        batch = gh_json("api", f"repos/{repo}/issues/events?per_page=100&page={page}") or []
        times = [e.get("created_at") or "" for e in batch]
        if times != sorted(times, reverse=True):
            raise RuntimeError(f"{repo}'s issue events aren't newest first")
        out += [e for e in batch if (e.get("created_at") or "") >= since]
        if len(batch) < 100 or times[-1] < since:
            return out
        page += 1


def discover(owner: str, repo: str, since: str, gh_json: Callable, gh_items: Callable) -> list[tuple]:
    """(key, event, action, repo, number, ref) per lead for the owner's possible acts since
    `since` in repo's org, found on GitHub rather than from webhooks. Raises RuntimeError."""
    def search(q: str) -> list[tuple[str, int]]:
        items = gh_items(f"search/issues?q={urllib.parse.quote(q)}&per_page=100", ".items[]")
        return [(it["repository_url"].split("/repos/", 1)[1], it["number"]) for it in items
                if isinstance(it.get("number"), int) and "/repos/" in (it.get("repository_url") or "")]

    qual, repos = scope_repos(repo, gh_items)
    found: list[tuple] = []
    for r in repos:
        for e in recent_events(r, since, gh_json):
            n = (e.get("issue") or {}).get("number")
            if login(e.get("actor")) != owner or not isinstance(n, int) or e.get("id") is None:
                continue
            if e.get("event") in ("labeled", "unlabeled"):     # one read finds every label act
                found.append((f"backfill:{r}:event:{e['id']}", "issues", "labeled", r, n, None))
            elif e.get("event") == "merged":
                found.append((f"backfill:{r}#{n}:merge", "pull_request", "merged", r, n, None))
        for c in gh_items(f"repos/{r}/issues/comments?since={since}&per_page=100"):
            num = (c.get("issue_url") or "").rsplit("/", 1)[-1]
            if (login(c.get("user")) == owner and (c.get("created_at") or "") >= since
                    and c.get("id") is not None and num.isdigit()):
                found.append((f"backfill:{r}:comment:{c['id']}", "issue_comment", "created", r,
                              int(num), str(c["id"])))
    for r, n in search(f"{qual} is:issue author:{owner} created:>={since}"):
        found.append((f"backfill:{r}#{n}:open", "issues", "opened", r, n, None))
    for r, n in search(f"{qual} is:pr reviewed-by:{owner} updated:>={since}"):
        for rv in gh_items(f"repos/{r}/pulls/{n}/reviews?per_page=100"):
            if (login(rv.get("user")) == owner and (rv.get("submitted_at") or "") >= since
                    and rv.get("id") is not None):
                found.append((f"backfill:{r}:review:{rv['id']}", "pull_request_review", "submitted",
                              r, n, str(rv["id"])))
    return found


def backfill(state_dir: Path, owner: str, report: tuple[str, int] | None, repo: str,
             gh_json: Callable, gh_items: Callable, protected: Callable[[str], bool],
             days: list[dt.date], now: dt.datetime | None = None,
             tz: dt.tzinfo | None = None) -> list[str]:
    """Read the owner's acts on each of `days` that is due (day_state) back from GitHub as leads,
    then sync() every unread lead. The window counts only once no backfilled lead is left
    unread. Returns the errors, sync()'s included."""
    now = now or dt.datetime.now(dt.timezone.utc)
    db = connect(state_dir)
    try:
        have = windows(db)
        due = [bounds(d, tz) for d in days if day_state(d, now, have, tz)[2]]
        errors: list[str] = []
        if due:
            start, end = min(a for a, _ in due), max(b for _, b in due)
            try:
                found = discover(owner, repo, utc(start), gh_json, gh_items)
            except RuntimeError as e:
                errors.append(f"backfill from {utc(start)}: {e}")
                due = []
            else:
                db.execute("BEGIN IMMEDIATE")
                for key, event, action, r, n, ref in found:
                    record_lead(db, key, event, (action, r, n, ref, owner), now)
                db.execute("COMMIT")
    finally:
        db.close()
    errors += sync(state_dir, owner, report, gh_json, gh_items, protected, now)
    if due:
        db = connect(state_dir)
        try:
            unread = db.execute("SELECT COUNT(*) FROM act_leads WHERE read_at IS NULL "
                                "AND delivery LIKE 'backfill:%'").fetchone()[0]
            if not unread:
                with db:
                    db.execute("INSERT INTO act_backfills VALUES (?, ?, ?)",
                               (utc(start), utc(end), now.isoformat(timespec="seconds")))
        finally:
            db.close()
    return errors


def backfilled(state_dir: Path) -> list[tuple[dt.datetime, dt.datetime]]:
    if not (state_dir / statedb.DB_FILE).exists():
        return []
    db = connect(state_dir)
    try:
        return windows(db)
    finally:
        db.close()


def refresh(state_dir: Path, owner: str, report: tuple[str, int] | None, repo: str,
            gh_json: Callable, gh_items: Callable, protected: Callable[[str], bool],
            days: list[dt.date], now: dt.datetime | None = None,
            tz: dt.tzinfo | None = None) -> tuple[list[dict], list[str]]:
    """backfill(), then per_day() for `days`: what `swarm acts` and `swarm trouble` read."""
    now = now or dt.datetime.now(dt.timezone.utc)
    errors = backfill(state_dir, owner, report, repo, gh_json, gh_items, protected, days, now, tz)
    return per_day(stored(state_dir), days, tz, now, backfilled(state_dir)), errors


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


def per_day(acts: list[dict], days: list[dt.date], tz: dt.tzinfo | None = None,
            now: dt.datetime | None = None, backfills: list | None = None) -> list[dict]:
    """One entry per day, in the order given: {day, status, why, count, other, under_limit,
    c_team, acts}, each act with its local time. Days are local (tz, or this machine's).
    Only a `counted` day (backfilled, day_state) has a count and the two checks; a `not
    counted` one has None for all three, never 0; an `in progress` one counts so far, unchecked."""
    now = now or dt.datetime.now(dt.timezone.utc)
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
        status, why, _ = day_state(d, now, backfills or [], tz)
        other = sum(a["kind"] == "other" for a in items)
        row = {"day": d.isoformat(), "status": status, "why": why, "count": None, "other": None,
               "under_limit": None, "c_team": None, "acts": items}
        if status == COUNTED:
            row.update(count=len(items), other=other, under_limit=len(items) < LIMIT, c_team=other == 0)
        elif status == IN_PROGRESS:
            row.update(count=len(items), other=other)
        out.append(row)
    return out


def text(rows: list[dict], owner: str, repo: str | None = None) -> str:
    """`swarm acts`'s output: each day newest first, its count (or why it isn't counted) and each act."""
    out = [f"Owner acts by @{owner} (local time; check 1: under {LIMIT} a day, check 2: none 'other'):"]
    for r in rows:
        d = dt.date.fromisoformat(r["day"])
        n = r["count"]
        if r["status"] == NOT_COUNTED:
            head = f"not counted ({r['why']})"
        else:
            head = f"{n} act{'' if n == 1 else 's'}"
            if r["status"] == IN_PROGRESS:
                head += " so far (the day isn't over)"
            verdict = []
            if r["under_limit"] is False:
                verdict.append(f"{LIMIT} or more")
            if r["c_team"] is False:
                verdict.append(f"{r['other']} not C-team")
            head += f"  ({', '.join(verdict)})" if verdict else ""
        out.append(f"  {d:%a %Y-%m-%d}  {head}")
        for a in r["acts"]:
            ref = f"#{a['number']}" if a["repo"] == repo else f"{a['repo']}#{a['number']}"
            out.append(f"    {a['at'][11:16]}  {a['kind']:<15}  {a['what']} on {ref}  {a['url']}")
    return "\n".join(out)
