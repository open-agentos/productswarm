"""`swarm specs push <goal>` (#957; per #942's ruling, #937 §5.4).

push() writes delivery state back to the spec source: each feature's status, its Issue and PR
links, and one delivery comment per merged PR. It talks to the source only through
`SpecSource` and to GitHub only through the small `GitHub` protocol below, so tests run it
against the fake backend and a stub with no network.

**Which issues.** A feature's issues are the Goal's sub-issues whose snapshot block (#953)
names it: usually one, several when the lead split it (§5.2). The Goal must pass the same
checks as for pull (an open Goal the owner opened and only the owner edited, whose
`Spec source:` line names the configured backend).

**Status** (§5.4's table), per issue:

- issue open, no open or merged PR: In progress;
- PR open (changes requested or not): In review, with the PR's URL;
- PR merged and issue closed: Shipped, with the PR's URL;
- issue closed with no merged PR, or a `hold` label: Blocked, with a one-line reason.

A merged PR whose issue GitHub left open (#806) counts as In review until the issue closes.
A split feature is Blocked if any child is; otherwise it takes its slowest child's status.

**Idempotence** (#942). The feature's own Status, Issue and PR fields are the key:
`set_status` and `set_links` run only when they differ. A delivery comment carries the
`swarm:pr=<n>` marker, and `SpecSource.comment` writes nothing when one exists. The event
log is a record, never consulted before a write.

**Reads before writes.** The Goal, its sub-issues and the features are all read, and every
feature's writes planned, before the first write.

The bridge makes no model calls (§7): the lead passes each feature's "what shipped"
paragraph in. A merged PR without one gets no comment and is listed as waiting on it,
unless the log records its comment as posted: the log only quiets that line, it never
decides a write. Standard library only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Mapping, Optional, Protocol

from . import events, snapshot
from .source import Feature, FeatureStatus, SpecSource
from .sync import Refused, check_goal, goal_ref, login, parse_link

REVIEWER = "productswarm-reviewer[bot]"
HOLD = "hold"
FEATURE_ID_RE = re.compile(r"FEAT-[1-9][0-9]*")
# Slowest first: a split feature takes the first of these any child has.
ORDER = (FeatureStatus.IN_PROGRESS, FeatureStatus.IN_REVIEW, FeatureStatus.SHIPPED)
VERDICTS = {"APPROVED": "approved", "CHANGES_REQUESTED": "changes requested",
            "COMMENTED": "commented", "DISMISSED": "dismissed"}


class GitHub(Protocol):
    """The GitHub reads push makes. swarm.py's GhSpecs is the real one."""

    def goal(self, repo: str, n: int) -> Optional[dict]:
        """As sync.GitHub.goal."""
        ...

    def sub_issues(self, repo: str, n: int) -> list[dict]:
        """The Goal's sub-issues, each as `items_from_graphql` returns them. Raises
        ValueError when there are more than one page holds."""
        ...


@dataclass(frozen=True)
class PR:
    number: int
    url: str
    state: str                      # OPEN, CLOSED or MERGED
    head: str = ""                  # head commit oid (the merged head, once merged)
    reviews: tuple = ()             # ({"author": login, "state": ..., "commit": oid}, ...)


@dataclass(frozen=True)
class Item:
    """One sub-issue of the Goal, with the PRs that close it."""

    url: str
    state: str                      # OPEN or CLOSED
    body: str = ""
    labels: tuple = ()
    prs: tuple = ()                 # PR, ...


@dataclass
class Result:
    feature_id: str
    line: str
    writes: list = field(default_factory=list)   # what was (or, dry run, would be) written
    waiting: list = field(default_factory=list)  # merged PR numbers waiting on a paragraph


