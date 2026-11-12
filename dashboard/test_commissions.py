"""Tests for the Commissions page (#931). Run: python3 -m unittest discover -s dashboard"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import commissions as cm  # noqa: E402
import layout  # noqa: E402
from test_bridge import NOW, REPO, item, model, scope  # noqa: E402

TROUBLE = json.loads((HERE.parent / "launcher" / "testdata" / "trouble.json").read_text())


def plan_scope(n, lead, title, kind="Goal", open_=2, done=3, subs=()):
    return {"number": n, "kind": kind, "lead": lead, "title": title, "url": f"https://github.com/{REPO}/issues/{n}",
            "open": open_, "done": done, "unread": False, "subs": list(subs)}


def cmodel(**over):
    m = model()
    m["trouble"]["scopes"].append(scope(687, "Engine host stays up", progress=[("uptime", "met")]) | {"type": "Area"})
    m["plan"] = {"read": True, "not_plan": [], "scopes": [
        plan_scope(685, "M3", "The Desk shows the plan and the report", subs=[
            {"number": 931, "ref": "#931", "title": "Commissions page", "url": f"https://github.com/{REPO}/issues/931",
             "status": {"kind": "go", "text": "go"}, "pr": {"number": 933, "url": f"https://github.com/{REPO}/pull/933"}}]),
        plan_scope(686, "M4", "Readiness review")]}
    m["closed_scopes"] = [
        {"number": 684, "title": "M2: Merges under delegation", "url": f"https://github.com/{REPO}/issues/684",
         "type": "Goal", "closed_at": "2026-11-10T12:00:00Z"},
        {"number": 600, "title": "M0: Old", "url": "u", "type": "Goal", "closed_at": "2026-10-01T00:00:00Z"}]
    return m | over


class BuildTest(unittest.TestCase):
    def test_groups_in_order(self):
        rows = cm.build(cmodel())["rows"]
        self.assertEqual([(r["number"], r["group"]) for r in rows],
                         [(686, "look"), (685, "waiting"), (683, "running"), (687, "keep"), (684, "delivered")])

    def test_plan_counts_and_subs_join_the_trouble_scope(self):
        r = next(r for r in cm.build(cmodel())["rows"] if r["number"] == 685)
        self.assertEqual((r["lead"], r["title"], r["open"], r["done"], r["met"]),
                         ("M3", "The Desk shows the plan and the report", 2, 3, 1))
        self.assertEqual(r["subs"][0]["ref"], "#931")

    def test_falls_back_to_the_plan_when_trouble_failed(self):
        rows = cm.build(cmodel(trouble={"error": "boom"}))["rows"]
        self.assertEqual([(r["number"], r["group"]) for r in rows], [(685, "running"), (686, "running"), (684, "delivered")])


class RenderTest(unittest.TestCase):
    def html(self, **over):
        return cm.render(cm.build(cmodel(**over)))

    def test_rows_link_to_their_drawer_and_each_drawer_exists(self):
        html = self.html()
        rows = re.findall(r'class="cm-row" href="#c-(\d+)"', html)
        drawers = re.findall(r'class="cm-drawer" id="c-(\d+)"', html)
        self.assertEqual(rows, drawers)
        self.assertEqual(len(rows), 5)

    def test_drawer_shows_the_done_test_stuck_waiting_and_work(self):
        html = self.html()
        m4 = html[html.index('id="c-686"'):html.index("</section>", html.index('id="c-686"'))]
        self.assertIn("<b>failing</b> drill", m4)
        self.assertIn("PR #894", m4)
        self.assertIn("changes requested, no push, nothing restarts it", m4)
        m3 = html[html.index('id="c-685"'):html.index("</section>", html.index('id="c-685"'))]
        self.assertIn("overstep: needs the owner", m3)
        self.assertIn("OPEN WORK UNDER IT", m3)
        self.assertIn('href="https://github.com/o/r/pull/933">PR #933</a>', m3)
        self.assertIn("WAITS ON YOU", m3)

    def test_group_headings_and_status_words(self):
        html = self.html()
        for text in ("NEEDS A LOOK · 1", "WAITS ON YOU · 1", "RUNNING · 1", "KEEP IT SO · 1",
                     "DELIVERED THIS WEEK · 1", "1 stuck", "1 wait on you", "steady", "closed Tue 12:00"):
            self.assertIn(text, html)
        self.assertNotIn("M0", html)   # delivered too long ago

    def test_unmeasured_never_reads_as_on_track(self):
        html = cm.render(cm.build(model(trouble=TROUBLE)))
        if "unmeasured" in json.dumps(TROUBLE):
            self.assertIn("unmeasured: not known to be on track", html)
        self.assertNotIn("javascript:", html)

    def test_empty(self):
        html = cm.render(cm.build(model(trouble={"scopes": [], "outside": {}}, plan=None)))
        self.assertIn("No open Goal or Area, and none delivered this week.", html)

    def test_page_has_no_script_and_safe_links(self):
        page = cm.page(cmodel(), "t", "")
        self.assertNotIn("<script", page)
        for href in re.findall(r'href="([^"]+)"', page):
            self.assertRegex(href, r"^(https://github\.com/|[a-z]+\.html$|#[a-z0-9-]+$)")
        self.assertIn('<span class="br-navi here" aria-current="page">Commissions', page)
        self.assertIn(("commissions.html", "Commissions"), layout.PAGES)


if __name__ == "__main__":
    unittest.main()
