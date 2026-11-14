"""The effort labelled set: build it, draft its labels, and take the owner's review (#1011).

    python3 classify/effort_data.py build [--live] [--model M] [--from FILE]
    python3 classify/effort_data.py review [--force]
    python3 classify/effort_data.py apply
    python3 classify/effort_data.py check

build   fetches every PR merged up to the cut-off (CUTOFF, UTC, inclusive) and adds the ones not
        yet in data/effort.jsonl. The model drafts each new item's label and fix flag (one sample,
        up to MAX_TRIES if a reply names no label), and the item is `labelled_by: draft`. A
        draft is never gold: `swarm classify eval` leaves drafts out. New items get a split,
        30% test, stratified by draft label and merge month. Items already in the file are kept
        as they are. --live calls the model on the owner's Claude Code login, capped at
        PER_PR_USD per PR (GOV-0045), and records every reply in
        recordings/effort-draft/<model>.jsonl. Without --live it replays those recordings and
        calls nothing. --from reads the PRs from a JSON Lines file instead of GitHub.
review  writes review/effort.md, the file the owner edits: test items first, each with its draft
        label, the model's evidence and four lines to edit (label, fix, hard, reviewed). It
        refuses to overwrite edits not yet applied, unless --force.
apply   reads review/effort.md back. An item marked `reviewed: yes` takes the owner's label
        and fix and becomes `labelled_by: owner`. An item given a `hard: <rule>` tag moves to
        the test split, and a draft test item with the same label moves to dev in its place, so
        the split stays 70/30. It then rewrites the review file from the result.
check   says how far the labelled set is from #1011's criteria, and exits 1 until they hold.

Standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

import classifier
import labelset as lsmod

HERE = Path(__file__).resolve().parent
NAME = "effort"
REPO = "open-agentos/productswarm"
CUTOFF = "2026-11-13"        # PRs merged on or before this UTC day are in the set
FIX_DAYS = 14                # the fix flag: fixes something merged this many days before
TEST_SHARE = 0.3
PER_PR_USD = 0.25            # GOV-0045's cap per PR classified
MAX_TRIES = 3                # draft samples per PR, until one names a label
DEFAULT_MODEL = "claude-haiku-5-5"
BODY_MAX = 2500
PATHS_MAX = 40
OWNER = "owner"
FIELDS = ("label", "fix", "hard", "reviewed")

QUERY = """query($owner: String!, $name: String!, $endCursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequests(states: MERGED, first: 50, after: $endCursor,
                 orderBy: {field: CREATED_AT, direction: ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes { number title body mergedAt
              files(first: 100) { totalCount nodes { path } }
              closingIssuesReferences(first: 5) { nodes { number title } } }
    }
  }
}"""


class Problem(RuntimeError):
    """The command can't do what was asked; the message says why."""


# ---------------------------------------------------------------- PRs to items

