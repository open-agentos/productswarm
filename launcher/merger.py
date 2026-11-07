"""The merger (GOV-0022, GOV-0027): for each open PR, merge or miss under GOV-0027's
standing grants and approved asks, with GOV-0022's other conditions kept.

    python3 launcher/merger.py plan [--pr N] [--manifest PATH] [--repo OWNER/NAME]
    python3 launcher/merger.py run [--dry-run] [--pr N] [--manifest PATH] [--repo OWNER/NAME]

A reconciler in the shape of actions_review.py's `plan` (GOV-0020): it reads repo state
from GitHub and the checkout of main it runs from, and reads PRs as data, never PR text as
instructions. `plan` (#589) writes nothing to GitHub. `run` (#592) runs plan, then acts per
[merger] mode:

- shadow: on a merge, post `Would merge (<kind>) at <sha>.` once per head. On a miss for a
  PR the reviewer or the owner approved at head, post `Left for the owner at <sha>: <reason>.`
  once per head (not while `tests` is still running). Other misses post nothing.
- live: merge with the head SHA pinned, then post `Merged under <kind> (GOV-0027) at <sha>.`
  Until GOV-0027's shadow bar is met ("would merge" by the merger App on SHADOW_PRS
  distinct PRs, or a day since the first), live acts as shadow and says so in the log.
- off: nothing.

Every comment ends `-- merger`. `--dry-run` prints each comment or merge instead of making
it. The token is $GH_TOKEN (the merger App's, minted by the workflow, GOV-0028); this code
holds no credentials and never runs Claude.

It prints one line per open PR: `#N <head sha> merge (standing grant)`, `... merge
(approved ask)` or `... miss: <first failed condition>`. Draft PRs, fork heads and closed
PRs are skipped, each with a `skip:` line. A PR is judged as a standing grant unless it
touches a protected path; then it is judged as an approved ask.

Standing grant (GOV-0027, GOV-0022), in the order checked:

- the author is productswarm-builder[bot], and the base is main;
- it closes exactly one issue in this repo, and that issue is go by its milestone
  (swarm.milestone_refusal, GOV-0026, #582). The owner's `ready` alone doesn't count: the
  record says "under an approved milestone". A gov:question never counts;
- the reviewer approved at the current head, and no one's latest review requests changes;
- no `Overstep:` line in any PR comment, review or review comment;
- the `tests` check (from GitHub Actions) passed at the current head;
- it touches no protected path (PROTECTED, GOV-0022's list);
- additions plus deletions are at most [merger] max_changed_lines.

Approved ask (GOV-0027), for a PR that touches a protected path:

- it touches none of GOVERNANCE.md, governance/jurisdictions.yml or .github/workflows/
  (EXCLUDED: the owner merges those);
- the author is a swarm App (identities.agents), and the base is main;
- the owner (humans.owner) approved at the current head, and no one's latest review
  requests changes;
- no `Overstep:` line, and the `tests` check passed at the current head.

The record states only the owner's approval at head for asks; the other conditions are a
stricter reading that fails closed (docs' note 2 on #585).

The switch is swarm.toml's [merger] table: `mode` (`off`, `shadow` or `live`) and
`max_changed_lines` (a whole number of at least 1). If either is missing or bad, the merger
is off and every PR is a miss with that reason. swarm.toml is the owner's; this only reads it.

Exit 0 when it decided (even if nothing merges). If GitHub or a file can't be read, every
PR is a miss and it exits 1.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import actions_review  # noqa: E402  (eligible(), head_sha(), trusted_authors())
import swarm  # noqa: E402  (milestone_refusal(), GOV-0026)
import watch  # noqa: E402

BUILDER = "productswarm-builder[bot]"
REVIEWER = watch.REVIEWER
BASE = "main"
TESTS = "tests"                  # .github/workflows/tests.yml's job (#521)
TESTS_APP = "github-actions"     # the only App whose `tests` check counts
APPROVED, CHANGES, DISMISSED = "APPROVED", "CHANGES_REQUESTED", "DISMISSED"
MODES = ("off", "shadow", "live")
GRANT, ASK = "merge (standing grant)", "merge (approved ask)"

# GOV-0022's protected paths. CLAUDE.md counts anywhere, since a nested one also instructs agents.
# PLAN.md is protected until it is deleted: an agent PR adding a milestone there would make its own
# issues go under GOV-0026 (operating model v2).
PROTECTED_DIRS = ("ops/", ".github/", "governance/", "roles/")
PROTECTED_FILES = ("GOVERNANCE.md", "CLAUDE.md", "swarm.toml", "PLAN.md")
DEPENDENCY_FILES = frozenset({
    "requirements.txt", "requirements-dev.txt", "constraints.txt", "pyproject.toml", "setup.py",
    "setup.cfg", "Pipfile", "Pipfile.lock", "poetry.lock", "uv.lock", "package.json",
    "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "Gemfile",
    "Gemfile.lock", "go.mod", "go.sum", "Cargo.toml", "Cargo.lock"})
DEPENDENCY_RE = re.compile(r"requirements[\w.-]*\.(txt|in)")
# GOV-0027: an approved ask never covers these; the owner merges them.
EXCLUDED_FILES = ("GOVERNANCE.md", "governance/jurisdictions.yml")
EXCLUDED_DIRS = (".github/workflows/",)

OVERSTEP_RE = re.compile(r"^[\s>*_-]*Overstep\s*:", re.IGNORECASE | re.MULTILINE)
SAFE_PATH_RE = re.compile(r"[\w./@+-]+")


# ---------------------------------------------------------------- the switch

@dataclass(frozen=True)
class Switch:
    mode: str                     # off, shadow or live
    max_changed_lines: int | None
    why_off: str | None = None    # why the merger is off, when it is


def load_switch(path: Path | str) -> Switch:
    """[merger] from swarm.toml. A missing or bad table or key means off, with the reason.
    Raises OSError or ValueError if the file itself can't be read or isn't TOML."""
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    t = data.get("merger")
    if t is None:
        return Switch("off", None, "swarm.toml has no [merger] table")
    if not isinstance(t, dict):
        return Switch("off", None, "swarm.toml's merger isn't a table")
    mode, cap = t.get("mode"), t.get("max_changed_lines")
    if mode not in MODES:
        return Switch("off", None, f"[merger] mode must be one of {', '.join(MODES)}")
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 1:
        return Switch("off", None, "[merger] max_changed_lines must be a whole number of at least 1")
    if mode == "off":
        return Switch("off", cap, "[merger] mode is off")
    return Switch(mode, cap)


# ---------------------------------------------------------------- paths

def is_protected(path: str) -> bool:
    name = path.rsplit("/", 1)[-1]
    return (path.startswith(PROTECTED_DIRS) or path in PROTECTED_FILES or name == "CLAUDE.md"
            or name in DEPENDENCY_FILES or bool(DEPENDENCY_RE.fullmatch(name)))


def is_excluded(path: str) -> bool:
    return path in EXCLUDED_FILES or path.startswith(EXCLUDED_DIRS)


def paths_of(files: list[dict]) -> list[str]:
    """Every path a PR touches: each file's name, and its old name if renamed."""
    out = []
    for f in files:
        for key in ("filename", "previous_filename"):
            p = f.get(key) if isinstance(f, dict) else None
            if isinstance(p, str) and p:
                out.append(p)
    return out


