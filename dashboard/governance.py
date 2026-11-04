"""The dashboard's governance section (#355, part 3 of #348).

Three parts, all from public repo data:
  - recent decision records: the newest rows of governance/INDEX.md, read from the
    checkout, with records past their review-by date (not precedent, GOVERNANCE.md §6)
    and those due within REVIEW_SOON_DAYS marked;
  - open gov questions: domain, shape, blocking, age and time to live, from the
    Governance question template's body and the issue's labels;
  - lapsed questions (`gov:lapsed`), open, or closed within the page's window.

generate.py fetches the data and calls build() and render(). Stdlib only, no JavaScript.
"""
from __future__ import annotations

import datetime as dt
import html
import re
from collections import Counter
from pathlib import Path

INDEX = Path(__file__).resolve().parent.parent / "governance" / "INDEX.md"
INDEX_PATH = "governance/INDEX.md"   # for links to GitHub
RECENT = 8              # records shown
REVIEW_SOON_DAYS = 30   # "review due soon" within this many days
SHAPE_LABEL = "gov:shape/"
BLOCKING_LABEL = "gov:blocking"
LAPSED_LABEL = "gov:lapsed"

ID_RE = re.compile(r"\[(GOV-(\d+))\]\(([^)\s]+)\)")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


# ---------------------------------------------------------------- INDEX.md

def split_row(line: str) -> list[str] | None:
    """The cells of one Markdown table row, or None if it isn't one. A `|` escaped as
    `\\|` or inside a code span stays in its cell."""
    line = line.strip()
    if not line.startswith("|"):
        return None
    cells, cur, code, i = [], [], False, 1
    while i < len(line):
        c = line[i]
        if c == "\\" and i + 1 < len(line) and line[i + 1] == "|":
            cur.append("|")
            i += 2
            continue
        if c == "`":
            code = not code
        if c == "|" and not code:
            cells.append("".join(cur).strip())
            cur = []
        else:
            cur.append(c)
        i += 1
    if cur and "".join(cur).strip():
        cells.append("".join(cur).strip())   # a row without a closing pipe
    return cells


def parse_date(s: str | None) -> dt.date | None:
    m = DATE_RE.fullmatch((s or "").strip())
    try:
        return dt.date.fromisoformat(m.group(0)) if m else None
    except ValueError:
        return None


def parse_index(text: str | None) -> list[dict]:
    """The decision records listed in INDEX.md: rows whose first cell links a GOV-NNNN
    file. Each: id, num, file (relative to governance/), ruling, domain, shape, status,
    review_by (a date, or None if it doesn't parse) and review_by_text."""
    out = []
    for line in (text or "").splitlines():
        cells = split_row(line)
        if not cells or len(cells) < 6:
            continue
        m = ID_RE.fullmatch(cells[0])
        if not m:
            continue
        out.append({"id": m.group(1), "num": int(m.group(2)), "file": m.group(3),
                    "ruling": cells[1], "domain": cells[2], "shape": cells[3],
                    "status": cells[4], "review_by_text": cells[5],
                    "review_by": parse_date(cells[5])})
    return out


def review_flag(review_by: dt.date | None, today: dt.date) -> str | None:
    """"passed" once the review-by date has gone (not precedent until re-affirmed, §6),
    "soon" within REVIEW_SOON_DAYS of it, else None."""
    if review_by is None:
        return None
    if review_by < today:
        return "passed"
    if (review_by - today).days <= REVIEW_SOON_DAYS:
        return "soon"
    return None


def recent_records(records: list[dict], today: dt.date, n: int = RECENT) -> list[dict]:
    """The n newest records, newest first, each with its review flag."""
    newest = sorted(records, key=lambda r: r["num"], reverse=True)[:n]
    return [{**r, "flag": review_flag(r["review_by"], today)} for r in newest]


def older_flagged(records: list[dict], today: dt.date, n: int = RECENT) -> list[dict]:
    """Records older than the n newest whose review date has passed or is due soon, oldest
    review date first, so a flag isn't hidden just because the record is old."""
    older = sorted(records, key=lambda r: r["num"], reverse=True)[n:]
    flagged = [{**r, "flag": review_flag(r["review_by"], today)} for r in older]
    return sorted((r for r in flagged if r["flag"]), key=lambda r: (r["review_by"], r["num"]))


# ---------------------------------------------------------------- questions

def template_field(body: str | None, heading: str) -> str | None:
    """The first line of a Governance question template answer (`### <heading>`), or None
    if the heading is missing or unanswered."""
    m = re.search(rf"^###\s*{re.escape(heading)}\s*\n+\s*(\S[^\n]*?)\s*$", body or "", re.M)
    return m.group(1) if m and m.group(1) != "_No response_" else None


