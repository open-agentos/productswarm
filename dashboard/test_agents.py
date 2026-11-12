"""Tests for the Agents page (#932). Run: python3 -m unittest discover -s dashboard"""
from __future__ import annotations

import datetime as dt
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import agents  # noqa: E402
import layout  # noqa: E402
from test_bridge import NOW, REPO, model  # noqa: E402


def amodel(**over):
    m = model()
    m["sessions"] = [
        {"role": "builder", "status": "active", "issue": 894, "pr": None, "last_ts": NOW - dt.timedelta(minutes=5)},
        {"role": "builder", "status": "stopped", "issue": 890, "pr": 923, "last_ts": NOW - dt.timedelta(hours=3)},
        {"role": "analyst", "status": "blocked", "issue": 692, "pr": None, "gov_question": 905,
         "last_ts": NOW - dt.timedelta(hours=1)},
        {"role": "planner", "status": "idle", "issue": None, "pr": None, "last_ts": NOW - dt.timedelta(hours=2)},
        {"role": "reviewer", "status": "active", "never_acted": True, "issue": 1, "pr": None, "last_ts": NOW}]
    m["issue_titles"] = {894: "M4 drill", 692: "Checklist brief"}
    m["prs"] = [{"number": 940, "title": "Drill fixes", "url": f"https://github.com/{REPO}/pull/940",
                 "author": "app/productswarm-builder", "reviewer": {"at_head": "CHANGES_REQUESTED"}},
                {"number": 941, "title": "Spec", "url": "u", "author": "app/productswarm-designer",
                 "reviewer": {"at_head": "APPROVED"}}]
    m["grants"] = {"calls": [{"number": 925, "group": "merged", "reason": "GOV-0027", "link": f"https://github.com/{REPO}/pull/925#c"},
                             {"number": 940, "group": "left", "reason": "protected path", "link": f"https://github.com/{REPO}/pull/940#d"}]}
    m["report"]["issue"] = 249
    return m | over


class BuildTest(unittest.TestCase):
    def rows(self, **over):
        return {r["role"]: r for r in agents.build(amodel(**over))["rows"]}

    def test_one_row_per_role_working_first(self):
        rows = agents.build(amodel())["rows"]
        self.assertEqual(len(rows), len(agents.ROLES))
        self.assertEqual([r["role"] for r in rows if r["group"] == "working"], ["builder", "analyst", "merger"])

    def test_what_each_is_on_and_its_record(self):
        r = self.rows()
        self.assertEqual([x["ref"] for x in r["builder"]["on"]], ["#894"])
        self.assertEqual((len(r["builder"]["merged"]), len(r["builder"]["open"]), len(r["builder"]["changes"]),
                          r["builder"]["sessions"]), (1, 1, 1, 2))
        self.assertTrue(r["analyst"]["blocked"])
        self.assertEqual(r["designer"]["group"], "idle")
        self.assertEqual(len(r["designer"]["merged"]), 1)   # the Brief, merged yesterday

    def test_authority_counts_for_the_prs_author_and_all_for_the_merger(self):
        r = self.rows()
        self.assertEqual([c["number"] for c in r["builder"]["authority"]], [925, 940])
        self.assertEqual(len(r["merger"]["authority"]), 2)
        self.assertEqual(r["planner"]["authority"], [])

    def test_a_session_that_never_acted_doesnt_count(self):
        self.assertEqual(self.rows()["reviewer"]["group"], "idle")


class RenderTest(unittest.TestCase):
    def test_rows_link_to_drawers(self):
        html = agents.render(agents.build(amodel()))
        self.assertEqual(re.findall(r'class="cm-row" href="#a-([a-z]+)"', html),
                         re.findall(r'class="cm-drawer" id="a-([a-z]+)"', html))
        self.assertIn("WORKING · 3", html)
        self.assertIn("IDLE · 4", html)

    def test_rows_hold_no_link_inside_their_link(self):
        html = agents.render(agents.build(amodel()))
        for row in re.findall(r'<a class="cm-row".*?</a>', html):
            self.assertEqual(row.count("<a "), 1)

    def test_drawer_contents(self):
        html = agents.render(agents.build(amodel()))
        b = html[html.index('id="a-builder"'):html.index("</section>", html.index('id="a-builder"'))]
        for text in ("LAST 14 DAYS", "Changes requested", "M4 drill", "Desk: trouble panel",
                     "left for you: protected path", "<code>Ask: builder: …</code>", "issues/249"):
            self.assertIn(text, b)
        mg = html[html.index('id="a-merger"'):html.index("</section>", html.index('id="a-merger"'))]
        self.assertNotIn("ASK IT SOMETHING", mg)
        an = html[html.index('id="a-analyst"'):html.index("</section>", html.index('id="a-analyst"'))]
        self.assertIn("BLOCKED", an)

    def test_empty_model(self):
        empty = {"repo": REPO, "now": NOW, "sessions": [], "prs": [], "merged": [], "grants": None,
                 "report": None, "trouble": None, "plan": None}
        html = agents.render(agents.build(empty))
        self.assertIn("Nothing merged in the window.", html)
        self.assertIn("No live session.", html)
        self.assertIn("the report issue", html)

    def test_page_shell(self):
        page = agents.page(amodel(), "t", "")
        self.assertNotIn("<script", page)
        for href in re.findall(r'href="([^"]+)"', page):
            self.assertRegex(href, r"^(https://github\.com/|[a-z]+\.html$|#[a-z0-9-]+$)")
        self.assertIn('<span class="br-navi here" aria-current="page">Agents', page)
        self.assertIn(("agents.html", "Agents"), layout.PAGES)


if __name__ == "__main__":
    unittest.main()
