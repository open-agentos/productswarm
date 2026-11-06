"""swarm watch: the v2 wake-up loop (GOV-0009). W1 (#89) is --dry-run; W2 (#90) starts;
#113 adds GOV-0011's [respond] trigger; #136 holds overlapping builds (the owner's answer on #127).

    launcher/swarm watch                          start sessions, within swarm.toml's [watch]
    launcher/swarm watch --dry-run [--interval MINUTES]   print what it would start

Every interval it reads the same GitHub and heartbeat state as `swarm inbox` and works
out each trigger below. --dry-run prints them and starts nothing. For each one it would
start, it also prints the full headless command on the next line, indented (#147), or why
it has none (for example, the role has no spend_cap_usd).

| kind   | trigger                                                                 | would start          |
|--------|-------------------------------------------------------------------------|----------------------|
| review | open, non-draft PR whose head the reviewer App hasn't reviewed          | a reviewer pass      |
| build  | issue whose most recent `ready` was added by the owner (GOV-0006),      | builder on the issue |
|        | with no open PR closing it                                              |                      |
| record | gov:question whose most recent `gov:ruled` was added by the owner, that | docs on the question |
|        | needs a record (GOV-0007), with no open PR closing it                   |                      |
| answer | gov:question whose most recent `ready` was added by the owner, again    | its "Raised by" role |
|        | when the owner then adds `gov:ruled` (#495)                             | (planner if owner)   |
| respond| open, non-draft PR the builder App opened, whose latest reviewer review | builder on the PR    |
|        | at its head is CHANGES_REQUESTED, with Authority not `fail`, for at     | (GOV-0011)           |
|        | most 2 rounds                                                           |                      |

[respond] counts the reviewer's CHANGES_REQUESTED reviews on the PR from GitHub's review
history, so the count holds across restarts. A third request starts nothing, and an
Authority: fail review at the head starts nothing either, and nor do requested changes
on a PR another App opened, such as a docs ruling PR (#178): the builder responds only on
its own PR (GOV-0011). `needs_you()` lists all three as needing the owner. A PR that doesn't close exactly one issue is skipped with a reason.

[answer] on a ruling (#495): a question that is already `ready` when the owner rules it
fires [answer] again, keyed on the owner's `gov:ruled` event (`answer:N:<event id>`), so
the asker (the planner, for an owner-raised question) acts on the ruling. Its key is the
later of the owner's two label events; `ready` must still be the owner's (GOV-0006). When
[record] is also due on that question, docs goes first: [answer] is held until [record]
has been acted on, and then waits through busy() until docs has stopped.

An issue or question with a live session on it starts nothing (`swarm launch`'s refusal
rule), so it can fire later, once that session has stopped. The trigger is held, not
dropped (#488): --dry-run prints it, and a real check lists it in `swarm inbox`, with the
session holding it and how long it has been idle (held_by()). Past [watch] stale_minutes
(default 60) of idleness the reason says `stale` and names the `swarm stop` that frees the
issue; the loop still never stops the session itself. Each is printed or logged once per
holder state. Each trigger has an identity,
which is the PR head SHA (for [review] and [respond]) or the id of the owner's label event. A trigger prints once per
identity, so a new push or a fresh owner label is a new trigger. In dry-run the memory
lives only in the process, and nothing is written to disk.

Leaving [review] to Actions (#216, GOV-0019): with `review_in_actions = true` in
swarm.toml's [watch] table, every [review] trigger is listed as "left to Actions" and
starts nothing, in --dry-run and for real; the GitHub Actions reviewer workflow reviews
that head instead. It is logged once per head and never recorded in watch.json, so
setting the switch back to false (or disabling the workflow and setting it false) puts
the local loop back in charge of any head still unreviewed. [respond], [build], [answer]
and [record] are unchanged. Changing the switch is a `ci-and-workflows` call for the owner.

A review trigger is also quiet while a reviewer that swarm watch started is live: that
pass may have listed the PRs before this push, so the trigger waits for it to stop rather
than being covered by it. Reviewers the owner started (`swarm up`, `swarm launch`) don't
keep it quiet (#132): they are the owner's to steer, and GOV-0010 already leaves sessions
the owner starts out of the loop's counts.

Without --dry-run, each new trigger starts one fresh headless run (#147): `claude -p`
with the opener as its prompt, auto mode and explicit denies for merging and label edits
(GOV-0013), `--max-budget-usd` from the role's spend_cap_usd and `--max-turns` from
[watch] max_turns (GOV-0012), and its JSON result written to
~/.productswarm/launcher/<session id>.result.json (swarm.Launcher.command()). It ends when
it is done or at either limit; Claude Code ends it, not the loop. It still opens in its
own Terminal window, as `swarm launch` does, so `swarm ls` and `swarm stop` work as before.
Every start is within the limits in GOV-0010 (the owner's answer on #88):

- at most [watch] max_live live sessions that the loop started; past that, a trigger is
  held, listed in `swarm inbox`, and started in order once a slot frees up;
- only roles that set spend_cap_usd in swarm.toml; any other trigger is skipped and
  listed in `swarm inbox`, and starts once the role has a cap;
- every [watch] interval_minutes. swarm.toml is read again on every check, and a [watch]
  table with no max_turns starts nothing, as a missing [watch] table doesn't.

A [build] trigger is also held while other work from the same GOV record is in flight
(#136, the owner's answer on #127; direction, not a ruling). An issue's GOV records are
the GOV-NNNN ids in its title only: bodies cite rulings in passing. A build for #N is
held while N's title shares a GOV id with the title of
- another issue a live builder is on: a heartbeat builder session that isn't stopped, or
  a launcher builder entry with no heartbeat yet, including builders started by hand and
  one started earlier in the same check; or
- an issue that an open PR, draft or not, closes.
The hold is listed in `swarm inbox` with what it waits on, logged once per reason, and
starts held-longest-first once the overlap clears. An issue whose title cites no GOV id
is never held this way, and [respond], [review], [record] and [answer] never are.

A [build] is also held while an issue its body's `**Waits on:**` line names is still open
(#490): the #N refs on that line; "nothing" or no line means none. The hold is listed in
`swarm inbox` as `held: waits on #N`, shown by --dry-run too, and never goes into "acted",
so the build starts on the first check after every listed issue is closed.

Before each start it runs `swarm launch`'s refusal checks again on fresh GitHub data. A
refusal is logged and the trigger is done. What it has acted on is kept in
~/.productswarm/launcher/watch.json, so a restart starts nothing twice. One reviewer
pass covers every review trigger present when it starts.

How each run ended (#149): when a run the loop started is no longer live, the loop reads
its result file and records, against the trigger in watch.json's "runs", the session id,
Claude Code's total_cost_usd (a client-side estimate that stays local: GOV-0002/3/4) and
its ending: done, ended at cap (--max-budget-usd or --max-turns), error, or no result (no
file or no JSON result, for example after `swarm stop`), or limited (#489, below). Unless
it was limited, the trigger stays done, so the loop never restarts it by itself; `swarm
inbox` lists a run that ended at cap, with its ref and cost, so the owner can decide
whether to restart it, and lists every recorded cost from the last RUNS_DAYS days. A kept worktree is tidy()'s job, as for any session.

A usage or rate limit (#489): a run whose result has api_error "usage_limit_reached" or
api_error_status 429 ends "limited". Its trigger leaves "acted", as do the review
triggers its reviewer pass covered, so they fire again with no label change. Because the
limit is account-wide, every start is held, with the reason `held: usage limit (until
HH:MM)`, until the reset time the result names ("resets 12pm (Europe/London)") or, if it
names none the loop can read, LIMIT_HOLD after the run ended. The loop says so once.

Each run it starts gets a Stop hook (stophook.py, #148) that keeps it going until its
role's done-condition is met; see that module for the conditions and the guards.

`swarm cost` (#176, cost_text()) prints those recorded costs grouped by the PR each run
served, with a read-only `gh pr list` to find the PR that closes a run's issue. It only
prints: no cost goes to GitHub or the repo.

One watcher at a time (#273): without --dry-run, swarm watch holds an exclusive,
non-blocking fcntl.flock on ~/.productswarm/launcher/watch.lock for its whole life, with
its pid in the file. A second one exits at once, naming that pid. The kernel drops the
lock when the process ends, even on a crash or `kill`, so there is no stale lock to clean
up. --dry-run takes no lock and writes no watch.json, so it is safe beside a running one.

It never stops a session (GOV-0008), never adds or removes labels, and never comments,
approves or merges: its only GitHub calls are reads. Sessions it starts are recorded
with by="watch", and `swarm ls` shows them as "by watch".

GitHub reads go through gather(); triggers() is pure, so tests feed it canned data.
"""
from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
import re
import tempfile
import time
import uuid
import zoneinfo
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

