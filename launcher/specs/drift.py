"""`swarm specs diff [<goal>]` and the lead's drift decisions (#956; per #942's ruling, #937 §5.3).

diff() finds specs edited after their snapshot was pulled. It reads each sub-issue of a linked
Goal that holds a snapshot block (#953), open or closed, and compares the snapshot with the
live spec. decide() records the lead's choice on one changed feature: adopt, defer or ask.

**Cheap first** (§5.3). A feature whose `last_edited` is not after the snapshot's `pulled`
time is unchanged, and its spec is never read. Otherwise the spec is read and its
`content_hash()` compared with the snapshot's, so a touch that changed nothing is unchanged.

**The latest snapshot counts.** A feature can have several issues under the Goal: the one
pull opened, and any that adopt (on a closed issue) or defer opened later. Only the snapshot
pulled last is compared, so a decision that opened a fresh snapshot settles the drift and a
rerun of the same decision finds nothing to do.

**Decisions** (each appends a `decision` event, #954):

- **adopt** on an open issue: its snapshot is replaced with the live spec, and the issue and
  every open PR that closes it get a comment saying what changed.
- **adopt** on a closed issue: a new sub-issue under the Goal carries the new snapshot.
  Drift after merge never reopens work.
- **defer:** a follow-up sub-issue under the Goal carries the new snapshot and waits on the
  original issue (a `**Waits on:**` line and a blocked-by link).
- **ask:** nothing is written on GitHub; the one-line ask is printed for the lead's report.

The bridge never writes a spec body, and none of these write to the source at all. Like
pull, it talks to the source only through `SpecSource` and to GitHub only through the
`GitHub` protocol below. Standard library only, and no model calls (#937 §7).
"""
from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional, Protocol

from . import events, snapshot, sync
from .source import SPEC_HEADINGS, Feature, Spec, SpecSource

MAX_DIFF_LINES = 15
CHOICES = ("adopt", "defer", "ask")


class GitHub(sync.GitHub, Protocol):
    """The GitHub reads and writes diff and decide make, on top of pull's. swarm.py's
    GhSpecs is the real one."""

    def open_goals(self, repo: str, owner: str) -> list[int]:
        """The numbers of repo's open issues of type Goal that `owner` opened."""
        ...

    def sub_issues_rest(self, repo: str, n: int) -> list[dict]:
        """repo#n's sub-issues as REST gives them: `id`, `number`, `state`, `body`, `html_url`."""
        ...

    def edit_body(self, repo: str, n: int, body: str) -> None:
        ...

    def comment(self, repo: str, n: int, body: str) -> None:
        ...

    def open_prs_closing(self, repo: str, n: int) -> list[tuple[str, int]]:
        """(owner/name, number) of each open PR that closes repo#n."""
        ...

    def add_blocked_by(self, repo: str, n: int, blocking_id: int) -> None:
        """Mark repo#n blocked by the issue with REST id `blocking_id`."""
        ...


@dataclass
class Check:
    """One feature's latest snapshot under the Goal, checked against the live spec."""

    feature_id: str
    issue: dict                          # the sub-issue, as `sub_issues_rest` gives it
    repo: str                            # the sub-issue's owner/name
    snap: snapshot.Snapshot
    feature: Optional[Feature] = None    # None when the source no longer has it
    spec: Optional[Spec] = None          # read only when last_edited is after the snapshot
    changed: bool = False
    sections: list = field(default_factory=list)    # headings that differ
    diff: list = field(default_factory=list)        # short unified diff lines
    note: str = ""                       # why it wasn't compared, if it wasn't

    @property
    def number(self) -> int:
        return self.issue["number"]

    @property
    def state(self) -> str:
        return "open" if (self.issue.get("state") or "").lower() == "open" else "closed"

    @property
    def ref(self) -> str:
        return sync.goal_ref(self.repo, self.number)


@dataclass
class GoalDrift:
    ref: str
    backend: str
    initiative: str
    checks: list = field(default_factory=list)      # Check, one per feature
    problems: list = field(default_factory=list)    # sub-issues whose block didn't parse

    @property
    def changes(self) -> list:
        return [c for c in self.checks if c.changed]


