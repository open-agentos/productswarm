#!/usr/bin/env python3
"""Pick the eval sample of merged PRs and gather what scoring needs (#173, v3 stage B).

Read-only: every GitHub call goes through `gh()` below, which only runs `gh pr list`,
`gh pr view`, `gh issue view` and plain GET `gh api`. It writes nothing to GitHub. The only
file it writes is `evals/data/sample.json`.

Sampling rule (fixed, not chosen by hand):

1. Start from every merged PR in the repo.
2. Keep a PR if `productswarm-reviewer[bot]` reviewed it, or if it closes one of the v1
   launcher issues #47 to #52 (L1 to L6 in PRODUCT.md's v1 table). The second part brings
   in the v1 PRs that merged with no reviewer pass.
3. Drop a PR that closes no issue, and a ruling PR: one whose changed files are all
   decision records or the index (`governance/decisions/`, `governance/INDEX.md`). Neither
   has a "Done when" to score.
4. If more than 20 are left, keep the 20 merged most recently.

For each PR it records: number, title, merged-at, head SHA at merge, the issues it closes
(and the first one's "Done when" / "Acceptance" section verbatim), every `GOV-NNNN` cited in
the PR body or that issue, files changed, and every reviewer review with its state, commit,
whether that commit is the merge head, and its `Overstep:` comments.

The output is sorted by PR number and carries no timestamp of its own, so re-running it on
the same GitHub state gives the same file. New merges after the file was written can change
the sample; the committed file is the fixed input #174 scores.

Run: python3 evals/gather.py [--repo OWNER/NAME] [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "sample.json"
DEFAULT_REPO = "open-agentos/productswarm"
REVIEWER = "productswarm-reviewer"
V1_ISSUES = frozenset(range(47, 53))
CAP = 20
GH_TIMEOUT = 60

GOV_RE = re.compile(r"\bGOV-\d{4}\b")
SECTION_NAMES = r"(?:done when|acceptance(?: criteria)?)"
HEADING_RE = re.compile(r"^(#{1,6})\s+" + SECTION_NAMES + r"\b.*$", re.I)
ANY_HEADING_RE = re.compile(r"^(#{1,6})\s+\S")
LABEL_RE = re.compile(r"^\*\*" + SECTION_NAMES + r":?\*\*:?", re.I)
ANY_LABEL_RE = re.compile(r"^\*\*[^*]+:?\*\*:?")
PARAGRAPH_RE = re.compile(r"^" + SECTION_NAMES + r"\b", re.I)
SIGNATURE_RE = re.compile(r"\n*^-- \S+ \([^)\n]*\)\s*\Z", re.M)


class ReadOnlyError(RuntimeError):
    pass


def check_read_only(args: list[str]) -> None:
    """Refuse any gh call that could write to GitHub."""
    if args[:2] in (["pr", "list"], ["pr", "view"], ["issue", "view"]):
        return
    if args[:1] == ["api"]:
        bad = {"-X", "--method", "-f", "-F", "--field", "--raw-field", "--input"}
        if not any(a in bad or a.split("=", 1)[0] in bad for a in args[1:]):
            return
    raise ReadOnlyError(f"refusing non-read-only gh call: gh {' '.join(args)}")


def gh(*args: str) -> str:
    check_read_only(list(args))
    r = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=GH_TIMEOUT)
    if r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def gh_json(*args: str):
    return json.loads(gh(*args))


def gh_api_list(path: str) -> list:
    """A paginated GET; `--slurp` gives one JSON array per page."""
    pages = gh_json("api", "--paginate", "--slurp", path)
    return [x for page in pages for x in page]


# --- pure helpers (tested with canned data) -------------------------------------------

def login(user: dict | None) -> str:
    """GraphQL gives bot logins without `[bot]`, REST with it; compare without."""
    name = (user or {}).get("login") or ""
    return name[:-5] if name.endswith("[bot]") else name


def _unsign(lines: list[str]) -> str | None:
    """Join a section's lines, without a trailing `-- role (model)` signature."""
    text = "\n".join(lines).strip()
    text = SIGNATURE_RE.sub("", text).strip()
    return text or None


def done_when(body: str | None) -> str | None:
    """The issue's "Done when" / "Acceptance" section, verbatim, or None.

    Three forms, tried in order:
    - a heading (`## Done when`): the lines after it up to the next heading at the same or
      a higher level;
    - a bold label (`**Done when:** ...`): that line and the lines after it up to the end
      of its paragraph, or the next heading or bold label;
    - a paragraph that starts with "Done when": that paragraph.

    A trailing `-- role (model)` signature is left out; the rest is verbatim.
    """
    lines = (body or "").replace("\r\n", "\n").split("\n")
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line.strip())
        if m:
            level = len(m.group(1))
            out = []
            for nxt in lines[i + 1:]:
                h = ANY_HEADING_RE.match(nxt.strip())
                if h and len(h.group(1)) <= level:
                    break
                out.append(nxt)
            return _unsign(out)
    for i, line in enumerate(lines):
        if LABEL_RE.match(line.strip()):
            out = [line]
            has_text = bool(LABEL_RE.sub("", line.strip()).strip())
            for nxt in lines[i + 1:]:
                s = nxt.strip()
                if ANY_HEADING_RE.match(s) or ANY_LABEL_RE.match(s) or (not s and has_text):
                    break
                has_text = has_text or bool(s)
                out.append(nxt)
            return _unsign(out)
    for i, line in enumerate(lines):
        if PARAGRAPH_RE.match(line.strip()):
            out = []
            for nxt in lines[i:]:
                if not nxt.strip():
                    break
                out.append(nxt)
            return _unsign(out)
    return None


