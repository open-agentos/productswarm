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
| build  | issue whose most recent `ready` was added by the owner (GOV-0006), or   | builder on the issue |
|        | that is go by its PLAN.md milestone (GOV-0026, #583), with no open PR   |                      |
|        | closing it                                                              |                      |
| record | gov:question whose most recent `gov:ruled` was added by the owner, that | docs on the question |
|        | needs a record (GOV-0007), with no open PR closing it                   |                      |
| answer | gov:question whose most recent `ready` was added by the owner, again    | its "Raised by" role |
|        | when the owner then adds `gov:ruled` (#495)                             | (planner if owner)   |
| respond| open, non-draft PR the builder App opened, whose latest reviewer review | builder on the PR    |
|        | at its head is CHANGES_REQUESTED, with Authority not `fail`, for at     | (GOV-0011)           |
|        | most 2 rounds                                                           |                      |
| call-in| a `Call in: <role>, <role>: <why>` line in a comment on an issue whose  | each named role on   |
|        | most recent `ready` was added by the owner, posted since that label, by | the issue, once per  |
|        | a swarm App or the owner (GOV-0023, #520)                               | call                 |
| daily  | a working day (Mon-Fri, local time) at or after [watch] daily_at, once  | planner on the       |
|        | per day, with daily = true (GOV-0029, #588)                             | report issue         |
| ask    | the owner's `Ask: <role>: <question>` comment on [watch] report_issue,  | that role on the     |
|        | with asks = true (GOV-0029, #590)                                       | report issue, once   |

[daily] (#588, GOV-0029): with `daily = true` in [watch], once each working day (Monday to
Friday, in this machine's local time) at or after daily_at, it starts the planner on
report_issue to write the daily report; on Mondays the prompt says the daily report and
the Monday check-in. Its key is `daily:<report_issue>:<local date>`, so a missed poll
fires late that day, not twice. It waits only while a planner session is live on the
report issue. A day whose trigger never started (held all day, or swarm watch stopped
mid-hold) is logged once the next day as missed and isn't caught up. Before the start
the report issue must exist and be open; it needs no label. Its run is headless like any
other (GOV-0010, GOV-0012, GOV-0013), and stophook.py lets it stop whenever it likes.
With daily off (the default) there is no trigger. `swarm inbox` says when it is next due.

[ask] (#590, GOV-0029): with `asks = true` in [watch], a comment on report_issue counts as
an ask when a line of it starts `Ask:` (any case): one role, a colon, then the question,
the rest of that line, at most WHY_MAX characters. Only the first such line counts. It is
keyed on the comment id, so it starts once. A comment by anyone but the owner, a name with
no prompt in roles/, a line naming more than one role, or a line with no question is
skipped with a reason. Only asks posted since the switch was turned on count: watch.json
keeps when this watcher first saw it on for that report issue (`asks_since`), and drops it
on a check that finds it off, so an ask posted while it was off (or answered by hand
before it was on) never starts; each is skipped once with that reason. It waits only while
a session of the same role is live on the report issue, and the report issue must exist
and be open. Its run is headless like any other (GOV-0010, GOV-0012, GOV-0013); its prompt
quotes the question and says it answers in one comment there, and stophook.py lets it
stop whenever it likes. With asks off (the default) the report issue's comments aren't read.

[call-in] (#520, GOV-0023): a comment counts as a call when a line of it starts `Call in:`
(any case). The roles are the comma-separated names before the next colon; the why is the
rest of that line. A call by anyone but the owner or a swarm App (identities.agents in
jurisdictions.yml, as GOV-0024 reads it) is skipped with a reason. Each named role gets
its own trigger, keyed on the comment id and the role, so it starts once. A role naming
itself, or a name with no prompt in roles/, is skipped with a reason. At most MAX_CALLS
calls count per issue per UTC day, by the comment's created_at; a call that names no role
it could start doesn't count, and later calls that day are skipped with a reason. A call-in
waits only while a session of the same role is live on the issue: the caller (often a live
builder) doesn't hold it. Its run is headless like any other (GOV-0010, GOV-0012,
GOV-0013); its prompt names the caller and the why, says the call asks it in (§8) and that
it posts one comment, and stophook.py lets it stop whenever it likes. `call_ins = true` in
[watch] turns call-ins on; while it is off (the default) each call is listed as off and
never recorded, so turning it on starts the calls still on `ready` issues.

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

[build] by milestone (#583, GOV-0026): an open, non-question, non-tracking issue without
the owner's `ready` builds when swarm.milestone_refusal() passes on this tick's reading:
the owner or a swarm App (identities.agents) opened it, its `**Milestone:** M<n>` names a
milestone in PLAN.md on main (read once per check) that isn't marked done, and there is no
`hold` label and no owner comment. Its `**Waits on:**` issues hold it, as for `ready`, rather
than stopping it. The owner's `ready` is read first and wins. The trigger's key is
`build:N:M<n>`, plus the id of the latest event removing `hold` if there is one, so a
change of milestone, or a veto then a lift, is one new trigger and starts at most one new
build. Its why is "go by milestone M<n> (GOV-0026)". Before the start, refusal() runs
swarm.go_refusals() on fresh GitHub data, as `swarm launch` does.

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
import subprocess
import sys
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
CALL_IN = "call-in"           # GOV-0023's trigger (#520)
CALL_RE = re.compile(r"^[ \t]*Call in:[ \t]*([^:\n]*?)[ \t]*(?::[ \t]*([^\n]*?))?[ \t]*$",
                     re.IGNORECASE | re.MULTILINE)
MAX_CALLS = 2                 # calls that count per issue per UTC day (GOV-0023)
WHY_MAX = 300                 # characters of a call's why that go into the prompt
CALL_INS_OFF = ("call-ins are off: call_ins = true in swarm.toml's [watch] turns them on "
                "(GOV-0023)")
NOT_RECORDED = (LEFT_TO_ACTIONS, CALL_INS_OFF)   # listed once, never kept in watch.json
DAILY = "daily"               # GOV-0029's daily report trigger (#588)
ASK = "ask"                   # GOV-0029's owner Ask: trigger (#590)
ASK_RE = re.compile(r"^[ \t]*Ask:[ \t]*([^:\n]*?)[ \t]*(?::[ \t]*([^\n]*?))?[ \t]*$",
                    re.IGNORECASE | re.MULTILINE)
WORKDAYS = range(5)           # Monday to Friday, by date.weekday()
RUNS_DAYS = 7                 # how long `swarm inbox` lists a recorded run, and watch.json keeps it
PUBLIC_FILE = "watch-public.json"   # watch.json's no-cost form, beside it (#456)
MAX_RETRIES = 2               # times a run that never started is started again (#550)
WAIT_RE = re.compile(r"\bwait(?:s|ing)?\s+(?:on|for)\b([^\n]*)", re.IGNORECASE)
BUILDER_APP = "productswarm-builder[bot]"

# How a headless run ended, from the `subtype` of its --output-format json result: the
# SDKResultMessage type in the Claude Code Agent SDK reference (#149). Any other subtype,
# or "success" with is_error set, is an error.
DONE, AT_CAP, ERROR, NO_RESULT = "done", "ended at cap", "error", "no result"
LIMITED = "limited"           # a usage or rate limit: tried again after the hold (#489)
LIMIT_HOLD = dt.timedelta(minutes=30)     # when the result names no reset time
RESETS_RE = re.compile(r"\bresets (\d{1,2})(?::(\d{2}))?\s*([ap]m)\b(?:\s*\(([^)]+)\))?", re.I)
CAPS = {"error_max_budget_usd": "budget (--max-budget-usd)",
        "error_max_turns": "turns (--max-turns)"}

# Why a trigger waits, as a fixed code and its sentence (#456). watch-public.json carries
# only these, never a reason's own text, which can quote an issue. A sentence's fields are
# integers only. Codes in SKIPS list as skipped; the rest as held.
REASONS = {
    "limit": "held: {live} of {max} running",
    "live": "held: a session is live on it",
    "stale": "held: a session on it has gone quiet",
    "waits_on": "held: waits on an open issue",
    "overlap": "held: work from the same GOV record is in flight",
    "usage_limit": "held: usage limit",
    "record_first": "held: docs records the ruling first",
    "error": "held: failed to start; trying again next check",
    "raised_by": "skipped: \"Raised by\" names no role",
    "no_role": "skipped: the role isn't in swarm.toml",
    "no_cap": "skipped: the role has no spend_cap_usd in swarm.toml",
    "other": "held",
}
SKIPS = {"raised_by", "no_role", "no_cap"}
ENDINGS = {AT_CAP: "at_cap", ERROR: "error", NO_RESULT: "no_result", LIMITED: "limited"}  # failed


@dataclass(frozen=True)
class Trigger:
    key: str                  # identity: a new key is a new trigger
    kind: str                 # review | build | record | answer | respond | call-in | daily | ask
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
    called_by: str | None = None  # [call-in]: who called the role in, for its prompt (#520)
    call_why: str | None = None   # [call-in]: the why from the `Call in:` line
    daily: str | None = None      # [daily]: what the planner writes, for its prompt (#588)
    ask: str | None = None        # [ask]: the owner's question, for its prompt (#590)
    ask_comment: int | None = None    # [ask]: the comment that asked it

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


def one_way_domains(path: Path = swarm.JURISDICTIONS) -> tuple[frozenset[str], str | None]:
    """(the domains jurisdictions.yml marks `always_one_way: true`, why none) (#519).

    Read through the dashboard's reader, not a second parser. If the file can't be read,
    no domain counts and the reason says why; the body's own ratings still apply."""
    if str(swarm.ROOT / "dashboard") not in sys.path:
        sys.path.insert(0, str(swarm.ROOT / "dashboard"))
    import authority   # jurisdictions.yml's reader
    try:
        ds = authority.domains(authority.read(Path(path).read_text()))
    except (OSError, UnicodeDecodeError, ValueError) as e:
        return frozenset(), f"can't read {authority.JURISDICTIONS_PATH} ({e.__class__.__name__})"
    return frozenset(d["name"].lower() for d in ds if d["always_one_way"]), None


def needs_record(body: str | None, comments: list[dict] = (), owner: str | None = None,
                 one_way: frozenset[str] = frozenset()) -> str | None:
    """Why a question needs a record under GOV-0007, else None.

    The body's ratings cover the governance domain, one-way and external. A domain in
    one_way (jurisdictions.yml's `always_one_way`, from one_way_domains()) counts as rated
    one-way whatever the body says (#519). GOV-0007's other case, "the owner says so in the
    answer", is a comment by the owner with a line `Record: yes` on its own (#501). Nobody
    else's comment counts, agents included."""
    domain = (template_field(body, "Domain") or "").strip().lower()
    rev = (template_field(body, "Reversibility") or "").strip().lower()
    blast = (template_field(body, "Blast radius") or "").strip().lower()
    if domain == "governance":
        return "domain governance"
    if domain in one_way:
        return f"domain {domain} is always one-way"
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
    plan: str | None = None                          # PLAN.md on main, None if absent (#583)


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
            stale_minutes: int = DEFAULT_STALE, role: str | None = None) -> tuple[str, str] | None:
    """Why a live session on issue n holds its trigger (#488), as (reason, once), or None.

    The same sessions as swarm.holders(): heartbeat sessions on n that aren't stopped, and
    launcher entries on n with no heartbeat yet. A holder idle on the heartbeat for longer
    than stale_minutes makes the reason `stale:` and names the `swarm stop` that frees n;
    the watcher still never stops it (GOV-0008, #132). `once` changes only when a holder's
    status does, so the reason is logged once per state, not once per tick. With role, only
    sessions of that role count ([call-in], #520)."""
    g = swarm.dashboard()
    names = {e.session_id: e.name for e in started}
    seen = {s["session_id"] for s in m["sessions"]}
    held, stale, once = [], [], []
    for s in m["sessions"]:
        if s["status"] == "stopped" or s["issue"] != n or role not in (None, s["role"]):
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
        if e.issue == n and e.session_id not in seen and role in (None, e.role):
            held.append(f"{e.name} is live on #{n} (starting, no heartbeat yet)")
            once.append(f"{e.name}:starting")
    if not held and not stale:
        return None
    reason = f"stale: {'; '.join(stale)}" if stale else f"held: {' and '.join(held)}"
    return reason, "|".join(sorted(once))


def triggers(w: World, owner: str, started: list, roles: set[str], needs_you: Callable,
             is_tracking: Callable, review_in_actions: bool = False,
             now: dt.datetime | None = None, stale_minutes: int = DEFAULT_STALE,
             one_way: frozenset[str] = frozenset(), apps: dict[str, str] | None = None,
             call_ins: bool = False, daily_at: dt.time | None = None,
             report_issue: int | None = None, tz: dt.tzinfo | None = None,
             ask_issue: int | None = None, asks_since: dt.datetime | None = None) -> list[Trigger]:
    """Every trigger present now, in needs-you order then issue order. Nothing is filtered
    for novelty here; Watch does that. With review_in_actions, each [review] trigger is
    skipped as left to Actions (GOV-0019). A [record], [answer], [build] or [respond]
    trigger on an issue a live session holds comes back with `held` set, saying who holds
    it and whether that session is stale (#488); Watch starts nothing for it. A question in
    a domain in one_way needs a record whatever its body rates it (#519). apps maps each
    swarm App login to its role, for [call-in] (#520); with call_ins off, each [call-in]
    comes back skipped as off. With daily_at and report_issue, [daily] is due at daily_at
    in tz (default: this machine's local time) on working days (#588, GOV-0029). With
    ask_issue, each owner `Ask:` comment on it posted since asks_since is an [ask] (#590)."""
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

    # Questions: every open gov:question, from the model, plus any a session is blocked on.
    # Not from needs-you alone: it leaves out gov:ruled questions (#469), which [record]
    # and [answer] still need.
    questions = {q["number"] for q in m["gov"]}
    questions |= {int(REF_RE.search(it["ref"]).group(1)) for it in items if it["kind"] == "blocked"}
    raw = {i["number"]: i for i in w.issues}
    for n in sorted(questions):
        body, events = (raw.get(n) or {}).get("body"), w.events.get(n, [])
        labels = {lb.get("name") for lb in (raw.get(n) or {}).get("labels") or []}
        ruled = owner_label(events, "gov:ruled", owner) if "gov:ruled" in labels else None
        why_record = needs_record(body, w.comments.get(n, []), owner, one_way)
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

    # Builds: open, non-question, non-tracking issues with no open PR closing them (that
    # work is done and waits on the owner's merge) that are go: the owner's `ready`
    # (GOV-0006), or else their PLAN.md milestone (GOV-0026, #583).
    agents = set(apps or {})
    for it in sorted(w.issues, key=lambda i: i["number"]):
        n = it["number"]
        labels = {lb.get("name") for lb in it.get("labels") or []}
        if (it.get("state") != "open" or "pull_request" in it or "gov:question" in labels
                or is_tracking(it) or n in closing):
            continue
        events = w.events.get(n, [])
        ready = owner_label(events, "ready", owner) if "ready" in labels else None
        if ready:
            key, why = f"build:{n}:{ready.get('id')}", "ready by the owner"
        else:
            mile = milestone_go(it, w, owner, agents)
            if mile is None:
                continue
            lift = next((e for e in reversed(events) if e.get("event") == "unlabeled"
                         and (e.get("label") or {}).get("name") == "hold"), None)
            key = f"build:{n}:M{mile}" + (f":{lift.get('id')}" if lift else "")
            why = f"go by milestone M{mile} (GOV-0026)"
        t = hold(Trigger(key=key, kind="build", ref=f"#{n}", why=why, role="builder",
                         command=launch_cmd("builder", n), issue=n), n)
        waits = None if t.held else blocked(it.get("body"), w)
        out.append(replace(t, held=waits, once=waits) if waits else t)

    # Call-ins (#520, GOV-0023): `Call in:` lines on ready issues, questions included.
    for it in sorted(w.issues, key=lambda i: i["number"]):
        n = it["number"]
        labels = {lb.get("name") for lb in it.get("labels") or []}
        if it.get("state") != "open" or "pull_request" in it or "ready" not in labels or is_tracking(it):
            continue
        ready = owner_label(w.events.get(n, []), "ready", owner)
        if not ready:
            continue
        for t in calls(n, w.comments.get(n, []), ready, owner, apps or {}, roles):
            if t.skipped:
                out.append(t)
            elif not call_ins:
                out.append(replace(t, skipped=CALL_INS_OFF))
            else:
                h = held_by(n, m, started, now, stale_minutes, t.role)
                out.append(replace(t, held=h[0], once=h[1]) if h else t)

    # The daily report (#588, GOV-0029): waits only for a planner live on the report issue.
    t = daily_trigger(now, daily_at, report_issue, tz) if daily_at and report_issue else None
    if t:
        h = held_by(report_issue, m, started, now, stale_minutes, t.role)
        out.append(replace(t, held=h[0], once=h[1]) if h else t)

    # Owner asks (#590, GOV-0029): wait only for a session of the asked role on the issue.
    if ask_issue:
        for t in asks(ask_issue, w.comments.get(ask_issue, []), owner, roles, asks_since):
            h = None if t.skipped else held_by(ask_issue, m, started, now, stale_minutes, t.role)
            out.append(replace(t, held=h[0], once=h[1]) if h else t)
    return out


def local_day(now: dt.datetime, tz: dt.tzinfo | None = None) -> dt.datetime:
    """now in tz, or in this machine's local time zone."""
    return now.astimezone(tz) if tz else now.astimezone()


def daily_trigger(now: dt.datetime | None, daily_at: dt.time, report_issue: int,
                  tz: dt.tzinfo | None = None) -> Trigger | None:
    """[daily] (#588, GOV-0029): due on a working day at or after daily_at, local time.
    Keyed on the local date, so it fires once a day however many checks see it."""
    if now is None:
        return None
    local = local_day(now, tz)
    if local.weekday() not in WORKDAYS or local.time() < daily_at:
        return None
    what = ("the daily report and the Monday check-in" if local.weekday() == 0
            else "the daily report")
    return Trigger(key=f"{DAILY}:{report_issue}:{local:%Y-%m-%d}", kind=DAILY,
                   ref=f"#{report_issue}", why=f"{local:%a %Y-%m-%d}, due at {daily_at:%H:%M}",
                   role="planner", command=f"planner on #{report_issue}, {what}",
                   issue=report_issue, daily=what)


def daily_key_day(key: str) -> str | None:
    """The local date in a [daily] key, or None if it isn't one."""
    parts = key.split(":")
    return parts[2] if len(parts) == 3 and parts[0] == DAILY else None


def next_daily(now: dt.datetime, daily_at: dt.time, report_issue: int, acted: dict,
               tz: dt.tzinfo | None = None) -> str:
    """When [daily] is next due, for `swarm inbox` (#588): "due now" if today's is due and
    not yet acted on, else the next working day at daily_at."""
    local = local_day(now, tz)
    day = local.date()
    if (local.weekday() in WORKDAYS and local.time() >= daily_at
            and f"{DAILY}:{report_issue}:{day}" not in acted):
        return "due now"
    if local.weekday() not in WORKDAYS or local.time() >= daily_at:
        day += dt.timedelta(days=1)
    while day.weekday() not in WORKDAYS:
        day += dt.timedelta(days=1)
    return f"next due {day:%a %Y-%m-%d} at {daily_at:%H:%M}"


def daily_text(limits: "manifest.WatchLimits | None", acted: dict, now: dt.datetime,
               tz: dt.tzinfo | None = None) -> str | None:
    """`swarm inbox`'s [daily] line (#588), or None while daily is off."""
    if not (limits and limits.daily and limits.daily_at and limits.report_issue):
        return None
    when = next_daily(now, limits.daily_at, limits.report_issue, acted, tz)
    return (f"swarm watch's [daily]: the planner writes the daily report on #{limits.report_issue} "
            f"each working day at {limits.daily_at:%H:%M} local time (GOV-0029); {when}")


def call_line(body: str | None) -> tuple[list[str], str] | None:
    """(the roles, the why) from a comment's first `Call in: <role>, <role>: <why>` line,
    or None if it has none (#520). Roles are lower-cased, each once, in order; the why is
    one line, at most WHY_MAX characters."""
    m = CALL_RE.search(body or "")
    if not m:
        return None
    names = [r.strip(" `*@").lower() for r in m.group(1).split(",")]
    why = " ".join((m.group(2) or "").split())
    return list(dict.fromkeys(r for r in names if r)), why[:WHY_MAX]


def ask_line(body: str | None) -> tuple[list[str], str] | None:
    """(the names, the question) from a comment's first `Ask: <role>: <question>` line, or
    None if it has none (#590). Names are lower-cased, split on commas so a line naming two
    roles can be told apart; the question is one line, at most WHY_MAX characters."""
    m = ASK_RE.search(body or "")
    if not m:
        return None
    names = [r.strip(" `*@").lower() for r in m.group(1).split(",")]
    question = " ".join((m.group(2) or "").split())
    return [r for r in names if r], question[:WHY_MAX]


def asks(n: int, comments: list[dict], owner: str, roles: set[str],
         since: dt.datetime | None = None) -> list[Trigger]:
    """GOV-0029's [ask] triggers on report issue n (#590): one per `Ask:` comment, keyed on
    the comment id, starting the named role, or a skipped one saying why it doesn't count.
    A comment posted before since (when asks was turned on) is skipped too."""
    out = []
    for c in sorted(comments, key=lambda c: (c.get("created_at") or "", c.get("id") or 0)):
        parsed = ask_line(c.get("body"))
        if not parsed:
            continue
        names, question = parsed
        cid, login = c.get("id"), (c.get("user") or {}).get("login") or "unknown"
        at = c.get("created_at")
        base = dict(key=f"{ASK}:{n}:{cid}", kind=ASK, ref=f"#{n}", issue=n,
                    why=f"ask by {login} (comment {cid})" + (f": {names[0]}" if len(names) == 1 else ""))
        posted = dt.datetime.fromisoformat(at) if at else None
        bad = (f"{login} isn't the owner, and only the owner's asks count (GOV-0029)" if login != owner
               else "the line names no role" if not names
               else f"the line names {len(names)} roles; an ask names one" if len(names) > 1
               else f"{names[0]!r} isn't a role with a prompt in roles/" if names[0] not in roles
               else "the line asks no question" if not question
               else "posted before asks was turned on in swarm.toml's [watch]"
               if since and (posted is None or posted < since) else None)
        if bad:
            out.append(Trigger(**base, skipped=bad))
            continue
        r = names[0]
        out.append(Trigger(**base, role=r, command=f"{r} on #{n}, to answer the ask",
                           ask=question, ask_comment=cid))
    return out


def calls(n: int, comments: list[dict], ready: dict, owner: str, apps: dict[str, str],
          roles: set[str]) -> list[Trigger]:
    """GOV-0023's [call-in] triggers on ready issue n, from its comments (#520): one per
    named role per call, keyed on the comment id, or a skipped one saying why it doesn't
    count. ready is the owner's `ready` event: a call posted before it doesn't count."""
    since, out, per_day = ready.get("created_at") or "", [], {}
    for c in sorted(comments, key=lambda c: (c.get("created_at") or "", c.get("id") or 0)):
        parsed = call_line(c.get("body"))
        at = c.get("created_at") or ""
        if not parsed or (since and at and at < since):
            continue
        names, why = parsed
        cid, login = c.get("id"), (c.get("user") or {}).get("login") or "unknown"
        caller = "owner" if login == owner else apps.get(login)
        key, what = f"call-in:{n}:{cid}", f"call in by {login} (comment {cid})"
        call = dict(kind=CALL_IN, ref=f"#{n}", issue=n)
        if caller is None:
            out.append(Trigger(key=key, why=what, **call,
                               skipped=f"{login} isn't a swarm App or the owner, so the call doesn't "
                                       f"count (GOV-0023)"))
            continue
        ok = []
        for r in names:
            bad = ("a role can't call itself in (GOV-0023)" if r == caller else
                   f"{r!r} isn't a role with a prompt in roles/" if r not in roles else None)
            if bad:
                out.append(Trigger(key=f"{key}:{r}", why=f"{what}: {r}", skipped=bad, **call))
            else:
                ok.append(r)
        if not ok:
            if not names:
                out.append(Trigger(key=key, why=what, skipped="the line names no role", **call))
            continue
        day = at[:10]
        if per_day.get(day, 0) >= MAX_CALLS:
            out.append(Trigger(key=key, why=what, **call,
                               skipped=f"#{n} already has {MAX_CALLS} calls on {day or 'that day'} "
                                       f"(UTC), the most that count per issue per day (GOV-0023)"))
            continue
        per_day[day] = per_day.get(day, 0) + 1
        who = "the owner" if caller == "owner" else f"the {caller} ({login})"
        for r in ok:
            out.append(Trigger(key=f"{key}:{r}", why=f"{what}: {r}", role=r,
                               command=f"{r} on #{n}, called in", called_by=who,
                               call_why=why or None, **call))
    return out


def swarm_apps(path: Path = swarm.JURISDICTIONS) -> tuple[dict[str, str], str | None]:
    """({swarm App login: role}, why none) from identities.agents in jurisdictions.yml, the
    list GOV-0024 trusts (#520). If it can't be read, no App counts: only the owner's calls
    do, and the reason says why."""
    if str(swarm.ROOT / "dashboard") not in sys.path:
        sys.path.insert(0, str(swarm.ROOT / "dashboard"))
    import authority   # jurisdictions.yml's reader
    try:
        doc = authority.read(Path(path).read_text())
    except (OSError, UnicodeDecodeError, ValueError) as e:
        return {}, f"can't read {authority.JURISDICTIONS_PATH} ({e.__class__.__name__})"
    ids = doc.get("identities")
    agents = ids.get("agents") if isinstance(ids, dict) else None
    if not isinstance(agents, dict) or not agents:
        return {}, f"{authority.JURISDICTIONS_PATH} has no identities.agents mapping"
    return {v: k for k, v in agents.items() if isinstance(k, str) and isinstance(v, str)}, None


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


def milestone_go(it: dict, w: World, owner: str, agents: set[str]) -> int | None:
    """n if issue `it` is go by its milestone M<n> on this tick's reading (GOV-0026, #583),
    else None. Its `**Waits on:**` issues aren't checked here: blocked() holds the build
    until they close, as it does for `ready` (#490)."""
    n, m = it["number"], swarm.milestone_of(it.get("body"))
    if m is None:
        return None
    r = swarm.GoReader(plan=lambda: w.plan, state=lambda _: "closed",
                       comments=lambda: w.comments.get(n, []))
    return None if swarm.milestone_refusal(n, it, owner, agents, r) else m


def open_issues(w: World) -> set[int]:
    return {i["number"] for i in w.issues if i.get("state") == "open" and "pull_request" not in i}


def said_waits(comments: list[dict], since: str, builders: set[str]) -> list[int]:
    """The issues a builder's last comment on an issue, posted at or after `since`, says it
    waits on (#550): the #N refs in the rest of each sentence that says "waits on" or
    "waiting for". None if the builder hasn't commented since then."""
    start = dt.datetime.fromisoformat(since)
    mine = [c for c in comments if (c.get("user") or {}).get("login") in builders
            and c.get("created_at") and dt.datetime.fromisoformat(c["created_at"]) >= start]
    if not mine:
        return []
    out = set()
    for m in WAIT_RE.finditer(mine[-1].get("body") or ""):
        sentence = re.split(r"[.;:](?:\s|$)", m.group(1), maxsplit=1)[0]
        out |= {int(x) for x in REF_RE.findall(sentence)}
    return sorted(out)


def blocked(body: str | None, w: World) -> str | None:
    """Why a [build] is held because an issue its `**Waits on:**` line names is still open
    (#490), or None. Open means an open issue in this tick's reading; anything else counts
    as closed."""
    open_ = open_issues(w)
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
    w = World(model=model, issues=issues, plan=swarm.gh_plan(repo))   # PLAN.md once per check (#583)
    for it in issues:
        labels = {lb.get("name") for lb in it.get("labels") or []}
        # A milestone issue (#583) needs its events (ready, a lifted hold) and its comments
        # (the owner's veto), like a ready one.
        milestone = ("gov:question" not in labels and not g.is_tracking(it)
                     and swarm.milestone_of(it.get("body")) is not None)
        if (labels & {"ready", "gov:ruled"} and not g.is_tracking(it)) or milestone:
            w.events[it["number"]] = g.gh_items(f"repos/{repo}/issues/{it['number']}/events?per_page=100")
        if ({"gov:question", "gov:ruled"} <= labels or ("ready" in labels and not g.is_tracking(it))
                or milestone):
            # the owner's `Record: yes` (#501), and `Call in:` lines on ready issues (#520)
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
    "runs": {key: run record}, "asks_since": {report issue: ISO time}}. A run record (#149)
    is {session_id, name, kind, ref, started}, plus {ending, detail, cost_usd, subtype,
    ended} once the run has ended. asks_since (#590) is when the watcher first saw [watch]
    asks on for that report issue; it is empty while asks is off."""
    try:
        data = json.loads(state_path(launcher).read_text())
    except FileNotFoundError:
        return {"checked": None, "acted": {}, "waiting": [], "runs": {}, "asks_since": {}}
    except ValueError as e:
        raise RuntimeError(f"{state_path(launcher)} is not valid JSON: {e}") from None
    return {"checked": data.get("checked"), "acted": dict(data.get("acted") or {}),
            "waiting": list(data.get("waiting") or []), "runs": dict(data.get("runs") or {}),
            "asks_since": dict(data.get("asks_since") or {})}


def gh_comments(repo: str, n: int) -> list[dict]:
    """Every comment on issue n, oldest first: the report issue's, for [ask] (#590)."""
    return swarm.dashboard().gh_items(f"repos/{repo}/issues/{n}/comments?per_page=100")


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


def save_state(launcher: "swarm.Launcher", st: dict, name: str = STATE_FILE) -> None:
    """Write watch.json (or `name` beside it) atomically through a temp file of its own, so
    two writers never rename each other's (#296), as Launcher.save() does for sessions.json
    (#272)."""
    launcher.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=launcher.dir, prefix=".watch.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(st, indent=1) + "\n")
        os.replace(tmp, launcher.dir / name)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def held_code(reason: str) -> str:
    """The code for a hold that triggers() set (#456): held_by()'s live or stale session, or
    blocked()'s open Waits-on issues."""
    if reason.startswith("stale:"):
        return "stale"
    return "waits_on" if reason.startswith("held: waits on ") else "live"


def reason_text(code: str | None, args: dict | None = None) -> tuple[str, str]:
    """(code, sentence) for a waiting entry; an unknown code, or a sentence whose fields
    aren't all integers, is "other"."""
    if code not in REASONS:
        return "other", REASONS["other"]
    args = args or {}
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in args.values()):
        return "other", REASONS["other"]
    try:
        return code, REASONS[code].format(**args)
    except (KeyError, IndexError, ValueError):
        return "other", REASONS["other"]


def public_state(st: dict, live: list, now: dt.datetime) -> dict:
    """watch.json in a form fit to show (#456): what swarm watch is running, holding and
    skipping, and which of its runs failed in the last RUNS_DAYS. Pure. Each field is picked
    by name, and reasons are codes with REASONS' sentences, so no cost (GOV-0014), detail
    or text copied from an issue gets in."""
    alive = {e.session_id: e for e in live}
    runs = list((st.get("runs") or {}).values())
    running = sorted(({"role": alive[r["session_id"]].role, "kind": r["kind"], "ref": r["ref"],
                       "started": r["started"]}
                      for r in runs if not r.get("ending") and r.get("session_id") in alive),
                     key=lambda x: x["started"])
    held, skipped = [], []
    for x in st.get("waiting") or []:
        code, sentence = reason_text(x.get("code"), x.get("args"))
        (skipped if code in SKIPS else held).append(
            {"ref": x["ref"], "kind": x["kind"], "code": code, "reason": sentence, "since": x["since"]})
    since = now - dt.timedelta(days=RUNS_DAYS)
    failed = sorted(({"ref": r["ref"], "kind": r["kind"], "ending": ENDINGS[r["ending"]],
                      "ended": r["ended"]}
                     for r in runs if r.get("ending") in ENDINGS and r.get("ended")
                     and dt.datetime.fromisoformat(r["ended"]) >= since),
                    key=lambda x: x["ended"], reverse=True)
    return {"checked": st.get("checked"), "running": running, "held": held, "skipped": skipped,
            "failed": failed}


# ---------------------------------------------------------------- swarm status (#457)

STALE_CHECKS = 2              # `swarm status` calls `checked` stale after this many intervals


def lock_holder(launcher: "swarm.Launcher") -> int | None:
    """The pid of the swarm watch holding watch.lock, or None. Read-only: it never takes
    the lock, even briefly, so it can't make a starting watcher exit (#273). The pid in
    the file counts only while that process is still a `swarm watch`, so a pid reused by
    another process after the watcher ended doesn't count."""
    try:
        pid = int((launcher.dir / LOCK_FILE).read_text().strip())
    except (OSError, ValueError):
        return None
    cmd = launcher.proc(pid) or ""
    return pid if re.search(r"\bswarm(\.py)?\s+watch\b", cmd) and "--dry-run" not in cmd else None


def spool_cost(home: Path, sid: str) -> float | None:
    """A running session's cost so far (#457): the dashboard's estimate (dashboard/spend.py)
    from the token counts on the last event in its local heartbeat spool,
    ~/.productswarm/events/<sid>.jsonl. Only the file's tail is read. None if there is no
    spool, or its last event has no figure."""
    swarm.dashboard()             # puts dashboard/ on sys.path
    import spend
    try:
        with open(home / "events" / f"{sid}.jsonl", "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 8192))
            lines = f.read().splitlines()
    except OSError:
        return None
    for raw in reversed(lines):
        try:
            ev = json.loads(raw)
        except ValueError:
            continue
        if isinstance(ev, dict):
            return spend.event_cost(ev)
    return None


def status_text(st: dict, live: list, now: dt.datetime, *, holder: int | None,
                interval: float, cost_of: Callable[[str], float | None], ago: Callable) -> str:
    """`swarm status` (#457): public_state() (#456) plus cost, one line per item, from local
    files only. st is load_state(); live is the launcher's live sessions; holder is
    lock_holder(); interval is [watch] interval_minutes; cost_of(session_id) is a running
    session's cost so far. Costs are printed only: they never leave this machine
    (GOV-0002, GOV-0003, GOV-0004, GOV-0014)."""
    pub = public_state(st, live, now)
    runs = list((st.get("runs") or {}).values())
    sid = {(r["kind"], r["ref"], r["started"]): r.get("session_id") for r in runs}
    spent = {(r["kind"], r["ref"], r.get("ended")): r.get("cost_usd") for r in runs}
    checked = dt.datetime.fromisoformat(pub["checked"]) if pub["checked"] else None
    when = lambda t: ago(dt.datetime.fromisoformat(t), now)

    head = (f"swarm watch: running (pid {holder})" if holder
            else "swarm watch: not running (nothing holds watch.lock)")
    head += f" · last check {ago(checked, now)}"
    if checked and now - checked > dt.timedelta(minutes=STALE_CHECKS * interval):
        head += f" · stale: checks are every {interval:g} min"
    out = [head]

    def section(title: str, lines: list[str]) -> None:
        out.append(f"\n{title} ({len(lines)}):" if lines else f"\n{title}: none")
        out.extend(lines)

    def took(start: str) -> str:
        m = max(0, int((now - dt.datetime.fromisoformat(start)).total_seconds()) // 60)
        return f"{m // 60}h {m % 60:02d}m" if m >= 60 else f"{m}m"

    section("running", [f"- [{r['kind']}] {r['ref']} {r['role']} · {took(r['started'])} · "
                        f"{usd(cost_of(sid.get((r['kind'], r['ref'], r['started'])) or ''))} so far (est.)"
                        for r in pub["running"]])
    section("held", [f"- [{x['kind']}] {x['ref']} · {x['reason']} · since {when(x['since'])}"
                     for x in pub["held"]])
    section("skipped", [f"- [{x['kind']}] {x['ref']} · {x['reason']} · since {when(x['since'])}"
                        for x in pub["skipped"]])
    section(f"failed in the last {RUNS_DAYS} days",
            [f"- [{r['kind']}] {r['ref']} · {r['ending'].replace('_', ' ')} · ended {when(r['ended'])} · "
             f"{usd(spent.get((r['kind'], r['ref'], r['ended'])))} (est.)" for r in pub["failed"]])
    out.append("\nCosts are estimates and stay on this machine: a running session's is its heartbeat "
               "tokens at list price (dashboard/spend.py); an ended run's is Claude Code's own.")
    return "\n".join(out)


# ---------------------------------------------------------------- the [watch] issue (#458)

WATCH_MARKER = "<!-- productswarm-watch -->"   # the [watch] issue's body starts with this
WATCH_TITLE = "[watch] swarm watch's state"
WATCH_HELP = (f"no open issue you opened starts with {WATCH_MARKER}, so swarm watch's state "
              f"isn't published; open it once with: gh issue create --repo {{repo}} "
              f"--title \"{WATCH_TITLE}\" --body '{WATCH_MARKER}'")


def watch_body(pub: dict) -> str:
    """The [watch] issue's body: the marker line, then public_state() as a fenced json block.
    Nothing else, so no text from another issue gets in."""
    return (f"{WATCH_MARKER} swarm watch's state, written by `swarm watch` after a check that "
            f"changed it (#458). Don't edit: the next change replaces it.\n\n"
            f"```json\n{json.dumps(pub, indent=1)}\n```\n")


def changes(pub: dict | None) -> dict | None:
    """public_state() without `checked`, which moves on every tick: two ticks that hold the
    same of this are the same state, and the second publishes nothing."""
    return None if pub is None else {k: v for k, v in pub.items() if k != "checked"}


def body_state(body: str | None) -> dict | None:
    """The public state in a [watch] issue's body, or None if it has none it can read."""
    m = re.search(r"```json\n(.*?)\n```", (body or "").replace("\r\n", "\n"), re.S)
    try:
        got = json.loads(m.group(1)) if m else None
    except ValueError:
        return None
    return got if isinstance(got, dict) else None


def watch_issues(issues: list[dict]) -> list[dict]:
    """Open issues (not PRs) whose body starts with WATCH_MARKER, as digest_issues() does."""
    return [i for i in issues if i.get("state") == "open" and "pull_request" not in i
            and (i.get("body") or "").lstrip().startswith(WATCH_MARKER)]


def owner_issues(repo: str, owner: str) -> list[dict]:
    """The open issues `owner` opened. A read only; raises RuntimeError."""
    return swarm.dashboard().gh_items(f"repos/{repo}/issues?state=open&creator={owner}&per_page=100")


def edit_body(repo: str, n: int, body: str) -> None:
    """Replace issue n's body: one PATCH, nothing else. Raises RuntimeError if it fails."""
    r = subprocess.run(["gh", "api", "-X", "PATCH", f"repos/{repo}/issues/{n}", "--input", "-"],
                       input=json.dumps({"body": body}), capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"editing #{n} failed: {r.stderr.strip()[:300]}")


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


def runs_text(runs: list[dict], now: dt.datetime,
              ago: Callable) -> tuple[list[str], list[str], list[str]]:
    """(lines for runs that ended at cap, lines for every ended run, newest first, lines for
    runs that never started after MAX_RETRIES retries), within RUNS_DAYS. runs is
    watch.runs(): every record, including runs still live.

    A run that ended at cap, or never started (#550), is listed until a later run on the
    same ref has started (the owner restarted it with a fresh label, or the loop moved on),
    or RUNS_DAYS pass. One that never started names every session id it was tried as."""
    since = now - dt.timedelta(days=RUNS_DAYS)
    recent = sorted((r for r in runs if r.get("ending") and r.get("ended")
                     and dt.datetime.fromisoformat(r["ended"]) >= since),
                    key=lambda r: r["ended"], reverse=True)
    capped = [r for r in recent if r["ending"] == AT_CAP
              and not any(o["ref"] == r["ref"] and o["started"] > r["started"] for o in runs)]
    gave_up = [r for r in recent if r.get("gave_up")
               and not any(o["ref"] == r["ref"] and o["started"] > r["started"] for o in runs)]
    when = lambda r: f" · ended {ago(dt.datetime.fromisoformat(r['ended']), now)}"
    sessions = lambda r: ", ".join(r.get("never_started", []) + [r["session_id"]])
    return ([f"- {run_line(r)}{when(r)}" for r in capped],
            [f"- {run_line(r)}{when(r)}" for r in recent],
            [f"- {run_line(r)}{when(r)} · sessions {sessions(r)}" for r in gave_up])


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

class Restart(Exception):
    """Raised between checks to re-exec swarm watch on new launcher code (#550)."""


def reexec() -> None:
    """Replace this process with a fresh `swarm watch`, same arguments (#550)."""
    sys.stdout.flush()
    sys.stderr.flush()
    os.execv(sys.executable, [sys.executable, str(Path(sys.argv[0]).resolve()), *sys.argv[1:]])


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
    get_reader: Callable[[str, int], "swarm.GoReader"] = swarm.gh_go_reader   # milestone go (#583)
    seen: set[str] = field(default_factory=set)                      # dry-run memory
    roles_from: Path | None = None    # repo root whose roles/ is re-read every tick (#487)
    jurisdictions: Path = swarm.JURISDICTIONS   # always_one_way domains, re-read every tick (#519)
    loaded: str | None = None         # the launcher/ tree this process runs, for code_check (#550)
    restart: Callable[[], None] = reexec
    said: set[str] = field(default_factory=set)   # code_check's lines, each said once
    tz: dt.tzinfo | None = None       # [daily]'s time zone (#588); None: this machine's
    get_comments: Callable[[str, int], list[dict]] = gh_comments    # the report issue's, for [ask] (#590)

    def once(self, line: str) -> None:
        if line not in self.said:
            self.said.add(line)
            self.launcher.out(line)

    def code_check(self) -> bool:
        """Whether to restart now on new launcher code (#550). Fetches origin/main, and if
        its launcher/ tree isn't the one this process loaded, says so once. It restarts only
        when nothing it started is still starting, and only after fast-forwarding the
        checkout it runs from to origin/main: that needs the checkout on main, with no
        changes to tracked files and no commits of its own. Otherwise it says why once and
        carries on with the code it has."""
        l, root = self.launcher, str(self.launcher.root)
        if not self.loaded:
            return False
        try:
            l.refetch()
        except RuntimeError as e:
            self.once(f"swarm watch: can't look for new launcher code on origin/main: {e}")
            return False
        rc, tree = l.git(["-C", root, "rev-parse", "origin/main:launcher"])
        if rc or not tree or tree == self.loaded:
            return False
        rc, n = l.git(["-C", root, "rev-list", "--count", "HEAD..origin/main", "--", "launcher"])
        commits = (f"{n} new commit{'s' * (n != '1')}" if rc == 0 and n.isdigit() else "new commits")
        self.once(f"swarm watch: origin/main has {commits} under launcher/; "
                  f"restarting on them once nothing it started is still starting (#550)")
        if any(e.by == "watch" and l.state(e) == "starting" for e in l.running()):
            return False
        rc, branch = l.git(["-C", root, "symbolic-ref", "--short", "-q", "HEAD"])
        rc2, changed = l.git(["-C", root, "status", "--porcelain", "--untracked-files=no"])
        why = (f"{root} is on {branch or 'a detached HEAD'}, not main" if rc or branch != "main" else
               f"{root} has changes to tracked files" if rc2 or changed else None)
        if why is None:
            rc, out = l.git(["-C", root, "merge", "--ff-only", "-q", "origin/main"])
            why = f"can't fast-forward {root} to origin/main: {out[:200]}" if rc else None
        if why:
            self.once(f"swarm watch: not restarting on the new launcher code: {why}. Pull and "
                      f"restart swarm watch by hand")
            return False
        l.out("swarm watch: restarting on origin/main's launcher code (#550)")
        return True

    # The [watch] issue (#458): `swarm watch` passes owner_issues and edit_body; None (tests,
    # by default) publishes nothing. `published` is the state last published, or None.
    list_issues: Callable[[str, str], list[dict]] | None = None
    edit_issue: Callable[[str, int, str], None] | None = None
    published: dict | None = None
    told_missing: bool = False

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

    def one_way(self) -> frozenset[str]:
        """jurisdictions.yml's always_one_way domains, read now so a domain the owner marks
        later counts on the next check (#519). If the file can't be read it says so, every
        tick, and only the body's ratings count."""
        domains, why = one_way_domains(self.jurisdictions)
        if why:
            self.launcher.out(f"swarm watch: {why}; only a question's own ratings count for [record]")
        return domains

    def apps(self) -> dict[str, str]:
        """The swarm Apps whose `Call in:` lines count (#520), read now from
        jurisdictions.yml. If it can't be read it says so, every tick, and only the owner's
        calls count."""
        apps, why = swarm_apps(self.jurisdictions)
        if why:
            self.launcher.out(f"swarm watch: {why}; only the owner's `Call in:` lines count")
        return apps

    def dry_tick(self, now: dt.datetime) -> list[Trigger]:
        """Print and return the triggers not seen before. Starts nothing, writes nothing.
        A held trigger (#488, #490) is printed once per reason and not returned; it prints
        as a trigger once its holder has stopped or its Waits-on issues have closed."""
        g = swarm.dashboard()
        w = self.read(self.repo, self.idle_minutes, now)
        limits = self.limits()
        try:
            kept = load_state(self.launcher)["asks_since"]
        except RuntimeError:
            kept = {}
        ask_n, since = self.asks(w, limits, kept, now)
        new = []
        for t in triggers(w, self.owner, self.launcher.running(), self.roles, g.needs_you,
                          g.is_tracking, bool(limits and limits.review_in_actions), now,
                          limits.stale_minutes if limits else DEFAULT_STALE, self.one_way(),
                          self.apps(), bool(limits and limits.call_ins), *self.daily(limits),
                          ask_issue=ask_n, asks_since=since):
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

    def daily(self, limits: "manifest.WatchLimits | None") -> tuple:
        """triggers()'s daily_at, report_issue and tz: (None, None, tz) while [daily] is off."""
        on = bool(limits and limits.daily)
        return ((limits.daily_at, limits.report_issue) if on else (None, None)) + (self.tz,)

    def asks(self, w: World, limits: "manifest.WatchLimits | None", kept: dict,
             now: dt.datetime) -> tuple[int | None, dt.datetime | None]:
        """[ask] (#590): (the report issue, when asks was first seen on for it), or (None,
        None) while asks is off. With asks on it reads the report issue's comments into w,
        unless gather() already did. kept is watch.json's asks_since."""
        n = limits.report_issue if limits and limits.asks else None
        if not n:
            return None, None
        if n not in w.comments:
            w.comments[n] = self.get_comments(self.repo, n)
        since = kept.get(str(n))
        return n, dt.datetime.fromisoformat(since) if since else now

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
                             budget_usd=s.spend_cap_usd, max_turns=limits.max_turns,
                             called_by=t.called_by, call_why=t.call_why, daily=t.daily,
                             ask=t.ask, ask_comment=t.ask_comment)

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
        runs = self.record_ended(st["runs"], live, now, acted, w)
        limited = limit_reason(runs, now)
        if limited and not any(x.get("reason") == limited for x in st["waiting"]):
            out(f"swarm watch: a run hit the account's usage limit; {limited}, for every start (#489)")
        ask_n, since = self.asks(w, limits, st["asks_since"], now)
        # #590: kept while asks is on for this report issue; dropped as soon as it is off.
        asks_since = {str(ask_n): iso(since)} if ask_n else {}
        todo = [t for t in triggers(w, self.owner, live, self.roles, g.needs_you, g.is_tracking,
                                    limits.review_in_actions, now, limits.stale_minutes,
                                    self.one_way(), self.apps(), limits.call_ins,
                                    *self.daily(limits), ask_issue=ask_n, asks_since=since)
                if t.key not in acted]
        today = local_day(now, self.tz).strftime("%Y-%m-%d")
        for x in st["waiting"]:
            day = daily_key_day(x["key"])
            if day and day != today and x["key"] not in acted:
                # #588: a day ended without its [daily] run. Logged once (the entry leaves
                # "waiting" on this check); not caught up.
                out(f"[daily] {x['ref']} {day}: no daily report run that day ({x.get('reason')}); "
                    f"not caught up (GOV-0029)")
        todo.sort(key=lambda t: before.get(t.key, {}).get("since", iso(now)))  # held longest first
        held, done, reviewer = [], [], None

        def finish(t: Trigger, outcome: str) -> None:
            acted[t.key] = outcome
            done.append(t)
            save_state(self.launcher, {"checked": iso(now), "acted": acted, "waiting": st["waiting"],
                                       "runs": runs, "asks_since": asks_since})

        def hold(t: Trigger, reason: str, once: str | None = None, code: str = "other",
                 args: dict | None = None) -> None:
            was = before.get(t.key, {})
            entry = {"key": t.key, "kind": t.kind, "ref": t.ref, "why": t.why,
                     "reason": reason, "code": code, "since": was.get("since", iso(now))}
            if args:
                entry["args"] = args
            if once:
                entry["once"] = once
            held.append(entry)
            if reason != limited and (was.get("once") or was.get("reason")) != (once or reason):   # each reason once
                out(f"[{t.kind}] {t.ref} {t.why} -> {reason}")

        for t in todo:
            if t.skipped in NOT_RECORDED:
                # Not recorded in watch.json: flip the switch and the loop acts on it again.
                if t.key not in self.seen:
                    self.seen.add(t.key)
                    out(t.line())
                continue
            if t.held:
                # #488: a live session is on the issue, or #490: a [build]'s Waits-on issues are
                # still open. Listed in `swarm inbox` with why, never recorded in `acted`; it
                # starts once that clears. The loop never stops a session (GOV-0008).
                hold(t, t.held, t.once, held_code(t.held))
                continue
            if t.kind == "answer" and t.skipped:
                # Listed in `swarm inbox` until the owner closes the question or drops `ready` (#271).
                hold(t, f"skipped: {t.skipped}", code="raised_by")
                continue
            if t.skipped:
                out(t.line())
                finish(t, f"skipped: {t.skipped}")
                continue
            if t.after and t.after not in acted:
                # #495: docs records the ruling first; once [record] is acted on, the held
                # check above and the holders check below keep [answer] waiting until docs
                # has stopped.
                hold(t, f"held: docs records the ruling on {t.ref} first, then {t.role} starts",
                     code="record_first")
                continue
            if t.kind == "review" and reviewer:
                out(f"[review] {t.ref} {t.why} -> covered by {reviewer}")
                finish(t, f"covered by {reviewer}")
                continue
            if t.issue is not None and swarm.holders(t.issue, w.model, live, own_role(t)):
                continue      # a session started this check is on it; it fires again once that stops
            prev = runs.get(t.key) or {}
            still = [n for n in prev.get("waits_on") or [] if n in open_issues(w)]
            if still:
                # #550: its last run's builder said it waits on these; it starts once they close.
                hold(t, f"held: waits on {', '.join(f'#{n}' for n in still)} (the builder said so "
                        f"on {t.ref})", code="waits_on")
                continue
            if t.held:
                # #490: not acted on, so it starts on the first check after its blockers close.
                hold(t, t.held, code=held_code(t.held))
                continue
            s = by_role.get(t.role)
            mine = sum(e.by == "watch" for e in live)
            if s is None:
                hold(t, f"skipped: {t.role} isn't in swarm.toml", code="no_role")
                continue
            if s.spend_cap_usd is None:
                hold(t, f"skipped: {t.role} has no spend_cap_usd in swarm.toml, and swarm watch "
                        f"starts only capped roles (GOV-0010)", code="no_cap")
                continue
            if limited:
                hold(t, limited, code="usage_limit")   # said once above: the limit is account-wide
                continue
            busy_with = overlap(t.issue, w, live) if t.kind == "build" else None
            if busy_with:
                hold(t, busy_with, code="overlap")
                continue
            if mine >= limits.max_live:
                hold(t, f"held: {mine} of {limits.max_live} sessions swarm watch started are live (GOV-0010)",
                     code="limit", args={"live": mine, "max": limits.max_live})
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
                if prev.get("retry"):     # #550: the same trigger again, after a run that never started
                    runs[t.key]["tries"] = prev.get("tries", 1) + 1
                    runs[t.key]["never_started"] = prev.get("never_started", []) + [prev["session_id"]]
                finish(t, f"started {entry.name}")
            else:
                hold(t, "failed to start (see above); trying again next check", code="error")
        st = {"checked": iso(now), "acted": acted, "waiting": held, "runs": runs,
              "asks_since": asks_since}
        save_state(self.launcher, st)
        pub = public_state(st, self.launcher.live(), now)
        save_state(self.launcher, pub, PUBLIC_FILE)
        self.publish(pub)
        return done

    def publish(self, pub: dict) -> None:
        """Write pub into the [watch] issue if the state changed (#458), as the watcher's own
        `gh` login (the owner's, per the owner's direction on #451). Its only write is one
        PATCH of that issue's body: never a comment, label or new issue. A tick whose state
        (less `checked`) matches the last one published reads and writes nothing; after a
        restart the issue's own body is compared first. A missing issue or a failed read or
        edit is printed, and the loop carries on: it never fails on a publish error."""
        if self.list_issues is None or self.edit_issue is None or changes(pub) == self.published:
            return
        try:
            found = watch_issues(self.list_issues(self.repo, self.owner))
            if len(found) != 1:
                if found:
                    nums = ", ".join(f"#{i['number']}" for i in found)
                    self.launcher.out(f"swarm watch: {len(found)} open issues start with "
                                      f"{WATCH_MARKER} ({nums}); close all but one to publish")
                elif not self.told_missing:
                    self.launcher.out(f"swarm watch: {WATCH_HELP.format(repo=self.repo)}")
                    self.told_missing = True
                return
            n = found[0]["number"]
            if changes(body_state(found[0].get("body"))) != changes(pub):
                self.edit_issue(self.repo, n, watch_body(pub))
                self.launcher.out(f"swarm watch: published its state to #{n}")
        except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as e:
            self.launcher.out(f"swarm watch: publishing its state failed: {e}; trying again "
                              f"next check")
            return
        self.published = changes(pub)

    def record_ended(self, runs: dict, live: list, now: dt.datetime, acted: dict,
                     w: World | None = None) -> dict:
        """Record how each run this loop started ended, once it is no longer live (#149):
        read its result file and log one line. Records older than RUNS_DAYS are dropped.
        Its trigger stays done in "acted", so the loop never starts it again by itself,
        unless:
        - the run was limited (#489): it records when the hold ends;
        - the run never started (#550): no result file, or no result and no transcript.
          It is tried again, at most MAX_RETRIES times; after that `swarm inbox` lists it;
        - a [build] ended with no open PR for its issue, and the builder's last comment says
          it waits on an issue that is open (#550): the run keeps those issues in
          "waits_on", and start_tick() holds the trigger until they close.
        In each case the trigger, and any review triggers its pass covered, come out of
        "acted" to fire again."""
        alive = {e.session_id for e in live}
        since = iso(now - dt.timedelta(days=RUNS_DAYS))
        kept = {}

        def again(key: str, r: dict) -> None:
            for k in [k for k, v in acted.items() if k == key or v == f"covered by {r['name']}"]:
                del acted[k]

        for key, r in runs.items():
            if r.get("ended") and r["ended"] < since:
                continue
            if not r.get("ending") and r["session_id"] not in alive:
                r = {**r, **read_result(self.launcher.result_file(r["session_id"])), "ended": iso(now)}
                waits = self.said_waits(r, w) if w is not None and r["kind"] == "build" else []
                if r["ending"] == LIMITED:
                    r["until"] = iso(limit_until(r["detail"], now))
                    again(key, r)
                    self.launcher.out(f"{run_line(r)} -> recorded; trying again after the hold")
                elif self.never_started(r) and r.get("tries", 1) <= MAX_RETRIES:
                    r["retry"] = True
                    again(key, r)
                    self.launcher.out(f"{run_line(r)} -> recorded; it never started, so trying again "
                                      f"(retry {r.get('tries', 1)} of {MAX_RETRIES})")
                elif self.never_started(r):
                    r["gave_up"] = True
                    self.launcher.out(f"{run_line(r)} -> recorded; it never started, after "
                                      f"{MAX_RETRIES} retries: listed in swarm inbox")
                elif waits:
                    r["waits_on"] = waits
                    again(key, r)
                    self.launcher.out(f"{run_line(r)} -> recorded; the builder says it waits on "
                                      f"{', '.join(f'#{n}' for n in waits)}: held until "
                                      f"{'they close' if len(waits) > 1 else 'it closes'}")
                else:
                    self.launcher.out(f"{run_line(r)} -> recorded")
            kept[key] = r
        return kept

    def never_started(self, r: dict) -> bool:
        """Whether an ended run never got as far as Claude Code (#550): no result file, or no
        JSON result and no transcript."""
        return r["ending"] == NO_RESULT and (r.get("detail") == "no result file"
                                             or self.launcher.transcript(r["session_id"]) is None)

    def said_waits(self, r: dict, w: World) -> list[int]:
        """The open issues a [build] run's builder said it waits on (#550), if it ended with
        its issue still open and no open PR closing it."""
        m = REF_RE.search(r["ref"])
        n = int(m.group(1)) if m else None
        open_ = open_issues(w)
        if n not in open_ or any(c["number"] == n for p in w.model.get("prs", []) for c in p["closes"]):
            return []
        builders = {login for login, role in self.apps().items() if role == "builder"} | {BUILDER_APP}
        return [x for x in said_waits(w.comments.get(n, []), r["started"], builders)
                if x in open_ and x != n]

    def refusal(self, t: Trigger, live: list, now: dt.datetime) -> tuple[str | None, bool]:
        """`swarm launch`'s refusal checks, run again on fresh GitHub data just before a
        start: (reason, False) refuses the trigger for good; (None, True) waits a check."""
        hb = self.get_heartbeat(self.repo, self.idle_minutes, now)
        if t.kind == "review":
            # A pass already running may have listed PRs before this push: wait for it.
            return None, bool(reviewers(hb, live))
        issue, events = self.get_issue(self.repo, t.issue)
        if t.kind in (DAILY, ASK):
            # #588, #590: the report issue needs no label, only to exist and be open.
            refused = ([f"#{t.issue} doesn't exist"] if issue is None else
                       [f"#{t.issue} is a pull request, not an issue"] if "pull_request" in issue else
                       [f"#{t.issue} is closed"] if issue.get("state") != "open" else [])
        elif t.kind in ("build", "respond"):
            # The owner's `ready`, or the issue's milestone (GOV-0026, #583), as `swarm launch`.
            refused = swarm.go_refusals(t.issue, issue, events, self.owner, set(self.apps()),
                                        self.get_reader(self.repo, t.issue))
        else:
            label = "gov:ruled" if t.kind == "record" else "ready"
            refused = swarm.issue_refusals(t.issue, issue, events, self.owner, label)
        if refused:
            return refused[0], False
        taken = swarm.holders(t.issue, hb, live, own_role(t))
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
        rc, tree = self.launcher.git(["-C", str(self.launcher.root), "rev-parse", "HEAD:launcher"])
        self.loaded = self.loaded or (tree if rc == 0 else None)
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
        except Restart:
            pass
        finally:
            os.close(fd)      # before a restart, so the new process takes the lock
        self.restart()
        return 0

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
                if not self.dry_run and self.code_check():
                    raise Restart
        except KeyboardInterrupt:
            self.launcher.out("swarm watch: stopped")
        return 0


def own_role(t: Trigger) -> str | None:
    """The role whose live sessions hold t: only its own for a [call-in] (#520), [daily]
    (#588) or [ask] (#590), else any."""
    return t.role if t.kind in (CALL_IN, DAILY, ASK) else None


def roles_in(root: Path) -> set[str]:
    """The roles with a prompt in root/roles/."""
    return {p.stem for p in (root / "roles").glob("*.md")}
