"""The desk's "Plan" panel (#712, laid out in #711, under #685).

The plan is the open Goal and Area issues the owner opened (GOV-0031). A Goal or Area opened
by anyone else isn't plan: it gets one quiet line at the panel's foot.

One block per Goal or Area, Goals first, then Areas, each by number: its line (the title's
lead, such as `M3`, then the rest, then "4 open, 2 done" over its direct sub-issues), then
each open sub-issue by number with its status:

  - go: go under GOV-0031, or by the owner's most recent `ready` (GOV-0006);
  - waiting on #N: its only reasons are open blocked-by issues;
  - not go: and the reason, in swarm.scope_refusal()'s words, so the desk and `swarm watch`
    say the same thing;
  - then "PR #N" when an open PR closes it.

A sub-issue's own open sub-issues (a mission's Tasks) sit one level in, the same way; deeper
levels show only a count. Closed sub-issues aren't listed; "done" counts them.

The go here is GOV-0031's scope and the owner's `ready`. GOV-0026's `**Milestone:**` lines,
which also count until swarm.MILESTONE_UNTIL (2026-11-16), aren't read: no Task under a Goal
needs them.

API calls: GraphQL only, through ghql.py: one query with two searches (open Goals, open
Areas); then each one's sub-issues two levels deep, TREE_BATCH Goals to a query; then what
the go needs for each open sub-issue, GO_BATCH to a query. About 3 or 4 queries for 5 Goals.
Every Goal is in this repo today; Goals in other repos of the org (GOV-0031) are left for
later. Stdlib only.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import ghql
from layout import esc
from report import inline

KINDS = ("Goal", "Area")
SEARCH_MAX = 50       # open Goals, and open Areas, read
SUBS_MAX = 50         # sub-issues read per issue, at each level
LABELS_MAX = 20
COMMENTS_MAX = 100    # the owner's comment is a veto (GOV-0031); more than this and the status is unknown
TREE_BATCH = 10       # Goals per tree query: 10 × 50 × 50 nodes, inside GraphQL's 500,000-node limit
GO_BATCH = 20         # sub-issues per go query

TITLE_RE = re.compile(r"^(\S{1,12}):\s+(.+)$")

_AUTHOR = "author { login __typename }"
_NODE = "number title url state " + _AUTHOR + " repository { nameWithOwner } issueType { name }"
# What the go needs for one sub-issue (GOV-0031, GOV-0006), read in a second pass so the tree's
# query stays inside GraphQL's node limit.
GO_FIELD = ("i%%d: issue(number: %%d) { labels(first: %d) { totalCount nodes { name } } "
            "timelineItems(last: 20, itemTypes: [LABELED_EVENT]) { nodes { ... on LabeledEvent "
            "{ label { name } actor { login __typename } } } } "
            "comments(last: %d) { totalCount nodes { %s } } "
            "blockedBy(first: %%d) { totalCount nodes { number state repository { nameWithOwner } } } "
            "closedByPullRequestsReferences(first: 5, includeClosedPrs: false) { nodes { number url } } }"
            ) % (LABELS_MAX, COMMENTS_MAX, _AUTHOR)
SEARCH = ("%s: search(type: ISSUE, first: " + str(SEARCH_MAX) + ', query: "repo:%s is:issue is:open type:%s") '
          "{ issueCount nodes { ... on Issue { " + _NODE + " } } }")


def _swarm():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "launcher"))
    import swarm
    return swarm


def tree_field() -> str:
    """The GraphQL for one Goal's sub-issues two levels deep, as `field % (n, n)` for
    ghql.batched(). The second level carries a count of what's below it."""
    inner = f"subIssues(first: {SUBS_MAX}) {{ totalCount nodes {{ {_NODE} subIssuesSummary {{ total completed }} }} }}"
    return (f"i%d: issue(number: %d) {{ subIssues(first: {SUBS_MAX}) {{ totalCount nodes "
            f"{{ {_NODE} {inner} }} }} }}")


def go_field() -> str:
    """The GraphQL for one sub-issue's go, as `field % (n, n)` for ghql.batched()."""
    return GO_FIELD.replace("first: %d)", f"first: {_swarm().BLOCKERS_MAX})")


