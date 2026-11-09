"""The desk's "Today's report" panel (#712, laid out in #711, under #685).

What counts: the newest comment on `[watch] report_issue` (swarm.toml) by the planner App
whose body starts `**Daily report`. A comment starting `**Monday check-in` is the check-in.
"Today" and the 10:00 cut-off are in the build machine's local time, the timezone `[daily]`
uses for `daily_at`; working days are Monday to Friday, as for `[daily]`. A report's day is
the date on its first line when it names one (swarm.report_day), so `swarm daily` and the
desk agree on which day a report is for.

It shows the report's bold first sentence, linking it, with its posting time; then the
numbered items under its `Asks` heading (at most 5), each its bold lead-in and the rest of its
first sentence; then, on a Monday, the check-in's first sentence. With no report today it says
whether one is due, late or not expected, and shows the last one's first sentence.

API calls: 1 REST call, more only if the report issue has over 100 comments in 4 days: the
report issue's comments since 4 days ago, which reaches Friday's report on a Monday or
Tuesday. Stdlib only.
"""
from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

from layout import esc

PLANNER = "productswarm-planner[bot]"
LOOK_BACK_DAYS = 4         # comments read: enough to reach Friday's report on a Tuesday
LATE = dt.time(10, 0)      # after this, a working day with no report shows it as late
MAX_ASKS = 5
ASK_CHARS = 120            # an ask's lead-in and first sentence, cut to about this

REPORT_START = "**Daily report"
CHECKIN_START = "**Monday check-in"
ASKS_HEADING_RE = re.compile(r"^\s*(?:#{1,6}\s*)?(?:\*\*)?\s*(?:\d+\.\s*)?Asks\b", re.IGNORECASE)
HEADING_RE = re.compile(r"^\s*(?:#{1,6}\s|\*\*\d+\.\s)")
ITEM_RE = re.compile(r"^\s*\d+[.)]\s+(.*\S)")
LEAD_RE = re.compile(r"^\*\*(.+?)\*\*")
BOLD_START_RE = re.compile(r"^\*\*(.+?)\*\*")
SENTENCE_END_RE = re.compile(r"[.?!](?=\s|$)")
ISSUE_RE = re.compile(r"(?<![\w/])#(\d+)\b")
INLINE_RE = re.compile(r"`([^`]+)`|\*\*(.+?)\*\*")


def _swarm():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "launcher"))
    import swarm
    return swarm


def config(path: Path | None = None) -> tuple[int | None, dt.time | None]:
    """(report_issue, daily_at) from swarm.toml's [watch] table, or (None, None) if it can't
    be read."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "launcher"))
        import manifest
        w = manifest.load_watch(path or manifest.DEFAULT_PATH)
    except Exception:   # ImportError (no tomllib), ManifestError: the panel says so
        return None, None
    return (w.report_issue, w.daily_at) if w else (None, None)


def fetch(repo: str, issue: int | None, now: dt.datetime, gh_items) -> list[dict] | None:
    """The report issue's comments from the last LOOK_BACK_DAYS, oldest first, or None if they
    couldn't be read."""
    if issue is None:
        return None
    since = (now - dt.timedelta(days=LOOK_BACK_DAYS)).astimezone(dt.timezone.utc)
    try:
        return gh_items(f"repos/{repo}/issues/{issue}/comments?since="
                        f"{since:%Y-%m-%dT%H:%M:%SZ}&per_page=100")
    except Exception:   # RuntimeError from gh, or anything odd: the panel says it couldn't read
        return None


def first_line(body: str) -> str:
    """The bold first sentence of a report or check-in, as written, without its `**`; or the
    whole first line if it doesn't open in bold."""
    line = ((body or "").strip().splitlines() or [""])[0].strip()
    m = BOLD_START_RE.match(line)
    return m.group(1).strip() if m else line


def cut(text: str, n: int = ASK_CHARS) -> str:
    if len(text) <= n:
        return text
    return text[:n].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


def asks(body: str) -> list[dict] | None:
    """The numbered items under the report's `Asks` heading, at most MAX_ASKS: each
    {"lead", "text", "issue"}. `lead` is its bold lead-in, `text` the rest of its first
    sentence, `issue` the first #N in the item. None if there is no Asks heading or no item
    under it."""
    lines = (body or "").splitlines()
    start = next((i for i, ln in enumerate(lines) if ASKS_HEADING_RE.match(ln)), None)
    if start is None:
        return None
    out = []
    for ln in lines[start + 1:]:
        if HEADING_RE.match(ln) or ln.strip().startswith("-- "):
            break
        m = ITEM_RE.match(ln)
        if not m:
            continue
        item = m.group(1)
        lead_m = LEAD_RE.match(item)
        lead, rest = (lead_m.group(1).strip(), item[lead_m.end():].strip()) if lead_m else ("", item)
        end = SENTENCE_END_RE.search(rest)
        rest = rest[:end.end()] if end else rest
        if len(lead) >= ASK_CHARS:
            lead, rest = cut(lead), ""
        else:
            rest = cut(rest, ASK_CHARS - len(lead))
        issue = ISSUE_RE.search(item)
        out.append({"lead": lead, "text": rest, "issue": int(issue.group(1)) if issue else None})
        if len(out) == MAX_ASKS:
            break
    return out or None


def _local(created_at: str, tz: dt.tzinfo | None) -> dt.datetime | None:
    try:
        t = dt.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return t.astimezone(tz) if tz else t.astimezone()