class Undecidable(Exception):
    """decide won't act on this feature; the message says why. Nothing was written."""


def _ts(value: str) -> datetime:
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _repo_of(issue: dict, default: str) -> str:
    """owner/name from the issue's html_url (a sub-issue may sit in another org repo)."""
    url = issue.get("html_url") or ""
    parts = url.split("github.com/", 1)[-1].split("/")
    return f"{parts[0]}/{parts[1]}" if "github.com/" in url and len(parts) >= 4 else default


def _sections_text(sections: dict) -> list[str]:
    out = []
    for h in tuple(SPEC_HEADINGS):
        out.append(f"## {h}")
        if sections.get(h):
            out.extend(sections[h].split("\n"))
    return out


def _live_sections(f: Feature, spec: Spec, source_name: str, when: datetime) -> dict:
    """The live spec's sections exactly as a snapshot would hold them."""
    return snapshot.parse(snapshot.render(f, spec, source_name, when)).sections


def _short_diff(old: dict, new: dict) -> list[str]:
    lines = [ln for ln in difflib.unified_diff(_sections_text(old), _sections_text(new),
                                                "snapshot", "live", n=0, lineterm="")
             if not ln.startswith(("---", "+++"))]
    if len(lines) > MAX_DIFF_LINES:
        more = len(lines) - (MAX_DIFF_LINES - 1)
        lines = lines[:MAX_DIFF_LINES - 1] + [f"… {more} more line{'s' * (more != 1)}"]
    return lines


def _link(gh: GitHub, goal: tuple[str, int], owner: str, backend: str) -> tuple[str, str]:
    """(initiative, Goal body) for a linked Goal, or sync.Refused."""
    ref = sync.goal_ref(*goal)
    body = sync.check_goal(gh.goal(*goal), ref, owner)
    scheme, initiative = sync.parse_link(body, ref)
    if scheme != backend:
        raise sync.Refused(f"{ref} links a {scheme}:// source, but [specs] backend is {backend!r}")
    return initiative, body


def check(goal: tuple[str, int], source: SpecSource, gh: GitHub, *, owner: str,
          backend: Optional[str] = None, now: Optional[datetime] = None) -> GoalDrift:
    """Every feature's latest snapshot under the Goal, against the live spec. Writes nothing.
    Raises sync.Refused, or the source's SchemaError."""
    backend = backend or source.name
    when = now or datetime.now(timezone.utc)
    ref = sync.goal_ref(*goal)
    initiative, _ = _link(gh, goal, owner, backend)
    try:
        features = {f.id: f for f in source.list_features(initiative)}
    except KeyError:
        raise sync.Refused(f"the {backend} source has no initiative {initiative!r}") from None
    out = GoalDrift(ref, backend, initiative)

    latest: dict[str, Check] = {}
    for issue in gh.sub_issues_rest(*goal):
        repo = _repo_of(issue, goal[0])
        try:
            snap = snapshot.parse(issue.get("body") or "")
        except snapshot.SnapshotError as e:
            out.problems.append(f"{sync.goal_ref(repo, issue['number'])}: {e}")
            continue
        if snap is None:
            continue
        c = Check(snap.feature_id, issue, repo, snap)
        prev = latest.get(snap.feature_id)
        if prev is None or (snap.pulled, c.number) > (prev.snap.pulled, prev.number):
            latest[snap.feature_id] = c

    for fid in sorted(latest, key=lambda x: (len(x), x)):          # FEAT-2 before FEAT-10
        c = latest[fid]
        out.checks.append(c)
        if c.snap.source != source.name:
            c.note = f"snapshot is from {c.snap.source}, not {source.name}"
            continue
        c.feature = features.get(fid)
        if c.feature is None:
            c.note = f"{fid} is no longer in {backend}://{initiative}"
            continue
        edited = c.feature.last_edited
        if edited and _ts(edited) <= c.snap.pulled:
            continue                                     # untouched: no spec read (§5.3)
        c.spec = source.get_spec(fid)
        if c.spec.content_hash() == c.snap.hash:
            continue                                     # touched, but the same content
        c.changed = True
        new = _live_sections(c.feature, c.spec, source.name, when)
        c.sections = [h for h in tuple(SPEC_HEADINGS) if c.snap.sections.get(h) != new.get(h)]
        c.diff = _short_diff(c.snap.sections, new)
    return out


