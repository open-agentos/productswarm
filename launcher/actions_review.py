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
App that opens PRs (productswarm-planner, -builder or -docs) or the owner from
governance/jurisdictions.yml as author (#206), head in this repo, not a fork, and head not
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
head is held, never started twice. It needs `actions: read` and stays read-only.

`run --pr N` runs one reviewer pass on PR N, in the workflow's second job, with the same
limits as a run `swarm watch` starts:

- the claude argv is swarm.headless_flags(), the flags Launcher.headless_args() quotes:
  `--permission-mode auto` and `--disallowedTools` (GOV-0013), `--max-budget-usd` from the
  reviewer's spend_cap_usd and `--max-turns` from [watch] max_turns in swarm.toml (GOV-0012),
  and `--output-format json`. The budget holds under a subscription token too: there
  total_cost_usd is Claude Code's estimate, not a bill, but it's still the ceiling;
- the opener is the reviewer's, on PR N only, one pass, then stop;
- the heartbeat hook (SWARM_ROLE=reviewer, as ops/swarm-session sets it) and the reviewer's
  Stop hook (stophook.py, GOV-0014, as by="actions") are written into this checkout's
  .claude/settings.local.json, so they run from the job's checkout of main;
- the model credential is CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY, whichever the job
  sets (the owner's direction on #208); it prefers neither and passes both through as is.
  With neither, it stops before starting anything;
- GitHub access is the reviewer App token the workflow puts in GH_TOKEN (#207). It mints
  nothing and doesn't touch ops/.

Per GOV-0016 it writes claude's stdout (the JSON result) and stderr to files in a fresh
directory under $RUNNER_TEMP, which the runner throws away, and prints only `result`,
`subtype`, `num_turns` and `total_cost_usd`, one JSON-encoded line each, never the
transcript, tool output or environment. Each line starts with the field name, so nothing
it prints can be read as an Actions workflow command (`::...`). The heartbeat's local spool
and state live in that same directory and are never uploaded.

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

# The Apps whose PRs the Actions reviewer reviews (#206). The reviewer itself opens none.
AUTHORS = {f"productswarm-{r}[bot]" for r in ("planner", "builder", "docs")}
SHA_RE = re.compile(r"[0-9a-f]{40}")

# `plan`'s attempt history (#258). The `review` matrix job in .github/workflows/reviewer.yml
# must be named exactly this (full SHA): it is how plan finds earlier attempts on a head.
REVIEW_JOB = "review #{pr} {head}"
REVIEW_JOB_RE = re.compile(r"review #(\d+) ([0-9a-f]{40})")
WORKFLOW = "reviewer.yml"     # whose runs plan reads, when GITHUB_WORKFLOW_REF doesn't say
MAX_JOB_READS = 50            # runs whose jobs one plan may read
CLOCK_SKEW = 600              # seconds: a commit's date may be a little after its push

# `run` (#215)
CREDENTIALS = ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY")   # either; neither preferred (#208)
FIELDS = ("result", "subtype", "num_turns", "total_cost_usd")   # all the job log gets (GOV-0016)
DONE, AT_CAP, ERROR, REFUSED = 0, 3, 1, 2                       # run's exit codes


def eligible(pr: dict, repo: str, owner: str) -> tuple[bool, int | None, str]:
    """GOV-0017's rules for one PR that need no further GitHub read: open, not a draft, a
    swarm App or the owner as author, head in this repo, a hex head SHA (#257)."""
    n = pr.get("number")
    if not isinstance(n, int) or isinstance(n, bool):
        return False, None, "the PR has no number"
    if pr.get("state") != "open":
        return False, n, f"PR #{n} is not open"
    if pr.get("draft"):
        return False, n, f"PR #{n} is a draft"
    author = (pr.get("user") or {}).get("login") or ""
    if author not in AUTHORS and author != owner:
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


def judge(pr: dict, repo: str, owner: str, get_reviews: Callable[[int], list[dict]]
          ) -> tuple[bool, int | None, str]:
    """(review it, pr number, why) for one PR: eligible(), then the head not yet reviewed
    by the reviewer App (watch.reviewed_heads(), the rule [review] uses). Reviews are read
    only for an eligible PR."""
    ok, n, why = eligible(pr, repo, owner)
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

    def newest_attempt(self, n: int, sha: str) -> tuple[dict | None, dict | None, bool]:
        """(run, job) of the newest attempt on PR n at head sha, and whether the search
        was complete (False when it stopped at max_reads first)."""
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
            return None
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
              hold: Callable[[int, str], str | None] = no_hold
              ) -> tuple[list[dict], list[str]]:
    """([{"pr": N, "head": sha}, ...], one line per PR considered). Oldest PR (lowest
    number) first; at most cap PRs go in, the rest wait for the next sweep. Pure apart
    from get_reviews, so tests feed it canned PR lists."""
    def number(pr):
        n = pr.get("number") if isinstance(pr, dict) else None
        return n if isinstance(n, int) and not isinstance(n, bool) else 0
    chosen, lines = [], []
    for pr in sorted((x for x in prs if isinstance(x, dict)), key=number):
        ok, n, why = judge(pr, repo, owner, get_reviews)
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
         out: Callable[[str], None] = print) -> int:
    """List the open PRs the reviewer should review now (or only PR pr, for --pr). Reads
    with the job's default token, writes nothing to GitHub, reads no secrets. Exit 0 when
    it decided (even on an empty plan), 1 when it couldn't (then any=false, prs=[]).
    hold defaults to a History of this workflow's runs (#258)."""
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
        chosen, lines = make_plan(prs, repo, owner(), cap, lambda n: get_reviews(repo, n), hold)
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
    sessions, limits = manifest.load_all(manifest_path)
    rev = next((x for x in sessions if x.role == "reviewer"), None)
    if rev is None or rev.spend_cap_usd is None:
        raise ValueError(f"{manifest_path} sets no spend_cap_usd for the reviewer (GOV-0012)")
    if limits is None or limits.max_turns is None:
        raise ValueError(f"{manifest_path} has no [watch] max_turns (GOV-0012)")
    return swarm.Started(name=f"reviewer-pr-{pr}", role="reviewer", model=rev.model,
                         session_id=session_id, started=started, by="actions", pr=pr,
                         budget_usd=rev.spend_cap_usd, max_turns=limits.max_turns)


def claude_argv(e: swarm.Started) -> list[str]:
    """What ops/swarm-session would exec for this run, with swarm.headless_flags()."""
    return ["claude", "--model", e.model, "--session-id", e.session_id,
            "-p", swarm.opener(e.role, e.issue, e.pr), *swarm.headless_flags(e.budget_usd, e.max_turns)]


def hook_settings(root: Path) -> dict:
    """root's .claude/settings.local.json with the heartbeat hooks and the reviewer's Stop
    hook, both from root (the job's checkout of main)."""
    hook = str(root / install.MARK)
    settings = install.with_hooks(install.read_settings(root / ".claude" / "settings.local.json"), hook=hook)
    return stophook.with_stop_hook(settings, stophook.script_for(hook))


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
        out(f"dry run: from {root}, with SWARM_ROLE=reviewer and the heartbeat and Stop hooks, would run:")
        out(shlex.join(argv))
        return DONE
    home = Path(tempfile.mkdtemp(prefix="productswarm-", dir=env.get("RUNNER_TEMP") or None))
    (home / "launcher").mkdir(mode=0o700)
    (home / "launcher" / "sessions.json").write_text(json.dumps([e.__dict__]) + "\n")   # stophook.py reads it
    install.write_settings(root / ".claude" / "settings.local.json", hook_settings(root))
    result = home / "launcher" / f"{e.session_id}.result.json"
    child = {**env, "SWARM_ROLE": e.role, "ANTHROPIC_MODEL": e.model, "PRODUCTSWARM_HOME": str(home)}
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
