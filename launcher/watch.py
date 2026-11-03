"""swarm watch: the v2 wake-up loop (GOV-0009). W1 (#89) is --dry-run; W2 (#90) starts;
#113 adds GOV-0011's [respond] trigger.

    launcher/swarm watch                          start sessions, within swarm.toml's [watch]
    launcher/swarm watch --dry-run [--interval MINUTES]   print what it would start

Every interval it reads the same GitHub and heartbeat state as `swarm inbox` and works
out each trigger below. --dry-run prints them and starts nothing.

| kind   | trigger                                                                 | would start          |
|--------|-------------------------------------------------------------------------|----------------------|
| review | open, non-draft PR whose head the reviewer App hasn't reviewed          | a reviewer pass      |
| build  | issue whose most recent `ready` was added by the owner (GOV-0006),      | builder on the issue |
|        | with no open PR closing it                                              |                      |
| record | gov:question whose most recent `gov:ruled` was added by the owner, that | docs on the question |
|        | needs a record (GOV-0007), with no open PR closing it                   |                      |
| answer | gov:question whose most recent `ready` was added by the owner           | its "Raised by" role |
| respond| open, non-draft PR whose latest reviewer review at its head is          | builder on the PR    |
|        | CHANGES_REQUESTED, with Authority not `fail`, for at most 2 rounds      | (GOV-0011)           |

[respond] counts the reviewer's CHANGES_REQUESTED reviews on the PR from GitHub's review
history, so the count holds across restarts. A third request starts nothing, and an
Authority: fail review at the head starts nothing either: `needs_you()` lists both PRs
as needing the owner. A PR that doesn't close exactly one issue is skipped with a reason.

An issue or question with a live session on it prints nothing (`swarm launch`'s refusal
rule), so it can fire later, once that session has stopped. Each trigger has an identity,
which is the PR head SHA (for [review] and [respond]) or the id of the owner's label event. A trigger prints once per
identity, so a new push or a fresh owner label is a new trigger. In dry-run the memory
lives only in the process, and nothing is written to disk.

A review trigger is also quiet while any reviewer session is live: that pass may have
listed the PRs before this push, so the trigger waits for it to stop rather than being
covered by it.

Without --dry-run, each new trigger starts one fresh session (one Terminal window, as
`swarm launch` does), within the limits in GOV-0010 (the owner's answer on #88):

- at most [watch] max_live live sessions that the loop started; past that, a trigger is
  held, listed in `swarm inbox`, and started in order once a slot frees up;
- only roles that set spend_cap_usd in swarm.toml; any other trigger is skipped and
  listed in `swarm inbox`, and starts once the role has a cap;
- every [watch] interval_minutes. swarm.toml is read again on every check.

Before each start it runs `swarm launch`'s refusal checks again on fresh GitHub data. A
refusal is logged and the trigger is done. What it has acted on is kept in
~/.productswarm/launcher/watch.json, so a restart starts nothing twice. One reviewer
pass covers every review trigger present when it starts.

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

    Oversteps and a third request are the owner's: needs_you() lists those PRs instead."""
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


def reviewers(model: dict, started: list) -> list[str]:
    """Live reviewer sessions: on the heartbeat and not stopped, or started by the launcher
    and not yet heard from."""
    seen = {s["session_id"] for s in model["sessions"]}
    out = [f"reviewer ({s['status']}, session {s['session_id']})"
           for s in model["sessions"] if s["role"] == "reviewer" and s["status"] != "stopped"]
    out += [f"{e.name} (starting, session {e.session_id})"
            for e in started if e.role == "reviewer" and e.session_id not in seen]
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
        w.reviewed[n] = {r.get("commit_id") for r in reviews
                         if (r.get("user") or {}).get("login") == REVIEWER}
    return w


# ---------------------------------------------------------------- local state

def state_path(launcher: "swarm.Launcher") -> Path:
    return launcher.dir / STATE_FILE


def load_state(launcher: "swarm.Launcher") -> dict:
    """{"checked": ISO time, "acted": {key: outcome}, "waiting": [trigger dicts]}."""
    try:
        data = json.loads(state_path(launcher).read_text())
    except FileNotFoundError:
        return {"checked": None, "acted": {}, "waiting": []}
    except ValueError as e:
        raise RuntimeError(f"{state_path(launcher)} is not valid JSON: {e}") from None
    return {"checked": data.get("checked"), "acted": dict(data.get("acted") or {}),
            "waiting": list(data.get("waiting") or [])}


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


def iso(t: dt.datetime) -> str:
    return t.isoformat()


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
        return new

    def start_tick(self, now: dt.datetime) -> list[Trigger]:
        """Start a session for each new trigger, within the [watch] limits (GOV-0010)."""
        g, out = swarm.dashboard(), self.launcher.out
        try:
            sessions, limits = manifest.load_all(self.manifest_path)
        except manifest.ManifestError as e:
            raise RuntimeError(str(e)) from None
        if limits is None:
            raise RuntimeError(f"{self.manifest_path} has no [watch] table; starting nothing (GOV-0010)")
        by_role = {s.role: s for s in sessions}
        w = self.read(self.repo, self.idle_minutes, now)
        live = self.launcher.live()
        st = load_state(self.launcher)
        acted, before = st["acted"], {x["key"]: x for x in st["waiting"]}
        todo = [t for t in triggers(w, self.owner, live, self.roles, g.needs_you, g.is_tracking)
                if t.key not in acted]
        todo.sort(key=lambda t: before.get(t.key, {}).get("since", iso(now)))  # held longest first
        held, done, reviewer = [], [], None

        def finish(t: Trigger, outcome: str) -> None:
            acted[t.key] = outcome
            done.append(t)
            save_state(self.launcher, {"checked": iso(now), "acted": acted, "waiting": st["waiting"]})

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
            entry = swarm.Started(name=self.name(t, live), role=t.role, model=s.model,
                                  session_id=str(uuid.uuid4()), started=self.launcher.clock(),
                                  issue=t.issue, pr=t.pr, by="watch")
            out(f"[{t.kind}] {t.ref} {t.why} -> starting {entry.name}")
            if self.launcher.start(entry, live):
                if t.kind == "review":
                    reviewer = entry.name
                finish(t, f"started {entry.name}")
            else:
                hold(t, "failed to start (see above); trying again next check")
        save_state(self.launcher, {"checked": iso(now), "acted": acted, "waiting": held})
        return done

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