def report_line(c: Check, goal_ref: str) -> str:
    """The `Spec changed: …` line for the daily report's Risks section."""
    return (f"Spec changed: {c.feature_id} {c.feature.name} ({c.ref}, {c.state}) since its "
            f"snapshot of {c.snap.pulled.strftime('%Y-%m-%d')}: {', '.join(c.sections)}. "
            f"Lead decides: swarm specs diff {goal_ref} --adopt | --defer | --ask {c.feature_id}")


def ask_line(c: Check) -> str:
    """The one-line ask for the lead's report."""
    then = ("adopt it into the open issue, or defer it to a follow-up after it closes"
            if c.state == "open" else "adopt it as a new issue, or defer it")
    return (f"{c.feature_id} {c.feature.name}: the spec changed after {c.ref} was pulled "
            f"({', '.join(c.sections)}). Should we {then}?")


def _as_json(d: GoalDrift) -> dict:
    return {
        "goal": d.ref, "source": f"{d.backend}://{d.initiative}",
        "changes": [{"feature": c.feature_id, "name": c.feature.name, "issue": c.ref,
                     "url": c.issue.get("html_url"), "state": c.state,
                     "snapshot_hash": c.snap.hash, "live_hash": c.spec.content_hash(),
                     "sections": c.sections, "diff": c.diff, "report": report_line(c, d.ref)}
                    for c in d.changes],
        "unchanged": [c.feature_id for c in d.checks if not c.changed and not c.note],
        "skipped": [{"feature": c.feature_id, "issue": c.ref, "why": c.note}
                    for c in d.checks if c.note],
        "problems": d.problems,
    }


def diff(goal: Optional[tuple[str, int]], source: SpecSource, gh: GitHub, *, owner: str,
         repo: Optional[str] = None, backend: Optional[str] = None, as_json: bool = False,
         now: Optional[datetime] = None, out: Callable[[str], None] = print) -> list[GoalDrift]:
    """Print the drift under `goal` ((owner/name, N)), or with None under every open Goal in
    `repo` the owner opened that has a `Spec source:` line. Writes nothing.

    With one Goal, raises sync.Refused or the source's SchemaError. With every Goal, a Goal
    that won't check is listed with why, and the rest are still checked."""
    backend = backend or source.name
    results: list[GoalDrift] = []
    skipped: list[str] = []
    if goal is not None:
        results.append(check(goal, source, gh, owner=owner, backend=backend, now=now))
    else:
        for n in gh.open_goals(repo, owner):
            g = (repo, n)
            node = gh.goal(*g)
            body = (node or {}).get("body") or ""
            if not sync.SPEC_SOURCE_RE.search(body):
                continue
            try:
                results.append(check(g, source, gh, owner=owner, backend=backend, now=now))
            except sync.Refused as e:
                skipped.append(f"{sync.goal_ref(*g)}: {e}")

    if as_json:
        out(json.dumps({"goals": [_as_json(d) for d in results], "skipped": skipped}, indent=2,
                       ensure_ascii=False))
        return results
    if goal is None and not results and not skipped:
        out(f"swarm specs diff: no open Goal in {repo} has a Spec source line")
    for d in results:
        simulated = ", simulated" if getattr(source, "simulated", False) else ""
        unchanged = sum(1 for c in d.checks if not c.changed and not c.note)
        out(f"swarm specs diff: Goal {d.ref}, {d.backend}://{d.initiative}{simulated}: "
            f"{len(d.changes)} changed, {unchanged} unchanged")
        for c in d.changes:
            out(f"  {c.feature_id} {c.feature.name}: {c.ref} ({c.state}) changed in "
                f"{', '.join(c.sections)}")
            out("\n".join("      " + ln for ln in c.diff))
            out(f"    {report_line(c, d.ref)}")
        for c in d.checks:
            if c.note:
                out(f"  {c.feature_id}: {c.ref} not checked ({c.note})")
        for p in d.problems:
            out(f"  {p}: not checked")
    for s in skipped:
        out(f"swarm specs diff: skipped {s}")
    return results


