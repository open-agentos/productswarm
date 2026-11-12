"""The Bridge page (bridge.html, #926, under M3 #685): the Bridge home from the owner's
"v5 · the bridge" mock-up, read-only.

It is built only from the model generate.build() already makes, so it adds no API calls:

  1. Status strip: the open Goals and Areas (plan.py) and how many have a not-go sub-issue;
     agents working (floor.py's cards); decisions waiting (section 2's count); and authority
     used in the last 24 hours (grants.py: the merger's calls).
  2. Decisions waiting, in owner amber: open gov:questions the owner hasn't ruled, with their
     time to live; sessions blocked on a question; PRs the merger left for the owner, or that
     GOV-0011 hands to the owner; and the asks in today's daily report (report.py). Each links
     to where it is answered on GitHub. No buttons: writes are #752's.
  3. Reports, newest first, each with its agent: today's daily report (or a flag when it's
     late), and PRs a role's App merged in the last 7 days (the merged PRs questions.py's
     search already reads): SHIPPED, or DELIVERED when the PR closes a Brief in the plan.
  4. In flight: each open Goal and Area with done of total direct sub-issues and a dot for
     its state.
  5. Orders received: the owner's acts in the repo's events (activity.py), newest first,
     with chair "GitHub".

A left column links Bridge, Commissions and Agents (today's plan on the desk and the
operations page, until those pages are built), then the other pages. No script; complete
with JavaScript off; fits a phone's width. No spend (GOV-0033). Stdlib only.
"""
from __future__ import annotations

import datetime as dt
import re

import activity
import layout
from layout import esc
from report import inline

BOT_RE = re.compile(r"\Aproductswarm-([a-z0-9-]+)\[bot\]\Z")
CLOSES_RE = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.I)
REPORT_AGENT = "planner"          # the lead writes the daily report (#529)
REPORTS_DAYS = 7                  # merged PRs shown under Reports
ORDERS_MAX = 20                   # owner's acts shown; the rest are counted
CHAIR = "GitHub"                  # where every order is given today (#760: orders stay GitHub acts)


# ---------------------------------------------------------------- model

def _rows(scope: dict):
    """Every open sub-issue row under a scope, both levels plan.py lists."""
    for r in scope.get("subs") or []:
        yield r
        yield from r.get("children") or []


def _flagged(trouble: dict | None) -> set[str]:
    """URLs of Goals and Areas the trouble report flags: a missed date or a failing criterion."""
    out = set()
    for s in (trouble or {}).get("scopes") or []:
        if s.get("date_missed") or any(p.get("status") == "failing" for p in s.get("progress") or []):
            out.add(s.get("url"))
    return out


def scope_state(scope: dict, flagged: set[str]) -> tuple[str, str]:
    """(dot class, words) for one Goal or Area. Red only for a flag (#397)."""
    rows = list(_rows(scope))
    if scope.get("url") in flagged:
        return "red", "flagged in today's trouble report"
    if any(r["status"]["kind"] == "not_go" for r in rows):
        return "owner", "a sub-issue isn't go"
    if any(r["status"]["kind"] == "unknown" for r in rows) or scope.get("open") is None:
        return "quiet", "status unknown"
    if any(r["status"]["kind"] == "go" for r in rows):
        return "agent", "moving"
    if rows:
        return "ink", "waiting on blockers"
    return "quiet", "nothing open"


