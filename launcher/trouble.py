"""`swarm trouble` (#803, stage 1 of #760): per open Goal and Area the owner opened, how its
done test stands, what is stuck, what waits on the owner, and what agents did on the
owner's authority. Spend is reported, never flagged (GOV-0033). Only reads GitHub; locally
it syncs swarm.db's owner acts, as `swarm acts` does.

    launcher/swarm trouble [--json] [--hours 24]

For each Goal and Area (GOV-0031):

- **Progress**, one entry per done-test criterion: a Goal's checkbox lines, an Area's
  `**Target:**` bullets. A ticked box is `met`. An unticked one is whatever its measure says
  (`met`, `progress` or `failing`), or `unmeasured` when no measure covers it: an
  unmeasured criterion is never reported as on track, and an Area is never "delivered".
  A `**Date:**` that has passed with the Goal still open is `date_missed`. The measures
  reuse the commands that count the same thing: M1's report streak from `swarm daily`,
  M2's merge share and unreviewed reverts this UTC week from `swarm merges`, and M4's
  acts from `swarm acts` (which first reads the owner's acts back from GitHub into
  swarm.db). A day `swarm acts` hasn't counted breaks M4's run like a failing one, and
  with no counted day M4's acts criterion is `unmeasured` (#844).
- **Stuck**: work nothing will start, with the reason and since when. Three rules, each from
  a real stall in #760's replays:
    1. `changes-no-restart`: the reviewer requested changes or found an overstep at a PR's
       head, there is no push since, and no trigger restarts the role: requested changes on
       a PR whose role [respond] doesn't start (#704); the owner answered the round bound,
       which [respond] won't pass; or the owner answered an overstep on a PR whose role
       [ruling] doesn't start (#679). An overstep is the reviewer's review at head with
       `Authority: fail`, whatever its state (it is usually COMMENTED). Which roles
       [respond] and [ruling] start is read from watch.py (RESPOND_ROLES, RULING_ROLES);
    2. `merged-issue-open`: a merged PR whose closing issue is still open (#760 replay 2);
    3. `waits-on-unplanned`: an open issue under no Goal or Area that another open issue
       waits on (`**Waits on:**` or a blocked-by link) (#786);
  plus a fourth signal, `unheard-command`: an owner `Ask:`, `Call in:` or `Research:` line
  nothing listens to (an `Ask:` off the report issue, a `Call in:` on a PR or on an issue
  that is neither `ready` nor under a Goal or Area, a switch that is off), while the issue
  or PR it is on is still open; and three from the owner's findings on #858:
    4. `conflict`: a PR approved at head (by the reviewer, and maybe the owner too) that
       conflicts with `main`. The merger can't merge it and no trigger starts a fix (PR #839);
    5. `quiet-session`: a hand-started session (not by `swarm watch`) that is still running
       but whose role's App has posted nothing on its issue, or its PR, for QUIET_MINUTES (#773);
    6. `stopped-no-issue`: the last word on an open issue is a role saying it stopped because
       the next piece it needs has no issue yet (NO_ISSUE_RE), with no open PR for the issue
       and no issue opened since that names it (#786).
- **Waiting on the owner**, with its age: untriaged issues, `gov:question`s not yet
  answered, PRs GOV-0011 hands to the owner (an overstep not yet answered, or answered
  and replied to by the role [ruling] started), and every PR the reviewer approved at
  head that the merger left for the owner, for whatever reason: the reason is the
  merger's own `Left for the owner at <head>: <reason>` comment, not re-derived here.
  Once the owner approves at head after that comment, the PR no longer waits on them.
- **On the owner's authority**, in the last --hours: merges by the merger App (GOV-0027;
  a PR it enqueued counts as its merge, as in `swarm merges`) and call-ins by a swarm App.
- **Spend**: the runs ledger's total under it (ledger.totals), reported only.

An item is filed under the Goal or Area above its issue (for a PR, the issue it closes);
items under none are in `outside`.

Limits: a `Call in:` asking for multi-step work gets one comment and can't be told apart
here; asks in the daily report and `decide` calls under jurisdictions.yml aren't read;
only M1's streak, M2's two criteria and M4's acts are measured, so other criteria read
`unmeasured` until one is added to MEASURES; a PR the merger hasn't judged at its head yet
isn't listed as left for the owner.
"""
from __future__ import annotations

import datetime as dt
import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable

import swarm

SCOPE_TYPES = ("Goal", "Area")
PLAN_TYPES = ("Mission", "Goal", "Area")
MERGER_APP = "productswarm-merger[bot]"
CHANGES = "CHANGES_REQUESTED"
COMMAND_DAYS = 7          # how far back owner commands are read for the fourth signal
MERGED_DAYS = 14          # how far back merged PRs are read for rule 2
HOURS = 24                # default window for "on the owner's authority"
QUIET_MINUTES = 60        # rule 5: a hand-started session silent this long is stuck (#858)
BUDGET_SECONDS = 20       # gather(): the acts backfill starts no read after this (#858)

