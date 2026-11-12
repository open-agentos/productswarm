"""The Commissions page (#931, under M3 #685): the owner's "v5 · the bridge" mock-up, read-only.

`commissions.html` lists each open Goal and Area the owner opened, grouped by what it needs
from the owner, and opens a focus drawer for the one picked. It is built from the model
generate.build() already makes, so it costs no API calls of its own:

  - the trouble report (`swarm trouble`, #903): each scope's criteria, what's stuck, what
    waits on the owner and the authority used;
  - the plan (plan.py, #712): each scope's open sub-issues with their go status and PRs;
  - `closed_scopes`: the owner's Goals and Areas closed in the build's window.

Groups, in order, each scope in the first that fits: needs a look (flagged: something stuck, a
failing criterion or a missed date, bridge.flagged), waits on you, running (Goals), keep it so
(Areas), then delivered this week (closed in the last DELIVERED_DAYS days).

The drawer needs no script: each row links to `#c-<number>`, and CSS `:target` shows that
scope's drawer; with none picked the drawer says how to pick one. With JavaScript off it all
works the same. No cost and no buttons: GOV-0033 sets no engine total, and the desk can't
write yet (#760). Stdlib only.
"""
from __future__ import annotations

import datetime as dt
import re

import bridge
import layout
from layout import esc
from report import inline

FILE = "commissions.html"
DELIVERED_DAYS = 7
GROUPS = (("look", "Needs a look"), ("waiting", "Waits on you"), ("running", "Running"),
          ("keep", "Keep it so"), ("delivered", "Delivered this week"))
STATUS = {"met": "met", "progress": "in progress", "failing": "failing", "counted": "counted",
          "unmeasured": "unmeasured: not known to be on track"}


def _num(ref) -> int | None:
    m = re.search(r"#(\d+)$", str(ref or ""))
    return int(m.group(1)) if m else None


def group(s: dict) -> str:
    if bridge.flagged(s):
        return "look"
    if s.get("waiting"):
        return "waiting"
    return "keep" if s.get("type") == "Area" else "running"


def build(m: dict) -> dict:
    """{"now", "repo", "error", "rows": [...], "counts"}: one row per scope, in group order."""
    now = m["now"]
    t = m.get("trouble") or {}
    plan = {s["number"]: s for s in (m.get("plan") or {}).get("scopes") or []}
    rows = []
    for s in bridge._scopes(t):
        n = _num(s.get("ref"))
        crit = s.get("progress") or []
        p = plan.get(n) or {}
        rows.append({"number": n, "group": group(s), "type": s.get("type") or "",
                     "lead": bridge.lead(s.get("title")), "title": re.sub(r"^\S{1,12}:\s+", "", s.get("title") or ""),
                     "url": s.get("url"), "date": s.get("date"), "date_missed": s.get("date_missed"),
                     "criteria": crit, "met": sum(c.get("status") == "met" for c in crit),
                     "stuck": s.get("stuck") or [], "waiting": s.get("waiting") or [],
                     "authority": s.get("authority") or [],
                     "open": p.get("open"), "done": p.get("done"), "subs": p.get("subs") or []})
    if not rows and t.get("scopes") is None:   # the trouble report wasn't read: the plan alone
        for n, p in plan.items():
            rows.append({"number": n, "group": "keep" if p.get("kind") == "Area" else "running",
                         "type": p.get("kind") or "", "lead": p.get("lead") or "", "title": p.get("title") or "",
                         "url": p.get("url"), "date": None, "date_missed": False, "criteria": [], "met": 0,
                         "stuck": [], "waiting": [], "authority": [], "open": p.get("open"),
                         "done": p.get("done"), "subs": p.get("subs") or []})
    since = now - dt.timedelta(days=DELIVERED_DAYS)
    for c in m.get("closed_scopes") or []:
        closed = bridge._ts(c.get("closed_at"))
        if closed and closed >= since:
            rows.append({"number": c["number"], "group": "delivered", "type": c.get("type") or "",
                         "lead": bridge.lead(c.get("title")),
                         "title": re.sub(r"^\S{1,12}:\s+", "", c.get("title") or ""), "url": c.get("url"),
                         "closed": closed, "date": None, "date_missed": False, "criteria": [], "met": 0,
                         "stuck": [], "waiting": [], "authority": [], "open": None, "done": None, "subs": []})
    order = [g for g, _ in GROUPS]
    rows.sort(key=lambda r: (order.index(r["group"]), r["type"] != "Goal", r["number"] or 0))
    return {"now": now, "repo": m["repo"], "error": t.get("error"), "rows": rows,
            "counts": bridge.nav_counts(m)}


