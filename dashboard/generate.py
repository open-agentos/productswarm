#!/usr/bin/env python3
"""Render the swarm dashboard: static, read-only HTML pages (#401).

Reads, through `gh api` (in a swarm session that's ops/shims/gh acting as the role's App):
  - heartbeat events from the comments on `[heartbeat]` tracking issues (GOV-0003,
    heartbeat/SCHEMA.md). Only the GitHub copy is read, which never carries prompt
    text (GOV-0002); the local spool is not touched;
  - open PRs, the issues they close, and the reviewer App's reviews on each non-draft
    PR (GOV-0011's round count and Authority line);
  - open `gov:question` issues, `gov:lapsed` ones closed in the window, and
    governance/INDEX.md from the checkout (the governance section, #355).

Builds three pages in one look (layout.py), and copies the self-hosted fonts beside them:
  - index.html, the desk: on the floor (floor.py), open committees, and a pointer to the
    other two (#397 fills it);
  - operations.html: the needs-you list, sessions, open PRs, the Actions reviewer, v3
    progress and spend;
  - decisions.html: the governance section with the full decision log, and ended committees.
Stdlib only, no JavaScript, per the default in gov question #26.

    python3 dashboard/generate.py                 # writes dashboard/out/{index,operations,decisions}.html
    python3 dashboard/generate.py --out /tmp/x/index.html --days 7 --idle-minutes 15
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import committees
import floor
import ghql
import governance
import layout
import progress
import reviewer_runs
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


COMMENTS_BATCH = 25   # tracking issues per GraphQL query: about one rate-limit point each
COMMENTS_FIELD = ("i%d: issue(number: %d) { comments(first: 100) "
                  "{ totalCount nodes { body author { login __typename } } } }")


def tracking_comments(repo: str, numbers: list[int]) -> dict[int, list[dict]]:
    """Each tracking issue's comments in REST's shape ({"user": {"login"}, "body"}), oldest
    first: one GraphQL query per COMMENTS_BATCH issues, not one REST call per issue (#392).
    An issue with more than 100 comments, or one the query didn't return, falls back to REST."""
    out: dict[int, list[dict]] = {}
    for n, issue in ghql.batched(repo, numbers, COMMENTS_FIELD, COMMENTS_BATCH).items():
        nodes = ghql.complete((issue or {}).get("comments"))
        out[n] = (gh_items(f"repos/{repo}/issues/{n}/comments?per_page=100") if nodes is None else
                  [{"user": {"login": ghql.login(x.get("author"))}, "body": x.get("body") or ""}
                   for x in nodes])
    return out


def fetch(repo: str, now: dt.datetime, days: int, with_progress: bool = False,
          with_actions: bool = False, with_committees: bool = False) -> dict:
    """Everything the page needs, as plain API data. build() does the rest. `with_progress`
    also reads the v3 progress section's data (progress.py), `with_actions` the Actions
    reviewer section's (reviewer_runs.py), and `with_committees` the committee Discussions
    (committees.py, GraphQL). Only the page shows them, so swarm's snapshot() and the digest
    leave all three off and make no Actions or GraphQL calls; main() asks for them."""
    since = (now - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    issues: dict[int, dict] = {}
    for path in (f"repos/{repo}/issues?state=open&per_page=100",
                 f"repos/{repo}/issues?state=closed&since={since}&per_page=100"):
        for it in gh_items(path):
            if "pull_request" not in it:
                issues[it["number"]] = it
    comments = tracking_comments(repo, [s["issue"] for s in tracking_issues(issues.values())])
    prs = gh_json("pr", "list", "--repo", repo, "--state", "open", "--limit", "100", "--json",
                  "number,title,url,author,isDraft,createdAt,reviewDecision,closingIssuesReferences,"
                  "headRefOid")
    reviews = {p["number"]: gh_items(f"repos/{repo}/pulls/{p['number']}/reviews?per_page=100")
               for p in prs or [] if not p.get("isDraft")}
    try:
        index = governance.INDEX.read_text(encoding="utf-8")
    except OSError:
        index = None   # the section says so; the rest of the page still builds
    return {"repo": repo, "issues": list(issues.values()), "comments": comments, "prs": prs or [],
            "reviews": reviews, "index": index,
            "progress": progress.fetch(repo, gh_json) if with_progress else None,
            "actions": reviewer_runs.fetch(repo, now, reviews) if with_actions else None,
            "committees": committees.fetch(repo, gh_items, gh_json) if with_committees else None}


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


def unreviewed(p: dict) -> str | None:
    """"no reviewer review at <sha7>" for a builder-App PR with no reviewer-App review at
    its current head, else None (#332). reviewDecision can't show this: an owner approval
    sets it too. Three builder PRs were merged with no reviewer review (#200, #269, #275)."""
    rv, head = p.get("reviewer") or {}, p.get("head")
    if head and pr_role(p.get("author", "")) == "builder" and rv.get("at_head") is None:
        return f"no reviewer review at {head[:7]}"
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
          caps: dict[str, float] | None = None, window: int = DAYS) -> dict:
    repo = data["repo"]
    issues = {i["number"]: i for i in data["issues"]}
    open_issues = {n for n, i in issues.items() if i.get("state") == "open"}
    sessions, events_of = [], {}
    for s in tracking_issues(issues.values()):
        events = session_events(s, data["comments"].get(s["issue"], []), repo)
        d = derive(s, events, open_issues, now, idle_after)
        d["cap"] = (caps or {}).get(d["role"])
        d["over_cap"] = d["status"] != "stopped" and over_cap(d["cost"], d["cap"])
        sessions.append(d)
        events_of[d["session_id"]] = events
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
                        "fields": governance.question_fields(it.get("body"), labels),
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
            "sessions": sessions, "prs": prs,
            "floor": floor.build([(s, events_of[s["session_id"]]) for s in sessions], now), "gov": gov, "days": window,
            "governance": governance.build(data.get("index"), gov, data["issues"], now,
                                           now - dt.timedelta(days=window), parse_ts,
                                           time_to_live, ttl_date),
            "progress": progress.build(data["progress"]) if data.get("progress") else None,
            "reviewer_runs": reviewer_runs.build(
                data.get("actions"), [p for p in prs if not p["draft"] and unreviewed(p)], now),
            "committees": committees.build(data.get("committees")),
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
            state = (p.get("needs_owner") or unreviewed(p)
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


TITLE = "Swarm dashboard"


def render_desk(m: dict) -> str:
    """The desk (index.html): on the floor (#403), the open committees, and a pointer to the
    other pages. #397's later panels join it."""
    repo = m["repo"]
    committee = committees.render(m.get("committees"), repo, part="open")
    out = ["<h1>The desk</h1>",
           floor.render(m.get("floor"), repo),
           committee or '<p class="muted">No committee is sitting.</p>',
           '<p class="pointer">The needs-you list, sessions, open PRs, reviewer sweeps, v3 '
           'progress and spend are on <a href="operations.html">Operations</a>; the full '
           'decision log, open and lapsed gov questions and past committees are on '
           '<a href="decisions.html">Decisions</a>.</p>']
    return layout.page("index.html", TITLE, repo, stamp(m["now"]), "\n".join(out))


def render_operations(m: dict) -> str:
    """operations.html: what needs the owner, and the swarm's day-to-day running."""
    repo, now, titles = m["repo"], m["now"], m["issue_titles"]
    live = [s for s in m["sessions"] if s["status"] != "stopped"]
    stopped = [s for s in m["sessions"] if s["status"] == "stopped"]
    blocked = sum(s["status"] == "blocked" for s in live)
    ready = [p for p in m["prs"] if not p["draft"]]

    def tile(n: int, label: str, hot: bool = False) -> str:
        return f'<div class="{"hot" if hot and n else ""}"><b>{n}</b>{esc(label)}</div>'

    out = [
        f'<h1>Operations</h1><div class="muted">idle after {m["idle_minutes"]} min without an event</div>',
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

    out.append(reviewer_runs.render(m["reviewer_runs"], repo, now, ago, stamp))
    if m.get("progress"):
        out.append(progress.render(m["progress"], repo))

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
    return layout.page("operations.html", TITLE, repo, stamp(now), "\n".join(out))


def render_decisions(m: dict) -> str:
    """decisions.html: the governance section with the full decision log, and ended
    committees."""
    repo, now = m["repo"], m["now"]
    out = ["<h1>Decisions</h1>",
           governance.render(m["governance"], repo, now, m["days"], ago, stamp, full=True),
           committees.render(m.get("committees"), repo, part="ended")]
    return layout.page("decisions.html", TITLE, repo, stamp(now), "\n".join(o for o in out if o))


def render(m: dict) -> dict[str, str]:
    """Every page, by file name, in layout.PAGES order."""
    pages = {"index.html": render_desk, "operations.html": render_operations,
             "decisions.html": render_decisions}
    return {f: pages[f](m) for f, _ in layout.PAGES}


# ---------------------------------------------------------------- CLI

def default_repo() -> str | None:
    try:
        url = subprocess.run(["git", "-C", str(HERE), "remote", "get-url", "origin"],
                             capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    m = REPO_RE.search(url)
    return m.group(1) if m else None


# ---------------------------------------------------------------- staying inside the rate limit (#392)

# What one run needs, with headroom. Against this repo on 2026-11-04 (#392's PR), a page
# rebuild made 23 REST calls and 19 GraphQL queries (before #392: 258 and 9), and the digest
# 5 and 8. The workflow token's allowance is 1,000 an hour of each, shared with the digest.
PAGE_NEEDS = {"core": 80, "graphql": 50}
DIGEST_NEEDS = {"core": 30, "graphql": 30}
SPACING = dt.timedelta(minutes=5)       # a nudged rebuild waits this long after a published one
WORKFLOW = "dashboard.yml"
NUDGE_ACTOR = "github-actions[bot]"     # digest-nudge.yml's dispatches run as this actor


def low_allowance(needs: dict[str, int]) -> str | None:
    """Why there isn't enough rate-limit allowance left for a run, or None. `gh api rate_limit`
    doesn't count against the allowance. If it can't be read, the run goes ahead."""
    try:
        res = gh_json("api", "rate_limit")["resources"]   # type: ignore[index]
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return None
    for kind, need in needs.items():
        r = res.get(kind) or {}
        if isinstance(r.get("remaining"), int) and r["remaining"] < need:
            reset = dt.datetime.fromtimestamp(r.get("reset", 0), dt.timezone.utc)
            return (f"{kind} API allowance low ({r['remaining']} of {r.get('limit')} left, a run needs "
                    f"about {need}; resets {stamp(reset)})")
    return None


def nudged(env=None) -> bool:
    """A workflow_dispatch from digest-nudge.yml, not a person's dispatch or the schedule."""
    env = os.environ if env is None else env
    actor = env.get("GITHUB_TRIGGERING_ACTOR") or env.get("GITHUB_ACTOR")
    return env.get("GITHUB_EVENT_NAME") == "workflow_dispatch" and actor == NUDGE_ACTOR


PUBLISH_STEP = "deploy-pages"            # the step of a dashboard.yml run that publishes
LOOK_BACK = 5                           # successful runs checked for the last one that published


def last_published(repo: str) -> dt.datetime | None:
    """When dashboard.yml last published: the newest of the last LOOK_BACK successful runs whose
    deploy step succeeded. A run that skipped (spacing or allowance) also ends `success` once
    its upload and deploy steps are conditional, so a run's own status isn't enough. One call
    for the runs, then one jobs call per run until a published one; None if none of them did."""
    runs = gh_json("api", f"repos/{repo}/actions/workflows/{WORKFLOW}/runs?status=success&per_page={LOOK_BACK}")
    for run in runs["workflow_runs"][:LOOK_BACK]:   # type: ignore[index]
        jobs = gh_json("api", f"repos/{repo}/actions/runs/{run['id']}/jobs")
        for job in jobs["jobs"]:   # type: ignore[index]
            for step in job.get("steps") or []:
                if PUBLISH_STEP in (step.get("name") or "") and step.get("conclusion") == "success":
                    return parse_ts(step.get("completed_at") or run["updated_at"])
    return None


def too_soon(repo: str, now: dt.datetime) -> str | None:
    """Why a nudged rebuild should wait, or None: dashboard.yml last published less than
    SPACING ago. Measured from a published run, not a skipped one, so a stream of nudges can't
    keep restarting the wait. If the Actions API can't be read, the rebuild runs."""
    try:
        last = last_published(repo)
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError):
        return None
    if last and now - last < SPACING:
        return f"last published {ago(last, now)}; nudged rebuilds wait {SPACING.seconds // 60} minutes"
    return None


STATE_FILE = "state.json"   # the page's data, written beside it (state.py, #400)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Render the swarm dashboard's static HTML pages.")
    ap.add_argument("--repo", help="owner/name (default: this checkout's origin)")
    ap.add_argument("--out", default=str(HERE / "out" / "index.html"),
                    help="the desk page; the other pages and fonts/ go beside it")
    ap.add_argument("--days", type=int, default=DAYS, help="include sessions closed in the last N days")
    ap.add_argument("--idle-minutes", type=int, default=IDLE_MINUTES,
                    help="a live session is idle after this long without an event")
    args = ap.parse_args(argv)

    repo = args.repo or default_repo()
    if not repo:
        print("generate.py: can't tell the repo; pass --repo owner/name", file=sys.stderr)
        return 2
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    # Exit 0 without writing the page: the last good page stays up and the run isn't a failure.
    skip = (too_soon(repo, now) if nudged() else None) or low_allowance(PAGE_NEEDS)
    if skip:
        print(f"generate.py: skipped, not published: {skip}")
        return 0
    try:
        data = fetch(repo, now, args.days, with_progress=True, with_actions=True,
                     with_committees=True)
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError) as e:
        print(f"generate.py: {e}", file=sys.stderr)
        return 1
    model = build(data, now, dt.timedelta(minutes=args.idle_minutes), caps=load_caps(),
                  window=args.days)
    import state   # here, not at the top: state imports this module
    data_json = json.dumps(state.state(model), indent=1) + "\n"
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    pages = render(model)
    layout.copy_fonts(out.parent)   # before the pages, so a published page never lacks them
    for name, page in pages.items():
        (out if name == "index.html" else out.parent / name).write_text(page, encoding="utf-8")
    (out.parent / STATE_FILE).write_text(data_json, encoding="utf-8")   # #400
    live = sum(s["status"] != "stopped" for s in model["sessions"])
    others = ", ".join(n for n in pages if n != "index.html")
    print(f"wrote {out}, {others}, {STATE_FILE} and {layout.FONTS_DIR}/ beside it: "
          f"{live} live / {len(model['sessions'])} sessions, "
          f"{len(model['prs'])} open PRs, {len(model['gov'])} open gov questions")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
