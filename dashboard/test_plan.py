"""Tests for dashboard/plan.py (#712). Run: python3 -m unittest discover -s dashboard"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import live  # noqa: E402
import plan  # noqa: E402

REPO = "open-agentos/productswarm"
OWNER = "mattmcalister"
PLANNER = {"login": "productswarm-planner", "__typename": "Bot"}
ME = {"login": OWNER, "__typename": "User"}
AGENTS = {"productswarm-planner[bot]", "productswarm-builder[bot]"}


def node(n, title="t", state="OPEN", author=PLANNER, kind="Task", repo=REPO, **extra):
    return {"number": n, "title": title, "url": f"https://github.com/{repo}/issues/{n}", "state": state,
            "author": author, "repository": {"nameWithOwner": repo},
            "issueType": {"name": kind} if kind else None, **extra}


def subs(*nodes, total=None):
    return {"totalCount": len(nodes) if total is None else total, "nodes": list(nodes)}


def go(labels=(), ready_by=None, comments=(), blocked=(), prs=()):
    return {"labels": {"totalCount": len(labels), "nodes": [{"name": x} for x in labels]},
            "timelineItems": {"nodes": [{"label": {"name": "ready"}, "actor": ready_by}] if ready_by else []},
            "comments": {"totalCount": len(comments), "nodes": [{"author": a} for a in comments]},
            "blockedBy": {"totalCount": len(blocked),
                          "nodes": [{"number": b, "state": s, "repository": {"nameWithOwner": REPO}}
                                    for b, s in blocked]},
            "closedByPullRequestsReferences": {"nodes": [{"number": p, "url": f"https://github.com/{REPO}/pull/{p}"}
                                                         for p in prs]}}


def data():
    goal = node(685, "M3: The Desk shows the plan and the report", author=ME, kind="Goal")
    area = node(687, "Engine", author=ME, kind="Area")
    stray = node(690, "M9: Not the owner's", author=PLANNER, kind="Goal")
    mission = node(700, "Mission", kind="Mission",
                   subIssues=subs(node(701, subIssuesSummary={"total": 5, "completed": 2}),
                                  node(702, state="CLOSED")))
    return {
        "scopes": [area, stray, goal],
        "trees": {
            685: {"subIssues": subs(node(711, state="CLOSED"), node(713), node(712), mission)},
            687: {"subIssues": subs()},
            690: {"subIssues": subs(node(720))},
        },
        "go": {712: go(blocked=[(711, "CLOSED")], prs=[730]),
               713: go(blocked=[(711, "CLOSED"), (714, "OPEN")]),
               700: go(),
               701: go(comments=[ME])},
    }


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.p = plan.build(data(), OWNER, REPO, AGENTS)

    def test_goals_first_then_areas_and_only_the_owners(self):
        self.assertTrue(self.p["read"])
        self.assertEqual([(s["number"], s["kind"]) for s in self.p["scopes"]], [(685, "Goal"), (687, "Area")])
        self.assertEqual(self.p["not_plan"], [{"number": 690, "kind": "Goal", "author": "productswarm-planner[bot]",
                                               "url": f"https://github.com/{REPO}/issues/690"}])

    def test_goal_line(self):
        g = self.p["scopes"][0]
        self.assertEqual((g["lead"], g["title"]), ("M3", "The Desk shows the plan and the report"))
        self.assertEqual((g["open"], g["done"]), (3, 1))
        self.assertEqual([r["number"] for r in g["subs"]], [700, 712, 713])

    def test_statuses(self):
        rows = {r["number"]: r for r in self.p["scopes"][0]["subs"]}
        self.assertEqual(rows[712]["status"], {"kind": "go", "text": "go"})
        self.assertEqual(rows[712]["pr"]["number"], 730)
        self.assertEqual(rows[713]["status"], {"kind": "waiting", "text": "waiting on #714"})
        self.assertEqual(rows[700]["status"]["kind"], "not_go")
        self.assertIn("is a Mission, not an implementation issue", rows[700]["status"]["text"])

    def test_a_missions_tasks_sit_one_level_in(self):
        mission = self.p["scopes"][0]["subs"][0]
        self.assertEqual([c["number"] for c in mission["children"]], [701])   # the closed one isn't listed
        task = mission["children"][0]
        self.assertEqual(task["below"], 3)
        self.assertEqual(task["status"]["text"],
                         f"not go: @{OWNER} commented on #701: that's a veto until @{OWNER} labels it `ready`")

    def test_hold_and_the_owners_ready(self):
        d = data()
        d["go"][712] = go(labels=["hold"])
        d["go"][713] = go(labels=["ready"], ready_by=ME, blocked=[(714, "OPEN")])
        rows = {r["number"]: r for r in plan.build(d, OWNER, REPO, AGENTS)["scopes"][0]["subs"]}
        self.assertEqual(rows[712]["status"]["text"], "not go: #712 is labelled `hold`: the owner's veto")
        self.assertEqual(rows[713]["status"]["kind"], "go")

    def test_ready_added_by_someone_else_doesnt_count(self):
        d = data()
        d["go"][712] = go(labels=["ready"], ready_by=PLANNER, comments=[ME])
        row = plan.build(d, OWNER, REPO, AGENTS)["scopes"][0]["subs"][1]
        self.assertEqual(row["status"]["kind"], "not_go")

    def test_unread_links_are_status_unknown(self):
        d = data()
        d["go"][712] = None
        row = plan.build(d, OWNER, REPO, AGENTS)["scopes"][0]["subs"][1]
        self.assertEqual(row["status"], {"kind": "unknown", "text": "status unknown: couldn't read its links"})

    def test_render(self):
        html = plan.render(self.p)
        self.assertIn('<span class="mono">M3</span>', html)
        self.assertIn("3 open, 1 done", html)
        self.assertIn("Nothing open under it.", html)
        self.assertIn("and 3 more below", html)
        self.assertIn(">PR #730</a>", html)
        self.assertIn("Not plan: <a", html)
        self.assertIn("a Goal opened by productswarm-planner[bot] (GOV-0031).", html)
        live.tree(html)   # the live refresh can draw it

    def test_empty_and_unread(self):
        self.assertIn("No plan: the owner has no open Goal or Area.",
                      plan.render(plan.build({"scopes": [], "trees": {}, "go": {}}, OWNER, REPO, AGENTS)))
        self.assertIn("Couldn't read the plan from GitHub.", plan.render(plan.build(None, OWNER, REPO, AGENTS)))

    def test_title_parts(self):
        self.assertEqual(plan.title_parts("M1: Daily report"), ("M1", "Daily report"))
        self.assertEqual(plan.title_parts("Engine"), ("", "Engine"))


class FetchTest(unittest.TestCase):
    def test_search_then_trees_then_go(self):
        d = data()
        out = {"data": {"goal": {"nodes": [d["scopes"][2], d["scopes"][1]]}, "area": {"nodes": [d["scopes"][0]]}}}
        searched = []

        def run(args, **kw):
            searched.append(args)
            return subprocess.CompletedProcess(args, 0, json.dumps(out), "")

        asked = []

        def batched(repo, numbers, field, size):
            asked.append((numbers, field.split(":", 1)[1].split("{", 2)[1].strip()))
            src = d["trees"] if "subIssues" in field[:80] else d["go"]
            return {n: src.get(n) for n in numbers}

        got = plan.fetch(REPO, run, batched)
        self.assertEqual(len(searched), 1)
        q = searched[0][-1]
        self.assertIn("is:open type:Goal", q)
        self.assertIn("is:open type:Area", q)
        self.assertEqual(asked[0][0], [685, 687, 690])
        self.assertEqual(asked[1][0], [700, 701, 712, 713, 720])   # the open ones, both levels
        self.assertEqual(sorted(got["go"]), [700, 701, 712, 713, 720])

    def test_a_failed_search_is_none(self):
        def run(args, **kw):
            return subprocess.CompletedProcess(args, 1, "", "HTTP 502")
        self.assertIsNone(plan.fetch(REPO, run, None))

    def test_a_failed_batch_leaves_its_numbers_none(self):
        out = {"data": {"goal": {"nodes": [node(685, author=ME, kind="Goal")]}, "area": {"nodes": []}}}

        def batched(*a):
            raise RuntimeError("gh api graphql failed")
        got = plan.fetch(REPO, lambda a, **k: subprocess.CompletedProcess(a, 0, json.dumps(out), ""), batched)
        self.assertEqual(got["trees"], {685: None})
        g = plan.build(got, OWNER, REPO, AGENTS)["scopes"][0]
        self.assertIsNone(g["open"])
        self.assertIn("couldn't read its sub-issues", plan.render(plan.build(got, OWNER, REPO, AGENTS)))


if __name__ == "__main__":
    unittest.main()
