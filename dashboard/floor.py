"""On the floor: a card per active or blocked session, from heartbeat events (#403, part 4 of #397).

Today's remote events carry the role, model, time, event type, `issue`, `pr`, `gov_question`
and `tools`, the distinct tool names used since the previous event (heartbeat/SCHEMA.md). So a
card shows the role, model, how long the session has run (first event to now), plain words from
its latest event and that event's tool names, and an activity line: events per 5-minute slot over
the last 30 minutes. In place of counts (files read or edited, tests run), which today's events
can't give, it says how many of those slots used each kind of tool. A new captured field, such
as a per-event tool-call count, is a GOV-0002 `security` question, not something this module adds.

Idle sessions share one quiet line ("idle: docs 40 min, reviewer 2 h"). Stopped ones aren't on
the floor. Nothing here carries tokens or cost (GOV-0014; #397).

Reads only the events generate.build() already parsed: no API calls.
"""
from __future__ import annotations

import datetime as dt
import html

SLOT = dt.timedelta(minutes=5)
SLOTS = 6                   # 30 minutes of 5-minute slots

# Tool name -> kind of work. Tools not listed (WebFetch, Agent, ...) say nothing about it.
KINDS = {"Edit": "editing", "Write": "editing", "NotebookEdit": "editing",
         "Bash": "commands",
         "Read": "reading", "Grep": "reading", "Glob": "reading"}
KIND_ORDER = ("editing", "reading", "commands")

# The plain words, first match wins: (situation, kind, words).
#   situation: "blocked" for a blocked session, else its latest event type; "*" is any.
#   kind: a kind in the latest event's tools (KINDS); "*" is any, including no tools.
#   words: {on} is " on #392" (or " on PR #394", or nothing); {pr} and {gov_question} are refs.
# Editing outranks commands, which outrank reading, so "Reading code" means only
# Read/Grep/Glob. A later capture change (GOV-0002) adds rows here, not logic.
TEMPLATES = (
    ("blocked", "*", "Waiting on {gov_question}"),
    ("pr_opened", "*", "Opened PR {pr}"),
    ("*", "editing", "Editing files{on}"),
    ("*", "commands", "Running commands{on}"),
    ("*", "reading", "Reading code{on}"),
    ("session_started", "*", "Starting up{on}"),
    ("*", "*", "Working{on}"),
)


