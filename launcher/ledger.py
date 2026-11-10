"""The runs ledger (#662): every run swarm watch started, once it has ended, with its
total_cost_usd and the Mission, Goal and Area issues above it, in swarm.db's `runs` table.

The watch state keeps a run for RUNS_DAYS only (watch.record_ended); the ledger keeps every
one, so totals cover a whole month. One row per session id, written once: recording the same
run again (a tick whose state save failed, then ran again) changes nothing.

    runs  session_id, name, kind, ref, issue, started, ended, ending, cost_usd,
          pr       the PR number for a review or respond run, else NULL
          mission  the nearest Mission above the issue, or NULL
          scopes   JSON list of every Mission, Goal and Area issue above it, nearest first,
                   as "owner/name#n"; NULL while they haven't been read

A run's issue is its trigger's issue, or for a PR the issue the PR closes (the first GitHub
lists, if it closes more than one). The watcher's open-PR model gives that issue when the PR
is still open; otherwise the row keeps its PR number and a later tick reads the issue from
GitHub for the PR in any state (watch.gh_pr_closes), so a PR merged before the run was
recorded still counts toward its Mission. Scopes are read from GitHub's sub-issue links on a
later tick (the watcher's scope query, swarm.gh_scopes), never from a webhook payload, so a
run is recorded even while GitHub can't be read.

Totals are reported only. Per GOV-0033 the engine has no daily, per-mission or monthly
spend total: nothing here holds or stops a run. `swarm spent` prints today's and this
month's totals and the Spent value for each Mission, Goal and Area. Writing that value to
the org Project's Spent field waits on #731 (which identity may write it).
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
from pathlib import Path

import statedb

SCOPE_TYPES = ("Mission", "Goal", "Area")
SCOPES_PER_TICK = 25          # rows whose scopes one tick reads at most (one GraphQL query)

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    session_id TEXT PRIMARY KEY,
    name TEXT, kind TEXT, ref TEXT, issue INTEGER,
    started TEXT, ended TEXT NOT NULL, ending TEXT, cost_usd REAL,
    mission TEXT, scopes TEXT, pr INTEGER
);
CREATE INDEX IF NOT EXISTS runs_ended ON runs (ended);
"""

_REF = re.compile(r"#(\d+)")


def connect(state_dir: Path) -> sqlite3.Connection:
    db = statedb.connect(state_dir / statedb.DB_FILE)
    db.executescript(SCHEMA)
    return db


def pr_of(run: dict) -> int | None:
    """The PR a review or respond run was on ("PR #n"), else None."""
    m = _REF.search(run.get("ref") or "")
    return int(m.group(1)) if m and (run.get("ref") or "").startswith("PR ") else None


def issue_of(run: dict, closes: dict[int, int]) -> int | None:
    """The issue a run served: #n for an issue trigger, or the issue PR #n closes (None if
    closes doesn't say; the PR is resolved on a later tick, see unresolved())."""
    pr = pr_of(run)
    if pr is not None:
        return closes.get(pr)
    m = _REF.search(run.get("ref") or "")
    return int(m.group(1)) if m else None


