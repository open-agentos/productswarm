"""The reviewer in GitHub Actions, v3 C stage 1 (GOV-0015). C1 (#214) is `check`.

    python3 launcher/actions_review.py check

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
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import swarm  # noqa: E402
import watch  # noqa: E402

# The Apps whose PRs the Actions reviewer reviews (#206). The reviewer itself opens none.
AUTHORS = {f"productswarm-{r}[bot]" for r in ("planner", "builder", "docs")}
EVENTS = {"pull_request", "workflow_dispatch"}


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
    n = pr.get("number")
    if not isinstance(n, int):
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
    sha = (pr.get("head") or {}).get("sha") or ""
    if not sha:
        return False, n, f"PR #{n} has no head SHA"
    if sha in watch.reviewed_heads(get_reviews(n)):
        return False, n, f"PR #{n}: the reviewer already reviewed head {sha[:7]}"
    return True, n, f"PR #{n} by {author}: head {sha[:7]} not reviewed by the reviewer"


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


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="actions_review.py", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="should this PR event start a reviewer run? (secret-free)")
    args = p.parse_args(argv)
    if args.cmd == "check":
        return check()
    return 2


if __name__ == "__main__":
    sys.exit(main())
