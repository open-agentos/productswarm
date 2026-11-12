"""Tests for the Bridge (#926). Run: python3 -m unittest discover -s dashboard"""
from __future__ import annotations

import datetime as dt
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bridge  # noqa: E402
import generate as g  # noqa: E402
import layout  # noqa: E402

REPO = "o/r"
OWNER = "owner"
NOW = dt.datetime(2026, 11, 12, 12, 0, tzinfo=dt.timezone.utc)
TROUBLE = json.loads((HERE.parent / "launcher" / "testdata" / "trouble.json").read_text())


def scope(n, title, progress=(), stuck=(), waiting=(), authority=(), date_missed=False):
    return {"ref": f"{REPO}#{n}", "type": "Goal", "title": title, "url": f"https://github.com/{REPO}/issues/{n}",
            "date": None, "date_missed": date_missed,
            "progress": [{"criterion": c, "status": s, "detail": ""} for c, s in progress],
            "stuck": list(stuck), "waiting": list(waiting), "authority": list(authority)}


def item(ref, reason, hours, url=None):
    since = (NOW - dt.timedelta(hours=hours)).isoformat()
    return {"kind": "pr", "ref": ref, "url": url or f"https://github.com/{REPO}/pull/{ref.split('#')[-1]}",
            "reason": reason, "since": since, "age_hours": hours}