def show(path: str) -> str:
    """A path for the log: as is if it's plain, else a placeholder (paths are PR data)."""
    return f"`{path}`" if SAFE_PATH_RE.fullmatch(path) and len(path) <= 200 else "a path with unusual characters"


# ---------------------------------------------------------------- reviews and checks

def login(x: dict) -> str:
    return ((x or {}).get("user") or {}).get("login") or ""


def approved_at_head(reviews: list[dict], who: str, head: str) -> bool:
    """Whether who's latest approve-or-request-changes review at head is an approval
    (a dismissed approval shows as DISMISSED and doesn't count)."""
    mine = [r for r in reviews if login(r) == who and r.get("commit_id") == head
            and r.get("state") in (APPROVED, CHANGES, DISMISSED)]
    return bool(mine) and mine[-1].get("state") == APPROVED


def changes_requested_by(reviews: list[dict]) -> list[str]:
    """Logins whose latest decisive review (REST order, oldest first) requests changes:
    a later comment doesn't clear a request, as on GitHub."""
    latest: dict[str, str] = {}
    for r in reviews:
        if r.get("state") in (APPROVED, CHANGES, DISMISSED) and login(r):
            latest[login(r)] = r["state"]
    return sorted(who for who, state in latest.items() if state == CHANGES)