import manifest
import swarm

REVIEWER = swarm.dashboard().REVIEWER
DEFAULT_INTERVAL = 5          # minutes, for --dry-run when swarm.toml has no [watch] table
STATE_FILE = "watch.json"     # in the launcher's state directory
LOCK_FILE = "watch.lock"      # held by the one running watcher (#273)
REF_RE = re.compile(r"#(\d+)")
GOV_RE = re.compile(r"\bGOV-\d{4}\b")
WAITS_RE = re.compile(r"^\s*\*\*Waits on:\*\*(.*)$", re.MULTILINE | re.IGNORECASE)
LEFT_TO_ACTIONS = ("left to Actions: review_in_actions = true in swarm.toml, so the GitHub "
                   "Actions reviewer reviews this head (GOV-0019)")
DEFAULT_STALE = 60            # [watch] stale_minutes when swarm.toml doesn't set it (#488)
RUNS_DAYS = 7                 # how long `swarm inbox` lists a recorded run, and watch.json keeps it

# How a headless run ended, from the `subtype` of its --output-format json result: the
# SDKResultMessage type in the Claude Code Agent SDK reference (#149). Any other subtype,
# or "success" with is_error set, is an error.
DONE, AT_CAP, ERROR, NO_RESULT = "done", "ended at cap", "error", "no result"
LIMITED = "limited"           # a usage or rate limit: tried again after the hold (#489)
LIMIT_HOLD = dt.timedelta(minutes=30)     # when the result names no reset time
RESETS_RE = re.compile(r"\bresets (\d{1,2})(?::(\d{2}))?\s*([ap]m)\b(?:\s*\(([^)]+)\))?", re.I)
CAPS = {"error_max_budget_usd": "budget (--max-budget-usd)",
        "error_max_turns": "turns (--max-turns)"}


@dataclass(frozen=True)
class Trigger:
    key: str                  # identity: a new key is a new trigger
    kind: str                 # review | build | record | answer | respond
    ref: str                  # "PR #12" or "#49"
    why: str
    role: str | None = None
    command: str | None = None
    skipped: str | None = None
    issue: int | None = None  # the issue the session works on (none for a reviewer pass)
    pr: int | None = None     # [respond]: the PR the builder responds on
    after: str | None = None  # [answer]: the [record] key that must be acted on first (#495)
    held: str | None = None   # why it is held: a live session on the issue (#488), or [build]'s
                              # open Waits-on issues (#490); a held trigger starts nothing
    once: str | None = None   # what changes the held reason enough to log it again (#488)

    def line(self) -> str:
        if self.held:
            return f"[{self.kind}] {self.ref} {self.why} -> {self.held}"
        if self.skipped:
            return f"[{self.kind}] {self.ref} {self.why} -> skipped: {self.skipped}"
        first = " once docs has stopped ([record] first)" if self.after else ""
        return f"[{self.kind}] {self.ref} {self.why} -> would start {self.command}{first}"


def launch_cmd(role: str, n: int, pr: int | None = None) -> str:
    return f"`launcher/swarm launch {role} --issue {n}" + (f" --pr {pr}`" if pr else "`")


# ---------------------------------------------------------------- the template body

def template_field(body: str | None, label: str) -> str | None:
    """The first line of a Governance question template answer, e.g. "Raised by"."""
    m = re.search(rf"^###\s*{re.escape(label)}\s*\n+\s*(\S[^\n]*?)\s*$", body or "", re.M)
    return m.group(1) if m and m.group(1) != "_No response_" else None


RECORD_LINE = re.compile(r"^\s*record:\s*yes\s*$", re.I | re.M)


def needs_record(body: str | None, comments: list[dict] = (), owner: str | None = None) -> str | None:
    """Why a question needs a record under GOV-0007, else None.

    The body's ratings cover the governance domain, one-way and external. GOV-0007's other
    case, "the owner says so in the answer", is a comment by the owner with a line
    `Record: yes` on its own (#501). Nobody else's comment counts, agents included."""
    domain = (template_field(body, "Domain") or "").strip().lower()
    rev = (template_field(body, "Reversibility") or "").strip().lower()
    blast = (template_field(body, "Blast radius") or "").strip().lower()
    if domain == "governance":
        return "domain governance"
    if rev == "one-way":
        return "one-way"
    if blast == "external":
        return "blast radius external"
    if owner and any((c.get("user") or {}).get("login") == owner and RECORD_LINE.search(c.get("body") or "")
                     for c in comments):
        return "the owner asked in the answer"
    return None