def _post(c: dict, day: dt.date, posted: dt.datetime) -> dict:
    body = c.get("body") or ""
    return {"day": day, "posted": posted, "url": c.get("html_url"), "line": first_line(body),
            "asks": asks(body)}


def build(comments: list[dict] | None, now: dt.datetime, issue: int | None,
          daily_at: dt.time | None, tz: dt.tzinfo | None = None) -> dict:
    """The panel's data: {"issue", "read", "today" (local date), "daily_at", "state", "report"
    (today's or None), "last" (the newest earlier report or None), "checkin" (today's, Mondays
    only, or None)}. `state` is one of "posted", "due", "late", "weekend", "unread", "unset"."""
    local = now.astimezone(tz) if tz else now.astimezone()
    today = local.date()
    out = {"issue": issue, "today": today, "daily_at": daily_at, "report": None, "last": None,
           "checkin": None, "read": comments is not None}
    if issue is None:
        return {**out, "state": "unset"}
    if comments is None:
        return {**out, "state": "unread"}
    swarm = _swarm()
    reports, checkins = [], []
    for c in comments:
        if (c.get("user") or {}).get("login") != PLANNER:
            continue
        body = (c.get("body") or "").lstrip()
        if body.startswith(REPORT_START):
            r = swarm.report_day(c, local.tzinfo)
            if r and r[1] <= local:
                reports.append(_post(c, *r))
        elif body.startswith(CHECKIN_START):
            posted = _local(c.get("created_at"), local.tzinfo)
            if posted and posted <= local:
                checkins.append(_post(c, posted.date(), posted))
    reports.sort(key=lambda r: r["posted"])
    out["report"] = next((r for r in reversed(reports) if r["day"] == today), None)
    out["last"] = next((r for r in reversed(reports) if r["day"] < today), None)
    if today.weekday() == 0:
        out["checkin"] = next((c for c in reversed(sorted(checkins, key=lambda c: c["posted"]))
                               if c["day"] == today), None)
    if out["report"]:
        state = "posted"
    elif today.weekday() >= 5:
        state = "weekend"
    elif local.time() < LATE:
        state = "due"
    else:
        state = "late"
    return {**out, "state": state}


def inline(text: str) -> str:
    """A line of report Markdown as HTML: escaped, with `code` and **bold** kept."""
    out, i = [], 0
    for m in INLINE_RE.finditer(text):
        out.append(esc(text[i:m.start()]))
        out.append(f"<code>{esc(m.group(1))}</code>" if m.group(1) is not None
                   else f"<b>{esc(m.group(2))}</b>")
        i = m.end()
    out.append(esc(text[i:]))
    return "".join(out)


def _due(r: dict) -> str:
    return f"due at {r['daily_at']:%H:%M}" if r.get("daily_at") else "due"


def _last(r: dict) -> str:
    last = r["last"]
    if last is None:
        return f'<p class="muted">No daily report found on #{r["issue"]}.</p>'
    return (f'<p class="last"><span class="muted">Last report, {last["day"]:%a %m-%d}:</span> '
            f'<a href="{esc(last["url"])}">{inline(last["line"])}</a></p>')


def render(r: dict | None, repo: str) -> str:
    """The desk's "Today's report" panel."""
    if r is None:
        return ""
    return f'<section class="report">{_body(r, repo)}</section>'


def _body(r: dict, repo: str) -> str:
    head = "<h2>Today's report</h2>"
    base = f"https://github.com/{repo}"
    if r["state"] == "unset":
        return f'{head}<p class="muted">No report issue is set in swarm.toml\'s [watch] table.</p>'
    if r["state"] == "unread":
        return f'{head}<p class="muted">Couldn\'t read #{r["issue"]}; the report may be there.</p>'
    if r["state"] == "weekend":
        return f'{head}<p>No report on weekends.</p>{_last(r)}'
    if r["state"] == "due":
        return f'{head}<p>Today\'s report is {_due(r)}.</p>{_last(r)}'
    if r["state"] == "late":
        return (f'{head}<p class="ask"><b>No report yet today.</b> It was {_due(r)}.</p>'
                f'{_last(r)}')
    rep = r["report"]
    out = [head, f'<p class="lead"><a href="{esc(rep["url"])}">{inline(rep["line"])}</a> '
                 f'<time class="stamp" datetime="{rep["posted"].astimezone(dt.timezone.utc):%Y-%m-%dT%H:%M:%SZ}">'
                 f'posted {rep["posted"]:%H:%M}</time></p>']
    if rep["asks"] is None:
        out.append(f'<p class="ask">Asks: couldn\'t read them; <a href="{esc(rep["url"])}">open the '
                   f'report</a>.</p>')
    else:
        items = []
        for a in rep["asks"]:
            link = f"{base}/issues/{a['issue']}" if a["issue"] else rep["url"]
            lead = f"<b>{inline(a['lead'])}</b> " if a["lead"] else ""
            items.append(f'<li><a href="{esc(link)}">{lead}{inline(a["text"])}</a></li>')
        out.append(f'<h3>Asks</h3><ol class="asks">{"".join(items)}</ol>')
    if r["checkin"]:
        c = r["checkin"]
        out.append(f'<p class="checkin">Monday check-in: <a href="{esc(c["url"])}">{inline(c["line"])}</a></p>')
    return "".join(out)


def state(r: dict | None) -> dict | None:
    """state.json's `report`: the panel's data, as plain fields."""
    if r is None:
        return None
    return {k: (v.strftime("%H:%M") if isinstance(v, dt.time) else v) for k, v in r.items()}