def has_overstep(*bodies_lists: list[dict]) -> bool:
    return any(OVERSTEP_RE.search(x.get("body") or "") for xs in bodies_lists for x in xs
               if isinstance(x, dict))


def tests_passed(check_runs: list[dict]) -> str | None:
    """None if the newest `tests` check run from GitHub Actions succeeded, else why not."""
    runs = [c for c in check_runs if isinstance(c, dict) and c.get("name") == TESTS
            and ((c.get("app") or {}).get("slug") == TESTS_APP)]
    if not runs:
        return f"no `{TESTS}` check at the head"
    newest = max(runs, key=lambda c: c.get("id") or 0)
    if newest.get("status") != "completed":
        return f"the `{TESTS}` check at the head hasn't finished"
    if newest.get("conclusion") != "success":
        return f"the `{TESTS}` check at the head concluded {newest.get('conclusion')}"
    return None


# ---------------------------------------------------------------- the decision

@dataclass
class Reader:
    """Everything the decision reads from GitHub, one PR or issue at a time. Tests pass
    canned functions; live() reads with `gh`."""
    pr: Callable[[int], dict]                   # one PR (REST: additions, deletions, base, head)
    files: Callable[[int], list[dict]]          # the PR's changed files
    reviews: Callable[[int], list[dict]]
    comments: Callable[[int], list[dict]]       # the PR's conversation comments
    review_comments: Callable[[int], list[dict]]
    checks: Callable[[str], list[dict]]         # check runs at a commit
    closes: Callable[[int], list[tuple[str, int]]]  # (repo, number) of each issue the PR closes
    issue: Callable[[int], dict]
    go_reader: Callable[[int], "swarm.GoReader"]


@dataclass(frozen=True)
class Context:
    repo: str
    owner: str                    # humans.owner's login, without the @
    agents: frozenset[str]        # identities.agents
    switch: Switch


def common(n: int, head: str, who: str, r: Reader) -> str | None:
    """Conditions both kinds share once the approver is known: who approved at head, no
    open request for changes, no Overstep:, tests passed at head."""
    reviews = r.reviews(n)
    if not approved_at_head(reviews, who, head):
        return f"{who} hasn't approved at head {head[:7]}"
    asking = changes_requested_by(reviews)
    if asking:
        return f"changes requested by {', '.join(asking)}"
    if has_overstep(r.comments(n), reviews, r.review_comments(n)):
        return "an `Overstep:` finding is on the PR"
    return tests_passed(r.checks(head))


def grant_issue(n: int, ctx: Context, r: Reader) -> str | None:
    """Why PR n's issue doesn't make it a standing grant, or None: exactly one closing
    issue in this repo, open, not a gov:question, go by its milestone (GOV-0026)."""
    closes = r.closes(n)
    if len(closes) != 1:
        return f"it closes {len(closes)} issues, not exactly one"
    repo, k = closes[0]
    if repo != ctx.repo:
        return "the issue it closes is in another repo"
    issue = r.issue(k)
    if not isinstance(issue, dict) or issue.get("state") != "open" or "pull_request" in issue:
        return f"#{k} isn't an open issue"
    if "gov:question" in {lb.get("name") for lb in issue.get("labels") or []}:
        return f"#{k} is a gov:question, not under a milestone"
    why = swarm.milestone_refusal(k, issue, ctx.owner, set(ctx.agents), r.go_reader(k))
    return f"not under an approved milestone: {why}" if why else None