CHECKBOX_RE = re.compile(r"^\s*[-*]\s*\[([ xX])\]\s*(\S.*?)\s*$", re.MULTILINE)
TARGET_RE = re.compile(r"^\s*\*\*Target:?\*\*:?[ \t]*(.*)$", re.MULTILINE)
BULLET_RE = re.compile(r"^\s*[-*]\s+(?!\[[ xX]\])(\S.*?)\s*$")
DATE_RE = re.compile(r"^\s*\*\*Date:?\*\*:?[ \t]*(\d{4}-\d{2}-\d{2})\b", re.MULTILINE)
APP_RE = re.compile(r"^(?:app/)?(productswarm-[a-z0-9-]+?)(?:\[bot\])?$")
# Rule 6: a role's stop comment saying the next piece has no issue (#786: "Stage 2 ... has no
# issue yet"; #858: "stage 2 isn't opened").
NO_ISSUE_RE = re.compile(r"\b(?:has|have|had|with) no issue\b|\bno issue (?:for it )?yet\b"
                         r"|\b(?:isn't|is not|hasn't been|has not been|not yet) opened\b", re.I)
ROLE_APP_RE = re.compile(r"^productswarm-([a-z]+)\[bot\]$")
NOT_ROLES = ("reviewer", "merger")     # Apps that comment but don't build


def rest_login(login: str | None) -> str:
    """REST's login: `gh pr list` shows an App as app/productswarm-x or productswarm-x."""
    m = APP_RE.match(login or "")
    return f"{m.group(1)}[bot]" if m else (login or "")


def when(s: str | None) -> dt.datetime | None:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


# ---------------------------------------------------------------- measures

@dataclass
class Data:
    """One reading of everything trouble needs. Plain data, so tests can build it."""
    repo: str
    owner: str
    now: dt.datetime
    issues: list[dict]                                   # open issues and PRs (REST items)
    scopes: dict[int, dict | None] = field(default_factory=dict)   # swarm.parse_scope() per issue
    other_scopes: dict[str, dict] = field(default_factory=dict)    # "o/r#n" -> REST item, other repos
    prs: list[dict] = field(default_factory=list)        # open PRs (gh pr list JSON)
    merged: list[dict] = field(default_factory=list)     # PRs merged in the last MERGED_DAYS
    comments: list[dict] = field(default_factory=list)   # repo comments, last COMMAND_DAYS (REST)
    report_issue: int | None = None
    switches: dict[str, bool] = field(default_factory=dict)   # asks, call_ins, research
    daily_streak: int | None = None                      # swarm daily's streak, None if unread
    week_merges: list[dict] | None = None                # swarm.gh_merged() this UTC week, None if unread
    owner_days: list[dict] | None = None                 # acts.per_day() for the last 11 working
                                                         # days (today may be in progress), newest
                                                         # first; None if unread
    spend: dict | None = None                            # ledger.totals(), None if unread
    sessions: list[dict] = field(default_factory=list)   # hand-started running sessions:
                                                         # {name, role, issue, pr, started (ISO)}
    hours: int = HOURS
    errors: list[str] = field(default_factory=list)


def daily_streak(m: re.Match, d: Data) -> tuple[str, str] | None:
    if d.daily_streak is None:
        return None
    need = int(m.group(1))
    return ("met" if d.daily_streak >= need else "progress",
            f"{d.daily_streak} of {need} working days (swarm daily)")


def this_week(d: Data) -> list[dict] | None:
    """This UTC week's merges, as `swarm merges` reads them, or None if unread."""
    if d.week_merges is None:
        return None
    start, end = swarm.week_of(d.now)
    return [p for p in d.week_merges if p.get("mergedAt") and start <= when(p["mergedAt"]) < end]


def merge_share(m: re.Match, d: Data) -> tuple[str, str] | None:
    """M2: over half of the week's merges without the owner's click (swarm.merged_by)."""
    week = this_week(d)
    if week is None:
        return None
    without = sum(swarm.merged_by(p, d.owner) != swarm.bare(d.owner) for p in week)
    return ("met" if without * 2 > len(week) else "progress",
            f"{without} of {len(week)} merges this week without the owner's click (swarm merges)")


def reviewed_reverts(m: re.Match, d: Data) -> tuple[str, str] | None:
    """M2: no unreviewed revert this week (swarm.reverted, swarm.reviewed_at_head)."""
    week = this_week(d)
    if week is None:
        return None
    reverts = [p for p in week if swarm.reverted(p) is not False]
    bad = [p["number"] for p in reverts if not swarm.reviewed_at_head(p, d.owner)]
    if bad:
        return "failing", (f"{len(bad)} unreviewed revert(s) this week: "
                           f"{', '.join(f'PR #{n}' for n in bad)} (swarm merges)")
    return "met", f"{len(reverts)} revert(s) this week so far, none unreviewed (swarm merges)"


