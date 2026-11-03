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
| answer | gov:question whose most recent `ready` was added by the owner           | its "Raised by" role |
| respond| open, non-draft PR the builder App opened, whose latest reviewer review | builder on the PR    |
|        | at its head is CHANGES_REQUESTED, with Authority not `fail`, for at     | (GOV-0011)           |
|        | most 2 rounds                                                           |                      |

[respond] counts the reviewer's CHANGES_REQUESTED reviews on the PR from GitHub's review
history, so the count holds across restarts. A third request starts nothing, and an
Authority: fail review at the head starts nothing either, and nor do requested changes
on a PR another App opened, such as a docs ruling PR (#178): the builder responds only on
its own PR (GOV-0011). `needs_you()` lists all three as needing the owner. A PR that doesn't close exactly one issue is skipped with a reason.

An issue or question with a live session on it prints nothing (`swarm launch`'s refusal
rule), so it can fire later, once that session has stopped. Each trigger has an identity,
which is the PR head SHA (for [review] and [respond]) or the id of the owner's label event. A trigger prints once per
identity, so a new push or a fresh owner label is a new trigger. In dry-run the memory
lives only in the process, and nothing is written to disk.

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

Before each start it runs `swarm launch`'s refusal checks again on fresh GitHub data. A
refusal is logged and the trigger is done. What it has acted on is kept in
~/.productswarm/launcher/watch.json, so a restart starts nothing twice. One reviewer
pass covers every review trigger present when it starts.

How each run ended (#149): when a run the loop started is no longer live, the loop reads
its result file and records, against the trigger in watch.json's "runs", the session id,
Claude Code's total_cost_usd (a client-side estimate that stays local: GOV-0002/3/4) and
its ending: done, ended at cap (--max-budget-usd or --max-turns), error, or no result (no
file or no JSON result, for example after `swarm stop`). The trigger stays done, so the
loop never restarts it by itself; `swarm inbox` lists a run that ended at cap, with its
ref and cost, so the owner can decide whether to restart it, and lists every recorded
cost from the last RUNS_DAYS days. A kept worktree is tidy()'s job, as for any session.

Each run it starts gets a Stop hook (stophook.py, #148) that keeps it going until its
role's done-condition is met; see that module for the conditions and the guards.

`swarm cost` (#176, cost_text()) prints those recorded costs grouped by the PR each run
served, with a read-only `gh pr list` to find the PR that closes a run's issue. It only
prints: no cost goes to GitHub or the repo.

It never stops a session (GOV-0008), never adds or removes labels, and never comments,
approves or merges: its only GitHub calls are reads. Sessions it starts are recorded
with by="watch", and `swarm ls` shows them as "by watch".

GitHub reads go through gather(); triggers() is pure, so tests feed it canned data.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import manifest
import swarm

REVIEWER = swarm.dashboard().REVIEWER
DEFAULT_INTERVAL = 5          # minutes, for --dry-run when swarm.toml has no [watch] table
STATE_FILE = "watch.json"     # in the launcher's state directory
REF_RE = re.compile(r"#(\d+)")
GOV_RE = re.compile(r"\bGOV-\d{4}\b")
RUNS_DAYS = 7                 # how long `swarm inbox` lists a recorded run, and watch.json keeps it

# How a headless run ended, from the `subtype` of its --output-format json result: the
# SDKResultMessage type in the Claude Code Agent SDK reference (#149). Any other subtype,
# or "success" with is_error set, is an error.
DONE, AT_CAP, ERROR, NO_RESULT = "done", "ended at cap", "error", "no result"
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

    def line(self) -> str:
        if self.skipped:
            return f"[{self.kind}] {self.ref} {self.why} -> skipped: {self.skipped}"
        return f"[{self.kind}] {self.ref} {self.why} -> would start {self.command}"


def launch_cmd(role: str, n: int, pr: int | None = None) -> str:
    return f"`launcher/swarm launch {role} --issue {n}" + (f" --pr {pr}`" if pr else "`")


# ---------------------------------------------------------------- the template body

def template_field(body: str | None, label: str) -> str | None:
    """The first line of a Governance question template answer, e.g. "Raised by"."""
    m = re.search(rf"^###\s*{re.escape(label)}\s*\n+\s*(\S[^\n]*?)\s*$", body or "", re.M)
    return m.group(1) if m and m.group(1) != "_No response_" else None


def needs_record(body: str | None) -> str | None:
    """Why a question needs a record under GOV-0007, as far as its body can say, else None.

    GOV-0007's other case, "the owner says so in the answer", is a comment that the loop
    can't read reliably, so those questions don't trigger here."""
    domain = (template_field(body, "Domain") or "").strip().lower()
    rev = (template_field(body, "Reversibility") or "").strip().lower()
    blast = (template_field(body, "Blast radius") or "").strip().lower()
    if domain == "governance":
        return "domain governance"
    if rev == "one-way":
        return "one-way"
    if blast == "external":
        return "blast radius external"
    return None


def raised_by(body: str | None, roles: set[str]) -> tuple[str | None, str]:
    """(role, "") from the "Raised by" field, or (None, why not)."""
    text = template_field(body, "Raised by")
    if not text:
        return None, 'it has no "Raised by" field'
    found = {w for w in re.findall(r"[a-z][a-z0-9-]*", text.lower()) if w in roles}
    if len(found) == 1:
        return found.pop(), ""
    if not found:
        return None, f'"Raised by" names no known role ({text!r})'
    return None, f'"Raised by" names more than one role ({", ".join(sorted(found))})'


# ---------------------------------------------------------------- triggers (pure)

@dataclass
class World:
    """One tick's reading of GitHub and the heartbeat. Plain data, so tests can build it."""
    model: dict                                      # generate.build() output
    issues: list[dict]                               # raw issues (generate.fetch)
    events: dict[int, list[dict]] = field(default_factory=dict)     # issue -> events, oldest first
    reviewed: dict[int, set[str]] = field(default_factory=dict)     # PR -> SHAs the reviewer reviewed


def owner_label(events: list[dict], name: str, owner: str) -> dict | None:
    """The owner's label event for `name`, if the most recent one is the owner's (GOV-0006)."""
    e = swarm.label_event(events, name)
    return e if e and (e.get("actor") or {}).get("login") == owner else None


def triggers(w: World, owner: str, started: list, roles: set[str], needs_you: Callable,
             is_tracking: Callable) -> list[Trigger]:
    """Every trigger present now, in needs-you order then issue order. Nothing is filtered
    for novelty here; Watch does that."""
    m, out = w.model, []
    items = needs_you(m)
    heads = {p["number"]: p.get("head") for p in m["prs"]}
    closing = {c["number"] for p in m["prs"] for c in p["closes"]}

    def busy(n: int) -> bool:
        return bool(swarm.holders(n, m, started))

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
                               command="a reviewer pass"))
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
        why_record = needs_record(body)
        if ruled and why_record and n not in closing and not busy(n):
            out.append(Trigger(key=f"record:{n}:{ruled.get('id')}", kind="record", ref=f"#{n}",
                               why=f"gov:ruled by the owner, needs a record ({why_record})",
                               role="docs", command=launch_cmd("docs", n), issue=n))
        ready = owner_label(events, "ready", owner) if "ready" in labels else None
        if ready and not busy(n):
            role, why_not = raised_by(body, roles)
            out.append(Trigger(key=f"answer:{n}:{ready.get('id')}", kind="answer", ref=f"#{n}",
                               why="ready by the owner", role=role,
                               command=launch_cmd(role, n) if role else None,
                               skipped=None if role else why_not, issue=n))

    # Builds: ready, open, non-question, non-tracking issues with no open PR closing them
    # (that work is done and waits on the owner's merge).
    for it in sorted(w.issues, key=lambda i: i["number"]):
        n = it["number"]
        labels = {lb.get("name") for lb in it.get("labels") or []}
        if (it.get("state") != "open" or "pull_request" in it or "ready" not in labels
                or "gov:question" in labels or is_tracking(it) or n in closing):
            continue
        ready = owner_label(w.events.get(n, []), "ready", owner)
        if ready and not busy(n):
            out.append(Trigger(key=f"build:{n}:{ready.get('id')}", kind="build", ref=f"#{n}",
                               why="ready by the owner", role="builder",
                               command=launch_cmd("builder", n), issue=n))
    return out


def respond(p: dict, busy: Callable[[int], bool]) -> Trigger | None:
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
    if busy(closes[0]):
        return None
    return Trigger(key=key, kind="respond", ref=f"PR #{n}", why=why, role="builder",
                   command=launch_cmd("builder", closes[0], n), issue=closes[0], pr=n)


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
    for n, reviews in (data.get("reviews") or {}).items():    # fetch() read them for build()
        w.reviewed[n] = reviewed_heads(reviews)
    return w


def reviewed_heads(reviews: list[dict]) -> set[str]:
    """The commit SHAs the reviewer App has reviewed on one PR, from its REST reviews. A
    head in this set is "already reviewed": the [review] trigger and the Actions check
    (actions_review.py, #214) both use this rule, so they agree."""
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
    if sub in CAPS:
        return {**rec, "ending": AT_CAP, "detail": CAPS[sub]}
    if sub == "success" and not result.get("is_error"):
        return {**rec, "ending": DONE, "detail": ""}
    errors = result.get("errors")
    detail = "; ".join(str(e) for e in errors) if isinstance(errors, list) and errors else ""
    return {**rec, "ending": ERROR, "detail": (detail or f"subtype {sub}")[:200]}


def usd(x: float | None) -> str:
    return "-" if x is None else f"${x:,.2f}"


def run_line(r: dict) -> str:
    """One recorded run, for the loop's log and `swarm inbox`."""
    ending = r["ending"] + (f" ({r['detail']})" if r.get("detail") else "")
    return f"[{r['kind']}] {r['ref']} {r['name']} · {ending} · {usd(r.get('cost_usd'))} (est.)"


def save_state(launcher: "swarm.Launcher", st: dict) -> None:
    launcher.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = state_path(launcher)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=1) + "\n")
    tmp.replace(path)


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

    def tick(self, now: dt.datetime | None = None) -> list[Trigger]:
        """One check. Returns the triggers it acted on or printed for the first time."""
        now = now or dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        return self.dry_tick(now) if self.dry_run else self.start_tick(now)

    def dry_tick(self, now: dt.datetime) -> list[Trigger]:
        """Print and return the triggers not seen before. Starts nothing, writes nothing."""
        g = swarm.dashboard()
        w = self.read(self.repo, self.idle_minutes, now)
        new = [t for t in triggers(w, self.owner, self.launcher.running(), self.roles,
                                   g.needs_you, g.is_tracking)
               if t.key not in self.seen]
        for t in new:
            self.seen.add(t.key)
            self.launcher.out(t.line())
            if not t.skipped:
                self.launcher.out(f"  {self.headless(t)}")
        return new

    def headless(self, t: Trigger) -> str:
        """For --dry-run: the full command a real start would run for t (#147), or why
        there isn't one. Reads swarm.toml as a real start would; never raises."""
        try:
            sessions, limits = manifest.load_all(self.manifest_path)
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
        try:
            sessions, limits = manifest.load_all(self.manifest_path)
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
        runs = self.record_ended(st["runs"], live, now)
        todo = [t for t in triggers(w, self.owner, live, self.roles, g.needs_you, g.is_tracking)
                if t.key not in acted]
        todo.sort(key=lambda t: before.get(t.key, {}).get("since", iso(now)))  # held longest first
        held, done, reviewer = [], [], None

        def finish(t: Trigger, outcome: str) -> None:
            acted[t.key] = outcome
            done.append(t)
            save_state(self.launcher, {"checked": iso(now), "acted": acted, "waiting": st["waiting"],
                                       "runs": runs})

        def hold(t: Trigger, reason: str) -> None:
            since = before.get(t.key, {}).get("since", iso(now))
            held.append({"key": t.key, "kind": t.kind, "ref": t.ref, "why": t.why,
                         "reason": reason, "since": since})
            if before.get(t.key, {}).get("reason") != reason:     # log each reason once
                out(f"[{t.kind}] {t.ref} {t.why} -> {reason}")

        for t in todo:
            if t.skipped:
                out(t.line())
                finish(t, f"skipped: {t.skipped}")
                continue
            if t.kind == "review" and reviewer:
                out(f"[review] {t.ref} {t.why} -> covered by {reviewer}")
                finish(t, f"covered by {reviewer}")
                continue
            if t.issue is not None and swarm.holders(t.issue, w.model, live):
                continue      # a session started this check is on it; it fires again once that stops
            s = by_role.get(t.role)
            mine = sum(e.by == "watch" for e in live)
            if s is None:
                hold(t, f"skipped: {t.role} isn't in swarm.toml")
                continue
            if s.spend_cap_usd is None:
                hold(t, f"skipped: {t.role} has no spend_cap_usd in swarm.toml, and swarm watch "
                        f"starts only capped roles (GOV-0010)")
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

    def record_ended(self, runs: dict, live: list, now: dt.datetime) -> dict:
        """Record how each run this loop started ended, once it is no longer live (#149):
        read its result file and log one line. Records older than RUNS_DAYS are dropped.
        Its trigger stays done in "acted", so the loop never starts it again by itself."""
        alive = {e.session_id for e in live}
        since = iso(now - dt.timedelta(days=RUNS_DAYS))
        kept = {}
        for key, r in runs.items():
            if r.get("ended") and r["ended"] < since:
                continue
            if not r.get("ending") and r["session_id"] not in alive:
                r = {**r, **read_result(self.launcher.result_file(r["session_id"])), "ended": iso(now)}
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
        else:
            self.launcher.out(f"swarm watch: checking every {interval_minutes:g} min; starts sessions "
                              f"within swarm.toml's [watch] limits and only for roles with a "
                              f"spend_cap_usd (GOV-0010); never stops one; Ctrl-C to stop")
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
    return {p.stem for p in (root / "roles").glob("*.md")}