def decisions(m: dict, ttl_date=None) -> list[dict]:
    """Section 2's items, each {"kind", "ref", "title", "url", "detail"}, in the order the
    issue lists them. `ttl_date` is generate.ttl_date (passed in: generate imports this module)."""
    if ttl_date is None:
        from generate import ttl_date
    repo = m["repo"]
    base = f"https://github.com/{repo}"
    titles = m.get("issue_titles") or {}
    out = []
    for q in m.get("gov") or []:
        if "gov:ruled" in q["labels"]:
            continue
        d = ttl_date(q.get("ttl"))
        past = d is not None and d < m["now"].date()
        out.append({"kind": "question", "ref": f"#{q['number']}", "title": q["title"], "url": q["url"],
                    "detail": (f"past its time to live ({q['ttl']})" if past
                               else f"time to live {q['ttl']}" if q.get("ttl") else "no time to live given")})
    for s in m.get("sessions") or []:
        if s["status"] == "blocked" and not s.get("never_acted") and s.get("gov_question"):
            n = s["gov_question"]
            out.append({"kind": "blocked", "ref": f"#{n}", "title": titles.get(n, ""),
                        "url": f"{base}/issues/{n}",
                        "detail": f"{s['role']} session is blocked on it"
                                  + (f" (working on #{s['issue']})" if s.get("issue") else "")})
    left = {}
    for c in (m.get("grants") or {}).get("calls") or []:
        if c["group"] == "left":
            left[c["number"]] = {"kind": "pr", "ref": f"PR #{c['number']}", "title": c.get("title") or "",
                                 "url": c.get("link") or f"{base}/pull/{c['number']}",
                                 "detail": f"the merger left it for you: {c['reason']}"}
    for p in m.get("prs") or []:
        if p.get("needs_owner") and p["number"] not in left:
            left[p["number"]] = {"kind": "pr", "ref": f"PR #{p['number']}", "title": p["title"],
                                 "url": p["url"], "detail": f"{p['needs_owner']} (GOV-0011)"}
    out += [left[n] for n in sorted(left)]
    rep = (m.get("report") or {}).get("report")
    for a in (rep or {}).get("asks") or []:
        url = f"{base}/issues/{a['issue']}" if a.get("issue") else rep.get("url")
        out.append({"kind": "ask", "ref": a.get("lead") or "Ask", "title": a.get("text") or "",
                    "url": url, "detail": "asked in today's daily report"})
    return out


def briefs(plan: dict | None, trees: dict | None) -> set[int]:
    """Issue numbers the plan's trees type as Brief, open or closed."""
    out = set()
    for t in (trees or {}).values():
        for a in ((t or {}).get("subIssues") or {}).get("nodes") or []:
            for x in [a, *(((a or {}).get("subIssues") or {}).get("nodes") or [])]:
                if x and (x.get("issueType") or {}).get("name") == "Brief":
                    out.add(x.get("number"))
    return out


def shipped(merged: list[dict] | None, brief_numbers: set[int], now: dt.datetime) -> list[dict]:
    """PRs a role's App merged in the last REPORTS_DAYS days, newest first: each {"number",
    "title", "url", "role", "time", "word"}. `merged` is the search items questions.py reads."""
    out = []
    for it in merged or []:
        login = (it.get("user") or {}).get("login") or ""
        role = BOT_RE.match(login)
        t = activity.parse_ts((it.get("pull_request") or {}).get("merged_at") or it.get("closed_at"))
        if not role or not t or not (now - dt.timedelta(days=REPORTS_DAYS) <= t <= now):
            continue
        closes = {int(n) for n in CLOSES_RE.findall(it.get("body") or "")}
        out.append({"number": it.get("number"), "title": it.get("title") or "", "url": it.get("html_url"),
                    "role": role.group(1), "time": t,
                    "word": "DELIVERED" if closes & brief_numbers else "SHIPPED"})
    out.sort(key=lambda x: (x["time"], x["number"] or 0), reverse=True)
    return out


def orders(act: dict | None, owner: str | None, repo: str) -> list[dict] | None:
    """The owner's acts in the events read, newest first: {"time", "text", "verb", "ref",
    "extra", "link"}. None when the events or the owner couldn't be read."""
    events = (act or {}).get("events")
    if events is None or not owner:
        return None
    out = []
    for e in events:
        t = activity.parse_ts(e.get("created_at"))
        if t and activity.by(e, owner) and not activity.watcher_edit(e):
            out.append({"time": t, **activity.describe(e, repo)})
    out.sort(key=lambda x: x["time"], reverse=True)
    return out


