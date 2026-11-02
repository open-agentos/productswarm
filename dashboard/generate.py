#!/usr/bin/env python3
"""Render the swarm dashboard: one static, read-only HTML page.

Reads, through `gh api` (in a swarm session that's ops/shims/gh acting as the role's App):
  - heartbeat events from the comments on `[heartbeat]` tracking issues (GOV-0003,
    heartbeat/SCHEMA.md). Only the GitHub copy is read, which never carries prompt
    text (GOV-0002); the local spool is not touched;
  - open PRs and the issues they close;
  - open `gov:question` issues.

Builds a page showing each session's role, current issue, last activity and status,
the open PRs, and the open gov questions with the sessions waiting on them.
Stdlib only, no JavaScript, per the default in gov question #26.

    python3 dashboard/generate.py                 # writes dashboard/out/index.html
    python3 dashboard/generate.py --out /tmp/x.html --days 7 --idle-minutes 15
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import subprocess
import sys
from pathlib import Path

import spend

HERE = Path(__file__).resolve().parent

SPEND_DAYS = 7     # days shown in the spend-per-day table
IDLE_MINUTES = 15  # heartbeat/SCHEMA.md leaves the idle threshold to #4
DAYS = 14          # closed tracking issues older than this are skipped

MARKER_RE = re.compile(r"\A\s*<!-- productswarm-heartbeat schema_version=1 session_id=(\S+) -->")
BOT_RE = re.compile(r"\Aproductswarm-([a-z0-9-]+)\[bot\]\Z")
FENCE_RE = re.compile(r"```jsonl[^\n]*\n(.*?)```", re.S)
REPO_RE = re.compile(r"github\.com[:/]([\w.-]+/[\w.-]+?)(?:\.git)?/?$")

EVENTS = {"session_started", "prompt_submitted", "working_on", "pr_opened",
          "blocked", "heartbeat", "stopped"}
REQUIRED = ("schema_version", "ts", "session_id", "repo", "role", "model", "event")
# Fields allowed in the GitHub copy of an event (#/$defs/remote in event.schema.json).
REMOTE_FIELDS = set(REQUIRED) | {"issue", "pr", "gov_question", "cost_usd", "token_counts", "tools"}
QUIET_EVENTS = {"heartbeat", "prompt_submitted"}
STATUS_ORDER = {"blocked": 0, "active": 1, "idle": 2, "stopped": 3}


# ---------------------------------------------------------------- reading GitHub

def gh_items(path: str) -> list[dict]:
    """Every item of a paginated list endpoint."""
    r = subprocess.run(["gh", "api", "--paginate", path, "--jq", ".[]"],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"gh api {path} failed: {r.stderr.strip()[:300]}")
    return [json.loads(line) for line in r.stdout.splitlines() if line.strip()]


def gh_json(*args: str) -> object:
    r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:2])} failed: {r.stderr.strip()[:300]}")
    return json.loads(r.stdout or "null")


def fetch(repo: str, now: dt.datetime, days: int) -> dict:
    """Everything the page needs, as plain API data. build() does the rest."""
    since = (now - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    issues: dict[int, dict] = {}
    for path in (f"repos/{repo}/issues?state=open&per_page=100",
                 f"repos/{repo}/issues?state=closed&since={since}&per_page=100"):
        for it in gh_items(path):
            if "pull_request" not in it:
                issues[it["number"]] = it
    comments = {s["issue"]: gh_items(f"repos/{repo}/issues/{s['issue']}/comments?per_page=100")
                for s in tracking_issues(issues.values())}
    prs = gh_json("pr", "list", "--repo", repo, "--state", "open", "--limit", "100", "--json",
                  "number,title,url,author,isDraft,createdAt,reviewDecision,closingIssuesReferences")
    return {"repo": repo, "issues": list(issues.values()), "comments": comments, "prs": prs or []}


# ---------------------------------------------------------------- deriving state

def parse_ts(s: str) -> dt.datetime | None:
    try:
        t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return t if t.tzinfo else None


def tracking_issues(issues) -> list[dict]:
    """Tracking issues: the heartbeat marker, opened by a productswarm-<role>[bot] App."""
    out = []
    for it in issues:
        login = (it.get("user") or {}).get("login", "")
        bot = BOT_RE.match(login)
        marker = MARKER_RE.match(it.get("body") or "")
        if bot and marker:
            out.append({"issue": it["number"], "session_id": marker.group(1), "role": bot.group(1),
                        "author": login, "closed": it.get("state") == "closed"})
    return out


def is_tracking(issue: dict) -> bool:
    return bool(tracking_issues([issue]))


def parse_comment(body: str) -> list[dict]:
    """Events from the first ```jsonl fence of a tracking comment; bad lines are skipped."""
    m = FENCE_RE.search(body or "")
    if not m:
        return []
    out = []
    for line in m.group(1).splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if isinstance(ev, dict):
            out.append(ev)
    return out


def valid_event(ev: dict, session: dict, repo: str) -> bool:
    if any(k not in ev for k in REQUIRED) or set(ev) - REMOTE_FIELDS:
        return False
    if ev["schema_version"] != 1 or ev["event"] not in EVENTS or parse_ts(ev["ts"]) is None:
        return False
    # The comment must describe this tracking issue's session, role and repo.
    return (ev["session_id"] == session["session_id"] and ev["role"] == session["role"]
            and ev["repo"] == repo)


def session_events(session: dict, comments: list[dict], repo: str) -> list[dict]:
    """Valid events posted by the App that opened the tracking issue, oldest first."""
    events = []
    for c in comments:
        if (c.get("user") or {}).get("login") != session["author"]:
            continue  # anyone else's comment is not a heartbeat
        events += [e for e in parse_comment(c.get("body", "")) if valid_event(e, session, repo)]
    events.sort(key=lambda e: parse_ts(e["ts"]))
    return events


def derive(session: dict, events: list[dict], open_issues: set[int], now: dt.datetime,
           idle_after: dt.timedelta) -> dict:
    """Status per heartbeat/SCHEMA.md, 'How the dashboard reads status'."""
    last = events[-1] if events else None
    last_ts = parse_ts(last["ts"]) if last else None
    state_ev = next((e for e in reversed(events) if e["event"] not in QUIET_EVENTS), None)
    issue = next((e["issue"] for e in reversed(events) if e.get("issue")), None)
    # Show a PR only while the session is still on the issue it was opened for (#29).
    pr = next((e["pr"] for e in reversed(events) if e.get("pr") and e.get("issue") == issue), None)
    gov = None
    if (last and last["event"] == "stopped") or session["closed"]:
        status = "stopped"  # the hook closes the issue after posting `stopped`
    elif state_ev and state_ev["event"] == "blocked" and state_ev.get("gov_question") in open_issues:
        status, gov = "blocked", state_ev["gov_question"]
    elif last_ts is None or now - last_ts > idle_after:
        status = "idle"
    else:
        status = "active"
    return {
        "session_id": session["session_id"], "role": session["role"],
        "tracking_issue": session["issue"], "status": status, "issue": issue, "pr": pr,
        "gov_question": gov, "model": last["model"] if last else None,
        "last_event": last["event"] if last else None, "last_ts": last_ts,
        "started_ts": parse_ts(events[0]["ts"]) if events else None,
        "cost": spend.session_cost(events), "daily": spend.daily(events, parse_ts),
    }


def build(data: dict, now: dt.datetime, idle_after: dt.timedelta) -> dict:
    repo = data["repo"]
    issues = {i["number"]: i for i in data["issues"]}
    open_issues = {n for n, i in issues.items() if i.get("state") == "open"}
    sessions = []
    for s in tracking_issues(issues.values()):
        events = session_events(s, data["comments"].get(s["issue"], []), repo)
        sessions.append(derive(s, events, open_issues, now, idle_after))
    epoch = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    sessions.sort(key=lambda s: (STATUS_ORDER[s["status"]], -(s["last_ts"] or epoch).timestamp()))

    gov = []
    for n in sorted(open_issues):
        it = issues[n]
        labels = [lb["name"] for lb in it.get("labels", [])]
        if "gov:question" in labels and not is_tracking(it):
            gov.append({"number": n, "title": it["title"], "url": it["html_url"],
                        "labels": [lb for lb in labels if lb != "gov:question"],
                        "created_ts": parse_ts(it["created_at"]),
                        "waiting": [s for s in sessions if s["gov_question"] == n]})

    prs = []
    for p in sorted(data["prs"], key=lambda p: p["number"]):
        closes = [{"number": c["number"], "title": issues.get(c["number"], {}).get("title", "")}
                  for c in p.get("closingIssuesReferences") or []]
        prs.append({"number": p["number"], "title": p["title"], "url": p["url"],
                    "author": (p.get("author") or {}).get("login", ""), "draft": p.get("isDraft"),
                    "review": p.get("reviewDecision") or "", "created_ts": parse_ts(p["createdAt"]),
                    "closes": closes})

    today = now.date()
    days = [today - dt.timedelta(days=i) for i in range(SPEND_DAYS)]
    per_day = {d: sum(s["daily"].get(d, 0.0) for s in sessions) for d in days}

    return {"repo": repo, "now": now, "idle_minutes": int(idle_after.total_seconds() // 60),
            "issue_titles": {n: i["title"] for n, i in issues.items()},
            "sessions": sessions, "prs": prs, "gov": gov,
            "spend": {"per_day": per_day, "today": per_day[today],
                      "unpriced": [s for s in sessions if s["cost"] is None]}}


# ---------------------------------------------------------------- rendering

CSS = """
:root { --bg:#fff; --fg:#1f2328; --muted:#656d76; --line:#d0d7de; --card:#f6f8fa;
  --active:#1a7f37; --idle:#9a6700; --blocked:#cf222e; --stopped:#8c959f; --link:#0969da; }
@media (prefers-color-scheme: dark) { :root { --bg:#0d1117; --fg:#e6edf3; --muted:#8d96a0;
  --line:#30363d; --card:#161b22; --active:#3fb950; --idle:#d29922; --blocked:#f85149;
  --stopped:#6e7681; --link:#4493f8; } }
* { box-sizing:border-box; }
body { margin:0; padding:24px 16px; background:var(--bg); color:var(--fg);
  font:14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }
main { max-width:1100px; margin:0 auto; }
h1 { font-size:20px; margin:0 0 4px; } h2 { font-size:16px; margin:28px 0 8px; }
a { color:var(--link); text-decoration:none; } a:hover { text-decoration:underline; }
.muted { color:var(--muted); }
.needs { display:flex; flex-wrap:wrap; gap:8px; margin:16px 0 0; }
.needs div { background:var(--card); border:1px solid var(--line); border-radius:6px; padding:8px 12px; }
.needs b { font-size:18px; margin-right:4px; }
.needs .hot { border-color:var(--blocked); }
.scroll { overflow-x:auto; }
table { border-collapse:collapse; width:100%; }
th, td { text-align:left; padding:6px 10px 6px 0; border-bottom:1px solid var(--line); vertical-align:top; }
th { font-weight:600; color:var(--muted); font-size:12px; white-space:nowrap; }
.pill { display:inline-block; padding:0 8px; border-radius:10px; font-size:12px; font-weight:600;
  color:#fff; white-space:nowrap; }
.s-active { background:var(--active); } .s-idle { background:var(--idle); }
.s-blocked { background:var(--blocked); } .s-stopped { background:var(--stopped); }
code { font-size:12px; }
.num { text-align:right; white-space:nowrap; }
table.narrow { width:auto; min-width:240px; }
.method { max-width:720px; font-size:12px; }
details summary { cursor:pointer; margin:12px 0 4px; color:var(--muted); }
"""


NONE = '<span class="muted">none</span>'


def esc(x) -> str:
    return html.escape("" if x is None else str(x))


def ago(t: dt.datetime | None, now: dt.datetime) -> str:
    if t is None:
        return "never"
    s = max(0, int((now - t).total_seconds()))
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if s >= size:
            return f"{s // size}{unit} ago"
    return "just now"


def stamp(t: dt.datetime | None) -> str:
    return t.strftime("%Y-%m-%d %H:%M UTC") if t else ""


def issue_link(repo: str, n: int | None, titles: dict, show_title: bool = True) -> str:
    if not n:
        return '<span class="muted">—</span>'
    url = f"https://github.com/{esc(repo)}/issues/{n}"
    title = titles.get(n)
    label = f"#{n}" + (f" {esc(title)}" if show_title and title else "")
    return f'<a href="{url}" title="{esc(title)}">{label}</a>'


def session_rows(m: dict, sessions: list[dict]) -> str:
    repo, now, titles = m["repo"], m["now"], m["issue_titles"]
    rows = []
    for s in sessions:
        status = f'<span class="pill s-{s["status"]}">{s["status"]}</span>'
        if s["gov_question"]:
            status += f' on {issue_link(repo, s["gov_question"], titles, show_title=False)}'
        pr = (f' · PR <a href="https://github.com/{esc(repo)}/pull/{s["pr"]}">#{s["pr"]}</a>'
              if s["pr"] else "")
        rows.append(
            "<tr>"
            f"<td>{status}</td>"
            f"<td><b>{esc(s['role'])}</b><br><span class=\"muted\">{esc(s['model'] or '')}</span></td>"
            f"<td>{issue_link(repo, s['issue'], titles)}{pr}</td>"
            f"<td title=\"{esc(stamp(s['last_ts']))}\">{esc(ago(s['last_ts'], now))}"
            f"<br><span class=\"muted\">{esc(s['last_event'] or '')}</span></td>"
            f"<td><a href=\"https://github.com/{esc(repo)}/issues/{s['tracking_issue']}\">"
            f"<code>{esc(s['session_id'][:8])}</code></a>"
            f"<br><span class=\"muted\">started {esc(ago(s['started_ts'], now))}</span></td>"
            f"<td class=\"num\">{esc(spend.usd(s['cost']))}</td>"
            "</tr>")
    head = ("<tr><th>Status</th><th>Role</th><th>Current issue</th>"
            "<th>Last activity</th><th>Session</th><th class=\"num\">Spend (est.)</th></tr>")
    return f'<div class="scroll"><table>{head}{"".join(rows)}</table></div>'


def render(m: dict) -> str:
    repo, now, titles = m["repo"], m["now"], m["issue_titles"]
    live = [s for s in m["sessions"] if s["status"] != "stopped"]
    stopped = [s for s in m["sessions"] if s["status"] == "stopped"]
    blocked = sum(s["status"] == "blocked" for s in live)
    ready = [p for p in m["prs"] if not p["draft"]]

    def tile(n: int, label: str, hot: bool = False) -> str:
        return f'<div class="{"hot" if hot and n else ""}"><b>{n}</b>{esc(label)}</div>'

    out = [
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">",
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="robots" content="noindex, nofollow">',  # published publicly; see #33
        f"<title>Swarm dashboard · {esc(repo)}</title><style>{CSS}</style></head><body><main>",
        f"<h1>Swarm dashboard</h1><div class=\"muted\">{esc(repo)} · generated {esc(stamp(now))}"
        f" · idle after {m['idle_minutes']} min without an event</div>",
        '<div class="needs">',
        tile(blocked, "blocked sessions", hot=True),
        tile(len(m["gov"]), "open gov questions", hot=True),
        tile(len(ready), "PRs to review", hot=True),
        tile(sum(s["status"] == "active" for s in live), "active"),
        tile(sum(s["status"] == "idle" for s in live), "idle"),
        f'<div><b>{esc(spend.usd(m["spend"]["today"]))}</b>spent today (est.)</div>',
        "</div>",
        "<h2>Sessions</h2>",
        session_rows(m, live) if live else '<p class="muted">No live sessions.</p>',
    ]
    if stopped:
        out += [f"<details><summary>{len(stopped)} stopped</summary>", session_rows(m, stopped),
                "</details>"]

    out.append("<h2>Open pull requests</h2>")
    if m["prs"]:
        rows = []
        for p in m["prs"]:
            closes = ", ".join(issue_link(repo, c["number"], titles) for c in p["closes"])
            state = "draft" if p["draft"] else (p["review"].replace("_", " ").lower() or "awaiting review")
            rows.append(f"<tr><td><a href=\"{esc(p['url'])}\">#{p['number']}</a> {esc(p['title'])}</td>"
                        f"<td>{closes or NONE}</td>"
                        f"<td>{esc(p['author'])}</td><td>{esc(state)}</td>"
                        f"<td title=\"{esc(stamp(p['created_ts']))}\">{esc(ago(p['created_ts'], now))}</td></tr>")
        out.append('<div class="scroll"><table><tr><th>PR</th><th>Closes</th><th>Author</th>'
                   f'<th>State</th><th>Opened</th></tr>{"".join(rows)}</table></div>')
    else:
        out.append('<p class="muted">None.</p>')

    out.append("<h2>Open gov questions</h2>")
    if m["gov"]:
        rows = []
        for g in m["gov"]:
            waiting = ", ".join(f"{esc(s['role'])} <code>{esc(s['session_id'][:8])}</code>"
                                for s in g["waiting"])
            rows.append(f"<tr><td><a href=\"{esc(g['url'])}\">#{g['number']}</a> {esc(g['title'])}</td>"
                        f"<td>{esc(', '.join(g['labels']))}</td>"
                        f"<td>{waiting or NONE}</td>"
                        f"<td title=\"{esc(stamp(g['created_ts']))}\">{esc(ago(g['created_ts'], now))}</td></tr>")
        out.append('<div class="scroll"><table><tr><th>Question</th><th>Labels</th>'
                   f'<th>Sessions waiting</th><th>Opened</th></tr>{"".join(rows)}</table></div>')
    else:
        out.append('<p class="muted">None.</p>')

    sp = m["spend"]
    out.append("<h2>Spend per day (est.)</h2>")
    rows = "".join(f"<tr><td>{d.isoformat()}</td><td class=\"num\">{esc(spend.usd(v))}</td></tr>"
                   for d, v in sp["per_day"].items())
    out.append('<div class="scroll"><table class="narrow"><tr><th>Day (UTC)</th>'
               f'<th class="num">Spend</th></tr>{rows}</table></div>')
    note = spend.METHOD + " Per day is each session's increase within that UTC day."
    if sp["unpriced"]:
        ids = ", ".join(f"{s['role']} {s['session_id'][:8]}" for s in sp["unpriced"])
        note += (f" Left out of totals, with no tokens or an unpriced model: "
                 f"{len(sp['unpriced'])} session(s) ({ids}).")
    out.append(f'<p class="muted method">Method: {esc(note)}</p>')

    out.append("</main></body></html>\n")
    return "\n".join(out)


# ---------------------------------------------------------------- CLI

def default_repo() -> str | None:
    try:
        url = subprocess.run(["git", "-C", str(HERE), "remote", "get-url", "origin"],
                             capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    m = REPO_RE.search(url)
    return m.group(1) if m else None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Render the swarm dashboard to a static HTML file.")
    ap.add_argument("--repo", help="owner/name (default: this checkout's origin)")
    ap.add_argument("--out", default=str(HERE / "out" / "index.html"), help="output file")
    ap.add_argument("--days", type=int, default=DAYS, help="include sessions closed in the last N days")
    ap.add_argument("--idle-minutes", type=int, default=IDLE_MINUTES,
                    help="a live session is idle after this long without an event")
    args = ap.parse_args(argv)

    repo = args.repo or default_repo()
    if not repo:
        print("generate.py: can't tell the repo; pass --repo owner/name", file=sys.stderr)
        return 2
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    try:
        data = fetch(repo, now, args.days)
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError) as e:
        print(f"generate.py: {e}", file=sys.stderr)
        return 1
    model = build(data, now, dt.timedelta(minutes=args.idle_minutes))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(model), encoding="utf-8")
    live = sum(s["status"] != "stopped" for s in model["sessions"])
    print(f"wrote {out}: {live} live / {len(model['sessions'])} sessions, "
          f"{len(model['prs'])} open PRs, {len(model['gov'])} open gov questions")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
