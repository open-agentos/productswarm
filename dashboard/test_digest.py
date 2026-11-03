"""Tests for the needs-you digest (dashboard/digest.py, v3 F2), with a canned model.

Run: python3 -m unittest discover -s dashboard
"""
import datetime as dt
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import digest as d  # noqa: E402
import generate as g  # noqa: E402
from test_generate import NOW, REPO  # noqa: E402
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
        {"kind": "idle", "ref": "builder session idle-lon", "title": "", "url": sess,
         "session_url": sess, "detail": "no event since 5h ago", "since": ago(300)},
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
        self.assertEqual(lines[0], f"{d.MARKER} **5 things need you**")
        self.assertEqual([ln for ln in lines if ln.startswith("### ")], [
            "### Blocked (1)", "### Gov question (1)", "### PR to review (1)",
            "### Idle session (1)", "### Over cap (1)"])
        self.assertIn("- #28 GOV-Q: someone waits: builder session s1 is blocked on it · 50m ago", lines)
        self.assertIn("- #26 GOV-Q: unwaited: time to live 2026-11-09 · 10h ago", lines)
        # Session items have no #N reference, so they link to the tracking issue; no age (as needs_line).
        self.assertIn("- [builder session idle-lon](https://github.com/open-agentos/productswarm/"
                      "issues/50): no event since 5h ago", lines)
        self.assertTrue(any(ln.startswith("- [builder session b-over](") and ln.endswith("(GOV-0008)")
                            for ln in lines))
        self.assertEqual(lines[-1], "Updated 2026-11-02 12:00 UTC · dashboard: "
                                    "https://open-agentos.github.io/productswarm/")

    def test_singular_count(self):
        self.assertTrue(d.render(one_of_each()[:1], NOW, REPO).startswith(
            f"{d.MARKER} **1 thing needs you**"))

    def test_only_kinds_with_items_get_a_heading(self):
        items = [i for i in one_of_each() if i["kind"] in ("question", "idle")]
        heads = [ln for ln in d.render(items, NOW, REPO).splitlines() if ln.startswith("### ")]
        self.assertEqual(heads, ["### Gov question (1)", "### Idle session (1)"])

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


if __name__ == "__main__":
    unittest.main()