def record(state_dir: Path, ended: list[dict], closes: dict[int, int]) -> int:
    """Add each ended run (a watch run record with "ended") to the ledger. Returns how many
    rows were new. closes maps a PR number to the issue it closes; a PR it doesn't know
    keeps its number for unresolved()."""
    rows = [(r["session_id"], r.get("name"), r.get("kind"), r.get("ref"), issue_of(r, closes),
             r.get("started"), r["ended"], r.get("ending"), r.get("cost_usd"), pr_of(r))
            for r in ended if r.get("session_id") and r.get("ended")]
    if not rows:
        return 0
    db = connect(state_dir)
    try:
        before = db.total_changes
        db.execute("BEGIN IMMEDIATE")
        db.executemany("INSERT OR IGNORE INTO runs (session_id, name, kind, ref, issue, started, "
                       "ended, ending, cost_usd, pr) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        db.execute("COMMIT")
        return db.total_changes - before
    finally:
        db.close()


def unscoped(state_dir: Path, limit: int = SCOPES_PER_TICK) -> list[int]:
    """Issues of ledger rows whose scopes haven't been read yet, oldest first."""
    if not (state_dir / statedb.DB_FILE).exists():
        return []
    db = connect(state_dir)
    try:
        return [n for (n,) in db.execute(
            "SELECT issue FROM runs WHERE scopes IS NULL AND issue IS NOT NULL "
            "GROUP BY issue ORDER BY MIN(ended) LIMIT ?", (limit,))]
    finally:
        db.close()


def unresolved(state_dir: Path, limit: int = SCOPES_PER_TICK) -> list[int]:
    """PRs of ledger rows whose issue isn't known yet (the PR wasn't in the open-PR model
    when the run was recorded), oldest first."""
    if not (state_dir / statedb.DB_FILE).exists():
        return []
    db = connect(state_dir)
    try:
        return [n for (n,) in db.execute(
            "SELECT pr FROM runs WHERE pr IS NOT NULL AND issue IS NULL AND scopes IS NULL "
            "GROUP BY pr ORDER BY MIN(ended) LIMIT ?", (limit,))]
    finally:
        db.close()


def set_prs(state_dir: Path, closes: dict[int, list[int]]) -> int:
    """Give each unresolved PR's rows the issue it closes, read from GitHub: the first one
    listed. A PR that closes no issue has nothing above it, so its rows get an empty scope
    list. A PR missing from closes stays unresolved for a later tick."""
    db = connect(state_dir)
    try:
        db.execute("BEGIN IMMEDIATE")
        done = 0
        for pr, issues in closes.items():
            if issues:
                done += db.execute("UPDATE runs SET issue = ? WHERE pr = ? AND issue IS NULL AND "
                                   "scopes IS NULL", (issues[0], pr)).rowcount
            else:
                done += db.execute("UPDATE runs SET scopes = '[]' WHERE pr = ? AND issue IS NULL "
                                   "AND scopes IS NULL", (pr,)).rowcount
        db.execute("COMMIT")
        return done
    finally:
        db.close()


def scopes_of(scope: dict, repo: str) -> list[dict]:
    """The Mission, Goal and Area issues in a parse_scope() result, nearest first."""
    return [{"ref": f"{p.get('repo') or repo}#{p['number']}", "type": p["type"]}
            for p in scope.get("parents") or [] if p.get("type") in SCOPE_TYPES]


def set_scopes(state_dir: Path, scopes: dict[int, dict | None], repo: str) -> int:
    """Fill in scopes for rows on each issue whose parse_scope() result was read; an issue
    whose scope couldn't be read (None) stays unscoped for a later tick. A run with no issue
    and no PR (or nothing above its issue) gets an empty list; a PR run whose issue isn't
    known yet waits for set_prs()."""
    db = connect(state_dir)
    try:
        db.execute("BEGIN IMMEDIATE")
        done = 0
        for n, scope in scopes.items():
            if scope is None:
                continue
            found = scopes_of(scope, repo)
            mission = next((x["ref"] for x in found if x["type"] == "Mission"), None)
            done += db.execute("UPDATE runs SET scopes = ?, mission = ? WHERE issue = ? AND "
                               "scopes IS NULL", (json.dumps([x["ref"] for x in found]), mission, n)
                               ).rowcount
        db.execute("UPDATE runs SET scopes = '[]' WHERE scopes IS NULL AND issue IS NULL "
                   "AND pr IS NULL")
        db.execute("COMMIT")
        return done
    finally:
        db.close()


def rows(state_dir: Path) -> list[dict]:
    """Every ledger row, oldest first. Read-only: never creates the database."""
    path = state_dir / statedb.DB_FILE
    if not path.exists():
        return []
    db = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=statedb.TIMEOUT)
    db.row_factory = sqlite3.Row
    try:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name = 'runs'").fetchone():
            return []
        out = [dict(r) for r in db.execute("SELECT * FROM runs ORDER BY ended, session_id")]
    finally:
        db.close()
    for r in out:
        r["scopes"] = None if r["scopes"] is None else json.loads(r["scopes"])
    return out


def totals(ledger: list[dict], now: dt.datetime, tz: dt.tzinfo | None = None) -> dict:
    """{"today", "month": spend recorded today and this calendar month in tz (this machine's
    if None), "spent": {scope ref: every run's cost under it, ever}, "unscoped": cost of runs
    whose scopes aren't read yet, "no_cost": runs with no cost recorded}. Pure. Reporting
    only: per GOV-0033 none of these holds or stops anything."""
    here = now.astimezone(tz)
    today, month = here.date(), (here.year, here.month)
    out = {"today": 0.0, "month": 0.0, "spent": {}, "unscoped": 0.0, "no_cost": 0}
    for r in ledger:
        cost = r.get("cost_usd")
        if cost is None:
            out["no_cost"] += 1
            continue
        ended = dt.datetime.fromisoformat(r["ended"]).astimezone(tz)
        if (ended.year, ended.month) == month:
            out["month"] += cost
            if ended.date() == today:
                out["today"] += cost
        if r.get("scopes") is None:
            out["unscoped"] += cost
        for ref in r.get("scopes") or []:
            out["spent"][ref] = out["spent"].get(ref, 0.0) + cost
    return out


def usd(x: float) -> str:
    return f"${x:,.2f}"


def spent_text(t: dict, repo: str, now: dt.datetime, tz: dt.tzinfo | None = None) -> str:
    """`swarm spent`: the totals() report, as text for the terminal."""
    here = now.astimezone(tz)
    lines = [f"Spent today ({here:%a %Y-%m-%d}): {usd(t['today'])}",
             f"Spent this month ({here:%B %Y}): {usd(t['month'])}", ""]
    if t["spent"]:
        lines.append("Spent (all time) by Mission, Goal and Area:")
        short = lambda ref: ref[len(repo):] if ref.startswith(repo + "#") else ref  # noqa: E731
        for ref, cost in sorted(t["spent"].items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"  {short(ref):<28} {usd(cost):>10}")
    else:
        lines.append("No run is under a Mission, Goal or Area yet.")
    if t["unscoped"]:
        lines.append(f"{usd(t['unscoped'])} is on runs whose Mission, Goal or Area isn't read "
                     f"yet; swarm watch reads it on a later check.")
    if t["no_cost"]:
        lines.append(f"{t['no_cost']} run{'s' * (t['no_cost'] != 1)} recorded no cost "
                     f"(no result, or ended before Claude Code started).")
    lines += ["", "Costs are Claude Code's total_cost_usd estimates for runs swarm watch started. "
              "They are reported only: the engine has no spend total that holds runs (GOV-0033). "
              "The Project's Spent field isn't written yet (#731)."]
    return "\n".join(lines)
