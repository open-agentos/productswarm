"""Effort on the Desk (#1013, FEAT-4 under M7 #987): what kind of work the swarm ships, per Goal.

Reads only `classify/cache/effort.json`, which `swarm classify run effort` writes (#1012). No
model calls and no API calls of its own. The cache, schema 1:

    {"schema": 1, "labelset": "effort", "classifier": "model" | "paths",
     "updated_at": "2026-11-13T09:00:00Z",
     "prs": {"1009": {"repo": "o/r", "title": "...", "merged_at": "2026-11-13T08:00:00Z",
                      "label": "capability" | "upkeep" | "governance" | "knowledge",
                      "fix": false, "fixes": 1001 | null, "goal": "o/r#987" | 987 | null,
                      "hash": "...", "labeller": "model" | "paths" | "owner"}}}

`repo` defaults to the desk's repo, and a bare `goal` number means an issue in it. An item
without a known label or a merge time is left out and counted as unreadable.

What it draws:
  - the Bridge's In flight: each Goal card's PRs by label for the last WINDOW days (card_line);
  - the desk's Effort panel: a stacked bar per open Goal (this window, the one before; the fix
    share hatched) and the capability share across all merged PRs by week, each segment
    linking to its PRs on effort.html;
  - `swarm daily`'s upkeep risk line (risks): upkeep is more than half of a Goal's merged PRs
    in the last WINDOW days.

Colours are layout.py's, by class (no new colours). Stdlib only, no script.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from layout import esc

FILE = "effort.html"
CACHE_NAME = "classify/cache/effort.json"
CACHE = Path(__file__).resolve().parent.parent / CACHE_NAME
LABELS = ("capability", "upkeep", "governance", "knowledge")
WINDOW = 7          # days: the Bridge's counts, the desk's bars and the risk rule
TREND_WEEKS = 8     # weeks of capability share, this week included
WINDOWS = (("this", "last 7 days"), ("last", "7 days before"))
REF_RE = re.compile(r"^([\w.-]+/[\w.-]+)#(\d+)$")
URL_RE = re.compile(r"github\.com/([\w.-]+/[\w.-]+)/(?:issues|pull)/(\d+)")


# ---------------------------------------------------------------- the cache

def load(path: Path | str = CACHE) -> dict | None:
    """The cache as read: None when it isn't there, {"error": why} when it can't be read."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as e:
        return {"error": f"can't read {path}: {e}"}
    try:
        data = json.loads(text)
    except ValueError as e:
        return {"error": f"{path} isn't JSON: {e}"}
    if not isinstance(data, dict) or not isinstance(data.get("prs"), dict):
        return {"error": f"{path} has no \"prs\" object"}
    return data


def _ts(s) -> dt.datetime | None:
    try:
        t = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


def goal_ref(goal, repo: str) -> str | None:
    """"o/r#987" from "o/r#987", 987, "987" or "#987"."""
    if isinstance(goal, bool) or goal is None:
        return None
    if isinstance(goal, int):
        return f"{repo}#{goal}"
    g = str(goal).strip()
    if REF_RE.match(g):
        return g
    m = re.fullmatch(r"#?(\d+)", g)
    return f"{repo}#{m.group(1)}" if m else None


def ref_of_url(url: str | None) -> str | None:
    m = URL_RE.search(url or "")
    return f"{m.group(1)}#{m.group(2)}" if m else None


def items(cache: dict | None, repo: str) -> tuple[list[dict], int]:
    """The cache's PRs, newest first, each {number, repo, title, url, label, fix, merged_at,
    goal}, and how many were left out as unreadable."""
    out, bad = [], 0
    for key, p in ((cache or {}).get("prs") or {}).items():
        if not isinstance(p, dict) or not str(key).isdigit():
            bad += 1
            continue
        when, label = _ts(p.get("merged_at")), p.get("label")
        if when is None or label not in LABELS:
            bad += 1
            continue
        r = p.get("repo") or repo
        out.append({"number": int(key), "repo": r, "title": p.get("title") or "",
                    "url": f"https://github.com/{r}/pull/{int(key)}", "label": label,
                    "fix": p.get("fix") is True, "merged_at": when, "goal": goal_ref(p.get("goal"), repo)})
    out.sort(key=lambda p: (p["merged_at"], p["number"]), reverse=True)
    return out, bad


