#!/usr/bin/env python3
"""The cost check on red (#330, part C of the owner's ruling on #311).

The ruling: after the first 5 builder-App reds under the new reviewer rule, revisit the rule
if more than 2 of them reach GOV-0011's 2-round bound. This counts them, so the owner can
see it without reading PRs one by one. It measures what red costs, not whether red is
right, so it isn't part of the C stage 2 bar (evals/README.md).

- **Start:** the merge time of the PR that closes #329 (the reviewer prompt, part A),
  looked up from GitHub. Before that merges it counts nothing.
- **A red:** a `CHANGES_REQUESTED` review by the reviewer App, submitted after the start,
  on a PR the builder App opened. A PR counts once however many reds it gets; the first
  5 PRs by the time of their first red are counted.
- **The bound:** the rule `dashboard/generate.py`'s `needs_owner()` uses, `past_bound()`.

Read-only: every GitHub call goes through `gather.gh()`, which refuses anything that could
write. It prints PR numbers, states, counts and block numbers only, no review text, and no
cost figures (evals/README.md); it doesn't read `watch.json`.

Run: python3 evals/red_check.py [--repo OWNER/NAME]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "dashboard"))
import gather  # noqa: E402
import generate  # noqa: E402

START_ISSUE = 329   # the reviewer prompt (#311 part A); reds count from its PR's merge
COUNT = 5           # #311: the first 5 builder-App reds under the new rule ...
REVISIT_OVER = 2    # ... revisit if more than 2 reach the bound. Changing these is the owner's call.

BLOCK_RE = re.compile(r"\bBlock\s+(\d)\b")

FIXED = "fixed in {n} round{s}"
BOUND = "reached the bound"
STILL_OPEN = "still open"
SKIPPED = "not responded: [respond] skips it"
ENDED_RED = "ended while red"


# ---------------------------------------------------------------- reading GitHub

def fetch(repo: str) -> dict:
    """The start PR and every builder-App PR updated since, with its reviews."""
    refs = gather.gh_json("issue", "view", str(START_ISSUE), "--repo", repo,
                          "--json", "closedByPullRequestsReferences")
    merged = []
    for ref in refs.get("closedByPullRequestsReferences") or []:
        p = gather.gh_json("pr", "view", str(ref["number"]), "--repo", repo,
                           "--json", "number,mergedAt,closingIssuesReferences")
        merged.append(p)
    start = start_of(merged)
    if start is None:
        return {"start": None, "prs": []}
    prs = gather.gh_json("pr", "list", "--repo", repo, "--state", "all",
                         "--author", "app/" + generate.BUILDER,
                         "--search", f"updated:>={start['mergedAt'][:10]}", "--limit", "1000",
                         "--json", "number,state,author,closingIssuesReferences")
    for p in prs:
        p["reviews"] = gather.gh_api_list(f"repos/{repo}/pulls/{p['number']}/reviews?per_page=100")
    return {"start": start, "prs": prs}


# ---------------------------------------------------------------- counting (pure)

def closes(pr: dict) -> list[int]:
    return [c["number"] for c in pr.get("closingIssuesReferences") or []]


def start_of(prs: list[dict]) -> dict | None:
    """The earliest merged PR that closes START_ISSUE, or None if none has merged."""
    done = [p for p in prs if p.get("mergedAt") and START_ISSUE in closes(p)]
    return min(done, key=lambda p: generate.parse_ts(p["mergedAt"])) if done else None


def outcome(pr: dict, reds: list[dict], last: dict) -> str:
    """How one counted PR's reds ended. `reds` and `last` are the reviewer App's reviews
    after the start: its reds, and its latest review of any state."""
    n = len(reds)
    if generate.past_bound(n):
        return BOUND
    if len(closes(pr)) != 1:
        return SKIPPED     # launcher/README.md: [respond] skips a PR that doesn't close one issue
    if last.get("state") != generate.CHANGES:
        return FIXED.format(n=n, s="" if n == 1 else "s")
    return STILL_OPEN if pr["state"].lower() == "open" else ENDED_RED


def count(data: dict) -> list[dict]:
    """The first COUNT builder-App PRs with a red after the start, oldest first red first."""
    if data["start"] is None:
        return []
    start = generate.parse_ts(data["start"]["mergedAt"])
    rows = []
    for pr in data["prs"]:
        if generate.pr_role((pr.get("author") or {}).get("login")) != "builder":
            continue
        mine = [r for r in pr.get("reviews") or []
                if (r.get("user") or {}).get("login") == generate.REVIEWER
                and (generate.parse_ts(r.get("submitted_at")) or start) > start]
        mine.sort(key=lambda r: generate.parse_ts(r["submitted_at"]))
        reds = [r for r in mine if r.get("state") == generate.CHANGES]
        if not reds:
            continue
        state = pr["state"].lower()
        result = outcome(pr, reds, mine[-1])
        blocks = sorted({int(b) for r in reds for b in BLOCK_RE.findall(r.get("body") or "")})
        rows.append({"number": pr["number"], "state": state, "reds": len(reds),
                     "blocks": blocks, "outcome": result,
                     "settled": state in ("merged", "closed") or result == BOUND,
                     "first": generate.parse_ts(reds[0]["submitted_at"])})
    rows.sort(key=lambda r: (r["first"], r["number"]))
    return rows[:COUNT]


def report(data: dict, rows: list[dict]) -> list[str]:
    lines = []
    if data["start"] is None:
        lines.append(f"#{START_ISSUE} hasn't merged yet, so no reds count yet.")
    else:
        lines.append(f"counting from PR #{data['start']['number']} (closes #{START_ISSUE}), "
                     f"merged {data['start']['mergedAt']}")
    for r in rows:
        blocks = f" (block {', '.join(map(str, r['blocks']))})" if r["blocks"] else ""
        lines.append(f"PR #{r['number']}  {r['state']}  {r['reds']} "
                     f"red{'' if r['reds'] == 1 else 's'}{blocks}  {r['outcome']}")
    at_bound = sum(r["outcome"] == BOUND for r in rows)
    lines.append(f"red check (#311): {len(rows)} of {COUNT} counted, {at_bound} reached the "
                 f"{generate.ROUNDS}-round bound; revisit if more than {REVISIT_OVER}")
    if len(rows) == COUNT and all(r["settled"] for r in rows):
        lines.append(f"revisit: {'yes' if at_bound > REVISIT_OVER else 'no'}")
    return lines


# ---------------------------------------------------------------- CLI

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Count the first builder-App reds under #311's "
                                             "rule and how many reach the round bound.")
    ap.add_argument("--repo", help="owner/name (default: this checkout's origin)")
    args = ap.parse_args(argv)
    repo = args.repo or generate.default_repo()
    if not repo:
        print("red_check.py: can't tell the repo; pass --repo owner/name", file=sys.stderr)
        return 2
    try:
        data = fetch(repo)
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError) as e:
        print(f"red_check.py: {e}", file=sys.stderr)
        return 1
    print("\n".join(report(data, count(data))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