def items_from_graphql(issue: Optional[dict]) -> list[Item]:
    """The Goal's sub-issues from the GraphQL issue node swarm.py's query returns. Raises
    ValueError when the sub-issues, or one issue's PRs, run past the page read."""
    subs = (issue or {}).get("subIssues") or {}
    nodes = subs.get("nodes") or []
    if subs.get("totalCount", 0) > len(nodes):
        raise ValueError(f"the Goal has {subs['totalCount']} sub-issues; push reads at most "
                         f"{len(nodes)}")
    out = []
    for n in nodes:
        refs = n.get("closedByPullRequestsReferences") or {}
        pr_nodes = refs.get("nodes") or []
        if refs.get("totalCount", 0) > len(pr_nodes):
            raise ValueError(f"{n.get('url')} has more closing PRs than push reads")
        prs = tuple(PR(
            number=p["number"], url=p["url"], state=p["state"], head=p.get("headRefOid") or "",
            reviews=tuple({"author": login(r.get("author")), "state": r.get("state"),
                           "commit": ((r.get("commit") or {}).get("oid") or "")}
                          for r in ((p.get("reviews") or {}).get("nodes") or [])))
            for p in pr_nodes)
        labels = tuple(lb["name"] for lb in ((n.get("labels") or {}).get("nodes") or []))
        out.append(Item(url=n["url"], state=n["state"], body=n.get("body") or "",
                        labels=labels, prs=prs))
    return out


def parse_what_shipped(values) -> dict[str, str]:
    """`FEAT-n=<text>` strings → {FEAT-n: text}. Raises ValueError on a bad one or a repeat."""
    out: dict[str, str] = {}
    for v in values or ():
        fid, sep, text = v.partition("=")
        fid, text = fid.strip(), text.strip()
        if not sep or not FEATURE_ID_RE.fullmatch(fid) or not text:
            raise ValueError(f"--what-shipped takes FEAT-n=<paragraph>, not {v[:60]!r}")
        if fid in out:
            raise ValueError(f"--what-shipped gives {fid} twice")
        out[fid] = text
    return out


def child_status(item: Item) -> tuple[FeatureStatus, Optional[PR], Optional[str]]:
    """(status, the PR to link, Blocked's reason) for one issue, by §5.4's table."""
    merged = [p for p in item.prs if p.state == "MERGED"]
    opened = [p for p in item.prs if p.state == "OPEN"]
    def latest(ps):
        return max(ps, key=lambda p: p.number)
    if item.state == "CLOSED" and merged:
        return FeatureStatus.SHIPPED, latest(merged), None
    if HOLD in item.labels:
        return FeatureStatus.BLOCKED, None, f"on hold: {item.url}"
    if item.state == "CLOSED":
        return FeatureStatus.BLOCKED, None, f"issue closed unmerged: {item.url}"
    if opened or merged:
        return FeatureStatus.IN_REVIEW, latest(opened or merged), None
    return FeatureStatus.IN_PROGRESS, None, None


def feature_status(items: list[Item]) -> tuple[FeatureStatus, Optional[PR], Optional[str]]:
    """A (split) feature's status: Blocked if any child is, else its slowest child's."""
    got = [child_status(i) for i in items]
    for s in got:
        if s[0] == FeatureStatus.BLOCKED:
            return s
    return min(got, key=lambda s: ORDER.index(s[0]))


def verdict_at_head(pr: PR) -> str:
    """The latest reviewer review on the PR's (merged) head, or "no review at head"."""
    at_head = [r for r in pr.reviews if r["author"] == REVIEWER and pr.head
               and r["commit"] == pr.head]
    if not at_head:
        return "no review at head"
    state = at_head[-1]["state"]
    return VERDICTS.get(state, str(state).lower())


def delivery_comment(pr: PR, paragraph: str, model: str) -> str:
    """The comment posted on the feature for one merge (§5.4)."""
    return (f"Shipped in {pr.url}.\n\n"
            f"Reviewer verdict at the merged head ({pr.head[:12] or 'unknown'}): "
            f"{verdict_at_head(pr)}.\n\n"
            f"{paragraph}\n\n"
            f"-- lead ({model})")


def marker(pr: PR) -> str:
    return f"swarm:pr={pr.number}"


def _label(f: Feature) -> str:
    return f"{f.id} {f.name}"


