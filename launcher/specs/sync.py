"""`swarm specs pull <goal>` (#955; per #942's ruling, #937 §5.1, §5.2, §6, §8).

pull() turns a linked initiative's Ready features into go sub-issues under the Goal, each
carrying a spec snapshot (#953). It talks to the spec source only through `SpecSource` and
to GitHub only through the small `GitHub` protocol below, so tests run it against the fake
backend and a stub with no network.

**The link** is the Goal's `Spec source: <backend>://<initiative id>` line (§5.1). It counts
only on an open Goal the owner opened whose body no one else has edited (GOV-0031), and only
when its scheme is the configured backend.

**Reads before writes.** Every read (the features, and the spec of each Ready, unlinked one)
and every issue body is done before the first write, so a SchemaError (§13) or a refusal
stops the run having written nothing.

**Publishing** (#943, Part B). Only Ready features are fetched: a Draft or any other status
is never read past its row, and its name never reaches an issue or an output line. An
issue body is the snapshot block plus one line naming the Goal, nothing more.

**Idempotence** (#942). The feature's Issue field is the key, never the event log: a Ready
feature with an issue is reported, not pulled again. The link is written straight after the
issue is opened, before anything else that could fail, so a rerun after a failure part-way
doesn't open a second issue.

Standard library only, and no model calls (#937 §7).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional, Protocol

from . import events, snapshot
from .source import Feature, FeatureStatus, SpecSource

SPEC_SOURCE_RE = re.compile(r"^[ \t]*Spec source:[ \t]*(?P<value>.*?)[ \t]*$", re.M)
LINK_RE = re.compile(r"(?P<scheme>[a-z][a-z0-9]*)://(?P<initiative>\S+)")
REPO_LINE_RE = re.compile(r"^[ \t]*Repo:[ \t]*(?P<value>.*?)[ \t]*$", re.M)
REPO_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", re.ASCII)

# The outcomes of one feature, as each output line names them.
OPENED, LINKED, NOT_PULLABLE, SKIPPED = "opened", "already linked", "not pullable", "skipped"


class Refused(Exception):
    """pull won't run against this Goal; the message says why. Nothing was written."""


class GitHub(Protocol):
    """The GitHub reads and writes pull makes. swarm.py's GhSpecs is the real one."""

    def goal(self, repo: str, n: int) -> Optional[dict]:
        """The issue as GraphQL gives it, or None if there is none: `state`, `body`,
        `author {login __typename}`, `issueType {name}` and `userContentEdits {totalCount
        nodes {editor {login __typename}}}` (the body edit history scope_edits reads)."""
        ...

    def open_issue(self, repo: str, title: str, body: str) -> dict:
        """Open an issue; returns REST's issue, with `id`, `number` and `html_url`."""
        ...

    def add_sub_issue(self, repo: str, n: int, sub_issue_id: int) -> None:
        """Make the issue with REST id `sub_issue_id` a sub-issue of repo#n."""
        ...


@dataclass(frozen=True)
class Result:
    feature_id: str
    outcome: str            # OPENED, LINKED, NOT_PULLABLE or SKIPPED
    line: str               # what pull printed for it


def login(a: Optional[dict]) -> str:
    """REST's login for a GraphQL actor, as swarm.py's scope_edits reads it."""
    return "ghost" if not a else a["login"] + "[bot]" if a.get("__typename") == "Bot" else a["login"]


def goal_ref(repo: str, n: int) -> str:
    return f"{repo}#{n}"


def _one_line(body: str, line_re: re.Pattern, what: str) -> Optional[str]:
    found = [m["value"] for m in line_re.finditer(body)]
    if len(found) > 1:
        raise Refused(f"the Goal has {len(found)} {what} lines; it needs exactly one")
    return found[0] if found else None


def check_goal(node: Optional[dict], ref: str, owner: str) -> str:
    """The Goal's body, or Refused unless it is an open Goal the owner opened whose body
    no one else has edited (GOV-0031, #937 §5.1)."""
    if not node:
        raise Refused(f"{ref} doesn't exist")
    if (node.get("issueType") or {}).get("name") != "Goal":
        raise Refused(f"{ref} isn't a Goal")
    if (node.get("state") or "").upper() != "OPEN":
        raise Refused(f"{ref} isn't open")
    author = login(node.get("author"))
    if author != owner:
        raise Refused(f"{ref} was opened by {author}, not the owner (@{owner})")
    edits = node.get("userContentEdits") or {}
    nodes = edits.get("nodes") or []
    if edits.get("totalCount", 0) > len(nodes):
        raise Refused(f"{ref}'s edit history is too long to read whole; can't tell who edited it")
    others = sorted({login(e.get("editor")) for e in nodes} - {owner})
    if others:
        raise Refused(f"{ref}'s body was edited by {', '.join(others)}, not only the owner "
                      f"(@{owner})")
    return node.get("body") or ""


