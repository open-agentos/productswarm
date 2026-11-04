#!/usr/bin/env python3
"""Render the swarm dashboard: one static, read-only HTML page.

Reads, through `gh api` (in a swarm session that's ops/shims/gh acting as the role's App):
  - heartbeat events from the comments on `[heartbeat]` tracking issues (GOV-0003,
    heartbeat/SCHEMA.md). Only the GitHub copy is read, which never carries prompt
    text (GOV-0002); the local spool is not touched;
  - open PRs, the issues they close, and the reviewer App's reviews on each non-draft
    PR (GOV-0011's round count and Authority line);
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

REVIEWER = "productswarm-reviewer[bot]"
BUILDER = "productswarm-builder"   # the App GOV-0011's [respond] starts; `gh` shows it as app/<slug>
CHANGES = "CHANGES_REQUESTED"
ROUNDS = 2         # builder rounds per PR before the owner steps in (GOV-0011)
# The rubric line roles/reviewer.md asks for: "- **Authority:** pass|fail".
AUTHORITY_RE = re.compile(r"^[\s>*-]*Authority\s*:?[\s*]*:?\s*(pass|fail)\b", re.I | re.M)


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
                  "number,title,url,author,isDraft,createdAt,reviewDecision,closingIssuesReferences,"
                  "headRefOid")
    reviews = {p["number"]: gh_items(f"repos/{repo}/pulls/{p['number']}/reviews?per_page=100")
               for p in prs or [] if not p.get("isDraft")}
    return {"repo": repo, "issues": list(issues.values()), "comments": comments, "prs": prs or [],
            "reviews": reviews}


# ---------------------------------------------------------------- deriving state

def reviewer_state(reviews: list[dict], head: str | None) -> dict:
    """The reviewer App's reviews on one PR (REST order, oldest first), as GOV-0011 reads
    them: how many times it requested changes, on any head, and its latest review at
    `head` with that review's Authority line. Keeps no review text (GOV-0002)."""
    mine = [r for r in reviews if (r.get("user") or {}).get("login") == REVIEWER]
    at_head = [r for r in mine if head and r.get("commit_id") == head]
    last = at_head[-1] if at_head else None
    m = AUTHORITY_RE.search((last or {}).get("body") or "")
    return {"changes_requested": sum(r.get("state") == CHANGES for r in mine),
            "at_head": last.get("state") if last else None,
            "authority": m.group(1).lower() if m else None}


def pr_role(author: str) -> str | None:
    """The productswarm role whose App opened a PR, from its author login: `gh` shows an App
    as app/productswarm-<role>, the REST API as productswarm-<role>[bot]. None for others."""
    m = re.fullmatch(r"(?:app/)?productswarm-([a-z0-9-]+?)(?:\[bot\])?", author or "")
    return m.group(1) if m else None


def past_bound(changes_requested: int) -> bool:
    """GOV-0011's round bound: the builder gets ROUNDS rounds, so the reviewer App's
    (ROUNDS + 1)th "changes requested" on a PR sends it to the owner. evals/red_check.py
    (#330) counts with this too."""
    return changes_requested > ROUNDS


def needs_owner(r: dict, author: str) -> str | None:
    """Why GOV-0011 hands this PR to the owner instead of the builder, else None.

    The builder responds only on its own PR (GOV-0011), so requested changes on a PR
    another author opened (a docs ruling PR, say) go to the owner too (#178)."""
    if r["at_head"] is None:
        return None
    if r["authority"] == "fail":
        return "overstep: needs the owner"
    role = pr_role(author)
    if r["at_head"] == CHANGES and f"productswarm-{role}" != BUILDER:
        return f"changes requested on a {role or 'non-swarm'} PR: needs the owner"
    if r["at_head"] == CHANGES and past_bound(r["changes_requested"]):
        return f"changes requested {r['changes_requested']} times: needs the owner"
    return None


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


def load_caps(path: Path | None = None) -> dict[str, float]:
    """Per-session spend cap by role, from the committed swarm.toml (L4, #52).

    The manifest is public, so caps keep the page public-data-only. A session's cap is
    its role's `spend_cap_usd`; no cap if the role sets none (#45). A missing or invalid
    manifest gives no caps rather than breaking the page."""
    try:
        sys.path.insert(0, str(HERE.parent / "launcher"))
        import manifest
        sessions = manifest.load(path or manifest.DEFAULT_PATH)
    except Exception:   # ImportError (no tomllib), ManifestError: no caps, page still renders
        return {}
    return {s.role: s.spend_cap_usd for s in sessions if s.spend_cap_usd is not None}


def over_cap(cost: float | None, cap: float | None) -> bool:
    """Warn-only (GOV-0008): this flags a session; nothing stops it."""
    return cost is not None and cap is not None and cost > cap


