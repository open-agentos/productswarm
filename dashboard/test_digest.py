"""Tests for the needs-you digest (dashboard/digest.py, v3 F2 and F3), with a canned model
and, for --update, a fake `gh` on PATH that logs every call, so nothing touches GitHub.

Run: python3 -m unittest discover -s dashboard
"""
import datetime as dt
import json
import os
import re
import stat
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import digest as d  # noqa: E402
import generate as g  # noqa: E402
from test_generate import NOW, REPO, issue, tracking  # noqa: E402
from test_needs import model  # noqa: E402

LONG = "A pull request title that runs on well past the sixty characters a phone shows"


def ago(minutes):
    return NOW - dt.timedelta(minutes=minutes)


def one_of_each():
    """One canned item per kind, in needs_you() order."""
    sess = "https://github.com/open-agentos/productswarm/issues/50"
    return [
        {"kind": "blocked", "ref": "#28", "title": "GOV-Q: someone waits", "url": "u28",
         "session_url": sess, "detail": "builder session s1 is blocked on it", "since": ago(50)},
        {"kind": "question", "ref": "#26", "title": "GOV-Q: unwaited", "url": "u26",
         "detail": "time to live 2026-11-09", "since": ago(600)},
        {"kind": "pr", "ref": "PR #30", "title": LONG, "url": "u30",
         "detail": "awaiting review, closes #4", "since": ago(90)},
        {"kind": "over_cap", "ref": "builder session b-over", "title": "", "url": sess,
         "session_url": sess, "detail": "est. $20.00, cap $15.00; warn only: swarm stop ends it (GOV-0008)",
         "since": ago(1), "over": 20 / 15},
    ]


class DigestTest(unittest.TestCase):
    def test_empty(self):
        body = d.render([], NOW, REPO)
        first = body.splitlines()[0]
        self.assertEqual(first, f"{d.MARKER} {g.NEEDS_EMPTY}")
        self.assertNotIn("###", body)
        self.assertFalse([ln for ln in body.splitlines() if ln.startswith("- ")])

    def test_one_of_each_kind(self):
        body = d.render(one_of_each(), NOW, REPO)
        lines = body.splitlines()
        self.assertEqual(lines[0], f"{d.MARKER} **4 things need you**")
        self.assertEqual([ln for ln in lines if ln.startswith("### ")], [
            "### Blocked (1)", "### Gov question (1)", "### PR to review (1)",
            "### Over cap (1)"])
        self.assertIn("- #28 GOV-Q: someone waits: builder session s1 is blocked on it · 50m ago", lines)
        self.assertIn("- #26 GOV-Q: unwaited: time to live 2026-11-09 · 10h ago", lines)
        # Session items have no #N reference, so they link to the tracking issue; no age (as needs_line).
        self.assertTrue(any(ln.startswith("- [builder session b-over](https://github.com/open-agentos/"
                                          "productswarm/issues/50)") and ln.endswith("(GOV-0008)")
                            for ln in lines))
        self.assertEqual(lines[-1], "Updated 2026-11-02 12:00 UTC · dashboard: "
                                    "https://open-agentos.github.io/productswarm/")

    def test_singular_count(self):
        self.assertTrue(d.render(one_of_each()[:1], NOW, REPO).startswith(
            f"{d.MARKER} **1 thing needs you**"))

    def test_only_kinds_with_items_get_a_heading(self):
        items = [i for i in one_of_each() if i["kind"] in ("question", "over_cap")]
        heads = [ln for ln in d.render(items, NOW, REPO).splitlines() if ln.startswith("### ")]
        self.assertEqual(heads, ["### Gov question (1)", "### Over cap (1)"])

    def test_title_shortening(self):
        s = d.short(LONG)
        self.assertLessEqual(len(s), d.TITLE_MAX)
        self.assertTrue(s.endswith("…"))
        self.assertTrue(LONG.startswith(s[:-1]))
        self.assertEqual(d.short("Short title"), "Short title")
        self.assertEqual(d.short("x" * 80), "x" * 59 + "…")   # no word break: hard cut
        pr_line = next(ln for ln in d.render(one_of_each(), NOW, REPO).splitlines()
                       if ln.startswith("- PR #30"))
        self.assertIn(f"- PR #30 {s}: awaiting review, closes #4 · 1h ago", pr_line)

    def test_order_matches_needs_you(self):
        items = g.needs_you(model())
        bullets = [ln for ln in d.render(items, NOW, REPO).splitlines() if ln.startswith("- ")]
        self.assertEqual(len(bullets), len(items))
        for item, ln in zip(items, bullets):
            ref = item["ref"] if item["ref"].startswith(("#", "PR #")) else f"[{item['ref']}]"
            self.assertTrue(ln.startswith(f"- {ref}"), (item["ref"], ln))

    def test_detail_matches_needs_line(self):
        for item in g.needs_you(model()):
            self.assertTrue(g.needs_line(item, NOW).endswith(d.tail(item, NOW)))

    def test_marker_on_first_line_and_no_tables(self):
        for items in ([], one_of_each(), g.needs_you(model())):
            body = d.render(items, NOW, REPO)
            self.assertTrue(body.startswith("<!-- productswarm-digest -->"))
            self.assertEqual(body.count(d.MARKER), 1)
            self.assertFalse(re.search(r"^\s*\|", body, re.M))


