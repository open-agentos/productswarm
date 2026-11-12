"""The Bridge (#926, under M3 #685): the owner's "v5 · the bridge" home, read-only.

One page, `bridge.html`, built only from what the desk already reads, so it costs no API
calls of its own (the merged PRs come from the closed items generate.fetch() already reads):

  - Status: open Goals and Areas and how many are flagged; agents working, from the floor;
    decisions waiting; authority used in `swarm trouble`'s window.
  - Decisions waiting (owner amber): what `swarm trouble` says waits on the owner, open gov
    questions, sessions blocked on one, PRs the merger left for the owner or that GOV-0011
    hands to the owner, and today's daily report's asks (as #928 collected them), each once,
    with its age or Time to live. Each links to
    where it's answered on GitHub: there are no buttons until the desk can write (#752).
  - Reports, newest first, each with its agent: today's daily report (a flag when it's late),
    what `swarm trouble` says is stuck (a flag), and PRs a role's App had merged in the last
    REPORT_DAYS days (shipped, or delivered for a Brief).
  - In flight: each open Goal and Area, its criteria met of total, and a dot: red if flagged,
    amber if it waits on the owner, blue otherwise.
  - Orders received: the owner's acts on GitHub from the repo's events, newest first. The
    chair is "GitHub" until a chair can send orders (#760: orders stay the owner's acts).

A scope is flagged when something under it is stuck, a criterion is failing, or its date is
missed. Spend isn't shown: GOV-0033 sets no engine total, and the desk is public.

No script; complete with JavaScript off; fits a phone's width. Stdlib only.
"""
from __future__ import annotations

import datetime as dt
import re

import activity
import layout
from layout import esc
from report import inline

FILE = "bridge.html"
REPORT_DAYS = 7          # merged PRs shown as reports
MAX_REPORTS = 12
MAX_ORDERS = 8
MAX_DECISIONS = 24

GH_RE = re.compile(r"https://github\.com/[^\s\"'<>]*")
# Owner events that are acts, not noise: branch creation and deletion are left out.
ORDER_TYPES = ("IssuesEvent", "IssueCommentEvent", "PullRequestEvent", "PullRequestReviewEvent",
               "PullRequestReviewCommentEvent", "PushEvent")
# Two letters per role, for the report's badge; the lead (planner) is drawn solid.
BADGE = {"planner": "PL", "builder": "BU", "reviewer": "RV", "analyst": "AN", "designer": "DS",
         "merger": "MG", "watch": "WA"}
LEAD = "planner"
ROLE_RE = re.compile(r"(?:app/)?productswarm-([a-z0-9-]+?)(?:\[bot\])?")


# ---------------------------------------------------------------- the model

def _ts(s) -> dt.datetime | None:
    if isinstance(s, dt.datetime):
        return s
    try:
        t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def role_of(login: str | None) -> str | None:
    m = ROLE_RE.fullmatch(login or "")
    return m.group(1) if m else None


def _scopes(trouble: dict | None) -> list[dict]:
    return [s for s in (trouble or {}).get("scopes") or [] if isinstance(s, dict)]


def flagged(s: dict) -> bool:
    return bool(s.get("stuck") or s.get("date_missed")
                or any(c.get("status") == "failing" for c in s.get("progress") or []))


def _short(ref: str | None) -> str:
    """"o/r#100" → "#100"."""
    return "#" + ref.rsplit("#", 1)[1] if ref and "#" in ref else (ref or "")


def lead(title: str | None) -> str:
    """"M3" from "M3: The Desk shows ..."."""
    m = re.match(r"^(\S{1,12}):\s", title or "")
    return m.group(1) if m else ""


def _num(ref: str | None) -> int | None:
    n = re.search(r"#(\d+)\b", ref or "")
    return int(n.group(1)) if n else None