def build(data: dict, now: dt.datetime, idle_after: dt.timedelta,
          caps: dict[str, float] | None = None) -> dict:
    repo = data["repo"]
    issues = {i["number"]: i for i in data["issues"]}
    open_issues = {n for n, i in issues.items() if i.get("state") == "open"}
    sessions = []
    for s in tracking_issues(issues.values()):
        events = session_events(s, data["comments"].get(s["issue"], []), repo)
        d = derive(s, events, open_issues, now, idle_after)
        d["cap"] = (caps or {}).get(d["role"])
        d["over_cap"] = d["status"] != "stopped" and over_cap(d["cost"], d["cap"])
        sessions.append(d)
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
                        "ttl": time_to_live(it.get("body")),
                        "waiting": [s for s in sessions if s["gov_question"] == n]})

    prs = []
    for p in sorted(data["prs"], key=lambda p: p["number"]):
        closes = [{"number": c["number"], "title": issues.get(c["number"], {}).get("title", "")}
                  for c in p.get("closingIssuesReferences") or []]
        prs.append({"number": p["number"], "title": p["title"], "url": p["url"],
                    "author": (p.get("author") or {}).get("login", ""), "draft": p.get("isDraft"),
                    "review": p.get("reviewDecision") or "", "created_ts": parse_ts(p["createdAt"]),
                    "closes": closes, "head": p.get("headRefOid")})
        prs[-1]["reviewer"] = rv = reviewer_state((data.get("reviews") or {}).get(p["number"], []),
                                                  p.get("headRefOid"))
        prs[-1]["needs_owner"] = needs_owner(rv, prs[-1]["author"])

    today = now.date()
    days = [today - dt.timedelta(days=i) for i in range(SPEND_DAYS)]
    per_day = {d: sum(s["daily"].get(d, 0.0) for s in sessions) for d in days}

    return {"repo": repo, "now": now, "idle_minutes": int(idle_after.total_seconds() // 60),
            "issue_titles": {n: i["title"] for n, i in issues.items()},
            "sessions": sessions, "prs": prs, "gov": gov,
            "spend": {"per_day": per_day, "today": per_day[today],
                      "unpriced": [s for s in sessions if s["cost"] is None]}}


TTL_RE = re.compile(r"^###\s*Time to live\s*\n+\s*(\S[^\n]*?)\s*$", re.M)


def time_to_live(body: str | None) -> str | None:
    """The 'Time to live' answer from a Governance question template body."""
    m = TTL_RE.search(body or "")
    return m.group(1) if m and m.group(1) != "_No response_" else None


TTL_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})(?:\s|$)")


def ttl_date(ttl: str | None) -> dt.date | None:
    """The date a 'Time to live' answer starts with, or None if it doesn't start with one.
    A note after the date ("2026-11-30 (the rulings' review date)") is allowed."""
    m = TTL_DATE_RE.match(ttl or "")
    try:
        return dt.date.fromisoformat(m.group(1)) if m else None
    except ValueError:
        return None


# ---------------------------------------------------------------- needs you (L5)

NEEDS_KINDS = ("blocked", "question", "pr", "idle", "over_cap")   # most urgent first