def build(m: dict, merged: list[dict] | None = None, trees: dict | None = None,
          owner: str | None = None, ttl_date=None) -> dict:
    """Everything the page shows, from generate.build()'s model plus the merged-PR search items
    and the plan's trees that build() reads but doesn't keep."""
    plan = m.get("plan")
    flagged = _flagged(m.get("trouble") if isinstance(m.get("trouble"), dict) else None)
    scopes = []
    for s in (plan or {}).get("scopes") or []:
        dot, words = scope_state(s, flagged)
        done, n_open = s.get("done"), s.get("open")
        scopes.append({"number": s["number"], "kind": s["kind"], "lead": s.get("lead"),
                       "title": s.get("title"), "url": s.get("url"), "done": done,
                       "total": None if done is None or n_open is None else done + n_open,
                       "not_go": any(r["status"]["kind"] == "not_go" for r in _rows(s)),
                       "dot": dot, "state": words})
    floor = m.get("floor") or {}
    grants = m.get("grants")
    dec = decisions(m, ttl_date)
    return {"plan_read": bool(plan and plan.get("read")), "scopes": scopes,
            "commissions": sum(len(list(_rows(s))) for s in (plan or {}).get("scopes") or [])
                           if plan and plan.get("read") else None,
            "working": len(floor.get("cards") or []) if m.get("floor") is not None else None,
            "agents": (len(floor.get("cards") or []) + len(floor.get("idle") or []))
                      if m.get("floor") is not None else None,
            "decisions": dec,
            "authority": len(grants["calls"]) if grants and grants.get("read") else None,
            "report": m.get("report"),
            "shipped": shipped(merged, briefs(plan, trees), m["now"]) if merged is not None else None,
            "orders": orders(m.get("activity"), owner, m["repo"])}


# ---------------------------------------------------------------- page

def _n(x) -> str:
    return "?" if x is None else str(x)