def decisions(m: dict) -> list[dict]:
    """What waits on the owner, each issue or PR once, oldest first (asks with no age last):
    `swarm trouble`'s waiting items (each scope's, then those under none); open gov questions
    not ruled; sessions blocked on a question; PRs the merger left for the owner in its last
    24 hours of calls, or that GOV-0011 hands to the owner; and the asks in today's daily
    report."""
    repo = m["repo"]
    base = f"https://github.com/{repo}"
    prs = {p["number"]: p for p in m.get("prs") or []}
    titles = {**(m.get("issue_titles") or {}), **{n: p.get("title") for n, p in prs.items()}}
    out, seen = [], set()

    def add(n, d):
        if n is not None and n in seen:
            return
        if n is not None:
            seen.add(n)
        out.append({"ttl": None, "why": "", **d})

    t = m.get("trouble") or {}
    for s in [*_scopes(t), {"waiting": (t.get("outside") or {}).get("waiting") or []}]:
        for x in s.get("waiting") or []:
            if not isinstance(x, dict):
                continue
            n = _num(x.get("ref"))
            title = titles.get(n) if n is not None else None
            add(n, {"scope": lead(s.get("title")) or _short(s.get("ref")) or "no Goal",
                    "ref": x.get("ref") or "", "url": x.get("url"),
                    "title": title or x.get("reason") or "", "why": x.get("reason") if title else "",
                    "since": _ts(x.get("since"))})
    for q in m.get("gov") or []:
        if q.get("waiting") or "gov:ruled" in (q.get("labels") or []):
            continue
        add(q["number"], {"scope": "gov question", "ref": f"#{q['number']}", "url": q.get("url"),
                          "title": q.get("title") or "", "since": _ts(q.get("created_ts")), "ttl": q.get("ttl")})
    for s in m.get("sessions") or []:
        if s.get("status") == "blocked" and not s.get("never_acted") and s.get("gov_question"):
            n = s["gov_question"]
            add(n, {"scope": "gov question", "ref": f"#{n}", "url": f"{base}/issues/{n}",
                    "title": titles.get(n) or "",
                    "why": f"{s.get('role')} session is blocked on it"
                           + (f" (working on #{s['issue']})" if s.get("issue") else ""),
                    "since": _ts(s.get("last_ts"))})
    for c in (m.get("grants") or {}).get("calls") or []:
        if c.get("group") == "left":
            n = c["number"]
            add(n, {"scope": "merger", "ref": f"PR #{n}", "url": c.get("link") or f"{base}/pull/{n}",
                    "title": c.get("title") or titles.get(n) or "", "why": f"left for you: {c.get('reason')}",
                    "since": _ts((prs.get(n) or {}).get("created_ts")) or _ts(c.get("time"))})
    for n, p in prs.items():
        if p.get("needs_owner"):
            add(n, {"scope": "review", "ref": f"PR #{n}", "url": p.get("url"), "title": p.get("title") or "",
                    "why": f"{p['needs_owner']} (GOV-0011)", "since": _ts(p.get("created_ts"))})
    rep = (m.get("report") or {}).get("report") or {}
    for a in rep.get("asks") or []:
        n = a.get("issue")
        add(n, {"scope": "daily report", "ref": f"#{n}" if n else "Ask",
                "url": f"{base}/issues/{n}" if n else rep.get("url"),
                "title": " ".join(x for x in (a.get("lead"), a.get("text")) if x).replace("**", ""),
                "why": "asked in today's daily report", "since": None})
    far = dt.datetime.max.replace(tzinfo=dt.timezone.utc)
    return sorted(out, key=lambda d: d["since"] or far)


def reports(m: dict) -> list[dict]:
    """The crew's reports, newest first: today's daily report, what's stuck, and merged PRs."""
    now, out = m["now"], []
    r = m.get("report") or {}
    if r.get("state") == "posted" and r.get("report"):
        rep = r["report"]
        asks = len(rep.get("asks") or [])
        out.append({"kind": "report", "role": LEAD, "time": _ts(rep.get("posted")), "scope": "daily",
                    "head": rep.get("line") or "Daily report", "url": rep.get("url"), "md": True,
                    "sub": f"{asks} ask{'s' if asks != 1 else ''} of you" if asks else "No asks of you."})
    elif r.get("state") == "late":
        out.append({"kind": "flag", "role": LEAD, "time": now, "scope": "daily",
                    "head": "No daily report yet today", "url": None, "md": False,
                    "sub": "It was due at " + (f"{r['daily_at']:%H:%M}" if r.get("daily_at") else "its usual time") + "."})
    t = m.get("trouble") or {}
    for s in [*_scopes(t), {"title": "", "ref": "", "stuck": (t.get("outside") or {}).get("stuck") or []}]:
        for x in s.get("stuck") or []:
            if isinstance(x, dict):
                out.append({"kind": "flag", "role": "watch", "time": _ts(x.get("since")),
                            "scope": lead(s.get("title")) or _short(s.get("ref")) or "no Goal",
                            "head": f"{x.get('ref') or ''} is stuck", "url": x.get("url"), "md": False,
                            "sub": (x.get("reason") or "") + "."})
    since = now - dt.timedelta(days=REPORT_DAYS)
    for p in m.get("merged") or []:
        role, when = role_of(p.get("author")), _ts(p.get("merged_at"))
        if not role or not when or when < since:
            continue
        brief = (p.get("title") or "").lower().startswith("brief")
        out.append({"kind": "delivered" if brief else "shipped", "role": role, "time": when,
                    "scope": f"PR #{p.get('number')}", "head": p.get("title") or "", "url": p.get("url"),
                    "md": False, "sub": ""})
    epoch = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    return sorted(out, key=lambda x: x["time"] or epoch, reverse=True)[:MAX_REPORTS]