# ---------------------------------------------------------------- the model

def counts(prs: list[dict]) -> dict:
    """{"total", "fixes", "by": {label: n}, "fix_by": {label: n}}."""
    return {"total": len(prs), "fixes": sum(p["fix"] for p in prs),
            "by": {lb: sum(p["label"] == lb for p in prs) for lb in LABELS},
            "fix_by": {lb: sum(p["label"] == lb and p["fix"] for p in prs) for lb in LABELS}}


def monday(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=d.weekday())


def build(cache: dict | None, repo: str, now: dt.datetime, goals: list[dict]) -> dict:
    """The effort model. `goals` are the open Goals, each {ref, lead, title, url}. Returns
    {"status": "missing" | "error" | "ok", "error", "classifier", "updated_at", "unreadable",
    "goals": [{ref, lead, title, url, "this": prs, "last": prs, counts per window}],
    "by_goal": {ref: counts for the last WINDOW days}, "trend": [{week, capability, total}]}."""
    if cache is None:
        return {"status": "missing", "goals": [], "by_goal": {}, "trend": [], "now": now}
    if cache.get("error"):
        return {"status": "error", "error": cache["error"], "goals": [], "by_goal": {}, "trend": [], "now": now}
    prs, bad = items(cache, repo)
    edges = {"this": (now - dt.timedelta(days=WINDOW), now),
             "last": (now - dt.timedelta(days=2 * WINDOW), now - dt.timedelta(days=WINDOW))}

    def within(p, w):
        lo, hi = edges[w]
        return lo < p["merged_at"] <= hi

    by_goal: dict[str, dict] = {}
    for ref in {p["goal"] for p in prs if p["goal"]}:
        by_goal[ref] = counts([p for p in prs if p["goal"] == ref and within(p, "this")])
    out_goals = []
    for g in goals:
        row = dict(g)
        for w, _ in WINDOWS:
            row[w] = [p for p in prs if p["goal"] == g["ref"] and within(p, w)]
            row[w + "_counts"] = counts(row[w])
        out_goals.append(row)
    first = monday(now.date()) - dt.timedelta(weeks=TREND_WEEKS - 1)
    trend = []
    for i in range(TREND_WEEKS):
        wk = first + dt.timedelta(weeks=i)
        these = [p for p in prs if monday(p["merged_at"].date()) == wk and p["merged_at"] <= now]
        trend.append({"week": wk, "capability": sum(p["label"] == "capability" for p in these),
                      "total": len(these)})
    return {"status": "ok", "classifier": cache.get("classifier"), "updated_at": _ts(cache.get("updated_at")),
            "unreadable": bad, "goals": out_goals, "by_goal": by_goal, "trend": trend, "now": now}


def card_line(c: dict | None) -> str | None:
    """The Bridge card's line: "5 PRs · 2 capability · 1 upkeep · 1 governance · 1 knowledge · 1 fix"."""
    if c is None:
        return None
    n = c["total"]
    parts = [f"{n} PR{'s' if n != 1 else ''}", *(f"{c['by'][lb]} {lb}" for lb in LABELS),
             f"{c['fixes']} fix{'es' if c['fixes'] != 1 else ''}"]
    return " · ".join(parts)


def upkeep_heavy(c: dict) -> bool:
    """The risk rule: upkeep is more than half of the Goal's merged PRs."""
    return c["total"] > 0 and 2 * c["by"]["upkeep"] > c["total"]


def risks(e: dict) -> list[str]:
    """`swarm daily`'s upkeep risk lines, one per Goal over the rule, by Goal."""
    return [f"Upkeep risk: {ref}: {c['by']['upkeep']} of {c['total']} PRs merged in the last "
            f"{WINDOW} days were upkeep (more than half)."
            for ref, c in sorted(e.get("by_goal", {}).items()) if upkeep_heavy(c)]


def daily_text(e: dict, path: Path | str = CACHE_NAME) -> str:
    """`swarm daily`'s effort section, for the report's Risks and mitigations."""
    if e["status"] == "missing":
        return f"Effort risks: no effort cache yet ({path}), so none checked."
    if e["status"] == "error":
        return f"Effort risks couldn't be read: {e['error']}"
    lines = risks(e)
    head = (f"Effort risks (upkeep more than half of a Goal's merged PRs in the last {WINDOW} days, "
            f"from {path}):")
    return "\n".join([head, *(f"  {x}" for x in lines)] if lines else [head, "  none"])