def event(kind, action, n, hours, actor=OWNER, **payload):
    p = {"action": action, "issue": {"number": n, "html_url": f"https://github.com/{REPO}/issues/{n}"}, **payload}
    return {"type": kind, "actor": {"login": actor}, "payload": p,
            "created_at": (NOW - dt.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")}


def model(**over) -> dict:
    trouble = {"authority_hours": 24, "outside": {"stuck": [], "waiting": [], "authority": []},
               "scopes": [
                   scope(685, "M3: The Desk shows the plan and the report",
                         progress=[("state questions", "met"), ("fixture test", "progress")],
                         waiting=[item("PR #930", "overstep: needs the owner", 5)],
                         authority=[item("PR #925", "merged under GOV-0027", 3)]),
                   scope(686, "M4: Readiness review", progress=[("drill", "failing")],
                         stuck=[item("PR #894", "changes requested, no push, nothing restarts it", 30)]),
                   scope(683, "M1: Daily report runs without the owner", progress=[("report", "met")])]}
    m = {"repo": REPO, "now": NOW, "trouble": trouble,
         "floor": {"cards": [{"role": "builder"}], "idle": [{"role": "planner"}]},
         "sessions": [{"status": "active"}, {"status": "idle"}, {"status": "stopped"}],
         "gov": [{"number": 901, "title": "Which login may the desk use?", "url": f"https://github.com/{REPO}/issues/901",
                  "labels": [], "created_ts": NOW - dt.timedelta(days=3), "ttl": "2026-11-20", "waiting": []},
                 {"number": 902, "title": "Ruled already", "url": "u", "labels": ["gov:ruled"],
                  "created_ts": NOW, "ttl": None, "waiting": []}],
         "report": {"state": "posted", "daily_at": dt.time(9, 0),
                    "report": {"line": "**Daily report, Thu 11-12.** Two merged.", "url": f"https://github.com/{REPO}/issues/249#c1",
                               "posted": NOW - dt.timedelta(hours=3), "asks": [{"lead": "a"}]}},
         "merged": [{"number": 925, "title": "Desk: trouble panel", "url": f"https://github.com/{REPO}/pull/925",
                     "author": "productswarm-builder[bot]", "merged_at": "2026-11-12T09:30:00Z"},
                    {"number": 920, "title": "Brief: state questions", "url": f"https://github.com/{REPO}/pull/920",
                     "author": "productswarm-designer[bot]", "merged_at": "2026-11-11T16:00:00Z"},
                    {"number": 800, "title": "old", "url": "u", "author": "productswarm-builder[bot]",
                     "merged_at": "2026-10-01T00:00:00Z"},
                    {"number": 921, "title": "owner's own", "url": "u", "author": OWNER,
                     "merged_at": "2026-11-12T10:00:00Z"}],
         "activity": {"events": [
             event("IssuesEvent", "labeled", 903, 1, label={"name": "ready"}),
             event("IssueCommentEvent", "created", 888, 2,
                   comment={"html_url": f"https://github.com/{REPO}/issues/888#c2"}),
             event("IssuesEvent", "labeled", 5, 1, actor="someone-else", label={"name": "ready"}),
             {"type": "CreateEvent", "actor": {"login": OWNER}, "payload": {"ref_type": "branch", "ref": "x"},
              "created_at": "2026-11-12T11:00:00Z"}]},
         "plan": None, "prs": [{"number": 930, "title": "Fix the merger"}], "issue_titles": {}}
    return m | over


class BuildTest(unittest.TestCase):
    def test_status_counts(self):
        b = bridge.build(model(), OWNER)
        self.assertEqual((b["commissions"], b["flagged"], b["working"], b["agents"], b["idle"], b["authority"]),
                         (3, 1, 1, 2, 1, 1))

    def test_decisions_oldest_first(self):
        ds = bridge.build(model(), OWNER)["decisions"]
        self.assertEqual([d["ref"] for d in ds], ["#901", "PR #930", "Ask"])   # the report's ask, no age, last
        self.assertEqual(ds[1]["scope"], "M3")
        self.assertEqual((ds[1]["title"], ds[1]["why"]), ("Fix the merger", "overstep: needs the owner"))
        self.assertEqual(ds[0]["ttl"], "2026-11-20")

    def test_928s_sources_each_once_asks_last(self):
        m = model(
            sessions=[{"status": "blocked", "gov_question": 905, "role": "builder", "issue": 40,
                       "last_ts": NOW - dt.timedelta(hours=40)}],
            prs=[{"number": 930, "title": "Fix the merger", "url": "https://github.com/o/r/pull/930",
                  "created_ts": NOW - dt.timedelta(hours=9), "needs_owner": None},
                 {"number": 931, "title": "Big change", "url": "https://github.com/o/r/pull/931",
                  "created_ts": NOW - dt.timedelta(hours=20), "needs_owner": None},
                 {"number": 932, "title": "Third round", "url": "https://github.com/o/r/pull/932",
                  "created_ts": NOW - dt.timedelta(hours=10), "needs_owner": "past the round bound"}],
            grants={"calls": [{"number": 931, "group": "left", "reason": "639 changed lines",
                               "title": "Big change", "link": "https://github.com/o/r/pull/931#c",
                               "time": NOW},
                              {"number": 930, "group": "left", "reason": "protected path", "title": "x",
                               "link": "l", "time": NOW},
                              {"number": 933, "group": "merged", "reason": "GOV-0027", "link": "l", "time": NOW}]},
            issue_titles={905: "Which login?"})
        m["report"]["report"]["asks"] = [{"lead": "**Merge** it", "text": "by hand.", "issue": 931},
                                         {"lead": "Close #821", "text": "as answered.", "issue": 821}]
        ds = bridge.decisions(m)
        self.assertEqual([d["ref"] for d in ds], ["#901", "#905", "PR #931", "PR #932", "PR #930", "#821"])
        why = {d["ref"]: d["why"] for d in ds}
        self.assertEqual(why["PR #931"], "left for you: 639 changed lines")
        self.assertEqual(why["PR #932"], "past the round bound (GOV-0011)")
        self.assertEqual(why["#905"], "builder session is blocked on it (working on #40)")
        self.assertEqual(why["#821"], "asked in today's daily report")
        self.assertNotIn("WAITING", bridge.decisions_html({"decisions": ds[-1:], "now": NOW}))

    def test_a_question_trouble_already_lists_shows_once(self):
        m = model()
        m["trouble"]["outside"]["waiting"] = [item("#901", "gov question waiting", 70,
                                                   url=f"https://github.com/{REPO}/issues/901")]
        self.assertEqual([d["ref"] for d in bridge.decisions(m)].count("#901"), 1)

    def test_reports_newest_first_with_flags_and_merged_prs_by_role(self):
        rs = bridge.build(model(), OWNER)["reports"]
        self.assertEqual([(r["kind"], r["role"]) for r in rs],
                         [("shipped", "builder"), ("report", "planner"), ("delivered", "designer"),
                          ("flag", "watch")])

    def test_a_late_report_is_a_flag(self):
        m = model(report={"state": "late", "daily_at": dt.time(9, 0), "report": None})
        r = bridge.reports(m)
        self.assertIn(("flag", "No daily report yet today"), [(x["kind"], x["head"]) for x in r])

    def test_in_flight_states(self):
        fs = {f["lead"]: (f["state"], f["met"], f["total"]) for f in bridge.build(model(), OWNER)["flights"]}
        self.assertEqual(fs, {"M3": ("waiting", 1, 2), "M4": ("flagged", 0, 1), "M1": ("running", 1, 1)})

    def test_in_flight_falls_back_to_the_plan_when_trouble_failed(self):
        m = model(trouble={"error": "boom"},
                  plan={"scopes": [{"lead": "M3", "title": "Desk", "url": "u", "kind": "Goal", "open": 2, "done": 3}]})
        b = bridge.build(m, OWNER)
        self.assertEqual([(f["lead"], f["met"], f["total"]) for f in b["flights"]], [("M3", 3, 5)])
        self.assertIn("wasn't read (boom)", bridge.render(b))

    def test_orders_are_the_owners_acts_without_branch_noise(self):
        os_ = bridge.build(model(), OWNER)["orders"]
        self.assertEqual([(o["verb"], o["ref"], o["extra"]) for o in os_],
                         [("labelled", "#903", "ready"), ("commented on", "#888", "")])

    def test_uses_the_real_trouble_fixture(self):
        b = bridge.build(model(trouble=TROUBLE), OWNER)
        self.assertEqual(b["commissions"], len(TROUBLE["scopes"]))
        html = bridge.render(b)
        self.assertNotIn("javascript:", html)   # the fixture's hostile link is dropped


class RenderTest(unittest.TestCase):
    def test_sections_in_order(self):
        html = bridge.render(bridge.build(model(), OWNER))
        order = [html.index(x) for x in ('aria-label="Status"', ">Decisions waiting<", ">Reports<",
                                         ">In flight<", ">Orders received<")]
        self.assertEqual(order, sorted(order))
        self.assertIn("Answer on GitHub", html)
        self.assertIn("you, via GitHub", html)
        self.assertIn("<b>Daily report, Thu 11-12.</b>", html)

    def test_empty_states(self):
        empty = {"repo": REPO, "now": NOW, "trouble": {"scopes": [], "outside": {}}, "floor": None,
                 "sessions": [], "gov": [], "report": None, "merged": [], "activity": None, "plan": None}
        html = bridge.render(bridge.build(empty, OWNER))
        for text in ("Nothing is waiting on you.", "No reports in the last 7 days.", "No open Goal or Area.",
                     "No acts of yours in the events read.", "nothing waits on you"):
            self.assertIn(text, html)

    def test_page_has_no_script_and_links_only_github_or_pages(self):
        page = bridge.page(model(), OWNER, "t", "")
        self.assertNotIn("<script", page)
        self.assertIn("script-src 'none'", page)
        for href in __import__("re").findall(r'href="([^"]+)"', page):
            self.assertRegex(href, r"^(https://github\.com/|[a-z]+\.html)")

    def test_generate_writes_it_first_in_the_footer(self):
        self.assertEqual(layout.PAGES[0], ("bridge.html", "Bridge"))
        self.assertIn('<span class="here" aria-current="page">Bridge</span>', layout.nav("bridge.html"))
        self.assertIn('href="bridge.html"', layout.nav("index.html"))


class MergedTest(unittest.TestCase):
    def test_merged_prs_from_closed_items(self):
        items = [{"number": 1, "title": "a", "html_url": "h1", "user": {"login": "x"},
                  "pull_request": {"merged_at": "2026-11-12T00:00:00Z"}},
                 {"number": 2, "title": "b", "pull_request": {"merged_at": None}},
                 {"number": 3, "title": "issue"}]
        self.assertEqual([p["number"] for p in g.merged_prs(items)], [1])


if __name__ == "__main__":
    unittest.main()