def in_flight(m: dict) -> list[dict]:
    """Each open Goal and Area: criteria met of total, and its state."""
    out = []
    for s in _scopes(m.get("trouble")):
        crit = s.get("progress") or []
        state = "flagged" if flagged(s) else "waiting" if s.get("waiting") else "running"
        out.append({"lead": lead(s.get("title")), "title": re.sub(r"^\S{1,12}:\s+", "", s.get("title") or ""),
                    "url": s.get("url"), "type": s.get("type"), "state": state,
                    "met": sum(c.get("status") == "met" for c in crit), "total": len(crit)})
    if out or (m.get("trouble") or {}).get("scopes") is not None:
        return out
    for s in (m.get("plan") or {}).get("scopes") or []:   # the trouble report wasn't read
        total = (s.get("open") or 0) + (s.get("done") or 0)
        out.append({"lead": s.get("lead"), "title": s.get("title"), "url": s.get("url"), "type": s.get("kind"),
                    "state": "running", "met": s.get("done") or 0, "total": total, "subs": True})
    return out


def orders(m: dict, owner: str | None) -> list[dict]:
    """The owner's acts on GitHub, newest first."""
    events = (m.get("activity") or {}).get("events") or []
    out = []
    for e in events:
        if (e.get("type") not in ORDER_TYPES or not activity.by(e, owner) or activity.watcher_edit(e)):
            continue
        t = activity.parse_ts(e.get("created_at"))
        if t is None:
            continue
        d = activity.describe(e, m["repo"])
        out.append({"time": t, "verb": d["verb"], "ref": d["ref"], "extra": d["extra"], "link": d["link"]})
    return sorted(out, key=lambda o: o["time"], reverse=True)[:MAX_ORDERS]


def build(m: dict, owner: str | None) -> dict:
    t = m.get("trouble") or {}
    scopes = _scopes(t)
    floor = m.get("floor") or {}
    live = [s for s in m.get("sessions") or [] if s.get("status") != "stopped" and not s.get("never_acted")]
    flights = in_flight(m)
    return {"now": m["now"], "repo": m["repo"], "trouble_error": t.get("error"),
            "commissions": len(flights), "flagged": sum(flagged(s) for s in scopes),
            "working": len(floor.get("cards") or []), "agents": len(live),
            "idle": len(floor.get("idle") or []),
            "authority": sum(len(s.get("authority") or []) for s in [*scopes, t.get("outside") or {}]),
            "authority_hours": t.get("authority_hours") or 24,
            "decisions": decisions(m), "reports": reports(m), "flights": flights,
            "orders": orders(m, owner)}


# ---------------------------------------------------------------- drawing

def _a(url: str | None, text_html: str) -> str:
    """A link only to github.com; otherwise just the text."""
    if url and GH_RE.fullmatch(url):
        return f'<a href="{esc(url)}">{text_html}</a>'
    return text_html


def when(t: dt.datetime | None, now: dt.datetime) -> str:
    """"14:12" today, "Wed 14:12" this week, else "11-03" (UTC)."""
    if t is None:
        return "?"
    t = t.astimezone(dt.timezone.utc)
    if t.date() == now.date():
        return t.strftime("%H:%M")
    if (now - t) < dt.timedelta(days=6):
        return t.strftime("%a %H:%M")
    return t.strftime("%m-%d")


def age(t: dt.datetime | None, now: dt.datetime) -> str:
    if t is None:
        return "age unknown"
    h = (now - t).total_seconds() / 3600
    return f"{h / 24:.0f}d" if h >= 48 else f"{max(h, 0):.0f}h"