# ---------------------------------------------------------------- drawing

def anchor(ref: str, w: str, label: str) -> str:
    """effort.html's fragment for one Goal's window and label: "e-o-r-987-this-upkeep"."""
    return "e-" + re.sub(r"[^A-Za-z0-9]+", "-", ref).strip("-") + f"-{w}-{label}"


def _pct(n: int, of: int) -> str:
    return f"{round(100 * n / of, 2):g}%"


def bar_html(row: dict, w: str, scale: int) -> str:
    """One window's stacked bar: a link per label segment to its PRs, the fix share hatched."""
    c = row[w + "_counts"]
    segs = []
    for lb in LABELS:
        n, fixes = c["by"][lb], c["fix_by"][lb]
        if not n:
            continue
        tip = f"{n} {lb}" + (f", {fixes} fixing recent work" if fixes else "")
        inner = ""
        if fixes:
            inner = f'<span class="ef-fix" style="width:{_pct(fixes, n)}"></span>'
        segs.append(f'<a class="ef-seg ef-{lb}" style="width:{_pct(n, scale)}" '
                    f'href="{FILE}#{anchor(row["ref"], w, lb)}" title="{esc(tip)}" '
                    f'aria-label="{esc(tip)}">{inner}</a>')
    body = "".join(segs) if segs else '<span class="ef-none"></span>'
    word = dict(WINDOWS)[w]
    total = c["total"]
    return (f'<div class="ef-row"><span class="ef-when muted">{esc(word)}</span>'
            f'<span class="ef-bar">{body}</span>'
            f'<span class="ef-n mono">{total}</span></div>')


def legend_html() -> str:
    keys = "".join(f'<span><span class="ef-key ef-{lb}"></span>{lb}</span>' for lb in LABELS)
    return (f'<div class="ef-legend muted">{keys}'
            '<span><span class="ef-key ef-capability"><span class="ef-fix" style="width:100%"></span></span>'
            'fixes recent work</span></div>')


def trend_html(e: dict) -> str:
    """Capability share by week across all merged PRs in the cache: a line and a sentence."""
    t = e["trend"]
    w, h, pad = 240, 48, 4
    step = (w - 2 * pad) / max(len(t) - 1, 1)
    pts = [(pad + i * step, pad + (h - 2 * pad) * (1 - x["capability"] / x["total"]))
           for i, x in enumerate(t) if x["total"]]
    marks = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5"></circle>' for x, y in pts)
    line = (f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}"></polyline>'
            if len(pts) > 1 else "")
    now = t[-1]
    said = (f'This week {_share(now)} of {now["total"]} merged PRs were capability'
            if now["total"] else "No PRs merged this week yet")
    prev = next((x for x in reversed(t[:-1]) if x["total"]), None)
    if prev:
        said += f'; the week of {prev["week"].day} {prev["week"]:%b}, {_share(prev)} of {prev["total"]}'
    label = f"Capability share by week, the last {len(t)} weeks"
    return (f'<div class="ef-trend"><h3>Capability share by week</h3>'
            f'<svg class="ef-line" role="img" aria-label="{esc(label)}" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}"><title>{esc(label)}</title>{line}{marks}</svg>'
            f'<p class="muted">{esc(said)}. All merged PRs in the cache, by week from Monday '
            f'(UTC), from the week of {t[0]["week"].day} {t[0]["week"]:%b}.</p></div>')


def _share(x: dict) -> str:
    return f'{round(100 * x["capability"] / x["total"])}%'