def _hm(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%H:%M")


def _when(t: dt.datetime) -> str:
    u = t.astimezone(dt.timezone.utc)
    return (f'<time class="stamp" datetime="{u:%Y-%m-%dT%H:%M:%SZ}" title="{u:%Y-%m-%d %H:%M UTC}">'
            f'{u:%m-%d %H:%M}</time>')


def strip(b: dict) -> str:
    ng = sum(s["not_go"] for s in b["scopes"])
    plan = ("Goals and Areas open" + (f", {ng} with a not-go sub-issue" if ng else "")
            if b["plan_read"] else "plan not read")
    cells = [("plan", _n(len(b["scopes"]) if b["plan_read"] else None), plan, ng > 0),
             ("working", _n(b["working"]), "agents working", False),
             ("decisions", str(len(b["decisions"])), "decisions waiting", bool(b["decisions"])),
             ("authority", _n(b["authority"]), "merger calls in 24 hours", False)]
    return ('<section class="strip" aria-label="Status">'
            + "".join(f'<div class="{k}{" hot" if hot else ""}"><b>{esc(v)}</b> {esc(t)}</div>'
                      for k, v, t, hot in cells) + "</section>")


def decisions_section(b: dict) -> str:
    out = ["<h2>Decisions waiting</h2>"]
    if not b["decisions"]:
        out.append('<p class="muted">Nothing is waiting on you.</p>')
        return '<section class="decide">' + "".join(out) + "</section>"
    labels = {"question": "question", "blocked": "blocked", "pr": "PR", "ask": "ask"}
    out.append('<ol class="decide">')
    for d in b["decisions"]:
        title = f" {esc(d['title'])}" if d["title"] else ""
        out.append(f'<li class="k-{esc(d["kind"])}"><span class="tag">{esc(labels[d["kind"]])}</span> '
                   f'<a href="{esc(d["url"])}">{esc(d["ref"])}</a>{title}'
                   f' <span class="muted">· {esc(d["detail"])}</span></li>')
    out.append("</ol>")
    return '<section class="decide">' + "".join(out) + "</section>"


def _report_line(r: dict | None) -> str | None:
    """Today's daily report as one Reports entry, or a flag when it's due, late or unread."""
    if r is None:
        return None
    agent = f'<span class="agent">{REPORT_AGENT}</span>'
    if r["state"] == "posted":
        p = r["report"]
        return (f'<li><span class="word">REPORTED</span> {agent} <a href="{esc(p["url"])}">'
                f'{inline(p["line"])}</a> {_when(p["posted"])}</li>')
    due = f" It was due at {r['daily_at']:%H:%M}." if r.get("daily_at") else ""
    words = {"late": f"<b>No report yet today.</b>{esc(due)}",
             "due": "Today's report is due" + (f" at {r['daily_at']:%H:%M}" if r.get("daily_at") else "") + ".",
             "weekend": "No report on weekends.",
             "unread": f"Couldn't read #{esc(r['issue'])}; the report may be there.",
             "unset": "No report issue is set in swarm.toml."}[r["state"]]
    cls = "flag" if r["state"] in ("late", "unread") else "muted"
    return f'<li class="{cls}"><span class="word">DAILY</span> {agent} {words}</li>'


def reports_section(b: dict) -> str:
    out = ["<h2>Reports</h2>", '<ol class="reports">']
    line = _report_line(b["report"])
    if line:
        out.append(line)
    if b["shipped"] is None:
        out.append('<li class="muted">Merged PRs couldn\'t be read.</li>')
    else:
        for x in b["shipped"]:
            out.append(f'<li><span class="word{" brief" if x["word"] == "DELIVERED" else ""}">{x["word"]}</span> '
                       f'<span class="agent">{esc(x["role"])}</span> '
                       f'<a href="{esc(x["url"])}">PR #{esc(x["number"])}</a> {esc(x["title"])} {_when(x["time"])}</li>')
        if not b["shipped"]:
            out.append(f'<li class="muted">No PR merged by a role\'s App in the last {REPORTS_DAYS} days.</li>')
    out.append("</ol>")
    return '<section class="reports">' + "".join(out) + "</section>"


def flight_section(b: dict) -> str:
    out = ["<h2>In flight</h2>"]
    if not b["plan_read"]:
        out.append('<p class="muted">Couldn\'t read the plan from GitHub.</p>')
    elif not b["scopes"]:
        out.append('<p class="muted">No plan: the owner has no open Goal or Area.</p>')
    else:
        out.append('<ul class="flight">')
        for s in b["scopes"]:
            count = (f'{s["done"]} of {s["total"]} done' if s["total"] is not None else "sub-issues not read")
            lead = f'<span class="mono">{esc(s["lead"])}</span> ' if s.get("lead") else ""
            out.append(f'<li><span class="dot {esc(s["dot"])}" title="{esc(s["state"])}"></span>'
                       f'{lead}<a href="{esc(s["url"])}">{esc(s["title"])}</a> '
                       f'<span class="muted">{esc(s["kind"])} · <span class="num">{esc(count)}</span>'
                       f' · {esc(s["state"])}</span></li>')
        out.append("</ul>")
    return '<section class="flight">' + "".join(out) + "</section>"


def orders_section(b: dict) -> str:
    out = ["<h2>Orders received</h2>"]
    o = b["orders"]
    if o is None:
        out.append('<p class="muted">Couldn\'t read the owner\'s acts from the repo\'s events.</p>')
    elif not o:
        out.append('<p class="muted">No acts by the owner in the events read.</p>')
    else:
        out.append('<ol class="orders">')
        for x in o[:ORDERS_MAX]:
            what = esc(x["verb"])
            if x["ref"]:
                what += f' <a href="{esc(x["link"])}">{esc(x["ref"])}</a>'
            if x["extra"]:
                what += f" <code>{esc(x['extra'])}</code>"
            if not x["ref"]:
                what = f'<a href="{esc(x["link"])}">{what}</a>'
            out.append(f'<li>{_when(x["time"])} <span class="chair">{CHAIR}</span> {what}</li>')
        out.append("</ol>")
        if len(o) > ORDERS_MAX:
            out.append(f'<p class="muted">and {len(o) - ORDERS_MAX} more in the events read.</p>')
    return '<section class="orders">' + "".join(out) + "</section>"


def rail(b: dict) -> str:
    """The left column: Bridge, Commissions and Agents (today's plan and operations pages until
    those pages are built), then the other pages."""
    links = ['<span class="here" aria-current="page">Bridge</span>',
             f'<a href="index.html">Commissions <span class="num">{esc(_n(b["commissions"]))}</span></a>',
             f'<a href="operations.html">Agents <span class="num">{esc(_n(b["agents"]))}</span></a>']
    others = [f'<a href="{esc(f)}">{esc(n)}</a>' for f, n in layout.PAGES if f != "bridge.html"]
    return (f'<nav class="rail" aria-label="Bridge">{"".join(links)}'
            f'<span class="sep"></span>{"".join(others)}</nav>')


def body(b: dict) -> str:
    return (f'<div class="bridge">{rail(b)}<div class="deck"><h1>The bridge</h1>{strip(b)}'
            f'{decisions_section(b)}{reports_section(b)}{flight_section(b)}{orders_section(b)}'
            "</div></div>")