def raised_by(body: str | None, roles: set[str], owner: str | None = None) -> tuple[str | None, str]:
    """(role, "") from the "Raised by" field, or (None, why not).

    The asker is the field's first word, optionally in the `-- role` signature form, as
    the planner, builder and docs write it ("planner, on #167 (...)"). A role named later
    in the text isn't the asker (#271): "owner, after the first Actions reviewer test"
    doesn't start the reviewer. A question the owner raised ("owner", or the owner's login,
    with or without "@") starts the planner, which reads the answer and does what it
    directs (#455)."""
    text = template_field(body, "Raised by")
    if not text:
        return None, 'it has no "Raised by" field'
    m = re.match(r"(?:--\s*)?@?([a-z0-9][a-z0-9-]*)(?![a-z0-9'’])", text.lower())
    asker = m.group(1) if m else None
    if asker in roles:
        return asker, ""
    if asker in {"owner", (owner or "owner").lower()} and "planner" in roles:
        return "planner", ""
    return None, f'"Raised by" doesn\'t start with a known role or the owner ({text!r})'


# ---------------------------------------------------------------- triggers (pure)

@dataclass
class World:
    """One tick's reading of GitHub and the heartbeat. Plain data, so tests can build it."""
    model: dict                                      # generate.build() output
    issues: list[dict]                               # raw issues (generate.fetch)
    events: dict[int, list[dict]] = field(default_factory=dict)     # issue -> events, oldest first
    reviewed: dict[int, set[str]] = field(default_factory=dict)     # PR -> SHAs the reviewer reviewed
    comments: dict[int, list[dict]] = field(default_factory=dict)   # gov:ruled question -> comments (#501)


def owner_label(events: list[dict], name: str, owner: str) -> dict | None:
    """The owner's label event for `name`, if the most recent one is the owner's (GOV-0006)."""
    e = swarm.label_event(events, name)
    return e if e and (e.get("actor") or {}).get("login") == owner else None


def later(events: list[dict], a: dict | None, b: dict) -> bool:
    """Whether event a comes after event b in an issue's events (oldest first)."""
    if a is None:
        return False
    pos = {id(e): i for i, e in enumerate(events)}
    return pos.get(id(a), -1) > pos.get(id(b), -1)


def held_by(n: int, m: dict, started: list, now: dt.datetime | None,
            stale_minutes: int = DEFAULT_STALE) -> tuple[str, str] | None:
    """Why a live session on issue n holds its trigger (#488), as (reason, once), or None.

    The same sessions as swarm.holders(): heartbeat sessions on n that aren't stopped, and
    launcher entries on n with no heartbeat yet. A holder idle on the heartbeat for longer
    than stale_minutes makes the reason `stale:` and names the `swarm stop` that frees n;
    the watcher still never stops it (GOV-0008, #132). `once` changes only when a holder's
    status does, so the reason is logged once per state, not once per tick."""
    g = swarm.dashboard()
    names = {e.session_id: e.name for e in started}
    seen = {s["session_id"] for s in m["sessions"]}
    held, stale, once = [], [], []
    for s in m["sessions"]:
        if s["status"] == "stopped" or s["issue"] != n:
            continue
        name = names.get(s["session_id"])
        who = name or f"{s['role']} session {s['session_id']}"
        last, status = s.get("last_ts"), s["status"]
        if status == "idle" and last and now and now - last > dt.timedelta(minutes=stale_minutes):
            fix = (f"swarm stop {name} frees #{n}" if name else
                   f"it wasn't started by swarm, so stop it where it runs to free #{n}")
            stale.append(f"{who} idle {g.ago(last, now).removesuffix(' ago')}; {fix}")
            once.append(f"{who}:stale")
            continue
        state = (f"idle since {last:%H:%M} UTC" if status == "idle" and last else
                 f"blocked on #{s['gov_question']}" if status == "blocked" else status)
        held.append(f"{who} is live on #{n} ({state})")
        once.append(f"{who}:{status}")
    for e in started:
        if e.issue == n and e.session_id not in seen:
            held.append(f"{e.name} is live on #{n} (starting, no heartbeat yet)")
            once.append(f"{e.name}:starting")
    if not held and not stale:
        return None
    reason = f"stale: {'; '.join(stale)}" if stale else f"held: {' and '.join(held)}"
    return reason, "|".join(sorted(once))


def triggers(w: World, owner: str, started: list, roles: set[str], needs_you: Callable,
             is_tracking: Callable, review_in_actions: bool = False,
             now: dt.datetime | None = None, stale_minutes: int = DEFAULT_STALE) -> list[Trigger]:
    """Every trigger present now, in needs-you order then issue order. Nothing is filtered
    for novelty here; Watch does that. With review_in_actions, each [review] trigger is
    skipped as left to Actions (GOV-0019). A [record], [answer], [build] or [respond]
    trigger on an issue a live session holds comes back with `held` set, saying who holds
    it and whether that session is stale (#488); Watch starts nothing for it."""
    m, out = w.model, []
    items = needs_you(m)
    heads = {p["number"]: p.get("head") for p in m["prs"]}
    closing = {c["number"] for p in m["prs"] for c in p["closes"]}

    def busy(n: int) -> tuple[str, str] | None:
        return held_by(n, m, started, now, stale_minutes)

    def hold(t: Trigger, n: int) -> Trigger:
        h = busy(n)
        return replace(t, held=h[0], once=h[1]) if h else t

    reviewing = reviewers(m, started)
    prs = {p["number"]: p for p in m["prs"]}

    # Reviews and responses: the needs-you PR list is the open non-draft PRs.
    for it in items:
        if it["kind"] != "pr":
            continue
        n = int(REF_RE.search(it["ref"]).group(1))
        head = heads.get(n)
        if not head:
            continue
        if head not in w.reviewed.get(n, set()) and not reviewing:
            out.append(Trigger(key=f"review:{n}:{head}", kind="review", ref=f"PR #{n}",
                               why=f"head {head[:7]} not reviewed by the reviewer", role="reviewer",
                               command="a reviewer pass",
                               skipped=LEFT_TO_ACTIONS if review_in_actions else None))
        t = respond(prs[n], busy)
        if t:
            out.append(t)

    # Questions: the needs-you list holds every open gov:question, as `question` or `blocked`.
    questions = []
    for it in items:
        if it["kind"] in ("question", "blocked"):
            n = int(REF_RE.search(it["ref"]).group(1))
            if n not in questions:
                questions.append(n)
    raw = {i["number"]: i for i in w.issues}
    for n in sorted(questions):
        body, events = (raw.get(n) or {}).get("body"), w.events.get(n, [])
        labels = {lb.get("name") for lb in (raw.get(n) or {}).get("labels") or []}
        ruled = owner_label(events, "gov:ruled", owner) if "gov:ruled" in labels else None
        why_record = needs_record(body, w.comments.get(n, []), owner)
        record = None
        if ruled and why_record and n not in closing:
            record = hold(Trigger(key=f"record:{n}:{ruled.get('id')}", kind="record", ref=f"#{n}",
                                  why=f"gov:ruled by the owner, needs a record ({why_record})",
                                  role="docs", command=launch_cmd("docs", n), issue=n), n)
            out.append(record)
        ready = owner_label(events, "ready", owner) if "ready" in labels else None
        if ready:
            # #495: a ruling on a question that is already ready fires [answer] again.
            label, e = ("gov:ruled", ruled) if later(events, ruled, ready) else ("ready", ready)
            role, why_not = raised_by(body, roles, owner)
            out.append(hold(Trigger(key=f"answer:{n}:{e.get('id')}", kind="answer", ref=f"#{n}",
                                    why=f"{label} by the owner", role=role,
                                    command=launch_cmd(role, n) if role else None,
                                    skipped=None if role else why_not, issue=n,
                                    after=record.key if record and role else None), n))

    # Builds: ready, open, non-question, non-tracking issues with no open PR closing them
    # (that work is done and waits on the owner's merge).
    for it in sorted(w.issues, key=lambda i: i["number"]):
        n = it["number"]
        labels = {lb.get("name") for lb in it.get("labels") or []}
        if (it.get("state") != "open" or "pull_request" in it or "ready" not in labels
                or "gov:question" in labels or is_tracking(it) or n in closing):
            continue
        ready = owner_label(w.events.get(n, []), "ready", owner)
        if ready:
            t = hold(Trigger(key=f"build:{n}:{ready.get('id')}", kind="build", ref=f"#{n}",
                             why="ready by the owner", role="builder",
                             command=launch_cmd("builder", n), issue=n), n)
            waits = None if t.held else blocked(it.get("body"), w)
            out.append(replace(t, held=waits, once=waits) if waits else t)
    return out