def owner_acts(m: re.Match, d: Data) -> tuple[str, str] | None:
    """M4: working days in a row, newest first, that `swarm acts` counted with under
    acts.LIMIT owner acts and none 'other' (checks 1 and 2). Today, while in progress, is
    skipped; a day not counted breaks the run as a failing day does, and with no counted day
    the criterion is unmeasured (#844)."""
    import acts
    if d.owner_days is None:
        return None
    days = d.owner_days[1:] if d.owner_days and d.owner_days[0]["status"] == acts.IN_PROGRESS \
        else d.owner_days
    if not any(day["status"] == acts.COUNTED for day in days):
        return "unmeasured", "no working day counted yet (swarm acts)"
    need, run = int(m.group(1)), 0
    for day in days:
        if not (day["status"] == acts.COUNTED and day["under_limit"] and day["c_team"]):
            break
        run += 1
    missing = sum(day["status"] != acts.COUNTED for day in days[:need])
    return ("met" if run >= need else "progress",
            f"{run} of {need} working days in a row under {acts.LIMIT} acts, all C-team"
            + (f"; {missing} of the last {need} not counted" if missing else "") + " (swarm acts)")


# (pattern on the criterion's text, measure(match, data) -> (status, detail) or None if unread)
Measure = tuple[re.Pattern, Callable[[re.Match, Data], tuple[str, str] | None]]
DAILY_STREAK: Measure = (re.compile(r"\b(\d+) working days in a row with a daily report\b", re.I),
                         daily_streak)
MERGE_SHARE: Measure = (re.compile(r"\bover half of a week's merges\b.*\bwithout the owner's click\b",
                                   re.I), merge_share)
REVERTS: Measure = (re.compile(r"\bno unreviewed revert\b", re.I), reviewed_reverts)
OWNER_ACTS: Measure = (re.compile(r"\bacts are counted for each of the (\d+) working days\b", re.I),
                       owner_acts)
MEASURES: list[Measure] = [DAILY_STREAK, MERGE_SHARE, REVERTS, OWNER_ACTS]


def criteria(body: str | None, kind: str) -> list[tuple[str, bool]]:
    """(text, ticked) per done-test criterion: every checkbox line, and for an Area the bullets
    after its `**Target:**` line (or that line itself when no bullets follow)."""
    body = body or ""
    out = [(m.group(2), m.group(1) != " ") for m in CHECKBOX_RE.finditer(body)]
    if kind == "Area":
        t = TARGET_RE.search(body)
        if t:
            bullets = []
            for line in body[t.end():].lstrip("\n").splitlines():
                b = BULLET_RE.match(line)
                if not b:
                    break
                bullets.append((b.group(1), False))
            out += bullets or ([(t.group(1).strip(), False)] if t.group(1).strip() else [])
    return out


def progress(body: str | None, kind: str, d: Data,
             measures=None) -> list[dict]:
    out = []
    for text, ticked in criteria(body, kind):
        status, detail = ("met", "ticked") if ticked else ("unmeasured", "no measure yet")
        if not ticked:
            for pat, fn in (MEASURES if measures is None else measures):
                m = pat.search(text)
                got = fn(m, d) if m else None
                if got:
                    status, detail = got
                    break
        out.append({"criterion": text, "status": status, "detail": detail})
    return out


# ---------------------------------------------------------------- the report (pure)

def item(kind: str, ref: str, url: str | None, reason: str, since: str | dt.datetime | None,
         now: dt.datetime, **extra) -> dict:
    t = since if isinstance(since, dt.datetime) else when(since)
    return {"kind": kind, "ref": ref, "url": url, "reason": reason,
            "since": t.isoformat(timespec="seconds") if t else None,
            "age_hours": round((now - t).total_seconds() / 3600, 1) if t else None, **extra}


def merger_left(comments: list[dict], head: str | None) -> tuple[str, str] | None:
    """(when, reason) from the merger's latest verdict comment at head, if it is `Left for
    the owner at <head>: <reason>.` (merger.left_body); None if it is anything else (a merge,
    a "would merge") or there is none. comments are {login, at, body}, oldest first."""
    import merger
    if not head:
        return None
    verdicts = (merger.LEFT, merger.WOULD, merger.MERGED, merger.ENQUEUED)
    mine = [c for c in comments if c["login"] == merger.MERGER and f" at {head}" in c["body"]
            and c["body"].startswith(verdicts)]
    if not mine or not mine[-1]["body"].startswith(merger.LEFT):
        return None
    body = mine[-1]["body"].removesuffix(merger.SIGN).strip()
    reason = body.split(f" at {head}:", 1)[-1].strip().removesuffix(".")
    return mine[-1]["at"], reason