def push(goal: tuple[str, int], source: SpecSource, gh: GitHub,
         what_shipped: Optional[Mapping[str, str]] = None, dry_run: bool = False, *,
         owner: str, model: str, backend: Optional[str] = None,
         out: Callable[[str], None] = print) -> list[Result]:
    """Push the Goal's delivery state to its linked initiative (`goal` is (owner/name, N)).
    Prints one line per feature and returns them. `what_shipped` maps FEAT-n to the lead's
    paragraph; `model` is the lead's model, for the comment's ending. With `dry_run`, writes
    nothing.

    Raises Refused, or the source's SchemaError, before any write. A source error after the
    first write propagates; what was written stays written and logged."""
    goal_repo, n = goal
    ref = goal_ref(goal_repo, n)
    what_shipped = dict(what_shipped or {})
    body = check_goal(gh.goal(goal_repo, n), ref, owner)
    scheme, initiative = parse_link(body, ref)
    backend = backend or source.name
    if scheme != backend:
        raise Refused(f"{ref} links a {scheme}:// source, but [specs] backend is {backend!r}")

    # Every read first.
    try:
        features = source.list_features(initiative)
    except KeyError:
        raise Refused(f"the {backend} source has no initiative {initiative!r}") from None
    try:
        items = gh.sub_issues(goal_repo, n)
    except ValueError as e:
        raise Refused(str(e)) from None
    by_feature: dict[str, list[Item]] = {}
    for item in items:
        try:
            snap = snapshot.parse(item.body)
        except snapshot.SnapshotError as e:
            raise Refused(f"{item.url}'s snapshot block can't be read: {e}") from None
        if snap is not None:
            by_feature.setdefault(snap.feature_id, []).append(item)
    known = {f.id for f in features}
    stray = sorted(set(what_shipped) - known)
    if stray:
        raise Refused(f"--what-shipped names {', '.join(stray)}, not a feature of {initiative}")

    mode = "dry run: nothing written" if dry_run else "writing to the source"
    simulated = ", simulated" if getattr(source, "simulated", False) else ""
    out(f"swarm specs push: Goal {ref}, {backend}://{initiative}{simulated} ({mode})")
    posted = {e.get("pr") for e in events.read(ref)
              if e.get("kind") == "write" and e.get("what") == "comment"}
    results = []
    for f in features:
        children = by_feature.get(f.id)
        if not children:
            # Only the ID: a feature never pulled may be a Draft, not consent to publish (#943).
            line = f"  {f.id}: no issue under the Goal"
            out(line)
            results.append(Result(f.id, line))
            continue
        results.append(_push_one(f, children, ref, source, what_shipped.get(f.id), model,
                                 posted, dry_run, out))
    return results


def _push_one(f: Feature, children: list[Item], ref: str, source: SpecSource,
              paragraph: Optional[str], model: str, posted: set, dry_run: bool,
              out: Callable[[str], None]) -> Result:
    status, pr, reason = feature_status(children)
    issue_url = f.issue_url or children[0].url
    pr_url = pr.url if pr else None
    new_issue = issue_url if issue_url != f.issue_url else None
    new_pr = pr_url if pr_url and pr_url != f.pr_url else None
    merged: dict[int, PR] = {}
    for item in children:
        for p in item.prs:
            if p.state == "MERGED":
                merged[p.number] = p

    result = Result(f.id, "")
    if status != f.status:
        result.writes.append(f"status {f.status.value} → {status.value}"
                             + (f" ({reason})" if reason else ""))
        if not dry_run:
            source.set_status(f.id, status, reason)
            events.append("write", ref, f.id, what="status", status=status.value,
                          **({"reason": reason} if reason else {}))
    if new_issue or new_pr:
        result.writes.append("; ".join(
            s for s in (new_issue and f"issue {new_issue}", new_pr and f"PR {new_pr}") if s))
        if not dry_run:
            source.set_links(f.id, issue_url=new_issue, pr_url=new_pr)
            events.append("write", ref, f.id, what="links",
                          **{k: v for k, v in (("issue_url", new_issue), ("pr_url", new_pr)) if v})
    for number in sorted(merged):
        p = merged[number]
        if paragraph is None:
            if number not in posted:
                result.waiting.append(number)
            continue
        if dry_run:
            result.writes.append(f"delivery comment for PR #{number}, unless it is there")
            continue
        if source.comment(f.id, delivery_comment(p, paragraph, model), marker(p)):
            result.writes.append(f"delivery comment for PR #{number}")
            events.append("write", ref, f.id, what="comment", pr=number, marker=marker(p))

    said = "; ".join(result.writes) or "unchanged"
    if dry_run and result.writes:
        said = "would write " + said
    if result.waiting:
        prs = ", ".join(f"#{n}" for n in result.waiting)
        said += (f"; PR {prs} merged, delivery comment waiting on the lead's paragraph "
                 f"(--what-shipped {f.id}=<text>)")
    result.line = f"  {_label(f)}: {said}"
    out(result.line)
    return result