def _time(t: dt.datetime | None, now: dt.datetime) -> str:
    if t is None:
        return '<span class="mono muted">?</span>'
    iso = t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f'<time class="mono muted" datetime="{iso}">{esc(when(t, now))}</time>'


def _tile(label: str, big: str, sub: str, cls: str = "") -> str:
    return (f'<div class="br-tile {cls}"><span class="muted">{esc(label)}</span>'
            f'<span class="br-big">{big}</span><span class="br-sub">{sub}</span></div>')


def status_html(b: dict) -> str:
    f = b["flagged"]
    tiles = [
        _tile("Commissions", str(b["commissions"]),
              f'<span class="br-red">{f} flagged</span>' if f else "none flagged"),
        _tile("Agents working", f'{b["working"]} <small>of {b["agents"]}</small>',
              f'{b["idle"]} idle' if b["idle"] else "none idle"),
        _tile("Decisions waiting", str(len(b["decisions"])),
              f'oldest {esc(age(b["decisions"][0]["since"], b["now"]))}' if b["decisions"] else "nothing waits on you",
              "hot" if b["decisions"] else ""),
        _tile("Authority used", str(b["authority"]), f'last {b["authority_hours"]}h, on your grants'),
    ]
    return f'<section class="br-status" aria-label="Status">{"".join(tiles)}</section>'


def decisions_html(b: dict) -> str:
    head = ('<div class="br-colh"><h2 class="br-h owner">Decisions waiting</h2>'
            '<span class="muted">answered on GitHub for now</span></div>')
    ds = b["decisions"]
    if not ds:
        return f'<section class="br-decisions">{head}<p class="muted">Nothing is waiting on you.</p></section>'
    cards = []
    for d in ds[:MAX_DECISIONS]:
        due = f' · TIME TO LIVE {esc(d["ttl"]).upper()}' if d["ttl"] else ""
        cards.append(
            f'<div class="br-dec"><div class="br-kind owner">{esc(d["scope"]).upper()}'
            + (f' · WAITING {esc(age(d["since"], b["now"])).upper()}' if d["since"] else "")
            + f'{due}</div>'
            f'<div class="br-title">{_a(d["url"], esc(d["ref"]))} {esc(d["title"])}</div>'
            + (f'<div class="muted">{inline(d["why"][:1].upper() + d["why"][1:].rstrip("."))}.</div>' if d["why"] else "")
            + f'<div>{_a(d["url"], "Answer on GitHub")}</div></div>')
    more = (f'<p class="muted">And {len(ds) - MAX_DECISIONS} more on '
            f'<a href="operations.html">Operations</a>.</p>' if len(ds) > MAX_DECISIONS else "")
    return f'<section class="br-decisions">{head}<div class="br-grid">{"".join(cards)}</div>{more}</section>'


KIND_WORD = {"report": "REPORT", "flag": "FLAG", "shipped": "SHIPPED", "delivered": "DELIVERED"}


def reports_html(b: dict) -> str:
    head = ('<div class="br-colh"><h2 class="br-h">Reports</h2>'
            '<span class="muted">from the crew, newest first</span></div>')
    if not b["reports"]:
        return (f'<section class="br-reports">{head}<p class="muted">No reports in the last '
                f'{REPORT_DAYS} days.</p></section>')
    rows = []
    for r in b["reports"]:
        badge = BADGE.get(r["role"], (r["role"] or "?")[:2].upper())
        solid = " lead" if r["role"] == LEAD else ""
        kind = KIND_WORD[r["kind"]]
        kind = f'<span class="br-red">{kind}</span>' if r["kind"] == "flag" else kind
        head_html = inline(r["head"]) if r["md"] else esc(r["head"])
        sub = f'<div class="muted">{esc(r["sub"])}</div>' if r["sub"] else ""
        rows.append(
            f'<div class="br-rep"><span class="br-av{solid}" aria-hidden="true">{esc(badge)}</span>'
            f'<div class="br-body"><div class="br-kind">{kind} · {esc((r["role"] or "").upper())} · '
            f'{_time(r["time"], b["now"])} · {esc(r["scope"]).upper()}</div>'
            f'<div class="br-title">{_a(r["url"], head_html)}</div>{sub}</div></div>')
    return f'<section class="br-reports">{head}{"".join(rows)}</section>'


DOT = {"flagged": "red", "waiting": "owner", "running": "agent"}
STATE_WORD = {"flagged": "flagged", "waiting": "waits on you", "running": "running"}