def report(d: Data, measures=None) -> dict:
    """The trouble report: {generated_at, repo, owner, scopes: [per Goal and Area], outside:
    the items under none, spend, errors}. Pure."""
    import generate   # swarm.dashboard() put it on the path
    repo, owner, now = d.repo, d.owner, d.now
    open_by_n = {it["number"]: it for it in d.issues}
    open_issues = {n for n, it in open_by_n.items() if "pull_request" not in it}
    since = now - dt.timedelta(hours=d.hours)

    def goal_of(n: int | None) -> str | None:
        g = swarm.scope_goal(d.scopes.get(n), owner) if n is not None else None
        return f"{g['repo'] or repo}#{g['number']}" if g else None

    def pr_goal(closes: list[int]) -> str | None:
        return next((g for g in map(goal_of, closes) if g), None)

    def ref(n: int, pr: bool = False) -> str:
        return f"PR #{n}" if pr else f"#{n}"

    def url(n: int) -> str:
        return f"https://github.com/{repo}/issues/{n}"

    scopes: dict[str, dict] = {}
    for it in d.issues:
        kind = (it.get("type") or {}).get("name")
        if ("pull_request" not in it and kind in SCOPE_TYPES
                and (it.get("user") or {}).get("login") == owner):
            scopes[f"{repo}#{it['number']}"] = {"repo": repo, **it}
    for key, it in d.other_scopes.items():
        if it.get("state") == "open" and (it.get("user") or {}).get("login") == owner:
            scopes.setdefault(key, {"repo": key.split("#")[0], **it})
    buckets = {k: {"stuck": [], "waiting": [], "authority": []} for k in scopes}
    outside = {"stuck": [], "waiting": [], "authority": []}

    def file(goal: str | None, section: str, x: dict) -> None:
        (buckets[goal] if goal in buckets else outside)[section].append(x)

    # Rule 1, and PRs waiting on the owner.
    import watch
    for p in d.prs:
        if p.get("isDraft"):
            continue
        n, author = p["number"], rest_login((p.get("author") or {}).get("login"))
        head = p.get("headRefOid")
        reviews = [{"user": {"login": rest_login((r.get("author") or {}).get("login"))},
                    "state": r.get("state"), "body": r.get("body"),
                    "commit_id": (r.get("commit") or {}).get("oid"), "at": r.get("submittedAt")}
                   for r in p.get("reviews") or []]
        comments = [{"login": rest_login((c.get("author") or {}).get("login")),
                     "at": c.get("createdAt"), "body": c.get("body") or ""}
                    for c in p.get("comments") or []]
        rv = generate.reviewer_state(reviews, head)
        closes = [c["number"] for c in p.get("closingIssuesReferences") or []]
        goal, pr_url = pr_goal(closes), p.get("url") or url(n)
        at_head = [r for r in reviews if r["user"]["login"] == generate.REVIEWER and r["commit_id"] == head]
        role = generate.pr_role(author)
        asked = at_head[-1]["at"] if at_head else None
        answered = sorted(t for t in [*(c["at"] for c in comments if c["login"] == owner),
                                      *(r["at"] for r in reviews if r["user"]["login"] == owner)]
                          if t and asked and t > asked)
        one = len(closes) == 1
        if rv["at_head"] is not None and rv["authority"] == "fail":
            # An overstep, whatever the review's state (#679's was COMMENTED). GOV-0011 hands it
            # to the owner; once the owner comments, [ruling] restarts the PR's role if it can.
            if not answered:
                file(goal, "waiting", item("pr", ref(n, True), pr_url, "overstep: needs the owner",
                                           asked, now))
            elif role not in watch.RULING_ROLES or not one:
                cant = (f"[ruling] restarts only {' and '.join(watch.RULING_ROLES)} PRs" if role not in
                        watch.RULING_ROLES else f"[ruling] skips a PR that closes {len(closes)} issues")
                file(goal, "stuck", item("changes-no-restart", ref(n, True), pr_url,
                                         f"overstep; @{owner} answered, and no trigger starts the "
                                         f"{role or 'author'} ({cant})", answered[0], now))
            else:
                replied = [c["at"] for c in comments
                           if c["login"] == f"productswarm-{role}[bot]" and c["at"] and c["at"] > answered[-1]]
                if replied:                              # [ruling] ran, and it asked back
                    file(goal, "waiting", item("pr", ref(n, True), pr_url,
                                               f"overstep: the {role} replied to @{owner}'s ruling "
                                               f"and changed nothing", replied[0], now))
        elif rv["at_head"] == CHANGES:
            if role in watch.RESPOND_ROLES and one and not generate.past_bound(rv["changes_requested"]):
                continue                                 # [respond] restarts it
            if role not in watch.RESPOND_ROLES:
                file(goal, "stuck", item("changes-no-restart", ref(n, True), pr_url,
                                         f"changes requested at {head[:7]}, no push since, and no "
                                         f"trigger restarts the {role or 'author'} ([respond] "
                                         f"restarts only {' and '.join(watch.RESPOND_ROLES)} PRs)",
                                         asked, now))
                continue
            why = (generate.needs_owner(rv, author)
                   or f"changes requested on a PR that closes {len(closes)} issues: needs the owner")
            if answered:
                file(goal, "stuck", item("changes-no-restart", ref(n, True), pr_url,
                                         f"{why.split(':')[0]}; @{owner} answered, and no trigger "
                                         f"starts the fix", answered[0], now))
            else:
                file(goal, "waiting", item("pr", ref(n, True), pr_url, why, asked, now))
        elif rv["at_head"] == "APPROVED":
            mine = [r for r in reviews if r["user"]["login"] == owner and r["commit_id"] == head
                    and r["state"] in ("APPROVED", CHANGES, "DISMISSED")]
            owner_ok = mine[-1]["at"] if mine and mine[-1]["state"] == "APPROVED" else None
            if p.get("mergeable") == "CONFLICTING":           # rule 4 (PR #839)
                by = f"the reviewer and @{owner}" if owner_ok else "the reviewer"
                file(goal, "stuck", item("conflict", ref(n, True), pr_url,
                                         f"approved at head by {by}, but it conflicts with main: "
                                         f"the merger can't merge it, and nothing will start a fix",
                                         owner_ok or asked, now))
                continue
            left = merger_left(comments, head)
            if left and not (owner_ok and owner_ok > left[0]):    # the owner approved since
                file(goal, "waiting", item("pr", ref(n, True), pr_url,
                                           f"approved at head; the merger left it for the owner: "
                                           f"{left[1]}", left[0], now))

    # Rule 2: merged, but its issue is still open.
    for p in d.merged:
        for c in p.get("closingIssuesReferences") or []:
            if c["number"] in open_issues:
                file(goal_of(c["number"]), "stuck", item(
                    "merged-issue-open", ref(c["number"]), url(c["number"]),
                    f"PR #{p['number']} merged, but #{c['number']} is still open", p.get("mergedAt"),
                    now, pr=p["number"]))

    # Rule 3: an issue under no Goal or Area that another issue waits on.
    seen: set[tuple[int, str | None]] = set()
    for a in sorted(open_issues):
        it = open_by_n[a]
        sc = d.scopes.get(a) or {}
        waits = set(watch.waits_on(it.get("body")))
        waits |= {b["number"] for b in sc.get("blocked_by") or [] if b.get("repo") in (None, repo)}
        for b in sorted(waits & open_issues):
            bt = open_by_n[b]
            labels = {lb.get("name") for lb in bt.get("labels") or []}
            if (goal_of(b) or (bt.get("type") or {}).get("name") in PLAN_TYPES
                    or "gov:question" in labels or (b, goal_of(a)) in seen):
                continue
            seen.add((b, goal_of(a)))
            file(goal_of(a), "stuck", item("waits-on-unplanned", ref(b), bt.get("html_url") or url(b),
                                           f"#{a} waits on it, and it sits under no Goal or Area, "
                                           f"so nothing starts it", bt.get("created_at"), now,
                                           waited_on_by=a))

    # Rule 5: a hand-started session gone quiet (#773). One whose work is over (its issue
    # closed or closed by a merged PR, its PR no longer open) is only an idle window.
    def closes(p: dict) -> list[int]:
        return [x["number"] for x in p.get("closingIssuesReferences") or []]
    open_prs = {p["number"] for p in d.prs}
    done = {n for p in d.merged for n in closes(p)}
    for s in d.sessions:
        app, issue, pr_n, started = (f"productswarm-{s['role']}[bot]", s.get("issue"), s.get("pr"),
                                     when(s["started"]))
        if (issue is not None and (issue not in open_issues or issue in done)) or \
                (pr_n is not None and pr_n not in open_prs):
            continue
        its_prs = {p["number"]: p for p in [*d.prs, *d.merged]
                   if p["number"] == pr_n or (issue is not None and issue in closes(p))}
        posts = [when(c.get("created_at")) for c in d.comments
                 if (c.get("user") or {}).get("login") == app
                 and (issue is None or watch.comment_issue(c) in {issue, *its_prs})]
        posts += [when(p.get("createdAt")) for p in its_prs.values()
                  if rest_login((p.get("author") or {}).get("login")) == app]
        last = max((t for t in posts if t and t >= started), default=None)
        quiet = last or started
        mins = int((now - quiet).total_seconds() // 60)
        if mins < QUIET_MINUTES:
            continue
        said = (f"last posted at {last:%Y-%m-%d %H:%M} UTC" if last
                else f"nothing since it started at {started:%Y-%m-%d %H:%M} UTC")
        file(goal_of(issue), "stuck", item(
            "quiet-session", ref(issue) if issue else s["name"], url(issue) if issue else None,
            f"hand-started {s['role']} session {s['name']} is still running but has posted nothing "
            f"for {mins} min ({said}; flagged after {QUIET_MINUTES} min)", quiet, now,
            session=s["name"]))

    # Rule 6: a role stopped because the next piece it needs has no issue yet (#786).
    pr_for = {x["number"] for p in d.prs for x in p.get("closingIssuesReferences") or []}
    last_word: dict[int, dict] = {}
    for c in d.comments:
        n = watch.comment_issue(c)
        if n in open_issues and (n not in last_word or c.get("created_at", "") >= last_word[n].get("created_at", "")):
            last_word[n] = c
    for n, c in sorted(last_word.items()):
        m = ROLE_APP_RE.match((c.get("user") or {}).get("login") or "")
        if not m or m.group(1) in NOT_ROLES or n in pr_for or not NO_ISSUE_RE.search(c.get("body") or ""):
            continue
        mention = re.compile(rf"(?<![\w/])#{n}\b")
        if any(it.get("created_at", "") > c.get("created_at", "") and mention.search(it.get("body") or "")
               for it in d.issues if it["number"] != n):
            continue                                     # an issue opened since names it
        file(goal_of(n), "stuck", item(
            "stopped-no-issue", ref(n), c.get("html_url") or url(n),
            f"the {m.group(1)} stopped: the next piece it needs has no issue yet, so nothing will "
            f"start it", c.get("created_at"), now))

    # Fourth signal: owner commands nothing listens to. Call-ins by Apps are authority used.
    agents_call = []
    for c in d.comments:
        login, n = (c.get("user") or {}).get("login") or "", watch.comment_issue(c)
        if n is None:
            continue
        is_pr = "/pull/" in str(c.get("html_url") or "")
        target = open_by_n.get(n)
        closes = ([x["number"] for p in d.prs if p["number"] == n
                   for x in p.get("closingIssuesReferences") or []] if is_pr else [])
        goal = pr_goal(closes) if is_pr else goal_of(n)
        body, at, curl = c.get("body"), c.get("created_at"), c.get("html_url") or url(n)
        call = watch.call_line(body)
        if login != owner:
            if call and login.endswith("[bot]") and (when(at) or now) >= since:
                agents_call.append((goal, item("call-in", ref(n, is_pr), curl,
                                               f"{login} called in {', '.join(call[0])}", at, now)))
            continue
        why = None
        if target is None:
            continue                                     # closed since: its work ended
        if watch.ask_line(body):
            why = ("`Ask:` is read only on the report issue" + (f" #{d.report_issue}" if d.report_issue else "")
                   if n != d.report_issue else
                   "asks are off in swarm.toml's [watch]" if not d.switches.get("asks") else None)
        elif call:
            labels = {lb.get("name") for lb in (target or {}).get("labels") or []}
            why = ("call-ins are off in swarm.toml's [watch]" if not d.switches.get("call_ins")
                   else "swarm watch reads `Call in:` on issues, not PRs" if is_pr
                   else f"#{n} is neither `ready` nor under a Goal or Area"
                   if "ready" not in labels and goal_of(n) is None else None)
        elif watch.research_line(body) is not None:
            labels = {lb.get("name") for lb in (target or {}).get("labels") or []}
            why = ("research is off in swarm.toml's [watch]" if not d.switches.get("research")
                   else "`Research:` isn't read on a PR" if is_pr
                   else "`Research:` isn't read on the report issue" if n == d.report_issue
                   else "`Research:` isn't read on a gov:question" if "gov:question" in labels else None)
        if why:
            file(goal, "stuck", item("unheard-command", ref(n, is_pr), curl,
                                     f"nothing listens: {why}", at, now))

    # Waiting on the owner: questions and untriaged issues.
    for n in sorted(open_issues):
        it = open_by_n[n]
        labels = {lb.get("name") for lb in it.get("labels") or []}
        kind = (it.get("type") or {}).get("name")
        if "gov:question" in labels:
            if not labels & {"ready", "gov:ruled"}:
                file(goal_of(n), "waiting", item("question", ref(n), it.get("html_url") or url(n),
                                                 "gov:question not answered", it.get("created_at"), now))
        elif (not labels and kind not in PLAN_TYPES and goal_of(n) is None and n != d.report_issue
              and (it.get("user") or {}).get("login") != owner and not generate.is_tracking(it)):
            file(None, "waiting", item("untriaged", ref(n), it.get("html_url") or url(n),
                                       "no label, and under no Goal or Area", it.get("created_at"), now))

    # On the owner's authority, in the window.
    for goal, x in agents_call:
        file(goal, "authority", x)
    for p in d.merged:
        at = when(p.get("mergedAt"))
        if not at or at < since:
            continue
        goal = pr_goal([c["number"] for c in p.get("closingIssuesReferences") or []])
        if swarm.merged_by(p, owner) == swarm.bare(MERGER_APP):
            file(goal, "authority", item("grant", ref(p["number"], True), p.get("url"),
                                         "merged by the merger under GOV-0027", at, now))

    spent = (d.spend or {}).get("spent") or {}
    out_scopes = []
    for key, it in sorted(scopes.items(), key=lambda kv: ((kv[1].get("type") or {}).get("name") or "", kv[0])):
        kind = (it.get("type") or {}).get("name")
        m = DATE_RE.search(it.get("body") or "")
        date = dt.date.fromisoformat(m.group(1)) if m else None
        for section in buckets[key].values():
            section.sort(key=lambda x: x["since"] or "")
        out_scopes.append({
            "ref": key, "type": kind, "title": it.get("title"), "url": it.get("html_url"),
            "date": date.isoformat() if date else None,
            "date_missed": bool(date and date < now.date()),
            "progress": progress(it.get("body"), kind, d, measures),
            **buckets[key],
            "spend_usd": None if d.spend is None else round(spent.get(key, 0.0), 2)})
    for section in outside.values():
        section.sort(key=lambda x: x["since"] or "")
    return {"generated_at": now.isoformat(timespec="seconds"), "repo": repo, "owner": owner,
            "authority_hours": d.hours, "scopes": out_scopes, "outside": outside,
            "spend": None if d.spend is None else {
                "today_usd": round(d.spend["today"], 2), "month_usd": round(d.spend["month"], 2),
                "unscoped_usd": round(d.spend["unscoped"], 2), "note": "reported only (GOV-0033)"},
            "errors": d.errors}


def text(r: dict) -> str:
    """The report for the terminal."""
    out = [f"Trouble for {r['repo']} at {r['generated_at']}:"]

    def items(head: str, xs: list[dict]) -> None:
        if xs:
            out.append(f"  {head}:")
            out.extend(f"    {x['ref']}  {x['reason']}"
                       + (f"  ({x['age_hours']}h)" if x["age_hours"] is not None else "") for x in xs)

    for s in r["scopes"]:
        date = f", date {s['date']}" + (" MISSED" if s["date_missed"] else "") if s["date"] else ""
        out.append(f"\n{s['type']} {s['ref']} {s['title']}{date}")
        for c in s["progress"]:
            out.append(f"  [{c['status']}] {c['criterion']} ({c['detail']})")
        items("stuck", s["stuck"])
        items("waiting on the owner", s["waiting"])
        items(f"on the owner's authority, last {r['authority_hours']}h", s["authority"])
        if s["spend_usd"] is not None:
            out.append(f"  spend: ${s['spend_usd']:,.2f} (reported only)")
    o = r["outside"]
    if any(o.values()):
        out.append("\nUnder no Goal or Area")
        items("stuck", o["stuck"])
        items("waiting on the owner", o["waiting"])
        items(f"on the owner's authority, last {r['authority_hours']}h", o["authority"])
    if r["spend"]:
        out.append(f"\nSpend today ${r['spend']['today_usd']:,.2f}, this month "
                   f"${r['spend']['month_usd']:,.2f} (reported only, GOV-0033)")
    out += [f"not read: {e}" for e in r["errors"]]
    return "\n".join(out)


# ---------------------------------------------------------------- reading

PR_FIELDS = ("number,title,url,author,isDraft,headRefOid,createdAt,reviews,comments,files,"
             "closingIssuesReferences,mergeable")
MERGED_FIELDS = ("number,title,url,author,body,createdAt,mergedAt,mergedBy,headRefOid,comments,"
                 "closingIssuesReferences")   # headRefOid and comments: swarm.merged_by


def hand_sessions(launcher) -> list[dict]:
    """Rule 5's sessions: the launcher's entries still running that `swarm watch` didn't start.
    Reads only (Launcher.running, not live, so nothing is tidied)."""
    out = []
    for e in launcher.running():
        if e.by == "watch" or launcher.state(e) != "running":
            continue
        started = dt.datetime.fromtimestamp(e.started, dt.timezone.utc)
        out.append({"name": e.name, "role": e.role, "issue": e.issue, "pr": e.pr,
                    "started": started.isoformat(timespec="seconds")})
    return out


def gather(launcher, repo: str, owner: str, manifest_path, hours: int = HOURS,
           now: dt.datetime | None = None) -> Data:
    """Read everything report() needs. Raises RuntimeError if GitHub can't be read; a local
    part that can't be read (the ledger, the daily streak) is left out and named in errors.

    The reads that don't depend on each other run at once (#858): one at a time, they took
    about 25 seconds. The acts backfill (acts.refresh) runs beside them and starts no read
    after BUDGET_SECONDS; what it hasn't read back yet, the next run (or `swarm acts`) does."""
    import acts
    import ledger
    import manifest
    import merger
    import watch
    g = swarm.dashboard()
    now = now or dt.datetime.now(dt.timezone.utc)
    deadline = time.monotonic() + BUDGET_SECONDS
    errors: list[str] = []
    try:
        limits = manifest.load_watch(manifest_path)
    except manifest.ManifestError as e:
        limits = None
        errors.append(f"swarm.toml: {e}")
    report_issue = limits.report_issue if limits else None
    today = now.astimezone().date()

    def streak():
        rows = swarm.daily_rows(swarm.working_days(today), watch.gh_comments(repo, report_issue),
                                watch.load_state(launcher)["acted"], report_issue,
                                swarm.agent_logins() | {owner})
        return swarm.daily_streak(rows, today)

    def owner_acts():
        return acts.refresh(launcher.dir, owner, (repo, report_issue) if report_issue else None, repo,
                            g.gh_json, g.gh_items, merger.is_protected,
                            swarm.working_days(today, swarm.DAILY_DAYS + 1), now, deadline=deadline)

    day = (now - dt.timedelta(days=MERGED_DAYS)).date()
    with ThreadPoolExecutor(8) as pool:
        jobs = {
            "issues": pool.submit(g.gh_items, f"repos/{repo}/issues?state=open&per_page=100"),
            "prs": pool.submit(g.gh_json, "pr", "list", "--repo", repo, "--state", "open", "--limit",
                               "200", "--json", PR_FIELDS),
            "merged": pool.submit(g.gh_json, "pr", "list", "--repo", repo, "--state", "merged",
                                  "--limit", "300", "--search", f"merged:>={day}", "--json", MERGED_FIELDS),
            "comments": pool.submit(watch.gh_recent_comments, repo, now - dt.timedelta(days=COMMAND_DAYS)),
            "week": pool.submit(swarm.gh_merged, repo, *swarm.week_of(now)),
            "acts": pool.submit(owner_acts),
            "streak": pool.submit(streak) if report_issue else None,
        }
        issues = jobs["issues"].result()
        prs = jobs["prs"].result() or []
        merged = jobs["merged"].result() or []
        numbers = {it["number"] for it in issues if "pull_request" not in it}
        numbers |= {c["number"] for p in [*prs, *merged] for c in p.get("closingIssuesReferences") or []}
        scopes = swarm.gh_scopes(repo, sorted(numbers)) if numbers else {}
        keys = sorted({f"{p['repo']}#{p['number']}" for sc in scopes.values() for p in (sc or {}).get("parents") or []
                       if p["repo"] not in (None, repo) and p["type"] in SCOPE_TYPES and p["state"] == "open"
                       and p["author"] == owner})
        got = list(pool.map(lambda k: g.gh_json("api", "repos/{}/issues/{}".format(*k.split("#"))) or {}, keys))
        other = dict(zip(keys, got))
        comments = jobs["comments"].result()
        streak_n = None
        if jobs["streak"]:
            try:
                streak_n = jobs["streak"].result()
            except RuntimeError as e:
                errors.append(f"daily streak: {e}")
        try:
            week_merges = jobs["week"].result()
        except RuntimeError as e:
            week_merges = None
            errors.append(f"swarm merges: {e}")
        owner_days = None
        try:
            owner_days, unread = jobs["acts"].result()
            errors.extend(f"swarm acts: not read yet: {e}" + (
                "; `launcher/swarm acts` has no time limit and reads it all" if acts.OUT_OF_TIME in e else "")
                for e in unread)
        except (OSError, sqlite3.Error) as e:
            errors.append(f"swarm acts: {e}")
    try:
        spend = ledger.totals(ledger.rows(launcher.dir), now)
    except (OSError, ValueError, sqlite3.Error) as e:
        spend = None
        errors.append(f"runs ledger: {e}")
    try:
        sessions = hand_sessions(launcher)
    except OSError as e:
        sessions = []
        errors.append(f"launcher sessions: {e}")
    switches = {k: bool(getattr(limits, k, False)) for k in ("asks", "call_ins", "research")}
    return Data(repo=repo, owner=owner, now=now, issues=issues, scopes=scopes, other_scopes=other,
                prs=prs, merged=merged, comments=comments, report_issue=report_issue,
                switches=switches, daily_streak=streak_n, week_merges=week_merges, owner_days=owner_days,
                spend=spend, hours=hours, errors=errors, sessions=sessions)
