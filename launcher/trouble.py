"""`swarm trouble` (#803, stage 1 of #760): per open Goal and Area the owner opened, how its
done test stands, what is stuck, what waits on the owner, and what agents did on the
owner's authority. Spend is reported, never flagged (GOV-0033). Only reads.

    launcher/swarm trouble [--json] [--hours 24]

For each Goal and Area (GOV-0031):

- **Progress**, one entry per done-test criterion: a Goal's checkbox lines, an Area's
  `**Target:**` bullets. A ticked box is `met`. An unticked one is whatever its measure says
  (`met`, `progress` or `failing`), or `unmeasured` when no measure covers it: an
  unmeasured criterion is never reported as on track, and an Area is never "delivered".
  A `**Date:**` that has passed with the Goal still open is `date_missed`.
- **Stuck**: work nothing will start, with the reason and since when. Three rules, each from
  a real stall in #760's replays:
    1. `changes-no-restart`: the reviewer requested changes at a PR's head, there is no push
       since, and no trigger restarts the role: a PR another role opened (#704), or the
       owner answered an overstep or the round bound and [respond] won't fire (#679);
    2. `merged-issue-open`: a merged PR whose closing issue is still open (#760 replay 2);
    3. `waits-on-unplanned`: an open issue under no Goal or Area that another open issue
       waits on (`**Waits on:**` or a blocked-by link) (#786);
  plus a fourth signal, `unheard-command`: an owner `Ask:`, `Call in:` or `Research:` line
  nothing listens to (an `Ask:` off the report issue, a `Call in:` on a PR or on an issue
  that is neither `ready` nor under a Goal or Area, a switch that is off), while the issue
  or PR it is on is still open.
- **Waiting on the owner**, with its age: untriaged issues, `gov:question`s not yet
  answered, PRs GOV-0011 hands to the owner, and protected-path PRs the reviewer approved
  that need the owner's approval at head (GOV-0027).
- **On the owner's authority**, in the last --hours: merges by the merger App (GOV-0027's
  standing grant), merged agent PRs that cite a ruling (`per GOV-NNNN`), and call-ins by a
  swarm App.
- **Spend**: the runs ledger's total under it (ledger.totals), reported only.

An item is filed under the Goal or Area above its issue (for a PR, the issue it closes);
items under none are in `outside`.

Limits: a `Call in:` asking for multi-step work gets one comment and can't be told apart
here; asks in the daily report and `decide` calls under jurisdictions.yml aren't read; only
the first measure (DAILY_STREAK, M1's report streak) exists, so most criteria read
`unmeasured` until one is added to MEASURES.
"""
from __future__ import annotations

import datetime as dt
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Callable

import swarm

SCOPE_TYPES = ("Goal", "Area")
PLAN_TYPES = ("Mission", "Goal", "Area")
MERGER_APP = "productswarm-merger[bot]"
BUILDER = "builder"
CHANGES = "CHANGES_REQUESTED"
COMMAND_DAYS = 7          # how far back owner commands are read for the fourth signal
MERGED_DAYS = 14          # how far back merged PRs are read for rule 2
HOURS = 24                # default window for "on the owner's authority"

CHECKBOX_RE = re.compile(r"^\s*[-*]\s*\[([ xX])\]\s*(\S.*?)\s*$", re.MULTILINE)
TARGET_RE = re.compile(r"^\s*\*\*Target:?\*\*:?[ \t]*(.*)$", re.MULTILINE)
BULLET_RE = re.compile(r"^\s*[-*]\s+(?!\[[ xX]\])(\S.*?)\s*$")
DATE_RE = re.compile(r"^\s*\*\*Date:?\*\*:?[ \t]*(\d{4}-\d{2}-\d{2})\b", re.MULTILINE)
RULING_RE = re.compile(r"\bper\s+(GOV-\d{4})\b", re.IGNORECASE)
APP_RE = re.compile(r"^(?:app/)?(productswarm-[a-z0-9-]+?)(?:\[bot\])?$")


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
    spend: dict | None = None                            # ledger.totals(), None if unread
    hours: int = HOURS
    errors: list[str] = field(default_factory=list)


def daily_streak(m: re.Match, d: Data) -> tuple[str, str] | None:
    if d.daily_streak is None:
        return None
    need = int(m.group(1))
    return ("met" if d.daily_streak >= need else "progress",
            f"{d.daily_streak} of {need} working days (swarm daily)")


