"""The dashboard's v3 progress section (#357, part 5 of #348).

Shows where each GOV-0015 stage stands, the eval bar's result, the planted-defect gate (#331)
and the red check's count (#330). Read-only, and needs no new token permission:

- **Stages** come from PRODUCT.md's v3 tables in the checkout. Each stage's issue states come
  from one GraphQL query (`issues: read`), since closed ones may be older than `--days`.
- **The eval bar** is the `**Result: …**` line under "Against the bar" in `evals/results.md`.
- **The gate** is #331's state. Its result comment has no fixed wording, so it isn't parsed.
- **The red check** calls `evals/red_check.py`'s own `fetch()`, `count()` and `summary()`.
  red_check imports `generate` at load, so it's imported inside `_red_check()`, never at
  this module's load, which would make a cycle with `generate`. It shows no cost, and nor
  does this section (evals/README.md).

`fetch()` reads GitHub and the checkout; `build()` and `render()` are pure.
"""
from __future__ import annotations

import html
import re
import subprocess
import sys
from pathlib import Path

import ghql

ROOT = Path(__file__).resolve().parent.parent
GATE_ISSUE = 331        # the planted-defect gate
RED_ISSUE = 330         # the red check
RESULTS = "evals/results.md"

V3_RE = re.compile(r"^## v3\b.*?(?=^## |\Z)", re.M | re.S)
STAGE_RE = re.compile(r"^### Stage\s+(.+?)\s*$", re.M)
DONE_RE = re.compile(r"\s*\(done\)\s*$", re.I)
NOT_PLANNED_RE = re.compile(r"C stage 2\b[^.]*\bnot planned", re.I)
BAR_RE = re.compile(r"^#+\s*Against the bar\b.*?(?=^#+\s|\Z)", re.M | re.S)
RESULT_RE = re.compile(r"^\*\*Result:\s*(.+?)\.?\*\*", re.M)
NUM_RE = re.compile(r"#(\d+)")

ERRORS = (RuntimeError, OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError)
UNREAD = "couldn't read (see the build log)"


# ---------------------------------------------------------------- parsing (pure)

def cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_stages(product: str) -> list[dict]:
    """GOV-0015's stages from PRODUCT.md's v3 section: one per `### Stage …` heading, with
    the issue numbers in its table's `Issue` column. Rows with no `#N` there are skipped."""
    m = V3_RE.search(product or "")
    if not m:
        return []
    v3 = m.group(0)
    heads = list(STAGE_RE.finditer(v3))
    stages = []
    for i, h in enumerate(heads):
        body = v3[h.end():heads[i + 1].start() if i + 1 < len(heads) else len(v3)]
        body = re.split(r"^#{1,3} ", body, maxsplit=1, flags=re.M)[0]
        issues, col = [], None
        for line in body.splitlines():
            if not line.lstrip().startswith("|"):
                col = None
                continue
            row = cells(line)
            if col is None:
                col = row.index("Issue") if "Issue" in row else -1
                continue
            if col < 0 or col >= len(row) or set(row[col]) <= set("-: "):
                continue
            n = NUM_RE.search(row[col])
            if n:
                issues.append(int(n.group(1)))
        name = DONE_RE.sub("", h.group(1))
        stages.append({"name": name, "done": bool(DONE_RE.search(h.group(1))), "issues": issues})
    return stages


def c_stage_2(product: str) -> str:
    m = V3_RE.search(product or "")
    return "not planned (GOV-0015)" if m and NOT_PLANNED_RE.search(m.group(0)) else "see PRODUCT.md"


def bar_result(results: str | None) -> str | None:
    """The `**Result: …**` line under "Against the bar", or None if it can't be found."""
    sec = BAR_RE.search(results or "")
    m = RESULT_RE.search(sec.group(0)) if sec else None
    return m.group(1).strip() if m else None


# ---------------------------------------------------------------- reading

def _red_check():
    """evals/red_check.py, imported here rather than at load: it imports `generate`."""
    evals = str(ROOT / "evals")
    if evals not in sys.path:
        sys.path.insert(0, evals)
    import red_check
    return red_check


def issue_states(repo: str, numbers: list[int], gh_json) -> dict[int, str]:
    """{number: "OPEN" | "CLOSED" | "MERGED"} in one GraphQL query."""
    if not numbers:
        return {}
    owner, name = repo.split("/", 1)
    fields = " ".join(f"i{n}: issueOrPullRequest(number: {n}) "
                      "{ ... on Issue { state } ... on PullRequest { state } }" for n in numbers)
    q = f"query($owner: String!, $name: String!) {{ repository(owner: $owner, name: $name) {{ {fields} }} }}"
    data = gh_json("api", "graphql", "-f", f"query={q}", "-f", f"owner={owner}", "-f", f"name={name}")
    repo_data = (data or {}).get("data", {}).get("repository") or {}
    return {n: (repo_data.get(f"i{n}") or {}).get("state") for n in numbers
            if (repo_data.get(f"i{n}") or {}).get("state")}


def read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


REVIEWS_FIELD = ("p%d: pullRequest(number: %d) { reviews(first: 100) { totalCount nodes "
                 "{ author { login __typename } submittedAt state body } } }")


