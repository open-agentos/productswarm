"""Tests for the Bridge page (bridge.py, #926): each of its five sections against a fixture
model, with their empty states, and the page's shell (no script, read-only)."""
from __future__ import annotations

import datetime as dt
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bridge  # noqa: E402
import generate as g  # noqa: E402

REPO = "o/r"
BASE = f"https://github.com/{REPO}"
NOW = dt.datetime(2026, 11, 12, 12, 0, tzinfo=dt.timezone.utc)
OWNER = "boss"


def at(hours_ago: float) -> dt.datetime:
    return NOW - dt.timedelta(hours=hours_ago)


def iso(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def row(n, kind, children=()):
    return {"number": n, "title": f"Task {n}", "url": f"{BASE}/issues/{n}",
            "status": {"kind": kind, "text": kind}, "pr": None, "children": list(children)}


def scope(n, lead, title, subs, done=1, kind="Goal"):
    return {"number": n, "kind": kind, "lead": lead, "title": title, "url": f"{BASE}/issues/{n}",
            "open": len(subs), "done": done, "unread": False, "subs": subs}


def full_model() -> dict:
    plan = {"read": True, "not_plan": [], "scopes": [
        scope(683, "M1", "Report", [row(701, "go"), row(702, "waiting")], done=3),
        scope(685, "M3", "The desk", [row(711, "go", [row(712, "not_go")])], done=2),
        scope(687, "", "Engine host", [], done=4, kind="Area")]}
    floor = {"cards": [{"role": "builder"}, {"role": "reviewer"}], "idle": [{"role": "docs"}]}
    grants = {"mode": "live", "read": True, "calls": [
        {"number": 801, "title": "Tidy", "group": "merged", "reason": "standing grant",
         "time": at(2), "link": f"{BASE}/pull/801#c1"},
        {"number": 653, "title": "Touch ops", "group": "left", "reason": "a protected path",
         "time": at(3), "link": f"{BASE}/pull/653#c2"}]}
    gov = [{"number": 900, "title": "Which host?", "url": f"{BASE}/issues/900", "labels": [],
            "ttl": "2026-11-10 (owner)", "waiting": []},
           {"number": 901, "title": "Ruled one", "url": f"{BASE}/issues/901", "labels": ["gov:ruled"],
            "ttl": None, "waiting": []},
           {"number": 902, "title": "Fresh", "url": f"{BASE}/issues/902", "labels": [],
            "ttl": "2026-12-01", "waiting": []}]
    sessions = [{"status": "blocked", "role": "builder", "gov_question": 900, "issue": 712},
                {"status": "active", "role": "reviewer", "gov_question": None, "issue": None}]
    prs = [{"number": 640, "title": "Big change", "url": f"{BASE}/pull/640",
            "needs_owner": "past 2 rounds"},
           {"number": 641, "title": "Fine", "url": f"{BASE}/pull/641", "needs_owner": None}]
    report = {"issue": 249, "state": "posted", "daily_at": dt.time(8, 30), "last": None, "checkin": None,
              "report": {"url": f"{BASE}/issues/249#r1", "line": "**On track**, two asks",
                         "posted": at(3), "asks": [{"lead": "#655 (GOV-0032)", "text": "merge it?", "issue": 655},
                                                   {"lead": "Spend", "text": "fine?", "issue": None}]}}
    activity = {"events": [
        {"type": "IssuesEvent", "actor": {"login": OWNER}, "created_at": iso(at(1)),
         "payload": {"action": "labeled", "issue": {"number": 926, "html_url": f"{BASE}/issues/926"},
                     "label": {"name": "ready"}}},
        {"type": "IssueCommentEvent", "actor": {"login": OWNER}, "created_at": iso(at(5)),
         "payload": {"action": "created", "issue": {"number": 760},
                     "comment": {"html_url": f"{BASE}/issues/760#c9"}}},
        {"type": "IssuesEvent", "actor": {"login": "productswarm-planner[bot]"}, "created_at": iso(at(0.5)),
         "payload": {"action": "opened", "issue": {"number": 927}}}]}
    trouble = {"scopes": [{"url": f"{BASE}/issues/683", "date_missed": False,
                           "progress": [{"status": "failing"}]}]}
    return {"repo": REPO, "now": NOW, "plan": plan, "floor": floor, "grants": grants, "gov": gov,
            "sessions": sessions, "prs": prs, "report": report, "activity": activity,
            "trouble": trouble, "issue_titles": {900: "Which host?"}}


MERGED = [
    {"number": 810, "title": "Brief on hosts", "html_url": f"{BASE}/pull/810",
     "user": {"login": "productswarm-analyst[bot]"}, "body": "Closes #750\n\n-- analyst",
     "pull_request": {"merged_at": iso(at(20))}},
    {"number": 811, "title": "Desk panel", "html_url": f"{BASE}/pull/811",
     "user": {"login": "productswarm-builder[bot]"}, "body": "Closes #712",
     "pull_request": {"merged_at": iso(at(4))}},
    {"number": 812, "title": "Owner's own", "html_url": f"{BASE}/pull/812",
     "user": {"login": OWNER}, "body": "", "pull_request": {"merged_at": iso(at(2))}},
    {"number": 700, "title": "Too old", "html_url": f"{BASE}/pull/700",
     "user": {"login": "productswarm-builder[bot]"}, "body": "",
     "pull_request": {"merged_at": iso(at(24 * 8))}},
]
TREES = {685: {"subIssues": {"nodes": [
    {"number": 750, "state": "CLOSED", "issueType": {"name": "Brief"}, "subIssues": {"nodes": []}},
    {"number": 711, "state": "OPEN", "issueType": {"name": "Task"},
     "subIssues": {"nodes": [{"number": 712, "state": "OPEN", "issueType": {"name": "Task"}}]}}]}}}


def empty_model() -> dict:
    return {"repo": REPO, "now": NOW, "plan": {"read": True, "scopes": [], "not_plan": []},
            "floor": {"cards": [], "idle": []}, "grants": {"mode": "shadow", "read": True, "calls": []},
            "gov": [], "sessions": [], "prs": [], "report": {"issue": 249, "state": "late",
                                                              "daily_at": dt.time(8, 30), "report": None,
                                                              "last": None, "checkin": None},
            "activity": {"events": []}, "trouble": None, "issue_titles": {}}


def section(html: str, cls: str) -> str:
    return re.search(rf'<section class="{cls}"[^>]*>(.*?)</section>', html, re.S)[1]


class FullTest(unittest.TestCase):
    def setUp(self):
        self.b = bridge.build(full_model(), MERGED, TREES, OWNER)
        self.html = bridge.body(self.b)

    def test_status_strip(self):
        s = section(self.html, "strip")
        self.assertIn("<b>3</b> Goals and Areas open, 1 with a not-go sub-issue", s)
        self.assertIn("<b>2</b> agents working", s)
        self.assertIn("<b>7</b> decisions waiting", s)
        self.assertIn("<b>2</b> merger calls in 24 hours", s)

    def test_decisions_waiting(self):
        d = section(self.html, "decide")
        refs = re.findall(r'<a href="([^"]+)">([^<]+)</a>', d)
        self.assertEqual(refs, [
            (f"{BASE}/issues/900", "#900"),                 # unruled question, past its TTL
            (f"{BASE}/issues/902", "#902"),                 # unruled question
            (f"{BASE}/issues/900", "#900"),                 # a session blocked on it
            (f"{BASE}/pull/640", "PR #640"),               # GOV-0011 hands it over
            (f"{BASE}/pull/653#c2", "PR #653"),            # the merger left it
            (f"{BASE}/issues/655", "#655 (GOV-0032)"),      # today's asks
            (f"{BASE}/issues/249#r1", "Spend")])
        self.assertNotIn("#901", d)                        # ruled
        self.assertNotIn("PR #641", d)                     # nothing hands it to the owner
        self.assertIn("past its time to live (2026-11-10 (owner))", d)
        self.assertIn("time to live 2026-12-01", d)
        self.assertIn("builder session is blocked on it (working on #712)", d)
        self.assertIn("the merger left it for you: a protected path", d)
        self.assertIn("past 2 rounds (GOV-0011)", d)
        self.assertNotIn("<button", d)

    def test_reports(self):
        r = section(self.html, "reports")
        items = re.findall(r"<li[^>]*>(.*?)</li>", r, re.S)
        self.assertEqual(len(items), 3)
        self.assertIn('REPORTED</span> <span class="agent">planner</span>', items[0])
        self.assertIn("<b>On track</b>, two asks", items[0])
        self.assertIn('SHIPPED</span> <span class="agent">builder</span>', items[1])
        self.assertIn("PR #811", items[1])
        self.assertIn('DELIVERED</span> <span class="agent">analyst</span>', items[2])
        self.assertNotIn("PR #812", r)                     # not a role's App
        self.assertNotIn("PR #700", r)                     # older than 7 days

    def test_in_flight(self):
        f = section(self.html, "flight")
        lines = re.findall(r"<li>(.*?)</li>", f, re.S)
        self.assertEqual(len(lines), 3)
        self.assertIn('class="dot red"', lines[0])          # failing criterion in trouble
        self.assertIn("3 of 5 done", lines[0])
        self.assertIn('class="dot owner"', lines[1])        # a not-go grandchild
        self.assertIn("2 of 3 done", lines[1])
        self.assertIn('class="dot quiet"', lines[2])
        self.assertIn("4 of 4 done</span> · nothing open", lines[2])

    def test_orders_received(self):
        o = section(self.html, "orders")
        lines = re.findall(r"<li>(.*?)</li>", o, re.S)
        self.assertEqual(len(lines), 2)                     # the planner's event isn't an order
        self.assertIn('<span class="chair">GitHub</span> labelled', lines[0])
        self.assertIn("<code>ready</code>", lines[0])
        self.assertIn(f'<a href="{BASE}/issues/760#c9">#760</a>', lines[1])

    def test_rail(self):
        rail = re.search(r'<nav class="rail"[^>]*>(.*?)</nav>', self.html, re.S)[1]
        self.assertIn('aria-current="page">Bridge', rail)
        self.assertIn('<a href="index.html">Commissions <span class="num">4</span></a>', rail)
        self.assertIn('<a href="operations.html">Agents <span class="num">3</span></a>', rail)
        for f in ("operations.html", "decisions.html", "authority.html"):
            self.assertIn(f'href="{f}"', rail)

    def test_no_spend(self):
        m = full_model()
        m["spend"] = {"today": 98.76}
        self.assertNotIn("98.76", bridge.body(bridge.build(m, MERGED, TREES, OWNER)))


class EmptyTest(unittest.TestCase):
    def setUp(self):
        self.html = bridge.body(bridge.build(empty_model(), [], {}, OWNER))

    def test_each_section_says_so(self):
        self.assertIn("<b>0</b> Goals and Areas open", section(self.html, "strip"))
        self.assertIn("Nothing is waiting on you.", section(self.html, "decide"))
        r = section(self.html, "reports")
        self.assertIn('class="flag"', r)
        self.assertIn("<b>No report yet today.</b> It was due at 08:30.", r)
        self.assertIn("No PR merged by a role's App in the last 7 days.", r)
        self.assertIn("No plan: the owner has no open Goal or Area.", section(self.html, "flight"))
        self.assertIn("No acts by the owner in the events read.", section(self.html, "orders"))

    def test_unread_data(self):
        m = empty_model() | {"plan": None, "floor": None, "grants": None, "activity": None}
        html = bridge.body(bridge.build(m, None, None, OWNER))
        self.assertIn("<b>?</b> plan not read", section(html, "strip"))
        self.assertIn("<b>?</b> agents working", section(html, "strip"))
        self.assertIn("Couldn't read the plan from GitHub.", section(html, "flight"))
        self.assertIn("Merged PRs couldn't be read.", section(html, "reports"))
        self.assertIn("Couldn't read the owner's acts", section(html, "orders"))


class PageTest(unittest.TestCase):
    def test_generate_builds_it_and_renders_it(self):
        from test_generate import PageTest as P
        m = P().model()
        self.assertIn("bridge", m)
        page = g.render(m)["bridge.html"]
        self.assertIn("<h1>The bridge</h1>", page)
        self.assertNotIn("<script", page.lower())
        self.assertIn("script-src 'none'", page)
        for tag in ("<form", "<button", "<input"):
            self.assertNotIn(tag, page.lower())

    def test_build_keeps_the_merged_prs_questions_reads(self):
        from test_generate import PageTest as P
        m = P().model()
        self.assertIsNone(m["bridge"]["shipped"])   # questions weren't fetched in this fixture


if __name__ == "__main__":
    unittest.main()
