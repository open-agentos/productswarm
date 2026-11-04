#!/usr/bin/env python3
"""Stop hook for runs `swarm watch` starts: keep going until the role's done-condition
is met (#148, the second of three issues for the owner's answer on #125, option 3).

    python3 -I <runtime>/launcher/stophook.py        (Claude Code's Stop payload on stdin)

The launcher writes this hook into a session's worktree .claude/settings.local.json
only when `swarm watch` started it (by="watch"). It runs from the pinned copy of
origin/main (#93), as the heartbeat hook does, so only merged code runs as a hook.
Sessions started with `swarm up` and `swarm launch` don't get it. A reviewer run in
GitHub Actions (launcher/actions_review.py run, #215) gets it too, as by="actions", from
the job's checkout of main.

When Claude Code is about to stop, the hook reads GitHub (only reads, as the run's App,
through the session's `gh`) and checks the run's done-condition:

| run                                         | done when                                       |
|---------------------------------------------|-------------------------------------------------|
| builder on an issue ([build])               | a PR, open or merged, closes the issue          |
| builder on a PR ([respond])                 | the reviewer's latest review at the PR's head   |
|                                             | isn't "changes requested" (a push moved the     |
|                                             | head, or there was nothing to respond to), or   |
|                                             | the run commented on the PR, or the PR closed   |
| reviewer                                    | every open, non-draft PR that existed when the  |
|                                             | run started has a reviewer review at its head   |
|                                             | or one posted since the run started             |
| reviewer on one PR (Actions, #215)          | that PR, if still open and not a draft, has a   |
|                                             | reviewer review at its head or one since start  |
| docs on a gov:ruled question ([record])     | a PR, open or merged, closes the question       |
| any other run (e.g. an [answer] run)        | always                                          |

Also done, because a run can stop for good reasons without that (#125, point 2):
- the run opened, or commented on, a `gov:question` (other than its own issue) since
  it started, naming its issue or PR as #N: it is blocked on it. Every session of a
  role acts as the same App, so the #N is what tells this run's question from another
  session's;
- the run commented on its own issue since it started, naming another open issue as #M:
  it is blocked on an unfinished prerequisite (#184);
- the issue fails `swarm launch`'s refusal checks: it is closed, or its latest `ready`
  (`gov:ruled` for [record]) wasn't added by the owner (GOV-0006);
- the work is already done: a PR, open or merged, already closes the issue.

When the condition isn't met it prints {"decision": "block", "reason": ...} naming what's
missing, and Claude Code continues the run. It allows the stop:
- whenever stop_hook_active is true (a hook is already continuing this run);
- after MAX_BLOCKS blocks in one run, counted in ~/.productswarm/launcher/<id>.stop.json;
- if GitHub can't be read, or anything else fails: it never fails closed.
The run's budget (GOV-0012) is what bounds spend; MAX_BLOCKS is a code value.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import swarm  # noqa: E402

MAX_BLOCKS = 3
MARK = "launcher/stophook.py"
TIMEOUT = 90          # seconds Claude Code gives the hook; past it the stop goes ahead
GH_TIMEOUT = 20       # per gh call
CHANGES = "CHANGES_REQUESTED"
# Who starts runs this hook keeps going: `swarm watch`, and a reviewer run in Actions
# (launcher/actions_review.py run, #215), which records its entry the same way.
HEADLESS = ("watch", "actions")


def app_login(role: str) -> str:
    return f"productswarm-{role}[bot]"


# ---------------------------------------------------------------- settings (launcher side)

def script_for(heartbeat_hook: str) -> str:
    """This script in the same pinned runtime copy as the heartbeat hook path."""
    return str(Path(heartbeat_hook).parent.parent / MARK)


def with_stop_hook(settings: dict, script: str) -> dict:
    """A copy of settings with our Stop entry added (any earlier one of ours replaced)."""
    settings = json.loads(json.dumps(settings))
    hooks = settings.setdefault("hooks", {})
    groups = []
    for g in hooks.get("Stop", []):
        kept = [h for h in g.get("hooks", []) if MARK not in h.get("command", "")]
        if kept:
            groups.append({**g, "hooks": kept})
    groups.append({"hooks": [{"type": "command", "command": f'python3 -I "{script}"',
                              "timeout": TIMEOUT}]})
    hooks["Stop"] = groups
    return settings


# ---------------------------------------------------------------- reading GitHub

@dataclass
class GitHub:
    """The hook's only GitHub access: reads. Tests pass canned functions."""
    get: Callable[[str], object]            # one REST GET
    items: Callable[[str], list]            # every item of a paginated REST list
    closing_prs: Callable[[str, int], list] # PRs (open or merged) that close an issue


def gh(*args: str) -> str:
    r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=GH_TIMEOUT)
    if r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:2])} failed: {r.stderr.strip()[:300]}")
    return r.stdout


