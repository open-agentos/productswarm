"""swarm watch: the v2 wake-up loop (#87, option 1). This is W1 (#89): dry-run only.

    launcher/swarm watch --dry-run [--interval MINUTES]

Every interval it reads the same GitHub and heartbeat state as `swarm inbox` and prints
each new trigger with what it would start. It starts nothing: real starts wait on the
spend limits in #88 (W2, #90).

| kind   | trigger                                                                 | would start          |
|--------|-------------------------------------------------------------------------|----------------------|
| review | open, non-draft PR whose head the reviewer App hasn't reviewed          | a reviewer pass      |
| build  | issue whose most recent `ready` was added by the owner (GOV-0006)       | builder on the issue |
| record | gov:question whose most recent `gov:ruled` was added by the owner, that | docs on the question |
|        | needs a record (GOV-0007), with no open PR closing it                   |                      |
| answer | gov:question whose most recent `ready` was added by the owner           | its "Raised by" role |

An issue or question with a live session on it prints nothing (`swarm launch`'s refusal
rule), so it can fire later, once that session has stopped. Each trigger has an identity,
which is the PR head SHA or the id of the owner's label event. A trigger prints once per
identity, so a new push or a fresh owner label is a new trigger. In dry-run the memory
lives only in the process, and nothing is written to disk.

GitHub reads go through gather(); triggers() is pure, so tests feed it canned data.
"""
from __future__ import annotations

import datetime as dt
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import swarm

REVIEWER = "productswarm-reviewer[bot]"
DEFAULT_INTERVAL = 5          # minutes, until #88 sets one
REF_RE = re.compile(r"#(\d+)")


@dataclass(frozen=True)
class Trigger:
    key: str                  # identity: a new key is a new trigger
    kind: str                 # review | build | record | answer
    ref: str                  # "PR #12" or "#49"
    why: str
    role: str | None = None
    command: str | None = None
    skipped: str | None = None

    def line(self) -> str:
        if self.skipped:
            return f"[{self.kind}] {self.ref} {self.why} -> skipped: {self.skipped}"
        return f"[{self.kind}] {self.ref} {self.why} -> would start {self.command}"


def launch_cmd(role: str, n: int) -> str:
    return f"`launcher/swarm launch {role} --issue {n}`"


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

    # Reviews: the needs-you PR list is the open non-draft PRs.
    for it in items:
        if it["kind"] != "pr":
            continue
        n = int(REF_RE.search(it["ref"]).group(1))
        head = heads.get(n)
        if not head or head in w.reviewed.get(n, set()):
            continue
        out.append(Trigger(key=f"review:{n}:{head}", kind="review", ref=f"PR #{n}",
                           why=f"head {head[:7]} not reviewed by the reviewer", role="reviewer",
                           command="a reviewer pass (`swarm launch` has no PR form yet; #90)"))

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
                               role="docs", command=launch_cmd("docs", n)))
        ready = owner_label(events, "ready", owner) if "ready" in labels else None
        if ready and not busy(n):
            role, why_not = raised_by(body, roles)
            out.append(Trigger(key=f"answer:{n}:{ready.get('id')}", kind="answer", ref=f"#{n}",
                               why="ready by the owner", role=role,
                               command=launch_cmd(role, n) if role else None,
                               skipped=None if role else why_not))

    # Builds: ready, open, non-question, non-tracking issues.
    for it in sorted(w.issues, key=lambda i: i["number"]):
        n = it["number"]
        labels = {lb.get("name") for lb in it.get("labels") or []}
        if (it.get("state") != "open" or "pull_request" in it or "ready" not in labels
                or "gov:question" in labels or is_tracking(it)):
            continue
        ready = owner_label(w.events.get(n, []), "ready", owner)
        if ready and not busy(n):
            out.append(Trigger(key=f"build:{n}:{ready.get('id')}", kind="build", ref=f"#{n}",
                               why="ready by the owner", role="builder",
                               command=launch_cmd("builder", n)))
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
    for p in model["prs"]:
        if not p["draft"]:
            reviews = g.gh_items(f"repos/{repo}/pulls/{p['number']}/reviews?per_page=100")
            w.reviewed[p["number"]] = {r.get("commit_id") for r in reviews
                                       if (r.get("user") or {}).get("login") == REVIEWER}
    return w


# ---------------------------------------------------------------- the loop

@dataclass
class Watch:
    launcher: "swarm.Launcher"
    repo: str
    owner: str
    roles: set[str]
    idle_minutes: int = 15
    read: Callable[[str, int, dt.datetime], World] = gather
    seen: set[str] = field(default_factory=set)

    def tick(self, now: dt.datetime | None = None) -> list[Trigger]:
        """Print and return the triggers not seen before. Starts nothing, writes nothing."""
        g = swarm.dashboard()
        now = now or dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        w = self.read(self.repo, self.idle_minutes, now)
        new = [t for t in triggers(w, self.owner, self.launcher.running(), self.roles,
                                   g.needs_you, g.is_tracking)
               if t.key not in self.seen]
        for t in new:
            self.seen.add(t.key)
            self.launcher.out(t.line())
        return new

    def run(self, interval_minutes: float, ticks: int | None = None,
            sleep: Callable[[float], None] = time.sleep) -> int:
        self.launcher.out(f"swarm watch --dry-run: checking every {interval_minutes:g} min; "
                          f"starts nothing; Ctrl-C to stop")
        n = 0
        try:
            while ticks is None or n < ticks:
                if n:
                    sleep(interval_minutes * 60)
                try:
                    self.tick()
                except RuntimeError as e:      # GitHub unreachable: try again next tick
                    self.launcher.out(f"swarm watch: {e}; trying again next tick")
                n += 1
        except KeyboardInterrupt:
            self.launcher.out("swarm watch: stopped")
        return 0


def roles_in(root: Path) -> set[str]:
    return {p.stem for p in (root / "roles").glob("*.md")}