def needs_you(m: dict) -> list[dict]:
    """Everything waiting on the owner, most urgent first: the one list behind both the
    dashboard's first section and `swarm inbox`, so they can't disagree.

    Reads only build()'s model, which comes from public GitHub data (GOV-0002, GOV-0004).
    Within a kind, the longest waiting comes first, except that questions past their time
    to live come first among questions (oldest time to live first). Each item: kind, ref,
    title, url, detail, since, for session items session_url, and for a question past its
    time to live past_ttl.
    """
    repo, now, titles = m["repo"], m["now"], m["issue_titles"]

    def issue_url(n):
        return f"https://github.com/{repo}/issues/{n}"

    def session(s):
        return f"{s['role']} session {s['session_id'][:8]}"

    items = []
    for s in m["sessions"]:
        if s["status"] == "blocked":
            q = s["gov_question"]
            items.append({"kind": "blocked", "ref": f"#{q}", "title": titles.get(q, ""),
                          "url": issue_url(q), "session_url": issue_url(s["tracking_issue"]),
                          "detail": f"{session(s)} is blocked on it"
                                    + (f" (working on #{s['issue']})" if s["issue"] else ""),
                          "since": s["last_ts"]})
    for q in m["gov"]:
        if not q["waiting"]:
            # Only shows a lapse; the owner alone adds gov:lapsed (GOV-0006).
            d = ttl_date(q["ttl"])
            past = d if d and d < now.date() else None
            bits = [f"past time to live ({past})" if past
                    else f"time to live {q['ttl']}" if q["ttl"] else "no time to live given"]
            bits += q["labels"]
            items.append({"kind": "question", "ref": f"#{q['number']}", "title": q["title"],
                          "url": q["url"], "detail": ", ".join(bits), "since": q["created_ts"],
                          **({"past_ttl": past} if past else {})})
    for p in m["prs"]:
        if not p["draft"]:
            state = (p.get("needs_owner")
                     or p["review"].replace("_", " ").lower() or "awaiting review")
            closes = ", ".join(f"#{c['number']}" for c in p["closes"])
            items.append({"kind": "pr", "ref": f"PR #{p['number']}", "title": p["title"],
                          "url": p["url"],
                          "detail": state + (f", closes {closes}" if closes else ""),
                          "since": p["created_ts"]})
    for s in m["sessions"]:
        if s["status"] == "idle":
            items.append({"kind": "idle", "ref": session(s), "title": "",
                          "url": issue_url(s["tracking_issue"]),
                          "session_url": issue_url(s["tracking_issue"]),
                          "detail": f"no event since {ago(s['last_ts'], now)}"
                                    + (f", on #{s['issue']}" if s["issue"] else ""),
                          "since": s["last_ts"]})
    for s in m["sessions"]:
        if s.get("over_cap"):
            items.append({"kind": "over_cap", "ref": session(s), "title": "",
                          "url": issue_url(s["tracking_issue"]),
                          "session_url": issue_url(s["tracking_issue"]),
                          "detail": f"est. {spend.usd(s['cost'])}, cap {spend.usd(s['cap'])}"
                                    + (f", on #{s['issue']}" if s["issue"] else "")
                                    + "; warn only: swarm stop ends it (GOV-0008)",
                          "since": s["last_ts"], "over": s["cost"] / s["cap"]})
    far, far_date = dt.datetime.max.replace(tzinfo=dt.timezone.utc), dt.date.max
    # Over-cap sessions: furthest over first. Questions past their time to live: oldest
    # time to live first, ahead of other questions. Everything else: longest waiting first.
    items.sort(key=lambda i: (NEEDS_KINDS.index(i["kind"]), -i.get("over", 0),
                              i.get("past_ttl", far_date), i["since"] or far))
    return items


NEEDS_LABELS = {"blocked": "blocked", "question": "gov question", "pr": "PR to review",
                "idle": "idle session", "over_cap": "over cap"}
NEEDS_EMPTY = "Nothing is waiting on you."


def needs_line(item: dict, now: dt.datetime) -> str:
    """One item as plain text, without its link. The CLI and the page both show this."""
    title = f" {item['title']}" if item["title"] else ""
    since = (f" · {ago(item['since'], now)}"
             if item["since"] and item["kind"] not in ("idle", "over_cap") else "")
    return f"[{NEEDS_LABELS[item['kind']]}] {item['ref']}{title} · {item['detail']}{since}"


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
ol.inbox { margin:0; padding-left:24px; }
ol.inbox li { padding:4px 0; border-bottom:1px solid var(--line); }
ol.inbox li.k-blocked::marker { color:var(--blocked); font-weight:600; }
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
            f"<td class=\"num\">{esc(spend.usd(s['cost']))}"
            + (f"<br><span class=\"pill s-blocked\">over cap {esc(spend.usd(s['cap']))}</span>"
               if s.get("over_cap") else "") + "</td>"
            "</tr>")
    head = ("<tr><th>Status</th><th>Role</th><th>Current issue</th>"
            "<th>Last activity</th><th>Session</th><th class=\"num\">Spend (est.)</th></tr>")
    return f'<div class="scroll"><table>{head}{"".join(rows)}</table></div>'


def needs_section(m: dict) -> str:
    items = needs_you(m)
    if not items:
        return f'<h2>Needs you</h2><p class="muted">{esc(NEEDS_EMPTY)}</p>'
    lis = []
    for i in items:
        line = esc(needs_line(i, m["now"]))
        session = (f' · <a href="{esc(i["session_url"])}">session</a>'
                   if i.get("session_url") and i["session_url"] != i["url"] else "")
        lis.append(f'<li class="k-{i["kind"]}"><a href="{esc(i["url"])}">{line}</a>{session}</li>')
    return f'<h2>Needs you ({len(items)})</h2><ol class="inbox">{"".join(lis)}</ol>'


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
        needs_section(m),
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
    model = build(data, now, dt.timedelta(minutes=args.idle_minutes), caps=load_caps())
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(model), encoding="utf-8")
    live = sum(s["status"] != "stopped" for s in model["sessions"])
    print(f"wrote {out}: {live} live / {len(model['sessions'])} sessions, "
          f"{len(model['prs'])} open PRs, {len(model['gov'])} open gov questions")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
