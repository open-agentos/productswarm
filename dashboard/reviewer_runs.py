"""The dashboard's Actions reviewer section (#356, part 4 of #348).

Shows the reviewer workflow's recent sweeps and how each started (schedule, nudge or a
manual dispatch), the review jobs each ran, the review-job success rate, the time from a
head's commit to its first reviewer-App review, and how many builder PRs have no reviewer
review at their head (generate.unreviewed(), #344; not a second rule).

Reads only run, job, review and commit metadata. It never fetches job logs: GOV-0016 puts
`total_cost_usd` in them, and #348 keeps cost off the page. Without `actions: read` the
section says so in one line and the rest of the page still builds.

generate.py fetches the data and calls build() and render(). Stdlib only, no JavaScript.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import statistics
import subprocess
import sys
from pathlib import Path

LAUNCHER = Path(__file__).resolve().parent.parent / "launcher"

WINDOW_DAYS = 7
MAX_RUNS = 30               # the newest runs in the window, at most
NUDGE_ACTOR = "github-actions[bot]"   # reviewer-nudge.yml's dispatches show this actor
REVIEWER = "productswarm-reviewer[bot]"
NO_ACTIONS = "can't read Actions runs: the token needs `actions: read`"




def _actions_review():
    """launcher/actions_review.py, imported on first use: it imports swarm, which imports
    generate, so importing it while generate loads would be circular."""
    if str(LAUNCHER) not in sys.path:
        sys.path.insert(0, str(LAUNCHER))
    import actions_review
    return actions_review


def parse_review_job(name: object) -> tuple[int, str] | None:
    """(pr, head) from a `review #<pr> <sha>` job name (REVIEW_JOB), else None."""
    return _actions_review().parse_review_job(name)


# ---------------------------------------------------------------- reading GitHub

def _gh(path: str, jq: str, paginate: bool) -> list[dict]:
    if "/logs" in path:   # never: GOV-0016 puts run cost in the logs (#348)
        raise ValueError(f"refusing to read logs: {path}")
    argv = ["gh", "api", *(["--paginate"] if paginate else []), path, "--jq", jq]
    r = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"gh api {path.split('?')[0]} failed: {r.stderr.strip()[:300]}")
    return [json.loads(line) for line in r.stdout.splitlines() if line.strip()]


def fetch(repo: str, now: dt.datetime, reviews: dict[int, list[dict]]) -> dict:
    """The section's raw data. `reviews` is generate.fetch()'s reviews on open PRs, reused
    so those aren't read twice. Never raises: a failure is kept as an error line."""
    since = (now - dt.timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%d")
    try:
        runs = _gh(f"repos/{repo}/actions/workflows/{_actions_review().WORKFLOW}/runs"
                   f"?per_page={MAX_RUNS}&created=%3E%3D{since}", ".workflow_runs[]", False)
        jobs = {r["id"]: _gh(f"repos/{repo}/actions/runs/{r['id']}/jobs?per_page=100",
                             ".jobs[]", True) for r in runs if isinstance(r.get("id"), int)}
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError) as e:
        msg = str(e)
        no_access = "403" in msg or "not accessible" in msg.lower()
        return {"error": NO_ACTIONS if no_access else f"can't read Actions runs: {msg[:200]}"}
    data = {"runs": runs, "jobs": jobs, "reviews": {}, "commits": {}}
    # Reviews and head dates for every PR a sweep reviewed in the window, plus open PRs.
    prs = {parsed[0] for js in jobs.values() for j in js if (parsed := parse_review_job(j.get("name")))}
    try:
        for n in sorted(prs | set(reviews)):
            rv = reviews.get(n)
            if rv is None:
                rv = _gh(f"repos/{repo}/pulls/{n}/reviews?per_page=100", ".[]", True)
            data["reviews"][n] = rv
            if any((r.get("user") or {}).get("login") == REVIEWER for r in rv):
                data["commits"][n] = _gh(f"repos/{repo}/pulls/{n}/commits?per_page=100", ".[]", True)
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError) as e:
        data["times_error"] = f"can't read reviews: {str(e)[:200]}"
    return data


# ---------------------------------------------------------------- deriving state

def parse_ts(s: object) -> dt.datetime | None:
    try:
        t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        return None
    return t if t.tzinfo else None


def started_by(run: dict) -> str:
    """How a sweep started: "schedule", "nudge", "manual (<login>)", or the event name."""
    event = run.get("event")
    if event == "schedule":
        return "schedule"
    if event == "workflow_dispatch":
        actor = (run.get("triggering_actor") or run.get("actor") or {}).get("login", "")
        return "nudge" if actor == NUDGE_ACTOR else f"manual ({actor or 'unknown'})"
    return str(event or "unknown")


def outcome(x: dict) -> str:
    """A run's or job's conclusion, or its status while it hasn't finished."""
    return x.get("conclusion") or x.get("status") or "unknown"


def commit_to_review(reviews: dict[int, list[dict]], commits: dict[int, list[dict]],
                     since: dt.datetime) -> list[dict]:
    """Each head's first reviewer-App review submitted at or after `since`, timed from the
    reviewed commit's committer date (not push time, which the API doesn't give). A review
    counts for the commit it was made on, so one on an older head says nothing about the
    PR's current head."""
    out = []
    for n, rv in sorted(reviews.items()):
        dates = {c.get("sha"): parse_ts(((c.get("commit") or {}).get("committer") or {}).get("date"))
                 for c in commits.get(n, [])}
        seen = set()
        for r in rv:   # REST order: oldest first
            sha, at = r.get("commit_id"), parse_ts(r.get("submitted_at"))
            if (r.get("user") or {}).get("login") != REVIEWER or not at or sha in seen:
                continue
            seen.add(sha)
            if at >= since and dates.get(sha):
                out.append({"pr": n, "head": sha, "seconds": max(0, (at - dates[sha]).total_seconds())})
    return out