def search(repo: str, run=subprocess.run) -> list[dict]:
    """The open Goal and Area issues, as GraphQL nodes. Raises RuntimeError if the query fails."""
    q = "query { %s }" % " ".join(SEARCH % (k.lower(), repo, k) for k in KINDS)
    r = run(["gh", "api", "graphql", "-f", f"query={q}"], capture_output=True, text=True, timeout=120)
    try:
        data = (json.loads(r.stdout or "null") or {}).get("data")
    except (ValueError, AttributeError):
        data = None
    if not data or any(data.get(k.lower()) is None for k in KINDS):
        raise RuntimeError(f"gh api graphql failed: {(r.stderr or '').strip()[:300]}")
    out = []
    for k in KINDS:
        out += [n for n in data[k.lower()].get("nodes") or [] if n]
    return out


def _open_subs(tree: dict | None, repo: str) -> list[int]:
    """The open sub-issues in this repo, both levels, by number."""
    out = set()
    for a in ((tree or {}).get("subIssues") or {}).get("nodes") or []:
        for x in [a, *(((a or {}).get("subIssues") or {}).get("nodes") or [])]:
            if x and (x.get("state") or "").lower() == "open" \
                    and (x.get("repository") or {}).get("nameWithOwner") in (None, repo):
                out.add(x["number"])
    return sorted(out)


def _batches(repo: str, numbers: list[int], field: str, size: int, batched) -> dict[int, dict | None]:
    out: dict[int, dict | None] = {}
    for i in range(0, len(numbers), size):
        chunk = numbers[i:i + size]
        try:
            out.update(batched(repo, chunk, field, size))
        except (RuntimeError, OSError, subprocess.SubprocessError):
            out.update({n: None for n in chunk})
    return out


def fetch(repo: str, run=subprocess.run, batched=ghql.batched) -> dict | None:
    """{"scopes": search()'s nodes, "trees": {number: its sub-issues two levels deep, or None},
    "go": {sub-issue number: go_field()'s data, or None}}, or None if the Goals couldn't be
    read. A batch that fails leaves its numbers as None."""
    try:
        scopes = search(repo, run)
    except (RuntimeError, OSError, subprocess.SubprocessError):
        return None
    trees = _batches(repo, sorted({s["number"] for s in scopes}), tree_field(), TREE_BATCH, batched)
    subs = sorted({n for t in trees.values() for n in _open_subs(t, repo)})
    return {"scopes": scopes, "trees": trees, "go": _batches(repo, subs, go_field(), GO_BATCH, batched)}


def _parent(node: dict) -> dict:
    return {"repo": (node.get("repository") or {}).get("nameWithOwner"), "number": node.get("number"),
            "state": (node.get("state") or "").lower(), "type": (node.get("issueType") or {}).get("name"),
            "author": ghql.login(node.get("author"))}