def question_fields(body: str | None, labels: list[str]) -> dict:
    """Domain, shape and blocking for one gov question. A `gov:shape/*` label wins over the
    body's suggested shape, which is marked as only suggested. Blocking is the `gov:blocking`
    label or a "yes" answer to `### Blocking?`; None if neither says."""
    shape_labels = [lb[len(SHAPE_LABEL):] for lb in labels if lb.startswith(SHAPE_LABEL)]
    suggested = template_field(body, "Suggested shape")
    answer = (template_field(body, "Blocking?") or "").lower()
    if BLOCKING_LABEL in labels or answer.startswith("yes"):
        blocking = True
    elif answer.startswith("no"):
        blocking = False
    else:
        blocking = None
    return {"domain": template_field(body, "Domain"),
            "shape": shape_labels[0] if shape_labels else suggested,
            "shape_suggested": not shape_labels and suggested is not None,
            "blocking": blocking}


def ttl_state(ttl_date: dt.date | None, today: dt.date) -> dict:
    """Days left to a question's time to live (negative once past), or None if no date."""
    if ttl_date is None:
        return {"ttl_date": None, "days_left": None, "past_ttl": False}
    left = (ttl_date - today).days
    return {"ttl_date": ttl_date, "days_left": left, "past_ttl": left < 0}


def counts(questions: list[dict], key: str) -> list[tuple[str, int]]:
    """Questions per value of key, most first, then by name; "unknown" for a missing one."""
    c = Counter(q.get(key) or "unknown" for q in questions)
    return sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))


def lapsed(issues: list[dict], since: dt.datetime, parse_ts, time_to_live) -> list[dict]:
    """`gov:lapsed` questions: open, or closed at or after `since`. Newest first."""
    out = []
    for it in issues:
        labels = [lb["name"] for lb in it.get("labels", [])]
        if LAPSED_LABEL not in labels:
            continue
        closed = parse_ts(it.get("closed_at") or "") if it.get("state") == "closed" else None
        if it.get("state") == "closed" and (closed is None or closed < since):
            continue
        out.append({"number": it["number"], "title": it["title"], "url": it["html_url"],
                    "state": it.get("state"), "closed_ts": closed,
                    "ttl": time_to_live(it.get("body"))})
    out.sort(key=lambda q: q["number"], reverse=True)
    return out


def build(index_text: str | None, gov: list[dict], issues: list[dict], now: dt.datetime,
          since: dt.datetime, parse_ts, time_to_live, ttl_date) -> dict:
    """The section's model. `gov` is generate.build()'s open-question list, whose items
    already carry `fields` (question_fields()) and `ttl`; this adds the TTL state."""
    today = now.date()
    records = parse_index(index_text)
    questions = [{**q, **q["fields"], **ttl_state(ttl_date(q["ttl"]), today)} for q in gov]
    return {"records": recent_records(records, today),
            "older_flagged": older_flagged(records, today),
            "index_found": index_text is not None,
            "questions": questions,
            "by_shape": counts(questions, "shape"), "by_domain": counts(questions, "domain"),
            "lapsed": lapsed(issues, since, parse_ts, time_to_live)}


# ---------------------------------------------------------------- rendering

NONE = '<span class="muted">none</span>'
DASH = '<span class="muted">—</span>'


def esc(x) -> str:
    return html.escape("" if x is None else str(x))


def inline(text: str) -> str:
    """A ruling cell: escaped, with `code` spans kept as <code>."""
    parts = esc(text).split("`")
    return "".join(f"<code>{p}</code>" if i % 2 else p for i, p in enumerate(parts))


def records_html(g: dict, repo: str) -> str:
    base = f"https://github.com/{esc(repo)}/blob/main/governance"
    if not g["records"]:
        why = "none" if g["index_found"] else f"{INDEX_PATH} not found"
        return f'<p class="muted">{esc(why)}</p>'
    rows = []
    for r in g["records"]:
        flag = {"passed": ' <span class="pill s-blocked">review date passed</span>'
                          '<br><span class="muted">not precedent until re-affirmed</span>',
                "soon": ' <span class="pill s-idle">review due soon</span>'}.get(r["flag"], "")
        rows.append(f'<tr><td><a href="{base}/{esc(r["file"])}">{esc(r["id"])}</a></td>'
                    f"<td>{inline(r['ruling'])}</td><td>{esc(r['domain'])}</td>"
                    f"<td>{esc(r['shape'])}</td><td>{esc(r['status'])}</td>"
                    f"<td>{esc(r['review_by_text'])}{flag}</td></tr>")
    return ('<div class="scroll"><table><tr><th>Record</th><th>Ruling</th><th>Domain</th>'
            f'<th>Shape</th><th>Status</th><th>Review by</th></tr>{"".join(rows)}</table></div>'
            f'{older_html(g, base)}<p class="muted"><a href="https://github.com/{esc(repo)}/blob/main/{INDEX_PATH}">'
            "Full index</a></p>")