def decide(pr: dict, ctx: Context, r: Reader) -> str:
    """GRANT, ASK, or `miss: <first failed condition>` for one eligible open PR (full REST
    object). Reads only what it needs, in the order the conditions are listed."""
    if ctx.switch.why_off:
        return f"miss: the merger is off ({ctx.switch.why_off})"
    n, head, author = pr["number"], actions_review.head_sha(pr), login(pr)
    if ((pr.get("base") or {}).get("ref")) != BASE:
        return f"miss: its base isn't {BASE}"
    files = r.files(n)
    changed = pr.get("changed_files")
    if not isinstance(changed, int) or len(files) < changed:
        return "miss: can't see every changed file"
    paths = paths_of(files)
    protected = [p for p in paths if is_protected(p)]
    if protected:      # an approved ask, or nothing
        excluded = [p for p in paths if is_excluded(p)]
        if excluded:
            return f"miss: approved ask: touches {show(excluded[0])}, which the owner merges (GOV-0027)"
        if author not in ctx.agents:
            return "miss: approved ask: not opened by a swarm App"
        why = common(n, head, ctx.owner, r)
        return f"miss: approved ask: touches {show(protected[0])}, and {why}" if why else ASK
    if author != BUILDER:
        return f"miss: not opened by {BUILDER}"
    why = grant_issue(n, ctx, r) or common(n, head, REVIEWER, r)
    if why:
        return f"miss: {why}"
    size = pr.get("additions"), pr.get("deletions")
    if not all(isinstance(x, int) for x in size):
        return "miss: can't read its size"
    if sum(size) > ctx.switch.max_changed_lines:
        return (f"miss: {sum(size)} changed lines, over [merger] max_changed_lines "
                f"{ctx.switch.max_changed_lines}")
    return GRANT


@dataclass(frozen=True)
class Decision:
    number: int
    head: str          # "-" if unknown
    verdict: str       # GRANT, ASK, "miss: ..." or "skip: ..."

    @property
    def merges(self) -> bool:
        return self.verdict in (GRANT, ASK)

    def line(self) -> str:
        return f"#{self.number} {self.head} {self.verdict}"


def make_decisions(prs: list[dict], ctx: Context, r: Reader) -> list[Decision]:
    """One decision per PR considered, lowest number first. Skips drafts, forks and closed
    PRs; an author outside the swarm Apps and the owner is a miss, not a skip."""
    out = []
    def number(p):
        n = p.get("number")
        return n if isinstance(n, int) and not isinstance(n, bool) else 0
    for listed in sorted((p for p in prs if isinstance(p, dict)), key=number):
        n = number(listed)
        if not n:
            continue
        pr = r.pr(n)
        sha = actions_review.head_sha(pr) or "-"
        if pr.get("state") != "open" or pr.get("draft") or \
                ((pr.get("head") or {}).get("repo") or {}).get("full_name") != ctx.repo:
            why = ("closed" if pr.get("state") != "open" else "a draft" if pr.get("draft")
                   else "its head isn't in this repo")
            out.append(Decision(n, sha, f"skip: {why}"))
            continue
        ok, _, why = actions_review.eligible(pr, ctx.repo, ctx.owner, ctx.agents)
        out.append(Decision(n, sha, decide(pr, ctx, r) if ok else "miss: " + why))
    return out


def make_plan(prs: list[dict], ctx: Context, r: Reader) -> list[str]:
    """make_decisions() as plan's lines."""
    return [d.line() for d in make_decisions(prs, ctx, r)]


# ---------------------------------------------------------------- reading GitHub

