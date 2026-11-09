#!/usr/bin/env python3
"""Render the needs-you list as short Markdown for a pinned GitHub issue (v3 F2, GOV-0015).

The owner reads it on GitHub mobile, so it only links: no tables (they scroll sideways on
a phone), short lines, and `#N` / `PR #N` references that GitHub turns into taps. It has
no write actions and runs no model. Its only write is `--update` (v3 F3): one PATCH of the
pinned digest issue's body, and only when the list changed.

It reuses generate.fetch(), build() and needs_you(), so the digest can't disagree with the
dashboard or `swarm inbox`. Like the dashboard, it reads only public GitHub data: local-only
state (`swarm.db` runs, held triggers, run cost) isn't on GitHub, so the digest doesn't
show it (GOV-0002, GOV-0004, GOV-0014).

    python3 dashboard/digest.py --print            # prints the issue body
    python3 dashboard/digest.py --update --repo OWNER/REPO   # edits the pinned issue
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys

import generate as g

MARKER = "<!-- productswarm-digest -->"   # --update finds the pinned issue by this
TITLE_MAX = 60


def short(title: str, limit: int = TITLE_MAX) -> str:
    """The title cut to about `limit` characters, at a word break where there is one."""
    title = " ".join(title.split())
    if len(title) <= limit:
        return title
    cut = title[:limit - 1]
    if " " in cut[limit // 2:]:
        cut = cut[:cut.rindex(" ")]
    return cut.rstrip(" ,;:·-") + "…"


def tail(item: dict, now: dt.datetime) -> str:
    """needs_line()'s detail and age: the line after its label, ref and title."""
    line = g.needs_line(item, now)
    title = f" {item['title']}" if item["title"] else ""
    head = f"[{g.NEEDS_LABELS[item['kind']]}] {item['ref']}{title} · "
    return line[len(head):] if line.startswith(head) else line


def bullet(item: dict, now: dt.datetime) -> str:
    ref = item["ref"] if item["ref"].startswith(("#", "PR #")) else f"[{item['ref']}]({item['url']})"
    title = f" {short(item['title'])}" if item["title"] else ""
    return f"- {ref}{title}: {tail(item, now)}"


def pages_url(repo: str) -> str:
    owner, name = repo.split("/", 1)
    return f"https://{owner.lower()}.github.io/{name}/"


def render(items: list[dict], now: dt.datetime, repo: str) -> str:
    """The issue body: count, one heading per kind with items (NEEDS_KINDS order), footer."""
    n = len(items)
    first = (f"**{n} thing{'s' if n != 1 else ''} need{'s' if n == 1 else ''} you**"
             if n else g.NEEDS_EMPTY)
    out = [f"{MARKER} {first}"]
    for kind in g.NEEDS_KINDS:
        group = [i for i in items if i["kind"] == kind]
        if group:
            label = g.NEEDS_LABELS[kind]
            out += ["", f"### {label[0].upper()}{label[1:]} ({len(group)})", ""]
            out += [bullet(i, now) for i in group]
    out += ["", f"Updated {g.stamp(now)} · dashboard: {pages_url(repo)}"]
    return "\n".join(out) + "\n"


# Text that changes with the clock alone: "Updated …" and ages ("5m ago", "just now").
UPDATED_RE = re.compile(r"^Updated .*$", re.M)
AGE_RE = re.compile(r"\b\d+[dhm] ago\b|\bjust now\b")


def comparable(body: str) -> str:
    """The body without the parts that change with the clock alone, so a run where only
    time passed leaves the issue alone. Ages are then as of the "Updated" line."""
    body = body.replace("\r\n", "\n")
    body = AGE_RE.sub("…", UPDATED_RE.sub("", body))
    return "\n".join(ln.rstrip() for ln in body.strip().splitlines())


def digest_issues(issues: list[dict]) -> list[dict]:
    """Open issues (not PRs) whose body starts with the digest marker."""
    return [i for i in issues if i.get("state") == "open" and "pull_request" not in i
            and (i.get("body") or "").lstrip().startswith(MARKER)]


def update(repo: str, issues: list[dict], body: str) -> int:
    """Write `body` into the one open marked issue if the list changed. Never creates,
    pins, labels, closes or comments on an issue: the owner makes and pins it once."""
    found = digest_issues(issues)
    if len(found) != 1:
        nums = ", ".join(f"#{i['number']}" for i in found)
        why = (f"found {len(found)} open issues starting with {MARKER} ({nums}); close all but one"
               if found else f"no open issue starts with {MARKER}; create and pin one "
                             "(see dashboard/README.md)")
        print(f"digest.py: {why}", file=sys.stderr)
        return 1
    n = found[0]["number"]
    if comparable(found[0].get("body") or "") == comparable(body):
        print(f"digest.py: #{n} unchanged; not edited")
        return 0
    r = subprocess.run(["gh", "api", "-X", "PATCH", f"repos/{repo}/issues/{n}", "--input", "-"],
                       input=json.dumps({"body": body}), capture_output=True, text=True,
                       timeout=120)
    if r.returncode != 0:
        print(f"digest.py: editing #{n} failed: {r.stderr.strip()[:300]}", file=sys.stderr)
        return 1
    print(f"digest.py: updated #{n}")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="The needs-you digest as Markdown.")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--print", action="store_true", help="print the issue body (read-only)")
    mode.add_argument("--update", action="store_true",
                      help="write it into the open issue that starts with the digest marker, "
                           "if the list changed")
    ap.add_argument("--repo", help="owner/name (default: this checkout's origin)")
    ap.add_argument("--days", type=int, default=g.DAYS)
    ap.add_argument("--idle-minutes", type=int, default=g.IDLE_MINUTES)
    args = ap.parse_args(argv)

    repo = args.repo or g.default_repo()
    if not repo:
        print("digest.py: can't tell the repo; pass --repo owner/name", file=sys.stderr)
        return 2
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    if args.update and (low := g.low_allowance(g.DIGEST_NEEDS)):
        print(f"digest.py: skipped, not edited: {low}")   # the issue keeps its last digest
        return 0
    try:
        data = g.fetch(repo, now, args.days)
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError) as e:
        print(f"digest.py: {e}", file=sys.stderr)
        return 1
    model = g.build(data, now, dt.timedelta(minutes=args.idle_minutes), caps=g.load_caps())
    body = render(g.needs_you(model), now, repo)
    if args.update:
        return update(repo, data["issues"], body)
    sys.stdout.write(body)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
