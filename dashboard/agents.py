"""The Agents page (#932, under M3 #685): the owner's "v5 · the bridge" mock-up, read-only.

`agents.html` has one row per role (the files in roles/, plus the merger App) and a focus
drawer for the one picked. It is built from the model generate.build() already makes, so it
costs no API calls of its own:

  - sessions (tracking issues and their heartbeat events): who is working, on what, and how
    many sessions each role ran in the build's window;
  - `merged`: PRs a role's App had merged in the window; `prs`: its open PRs, and whether the
    reviewer's latest review at head requested changes;
  - grants: the merger's calls in the last 24 hours, counted for the role whose PR it was.

Groups: working (a live session that is active or blocked; for the merger, a call in the
last 24 hours), then idle. The drawer opens through CSS `:target`, as on Commissions, so it
needs no script. To ask a role something, the owner comments `Ask: <role>: ...` on the
report issue (GOV-0029); the drawer says so and links there.

No spend, caps or cost per result (GOV-0033), and no first-pass review rate or reverts: the
build doesn't read merged PRs' reviews. Stdlib only.
"""
from __future__ import annotations

import datetime as dt

import bridge
import layout
from layout import esc

FILE = "agents.html"
# (role, what it does), in the order the page lists them.
ROLES = (("planner", "Runs the plan and writes your daily report"),
         ("builder", "Builds and ships code"),
         ("reviewer", "Reviews every PR against its rubric"),
         ("analyst", "Research and briefs"),
         ("designer", "Specs, and how the product reads to you"),
         ("docs", "Records, rulings and docs"),
         ("merger", "Merges under your standing grant (GOV-0027)"))
RECENT = 6
CHANGES = "CHANGES_REQUESTED"


def build(m: dict) -> dict:
    now, repo = m["now"], m["repo"]
    titles = m.get("issue_titles") or {}
    prs = m.get("prs") or []
    days = m.get("days") or 14
    since = now - dt.timedelta(days=days)
    merged = sorted((p for p in m.get("merged") or [] if bridge.role_of(p.get("author"))
                     and (bridge._ts(p.get("merged_at")) or since) >= since),
                    key=lambda p: p.get("merged_at") or "", reverse=True)
    author = {p["number"]: bridge.role_of(p.get("author")) for p in merged}
    author.update({p["number"]: bridge.role_of(p.get("author")) for p in prs})
    calls = (m.get("grants") or {}).get("calls") or []
    sessions = [s for s in m.get("sessions") or [] if not s.get("never_acted")]
    report_issue = (m.get("report") or {}).get("issue")
    rows = []
    for role, does in ROLES:
        mine = [s for s in sessions if s.get("role") == role]
        live = [s for s in mine if s.get("status") in ("active", "blocked")]
        on = []
        for s in live:
            n = s.get("pr") or s.get("issue")
            if n:
                on.append({"ref": f"PR #{n}" if s.get("pr") else f"#{n}", "title": titles.get(n) or "",
                           "url": f"https://github.com/{repo}/{'pull' if s.get('pr') else 'issues'}/{n}",
                           "status": s.get("status")})
        used = [c for c in calls if (role == "merger" or author.get(c.get("number")) == role)]
        open_prs = [p for p in prs if bridge.role_of(p.get("author")) == role]
        working = bool(live) or (role == "merger" and bool(used))
        rows.append({
            "role": role, "does": does, "group": "working" if working else "idle",
            "blocked": any(s.get("status") == "blocked" for s in live), "on": on,
            "merged": [p for p in merged if bridge.role_of(p.get("author")) == role],
            "open": open_prs,
            "changes": [p for p in open_prs if (p.get("reviewer") or {}).get("at_head") == CHANGES],
            "sessions": len(mine), "authority": used,
            "last_ts": max((s["last_ts"] for s in mine if s.get("last_ts")), default=None),
            "ask": role != "merger"})
    rows.sort(key=lambda r: r["group"] != "working")
    return {"now": now, "repo": repo, "days": days, "rows": rows,
            "report_issue": report_issue, "counts": bridge.nav_counts(m)}


# ---------------------------------------------------------------- drawing

def _badge(role: str, group: str) -> str:
    cls = " lead" if role == bridge.LEAD else " idle" if group == "idle" else ""
    return f'<span class="br-av{cls}" aria-hidden="true">{esc(bridge.BADGE.get(role, role[:2].upper()))}</span>'


def _line(r: dict, now: dt.datetime) -> str:
    """The row's second line, as escaped text: no links, since the whole row is one."""
    if r["on"]:
        x = r["on"][0]
        verb = "Blocked on" if x["status"] == "blocked" else "On"
        more = f' and {len(r["on"]) - 1} more' if len(r["on"]) > 1 else ""
        return esc(f'{verb} {x["ref"]} {x["title"]}{more}')
    if r["role"] == "merger" and r["authority"]:
        return esc(f'{len(r["authority"])} call{"s" if len(r["authority"]) != 1 else ""} in the last 24 hours')
    if r["merged"]:
        p = r["merged"][0]
        return esc(f'Last: {p.get("title") or ""}, merged {bridge.when(bridge._ts(p.get("merged_at")), now)}')
    return "Nothing merged in the window."


def row_html(r: dict, b: dict) -> str:
    return (f'<a class="cm-row" href="#a-{r["role"]}">{_badge(r["role"], r["group"])}'
            f'<span class="cm-name"><span class="br-title">{esc(r["role"].capitalize())}</span>'
            f'<span class="muted">{esc(r["does"])}</span><span class="muted">{_line(r, b["now"])}</span></span>'
            f'<span class="mono ag-n">{_count(r)}</span></a>')