# ---------------------------------------------------------------- drawing

DOT = {"look": "red", "waiting": "owner", "running": "agent", "keep": "quiet", "delivered": "quiet"}


def _word(r: dict, now: dt.datetime) -> tuple[str, str]:
    """The row's status word and its class."""
    if r["group"] == "delivered":
        return f"closed {bridge.when(r.get('closed'), now)}", ""
    if r["stuck"]:
        return f"{len(r['stuck'])} stuck", "br-red"
    if r["date_missed"]:
        return "date missed", "br-red"
    failing = sum(c.get("status") == "failing" for c in r["criteria"])
    if failing:
        return f"{failing} failing", "br-red"
    if r["waiting"]:
        return f"{len(r['waiting'])} wait on you", "owner"
    return ("steady" if r["type"] == "Area" else "running"), ""


def _bar(r: dict) -> str:
    total = len(r["criteria"])
    if not total:
        return '<span class="cm-bar-none mono muted">no criteria</span>'
    pct = round(100 * r["met"] / total)
    return (f'<span class="cm-bar" role="img" aria-label="{r["met"]} of {total} criteria met">'
            f'<span class="cm-fill" style="width:{pct}%"></span></span>'
            f'<span class="mono muted cm-of">{r["met"]}/{total}</span>')


def _sub(r: dict) -> str:
    bits = [r["type"] or "scope"]
    if r["open"] is not None:
        bits.append(f'{r["open"]} open, {r["done"]} done')
    if r.get("date"):
        bits.append(f'date {r["date"]}')
    return " · ".join(bits)


def row_html(r: dict, now: dt.datetime) -> str:
    word, cls = _word(r, now)
    lead = f'<span class="mono">{esc(r["lead"])}</span> ' if r["lead"] else ""
    return (f'<a class="cm-row" href="#c-{r["number"]}"><span class="br-dot {DOT[r["group"]]}" aria-hidden="true"></span>'
            f'<span class="cm-name"><span class="br-title">{lead}{esc(r["title"])}</span>'
            f'<span class="muted">{esc(_sub(r))}</span></span>'
            f'<span class="cm-bars">{_bar(r)}</span><span class="cm-word {cls}">{esc(word)}</span></a>')


def _items(head: str, xs: list[dict], none: str, now: dt.datetime) -> str:
    if not xs:
        return f'<div class="cm-sec"><p class="br-kind">{esc(head)}</p><p class="muted">{esc(none)}</p></div>'
    lis = "".join(
        f'<li>{bridge._a(x.get("url"), esc(x.get("ref") or ""))} {inline(x.get("reason") or "")} '
        f'<span class="muted">· {esc(bridge.age(bridge._ts(x.get("since")), now))}</span></li>'
        for x in xs)
    return f'<div class="cm-sec"><p class="br-kind">{esc(head)}</p><ul class="cm-list">{lis}</ul></div>'


def _subs(subs: list[dict]) -> str:
    if not subs:
        return ""
    lis = []
    for x in subs:
        st = x.get("status") or {}
        pr = (f' · {bridge._a((x.get("pr") or {}).get("url"), "PR #" + str(x["pr"]["number"]))}'
              if x.get("pr") else "")
        lis.append(f'<li>{bridge._a(x.get("url"), esc(x.get("ref") or ""))} {esc(x.get("title") or "")} '
                   f'<span class="st {esc(st.get("kind") or "")}">{inline(st.get("text") or "")}</span>{pr}</li>')
    return f'<div class="cm-sec"><p class="br-kind">OPEN WORK UNDER IT</p><ul class="cm-list">{"".join(lis)}</ul></div>'