def waits_on(body: str | None) -> list[int]:
    """The issues a task issue waits on: the #N refs in the first sentence of its body's
    first `**Waits on:**` line (#490). No line, a line that starts "nothing", or no #N means
    none. Prose after the first sentence ("nothing. Do this before #480 ...") doesn't count."""
    m = WAITS_RE.search(body or "")
    value = m.group(1).strip() if m else ""
    if not value or value.lower().startswith("nothing"):
        return []
    first = re.split(r"\.(?:\s|$)", value, maxsplit=1)[0]
    return sorted({int(x) for x in REF_RE.findall(first)})


def blocked(body: str | None, w: World) -> str | None:
    """Why a [build] is held because an issue its `**Waits on:**` line names is still open
    (#490), or None. Open means an open issue in this tick's reading; anything else counts
    as closed."""
    open_ = {i["number"] for i in w.issues if i.get("state") == "open" and "pull_request" not in i}
    still = [n for n in waits_on(body) if n in open_]
    return f"held: waits on {', '.join(f'#{n}' for n in still)}" if still else None


def respond(p: dict, busy: Callable[[int], tuple[str, str] | None]) -> Trigger | None:
    """GOV-0011's [respond] trigger for one open, non-draft PR, or None.

    Oversteps, a third request and requested changes on a PR the builder didn't open (#178)
    are the owner's: needs_you() lists those PRs instead."""
    g = swarm.dashboard()
    r, n, head = p["reviewer"], p["number"], p["head"]
    if r["at_head"] != g.CHANGES or p["needs_owner"]:
        return None
    key = f"respond:{n}:{head}"
    why = f"changes requested at {head[:7]} (round {r['changes_requested']} of {g.ROUNDS})"
    closes = [c["number"] for c in p["closes"]]
    if len(closes) != 1:
        return Trigger(key=key, kind="respond", ref=f"PR #{n}", why=why, role="builder", pr=n,
                       skipped=f"it closes {len(closes)} issues, and the builder responds only on "
                               f"a PR that closes exactly one")
    h = busy(closes[0])
    return Trigger(key=key, kind="respond", ref=f"PR #{n}", why=why, role="builder",
                   command=launch_cmd("builder", closes[0], n), issue=closes[0], pr=n,
                   held=h[0] if h else None, once=h[1] if h else None)


def gov_ids(title: str | None) -> set[str]:
    """The GOV records an issue belongs to: the GOV-NNNN ids in its title (#136)."""
    return set(GOV_RE.findall(title or ""))


def overlap(n: int, w: World, live: list) -> str | None:
    """Why a [build] trigger for #n is held because other work from the same GOV record is
    in flight (#136, the owner's answer on #127), or None. Pure: reads only w and live."""
    m = w.model
    titles = {c["number"]: c.get("title") or "" for p in m["prs"] for c in p["closes"]}
    titles.update({i["number"]: i.get("title") or "" for i in w.issues})
    ids = gov_ids(titles.get(n))
    if not ids:
        return None
    names = {e.session_id: e.name for e in live}
    seen = {s["session_id"] for s in m["sessions"]}
    builders = [(names.get(s["session_id"], f"builder session {s['session_id']}"), s["issue"])
                for s in m["sessions"]
                if s["role"] == "builder" and s["status"] != "stopped" and s["issue"] is not None]
    builders += [(e.name, e.issue) for e in live
                 if e.role == "builder" and e.session_id not in seen and e.issue is not None]
    shared, why = set(), []
    for name, i in sorted(builders, key=lambda b: (b[1], b[0])):
        common = ids & gov_ids(titles.get(i))
        if i != n and common:
            shared |= common
            why.append(f"live {name} (on #{i})")
    for p in m["prs"]:
        common = set().union(*(ids & gov_ids(c.get("title")) for c in p["closes"] if c["number"] != n))
        if common:
            shared |= common
            why.append(f"open PR #{p['number']}")
    if not why:
        return None
    return f"held: #{n} shares {', '.join(sorted(shared))} with {' / '.join(why)} (#127)"


def reviewers(model: dict, started: list) -> list[str]:
    """Live reviewer sessions that swarm watch started (#132): live launcher entries with
    by="watch" whose heartbeat isn't stopped, or that have no heartbeat yet. Reviewers the
    owner started don't count. triggers() and Watch.refusal() both use this rule."""
    mine = {e.session_id: e.name for e in started if e.role == "reviewer" and e.by == "watch"}
    beats = {s["session_id"]: s for s in model["sessions"]}
    out = []
    for sid, name in mine.items():
        s = beats.get(sid)
        if s is None:
            out.append(f"{name} (starting, session {sid})")
        elif s["status"] != "stopped":
            out.append(f"{name} ({s['status']}, session {sid})")
    return out


# ---------------------------------------------------------------- reading GitHub

