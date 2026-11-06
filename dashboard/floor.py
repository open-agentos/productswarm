"""On the floor: a card per active or blocked session, from heartbeat events (#403, part 4 of #397).

Today's remote events carry the role, model, time, event type, `issue`, `pr`, `gov_question`
and `tools`, the distinct tool names used since the previous event (heartbeat/SCHEMA.md). So a
card shows the role, model, how long the session has run (first event to now), plain words from
its latest event and that event's tool names, and an activity line: events per 5-minute slot over
the last 30 minutes. In place of counts (files read or edited, tests run), which today's events
can't give, it says how many of those slots used each kind of tool. A new captured field, such
as a per-event tool-call count, is a GOV-0002 `security` question, not something this module adds.

Idle sessions share one quiet line ("idle: docs 40 min, reviewer 2 h"). Stopped ones aren't on
the floor, and nor are sessions that never acted (generate.derive()'s `never_acted`, #454). Nothing here carries tokens or cost (GOV-0014; #397).

Under the cards, the watcher's state (#459): what `swarm watch` is running, holding and
skipping, and its recent failures, from the `[watch]` issue's body (#458, GOV-0025).

Reads only the events and open issues generate.build() already has: no API calls.
"""
from __future__ import annotations

import datetime as dt
import functools
import html
import json
import re
import sys
from pathlib import Path

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
    """The floor from (session, its events) pairs, in the sessions' page order.
    Sessions that never acted (#454) are left out."""
    sessions = [(s, ev) for s, ev in sessions if not s.get("never_acted")]
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


def render(floor: dict | None, repo: str, watch: dict | None = None) -> str:
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
    out.append(render_watcher(watch, repo))
    return "\n".join(out)


# ---------------------------------------------------------------- the watcher (#459)
# `swarm watch` publishes its public state (launcher/watch.py's public_state(), #456) into the
# body of one `[watch]` issue the owner opened (#458, GOV-0025). The floor reads that body from
# the open issues generate.fetch() already lists, so it adds no API calls. It keeps only the
# fields #456 defines, each checked by type and shape; anything else is dropped. A reason is
# kept only if it is one of watch.REASONS' sentences, so no text from another issue gets in.

WATCH_MARKER = "<!-- productswarm-watch -->"    # launcher/watch.py's WATCH_MARKER
STALE_CHECKS = 2       # as `swarm status`: older than two intervals is stale (watch.STALE_CHECKS)
LISTS = ("running", "held", "skipped", "failed")
ENDING_WORDS = {"at_cap": "at its cap", "error": "error", "limited": "usage limit",
                "no_result": "no result"}

_ROLE = re.compile(r"[a-z0-9-]{1,40}")
_KIND = re.compile(r"[a-z-]{1,20}")
_CODE = re.compile(r"[a-z_]{1,20}")
_REF = re.compile(r"(?:PR )?#\d{1,7}")


@functools.cache
def reasons() -> dict[str, re.Pattern]:
    """watch.REASONS as patterns, each sentence's {fields} as integers: the only reasons
    the floor shows. Empty if launcher/watch.py can't be imported (reasons are then dropped)."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "launcher"))
        import watch
        table = watch.REASONS
    except Exception:
        return {}
    return {code: re.compile(re.sub(r"\\\{\w+\\\}", r"\\d{1,4}", re.escape(s)))
            for code, s in table.items()}


def _ts(v) -> dt.datetime | None:
    if not isinstance(v, str) or len(v) > 40:
        return None
    try:
        t = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t.astimezone(dt.timezone.utc) if t.tzinfo else None


def _str(v, pattern: re.Pattern) -> str | None:
    return v if isinstance(v, str) and pattern.fullmatch(v) else None


def _entry(name: str, x, known: dict[str, re.Pattern]) -> dict | None:
    """One list entry with only #456's fields, or None if any is missing or the wrong shape."""
    if not isinstance(x, dict):
        return None
    out = {"ref": _str(x.get("ref"), _REF), "kind": _str(x.get("kind"), _KIND)}
    if name == "running":
        out |= {"role": _str(x.get("role"), _ROLE), "started": _ts(x.get("started"))}
    elif name == "failed":
        ending = x.get("ending")
        out |= {"ending": ending if ending in ENDING_WORDS else None, "ended": _ts(x.get("ended"))}
    else:
        code, reason = _str(x.get("code"), _CODE), x.get("reason")
        ok = code in known and isinstance(reason, str) and known[code].fullmatch(reason)
        out |= {"code": code, "reason": reason if ok else None, "since": _ts(x.get("since"))}
        # A reason that isn't a known sentence is dropped, not the entry.
        return None if None in (out["ref"], out["kind"], code, out["since"]) else out
    return out if None not in out.values() else None