def live(repo: str) -> Reader:
    g = swarm.dashboard()

    def closes(n):
        d = g.gh_json("pr", "view", str(n), "--repo", repo, "--json", "closingIssuesReferences")
        out = []
        for c in (d or {}).get("closingIssuesReferences") or []:
            rep = c.get("repository") or {}
            out.append((f"{(rep.get('owner') or {}).get('login')}/{rep.get('name')}", c.get("number")))
        return out

    return Reader(
        pr=lambda n: g.gh_json("api", f"repos/{repo}/pulls/{n}"),
        files=lambda n: g.gh_items(f"repos/{repo}/pulls/{n}/files?per_page=100"),
        reviews=lambda n: g.gh_items(f"repos/{repo}/pulls/{n}/reviews?per_page=100"),
        comments=lambda n: g.gh_items(f"repos/{repo}/issues/{n}/comments?per_page=100"),
        review_comments=lambda n: g.gh_items(f"repos/{repo}/pulls/{n}/comments?per_page=100"),
        checks=lambda sha: g.gh_items(f"repos/{repo}/commits/{sha}/check-runs?check_name={TESTS}"
                                      "&per_page=100", ".check_runs[]"),
        closes=closes,
        issue=lambda k: g.gh_json("api", f"repos/{repo}/issues/{k}"),
        go_reader=lambda k: swarm.gh_go_reader(repo, k))


def decide_all(repo: str, pr: int | None, manifest_path: Path | str | None, r: Reader,
               owner: Callable[[], str], authors: Callable[[], tuple[frozenset[str], str | None]],
               list_prs: Callable[[], list[dict]]) -> tuple[Context, list[Decision]]:
    """plan's reads and decisions. Raises one of UNREADABLE if it can't decide."""
    switch = load_switch(manifest_path or swarm.ROOT / "swarm.toml")
    apps, why_none = authors()
    if why_none:
        raise ValueError(why_none)
    ctx = Context(repo, owner(), apps, switch)
    prs = [{"number": pr}] if pr is not None else list_prs()
    if not isinstance(prs, list):
        raise ValueError("the PR list is not a list")
    return ctx, make_decisions(prs, ctx, r)


UNREADABLE = (KeyError, TypeError, OSError, ValueError, RuntimeError, subprocess.SubprocessError)


def default_list_prs(repo: str) -> Callable[[], list[dict]]:
    return lambda: swarm.dashboard().gh_items(f"repos/{repo}/pulls?state=open&per_page=100")


def plan(repo: str, pr: int | None = None, manifest_path: Path | str | None = None,
         reader: Reader | None = None, owner: Callable[[], str] = swarm.owner_login,
         authors: Callable[[], tuple[frozenset[str], str | None]] = actions_review.trusted_authors,
         list_prs: Callable[[], list[dict]] | None = None,
         out: Callable[[str], None] = print) -> int:
    """Print merge or miss for each open PR (or only PR pr). 0 decided, 1 couldn't."""
    r = reader or live(repo)
    try:
        ctx, decisions = decide_all(repo, pr, manifest_path, r, owner, authors,
                                    list_prs or default_list_prs(repo))
    except UNREADABLE as e:
        out(f"merger: can't decide ({e.__class__.__name__}): every PR is a miss")
        return 1
    for d in decisions:
        out(d.line())
    merging = sum(d.merges for d in decisions)
    out(f"merger: mode {ctx.switch.mode}: {merging} PR(s) would merge" +
        (f" (--pr {pr})" if pr is not None else ""))
    return 0


# ---------------------------------------------------------------- run: comments and merges (#592)

MERGER = "productswarm-merger[bot]"   # the App whose comments count (GOV-0022, GOV-0028)
SIGN = "\n\n-- merger"
WOULD, MERGED, LEFT = "Would merge", "Merged under", "Left for the owner"
SHADOW_PRS = 10                       # GOV-0027: "would merge" on 10 PRs ...
SHADOW_SECONDS = 24 * 3600            # ... or a day since the first, whichever comes first


def kind(verdict: str) -> str:
    return "standing grant" if verdict == GRANT else "approved ask"