def gather(repo: str, idle_minutes: int, now: dt.datetime) -> World:
    """Read one tick's state. Only reads; raises RuntimeError if GitHub can't be read."""
    g = swarm.dashboard()
    data, model = swarm.snapshot(repo, idle_minutes, now)
    issues = [i for i in data["issues"] if i.get("state") == "open"]
    w = World(model=model, issues=issues)
    for it in issues:
        labels = {lb.get("name") for lb in it.get("labels") or []}
        if labels & {"ready", "gov:ruled"} and not g.is_tracking(it):
            w.events[it["number"]] = g.gh_items(f"repos/{repo}/issues/{it['number']}/events?per_page=100")
        if {"gov:question", "gov:ruled"} <= labels:     # the owner's `Record: yes` (#501)
            w.comments[it["number"]] = g.gh_items(f"repos/{repo}/issues/{it['number']}/comments?per_page=100")
    for n, reviews in (data.get("reviews") or {}).items():    # fetch() read them for build()
        w.reviewed[n] = reviewed_heads(reviews)
    return w


def reviewed_heads(reviews: list[dict]) -> set[str]:
    """The commit SHAs the reviewer App has reviewed on one PR, from its REST reviews. A
    head in this set is "already reviewed": the [review] trigger and the Actions reconciler
    (actions_review.py plan, GOV-0020) both use this rule, so they agree."""
    return {r.get("commit_id") for r in reviews
            if (r.get("user") or {}).get("login") == REVIEWER and r.get("commit_id")}


# ---------------------------------------------------------------- local state

def state_path(launcher: "swarm.Launcher") -> Path:
    return launcher.dir / STATE_FILE


def load_state(launcher: "swarm.Launcher") -> dict:
    """{"checked": ISO time, "acted": {key: outcome}, "waiting": [trigger dicts],
    "runs": {key: run record}}. A run record (#149) is {session_id, name, kind, ref,
    started}, plus {ending, detail, cost_usd, subtype, ended} once the run has ended."""
    try:
        data = json.loads(state_path(launcher).read_text())
    except FileNotFoundError:
        return {"checked": None, "acted": {}, "waiting": [], "runs": {}}
    except ValueError as e:
        raise RuntimeError(f"{state_path(launcher)} is not valid JSON: {e}") from None
    return {"checked": data.get("checked"), "acted": dict(data.get("acted") or {}),
            "waiting": list(data.get("waiting") or []), "runs": dict(data.get("runs") or {})}


def read_result(path: Path) -> dict:
    """How a headless run ended (#149), from its result file: ops/swarm-session's banner,
    then the JSON result on the last line (#147). Never raises.

    {"ending", "detail", "cost_usd", "subtype"}; cost_usd is total_cost_usd, or None."""
    try:
        text = path.read_text()
    except FileNotFoundError:
        return {"ending": NO_RESULT, "detail": "no result file", "cost_usd": None, "subtype": None}
    except (OSError, UnicodeDecodeError) as e:
        return {"ending": NO_RESULT, "detail": f"can't read the result file ({e.__class__.__name__})",
                "cost_usd": None, "subtype": None}
    lines = [x for x in text.splitlines() if x.strip()]
    result = None
    for candidate in (text, lines[-1] if lines else ""):
        try:
            d = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(d, dict) and d.get("type") == "result":
            result = d
            break
    if result is None:
        return {"ending": NO_RESULT, "detail": "no JSON result in the result file", "cost_usd": None,
                "subtype": None}
    cost = result.get("total_cost_usd")
    cost = float(cost) if isinstance(cost, (int, float)) and not isinstance(cost, bool) else None
    sub = result.get("subtype")
    rec = {"cost_usd": cost, "subtype": sub if isinstance(sub, str) else None}
    if result.get("api_error") == "usage_limit_reached" or result.get("api_error_status") == 429:
        msg = result.get("result")
        detail = msg if isinstance(msg, str) and msg else str(result.get("api_error") or "HTTP 429")
        return {**rec, "ending": LIMITED, "detail": detail[:200]}
    if sub in CAPS:
        return {**rec, "ending": AT_CAP, "detail": CAPS[sub]}
    if sub == "success" and not result.get("is_error"):
        return {**rec, "ending": DONE, "detail": ""}
    errors = result.get("errors")
    detail = "; ".join(str(e) for e in errors) if isinstance(errors, list) and errors else ""
    return {**rec, "ending": ERROR, "detail": (detail or f"subtype {sub}")[:200]}


def limit_until(message: str | None, ended: dt.datetime) -> dt.datetime:
    """When a limited run's hold ends (#489): the first time after `ended` that matches the
    message's "resets 12pm (Europe/London)" (in that zone, or this machine's if it names
    none), or LIMIT_HOLD after `ended` if there is no reset time it can read."""
    m = RESETS_RE.search(message or "")
    if m:
        hour, minute = int(m[1]), int(m[2] or 0)
        try:
            zone = zoneinfo.ZoneInfo(m[4]) if m[4] else None
        except (zoneinfo.ZoneInfoNotFoundError, ValueError):
            zone, m = None, None
        if m and 1 <= hour <= 12 and minute < 60:
            here = ended.astimezone(zone)
            t = here.replace(hour=hour % 12 + 12 * (m[3].lower() == "pm"), minute=minute,
                             second=0, microsecond=0)
            if t <= here:
                t += dt.timedelta(days=1)
            return t.astimezone(dt.timezone.utc)
    return ended + LIMIT_HOLD


def limit_reason(runs: dict, now: dt.datetime) -> str | None:
    """The hold every start waits on while a run is limited (#489), or None."""
    until = [dt.datetime.fromisoformat(r["until"]) for r in runs.values()
             if r.get("ending") == LIMITED and r.get("until")]
    until = max((u for u in until if u > now), default=None)
    return until and f"held: usage limit (until {until.astimezone().strftime('%H:%M')})"


def usd(x: float | None) -> str:
    return "-" if x is None else f"${x:,.2f}"


def run_line(r: dict) -> str:
    """One recorded run, for the loop's log and `swarm inbox`."""
    ending = r["ending"] + (f" ({r['detail']})" if r.get("detail") else "")
    return f"[{r['kind']}] {r['ref']} {r['name']} · {ending} · {usd(r.get('cost_usd'))} (est.)"


def save_state(launcher: "swarm.Launcher", st: dict) -> None:
    """Write watch.json atomically through a temp file of its own, so two writers never
    rename each other's (#296), as Launcher.save() does for sessions.json (#272)."""
    launcher.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=launcher.dir, prefix=".watch.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(st, indent=1) + "\n")
        os.replace(tmp, state_path(launcher))
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def take_lock(launcher: "swarm.Launcher") -> tuple[int | None, str]:
    """The one-watcher lock (#273): (fd, "") if this process now holds it, or (None, pid)
    if another process does, with the pid it wrote ("" if not yet written). The lock lasts
    until the fd is closed or the process ends; the file is never removed, since removing
    it would let a second watcher lock a fresh file beside the first."""
    launcher.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = launcher.dir / LOCK_FILE
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)   # no O_TRUNC: keep the holder's pid
    except OSError as e:
        raise RuntimeError(f"can't open {path}: {e}") from None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        pid = os.read(fd, 64).decode(errors="replace").strip()
        os.close(fd)
        return None, pid
    except OSError as e:
        os.close(fd)
        raise RuntimeError(f"can't lock {path}: {e}") from None
    os.ftruncate(fd, 0)
    os.write(fd, f"{os.getpid()}\n".encode())
    return fd, ""