def parse_watch(body: str | None) -> dict | None:
    """The [watch] issue body's state, or None if it has no readable json block with a
    `checked` time. Each list keeps its well-formed entries; other keys are dropped."""
    m = re.search(r"```json\n(.*?)\n```", (body or "").replace("\r\n", "\n"), re.S)
    try:
        got = json.loads(m.group(1)) if m else None
    except ValueError:
        return None
    if not isinstance(got, dict) or (checked := _ts(got.get("checked"))) is None:
        return None
    known = reasons()
    out = {"checked": checked}
    for name in LISTS:
        items = got.get(name)
        items = items if isinstance(items, list) else []
        out[name] = [e for e in (_entry(name, x, known) for x in items[:50]) if e]
    return out


def watcher(issues: list[dict], owner: str | None, now: dt.datetime,
            interval: float | None) -> dict:
    """The watcher's state for the floor, from the open issues generate.fetch() lists.
    `status` is "ok", "missing" (no open [watch] issue), "not_owner" (marked issues exist,
    but the owner opened none of them; GOV-0025), "several" (the owner opened more than one,
    which the watcher won't publish to either) or "malformed" (no readable state).
    `checked` is when the state last changed: the watcher publishes only on a change (#458).
    `stale` is True when that is older than STALE_CHECKS intervals."""
    marked = [i for i in issues if i.get("state") == "open" and "pull_request" not in i
              and (i.get("body") or "").lstrip().startswith(WATCH_MARKER)]
    mine = [i for i in marked if owner and
            ((i.get("user") or {}).get("login") or "").lower() == owner.lower()]
    if not marked:
        return {"status": "missing"}
    if not mine:
        return {"status": "not_owner"}
    if len(mine) > 1:
        return {"status": "several"}
    got = parse_watch(mine[0].get("body"))
    if got is None:
        return {"status": "malformed", "issue": mine[0]["number"]}
    age = int((now - got["checked"]).total_seconds() // 60)
    return {"status": "ok", "issue": mine[0]["number"], **got, "age_minutes": max(age, 0),
            "stale": interval is not None and age > STALE_CHECKS * interval}


def watcher_lines(w: dict, ref=lambda r: r) -> list[str]:
    """One plain line per item: "builder on #405 since 11:09", "held: #407, 2 of 2 running",
    "skipped: #439, the role isn't in swarm.toml", "failed: #51 build, at its cap, 10:02".
    `ref(r)` formats a ref ("#405" or "PR #405"); the default is plain text."""
    hm = lambda t: t.strftime("%H:%M")  # noqa: E731
    out = [f"{r['role']} on {ref(r['ref'])} since {hm(r['started'])}" for r in w.get("running", [])]
    for name in ("held", "skipped"):
        for h in w.get(name, []):
            why = (h["reason"] or "").split(": ", 1)[-1] if h["reason"] else h["code"]
            out.append(f"{name}: {ref(h['ref'])}, {why}" if why != name else f"{name}: {ref(h['ref'])}")
    out += [f"failed: {ref(f['ref'])} {f['kind']}, {ENDING_WORDS[f['ending']]}, {hm(f['ended'])}"
            for f in w.get("failed", [])]
    return out


WATCHER_NOTES = {
    "missing": "No [watch] issue: swarm watch's state isn't published (launcher/README.md).",
    "not_owner": "The [watch] issue wasn't opened by the owner, so the floor doesn't show it (GOV-0025).",
    "several": "The owner has more than one open [watch] issue; close all but one.",
    "malformed": "Can't read swarm watch's state from the [watch] issue.",
}


def render_watcher(w: dict | None, repo: str) -> str:
    esc = lambda x: html.escape("" if x is None else str(x))  # noqa: E731
    w = w or {"status": "missing"}
    out = ['<div class="watcher"><h3>The watcher</h3>']
    if w["status"] != "ok":
        out.append(f'<p class="muted">{esc(WATCHER_NOTES[w["status"]])}</p></div>')
        return "\n".join(out)

    def ref(r: str) -> str:
        n = r.rsplit("#", 1)[1]
        path = "pull" if r.startswith("PR ") else "issues"
        return (f'{"PR " if path == "pull" else ""}'
                f'<a href="https://github.com/{esc(repo)}/{path}/{n}">#{n}</a>')

    when = f'{span(w["age_minutes"])} ago, at {w["checked"].strftime("%H:%M")} UTC'
    if w["stale"]:
        # The watcher publishes only when its state changes (#458), so an old time can mean a
        # quiet loop or a stopped one: the lists are shown as of then, not as current.
        out.append(f'<p class="stale">watcher last published {esc(when)}: these lists are as '
                   f'of then, and it may have stopped (it publishes only when they change)</p>')
    else:
        out.append(f'<p class="muted">as of {esc(when)}</p>')
    lines = watcher_lines(w, ref)
    if lines:
        out.append("<ul>" + "".join(f"<li>{line}</li>" for line in lines) + "</ul>")
    else:
        out.append('<p class="muted">Nothing running, held, skipped or failed.</p>')
    out.append("</div>")
    return "\n".join(out)