def would_body(d: Decision) -> str:
    return f"{WOULD} ({kind(d.verdict)}) at {d.head}.{SIGN}"


def merged_body(d: Decision) -> str:
    return f"{MERGED} {kind(d.verdict)} (GOV-0027) at {d.head}.{SIGN}"


def left_body(d: Decision) -> str:
    return f"{LEFT} at {d.head}: {d.verdict.removeprefix('miss: ')}.{SIGN}"


def posted(comments: list[dict], prefix: str, head: str) -> bool:
    """Whether the merger App already posted a `prefix` comment for this head."""
    return any(login(c) == MERGER and (c.get("body") or "").startswith(prefix)
               and f" at {head}" in (c.get("body") or "") for c in comments if isinstance(c, dict))


def shadow_bar(comments: list[dict], now: float) -> str | None:
    """None once GOV-0027's shadow is over ("would merge" by the merger App on SHADOW_PRS
    distinct PRs, or SHADOW_SECONDS since the first), else why live is still held back.
    A PR counts once however many heads it was posted for; a comment without an
    issue_url names no PR, so it doesn't count towards the PRs (it still dates the first)."""
    mine = [c for c in comments if isinstance(c, dict) and login(c) == MERGER
            and (c.get("body") or "").startswith(WOULD)]
    prs = {u for c in mine if isinstance(u := c.get("issue_url"), str) and u}
    times = sorted(t for c in mine if (t := actions_review.iso_time(c.get("created_at"))) is not None)
    if len(prs) >= SHADOW_PRS or (times and now - times[0] >= SHADOW_SECONDS):
        return None
    since = f", the first at {actions_review.utc(times[0])}" if times else ""
    return (f"the shadow bar isn't met ({len(prs)} of {SHADOW_PRS} PRs with a \"would merge\" "
            f"comment{since}; or a day since the first)")


def worth_telling(d: Decision, reviews: list[dict], owner: str) -> bool:
    """A miss is posted only on a PR the reviewer or the owner approved at head (GOV-0022:
    the owner sees why it's left to them), and not while `tests` is still running."""
    if not d.verdict.startswith("miss: ") or "hasn't finished" in d.verdict:
        return False
    return approved_at_head(reviews, REVIEWER, d.head) or approved_at_head(reviews, owner, d.head)


@dataclass
class Writer:
    """What run writes to GitHub, and the repo-wide comment list the shadow bar counts.
    Tests pass canned functions; gh_writer() uses `gh` with $GH_TOKEN."""
    history: Callable[[], list[dict]]          # every issue and PR comment in the repo
    post: Callable[[int, str], None]           # comment on PR n
    merge: Callable[[int, str], None]          # merge PR n only if its head is still sha