def build(data: dict | None, unreviewed_prs: list[dict], now: dt.datetime) -> dict:
    """The section's model. `unreviewed_prs` is generate.build()'s non-draft PRs that
    generate.unreviewed() flags."""
    m = {"window_days": WINDOW_DAYS, "unreviewed": unreviewed_prs}
    data = data or {"error": "Actions runs weren't read"}
    if data.get("error"):
        return {**m, "error": data["error"]}
    sweeps, review_jobs = [], []
    for run in sorted(data["runs"], key=lambda r: r.get("created_at") or "", reverse=True):
        reviewed = []
        for j in data["jobs"].get(run.get("id"), []):
            parsed = parse_review_job(j.get("name"))
            if parsed:
                reviewed.append({"pr": parsed[0], "head": parsed[1], "outcome": outcome(j),
                                 "done": j.get("status") == "completed", "url": j.get("html_url")})
        review_jobs += reviewed
        sweeps.append({"ts": parse_ts(run.get("created_at")), "started_by": started_by(run),
                       "outcome": outcome(run), "done": run.get("status") == "completed",
                       "url": run.get("html_url"), "reviewed": reviewed})
    done = [j for j in review_jobs if j["done"]]
    times = commit_to_review(data["reviews"], data["commits"], now - dt.timedelta(days=WINDOW_DAYS))
    secs = [t["seconds"] for t in times]
    return {**m, "sweeps": sweeps, "jobs_done": len(done),
            "jobs_ok": sum(j["outcome"] == "success" for j in done),
            "failed": [j for j in done if j["outcome"] != "success"],
            "times": times, "times_error": data.get("times_error"),
            "median": statistics.median(secs) if secs else None,
            "longest": max(times, key=lambda t: t["seconds"]) if times else None}


# ---------------------------------------------------------------- rendering

def esc(x) -> str:
    return html.escape("" if x is None else str(x))


def duration(seconds: float) -> str:
    s = int(seconds)
    d, h, mi = s // 86400, s % 86400 // 3600, s % 3600 // 60
    if d:
        return f"{d}d {h}h"
    if h:
        return f"{h}h {mi}m"
    return f"{mi}m" if mi else f"{s}s"


def render(r: dict, repo: str, now: dt.datetime, ago, stamp) -> str:
    def pr_link(n, head=None):
        label = f"#{n}" + (f" <code>{esc(head[:7])}</code>" if head else "")
        return f'<a href="https://github.com/{esc(repo)}/pull/{n}">{label}</a>'

    out = ["<h2>Actions reviewer</h2>"]
    unrev = r["unreviewed"]
    unrev_line = (f"{len(unrev)} builder PR{'s' if len(unrev) != 1 else ''} with no reviewer review "
                  f"at {'their' if len(unrev) != 1 else 'its'} head"
                  + (": " + ", ".join(pr_link(p["number"]) for p in unrev) if unrev else "")
                  + " (also in Needs you).")
    if r.get("error"):
        out.append(f'<p class="muted">{esc(r["error"])}</p><p>{unrev_line}</p>')
        return "\n".join(out)

    days = r["window_days"]
    rate = f"{r['jobs_ok']} of {r['jobs_done']} review jobs succeeded in the last {days} days"
    if r["failed"]:
        rate += ". Failed: " + ", ".join(
            f'<a href="{esc(j["url"])}">#{j["pr"]} <code>{esc(j["head"][:7])}</code></a> '
            f'({esc(j["outcome"])})' for j in r["failed"])
    if r.get("times_error"):
        times = f'<span class="muted">Commit to review: {esc(r["times_error"])}</span>'
    elif r["times"]:
        lg = r["longest"]
        times = (f"Commit to review: median {duration(r['median'])}, longest {duration(lg['seconds'])} "
                 f"({pr_link(lg['pr'], lg['head'])}), over {len(r['times'])} reviewed heads.")
    else:
        times = '<span class="muted">Commit to review: no reviewer reviews in the window.</span>'
    out.append(f"<p>{rate}.<br>{times}<br>{unrev_line}</p>")

    if not r["sweeps"]:
        out.append(f'<p class="muted">No reviewer sweeps in the last {days} days.</p>')
    else:
        rows = []
        for s in r["sweeps"]:
            if s["reviewed"]:
                what = "<br>".join(f"{pr_link(j['pr'], j['head'])} "
                                   + (f'<a href="{esc(j["url"])}">{esc(j["outcome"])}</a>'
                                      if j["url"] else esc(j["outcome"]))
                                   for j in s["reviewed"])
            else:
                what = ('<span class="muted">nothing to review</span>'
                        if s["outcome"] == "success" else '<span class="muted">no review jobs</span>')
            rows.append(f"<tr><td title=\"{esc(stamp(s['ts']))}\">{esc(ago(s['ts'], now))}</td>"
                        f"<td>{esc(s['started_by'])}</td>"
                        f"<td><a href=\"{esc(s['url'])}\">{esc(s['outcome'])}</a></td>"
                        f"<td>{what}</td></tr>")
        out.append(f'<details><summary>{len(r["sweeps"])} sweeps in the last {days} days '
                   f'(newest {MAX_RUNS} at most)</summary><div class="scroll"><table>'
                   "<tr><th>Started</th><th>How</th><th>Sweep</th><th>Reviewed</th></tr>"
                   f'{"".join(rows)}</table></div></details>')
    out.append('<p class="muted method">Commit to review runs from the reviewed commit\'s committer '
               "date (GitHub doesn't give push time) to the reviewer App's first review of that "
               "commit. No cost is shown, and no job logs are read.</p>")
    return "\n".join(out)