STATE_PILL = {"look": ("NEEDS A LOOK", "red"), "waiting": ("WAITS ON YOU", "owner"),
              "running": ("RUNNING", "agent"), "keep": ("KEEP IT SO", "ink"), "delivered": ("DELIVERED", "ink")}


def drawer_html(r: dict, now: dt.datetime) -> str:
    pill, color = STATE_PILL[r["group"]]
    word, _ = _word(r, now)
    out = [f'<section class="cm-drawer" id="c-{r["number"]}" aria-label="{esc(r["lead"] or r["title"])}">',
           f'<p class="br-kind">IN FOCUS · {esc(r["type"].upper() or "SCOPE")}</p>',
           f'<p class="muted cm-crumb">Whole plan › {bridge._a(r["url"], "#" + str(r["number"]))}</p>',
           f'<h2 class="br-h cm-dtitle">{esc(r["lead"] + ": " if r["lead"] else "")}{esc(r["title"])}</h2>',
           f'<p><span class="cm-pill {color}">{pill}</span> <span class="muted">{esc(word)}</span></p>']
    if r["criteria"]:
        lis = "".join(f'<li class="status-{esc(c.get("status"))}"><b>{esc(STATUS.get(c.get("status"), c.get("status")))}</b> '
                      f'{inline(c.get("criterion") or "")}' + (f' <span class="muted">({inline(c.get("detail") or "")})</span>' if c.get("detail") else "")
                      + "</li>" for c in r["criteria"])
        out.append(f'<div class="cm-sec"><p class="br-kind">DONE TEST</p><ul class="cm-list">{lis}</ul></div>')
    elif r["group"] != "delivered":
        out.append('<div class="cm-sec"><p class="br-kind">DONE TEST</p><p class="muted">No criteria found in its body.</p></div>')
    if r["group"] != "delivered":
        out.append(_items("STUCK, AND WHY NOTHING WILL START IT", r["stuck"], "Nothing is stuck.", now))
        out.append(_items("WAITS ON YOU", r["waiting"], "Nothing waits on you.", now))
        out.append(_items("DONE ON YOUR AUTHORITY", r["authority"], "Nothing in the last day.", now))
        out.append(_subs(r["subs"]))
    out.append(f'<p class="cm-sec">{bridge._a(r["url"], "Open it on GitHub")} · '
               f'<a href="#top">Back to the list</a></p></section>')
    return "".join(out)


def render(c: dict) -> str:
    now = c["now"]
    rows = c["rows"]
    err = (f'<p class="error">The trouble report wasn\'t read ({esc(c["error"])}), so criteria and flags '
           'are missing.</p>' if c.get("error") else "")
    open_n = sum(r["group"] != "delivered" for r in rows)
    out = [f'<div class="br-titlebar"><h1>Commissions</h1><span class="mono muted">{open_n} open · '
           f'{esc(now.strftime("%a %d %b, %H:%M UTC"))}</span></div>', err,
           '<p class="muted">Your open Goals and Areas, grouped by what each needs from you. Pick one to see it in focus.</p>']
    if not rows:
        out.append('<p class="muted">No open Goal or Area, and none delivered this week.</p>')
    for g, name in GROUPS:
        rs = [r for r in rows if r["group"] == g]
        if rs:
            cls = " br-red" if g == "look" else " owner" if g == "waiting" else ""
            out.append(f'<p class="cm-grp{cls}">{esc(name.upper())} · {len(rs)}</p>'
                       + "".join(row_html(r, now) for r in rs))
    drawers = "".join(drawer_html(r, now) for r in rows)
    aside = (f'<aside class="cm-aside" aria-label="In focus"><p class="cm-pick muted">'
             f'Pick a Goal or Area to see its done test, what\'s stuck, what waits on you and the work under it.</p>'
             f'{drawers}</aside>')
    main = f'<div class="cm-main" id="top">{"".join(out)}</div>'
    return (f'<div class="bridge">{bridge.nav_html(FILE, c["counts"])}'
            f'<div class="cm-wrap">{main}{aside}</div></div>')


def page(m: dict, title: str, owner_line: str) -> str:
    """commissions.html, in the shared page shell."""
    return layout.page(FILE, title, m["repo"], m["now"], render(build(m)), owner_line)