def waiting(launcher: "swarm.Launcher") -> tuple[dt.datetime | None, list[dict]]:
    """For `swarm inbox`: when swarm watch last checked, and the triggers it is holding
    or skipping. Never raises: a missing or bad state file shows nothing."""
    try:
        st = load_state(launcher)
    except (RuntimeError, OSError):
        return None, []
    checked = dt.datetime.fromisoformat(st["checked"]) if st["checked"] else None
    return checked, st["waiting"]


def runs(launcher: "swarm.Launcher") -> list[dict]:
    """For `swarm inbox` (#149): every run record in watch.json, ended or not. Never
    raises: a missing or bad state file shows nothing."""
    try:
        return list(load_state(launcher)["runs"].values())
    except (RuntimeError, OSError):
        return []


def runs_text(runs: list[dict], now: dt.datetime, ago: Callable) -> tuple[list[str], list[str]]:
    """(lines for runs that ended at cap, lines for every ended run, newest first), within
    RUNS_DAYS. runs is watch.runs(): every record, including runs still live.

    A run that ended at cap is listed until a later run on the same ref has started (the
    owner restarted it with a fresh label, or the loop moved on), or RUNS_DAYS pass."""
    since = now - dt.timedelta(days=RUNS_DAYS)
    recent = sorted((r for r in runs if r.get("ending") and r.get("ended")
                     and dt.datetime.fromisoformat(r["ended"]) >= since),
                    key=lambda r: r["ended"], reverse=True)
    capped = [r for r in recent if r["ending"] == AT_CAP
              and not any(o["ref"] == r["ref"] and o["started"] > r["started"] for o in runs)]
    when = lambda r: f" · ended {ago(dt.datetime.fromisoformat(r['ended']), now)}"
    return ([f"- {run_line(r)}{when(r)}" for r in capped],
            [f"- {run_line(r)}{when(r)}" for r in recent])


def iso(t: dt.datetime) -> str:
    return t.isoformat()


# ---------------------------------------------------------------- swarm cost (#176)

PR_STATES = {"MERGED": "merged", "OPEN": "open", "CLOSED": "closed"}


def gh_prs(repo: str) -> list[dict]:
    """Every recent PR, merged, open or closed, with the issues it closes. A read only."""
    g = swarm.dashboard()
    return g.gh_json("pr", "list", "--repo", repo, "--state", "all", "--limit", "300", "--json",
                     "number,state,mergedAt,closingIssuesReferences") or []


def served_pr(r: dict, prs: list[dict]) -> int | None:
    """The PR a run ended up serving: the trigger's PR for [review] and [respond]; for a
    run on an issue ([build], [record], [answer]), the PR that closes it, merged first,
    then open, then closed, newest first. None if no PR closes it."""
    m = REF_RE.search(r.get("ref") or "")
    if not m:
        return None
    n = int(m.group(1))
    if (r.get("ref") or "").startswith("PR "):
        return n
    rank = {"MERGED": 0, "OPEN": 1, "CLOSED": 2}
    closing = [p for p in prs if n in {c.get("number") for c in p.get("closingIssuesReferences") or []}]
    if not closing:
        return None
    return min(closing, key=lambda p: (rank.get(p.get("state"), 3), -p["number"]))["number"]


def cost_text(runs: list[dict], prs: list[dict]) -> str:
    """`swarm cost` (#176): each recorded run's total_cost_usd, grouped by the PR it served.

    runs is watch.runs(); prs is gh_prs(). Only prints: the costs stay on this machine
    (GOV-0002, GOV-0003, GOV-0004, GOV-0014)."""
    limits = ["Only runs swarm watch started have a cost: sessions you start by hand have none.",
              f"watch.json keeps runs for {RUNS_DAYS} days (watch.RUNS_DAYS), so older runs aren't counted.",
              "Costs are Claude Code's local estimate and stay on this machine."]
    if not runs:
        return "\n".join(["no runs recorded in watch.json"] + limits)
    state = {p["number"]: PR_STATES.get(p.get("state"), (p.get("state") or "?").lower()) for p in prs}
    groups: dict[tuple, dict] = {}
    for r in runs:
        n = served_pr(r, prs)
        if n is not None:
            key, label, st = (0, n, ""), f"PR #{n}", state.get(n, "?")
        else:
            key, label, st = (1, 0, r.get("ref") or ""), f"{r.get('ref')} (no PR)", "-"
        g = groups.setdefault(key, {"pr": n, "label": label, "state": st, "runs": 0, "cost": 0.0,
                                    "none": 0})
        g["runs"] += 1
        if isinstance(r.get("cost_usd"), (int, float)):
            g["cost"] += r["cost_usd"]
        else:
            g["none"] += 1
    rows = [[g["label"], g["state"], str(g["runs"]), usd(g["cost"]) if g["runs"] > g["none"] else "-",
             str(g["none"])] for _, g in sorted(groups.items())]
    total = sum(g["cost"] for g in groups.values())
    nruns, nnone = len(runs), sum(g["none"] for g in groups.values())
    starts = sorted(r["started"] for r in runs if r.get("started"))
    ends = sorted(r.get("ended") or r["started"] for r in runs if r.get("started"))
    span = f"{starts[0][:10]} to {ends[-1][:10]}" if starts else "unknown dates"
    out = [swarm.table(["PR", "STATE", "RUNS", "COST (EST.)", "NO COST"], rows), "",
           f"total: {usd(total)} over {nruns} run{'s' * (nruns != 1)}, runs started {span}"
           + (f"; {nnone} run{'s' * (nnone != 1)} with no cost recorded (still running, or no result)"
              if nnone else "")]
    if starts:
        seen = {g["pr"] for g in groups.values()}
        unrecorded = sorted(p["number"] for p in prs if p.get("state") == "MERGED" and p.get("mergedAt")
                            and p["mergedAt"] >= starts[0][:19] and p["number"] not in seen)
        out.append(f"{len(unrecorded)} PR{'s' * (len(unrecorded) != 1)} merged since {starts[0][:10]} "
                   f"{'have' if len(unrecorded) != 1 else 'has'} no run recorded"
                   + (f": {', '.join(f'#{n}' for n in unrecorded)}" if unrecorded else ""))
    return "\n".join(out + [""] + limits)


# ---------------------------------------------------------------- the loop