# (pattern on the criterion's text, measure(match, data) -> (status, detail) or None if unread)
DAILY_STREAK = (re.compile(r"\b(\d+) working days in a row with a daily report\b", re.I), daily_streak)
MEASURES: list[tuple[re.Pattern, Callable[[re.Match, Data], tuple[str, str] | None]]] = [DAILY_STREAK]


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
    for p in d.prs:
        if p.get("isDraft"):
            continue
        n, author = p["number"], rest_login((p.get("author") or {}).get("login"))
        head = p.get("headRefOid")
        reviews = [{"user": {"login": rest_login((r.get("author") or {}).get("login"))},
                    "state": r.get("state"), "body": r.get("body"),
                    "commit_id": (r.get("commit") or {}).get("oid"), "at": r.get("submittedAt")}
                   for r in p.get("reviews") or []]
        rv = generate.reviewer_state(reviews, head)
        closes = [c["number"] for c in p.get("closingIssuesReferences") or []]
        goal, pr_url = pr_goal(closes), p.get("url") or url(n)
        at_head = [r for r in reviews if r["user"]["login"] == generate.REVIEWER and r["commit_id"] == head]
        if rv["at_head"] == CHANGES:
            asked = at_head[-1]["at"]
            role = generate.pr_role(author)
            why = generate.needs_owner(rv, author)
            if why is None:
                continue                                 # [respond] restarts the builder
            answered = sorted(t for t in [*(c.get("createdAt") for c in p.get("comments") or []
                                            if rest_login((c.get("author") or {}).get("login")) == owner),
                                          *(r["at"] for r in reviews if r["user"]["login"] == owner)]
                              if t and asked and t > asked)
            if role != BUILDER and rv["authority"] != "fail":
                file(goal, "stuck", item("changes-no-restart", ref(n, True), pr_url,
                                         f"changes requested at {head[:7]}, no push since, and no "
                                         f"trigger restarts the {role or 'author'} (GOV-0011 "
                                         f"restarts only the builder)", asked, now))
            elif answered:
                file(goal, "stuck", item("changes-no-restart", ref(n, True), pr_url,
                                         f"{why.split(':')[0]}; @{owner} answered, and no trigger "
                                         f"starts the fix", answered[0], now))
            else:
                file(goal, "waiting", item("pr", ref(n, True), pr_url, why, asked, now))
        elif rv["at_head"] == "APPROVED":
            import merger
            paths = [f.get("path") or "" for f in p.get("files") or []]
            owner_ok = any(r["user"]["login"] == owner and r["state"] == "APPROVED"
                           and r["commit_id"] == head for r in reviews)
            if any(merger.is_protected(x) for x in paths) and not owner_ok:
                file(goal, "waiting", item("pr", ref(n, True), pr_url,
                                           "touches a protected path: needs the owner's approval "
                                           "at head (GOV-0027)", at_head[-1]["at"], now))

    # Rule 2: merged, but its issue is still open.
    for p in d.merged:
        for c in p.get("closingIssuesReferences") or []:
            if c["number"] in open_issues:
                file(goal_of(c["number"]), "stuck", item(
                    "merged-issue-open", ref(c["number"]), url(c["number"]),
                    f"PR #{p['number']} merged, but #{c['number']} is still open", p.get("mergedAt"),
                    now, pr=p["number"]))

    # Rule 3: an issue under no Goal or Area that another issue waits on.
    import watch
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
        by = rest_login((p.get("mergedBy") or {}).get("login"))
        author = rest_login((p.get("author") or {}).get("login"))
        rulings = sorted(set(g.upper() for g in RULING_RE.findall(p.get("body") or "")))
        if by == MERGER_APP:
            file(goal, "authority", item("grant", ref(p["number"], True), p.get("url"),
                                         "merged by the merger under GOV-0027's standing grant", at, now))
        if rulings and author.endswith("[bot]"):
            file(goal, "authority", item("ruling", ref(p["number"], True), p.get("url"),
                                         f"{author} acted under {', '.join(rulings)}", at, now))

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
             "closingIssuesReferences")
MERGED_FIELDS = "number,title,url,author,body,mergedAt,mergedBy,closingIssuesReferences"


def gather(launcher, repo: str, owner: str, manifest_path, hours: int = HOURS,
           now: dt.datetime | None = None) -> Data:
    """Read everything report() needs. Raises RuntimeError if GitHub can't be read; a local
    part that can't be read (the ledger, the daily streak) is left out and named in errors."""
    import ledger
    import manifest
    import watch
    g = swarm.dashboard()
    now = now or dt.datetime.now(dt.timezone.utc)
    errors: list[str] = []
    try:
        limits = manifest.load_watch(manifest_path)
    except manifest.ManifestError as e:
        limits = None
        errors.append(f"swarm.toml: {e}")
    issues = g.gh_items(f"repos/{repo}/issues?state=open&per_page=100")
    prs = g.gh_json("pr", "list", "--repo", repo, "--state", "open", "--limit", "200",
                    "--json", PR_FIELDS) or []
    day = (now - dt.timedelta(days=MERGED_DAYS)).date()
    merged = g.gh_json("pr", "list", "--repo", repo, "--state", "merged", "--limit", "300",
                       "--search", f"merged:>={day}", "--json", MERGED_FIELDS) or []
    comments = watch.gh_recent_comments(repo, now - dt.timedelta(days=COMMAND_DAYS))
    numbers = {it["number"] for it in issues if "pull_request" not in it}
    numbers |= {c["number"] for p in [*prs, *merged] for c in p.get("closingIssuesReferences") or []}
    scopes = swarm.gh_scopes(repo, sorted(numbers)) if numbers else {}
    other: dict[str, dict] = {}
    for sc in scopes.values():
        for p in (sc or {}).get("parents") or []:
            key = f"{p['repo']}#{p['number']}"
            if (p["repo"] not in (None, repo) and p["type"] in SCOPE_TYPES and p["state"] == "open"
                    and p["author"] == owner and key not in other):
                other[key] = g.gh_json("api", f"repos/{p['repo']}/issues/{p['number']}") or {}
    report_issue = limits.report_issue if limits else None
    streak = None
    if report_issue:
        try:
            today = now.astimezone().date()
            rows = swarm.daily_rows(swarm.working_days(today), watch.gh_comments(repo, report_issue),
                                    watch.load_state(launcher)["acted"], report_issue,
                                    swarm.agent_logins() | {owner})
            streak = swarm.daily_streak(rows, today)
        except RuntimeError as e:
            errors.append(f"daily streak: {e}")
    try:
        spend = ledger.totals(ledger.rows(launcher.dir), now)
    except (OSError, ValueError, sqlite3.Error) as e:
        spend = None
        errors.append(f"runs ledger: {e}")
    switches = {k: bool(getattr(limits, k, False)) for k in ("asks", "call_ins", "research")}
    return Data(repo=repo, owner=owner, now=now, issues=issues, scopes=scopes, other_scopes=other,
                prs=prs, merged=merged, comments=comments, report_issue=report_issue,
                switches=switches, daily_streak=streak, spend=spend, hours=hours, errors=errors)