def gh_writer(repo: str) -> Writer:
    g = swarm.dashboard()

    def gh(*args: str) -> None:
        r = subprocess.run(["gh", "api", *args], capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError(f"gh api {args[0]} failed: {r.stderr.strip()[:300]}")

    return Writer(
        history=lambda: g.gh_items(f"repos/{repo}/issues/comments?per_page=100"),
        post=lambda n, body: gh(f"repos/{repo}/issues/{n}/comments", "-f", f"body={body}"),
        # sha pins the merge to the head the decision saw: GitHub refuses it if the head moved.
        merge=lambda n, sha: gh("-X", "PUT", f"repos/{repo}/pulls/{n}/merge",
                                "-f", f"sha={sha}", "-f", "merge_method=merge"))


def run(repo: str, dry_run: bool = False, pr: int | None = None,
        manifest_path: Path | str | None = None, reader: Reader | None = None,
        writer: Writer | None = None, owner: Callable[[], str] = swarm.owner_login,
        authors: Callable[[], tuple[frozenset[str], str | None]] = actions_review.trusted_authors,
        list_prs: Callable[[], list[dict]] | None = None, clock: Callable[[], float] = time.time,
        out: Callable[[str], None] = print) -> int:
    """plan, then act on each decision per [merger] mode. 0 done, 1 couldn't decide or a
    write failed. --dry-run prints each write instead of making it."""
    r = reader or live(repo)
    w = writer or gh_writer(repo)
    try:
        ctx, decisions = decide_all(repo, pr, manifest_path, r, owner, authors,
                                    list_prs or default_list_prs(repo))
    except UNREADABLE as e:
        out(f"merger: can't decide ({e.__class__.__name__}): nothing posted or merged")
        return 1
    for d in decisions:
        out(d.line())
    mode = ctx.switch.mode
    if mode == "off":
        out(f"merger: off ({ctx.switch.why_off}): nothing posted or merged")
        return 0
    held = None
    if mode == "live":
        try:
            held = shadow_bar(w.history(), clock())
        except UNREADABLE as e:
            held = f"can't count the shadow's comments ({e.__class__.__name__})"
        if held:
            out(f"merger: live acts as shadow: {held}")
    merging = mode == "live" and not held
    failed = 0

    def write(what: str, act: Callable[[], None]) -> bool:
        nonlocal failed
        if dry_run:
            out(f"dry run: would {what}")
            return True
        try:
            act()
            out(f"merger: {what}")
            return True
        except UNREADABLE as e:
            failed += 1
            out(f"merger: couldn't {what} ({e.__class__.__name__}: {str(e)[:200]})")
            return False

    def comment(n: int, body: str) -> bool:
        return write(f"post on #{n}: {body.removesuffix(SIGN)}", lambda: w.post(n, body))

    for d in decisions:
        if d.verdict.startswith("skip: "):
            continue
        try:
            if d.merges and merging:
                now_head = actions_review.head_sha(r.pr(d.number))
                if now_head != d.head:
                    out(f"merger: #{d.number}'s head moved since the decision "
                        f"({d.head[:7]} to {(now_head or '-')[:7]}); not merging")
                    continue
                if write(f"merge #{d.number} at {d.head}", lambda: w.merge(d.number, d.head)):
                    comment(d.number, merged_body(d))
            elif d.merges:
                if not posted(r.comments(d.number), WOULD, d.head):
                    comment(d.number, would_body(d))
            elif worth_telling(d, r.reviews(d.number), ctx.owner) \
                    and not posted(r.comments(d.number), LEFT, d.head):
                comment(d.number, left_body(d))
        except UNREADABLE as e:
            failed += 1
            out(f"merger: #{d.number}: can't read GitHub ({e.__class__.__name__}); left alone")
    verb = "merged" if merging else "would merge"
    out(f"merger: mode {mode}{' (dry run)' if dry_run else ''}: "
        f"{sum(d.merges for d in decisions)} PR(s) {verb}" + (f", {failed} failure(s)" if failed else ""))
    return 1 if failed else 0


def main(argv: list[str] | None = None, env: dict | None = None) -> int:
    env = os.environ if env is None else env
    ap = argparse.ArgumentParser(prog="merger.py", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan", help="print merge or miss for each open PR; writes nothing")
    q = sub.add_parser("run", help="plan, then comment or merge per [merger] mode (GOV-0027)")
    q.add_argument("--dry-run", action="store_true", help="print what it would post or merge")
    for x in (p, q):
        x.add_argument("--pr", type=int, help="consider only this PR")
        x.add_argument("--manifest", help="swarm.toml to read [merger] from (default: the repo's)")
        x.add_argument("--repo", help="owner/name (default: $GITHUB_REPOSITORY, else origin)")
    args = ap.parse_args(argv)
    repo = args.repo or env.get("GITHUB_REPOSITORY") or swarm.dashboard().default_repo()
    if not repo:
        print("merger: can't tell the repo; pass --repo owner/name")
        return 1
    if args.cmd == "run":
        return run(repo, args.dry_run, args.pr, args.manifest)
    return plan(repo, args.pr, args.manifest)


if __name__ == "__main__":
    sys.exit(main())