@dataclass
class Watch:
    launcher: "swarm.Launcher"
    repo: str
    owner: str
    roles: set[str]
    idle_minutes: int = 15
    dry_run: bool = True
    manifest_path: Path = manifest.DEFAULT_PATH
    read: Callable[[str, int, dt.datetime], World] = gather
    get_issue: Callable[[str, int], tuple] = swarm.gh_issue           # refusal re-checks
    get_heartbeat: Callable[[str, int, dt.datetime], dict] = swarm.heartbeat
    seen: set[str] = field(default_factory=set)                      # dry-run memory
    roles_from: Path | None = None    # repo root whose roles/ is re-read every tick (#487)

    def tick(self, now: dt.datetime | None = None) -> list[Trigger]:
        """One check. Returns the triggers it acted on or printed for the first time."""
        now = now or dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        if self.roles_from is not None:
            self.roles = roles_in(self.roles_from)
        self.report_manifest_problems()
        return self.dry_tick(now) if self.dry_run else self.start_tick(now)

    def report_manifest_problems(self) -> None:
        """Print each bad [[session]] entry in swarm.toml, every tick (#487): the loop
        carries on with the valid ones. A file it can't use at all is reported where it's
        read (start_tick raises, headless() says so)."""
        try:
            problems = manifest.load_all(self.manifest_path)[2]
        except manifest.ManifestError:
            return
        for p in problems:
            self.launcher.out(f"{self.manifest_path.name}: {p}")

    def dry_tick(self, now: dt.datetime) -> list[Trigger]:
        """Print and return the triggers not seen before. Starts nothing, writes nothing.
        A held trigger (#488, #490) is printed once per reason and not returned; it prints
        as a trigger once its holder has stopped or its Waits-on issues have closed."""
        g = swarm.dashboard()
        w = self.read(self.repo, self.idle_minutes, now)
        limits = self.limits()
        new = []
        for t in triggers(w, self.owner, self.launcher.running(), self.roles, g.needs_you,
                          g.is_tracking, bool(limits and limits.review_in_actions), now,
                          limits.stale_minutes if limits else DEFAULT_STALE):
            key = f"{t.key}|held|{t.once}" if t.held else t.key
            if key in self.seen:
                continue
            self.seen.add(key)
            self.launcher.out(t.line())
            if t.held:
                continue
            new.append(t)
            if not t.skipped:
                self.launcher.out(f"  {self.headless(t)}")
        return new

    def limits(self) -> "manifest.WatchLimits | None":
        """For --dry-run: swarm.toml's [watch] limits, or None if swarm.toml has no [watch]
        table or can't be read (headless() reports that). Never raises."""
        try:
            return manifest.load_watch(self.manifest_path)
        except manifest.ManifestError:
            return None

    def review_in_actions(self) -> bool:
        """For --dry-run: swarm.toml's [watch] review_in_actions, or False (see limits())."""
        limits = self.limits()
        return bool(limits and limits.review_in_actions)

    def headless(self, t: Trigger) -> str:
        """For --dry-run: the full command a real start would run for t (#147), or why
        there isn't one. Reads swarm.toml as a real start would; never raises."""
        try:
            sessions, limits, _ = manifest.load_all(self.manifest_path)
        except manifest.ManifestError as e:
            return f"(no headless command: {e})"
        s = {x.role: x for x in sessions}.get(t.role)
        if s is None or s.spend_cap_usd is None:
            return f"(no headless command: {t.role} has no spend_cap_usd in swarm.toml)"
        if limits is None or limits.max_turns is None:
            return "(no headless command: swarm.toml's [watch] table has no max_turns)"
        entry = self.entry(t, s, limits, self.launcher.running())
        return self.launcher.command(entry)

    def entry(self, t: Trigger, s: "manifest.Session", limits: "manifest.WatchLimits",
              live: list) -> "swarm.Started":
        """The launcher entry for a headless run on t, with its budget and turn ceiling."""
        return swarm.Started(name=self.name(t, live), role=t.role, model=s.model,
                             session_id=str(uuid.uuid4()), started=self.launcher.clock(),
                             issue=t.issue, pr=t.pr, by="watch",
                             budget_usd=s.spend_cap_usd, max_turns=limits.max_turns)

    def start_tick(self, now: dt.datetime) -> list[Trigger]:
        """Start a session for each new trigger, within the [watch] limits (GOV-0010)."""
        g, out = swarm.dashboard(), self.launcher.out
        try:   # a bad entry is skipped, and reported by tick(); a bad [watch] starts nothing
            sessions, limits, _ = manifest.load_all(self.manifest_path)
        except manifest.ManifestError as e:
            raise RuntimeError(str(e)) from None
        if limits is None:
            raise RuntimeError(f"{self.manifest_path} has no [watch] table; starting nothing (GOV-0010)")
        if limits.max_turns is None:
            raise RuntimeError(f"{self.manifest_path}'s [watch] table has no max_turns; starting "
                               f"nothing (GOV-0012)")
        by_role = {s.role: s for s in sessions}
        w = self.read(self.repo, self.idle_minutes, now)
        live = self.launcher.live()
        st = load_state(self.launcher)
        acted, before = st["acted"], {x["key"]: x for x in st["waiting"]}
        runs = self.record_ended(st["runs"], live, now, acted)
        limited = limit_reason(runs, now)
        if limited and not any(x.get("reason") == limited for x in st["waiting"]):
            out(f"swarm watch: a run hit the account's usage limit; {limited}, for every start (#489)")
        todo = [t for t in triggers(w, self.owner, live, self.roles, g.needs_you, g.is_tracking,
                                    limits.review_in_actions, now, limits.stale_minutes)
                if t.key not in acted]
        todo.sort(key=lambda t: before.get(t.key, {}).get("since", iso(now)))  # held longest first
        held, done, reviewer = [], [], None

        def finish(t: Trigger, outcome: str) -> None:
            acted[t.key] = outcome
            done.append(t)
            save_state(self.launcher, {"checked": iso(now), "acted": acted, "waiting": st["waiting"],
                                       "runs": runs})

        def hold(t: Trigger, reason: str, once: str | None = None) -> None:
            was = before.get(t.key, {})
            entry = {"key": t.key, "kind": t.kind, "ref": t.ref, "why": t.why,
                     "reason": reason, "since": was.get("since", iso(now))}
            if once:
                entry["once"] = once
            held.append(entry)
            if reason != limited and (was.get("once") or was.get("reason")) != (once or reason):   # each reason once
                out(f"[{t.kind}] {t.ref} {t.why} -> {reason}")

        for t in todo:
            if t.kind == "review" and t.skipped == LEFT_TO_ACTIONS:
                # Not recorded in watch.json: switch it off and the loop reviews this head again.
                if t.key not in self.seen:
                    self.seen.add(t.key)
                    out(t.line())
                continue
            if t.held:
                # #488: a live session is on the issue, or #490: a [build]'s Waits-on issues are
                # still open. Listed in `swarm inbox` with why, never recorded in `acted`; it
                # starts once that clears. The loop never stops a session (GOV-0008).
                hold(t, t.held, t.once)
                continue
            if t.kind == "answer" and t.skipped:
                # Listed in `swarm inbox` until the owner closes the question or drops `ready` (#271).
                hold(t, f"skipped: {t.skipped}")
                continue
            if t.skipped:
                out(t.line())
                finish(t, f"skipped: {t.skipped}")
                continue
            if t.after and t.after not in acted:
                # #495: docs records the ruling first; once [record] is acted on, the held
                # check above and the holders check below keep [answer] waiting until docs
                # has stopped.
                hold(t, f"held: docs records the ruling on {t.ref} first, then {t.role} starts")
                continue
            if t.kind == "review" and reviewer:
                out(f"[review] {t.ref} {t.why} -> covered by {reviewer}")
                finish(t, f"covered by {reviewer}")
                continue
            if t.issue is not None and swarm.holders(t.issue, w.model, live):
                continue      # a session started this check is on it; it fires again once that stops
            if t.held:
                # #490: not acted on, so it starts on the first check after its blockers close.
                hold(t, t.held)
                continue
            s = by_role.get(t.role)
            mine = sum(e.by == "watch" for e in live)
            if s is None:
                hold(t, f"skipped: {t.role} isn't in swarm.toml")
                continue
            if s.spend_cap_usd is None:
                hold(t, f"skipped: {t.role} has no spend_cap_usd in swarm.toml, and swarm watch "
                        f"starts only capped roles (GOV-0010)")
                continue
            if limited:
                hold(t, limited)       # said once above: the limit is account-wide
                continue
            busy_with = overlap(t.issue, w, live) if t.kind == "build" else None
            if busy_with:
                hold(t, busy_with)
                continue
            if mine >= limits.max_live:
                hold(t, f"held: {mine} of {limits.max_live} sessions swarm watch started are live (GOV-0010)")
                continue
            refused, wait = self.refusal(t, live, now)
            if wait:
                continue
            if refused:
                out(f"[{t.kind}] {t.ref} {t.why} -> refused: {refused}")
                finish(t, f"refused: {refused}")
                continue
            entry = self.entry(t, s, limits, live)
            out(f"[{t.kind}] {t.ref} {t.why} -> starting {entry.name}")
            if self.launcher.start(entry, live):
                if t.kind == "review":
                    reviewer = entry.name
                runs[t.key] = {"session_id": entry.session_id, "name": entry.name, "kind": t.kind,
                               "ref": t.ref, "started": iso(now)}
                finish(t, f"started {entry.name}")
            else:
                hold(t, "failed to start (see above); trying again next check")
        save_state(self.launcher, {"checked": iso(now), "acted": acted, "waiting": held, "runs": runs})
        return done

    def record_ended(self, runs: dict, live: list, now: dt.datetime, acted: dict) -> dict:
        """Record how each run this loop started ended, once it is no longer live (#149):
        read its result file and log one line. Records older than RUNS_DAYS are dropped.
        Its trigger stays done in "acted", so the loop never starts it again by itself,
        unless the run was limited (#489): then it records when the hold ends and takes the
        trigger, and any review triggers its pass covered, out of "acted" to fire again."""
        alive = {e.session_id for e in live}
        since = iso(now - dt.timedelta(days=RUNS_DAYS))
        kept = {}
        for key, r in runs.items():
            if r.get("ended") and r["ended"] < since:
                continue
            if not r.get("ending") and r["session_id"] not in alive:
                r = {**r, **read_result(self.launcher.result_file(r["session_id"])), "ended": iso(now)}
                if r["ending"] == LIMITED:
                    r["until"] = iso(limit_until(r["detail"], now))
                    for k in [k for k, v in acted.items() if k == key or v == f"covered by {r['name']}"]:
                        del acted[k]
                    self.launcher.out(f"{run_line(r)} -> recorded; trying again after the hold")
                else:
                    self.launcher.out(f"{run_line(r)} -> recorded")
            kept[key] = r
        return kept

    def refusal(self, t: Trigger, live: list, now: dt.datetime) -> tuple[str | None, bool]:
        """`swarm launch`'s refusal checks, run again on fresh GitHub data just before a
        start: (reason, False) refuses the trigger for good; (None, True) waits a check."""
        hb = self.get_heartbeat(self.repo, self.idle_minutes, now)
        if t.kind == "review":
            # A pass already running may have listed PRs before this push: wait for it.
            return None, bool(reviewers(hb, live))
        issue, events = self.get_issue(self.repo, t.issue)
        label = "gov:ruled" if t.kind == "record" else "ready"
        refused = swarm.issue_refusals(t.issue, issue, events, self.owner, label)
        if refused:
            return refused[0], False
        taken = swarm.holders(t.issue, hb, live)
        if taken:
            return f"#{t.issue} already has a live session: {'; '.join(taken)}", False
        return None, False

    def name(self, t: Trigger, live: list) -> str:
        taken = {e.name for e in live}
        if t.issue is not None:
            return swarm.launch_name(t.role, t.issue, taken, t.pr)
        name, k = "reviewer-watch", 2
        while name in taken:
            name, k = f"reviewer-watch-{k}", k + 1
        return name

    def run(self, interval_minutes: float, ticks: int | None = None,
            sleep: Callable[[float], None] = time.sleep) -> int:
        if self.dry_run:
            self.launcher.out(f"swarm watch --dry-run: checking every {interval_minutes:g} min; "
                              f"starts nothing; Ctrl-C to stop")
            return self.loop(interval_minutes, ticks, sleep)
        fd, holder = take_lock(self.launcher)
        if fd is None:
            self.launcher.out(f"swarm watch: refused: another swarm watch is already running "
                              f"(pid {holder or 'unknown'}; lock {self.launcher.dir / LOCK_FILE}). "
                              f"Stop it first; --dry-run is safe beside it (#273)")
            return 1
        try:
            self.launcher.out(f"swarm watch: checking every {interval_minutes:g} min; starts sessions "
                              f"within swarm.toml's [watch] limits and only for roles with a "
                              f"spend_cap_usd (GOV-0010); never stops one; Ctrl-C to stop")
            return self.loop(interval_minutes, ticks, sleep)
        finally:
            os.close(fd)

    def loop(self, interval_minutes: float, ticks: int | None, sleep: Callable[[float], None]) -> int:
        n = 0
        try:
            while ticks is None or n < ticks:
                if n:
                    sleep(interval_minutes * 60)
                try:
                    self.tick()
                except RuntimeError as e:      # GitHub unreachable, bad swarm.toml: try again next tick
                    self.launcher.out(f"swarm watch: {e}; trying again next tick")
                n += 1
        except KeyboardInterrupt:
            self.launcher.out("swarm watch: stopped")
        return 0


def roles_in(root: Path) -> set[str]:
    """The roles with a prompt in root/roles/."""
    return {p.stem for p in (root / "roles").glob("*.md")}