def status(node: dict, parents: list[dict], owner: str, agents: set[str], repo: str) -> dict:
    """One open sub-issue's status: {"kind": "go" | "waiting" | "not_go" | "unknown", "text"}.
    `parents` is the chain above it, nearest first, ending at the owner's Goal or Area."""
    swarm = _swarm()
    n = node.get("number")
    blocked = node.get("blockedBy")
    comments = node.get("comments")
    labels = node.get("labels")
    if blocked is None or comments is None or labels is None or node.get("timelineItems") is None \
            or (comments.get("totalCount") or 0) > len(comments.get("nodes") or []) \
            or (labels.get("totalCount") or 0) > len(labels.get("nodes") or []):
        return {"kind": "unknown", "text": "status unknown: couldn't read its links"}
    issue = {"user": {"login": ghql.login(node.get("author"))},
             "labels": [{"name": x.get("name")} for x in labels.get("nodes") or []]}
    names = {x["name"] for x in issue["labels"]}
    events = [{"event": "labeled", "label": {"name": (e.get("label") or {}).get("name")},
               "actor": {"login": ghql.login(e.get("actor"))}}
              for e in (node.get("timelineItems") or {}).get("nodes") or [] if e]
    ready = swarm.label_event(events, "ready")
    if "ready" in names and ready and ready["actor"]["login"] == owner:
        return {"kind": "go", "text": "go"}
    if "gov:question" in names:
        why = swarm.issue_refusals(n, {**issue, "state": "open"}, events, owner)
        return {"kind": "not_go", "text": f"not go: {why[0]}" if why else "go"}
    bnodes = blocked.get("nodes") or []
    scope = {"author": issue["user"]["login"], "type": (node.get("issueType") or {}).get("name"),
             "parents": parents, "deep": False,
             "blocked_by": [{"repo": (b.get("repository") or {}).get("nameWithOwner"),
                             "number": b.get("number"), "state": (b.get("state") or "").lower()}
                            for b in bnodes],
             "blockers_complete": (blocked.get("totalCount") or 0) <= len(bnodes)}
    owner_comments = [{"user": {"login": ghql.login(c.get("author"))}}
                      for c in comments.get("nodes") or [] if c]
    other = swarm.scope_refusal(n, issue, scope, owner, agents, lambda: owner_comments,
                                blockers=False, repo=repo)
    if other is not None:
        return {"kind": "not_go", "text": f"not go: {other}"}
    if not scope["blockers_complete"]:
        why = swarm.scope_refusal(n, issue, scope, owner, agents, None, repo=repo)
        return {"kind": "not_go", "text": f"not go: {why}"}
    still = [b for b in scope["blocked_by"] if b["state"] != "closed"]
    if still:
        return {"kind": "waiting",
                "text": "waiting on " + ", ".join(swarm.scope_ref(b, repo) for b in still)}
    return {"kind": "go", "text": "go"}


def _row(node: dict, parents: list[dict], owner: str, agents: set[str], repo: str,
         depth: int, go: dict) -> dict:
    """One open sub-issue's line, with its go data (go_field()) merged in when it was read."""
    tree = node
    if (node.get("repository") or {}).get("nameWithOwner") in (None, repo):
        node = {**node, **(go.get(node.get("number")) or {})}
    prs = ((node.get("closedByPullRequestsReferences") or {}).get("nodes") or [])
    pr = next((p for p in prs if p), None)
    row = {"number": node.get("number"), "ref": _swarm().scope_ref(_parent(node), repo),
           "title": node.get("title") or "", "url": node.get("url"),
           "status": status(node, parents, owner, agents, repo),
           "pr": {"number": pr["number"], "url": pr.get("url")} if pr else None}
    if depth == 1:
        conn = tree.get("subIssues")
        kids = [k for k in (conn or {}).get("nodes") or [] if k]
        here = [_parent(node), *parents]
        row["children"] = [_row(k, here, owner, agents, repo, 2, go)
                           for k in sorted(kids, key=lambda k: k.get("number") or 0)
                           if (k.get("state") or "").lower() == "open"]
        row["unread"] = conn is None or (conn.get("totalCount") or 0) > len(kids)
    else:
        summary = node.get("subIssuesSummary") or {}
        row["below"] = max(0, (summary.get("total") or 0) - (summary.get("completed") or 0))
    return row


def title_parts(title: str) -> tuple[str, str]:
    """("M3", "The Desk shows ...") from "M3: The Desk shows ..."; ("", title) if it has no lead."""
    m = TITLE_RE.match(title or "")
    return (m.group(1), m.group(2)) if m else ("", title or "")