def gov_ids(*texts: str | None) -> list[str]:
    return sorted({m for t in texts for m in GOV_RE.findall(t or "")})


def is_ruling_pr(files: list[str]) -> bool:
    return bool(files) and all(
        f.startswith("governance/decisions/") or f == "governance/INDEX.md" for f in files)


def closing_numbers(pr: dict) -> list[int]:
    return sorted(i["number"] for i in pr.get("closingIssuesReferences") or [])


def file_paths(pr: dict) -> list[str]:
    return sorted(f["path"] for f in pr.get("files") or [])


def reviewed_by_reviewer(pr: dict) -> bool:
    return any(login(r.get("author")) == REVIEWER for r in pr.get("reviews") or [])


def select_sample(prs: list[dict], cap: int = CAP) -> list[dict]:
    """Apply the sampling rule in the module docstring to `gh pr list` rows."""
    keep = []
    for pr in prs:
        if not pr.get("mergedAt"):
            continue
        closes = closing_numbers(pr)
        if not (reviewed_by_reviewer(pr) or V1_ISSUES & set(closes)):
            continue
        if not closes or is_ruling_pr(file_paths(pr)):
            continue
        keep.append(pr)
    keep.sort(key=lambda p: (p["mergedAt"], p["number"]), reverse=True)
    return sorted(keep[:cap], key=lambda p: p["number"])


def reviewer_reviews(reviews: list[dict], comments: list[dict], merge_head: str) -> list[dict]:
    """The reviewer's reviews (REST shape), oldest first, each with its `Overstep:` comments.

    `comments` are the reviewer's PR comments and inline review comments (REST shape). An
    inline comment belongs to the review whose id it carries. A PR comment belongs to the
    first review the reviewer submitted at or after it (the reviewer posts its `Overstep:`
    comments, then the review), or to the last review if none came after.
    """
    mine = sorted((r for r in reviews if login(r.get("user")) == REVIEWER),
                  key=lambda r: (r.get("submitted_at") or "", r["id"]))
    out = [{"id": r["id"], "state": r["state"], "submitted_at": r.get("submitted_at"),
            "commit_id": r.get("commit_id"), "at_merge_head": r.get("commit_id") == merge_head,
            "overstep_comments": []} for r in mine]
    if not out:
        return out
    by_id = {r["id"]: r for r in out}
    for c in sorted(comments, key=lambda c: (c.get("created_at") or "", c.get("id") or 0)):
        if login(c.get("user")) != REVIEWER or not (c.get("body") or "").lstrip().startswith("Overstep:"):
            continue
        entry = {"url": c.get("html_url"), "body": c["body"].strip()}
        target = by_id.get(c.get("pull_request_review_id"))
        if target is None:
            at = c.get("created_at") or ""
            target = next((r for r in out if (r["submitted_at"] or "") >= at), out[-1])
        target["overstep_comments"].append(entry)
    return out


def record(pr: dict, issue: dict | None, reviews: list[dict], comments: list[dict]) -> dict:
    """One sample.json entry from `gh pr view` JSON, the closed issue and REST reviews/comments."""
    issue = issue or {}
    return {
        "number": pr["number"],
        "title": pr["title"],
        "merged_at": pr["mergedAt"],
        "head_sha": pr["headRefOid"],
        "closed_issues": closing_numbers(pr),
        "issue": {
            "number": issue.get("number"),
            "title": issue.get("title"),
            "done_when": done_when(issue.get("body")),
        },
        "gov_ids": gov_ids(pr.get("body"), issue.get("body")),
        "files": file_paths(pr),
        "reviews": reviewer_reviews(reviews, comments, pr["headRefOid"]),
    }


# --- GitHub reads ----------------------------------------------------------------------

def gather(repo: str) -> list[dict]:
    rows = gh_json("pr", "list", "--repo", repo, "--state", "merged", "--limit", "1000",
                   "--json", "number,mergedAt,closingIssuesReferences,files,reviews")
    out = []
    for row in select_sample(rows):
        n = row["number"]
        pr = gh_json("pr", "view", str(n), "--repo", repo, "--json",
                     "number,title,mergedAt,headRefOid,body,closingIssuesReferences,files")
        closes = closing_numbers(pr)
        issue = gh_json("issue", "view", str(closes[0]), "--repo", repo,
                        "--json", "number,title,body") if closes else None
        reviews = gh_api_list(f"repos/{repo}/pulls/{n}/reviews?per_page=100")
        comments = (gh_api_list(f"repos/{repo}/issues/{n}/comments?per_page=100")
                    + gh_api_list(f"repos/{repo}/pulls/{n}/comments?per_page=100"))
        out.append(record(pr, issue, reviews, comments))
        print(f"#{n}: issue #{closes[0] if closes else '-'}, "
              f"{len(out[-1]['reviews'])} reviewer review(s)", file=sys.stderr)
    return sorted(out, key=lambda r: r["number"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)
    sample = gather(a.repo)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps({"repo": a.repo, "prs": sample}, indent=2, sort_keys=True) + "\n")
    print(f"wrote {len(sample)} PRs to {a.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