def older_html(g: dict, base: str) -> str:
    """One line naming older records whose review date has passed or is due soon."""
    if not g["older_flagged"]:
        return ""
    words = {"passed": "review date passed", "soon": "review due"}
    bits = [f'<a href="{base}/{esc(r["file"])}">{esc(r["id"])}</a> '
            f'({words[r["flag"]]} {esc(r["review_by"])})' for r in g["older_flagged"]]
    return f'<p>Older records to review: {", ".join(bits)}</p>'


def ttl_html(q: dict) -> str:
    if q["ttl"] is None:
        return '<span class="muted">none given</span>'
    if q["ttl_date"] is None:
        return f'{esc(q["ttl"])}<br><span class="muted">no date</span>'
    if q["past_ttl"]:
        return (f'{esc(q["ttl_date"])}<br><span class="pill s-blocked">past TTL</span>'
                f' <span class="muted">{-q["days_left"]}d ago</span>')
    return f'{esc(q["ttl_date"])}<br><span class="muted">{q["days_left"]}d left</span>'


def questions_html(g: dict, now: dt.datetime, ago, stamp) -> str:
    if not g["questions"]:
        return '<p class="muted">None.</p>'

    def line(name, pairs):
        return f"{name}: " + ", ".join(f"{esc(k)} {n}" for k, n in pairs)

    rows = []
    for q in g["questions"]:
        shape = (f'{esc(q["shape"])}<br><span class="muted">suggested</span>'
                 if q["shape_suggested"] else esc(q["shape"]) if q["shape"]
                 else DASH)
        blocking = {True: "yes", False: "no", None: DASH}[q["blocking"]]
        waiting = ", ".join(f"{esc(s['role'])} <code>{esc(s['session_id'][:8])}</code>"
                            for s in q["waiting"])
        labels = [lb for lb in q["labels"]
                  if not lb.startswith(SHAPE_LABEL) and lb != BLOCKING_LABEL]
        rows.append(f"<tr><td><a href=\"{esc(q['url'])}\">#{q['number']}</a> {esc(q['title'])}"
                    + (f'<br><span class="muted">{esc(", ".join(labels))}</span>' if labels else "")
                    + f"</td><td>{esc(q['domain']) if q['domain'] else DASH}</td>"
                    f"<td>{shape}</td><td>{blocking}</td>"
                    f"<td title=\"{esc(stamp(q['created_ts']))}\">{esc(ago(q['created_ts'], now))}</td>"
                    f"<td>{ttl_html(q)}</td><td>{waiting or NONE}</td></tr>")
    return (f'<p class="muted">{line("By shape", g["by_shape"])} · '
            f'{line("by domain", g["by_domain"])}</p>'
            '<div class="scroll"><table><tr><th>Question</th><th>Domain</th><th>Shape</th>'
            '<th>Blocking</th><th>Opened</th><th>Time to live</th><th>Sessions waiting</th></tr>'
            f'{"".join(rows)}</table></div>')


def lapsed_html(g: dict, days: int) -> str:
    note = ('<p class="muted">A lapsed default stands but is not precedent: the next agent '
            "to hit the same situation asks again (GOVERNANCE.md §8).</p>")
    if not g["lapsed"]:
        return f'<p class="muted">None open or closed in the last {days} days.</p>'
    items = []
    for q in g["lapsed"]:
        state = "open" if q["state"] == "open" else "closed"
        ttl = f", time to live {esc(q['ttl'])}" if q["ttl"] else ", no time to live given"
        items.append(f'<li><a href="{esc(q["url"])}">#{q["number"]}</a> {esc(q["title"])}'
                     f' <span class="muted">({state}{ttl})</span></li>')
    return f'<ul>{"".join(items)}</ul>{note}'


def render(g: dict, repo: str, now: dt.datetime, days: int, ago, stamp) -> str:
    return "\n".join([
        "<h2>Governance</h2>",
        f"<h3>Recent decision records</h3>{records_html(g, repo)}",
        f"<h3>Open gov questions ({len(g['questions'])})</h3>{questions_html(g, now, ago, stamp)}",
        f"<h3>Lapsed questions</h3>{lapsed_html(g, days)}",
    ])