def parse_ts(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def kinds(tools) -> set[str]:
    return {KINDS[t] for t in tools or () if t in KINDS}


def template(situation: str, tool_kinds: set[str]) -> str:
    for sit, kind, words in TEMPLATES:
        if sit in ("*", situation) and (kind == "*" or kind in tool_kinds):
            return words
    raise AssertionError("TEMPLATES ends with a catch-all row")


def words(card: dict, ref=lambda kind, n: f"#{n}") -> str:
    """The card's plain words. `ref(kind, n)` formats an issue, PR or question number
    (kind "issue" or "pr"); the default is plain text, the page passes links."""
    if card["issue"]:
        on = f" on {ref('issue', card['issue'])}"
    elif card["pr"]:
        on = f" on PR {ref('pr', card['pr'])}"
    else:
        on = ""
    return card["template"].format(
        on=on, pr=ref("pr", card["pr"]) if card["pr"] else "",
        gov_question=ref("issue", card["gov_question"]) if card["gov_question"] else "")


def slots(events: list[dict], now: dt.datetime) -> list[list[dict]]:
    """The last 30 minutes' events in 5-minute slots, oldest slot first."""
    out = [[] for _ in range(SLOTS)]
    for e in events:
        age = now - parse_ts(e["ts"])
        if dt.timedelta(0) <= age < SLOT * SLOTS:
            out[SLOTS - 1 - int(age // SLOT)].append(e)
    return out


def card(s: dict, events: list[dict], now: dt.datetime) -> dict:
    """One session's card: `s` is a session generate.derive() made, `events` its events."""
    latest = events[-1] if events else {}
    situation = "blocked" if s["status"] == "blocked" else latest.get("event", "")
    window = slots(events, now)
    used = [set().union(*(kinds(e.get("tools")) for e in slot)) for slot in window]
    c = {"session_id": s["session_id"], "role": s["role"], "model": s["model"],
         "status": s["status"], "started_ts": s["started_ts"],
         "run_minutes": int((now - s["started_ts"]).total_seconds() // 60) if s["started_ts"] else None,
         "issue": s["issue"], "pr": s["pr"], "gov_question": s["gov_question"],
         "template": template(situation, kinds(latest.get("tools"))),
         "events_per_slot": [len(slot) for slot in window],
         "slots_used": {k: sum(k in u for u in used) for k in KIND_ORDER}}
    c["activity"] = words(c)
    return c


def build(sessions: list[tuple[dict, list[dict]]], now: dt.datetime) -> dict:
    """The floor from (session, its events) pairs, in the sessions' page order."""
    cards = [card(s, ev, now) for s, ev in sessions if s["status"] in ("active", "blocked")]
    idle = [{"session_id": s["session_id"], "role": s["role"],
             "idle_minutes": int((now - s["last_ts"]).total_seconds() // 60) if s["last_ts"] else None}
            for s, _ in sessions if s["status"] == "idle"]
    return {"cards": cards, "idle": idle}


def span(minutes: int | None) -> str:
    """40 min, 2 h, 2 h 5 min, 3 d."""
    if minutes is None:
        return "no events"
    if minutes < 60:
        return f"{minutes} min"
    if minutes < 24 * 60:
        h, m = divmod(minutes, 60)
        return f"{h} h {m} min" if m else f"{h} h"
    return f"{minutes // (24 * 60)} d"


def idle_line(idle: list[dict]) -> str:
    return "idle: " + ", ".join(f"{i['role']} {span(i['idle_minutes'])}" for i in idle)


def sparkline(counts: list[int]) -> str:
    """Events per 5-minute slot as inline SVG bars, oldest left. Plain SVG, no script."""
    w, gap, h = 10, 3, 22
    top = max(counts) or 1
    bars = []
    for i, n in enumerate(counts):
        bh = max(1, round(h * n / top)) if n else 1
        cls = "bar" if n else "bar zero"
        bars.append(f'<rect class="{cls}" x="{i * (w + gap)}" y="{h - bh}" width="{w}" height="{bh}"/>')
    label = ("events per 5 minutes, last 30 minutes, oldest first: "
             + ", ".join(str(n) for n in counts))
    width = len(counts) * (w + gap) - gap
    return (f'<svg class="spark" role="img" aria-label="{label}" width="{width}" height="{h}" '
            f'viewBox="0 0 {width} {h}">{"".join(bars)}</svg>')


def render(floor: dict | None, repo: str) -> str:
    esc = lambda x: html.escape("" if x is None else str(x))  # noqa: E731

    def ref(kind: str, n: int) -> str:
        path = "pull" if kind == "pr" else "issues"
        return f'<a href="https://github.com/{esc(repo)}/{path}/{n}">#{n}</a>'

    floor = floor or {"cards": [], "idle": []}
    out = ["<h2>On the floor</h2>"]
    if floor["cards"]:
        out.append('<div class="floor">')
        for c in floor["cards"]:
            used = " · ".join(f"{k} in {n} of {SLOTS}" for k, n in c["slots_used"].items())
            ran = f'running {span(c["run_minutes"])}' if c["run_minutes"] is not None else ""
            out.append(
                f'<div class="card s-{esc(c["status"])}">'
                f'<div class="who"><span class="role">{esc(c["role"])}</span> '
                f'<span class="mono muted">{esc(c["model"])}</span></div>'
                f'<div class="what">{words(c, ref)}</div>'
                f'<div class="muted">{esc(ran)}</div>'
                f'{sparkline(c["events_per_slot"])}'
                f'<div class="muted used">last 30 min, 5-min slots: {esc(used)}</div>'
                "</div>")
        out.append("</div>")
    else:
        out.append('<p class="muted">No session is working.</p>')
    if floor["idle"]:
        out.append(f'<p class="muted idle">{esc(idle_line(floor["idle"]))}</p>')
    return "\n".join(out)