def fetch_github(repo: str = REPO) -> list[dict]:
    """Every merged PR of repo, as GitHub's GraphQL API gives them."""
    owner, name = repo.split("/")
    r = subprocess.run(["gh", "api", "graphql", "--paginate", "-F", f"owner={owner}",
                        "-F", f"name={name}", "-f", f"query={QUERY}",
                        "--jq", ".data.repository.pullRequests.nodes[]"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise Problem(f"gh api graphql failed: {r.stderr.strip()[:300]}")
    return [json.loads(line) for line in r.stdout.splitlines() if line.strip()]


def read_prs(path: Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()]


def merged_on_or_before(pr: dict, day: str = CUTOFF) -> bool:
    return bool(pr.get("mergedAt")) and pr["mergedAt"][:10] <= day


def iso_week(stamp: str) -> str:
    y, w, _ = dt.date.fromisoformat(stamp[:10]).isocalendar()
    return f"{y}-W{w:02d}"


def item_text(pr: dict) -> str:
    """What the classifier reads for one PR: title, linked issues, paths touched and body."""
    issues = (pr.get("closingIssuesReferences") or {}).get("nodes") or []
    files = pr.get("files") or {}
    paths = [f["path"] for f in files.get("nodes") or []]
    total = max(files.get("totalCount") or 0, len(paths))
    shown = paths[:PATHS_MAX]
    more = total - len(shown)
    body = (pr.get("body") or "").replace("\r\n", "\n").strip()
    if len(body) > BODY_MAX:
        body = body[:BODY_MAX].rstrip() + " …"
    return "\n".join([
        f"Title: {pr['title'].strip()}",
        "Linked issue: " + ("; ".join(f"#{i['number']} {i['title'].strip()}" for i in issues)
                            or "none"),
        f"Paths touched ({total}): " + (", ".join(shown) or "none")
        + (f", and {more} more" if more > 0 else ""),
        "Body:",
        body or "(empty)",
    ])


def fixed_pr(pr: dict, merged: dict) -> Optional[int]:
    """The first PR that pr's title or body names (#N) and that merged in the FIX_DAYS before it."""
    at = dt.datetime.fromisoformat(pr["mergedAt"].replace("Z", "+00:00"))
    for n in re.findall(r"(?<![\w/])#(\d+)\b", f"{pr['title']}\n{pr.get('body') or ''}"):
        other = merged.get(int(n))
        if not other or other["number"] == pr["number"]:
            continue
        then = dt.datetime.fromisoformat(other["mergedAt"].replace("Z", "+00:00"))
        if dt.timedelta(0) <= at - then <= dt.timedelta(days=FIX_DAYS):
            return other["number"]
    return None


def pr_number(item_id: str) -> int:
    return int(item_id.split("-", 1)[1])


def rule_names(ls: lsmod.LabelSet) -> list[str]:
    """Each boundary rule's name: the `name:` it starts with."""
    out = []
    for lb in ls.labels:
        for rule in lb.boundary:
            m = re.match(r"([a-z0-9-]+):\s", rule)
            if m:
                out.append(m.group(1))
    return out


# ---------------------------------------------------------------- drafting

def as_item(row: dict) -> lsmod.Item:
    return lsmod.Item(row["id"], row["text"], row.get("label", ""), row.get("split", "dev"),
                      row.get("labelled_by", lsmod.DRAFT), dict(row.get("flags", {})),
                      row.get("week"))


def draft_one(ls, system: str, row: dict, rec: classifier.Recordings, live: bool,
              cap: Optional[classifier.Cap], model: str, runner: Callable) -> Optional[dict]:
    """The first sample that names a label ({"label", "flags", "evidence"}), or None."""
    user = classifier.user_prompt(as_item(row))
    key = classifier.prompt_hash(system, user)
    for k in range(MAX_TRIES):
        reply = rec.get(row["id"], key, k)
        if reply is None:
            if not live:
                return None
            budget = min(PER_PR_USD, cap.take())
            reply, cost = runner(model, system, user, budget)
            cap.spent += cost
            rec.add(row["id"], key, k, reply)
        parsed = classifier.parse_reply(ls, reply)
        if parsed:
            return parsed
    return None


def drafter(ls, root: Path, model: str, live: bool = False, runner: Callable = None,
            n_items: int = 0):
    """A function row -> draft (or None), recording to or replaying from recordings/."""
    rec = classifier.Recordings(root / "recordings", f"{NAME}-draft", model)
    cap = classifier.Cap(MAX_TRIES * n_items, PER_PR_USD * n_items) if live else None
    system = classifier.system_prompt(ls)
    runner = runner or classifier.claude_runner
    return lambda row: draft_one(ls, system, row, rec, live, cap, model, runner)


# ---------------------------------------------------------------- the labelled set file

def id_hash(item_id: str) -> str:
    return hashlib.sha256(item_id.encode()).hexdigest()


def read_rows(path: Path) -> dict:
    """The labelled set's rows by id, as plain dicts (empty if there is no file yet)."""
    if not path.exists():
        return {}
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            rows[d["id"]] = d
    return rows


ROW_ORDER = ("id", "label", "flags", "fixes", "labelled_by", "split", "hard", "week", "text")


def write_rows(path: Path, rows: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for item_id in sorted(rows, key=pr_number):
        r = rows[item_id]
        lines.append(json.dumps({k: r[k] for k in ROW_ORDER if k in r}, ensure_ascii=False))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def assign_splits(rows: list[dict]) -> None:
    """Give each row a split: TEST_SHARE of them test, spread evenly over (label, month) by
    taking every k-th row in that order, so each stratum gets its share."""
    order = sorted(rows, key=lambda r: (r["label"], r["merged"][:7], id_hash(r["id"])))
    for i, r in enumerate(order):
        r["split"] = "test" if int((i + 1) * TEST_SHARE) > int(i * TEST_SHARE) else "dev"


def build(root: Path, prs: list[dict], live: bool, model: str, runner: Callable = None,
          say: Callable = print) -> int:
    ls = lsmod.load_labelset(root / "labelsets" / f"{NAME}.yml")
    path = root / "data" / f"{NAME}.jsonl"
    rows = read_rows(path)
    prs = [p for p in prs if merged_on_or_before(p)]
    merged = {p["number"]: p for p in prs}
    new = [p for p in sorted(prs, key=lambda p: p["number"]) if f"pr-{p['number']}" not in rows]
    draft = drafter(ls, root, model, live, runner, len(new))
    added, missing = [], []
    try:
        for p in new:
            row = {"id": f"pr-{p['number']}", "text": item_text(p), "week": iso_week(p["mergedAt"]),
                   "merged": p["mergedAt"], "labelled_by": lsmod.DRAFT}
            d = draft(row)
            if d is None:
                missing.append(row["id"])
                continue
            row["label"], row["flags"] = d["label"], {"fix": d["flags"]["fix"]}
            n = fixed_pr(p, merged) if d["flags"]["fix"] else None
            if n:
                row["fixes"] = n
            added.append(row)
    except classifier.CapReached as e:
        say(f"effort_data build: {e}; the items drafted so far are kept")
    except classifier.ModelError as e:
        say(f"effort_data build: {e}; the items drafted so far are kept")
    assign_splits(added)
    for row in added:
        row.pop("merged", None)
        rows[row["id"]] = row
    write_rows(path, rows)
    say(f"effort_data build: {len(prs)} PRs merged up to {CUTOFF}; {len(added)} added, "
        f"{len(rows)} in {path}")
    if missing:
        say(f"effort_data build: no draft for {len(missing)} PRs ("
            + ", ".join(missing[:10]) + (", …" if len(missing) > 10 else "")
            + ("); run it again" if live else "); --live drafts them"))
        return 1
    return 0


# ---------------------------------------------------------------- the review file

REVIEW_HEAD = f"""# Effort review: the owner's pass on the labelled set

Edit the four lines under each PR, then run `python3 classify/effort_data.py apply`.

- `label:` one of LABELS.
- `fix:` `no`, or `#N` when the PR fixes PR #N, merged in the {FIX_DAYS} days before it
  (`yes` if you don't know N).
- `hard:` blank, or the boundary rule this PR tests: RULES.
  A PR tagged `hard` moves to the test split.
- `reviewed:` `yes` makes your label and fix gold (`labelled_by: owner`). Leave it `no` and the
  draft stays a draft, which never counts.

Every test item needs `reviewed: yes` (#1011). Dev items are optional. The draft line is the
model's guess and its evidence: it is there to save time, not to agree with.
"""


def fix_field(row: dict) -> str:
    if row.get("fixes"):
        return f"#{row['fixes']}"
    return "yes" if row.get("flags", {}).get("fix") else "no"


def fields_of(row: dict) -> dict:
    return {"label": row["label"], "fix": fix_field(row), "hard": row.get("hard", ""),
            "reviewed": "yes" if row["labelled_by"] == OWNER else "no"}


def head_lines(text: str) -> tuple[list[str], str]:
    """(the title, issue and paths lines, the body) of an item's text."""
    head, _, body = text.partition("\nBody:\n")
    return head.splitlines(), body


def render_review(ls, rows: dict, draft: Callable) -> str:
    out = [REVIEW_HEAD.replace("LABELS", ", ".join(ls.label_names))
           .replace("RULES", ", ".join(rule_names(ls)))]
    for split in ("test", "dev"):
        ids = sorted((i for i in rows if rows[i]["split"] == split), key=pr_number)
        done = sum(rows[i]["labelled_by"] == OWNER for i in ids)
        out += [f"# {split.capitalize()} split: {len(ids)} PRs, {done} reviewed", ""]
        for i in ids:
            r = rows[i]
            n = pr_number(i)
            head, body = head_lines(r["text"])
            title = head[0].removeprefix("Title: ")
            excerpt = " ".join(body.split())
            excerpt = excerpt[:300] + (" …" if len(excerpt) > 300 else "")
            d = draft(r)
            guess = (f"{d['label']}, fix {'yes' if d['flags']['fix'] else 'no'}. "
                     f"\"{d['evidence']}\"" if d else "(no recorded draft for this label set)")
            out += [f"## {i} · {split} · {r.get('week', '')}", "",
                    f"[#{n}](https://github.com/{REPO}/pull/{n}) {title}  ",
                    *(f"{h}  " for h in head[1:]),
                    f"> {excerpt}", "",
                    f"Draft: {guess}", ""]
            out += [f"{k}: {v}".rstrip() for k, v in fields_of(r).items()]
            out.append("")
    return "\n".join(out)


def parse_review(text: str) -> tuple[dict, list[str]]:
    """({id: {field: value}}, problems) from the review file."""
    blocks, problems, cur = {}, [], None
    for n, line in enumerate(text.splitlines(), 1):
        m = re.match(r"## (pr-\d+) · ", line)
        if m:
            cur = m.group(1)
            if cur in blocks:
                problems.append(f"line {n}: {cur} appears twice")
            blocks[cur] = {}
            continue
        m = re.match(r"(label|fix|hard|reviewed):(.*)$", line)
        if m and cur:
            if m.group(1) in blocks[cur]:
                problems.append(f"line {n}: {cur} has two '{m.group(1)}' lines")
            blocks[cur][m.group(1)] = m.group(2).strip()
    for i, b in blocks.items():
        lost = [f for f in FIELDS if f not in b]
        if lost:
            problems.append(f"{i}: no '{lost[0]}' line")
    return blocks, problems


def changes(ls, rows: dict, blocks: dict) -> tuple[dict, list[str]]:
    """({id: new fields}, problems) for the blocks that differ from the labelled set."""
    rules, out, p = rule_names(ls), {}, []
    for i, b in blocks.items():
        if i not in rows:
            p.append(f"{i}: not in the labelled set")
            continue
        if any(f not in b for f in FIELDS):
            continue
        if b == fields_of(rows[i]):
            continue
        if b["label"] not in ls.label_names:
            p.append(f"{i}: label '{b['label']}' isn't one of {', '.join(ls.label_names)}")
        if not re.fullmatch(r"no|yes|#\d+", b["fix"]):
            p.append(f"{i}: fix must be no, yes or #N, not '{b['fix']}'")
        if b["hard"] and b["hard"] not in rules:
            p.append(f"{i}: hard '{b['hard']}' isn't a boundary rule ({', '.join(rules)})")
        if b["reviewed"] not in ("yes", "no"):
            p.append(f"{i}: reviewed must be yes or no")
        was = fields_of(rows[i])
        if b["reviewed"] == "no":
            if was["reviewed"] == "yes":
                p.append(f"{i}: an owner label can't go back to a draft")
            elif (b["label"], b["fix"]) != (was["label"], was["fix"]):
                p.append(f"{i}: label or fix changed but reviewed is no; set reviewed: yes")
        out[i] = b
    return out, p


def plant(rows: dict, item_id: str, say: Callable) -> None:
    """Move a hard case to test, and a draft test item with its label (same month if one
    exists) to dev in its place."""
    r = rows[item_id]
    if r["split"] == "test":
        return
    r["split"] = "test"
    pool = [x for x in rows.values() if x["split"] == "test" and x["labelled_by"] == lsmod.DRAFT
            and not x.get("hard") and x["label"] == r["label"]]
    pool.sort(key=lambda x: (x.get("week", "")[:7] != r.get("week", "")[:7], id_hash(x["id"])))
    if pool:
        pool[0]["split"] = "dev"
    else:
        say(f"effort_data apply: no draft {r['label']} test item to swap for {item_id}; "
            f"the test split grew by one")


def apply(root: Path, say: Callable = print) -> int:
    ls = lsmod.load_labelset(root / "labelsets" / f"{NAME}.yml")
    path, review = root / "data" / f"{NAME}.jsonl", root / "review" / f"{NAME}.md"
    rows = read_rows(path)
    if not review.exists():
        raise Problem(f"no {review}; `effort_data.py review` writes it")
    blocks, problems = parse_review(review.read_text(encoding="utf-8"))
    edits, more = changes(ls, rows, blocks)
    problems += more
    if problems:
        raise Problem("nothing applied:\n  " + "\n  ".join(problems))
    reviewed = hard = 0
    for i, b in edits.items():
        r, was = rows[i], fields_of(rows[i])
        if b["reviewed"] == "yes":
            reviewed += (b["reviewed"], b["label"], b["fix"]) != \
                (was["reviewed"], was["label"], was["fix"])
            r["label"], r["labelled_by"] = b["label"], OWNER
            r["flags"] = {"fix": b["fix"] != "no"}
            r.pop("fixes", None)
            if b["fix"].startswith("#"):
                r["fixes"] = int(b["fix"][1:])
        if b["hard"] != r.get("hard", ""):
            hard += 1
            if b["hard"]:
                r["hard"] = b["hard"]
            else:
                r.pop("hard", None)
    for i in sorted(edits, key=pr_number):
        if rows[i].get("hard"):
            plant(rows, i, say)
    write_rows(path, rows)
    lsmod.load_items(path, ls)   # the result must still load
    review.write_text(render_review(ls, rows, replay_drafter(ls, root)), encoding="utf-8")
    say(f"effort_data apply: {reviewed} labels made gold, {hard} hard tags changed; "
        f"wrote {path.name} and rewrote {review.name}")
    return 0


def replay_drafter(ls, root: Path, model: str = DEFAULT_MODEL) -> Callable:
    return drafter(ls, root, model, live=False)


def write_review(root: Path, force: bool = False, model: str = DEFAULT_MODEL,
                 say: Callable = print) -> int:
    ls = lsmod.load_labelset(root / "labelsets" / f"{NAME}.yml")
    rows = read_rows(root / "data" / f"{NAME}.jsonl")
    if not rows:
        raise Problem("the labelled set is empty; `effort_data.py build` fills it")
    review = root / "review" / f"{NAME}.md"
    if review.exists() and not force:
        blocks, _ = parse_review(review.read_text(encoding="utf-8"))
        edited = [i for i, b in blocks.items() if i in rows and b != fields_of(rows[i])]
        if edited:
            raise Problem(f"{review} has edits not yet applied ({', '.join(edited[:5])}); "
                          f"run apply, or pass --force to discard them")
    review.parent.mkdir(parents=True, exist_ok=True)
    review.write_text(render_review(ls, rows, drafter(ls, root, model)), encoding="utf-8")
    say(f"effort_data review: wrote {review}")
    return 0


# ---------------------------------------------------------------- check

def check(root: Path, say: Callable = print) -> int:
    ls = lsmod.load_labelset(root / "labelsets" / f"{NAME}.yml")
    items = lsmod.load_items(root / "data" / f"{NAME}.jsonl", ls)
    test = [it for it in items if it.split == "test"]
    rules = rule_names(ls)
    unreviewed = [it for it in test if it.labelled_by != OWNER]
    per_rule = {r: sum(it.hard == r for it in test) for r in rules}
    stray = sorted({it.hard for it in items if it.hard and it.hard not in rules})
    ok = True

    def line(good: bool, text: str) -> None:
        nonlocal ok
        ok = ok and good
        say(f"[{'ok' if good else '  '}] {text}")

    say(f"{len(items)} PRs merged up to {CUTOFF}: {len(items) - len(test)} dev, {len(test)} test "
        f"({len(test) / max(len(items), 1):.0%})")
    line(not unreviewed, f"test items labelled by the owner: {len(test) - len(unreviewed)} of "
         f"{len(test)}")
    for r in rules:
        line(per_rule[r] >= 5, f"hard cases for {r} in the test split: {per_rule[r]} (5 needed)")
    if stray:
        line(False, f"hard tags that name no boundary rule: {', '.join(stray)}")
    return 0 if ok else 1


# ---------------------------------------------------------------- command line

def main(argv: list[str], say: Callable = print, runner: Callable = None) -> int:
    ap = argparse.ArgumentParser(prog="effort_data.py", description=__doc__.split("\n")[0])
    ap.add_argument("--dir", default=str(HERE), help="the classify directory (default: classify/)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="add every PR merged up to the cut-off, with draft labels")
    b.add_argument("--live", action="store_true", help="call the model (GOV-0045)")
    b.add_argument("--model", default=DEFAULT_MODEL)
    b.add_argument("--from", dest="source", help="read the PRs from this JSON Lines file")
    r = sub.add_parser("review", help="write review/effort.md for the owner")
    r.add_argument("--force", action="store_true", help="discard edits not yet applied")
    r.add_argument("--model", default=DEFAULT_MODEL, help="whose draft replies to show")
    sub.add_parser("apply", help="take the owner's edits from review/effort.md")
    sub.add_parser("check", help="how far the labelled set is from #1011's criteria")
    args = ap.parse_args(argv)
    root = Path(args.dir)
    try:
        if args.cmd == "build":
            prs = read_prs(Path(args.source)) if args.source else fetch_github()
            return build(root, prs, args.live, args.model, runner, say)
        if args.cmd == "review":
            return write_review(root, args.force, args.model, say)
        if args.cmd == "apply":
            return apply(root, say)
        return check(root, say)
    except (Problem, lsmod.FormatError, ValueError) as e:
        say(f"effort_data {args.cmd}: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
