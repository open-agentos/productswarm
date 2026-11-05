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

import committees
import generate

SCHEMA = 1

# What the page shows for a session (generate.session_rows), minus its spend column.
SESSION_FIELDS = ("session_id", "role", "model", "status", "issue", "pr", "gov_question",
                  "last_event", "last_ts", "started_ts", "tracking_issue")
# What the page shows for a PR (render's "Open pull requests" and the needs-you list).
PR_FIELDS = ("number", "title", "url", "author", "draft", "review", "created_ts", "closes",
             "needs_owner")
NEEDS_FIELDS = ("kind", "ref", "title", "url", "detail", "since", "session_url", "past_ttl")


def rfc3339(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def state(m: dict) -> dict:
    gov = {k: v for k, v in m["governance"].items() if k != "questions"}
    return plain({
        "schema": SCHEMA,
        "built_at": m["now"],
        "repo": m["repo"],
        "idle_minutes": m["idle_minutes"],
        "needs_you": needs(m),
        "sessions": [session(s) for s in m["sessions"]],
        "prs": [pick(p, PR_FIELDS) for p in m["prs"]],
        "gov_questions": [gov_question(q) for q in m["governance"]["questions"]],
        "governance": {**gov, "days": m["days"]},
        "committees": m.get("committees"),
        "committee_desk": committees.desk_states(m.get("committees")),
        "past_committees": committees.past_states(
            m.get("committees"), {r["id"]: r["ruling"] for r in gov.get("all_records") or []}, m["repo"]),
        "progress": m.get("progress"),
        "reviewer_runs": reviewer_runs(m["reviewer_runs"]),
    })