def live_github() -> GitHub:
    def get(path):
        return json.loads(gh("api", path) or "null")

    def items(path):
        out = gh("api", "--paginate", path, "--jq", ".[]")
        return [json.loads(line) for line in out.splitlines() if line.strip()]

    def closing_prs(repo, n):
        d = json.loads(gh("issue", "view", str(n), "--repo", repo, "--json", "closedByPullRequestsReferences"))
        return d.get("closedByPullRequestsReferences") or []

    return GitHub(get=get, items=items, closing_prs=closing_prs)


# ---------------------------------------------------------------- done-conditions

def ts(s: str | None) -> float | None:
    if not s:
        return None
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def iso(t: float) -> str:
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def since_start(x: dict, start: float, field: str = "created_at") -> bool:
    t = ts(x.get(field))
    return t is not None and t >= start


def mine(x: dict, login: str) -> bool:
    return (x.get("user") or {}).get("login") == login


def labels_of(issue: dict) -> set[str]:
    return {lb.get("name") for lb in issue.get("labels") or []}


def names_run(text: str | None, e: swarm.Started) -> bool:
    """Whether text cites the run's issue or PR as #N. Every session of a role acts as
    the same App, so this is what ties a question to this run rather than to another
    session of the role. A reviewer pass isn't on one issue, so any question counts."""
    refs = [n for n in (e.issue, e.pr) if n]
    return not refs or any(re.search(rf"#{n}\b", text or "") for n in refs)


def blocked_on_question(g: GitHub, repo: str, e: swarm.Started, login: str) -> int | None:
    """A gov:question (other than the run's own issue) that the run's App opened or
    commented on since the run started, naming the run's issue or PR, else None."""
    since = iso(e.started)
    for it in g.items(f"repos/{repo}/issues?labels=gov:question&state=all&since={since}&per_page=100"):
        if (it.get("number") != e.issue and mine(it, login) and since_start(it, e.started)
                and names_run(it.get("body"), e)):
            return it["number"]
    for c in g.items(f"repos/{repo}/issues/comments?since={since}&per_page=100"):
        n = int(str(c.get("issue_url", "")).rsplit("/", 1)[-1] or 0)
        if (not n or n == e.issue or not mine(c, login) or not since_start(c, e.started)
                or not names_run(c.get("body"), e)):
            continue
        if "gov:question" in labels_of(g.get(f"repos/{repo}/issues/{n}") or {}):
            return n
    return None


def blocked_on_prerequisite(g: GitHub, repo: str, e: swarm.Started, login: str) -> int | None:
    """An open issue (not a PR, not the run's own issue) that the run's App named as #M in
    a comment on the run's issue since the run started, else None (#184). The comment on
    its own issue is what tells this run's "blocked" from another session's."""
    seen: set[int] = set()
    for c in g.items(f"repos/{repo}/issues/{e.issue}/comments?since={iso(e.started)}&per_page=100"):
        if not mine(c, login) or not since_start(c, e.started):
            continue
        for m in re.findall(r"(?<![\w/])#(\d+)\b", c.get("body") or ""):
            n = int(m)
            if n == e.issue or n in seen:
                continue
            seen.add(n)
            it = g.get(f"repos/{repo}/issues/{n}") or {}
            if it.get("state") == "open" and "pull_request" not in it:
                return n
    return None


def closed_by(g: GitHub, repo: str, n: int) -> list[int]:
    return [p["number"] for p in g.closing_prs(repo, n)]


def missing_review(g: GitHub, repo: str, e: swarm.Started) -> str | None:
    login = swarm.dashboard().REVIEWER
    todo = []
    if e.pr:     # a run on one PR (Actions, #215): only that PR is its to review
        p = g.get(f"repos/{repo}/pulls/{e.pr}") or {}
        prs = [p] if p.get("state") == "open" and not p.get("draft") else []
    else:
        prs = [p for p in g.items(f"repos/{repo}/pulls?state=open&per_page=100")
               if not p.get("draft") and (ts(p.get("created_at")) or 0) <= e.started]
        # drafts, and PRs opened after the run started, weren't its to review
    for p in prs:
        head = (p.get("head") or {}).get("sha")
        reviews = [r for r in g.items(f"repos/{repo}/pulls/{p['number']}/reviews?per_page=100")
                   if mine(r, login)]
        if not any(r.get("commit_id") == head or since_start(r, e.started, "submitted_at")
                   for r in reviews):
            todo.append(f"#{p['number']}")
    if not todo:
        return None
    return (f"No review from you at the current head of PR {', '.join(todo)} yet. Review each "
            f"one as roles/reviewer.md says, then stop.")