def _count(r: dict) -> str:
    """The row's number: merged PRs by its App, or for the merger its calls in the last day."""
    if r["role"] == "merger":
        return f'{len(r["authority"])} calls'
    return f'{len(r["merged"])} merged'


def _tile(label: str, n: int, sub: str, red: bool = False) -> str:
    cls = " br-red" if red and n else ""
    return (f'<div class="ag-tile"><span class="muted">{esc(label)}</span>'
            f'<span class="mono{cls}">{n}</span><span class="muted">{esc(sub)}</span></div>')


def _list(head: str, items: list[str], none: str) -> str:
    body = (f'<ul class="cm-list">{"".join(f"<li>{x}</li>" for x in items)}</ul>' if items
            else f'<p class="muted">{esc(none)}</p>')
    return f'<div class="cm-sec"><p class="br-kind">{esc(head)}</p>{body}</div>'


GROUP_WORD = {"merged": "merged under", "enqueued": "enqueued under", "would": "would merge:", "left": "left for you:"}


def drawer_html(r: dict, b: dict) -> str:
    now, days, repo = b["now"], b["days"], b["repo"]
    pill = ("BLOCKED", "owner") if r["blocked"] else ("WORKING", "agent") if r["group"] == "working" else ("IDLE", "ink")
    out = [f'<section class="cm-drawer" id="a-{r["role"]}" aria-label="{esc(r["role"])}">',
           '<p class="br-kind">IN FOCUS · AGENT</p>',
           f'<div class="ag-head">{_badge(r["role"], r["group"])}<div><h2 class="br-h cm-dtitle">'
           f'{esc(r["role"].capitalize())}</h2><p class="muted cm-crumb">{esc(r["does"])}</p></div></div>',
           f'<p><span class="cm-pill {pill[1]}">{pill[0]}</span> '
           f'<span class="muted">{"last seen " + esc(bridge.when(r["last_ts"], now)) if r["last_ts"] else ""}</span></p>',
           f'<div class="cm-sec"><p class="br-kind">LAST {days} DAYS</p><div class="ag-tiles">'
           + _tile("Merged", len(r["merged"]), "PRs by its App")
           + _tile("Open now", len(r["open"]), "PRs by its App")
           + _tile("Changes requested", len(r["changes"]), "at head, open PRs", red=True)
           + _tile("Sessions", r["sessions"], "run in the window")
           + "</div></div>"]
    out.append(_list("WORKING ON", [f'{bridge._a(x["url"], esc(x["ref"]))} {esc(x["title"])}'
                                    + (' <span class="owner">blocked</span>' if x["status"] == "blocked" else "")
                                    for x in r["on"]], "No live session."))
    out.append(_list("RECENTLY MERGED", [
        f'{bridge._a(p.get("url"), "#" + str(p.get("number")))} {esc(p.get("title") or "")} '
        f'<span class="muted">· {esc(bridge.when(bridge._ts(p.get("merged_at")), now))}</span>'
        for p in r["merged"][:RECENT]], "Nothing merged in the window."))
    out.append(_list("AUTHORITY USED, LAST 24 HOURS", [
        f'{bridge._a(c.get("link"), "PR #" + str(c.get("number")))} {esc(GROUP_WORD.get(c.get("group"), ""))} '
        f'{esc(c.get("reason") or "")}' for c in r["authority"]], "None."))
    if r["ask"]:
        issue = b.get("report_issue")
        where = (bridge._a(f"https://github.com/{repo}/issues/{issue}", f"#{issue}") if issue
                 else "the report issue")
        out.append(f'<div class="cm-sec"><p class="br-kind">ASK IT SOMETHING</p><p>Comment '
                   f'<code>Ask: {esc(r["role"])}: …</code> on {where}. <span class="muted">It starts '
                   f'once and answers there (GOV-0029).</span></p></div>')
    out.append('<p class="cm-sec"><a href="#top">Back to the list</a></p></section>')
    return "".join(out)


def render(b: dict) -> str:
    rows = b["rows"]
    working = sum(r["group"] == "working" for r in rows)
    out = [f'<div class="br-titlebar"><h1>Agents</h1><span class="mono muted">{working} working · '
           f'{len(rows) - working} idle · {esc(b["now"].strftime("%a %d %b, %H:%M UTC"))}</span></div>',
           '<p class="muted">The team that runs the plan for you. Pick one to see its record.</p>']
    for g, name in (("working", "Working"), ("idle", "Idle")):
        rs = [r for r in rows if r["group"] == g]
        if rs:
            out.append(f'<p class="cm-grp">{name.upper()} · {len(rs)}</p>' + "".join(row_html(r, b) for r in rs))
    aside = ('<aside class="cm-aside" aria-label="In focus"><p class="cm-pick muted">Pick an agent to see '
             'what it merged, what it\'s working on, the authority it used and how to ask it something.</p>'
             + "".join(drawer_html(r, b) for r in rows) + "</aside>")
    return (f'<div class="bridge">{bridge.nav_html(FILE, b["counts"])}'
            f'<div class="cm-wrap"><div class="cm-main" id="top">{"".join(out)}</div>{aside}</div></div>')


def page(m: dict, title: str, owner_line: str) -> str:
    """agents.html, in the shared page shell."""
    return layout.page(FILE, title, m["repo"], m["now"], render(build(m)), owner_line)
