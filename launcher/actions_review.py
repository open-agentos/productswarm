"""The reviewer in GitHub Actions, v3 C stage 1 (GOV-0015), as a reconciler on main
(GOV-0020, from #255). `plan` (#257, #258) decides which open PRs to review; `run` (#215)
reviews one. .github/workflows/reviewer.yml runs `plan` on a schedule or a dispatch, then
one `run` job per PR it listed. No PR event starts a run.

    python3 launcher/actions_review.py plan [--pr N] [--manifest PATH]
    python3 launcher/actions_review.py run --pr N [--dry-run]

`plan` asks "which open PRs need a review now?" from repo state, so it doesn't depend on
PR events (GOV-0020). It runs in the workflow's first job, which holds no secrets, and
reads PRs as data, never PR text as instructions. It reads the open PRs and keeps each
that passes GOV-0017's per-PR rules (eligible() and judge()): open, not a draft, a swarm
App or the owner as author, head in this repo, not a fork, and head not
yet reviewed by the reviewer App: watch.reviewed_heads(), the rule the local [review]
trigger uses, so Actions and `swarm watch` agree (#209). `--pr N` (the workflow_dispatch
input) considers only PR N, under the same rules. At most [watch] actions_max_reviews PRs
go in, lowest number (oldest) first; the rest wait for the next sweep. With that key unset it lists nothing and says so (as GOV-0012 does for a
missing max_turns). It writes `prs=<JSON list of {"pr": N, "head": "<sha>"}>` and
`any=true|false` to $GITHUB_OUTPUT, ints and hex SHAs only, and prints one line per PR
considered (numbers, SHAs, known logins and rule names; never PR text). It only reads
GitHub, with the job's default token, reads no secrets and writes nothing to GitHub.
If it can't decide (GitHub unreadable, a bad swarm.toml) it writes any=false, prs=[] and
exits 1.

The swarm Apps it trusts as authors are every login under identities.agents in
governance/jurisdictions.yml (#491, #506), read from the checkout of main the plan job runs
(GOV-0020), so a PR head can't change them and a role added there is trusted with no code
change. The owner is humans.owner from the same file (#206). If the file is missing or that
block can't be read, plan fails closed: it trusts only the owner and says why in one line
(the file's path and an exception name, never its text).

`plan` also leaves out a head the reviewer workflow has already tried (#258), from the
Actions run history rather than a local file, the rule `swarm watch` keeps in watch.json.
An attempt is a `review` matrix job named REVIEW_JOB (`review #<pr> <head sha>`). A head
whose newest attempt is queued or in progress is out, so GOV-0019's cancel-in-progress
never cancels a live review of it; one whose newest attempt completed with any conclusion
but `cancelled` is out too, so a run that ended at its budget isn't restarted every sweep.
`--pr N` (the owner's dispatch) still leaves out an in-flight head but retries a completed
attempt: that is the owner's restart. The read is bounded: only this workflow's runs
created since the head's commit (less CLOCK_SKEW), newest first, stopping at the head's
newest attempt, and at most MAX_JOB_READS runs' jobs per plan; past that, an unresolved
head is held, never started twice. A run still in progress whose `plan` job has
succeeded but which lists no other job yet is starting (#278): its review jobs are about to
be created, so every head it could have listed (committed before the run was created,
plus CLOCK_SKEW) is held, with that reason in the log. It needs `actions: read` and stays read-only.

`run --pr N` runs one reviewer pass on PR N, in the workflow's second job, with the same
limits as a run `swarm watch` starts:

- the claude argv is swarm.headless_flags(), the flags Launcher.headless_args() quotes:
  `--permission-mode auto` and `--disallowedTools` (GOV-0013) plus REVIEWER_DENY, which
  denies creating issues in these runs only (#389), `--max-budget-usd` from the
  reviewer's spend_cap_usd and `--max-turns` from [watch] max_turns in swarm.toml (GOV-0012),
  and `--output-format json`. The budget holds under a subscription token too: there
  total_cost_usd is Claude Code's estimate, not a bill, but it's still the ceiling;
- the opener is the reviewer's, on PR N only, one pass, then stop;
- the reviewer's Stop hook (stophook.py, GOV-0014, as by="actions") is written into this
  checkout's .claude/settings.local.json, so it runs from the job's checkout of main;
- the heartbeat is off (#307): its hooks are not installed (any already in the settings are
  removed) and SWARM_ROLE is unset in claude's env, so hook.py does nothing even if run.
  Its first flush used to open a `[heartbeat] reviewer` tracking issue whose event comments
  were then refused, leaving an empty open issue per run. Actions runs don't appear on the
  dashboard (the owner's direction on #240 and #307); the job log (GOV-0016) and the
  Actions tab are their record;
- the model credential is CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY, whichever the job
  sets (the owner's direction on #208); it prefers neither and passes both through as is.
  With neither, it stops before starting anything;
- GitHub access is the reviewer App token the workflow puts in GH_TOKEN (#207). It mints
  nothing and doesn't touch ops/.

Per GOV-0016 it writes claude's stdout (the JSON result) and stderr to files in a fresh
directory under $RUNNER_TEMP, which the runner throws away, and prints only `result`,
`subtype`, `num_turns` and `total_cost_usd`, one JSON-encoded line each, never the
transcript, tool output or environment. Each line starts with the field name, so nothing
it prints can be read as an Actions workflow command (`::...`).

Exit: 0 done, 3 ended at its budget or turn ceiling, 1 an error or no result, 2 refused
(not in Actions, no credential, or no reviewer cap or max_turns in swarm.toml), so the job
shows red for all but done. `--dry-run` prints the command and starts nothing; it works
anywhere and needs no credential.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import manifest  # noqa: E402
import stophook  # noqa: E402
import swarm  # noqa: E402
import watch  # noqa: E402

sys.path.insert(0, str(swarm.ROOT / "heartbeat"))
import install  # noqa: E402

sys.path.insert(0, str(swarm.ROOT / "dashboard"))
import authority  # noqa: E402  (jurisdictions.yml's reader, not a second parser)

APP_RE = re.compile(r"productswarm-[a-z0-9-]+\[bot\]")   # a swarm App's login (#506)
SHA_RE = re.compile(r"[0-9a-f]{40}")

# `plan`'s attempt history (#258). The `review` matrix job in .github/workflows/reviewer.yml
# must be named exactly this (full SHA): it is how plan finds earlier attempts on a head.
REVIEW_JOB = "review #{pr} {head}"
REVIEW_JOB_RE = re.compile(r"review #(\d+) ([0-9a-f]{40})")
PLAN_JOB = "plan"             # reviewer.yml's first job; a run with only this, done, is starting (#278)
WORKFLOW = "reviewer.yml"     # whose runs plan reads, when GITHUB_WORKFLOW_REF doesn't say
MAX_JOB_READS = 50            # runs whose jobs one plan may read
CLOCK_SKEW = 600              # seconds: a commit's date may be a little after its push

# `run` (#215)
CREDENTIALS = ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY")   # either; neither preferred (#208)
FIELDS = ("result", "subtype", "num_turns", "total_cost_usd")   # all the job log gets (GOV-0016)
DONE, AT_CAP, ERROR, REFUSED = 0, 3, 1, 2                       # run's exit codes


def trusted_authors(path: Path = swarm.JURISDICTIONS) -> tuple[frozenset[str], str | None]:
    """(the swarm Apps whose PRs plan reviews, why none) from identities.agents in
    jurisdictions.yml (#491, #506). Fails closed: if the file is missing, can't be parsed,
    or the block isn't a non-empty mapping of swarm App logins, no App is trusted, and the
    reason names only the file and an exception or rule, never the file's text."""
    where = authority.JURISDICTIONS_PATH
    try:
        doc = authority.read(Path(path).read_text())
    except (OSError, UnicodeDecodeError, ValueError) as e:
        return frozenset(), f"can't read {where} ({e.__class__.__name__})"
    ids = doc.get("identities")
    agents = ids.get("agents") if isinstance(ids, dict) else None
    if not isinstance(agents, dict) or not agents:
        return frozenset(), f"{where} has no identities.agents mapping"
    if not all(isinstance(v, str) and APP_RE.fullmatch(v) for v in agents.values()):
        return frozenset(), f"{where}: identities.agents holds a value that isn't a swarm App login"
    return frozenset(agents.values()), None


def eligible(pr: dict, repo: str, owner: str, authors: frozenset[str] = frozenset()
             ) -> tuple[bool, int | None, str]:
    """GOV-0017's rules for one PR that need no further GitHub read: open, not a draft, a
    swarm App in authors (trusted_authors()) or the owner as author, head in this repo, a
    hex head SHA (#257). With no authors only the owner's PRs pass (fail closed, #506)."""
    n = pr.get("number")
    if not isinstance(n, int) or isinstance(n, bool):
        return False, None, "the PR has no number"
    if pr.get("state") != "open":
        return False, n, f"PR #{n} is not open"
    if pr.get("draft"):
        return False, n, f"PR #{n} is a draft"
    author = (pr.get("user") or {}).get("login") or ""
    if author not in authors and author != owner:
        return False, n, f"PR #{n} was opened by someone other than a swarm App or the owner (#206)"
    head_repo = ((pr.get("head") or {}).get("repo") or {}).get("full_name")
    if head_repo != repo:
        return False, n, f"PR #{n}'s head is not in {repo} (a fork, or a deleted repo)"
    if not head_sha(pr):
        return False, n, f"PR #{n} has no head SHA"
    return True, n, f"PR #{n} by {author}"


def head_sha(pr: dict) -> str:
    """The PR's head SHA if it is 40 lowercase hex digits, else "": nothing else from
    GitHub reaches an output."""
    sha = (pr.get("head") or {}).get("sha")
    return sha if isinstance(sha, str) and SHA_RE.fullmatch(sha) else ""


def judge(pr: dict, repo: str, owner: str, get_reviews: Callable[[int], list[dict]],
          authors: frozenset[str] = frozenset()) -> tuple[bool, int | None, str]:
    """(review it, pr number, why) for one PR: eligible(), then the head not yet reviewed
    by the reviewer App (watch.reviewed_heads(), the rule [review] uses). Reviews are read
    only for an eligible PR."""
    ok, n, why = eligible(pr, repo, owner, authors)
    if not ok:
        return False, n, why
    sha = head_sha(pr)
    if sha in watch.reviewed_heads(get_reviews(n)):
        return False, n, f"PR #{n}: the reviewer already reviewed head {sha[:7]}"
    return True, n, f"{why}: head {sha[:7]} not reviewed by the reviewer"


# ---------------------------------------------------------------- plan (#257)

def max_reviews(manifest_path: Path | str) -> int | None:
    """[watch] actions_max_reviews from swarm.toml: the most PRs one plan lists, or None
    if it is unset (then plan lists nothing, as a missing max_turns starts nothing,
    GOV-0012). Raises ManifestError (a ValueError) on a bad swarm.toml."""
    limits = manifest.load_watch(manifest_path)
    return None if limits is None else limits.actions_max_reviews


def no_hold(n: int, sha: str) -> str | None:
    """A hold that holds nothing (tests of the per-PR rules use it)."""
    return None


def review_job(pr: int, head: str) -> str:
    """The name reviewer.yml's `review` job must have for PR pr at head (REVIEW_JOB)."""
    return REVIEW_JOB.format(pr=pr, head=head)


def parse_review_job(name: object) -> tuple[int, str] | None:
    """(pr, head) from a REVIEW_JOB job name, or None for any other job."""
    m = REVIEW_JOB_RE.fullmatch(name) if isinstance(name, str) else None
    return (int(m.group(1)), m.group(2)) if m else None


def iso_time(value: object) -> float | None:
    """Seconds since the epoch from a GitHub ISO 8601 time, or None."""
    if not isinstance(value, str):
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


class History:
    """The reviewer workflow's earlier attempts, as hold(n, sha) for make_plan (#258).

    list_runs(since) gives the workflow's runs created at or after since (epoch seconds),
    get_jobs(run id) a run's jobs, head_time(sha) the head commit's date (epoch seconds).
    Jobs are read lazily, newest run first, cached across PRs, and at most max_reads runs'
    worth per plan. retry_completed is --pr: a completed attempt doesn't hold."""

    def __init__(self, list_runs: Callable[[float], list[dict]], get_jobs: Callable[[int], list[dict]],
                 head_time: Callable[[str], float], retry_completed: bool = False,
                 max_reads: int = MAX_JOB_READS):
        self.list_runs, self.get_jobs, self.head_time = list_runs, get_jobs, head_time
        self.retry_completed, self.max_reads = retry_completed, max_reads
        self.jobs: dict[int, list[dict]] = {}

    @staticmethod
    def starting(run: dict, jobs: list[dict]) -> bool:
        """Whether run is between its plan and its review jobs (#278): not completed, and
        its only job is a successful PLAN_JOB. reviewer-plan is released when plan ends,
        and GitHub creates the review matrix just after, so another plan in that gap would
        see no attempt on a head this run has listed."""
        return (run.get("status") != "completed" and len(jobs) == 1
                and jobs[0].get("name") == PLAN_JOB and jobs[0].get("status") == "completed"
                and jobs[0].get("conclusion") == "success")

    def newest_attempt(self, n: int, sha: str) -> tuple[dict | None, dict | None, bool]:
        """(run, job) of the newest attempt on PR n at head sha, and whether the search
        was complete (False when it stopped at max_reads first). A starting run (#278)
        newer than any attempt gives (run, None): it may be about to review this head."""
        def key(run):
            return (iso_time(run.get("created_at")) or 0, run.get("id") or 0)
        runs = [r for r in self.list_runs(self.head_time(sha) - CLOCK_SKEW)
                if isinstance(r, dict) and isinstance(r.get("id"), int)]
        for run in sorted(runs, key=key, reverse=True):
            if self.retry_completed and run.get("status") == "completed":
                continue      # nothing in a finished run is in flight, and --pr retries the rest
            if run["id"] not in self.jobs:
                if len(self.jobs) >= self.max_reads:
                    return None, None, False
                self.jobs[run["id"]] = [j for j in self.get_jobs(run["id"]) if isinstance(j, dict)]
            if self.starting(run, self.jobs[run["id"]]):
                return run, None, True
            for job in self.jobs[run["id"]]:
                if parse_review_job(job.get("name")) == (n, sha):
                    return run, job, True
        return None, None, True

    def __call__(self, n: int, sha: str) -> str | None:
        run, job, complete = self.newest_attempt(n, sha)
        if not complete:
            return (f"head {sha[:7]}: no attempt found in the {self.max_reads} newest runs "
                    "read, so one can't be ruled out")
        if job is None:
            return None if run is None else (
                f"run {run['id']} is starting: its plan has finished but it lists no review "
                f"job yet, so it may be about to review head {sha[:7]}")
        status, conclusion = job.get("status"), job.get("conclusion")
        if status != "completed":
            return f"head {sha[:7]} is being reviewed in run {run['id']} ({status})"
        if conclusion == "cancelled" or self.retry_completed:
            return None
        return f"head {sha[:7]} already attempted in run {run['id']}, conclusion {conclusion}"


def workflow_file(env: dict) -> str:
    """This workflow's file name from GITHUB_WORKFLOW_REF
    (owner/repo/.github/workflows/<file>@<ref>), else WORKFLOW."""
    ref = (env.get("GITHUB_WORKFLOW_REF") or "").split("@", 1)[0]
    name = ref.rsplit("/", 1)[-1]
    return name if re.fullmatch(r"[\w.-]+\.ya?ml", name) else WORKFLOW


def gh_list(path: str, key: str) -> list[dict]:
    """Every item under key of a paginated endpoint that wraps its list in an object (the
    Actions runs and jobs endpoints)."""
    r = subprocess.run(["gh", "api", "--paginate", path, "--jq", f".{key}[]"],
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"gh api {path} failed: {r.stderr.strip()[:300]}")
    return [json.loads(line) for line in r.stdout.splitlines() if line.strip()]


def utc(t: float) -> str:
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_plan(prs: list[dict], repo: str, owner: str, cap: int,
              get_reviews: Callable[[int], list[dict]],
              hold: Callable[[int, str], str | None] = no_hold,
              authors: frozenset[str] = frozenset()) -> tuple[list[dict], list[str]]:
    """([{"pr": N, "head": sha}, ...], one line per PR considered). Oldest PR (lowest
    number) first; at most cap PRs go in, the rest wait for the next sweep. Pure apart
    from get_reviews, so tests feed it canned PR lists."""
    def number(pr):
        n = pr.get("number") if isinstance(pr, dict) else None
        return n if isinstance(n, int) and not isinstance(n, bool) else 0
    chosen, lines = [], []
    for pr in sorted((x for x in prs if isinstance(x, dict)), key=number):
        ok, n, why = judge(pr, repo, owner, get_reviews, authors)
        if ok:
            sha = head_sha(pr)
            held = hold(n, sha)
            if held:
                ok, why = False, f"PR #{n}: {held}"
            elif len(chosen) >= cap:
                ok, why = False, f"PR #{n}: head {sha[:7]} waits for the next sweep (cap {cap})"
            else:
                chosen.append({"pr": n, "head": sha})
        lines.append(f"{'in' if ok else 'out'}: {why}")
    return chosen, lines


def commit_time(commit: object) -> float:
    """The committer date of a REST commit, in epoch seconds. Raises ValueError."""
    date = (((commit or {}).get("commit") or {}).get("committer") or {}).get("date") \
        if isinstance(commit, dict) else None
    t = iso_time(date)
    if t is None:
        raise ValueError("a head commit has no date")
    return t


def write_plan(path: str | None, chosen: list[dict]) -> None:
    """prs= and any= lines for the next job: ints and hex SHAs only."""
    if not path:
        return
    safe = [{"pr": int(c["pr"]), "head": c["head"]} for c in chosen if SHA_RE.fullmatch(c["head"])]
    with open(path, "a") as f:
        f.write(f"prs={json.dumps(safe, separators=(',', ':'))}\nany={'true' if safe else 'false'}\n")


def plan(env: dict | None = None, pr: int | None = None, owner: Callable[[], str] = swarm.owner_login,
         list_prs: Callable[[str], list[dict]] | None = None,
         get_pr: Callable[[str, int], dict] | None = None,
         get_reviews: Callable[[str, int], list[dict]] | None = None,
         manifest_path: Path | str | None = None,
         hold: Callable[[int, str], str | None] | None = None,
         list_runs: Callable[[str, str, float], list[dict]] | None = None,
         get_jobs: Callable[[str, int], list[dict]] | None = None,
         head_time: Callable[[str, str], float] | None = None,
         authors: Callable[[], tuple[frozenset[str], str | None]] = trusted_authors,
         out: Callable[[str], None] = print) -> int:
    """List the open PRs the reviewer should review now (or only PR pr, for --pr). Reads
    with the job's default token, writes nothing to GitHub, reads no secrets. Exit 0 when
    it decided (even on an empty plan), 1 when it couldn't (then any=false, prs=[]).
    hold defaults to a History of this workflow's runs (#258). authors gives the trusted
    swarm Apps (trusted_authors(), #506); when it gives none, only the owner's PRs pass."""
    env = os.environ if env is None else env
    g = swarm.dashboard()
    list_runs = list_runs or (lambda repo, wf, since: gh_list(
        f"repos/{repo}/actions/workflows/{wf}/runs?created=%3E%3D{utc(since)}&per_page=100",
        "workflow_runs"))
    get_jobs = get_jobs or (lambda repo, run: gh_list(
        f"repos/{repo}/actions/runs/{run}/jobs?per_page=100", "jobs"))
    head_time = head_time or (lambda repo, sha: commit_time(
        g.gh_json("api", f"repos/{repo}/commits/{sha}")))
    list_prs = list_prs or (lambda repo: g.gh_items(f"repos/{repo}/pulls?state=open&per_page=100"))
    get_pr = get_pr or (lambda repo, n: g.gh_json("api", f"repos/{repo}/pulls/{n}"))
    get_reviews = get_reviews or (lambda repo, n: g.gh_items(f"repos/{repo}/pulls/{n}/reviews?per_page=100"))
    output = env.get("GITHUB_OUTPUT")
    repo = env.get("GITHUB_REPOSITORY") or ""
    try:
        if not repo:
            raise ValueError("no GITHUB_REPOSITORY")
        cap = max_reviews(manifest_path or swarm.ROOT / "swarm.toml")
        if cap is None:
            write_plan(output, [])
            out("plan: nothing listed: swarm.toml sets no [watch] actions_max_reviews (#257)")
            return 0
        prs = [get_pr(repo, pr)] if pr is not None else list_prs(repo)
        if hold is None:
            wf = workflow_file(env)
            hold = History(lambda since: list_runs(repo, wf, since),
                           lambda run: get_jobs(repo, run),
                           lambda sha: head_time(repo, sha), retry_completed=pr is not None)
        if not isinstance(prs, list):
            raise ValueError("the PR list is not a list")
        apps, why_none = authors()
        if why_none:
            out(f"plan: trusting only the owner: {why_none} (#506)")
        chosen, lines = make_plan(prs, repo, owner(), cap, lambda n: get_reviews(repo, n), hold,
                                  apps)
    except (KeyError, OSError, ValueError, RuntimeError, subprocess.SubprocessError) as e:
        write_plan(output, [])
        out(f"plan: can't decide ({e.__class__.__name__})")
        return 1
    write_plan(output, chosen)
    for line in lines:
        out(line)
    out(f"plan: {len(chosen)} PR(s) to review" + (f" (--pr {pr})" if pr is not None else ""))
    return 0


# ---------------------------------------------------------------- run (#215)

def reviewer_entry(pr: int, manifest_path: Path | str, session_id: str, started: float
                   ) -> swarm.Started:
    """The run as a launcher entry: the reviewer's model and spend_cap_usd, and [watch]
    max_turns, from swarm.toml. Raises ValueError (ManifestError is one) if either limit
    is missing: a run with no budget or turn ceiling never starts (GOV-0012)."""
    sessions, limits, problems = manifest.load_all(manifest_path)
    if problems:
        raise manifest.ManifestError(Path(manifest_path), problems)
    rev = next((x for x in sessions if x.role == "reviewer"), None)
    if rev is None or rev.spend_cap_usd is None:
        raise ValueError(f"{manifest_path} sets no spend_cap_usd for the reviewer (GOV-0012)")
    if limits is None or limits.max_turns is None:
        raise ValueError(f"{manifest_path} has no [watch] max_turns (GOV-0012)")
    return swarm.Started(name=f"reviewer-pr-{pr}", role="reviewer", model=rev.model,
                         session_id=session_id, started=started, by="actions", pr=pr,
                         budget_usd=rev.spend_cap_usd, max_turns=limits.max_turns)


# Reviewer runs in Actions only, on top of swarm.DENY (#389): never create an issue. The
# reviewer token has `issues: read` (#384's log), yet GraphQL createIssue, which `gh issue
# create` uses, accepted it (#364). A backstop like DENY, not a fence: e.g. a GraphQL query
# read from a file (`-F query=@q.graphql`) gets past it. Not in swarm.DENY: the planner
# opens issues as its job.
REVIEWER_DENY = (
    "Bash(gh issue create *)",               # gh's own command (it uses GraphQL createIssue)
    "Bash(gh api graphql *createIssue*)",    # the mutation, called directly
    "Bash(gh api *repos/*/issues)",          # REST create, path last: `gh api -X POST repos/o/r/issues`
    "Bash(gh api *repos/*/issues *)",        # REST create, flags after the path, any of -X/--method/-f/-F/--input
)


def claude_argv(e: swarm.Started) -> list[str]:
    """What ops/swarm-session would exec for this run, with swarm.headless_flags() and
    REVIEWER_DENY."""
    return ["claude", "--model", e.model, "--session-id", e.session_id,
            "-p", swarm.opener(e.role, e.issue, e.pr),
            *swarm.headless_flags(e.budget_usd, e.max_turns, REVIEWER_DENY)]


def hook_settings(root: Path) -> dict:
    """root's .claude/settings.local.json with the reviewer's Stop hook from root (the job's
    checkout of main) and no heartbeat hooks (#307): an Actions run posts nothing to GitHub
    through the heartbeat."""
    settings = install.with_hooks(install.read_settings(root / ".claude" / "settings.local.json"),
                                  uninstall=True)
    return stophook.with_stop_hook(settings, stophook.script_for(str(root / install.MARK)))


def load_result(path: Path) -> dict | None:
    """claude's --output-format json result from its stdout file, or None."""
    try:
        text = path.read_text()
    except (OSError, UnicodeDecodeError):
        return None
    lines = [x for x in text.splitlines() if x.strip()]
    for candidate in (text, lines[-1] if lines else ""):
        try:
            d = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(d, dict) and d.get("type") == "result":
            return d
    return None


def report(path: Path, out: Callable[[str], None]) -> int:
    """Print GOV-0016's four fields and return the exit code for how the run ended. The
    ending is watch.read_result()'s, so Actions and `swarm watch` classify runs alike."""
    result = load_result(path)
    if result is None:
        out("run: no JSON result from claude")
        return ERROR
    for f in FIELDS:
        out(f"{f}: {json.dumps(result.get(f))}")
    ending = watch.read_result(path)["ending"]
    return DONE if ending == watch.DONE else AT_CAP if ending == watch.AT_CAP else ERROR


def run(pr: int, dry_run: bool = False, env: dict | None = None, root: Path = swarm.ROOT,
        manifest_path: Path | str | None = None, call: Callable = subprocess.run,
        out: Callable[[str], None] = print, clock: Callable[[], float] = time.time,
        new_id: Callable[[], str] = lambda: str(uuid.uuid4())) -> int:
    env = dict(os.environ if env is None else env)
    root = Path(root)
    manifest_path = manifest_path or root / "swarm.toml"
    if not dry_run:
        if env.get("GITHUB_ACTIONS") != "true":
            out("run: refused: this runs only in GitHub Actions (it writes this checkout's hook "
                "settings); use --dry-run to see the command")
            return REFUSED
        if not any(env.get(k) for k in CREDENTIALS):
            out(f"run: refused: no model credential; set {CREDENTIALS[0]} or {CREDENTIALS[1]}")
            return REFUSED
    try:
        e = reviewer_entry(pr, manifest_path, new_id(), clock())
    except ValueError as ex:
        out(f"run: refused: {ex}")
        return REFUSED
    argv = claude_argv(e)
    if dry_run:
        out(f"dry run: from {root}, with the Stop hook and no heartbeat, would run:")
        out(shlex.join(argv))
        return DONE
    home = Path(tempfile.mkdtemp(prefix="productswarm-", dir=env.get("RUNNER_TEMP") or None))
    (home / "launcher").mkdir(mode=0o700)
    (home / "launcher" / "sessions.json").write_text(json.dumps([e.__dict__]) + "\n")   # stophook.py reads it
    install.write_settings(root / ".claude" / "settings.local.json", hook_settings(root))
    result = home / "launcher" / f"{e.session_id}.result.json"
    # No SWARM_ROLE: without it hook.py is a no-op, so no heartbeat posts from Actions (#307).
    child = {k: v for k, v in env.items() if k != "SWARM_ROLE"}
    child.update({"ANTHROPIC_MODEL": e.model, "PRODUCTSWARM_HOME": str(home)})
    out(f"run: reviewer on PR #{pr}, budget ${e.budget_usd:g}, at most {e.max_turns} turns")
    try:
        with open(result, "w") as so, open(home / "launcher" / f"{e.session_id}.stderr", "w") as se:
            call(argv, cwd=str(root), env=child, stdin=subprocess.DEVNULL, stdout=so, stderr=se)
    except OSError as ex:
        out(f"run: can't start claude ({ex.__class__.__name__})")
        return ERROR
    return report(result, out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="actions_review.py", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    p_plan = sub.add_parser("plan", help="which open PRs need a reviewer run now? (secret-free)")
    p_plan.add_argument("--pr", type=int, default=None, help="consider only this PR")
    p_plan.add_argument("--manifest", default=None, help="swarm.toml to read (default: the repo's)")
    p_run = sub.add_parser("run", help="one reviewer pass on one PR, with GOV-0012/0013/0014 limits")
    p_run.add_argument("--pr", type=int, required=True, help="the PR to review")
    p_run.add_argument("--dry-run", action="store_true", help="print the command; start nothing")
    p_run.add_argument("--manifest", default=None, help="swarm.toml to read (default: the repo's)")
    args = p.parse_args(argv)
    if args.cmd == "plan":
        return plan(pr=args.pr, manifest_path=args.manifest)
    if args.cmd == "run":
        return run(args.pr, dry_run=args.dry_run, manifest_path=args.manifest)
    return 2


if __name__ == "__main__":
    sys.exit(main())