# Serves GETs from FAKE_GH_DATA, applies a PATCH to it, and logs every call (argv and stdin).
FAKE_GH = r"""#!/usr/bin/env python3
import json, os, sys
a = sys.argv[1:]
path_data = os.environ["FAKE_GH_DATA"]
data = json.load(open(path_data))
stdin = sys.stdin.read() if "--input" in a else None
with open(os.environ["FAKE_GH_LOG"], "a") as f:
    f.write(json.dumps({"argv": a, "stdin": stdin}) + "\n")
if a[:2] == ["api", "graphql"]:
    print(json.dumps({"data": {"repository": {}}}))   # no batched data: comments come over REST
elif a[:1] == ["api"] and "-X" not in a and len(a) > 2:
    path = a[2]
    key = "open" if "state=open" in path else "closed" if "state=closed" in path else path.split("?")[0]
    for item in data.get(key, []):
        print(json.dumps(item))
elif a[:3] == ["api", "-X", "PATCH"]:
    n = int(a[3].rsplit("/", 1)[1])
    for it in data["open"]:
        if it["number"] == n:
            it["body"] = json.loads(stdin)["body"]
    json.dump(data, open(path_data, "w"))
    print("{}")
elif a[:2] == ["pr", "list"]:
    print(json.dumps(data["prs"]))
else:
    sys.exit(1)
"""


def digest_issue(n, body=d.MARKER + "\nPinned by the owner.\n"):
    it = issue(n, "Needs you")
    it["body"] = body
    return it


class UpdateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        fake = self.dir / "gh"
        fake.write_text(FAKE_GH)
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        self.log = self.dir / "log.jsonl"
        self.data = self.dir / "data.json"
        env = {"PATH": f"{self.dir}{os.pathsep}{os.environ['PATH']}",
               "FAKE_GH_DATA": str(self.data), "FAKE_GH_LOG": str(self.log)}
        self.old = {k: os.environ.get(k) for k in env}
        os.environ.update(env)

    def tearDown(self):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def run_update(self, open_issues, closed=()):
        self.data.write_text(json.dumps({"open": open_issues, "closed": list(closed), "prs": []}))
        self.log.write_text("")
        return d.main(["--update", "--repo", REPO])

    def calls(self):
        return [json.loads(ln) for ln in self.log.read_text().splitlines()]

    def writes(self):
        """Every call that isn't a read: `gh api` without -X, or `gh pr list`."""
        return [c for c in self.calls()
                if not ((c["argv"][:1] == ["api"] and "-X" not in c["argv"])
                        or c["argv"][:2] == ["pr", "list"])]

    def body(self, n):
        return next(i["body"] for i in json.loads(self.data.read_text())["open"] if i["number"] == n)

    def test_no_marked_issue(self):
        rc = self.run_update([issue(4, "Dashboard"), digest_issue(9) | {"state": "closed"}])
        self.assertEqual(rc, 1)
        self.assertEqual(self.writes(), [])

    def test_two_marked_issues(self):
        self.assertEqual(self.run_update([digest_issue(9), digest_issue(10)]), 1)
        self.assertEqual(self.writes(), [])

    def test_marker_must_start_the_body(self):
        it = digest_issue(9, body=f"See {d.MARKER} here")
        self.assertEqual(self.run_update([it]), 1)
        self.assertEqual(self.writes(), [])

    def test_changed_body_one_patch_then_unchanged_no_patch(self):
        self.assertEqual(self.run_update([digest_issue(9), issue(4, "Dashboard")]), 0)
        writes = self.writes()
        self.assertEqual([w["argv"] for w in writes],
                         [["api", "-X", "PATCH", f"repos/{REPO}/issues/9", "--input", "-"]])
        self.assertEqual(set(json.loads(writes[0]["stdin"])), {"body"})
        body = self.body(9)
        self.assertTrue(body.startswith(f"{d.MARKER} {g.NEEDS_EMPTY}"))

        # The same list again: no edit, even though the "Updated" line would differ.
        stale = body.replace("Updated 20", "Updated 19")
        self.assertEqual(self.run_update([digest_issue(9, body=stale)]), 0)
        self.assertEqual(self.writes(), [])

        # The list changes (a new gov:question): one more edit.
        self.assertEqual(self.run_update([digest_issue(9, body=body),
                                          issue(70, "GOV-Q: new", ["gov:question"])]), 0)
        self.assertEqual(len(self.writes()), 1)
        self.assertIn("### Gov question (1)", self.body(9))

    def test_patch_failure_is_reported(self):
        self.data.write_text(json.dumps({"open": [digest_issue(9)], "closed": [], "prs": []}))
        os.environ["FAKE_GH_LOG"] = str(self.dir / "missing" / "log.jsonl")   # fake gh fails
        self.assertEqual(d.update(REPO, [digest_issue(9)], "new"), 1)

    def test_comparable_ignores_clock_only_changes(self):
        a = d.render(one_of_each(), NOW, REPO)
        b = d.render(one_of_each(), NOW + dt.timedelta(hours=3), REPO)
        self.assertNotEqual(a, b)
        self.assertEqual(d.comparable(a), d.comparable(b))
        self.assertEqual(d.comparable(a.replace("\n", "\r\n")), d.comparable(a))
        self.assertNotEqual(d.comparable(a), d.comparable(d.render(one_of_each()[1:], NOW, REPO)))

    def test_digest_issue_never_needs_you(self):
        # It isn't a [heartbeat] tracking issue or a gov:question, even if a bot opened it.
        bot_made = digest_issue(9, body=d.render(one_of_each(), NOW, REPO))
        bot_made["user"] = {"login": "productswarm-builder[bot]"}
        m = g.build({"repo": REPO, "issues": [digest_issue(8), bot_made], "comments": {},
                     "prs": []}, NOW, dt.timedelta(minutes=15))
        self.assertEqual(m["sessions"], [])
        self.assertEqual(m["gov"], [])
        self.assertEqual(g.needs_you(m), [])


if __name__ == "__main__":
    unittest.main()