def red_reviews(repo: str, numbers: list[int]) -> dict[int, list[dict]]:
    """The red check's reviews in REST's shape (the fields it reads), from one GraphQL query
    per 20 PRs instead of one REST call per PR (#392). PRs with more than 100 reviews, or
    that the query didn't return, are left out, so red_check reads them over REST."""
    out = {}
    for n, pr in ghql.batched(repo, numbers, REVIEWS_FIELD, 20).items():
        nodes = ghql.complete((pr or {}).get("reviews"))
        if nodes is not None:
            out[n] = [{"user": {"login": ghql.login(x.get("author"))}, "submitted_at": x.get("submittedAt"),
                       "state": x.get("state"), "body": x.get("body") or ""} for x in nodes]
    return out


def fetch(repo: str, gh_json, root: Path = ROOT) -> dict:
    """Everything the section needs. A part that fails to read is recorded as an error, so
    one bad call doesn't stop the page from publishing."""
    product = read(root / "PRODUCT.md") or ""
    out = {"product": product, "results": read(root / RESULTS), "states": None, "red": None,
           "errors": {}}
    numbers = sorted({n for s in parse_stages(product) for n in s["issues"]} | {GATE_ISSUE})
    try:
        out["states"] = issue_states(repo, numbers, gh_json)
    except ERRORS as e:
        out["errors"]["states"] = str(e)
        print(f"progress.py: issue states: {e}", file=sys.stderr)
    try:
        out["red"] = _red_check().fetch(repo, reviews=lambda ns: red_reviews(repo, ns))
    except ERRORS as e:
        out["errors"]["red"] = str(e)
        print(f"progress.py: red check: {e}", file=sys.stderr)
    return out


# ---------------------------------------------------------------- the model (pure)

def build(data: dict) -> dict:
    states = data.get("states")
    stages = []
    for s in parse_stages(data.get("product") or ""):
        known = states is not None
        stages.append({**s, "known": known,
                       "closed": [n for n in s["issues"] if (states or {}).get(n) in ("CLOSED", "MERGED")],
                       "open": [n for n in s["issues"] if (states or {}).get(n) == "OPEN"]})
    if states is None:
        gate = None
    else:
        gate = {"OPEN": "not run", "CLOSED": f"done, see #{GATE_ISSUE}"}.get(states.get(GATE_ISSUE))

    red = None
    if data.get("red") is not None:
        rc = _red_check()
        rows = rc.count(data["red"])
        start = data["red"].get("start")
        red = {**rc.summary(rows), "of": rc.COUNT, "over": rc.REVISIT_OVER,
               "rounds": rc.generate.ROUNDS, "start_issue": rc.START_ISSUE,
               "start_pr": start["number"] if start else None}
    return {"stages": stages, "c2": c_stage_2(data.get("product") or ""),
            "bar": bar_result(data.get("results")), "gate": gate, "red": red}


# ---------------------------------------------------------------- HTML

def esc(x) -> str:
    return html.escape(str(x), quote=True)


def link(repo: str, n: int) -> str:
    return f'<a href="https://github.com/{esc(repo)}/issues/{n}">#{n}</a>'


def stage_status(s: dict, repo: str) -> str:
    if not s["issues"]:
        return "done" if s["done"] else "no issues listed"
    if not s["known"]:
        count = UNREAD
    else:
        count = f"{len(s['closed'])} of {len(s['issues'])} issues closed"
        if s["open"]:
            count += " · open: " + ", ".join(link(repo, n) for n in s["open"])
    return f"done · {count}" if s["done"] else count


def red_line(red: dict | None, repo: str) -> str:
    if red is None:
        return UNREAD
    if red["start_pr"] is None:
        return f"not started: no reds count until {link(repo, red['start_issue'])}'s PR merges"
    line = (f"{red['counted']} of {red['of']} reds counted, {red['at_bound']} reached the "
            f"{red['rounds']}-round bound; revisit if more than {red['over']}")
    verdict = {None: "not yet decided", True: "revisit: yes", False: "revisit: no"}[red["revisit"]]
    return f"{line} · {verdict}"


def render(p: dict, repo: str) -> str:
    rows = [f"<tr><td>{esc(s['name'])}</td><td>{stage_status(s, repo)}</td></tr>"
            for s in p["stages"]]
    rows.append(f"<tr><td>C stage 2</td><td>{esc(p['c2'])}</td></tr>")
    results_url = f"https://github.com/{esc(repo)}/blob/main/{RESULTS}"
    return "\n".join([
        "<h2>v3 progress</h2>",
        '<div class="scroll"><table><tr><th>Stage (GOV-0015)</th><th>Status</th></tr>'
        f'{"".join(rows)}</table></div>',
        "<ul>",
        f'<li><a href="{results_url}">Eval bar</a>: {esc(p["bar"] or "unknown")}</li>',
        f"<li>Planted-defect gate ({link(repo, GATE_ISSUE)}): {esc(p['gate'] or 'unknown')}</li>",
        f"<li>Red check ({link(repo, RED_ISSUE)}): {red_line(p['red'], repo)}</li>",
        "</ul>",
    ])
