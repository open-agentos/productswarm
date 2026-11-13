"""The data the dashboard page shows, as JSON: `state.json`, written beside `index.html` (#400).

`state(model)` takes what `generate.build()` returns and keeps only what the page renders,
with no HTML. It carries no cost: no session cost, daily spend, cap or over-cap flag, and no
spend block (GOV-0014; #397). It's public like the page (#33), so sessions and PRs keep only
the fields the page shows, by name.

Timestamps are RFC 3339 strings in UTC (`2026-11-05T07:20:08Z`); dates are `YYYY-MM-DD`.
Each later #397 panel adds its slice here.
"""
import datetime as dt
from pathlib import Path

import activity
import committees
import effort
import grants
import floor as floor_mod
import generate
import layout
import live
import plan
import precedent
import report
import wire

SCHEMA = 1

# What the page shows for a session (generate.session_rows), minus its spend column.
SESSION_FIELDS = ("session_id", "role", "model", "status", "issue", "pr", "gov_question",
                  "last_event", "last_ts", "started_ts", "tracking_issue")
# What the page shows for a PR (render's "Open pull requests" and the needs-you list).
PR_FIELDS = ("number", "title", "url", "author", "draft", "review", "created_ts", "closes",
             "needs_owner")
NEEDS_FIELDS = ("kind", "ref", "title", "url", "detail", "since", "session_url", "past_ttl")


rfc3339 = generate.rfc3339


def plain(x):
    """JSON-ready: datetimes as RFC 3339, dates as ISO, tuples as lists, keys as strings.
    Anything else that JSON can't hold is an error, so a new type can't slip out unseen."""
    if isinstance(x, dt.datetime):
        return rfc3339(x)
    if isinstance(x, dt.date):
        return x.isoformat()
    if isinstance(x, dict):
        return {str(k): plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [plain(v) for v in x]
    if x is None or isinstance(x, (str, int, float, bool)):
        return x
    if isinstance(x, Path):
        return x.name
    raise TypeError(f"state.json can't hold {type(x).__name__}")


def pick(d: dict, fields: tuple) -> dict:
    return {k: d[k] for k in fields if k in d}


def session(s: dict) -> dict:
    return pick(s, SESSION_FIELDS)


def needs(m: dict) -> list[dict]:
    # Over-cap items are about spend (their detail is the cost), so they stay off (#397).
    return [pick(i, NEEDS_FIELDS) for i in generate.needs_you(m) if i["kind"] != "over_cap"]


def gov_question(q: dict) -> dict:
    out = {k: v for k, v in q.items() if k not in ("fields", "waiting")}
    out["waiting"] = [s["session_id"] for s in q["waiting"]]   # sessions are listed once, above
    return out


def reviewer_runs(r: dict) -> dict:
    return {**r, "unreviewed": [p["number"] for p in r.get("unreviewed") or []]}


# A floor card (floor.py) minus its unfilled template; it has no tokens or cost to drop.
CARD_FIELDS = ("session_id", "role", "model", "status", "started_ts", "run_minutes", "issue", "pr",
               "gov_question", "activity", "events_per_slot", "slots_used")


def floor(f: dict | None) -> dict | None:
    if f is None:
        return None
    return {"cards": [pick(c, CARD_FIELDS) for c in f["cards"]], "idle": f["idle"]}


# The watcher's state (#459): floor.watcher() already kept only #456's fields, so this
# copies them by name again and adds nothing. No cost: #456's public form carries none.
WATCHER_FIELDS = ("status", "issue", "checked", "age_minutes", "stale", *floor_mod.LISTS)


def watcher(w: dict | None) -> dict | None:
    return None if w is None else pick(w, WATCHER_FIELDS)


def desk(m: dict) -> dict:
    """The desk's masthead and panels as node trees, which the live refresh draws (#411)."""
    mast = layout.masthead("index.html", m["repo"], m["now"], generate.owner_line(m))
    return live.trees({"mast": mast, **generate.desk_panels(m)})


def state(m: dict) -> dict:
    gov = {k: v for k, v in m["governance"].items() if k != "questions"}
    return plain({
        "schema": SCHEMA,
        "built_at": m["now"],
        "repo": m["repo"],
        "idle_minutes": m["idle_minutes"],
        "needs_you": needs(m),
        "sessions": [session(s) for s in m["sessions"]],
        "floor": floor(m.get("floor")),
        "watcher": watcher(m.get("watcher")),   # #459: swarm watch's state, from the [watch] issue
        "prs": [pick(p, PR_FIELDS) for p in m["prs"]],
        "gov_questions": [gov_question(q) for q in m["governance"]["questions"]],
        "governance": {**gov, "days": m["days"]},
        "committees": m.get("committees"),
        "committee_desk": committees.desk_states(m.get("committees")),
        "past_committees": committees.past_states(
            m.get("committees"), {r["id"]: r["ruling"] for r in gov.get("all_records") or []}, m["repo"]),
        "progress": m.get("progress"),
        "reviewer_runs": reviewer_runs(m["reviewer_runs"]),
        "trends": m.get("trends"),   # #406: each trend's sentence and its series by day
        "questions_went": m.get("questions_went"),   # #407: counts, and each question's categories
        "precedent": precedent.state(m.get("precedent")),   # #408; the next build carries it forward
        "owner_last_acted": activity.state(m.get("owner_last_acted")),   # #402: the header's line
        "wire": wire.state(m.get("wire")),
        "report": report.state(m.get("report")),   # #712: today's report, its asks, the check-in
        "plan": plan.state(m.get("plan")),   # #712: the owner's Goals and Areas, each sub-issue's go   # #405: today's governance events, newest first
        "grants": grants.state(m.get("grants")),   # #713: the merger's calls in the last 24 hours
        "effort": effort.state(m.get("effort")),   # #1013: PRs by kind of work per open Goal, and the trend
        "desk": desk(m),   # #411: what the desk's live refresh draws
    })