def parse_link(body: str, ref: str) -> tuple[str, str]:
    """(scheme, initiative id) from the Goal's one `Spec source:` line."""
    value = _one_line(body, SPEC_SOURCE_RE, "Spec source:")
    if value is None:
        raise Refused(f"{ref} has no 'Spec source: <backend>://<initiative id>' line")
    m = LINK_RE.fullmatch(value)
    if not m:
        raise Refused(f"{ref}'s Spec source line isn't <backend>://<initiative id>: {value[:80]!r}")
    return m["scheme"], m["initiative"]


def target_repo(body: str, goal_repo: str) -> str:
    """The Goal's `Repo: owner/name`, or the Goal's own repo without one (#937 §8). A repo
    outside the Goal's owner is refused: the bridge opens issues only in the org."""
    value = _one_line(body, REPO_LINE_RE, "Repo:")
    if value is None:
        return goal_repo
    if not REPO_RE.fullmatch(value):
        raise Refused(f"the Goal's Repo line isn't owner/name: {value[:80]!r}")
    if value.split("/")[0].lower() != goal_repo.split("/")[0].lower():
        raise Refused(f"the Goal's Repo {value} is outside {goal_repo.split('/')[0]}")
    return value


def issue_body(block: str, ref: str) -> str:
    """The snapshot block plus the Goal line, and nothing else (#943, Part B)."""
    return f"{block}\n\nGoal: {ref}\n"


def _label(f: Feature) -> str:
    return f"{f.id} {f.name}"


def pull(goal: tuple[str, int], source: SpecSource, gh: GitHub, today: Optional[datetime] = None,
         dry_run: bool = False, *, owner: str, backend: Optional[str] = None,
         out: Callable[[str], None] = print) -> list[Result]:
    """Pull the Goal's linked initiative (`goal` is (owner/name, N)). Prints one line per
    feature and returns them. `today` is the pull time (default now, UTC); `backend` is
    `[specs] backend` (default the source's name). With `dry_run`, writes nothing.

    Raises Refused, or the source's SchemaError, before any write. A GitHub or source error
    after the first write propagates; what was written stays written and logged."""
    goal_repo, n = goal
    ref = goal_ref(goal_repo, n)
    when = today or datetime.now(timezone.utc)
    body = check_goal(gh.goal(goal_repo, n), ref, owner)
    scheme, initiative = parse_link(body, ref)
    backend = backend or source.name
    if scheme != backend:
        raise Refused(f"{ref} links a {scheme}:// source, but [specs] backend is {backend!r}")
    repo = target_repo(body, goal_repo)

    # Every read first: a SchemaError here stops the run before any write (§13).
    try:
        features = source.list_features(initiative)
    except KeyError:
        raise Refused(f"the {backend} source has no initiative {initiative!r}") from None
    plan: list[tuple[Feature, str, str, str]] = []   # (feature, outcome, detail, body)
    for f in features:
        if f.status != FeatureStatus.READY:
            plan.append((f, SKIPPED, f.status.value, ""))
        elif f.issue_url:
            plan.append((f, LINKED, f.issue_url, ""))
        else:
            spec = source.get_spec(f.id)
            ok, why = spec.pullable()
            if not ok:
                plan.append((f, NOT_PULLABLE, why, ""))
            else:
                try:
                    block = snapshot.render(f, spec, source.name, when)
                except ValueError as e:
                    raise Refused(f"{f.id} can't go in a snapshot: {e}") from None
                plan.append((f, OPENED, spec.content_hash(), issue_body(block, ref)))

    mode = "dry run: nothing written" if dry_run else f"issues open in {repo}"
    simulated = ", simulated" if getattr(source, "simulated", False) else ""
    out(f"swarm specs pull: Goal {ref}, {backend}://{initiative}{simulated} ({mode})")
    results = []
    for f, outcome, detail, new_body in plan:
        if outcome == SKIPPED:
            # Only the ID and status: a Draft's name is not consent to publish (#943).
            line = f"  {f.id}: skipped ({detail})"
        elif outcome == LINKED:
            line = f"  {_label(f)}: already linked to {detail}"
        elif outcome == NOT_PULLABLE:
            line = f"  {_label(f)}: not pullable ({detail})"
        elif dry_run:
            line = f"  {_label(f)}: would open an issue in {repo}"
        else:
            line = f"  {_label(f)}: opened {_open(f, detail, new_body, repo, goal, source, gh)}"
        out(line)
        results.append(Result(f.id, outcome, line))
    return results


def _open(f: Feature, digest: str, body: str, repo: str, goal: tuple[str, int],
          source: SpecSource, gh: GitHub) -> str:
    """Open the feature's issue under the Goal, write the link and status back, and log it.
    The link goes first: it is the idempotence key (#942)."""
    ref = goal_ref(*goal)
    issue = gh.open_issue(repo, f.name, body)
    url = issue["html_url"]
    source.set_links(f.id, issue_url=url)
    events.append("pull", ref, f.id, hash=digest, issue_url=url)
    events.append("write", ref, f.id, what="links", issue_url=url)
    gh.add_sub_issue(goal[0], goal[1], issue["id"])
    source.set_status(f.id, FeatureStatus.IN_PROGRESS)
    events.append("write", ref, f.id, what="status", status=FeatureStatus.IN_PROGRESS.value)
    return url