def flights_html(b: dict) -> str:
    head = ('<div class="br-colh"><h2 class="br-h">In flight</h2>'
            '<a class="muted" href="index.html">The plan</a></div>')
    if not b["flights"]:
        return f'<section class="br-flight">{head}<p class="muted">No open Goal or Area.</p></section>'
    rows = []
    for f in b["flights"]:
        lead_html = f'<span class="mono">{esc(f["lead"])}</span> ' if f["lead"] else ""
        unit = "sub-issues done" if f.get("subs") else "criteria met"
        count = f'{f["met"]}/{f["total"]} {unit}' if f["total"] else "no criteria"
        rows.append(f'<div class="br-row"><span class="br-dot {DOT[f["state"]]}" aria-hidden="true"></span>'
                    f'<span class="br-grow">{lead_html}{_a(f["url"], esc(f["title"]))}'
                    f'<br><span class="muted">{esc(STATE_WORD[f["state"]])} · {esc(count)}</span></span></div>')
    return f'<section class="br-flight">{head}{"".join(rows)}</section>'


def orders_html(b: dict) -> str:
    head = ('<div class="br-colh"><h2 class="br-h">Orders received</h2>'
            '<span class="muted">your acts on GitHub</span></div>')
    if not b["orders"]:
        return f'<section class="br-orders">{head}<p class="muted">No acts of yours in the events read.</p></section>'
    rows = []
    for o in b["orders"]:
        what = esc(o["verb"])
        if o["ref"]:
            what += " " + _a(o["link"], f'<b>{esc(o["ref"])}</b>')
        if o["extra"]:
            what += f' <code>{esc(o["extra"])}</code>'
        if not o["ref"]:
            what = _a(o["link"], what)
        rows.append(f'<div class="br-row">{_time(o["time"], b["now"])}'
                    f'<span class="br-grow">{what} <span class="muted">· you, via GitHub</span></span></div>')
    return f'<section class="br-orders">{head}{"".join(rows)}</section>'


# The Bridge's left column, shared by its pages: (file, name). Agents is Operations until #932.
NAV = (("bridge.html", "Bridge"), ("commissions.html", "Commissions"), ("operations.html", "Agents"))


def nav_html(current: str, counts: dict[str, int]) -> str:
    """The left column: the Bridge's pages, the current one marked, each with its count."""
    items = []
    for file, name in NAV:
        n = counts.get(name)
        count = f'<span class="mono muted">{n}</span>' if n is not None else ""
        if file == current:
            items.append(f'<span class="br-navi here" aria-current="page">{esc(name)}{count}</span>')
        else:
            items.append(f'<a class="br-navi" href="{esc(file)}">{esc(name)}{count}</a>')
    return ('<nav class="br-nav" aria-label="Bridge">' + "".join(items)
            + '<p class="br-kind">YOUR CHAIRS</p>'
            '<p class="muted br-note">None connected yet. You give orders on GitHub; '
            'the Bridge is where you look.</p></nav>')


def nav_counts(m: dict) -> dict[str, int]:
    """The left column's counts: open Goals and Areas, and live sessions."""
    live = [s for s in m.get("sessions") or [] if s.get("status") != "stopped" and not s.get("never_acted")]
    return {"Commissions": len(in_flight(m)), "Agents": len(live)}


def render(b: dict) -> str:
    """The Bridge's <main> content."""
    err = (f'<p class="error">The trouble report wasn\'t read ({esc(b["trouble_error"])}), so flags, '
           'decisions and authority may be missing.</p>' if b.get("trouble_error") else "")
    day = b["now"].astimezone(dt.timezone.utc).strftime("%a %d %b, %H:%M UTC")
    main = (f'<div class="br-main"><div class="br-titlebar"><h1>Bridge</h1>'
            f'<span class="mono muted">{esc(day)}</span></div>{err}'
            f'{status_html(b)}{decisions_html(b)}'
            f'<div class="br-cols"><div class="br-left">{reports_html(b)}</div>'
            f'<div class="br-right">{flights_html(b)}{orders_html(b)}</div></div></div>')
    return f'<div class="bridge">{nav_html(FILE, {"Commissions": b["commissions"], "Agents": b["agents"]})}{main}</div>'


def page(m: dict, owner: str | None, title: str, owner_line: str) -> str:
    """bridge.html, in the shared page shell."""
    return layout.page(FILE, title, m["repo"], m["now"], render(build(m, owner)), owner_line)