def missing_respond(g: GitHub, repo: str, e: swarm.Started, login: str) -> str | None:
    p = g.get(f"repos/{repo}/pulls/{e.pr}") or {}
    if p.get("state") != "open":
        return None
    head = (p.get("head") or {}).get("sha")
    reviews = g.items(f"repos/{repo}/pulls/{e.pr}/reviews?per_page=100")
    if swarm.dashboard().reviewer_state(reviews, head)["at_head"] != CHANGES:
        return None          # pushed (new head), or nothing to respond to (roles/builder.md)
    since = iso(e.started)
    for path in (f"repos/{repo}/issues/{e.pr}/comments?since={since}&per_page=100",
                 f"repos/{repo}/pulls/{e.pr}/comments?since={since}&per_page=100"):
        if any(mine(c, login) and since_start(c, e.started) for c in g.items(path)):
            return None      # replied where it disagrees
    return (f"The reviewer's changes requested at PR #{e.pr}'s head are unanswered. Push a fix "
            f"to the PR's branch or reply on the PR where you disagree, as roles/builder.md "
            f"says, then stop.")


def missing(g: GitHub, repo: str, e: swarm.Started, owner: str) -> str | None:
    """What the run still has to do before it may stop, or None if it may stop."""
    login = app_login(e.role)
    if e.role == "reviewer":
        what = missing_review(g, repo, e)
    elif e.role == "builder" and e.pr:
        what = missing_respond(g, repo, e, login)
    elif e.role in ("builder", "docs") and e.issue:
        issue = g.get(f"repos/{repo}/issues/{e.issue}") or {}
        record = "gov:question" in labels_of(issue)
        if record and (e.role != "docs" or "gov:ruled" not in labels_of(issue)):
            return None      # an [answer] run: no condition
        if closed_by(g, repo, e.issue):
            return None      # opened its PR, or the work was already done
        events = g.items(f"repos/{repo}/issues/{e.issue}/events?per_page=100")
        if swarm.issue_refusals(e.issue, issue, events, owner, "gov:ruled" if record else "ready"):
            return None      # it was right to refuse the issue (GOV-0006)
        if blocked_on_prerequisite(g, repo, e, login):
            return None      # said on its issue which unfinished issue it waits for (#184)
        what = (f"No PR closes #{e.issue} yet. Open the {'record ' if record else ''}PR for "
                f"#{e.issue}, then stop. If an unfinished issue the work depends on blocks it, "
                f"comment on #{e.issue} naming that issue, and stop.")
    else:
        return None
    if what and blocked_on_question(g, repo, e, login):
        return None
    if what:
        ref = f" naming #{e.issue}" if e.issue else ""
        what += (f" If a gov:question blocks the work, open or comment on it{ref}, and stop "
                 f"work on that path.")
    return what


# ---------------------------------------------------------------- the hook

def log(home: Path, msg: str) -> None:
    try:
        with open(home / "launcher" / "stophook.log", "a") as f:
            f.write(f"{dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')} {msg}\n")
    except OSError:
        pass


def entry_for(home: Path, sid: str) -> swarm.Started | None:
    try:
        data = json.loads((home / "launcher" / "sessions.json").read_text())
    except (OSError, ValueError):
        return None
    for d in data:
        if d.get("session_id") == sid:
            return swarm.Started.from_dict(d)
    return None


def decide(payload: dict, home: Path, repo: str | None, g: GitHub,
           owner: Callable[[], str] = swarm.owner_login) -> dict | None:
    """The hook's output: {"decision": "block", "reason": ...}, or None to allow the stop."""
    if payload.get("stop_hook_active"):
        return None
    sid = str(payload.get("session_id") or "")
    e = entry_for(home, sid)
    if e is None or e.by not in HEADLESS or not repo:
        return None
    count_file = home / "launcher" / f"{sid}.stop.json"
    try:
        blocks = int(json.loads(count_file.read_text()).get("blocks", 0))
    except (OSError, ValueError, AttributeError):
        blocks = 0
    if blocks >= MAX_BLOCKS:
        return None
    try:
        reason = missing(g, repo, e, owner())
    except Exception as ex:   # noqa: BLE001 -- GitHub unreachable or odd data: allow the stop
        log(home, f"{sid}: allowing the stop, check failed: {ex!r}")
        return None
    if not reason:
        return None
    count_file.write_text(json.dumps({"blocks": blocks + 1}) + "\n")
    log(home, f"{sid}: blocked stop {blocks + 1} of {MAX_BLOCKS}: {reason}")
    return {"decision": "block", "reason": reason}


def main() -> int:
    home = swarm.home()
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        out = decide(payload, home, swarm.dashboard().default_repo(), live_github())
        if out:
            print(json.dumps(out))
    except Exception:   # noqa: BLE001 -- never fail closed
        log(home, traceback.format_exc().strip().replace("\n", " | "))
    return 0


if __name__ == "__main__":
    sys.exit(main())