def render(e: dict | None) -> str:
    """The desk's Effort panel."""
    head = '<h2>Effort</h2>'
    if not e or e["status"] == "missing":
        return (f'<section class="effort">{head}<p class="muted">No effort labels yet: '
                f'<code>classify/cache/effort.json</code> isn\'t there. '
                f'<code>swarm classify run effort</code> writes it (#1012).</p></section>')
    if e["status"] == "error":
        return f'<section class="effort">{head}<p class="muted">Effort labels couldn\'t be read: {esc(e["error"])}</p></section>'
    rows = e["goals"]
    scale = max([1, *(r[w + "_counts"]["total"] for r in rows for w, _ in WINDOWS)])
    goals = []
    for r in rows:
        lead = f'<span class="mono">{esc(r["lead"])}</span> ' if r.get("lead") else ""
        name = f'<a href="{esc(r["url"])}">{esc(r["title"])}</a>' if r.get("url") else esc(r["title"])
        goals.append(f'<div class="ef-goal"><div class="ef-name">{lead}{name}</div>'
                     + "".join(bar_html(r, w, scale) for w, _ in WINDOWS) + "</div>")
    by = ("the model classifier" if e.get("classifier") == "model" else
          "the paths baseline" if e.get("classifier") == "paths" else "the classifier")
    upd = e.get("updated_at")
    note = (f'Merged PRs per open Goal, by kind of work, from {by}'
            + (f', labels updated {upd:%Y-%m-%d %H:%M} UTC' if upd else "")
            + (f'; {e["unreadable"]} cache entries left out as unreadable' if e.get("unreadable") else "")
            + '. A segment opens its PRs.')
    body = "".join(goals) if goals else '<p class="muted">No open Goal.</p>'
    return (f'<section class="effort">{head}<p class="muted">{esc(note)}</p>{legend_html()}'
            f'{body}{trend_html(e)}</section>')


def page_body(e: dict | None, repo: str) -> str:
    """effort.html: each open Goal's PRs by window and label, for the desk's bar segments."""
    out = ['<h1>Effort</h1>',
           '<p class="muted">The PRs behind the <a href="index.html">desk</a>\'s Effort bars, '
           'from <code>classify/cache/effort.json</code>. A PR marked fix fixes something merged '
           'in the 14 days before it.</p>']
    if not e or e["status"] != "ok":
        out.append(render(e))
        return "\n".join(out)
    for r in e["goals"]:
        lead = f'{r["lead"]}: ' if r.get("lead") else ""
        out.append(f'<h2>{esc(lead + r["title"])}</h2>')
        for w, word in WINDOWS:
            for lb in LABELS:
                prs = [p for p in r[w] if p["label"] == lb]
                lis = "".join(
                    f'<li><a href="{esc(p["url"])}">#{p["number"]}</a> {esc(p["title"])}'
                    + (' <span class="muted">· fix</span>' if p["fix"] else "")
                    + f' <span class="muted mono">{p["merged_at"]:%Y-%m-%d}</span></li>' for p in prs)
                out.append(f'<h3 id="{anchor(r["ref"], w, lb)}">{esc(lb.capitalize())}, {esc(word)}: '
                           f'{len(prs)}</h3>' + (f'<ul>{lis}</ul>' if prs else ""))
    return "\n".join(out)


def goals_of(m: dict) -> list[dict]:
    """The open Goals, from the trouble report, or the plan when that wasn't read."""
    out = []
    t = m.get("trouble") or {}
    if t.get("scopes") is not None:
        for s in t["scopes"]:
            if isinstance(s, dict) and s.get("type") == "Goal" and s.get("ref"):
                lead, title = _parts(s.get("title"))
                out.append({"ref": s["ref"], "lead": lead, "title": title, "url": s.get("url")})
        return out
    for s in (m.get("plan") or {}).get("scopes") or []:
        ref = ref_of_url(s.get("url"))
        if s.get("kind") == "Goal" and ref:
            out.append({"ref": ref, "lead": s.get("lead") or "", "title": s.get("title") or "",
                        "url": s.get("url")})
    return out


def _parts(title: str | None) -> tuple[str, str]:
    m = re.match(r"^(\S{1,12}):\s+(.*)$", title or "")
    return (m.group(1), m.group(2)) if m else ("", title or "")


def state(e: dict | None) -> dict | None:
    """state.json's "effort": counts only, no HTML."""
    if not e:
        return None
    if e["status"] != "ok":
        return {"status": e["status"], "error": e.get("error")}
    return {"status": "ok", "classifier": e.get("classifier"),
            "goals": [{"ref": r["ref"], **{w: r[w + "_counts"] for w, _ in WINDOWS}} for r in e["goals"]],
            "trend": [{"week": x["week"].isoformat(), "capability": x["capability"], "total": x["total"]}
                      for x in e["trend"]]}
