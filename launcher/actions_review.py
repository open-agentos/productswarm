"""The reviewer in GitHub Actions, v3 C stage 1 (GOV-0015). C1 (#214) is `check`; C2
(#215) is `run`. `plan` (#257) is the reconciler's first part (#255, stage 1).

    python3 launcher/actions_review.py check
    python3 launcher/actions_review.py plan [--pr N] [--manifest PATH]
    python3 launcher/actions_review.py run --pr N [--dry-run]

`check` decides whether a pull-request event should start a reviewer run. It runs in the
workflow's first job, which holds no secrets, so untrusted input never reaches a job that
does. It reads the event payload ($GITHUB_EVENT_PATH) as data, never PR text as
instructions, and it never prints PR text. It says run only if all of these hold:

- the event is `pull_request` or `workflow_dispatch` with a `pr` input (the owner's
  answer on #209); any other event, `pull_request_target` included, never runs;
- the PR is open and not a draft;
- its author is a swarm App that opens PRs (productswarm-planner, -builder or -docs) or
  the owner from governance/jurisdictions.yml (option 2, the owner's answer on #206);
- its head repo is this repo, not a fork (#206);
- the reviewer App hasn't reviewed its current head SHA: watch.reviewed_heads(), the same
  rule the local [review] trigger uses, so Actions and `swarm watch` agree (#209).

It writes `run=true|false` and `pr=<N>` to $GITHUB_OUTPUT and prints one line saying why.
Its only GitHub calls are reads through `gh` with the job's default token: the reviews on
the PR, and the PR itself for workflow_dispatch (whose payload has only the number). It
reads no secrets and writes nothing to GitHub. If it can't decide (a missing payload, or
GitHub can't be read), it writes run=false and exits 1.

`plan` asks "which open PRs need a review now?" instead of "did this event ask for one?",
so it doesn't depend on PR events (#255). It reads the open PRs and keeps each that passes
the same per-PR rules as `check` (eligible() and judge(), shared): open, not a draft, a
swarm App or the owner as author, head in this repo, head not yet reviewed by the reviewer
App. `--pr N` (the workflow_dispatch input) considers only PR N, under the same rules. At
most [watch] actions_max_reviews PRs go in, lowest number (oldest) first; the rest wait for
the next sweep. With that key unset it lists nothing and says so (as GOV-0012 does for a
missing max_turns). It writes `prs=<JSON list of {"pr": N, "head": "<sha>"}>` and
`any=true|false` to $GITHUB_OUTPUT, ints and hex SHAs only, and prints one line per PR
considered (numbers, SHAs, known logins and rule names; never PR text). Like `check` it
reads GitHub with the job's default token, reads no secrets and writes nothing to GitHub.
If it can't decide (GitHub unreadable, a bad swarm.toml) it writes any=false, prs=[] and
exits 1. hold= is the seam for in-flight and already-attempted heads (part 2).

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
EVENTS = {"pull_request", "workflow_dispatch"}
SHA_RE = re.compile(r"[0-9a-f]{40}")

# `run` (#215)
CREDENTIALS = ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY")   # either; neither preferred (#208)
FIELDS = ("result", "subtype", "num_turns", "total_cost_usd")   # all the job log gets (GOV-0016)
DONE, AT_CAP, ERROR, REFUSED = 0, 3, 1, 2                       # run's exit codes


def decide(event: str, payload: dict, repo: str, owner: str,
           get_pr: Callable[[int], dict], get_reviews: Callable[[int], list[dict]]
           ) -> tuple[bool, int | None, str]:
    """(run, pr number, why). Pure apart from the two read callables, so tests feed it
    canned payloads. The payload's PR is used as is for pull_request; workflow_dispatch
    carries only a number, so the PR is read with get_pr()."""
    if event not in EVENTS:
        return False, None, f"event {event!r} never starts a reviewer run"
    if event == "pull_request":
        pr = payload.get("pull_request")
        if not isinstance(pr, dict):
            return False, None, "pull_request event with no pull_request in its payload"
    else:
        raw = str((payload.get("inputs") or {}).get("pr") or "").strip().lstrip("#")
        if not raw.isdigit():
            return False, None, "workflow_dispatch needs a PR number in its `pr` input"
        pr = get_pr(int(raw))
    return judge(pr, repo, owner, get_reviews)


def eligible(pr: dict, repo: str, owner: str) -> tuple[bool, int | None, str]:
    """GOV-0017's rules for one PR that need no further GitHub read: open, not a draft, a
    swarm App or the owner as author, head in this repo, a hex head SHA. `check` and
    `plan` share it (#257)."""
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


def write_output(path: str | None, run: bool, n: int | None) -> None:
    """run= and pr= lines for the next job. Nothing from the payload but an int goes in."""
    if not path:
        return
    with open(path, "a") as f:
        f.write(f"run={'true' if run else 'false'}\npr={n if isinstance(n, int) else ''}\n")


def check(env: dict | None = None, owner: Callable[[], str] = swarm.owner_login,
          get_pr: Callable[[str, int], dict] | None = None,
          get_reviews: Callable[[str, int], list[dict]] | None = None,
          out: Callable[[str], None] = print) -> int:
    env = os.environ if env is None else env
    g = swarm.dashboard()
    get_pr = get_pr or (lambda repo, n: g.gh_json("api", f"repos/{repo}/pulls/{n}"))
    get_reviews = get_reviews or (lambda repo, n: g.gh_items(f"repos/{repo}/pulls/{n}/reviews?per_page=100"))
    output = env.get("GITHUB_OUTPUT")
    repo = env.get("GITHUB_REPOSITORY") or ""
    try:
        payload = json.loads(Path(env["GITHUB_EVENT_PATH"]).read_text())
        if not repo or not isinstance(payload, dict):
            raise ValueError("no repository or no event payload")
        run, n, why = decide(env.get("GITHUB_EVENT_NAME") or "", payload, repo, owner(),
                             lambda n: get_pr(repo, n), lambda n: get_reviews(repo, n))
    except (KeyError, OSError, ValueError, RuntimeError, subprocess.SubprocessError) as e:
        write_output(output, False, None)
        out(f"run=false: can't decide ({e.__class__.__name__})")
        return 1
    write_output(output, run, n)
    out(f"run={'true' if run else 'false'}: {why}")
    return 0


# ---------------------------------------------------------------- plan (#257)

def max_reviews(manifest_path: Path | str) -> int | None:
    """[watch] actions_max_reviews from swarm.toml: the most PRs one plan lists, or None
    if it is unset (then plan lists nothing, as a missing max_turns starts nothing,
    GOV-0012). Raises ManifestError (a ValueError) on a bad swarm.toml."""
    limits = manifest.load_watch(manifest_path)
    return None if limits is None else limits.actions_max_reviews


def no_hold(n: int, sha: str) -> str | None:
    """The seam for part 2 (in-flight and already-attempted heads): a reason to leave
    PR n at head sha out of the plan, or None. Today nothing is held."""
    return None


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
         hold: Callable[[int, str], str | None] = no_hold,
         out: Callable[[str], None] = print) -> int:
    """List the open PRs the reviewer should review now (or only PR pr, for --pr). Reads
    with the job's default token, writes nothing to GitHub, reads no secrets. Exit 0 when
    it decided (even on an empty plan), 1 when it couldn't (then any=false, prs=[])."""
    env = os.environ if env is None else env
    g = swarm.dashboard()
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
    sub.add_parser("check", help="should this PR event start a reviewer run? (secret-free)")
    p_plan = sub.add_parser("plan", help="which open PRs need a reviewer run now? (secret-free)")
    p_plan.add_argument("--pr", type=int, default=None, help="consider only this PR")
    p_plan.add_argument("--manifest", default=None, help="swarm.toml to read (default: the repo's)")
    p_run = sub.add_parser("run", help="one reviewer pass on one PR, with GOV-0012/0013/0014 limits")
    p_run.add_argument("--pr", type=int, required=True, help="the PR to review")
    p_run.add_argument("--dry-run", action="store_true", help="print the command; start nothing")
    p_run.add_argument("--manifest", default=None, help="swarm.toml to read (default: the repo's)")
    args = p.parse_args(argv)
    if args.cmd == "check":
        return check()
    if args.cmd == "plan":
        return plan(pr=args.pr, manifest_path=args.manifest)
    if args.cmd == "run":
        return run(args.pr, dry_run=args.dry_run, manifest_path=args.manifest)
    return 2


if __name__ == "__main__":
    sys.exit(main())