def build(data: dict | None, owner: str | None, repo: str, agents: set[str] | None = None) -> dict:
    """The panel's data: {"read": bool, "scopes": [...], "not_plan": [...]}. Each scope is
    {"number", "kind", "lead", "title", "url", "open", "done", "unread", "subs": [rows]}."""
    if data is None or not owner:
        return {"read": False, "scopes": [], "not_plan": []}
    if agents is None:
        agents = _swarm().agent_logins()
    scopes, not_plan = [], []
    seen = set()
    for s in sorted(data["scopes"], key=lambda s: (KINDS.index((s.get("issueType") or {}).get("name"))
                                                    if (s.get("issueType") or {}).get("name") in KINDS
                                                    else len(KINDS), s.get("number") or 0)):
        kind = (s.get("issueType") or {}).get("name")
        if kind not in KINDS or (s.get("state") or "").lower() != "open" or s["number"] in seen:
            continue
        seen.add(s["number"])
        author = ghql.login(s.get("author"))
        if author != owner:
            not_plan.append({"number": s["number"], "kind": kind, "author": author, "url": s.get("url")})
            continue
        lead, title = title_parts(s.get("title"))
        top = _parent(s)
        conn = (data["trees"].get(s["number"]) or {}).get("subIssues")
        kids = [k for k in (conn or {}).get("nodes") or [] if k]
        opened = [k for k in kids if (k.get("state") or "").lower() == "open"]
        scopes.append({
            "number": s["number"], "kind": kind, "lead": lead, "title": title, "url": s.get("url"),
            "open": len(opened) if conn is not None else None,
            "done": len(kids) - len(opened) if conn is not None else None,
            "unread": conn is None or (conn.get("totalCount") or 0) > len(kids),
            "subs": [_row(k, [top], owner, agents, repo, 1, data.get("go") or {})
                     for k in sorted(opened, key=lambda k: k.get("number") or 0)]})
    return {"read": True, "scopes": scopes, "not_plan": not_plan}


def _sub_lines(rows: list[dict]) -> str:
    out = []
    for r in rows:
        st = r["status"]
        pr = (f' <a class="pr" href="{esc(r["pr"]["url"])}">PR #{r["pr"]["number"]}</a>'
              if r["pr"] and r["pr"].get("url") else
              f' <span class="pr">PR #{r["pr"]["number"]}</span>' if r["pr"] else "")
        kids = ""
        if r.get("children"):
            kids = f'<ul>{_sub_lines(r["children"])}</ul>'
        more = ""
        if r.get("below"):
            more = f' <span class="muted">and {r["below"]} more below</span>'
        if r.get("unread"):
            more += ' <span class="muted">(not all its sub-issues could be read)</span>'
        out.append(f'<li><a href="{esc(r["url"])}"><span class="num">{esc(r["ref"])}</span> '
                   f'{esc(r["title"])}</a> <span class="st {esc(st["kind"])}">{inline(st["text"])}</span>'
                   f'{pr}{more}{kids}</li>')
    return "".join(out)


def render(p: dict | None) -> str:
    """The desk's "Plan" panel."""
    if p is None:
        return ""
    return f'<section class="plan">{_body(p)}</section>'


def _body(p: dict) -> str:
    head = "<h2>Plan</h2>"
    if not p["read"]:
        return f'{head}<p class="muted">Couldn\'t read the plan from GitHub.</p>'
    out = [head]
    if not p["scopes"]:
        out.append('<p class="muted">No plan: the owner has no open Goal or Area.</p>')
    for s in p["scopes"]:
        lead = f'<span class="mono">{esc(s["lead"])}</span> ' if s["lead"] else ""
        counts = (f'<span class="muted">{s["open"]} open, {s["done"]} done</span>'
                  if s["open"] is not None else
                  '<span class="muted">couldn\'t read its sub-issues</span>')
        out.append(f'<div class="scope"><h3>{lead}<a href="{esc(s["url"])}">{esc(s["title"])}</a> '
                   f'{counts}</h3>')
        if s["subs"]:
            out.append(f'<ul class="subs">{_sub_lines(s["subs"])}</ul>')
        elif s["open"] is not None:
            out.append('<p class="muted">Nothing open under it.</p>')
        if s["unread"] and s["open"] is not None:
            out.append('<p class="muted">Not all its sub-issues could be read.</p>')
        out.append("</div>")
    for x in p["not_plan"]:
        out.append(f'<p class="muted method">Not plan: <a href="{esc(x["url"])}">#{x["number"]}</a>, '
                   f'a {esc(x["kind"])} opened by {esc(x["author"])} (GOV-0031).</p>')
    return "".join(out)


def state(p: dict | None) -> dict | None:
    """state.json's `plan`."""
    return p