# --- decisions -----------------------------------------------------------------------------

def _what_changed(c: Check, new_hash: str) -> str:
    return "\n".join([
        f"The spec for {c.feature_id} changed after this issue's snapshot was pulled, and the "
        f"lead adopted the change: the snapshot above now holds the live spec "
        f"(`{c.snap.hash[:12]}` → `{new_hash[:12]}`).",
        "",
        f"Changed: {', '.join(c.sections)}.",
        "",
        "```diff",
        *c.diff,
        "```",
    ])


def _new_issue_body(block: str, goal_ref: str, waits_on: Optional[str] = None) -> str:
    body = sync.issue_body(block, goal_ref)
    return body + (f"**Waits on:** {waits_on}\n" if waits_on else "")


def decide(goal: tuple[str, int], feature_id: str, choice: str, source: SpecSource,
           gh: GitHub, *, owner: str, backend: Optional[str] = None,
           now: Optional[datetime] = None, out: Callable[[str], None] = print) -> dict:
    """Act on the lead's choice for one changed feature under the Goal and append the
    `decision` event, which it returns. Raises Undecidable when the feature hasn't changed
    (or has no snapshot under the Goal), and sync.Refused as check does; both before any
    write. A GitHub error after the first write propagates; what was written stays written."""
    if choice not in CHOICES:
        raise ValueError(f"unknown choice {choice!r}; choose from {', '.join(CHOICES)}")
    when = now or datetime.now(timezone.utc)
    d = check(goal, source, gh, owner=owner, backend=backend, now=when)
    c = next((x for x in d.checks if x.feature_id == feature_id), None)
    if c is None:
        raise Undecidable(f"no sub-issue of {d.ref} holds a snapshot of {feature_id}")
    if c.note:
        raise Undecidable(f"{feature_id} can't be compared: {c.note}")
    if not c.changed:
        raise Undecidable(f"{feature_id}'s spec hasn't changed since {c.ref}'s snapshot")

    new_hash = c.spec.content_hash()
    if choice == "ask":
        line = ask_line(c)
        out(line)
        return events.append("decision", d.ref, feature_id, choice="ask", where="report",
                             issue_url=c.issue.get("html_url"), hash=new_hash, ask=line)

    block = snapshot.render(c.feature, c.spec, source.name, when)
    if choice == "adopt" and c.state == "open":
        gh.edit_body(c.repo, c.number, snapshot.replace(c.issue.get("body") or "", block))
        note = _what_changed(c, new_hash)
        gh.comment(c.repo, c.number, note)
        prs = gh.open_prs_closing(c.repo, c.number)
        for pr_repo, pr in prs:
            gh.comment(pr_repo, pr, note)
        where = c.issue.get("html_url")
        out(f"swarm specs diff: adopted {feature_id} into {c.ref}: snapshot replaced, "
            f"commented on the issue" + (f" and {len(prs)} open PR{'s' * (len(prs) != 1)}"
                                         if prs else ""))
        return events.append("decision", d.ref, feature_id, choice="adopt", where=where,
                             issue_url=where, hash=new_hash,
                             prs=[sync.goal_ref(r, n) for r, n in prs])

    if choice == "adopt":                                # on a closed issue: a new sub-issue
        title = f"{c.feature.name}: spec change after #{c.number}"
        body = _new_issue_body(block, d.ref)
    else:                                                # defer: a follow-up that waits
        title = f"{c.feature.name}: follow-up for the spec change"
        body = _new_issue_body(block, d.ref, waits_on=f"#{c.number}")
    issue = gh.open_issue(c.repo, title, body)
    url = issue["html_url"]
    gh.add_sub_issue(goal[0], goal[1], issue["id"])
    if choice == "defer":
        gh.add_blocked_by(c.repo, issue["number"], c.issue["id"])
    out(f"swarm specs diff: {'adopted' if choice == 'adopt' else 'deferred'} {feature_id} "
        f"({c.ref} is {c.state}): opened {url}")
    return events.append("decision", d.ref, feature_id, choice=choice, where=url,
                         issue_url=c.issue.get("html_url"), hash=new_hash)
