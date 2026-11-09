"""Tests for #681 (GOV-0031): an issue under an open Goal or Area the owner opened is go,
for `swarm launch` and `swarm watch`, and the GOV-0026 milestone lines stop counting a week
after GOV-0031 merged. Canned GitHub data only."""
import dataclasses
import datetime as dt
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import swarm  # noqa: E402
import watch  # noqa: E402
import test_watch as tw  # noqa: E402
from test_watch import (MILESTONE_PLAN, NOW, OWNER, PLANNER_APP, REPO, ROLES,  # noqa: E402
                        call, ev, issue, milestone_issue, pr, trigger_lines)
from test_watch import SHA2  # noqa: E402

AGENTS = {PLANNER_APP, "productswarm-builder[bot]"}
OTHER = "open-agentos/agent-governance"


def parent(n, type_="Goal", state="open", author=OWNER, repo=REPO):
    return {"repo": repo, "number": n, "state": state, "type": type_, "author": author}


def scope(*parents, blocked=(), complete=True, type_=None):
    return {"author": OWNER, "type": type_, "parents": list(parents), "deep": len(parents) >= swarm.SCOPE_DEPTH,
            "blocked_by": [{"repo": REPO, "number": b, "state": s} for b, s in blocked],
            "blockers_complete": complete}


def task(n, author=PLANNER_APP, labels=(), body="Do it.\n"):
    it = issue(n, labels, body=body)
    it["user"] = {"login": author}
    return it


class ParseScopeTest(unittest.TestCase):
    def test_reads_the_chain_blockers_and_bot_logins(self):
        node = {"author": {"login": "productswarm-planner", "__typename": "Bot"}, "issueType": {"name": "Task"},
                "blockedBy": {"totalCount": 2, "nodes": [
                    {"number": 5, "state": "OPEN", "repository": {"nameWithOwner": REPO}},
                    {"number": 6, "state": "CLOSED", "repository": {"nameWithOwner": OTHER}}]},
                "parent": {"number": 20, "state": "OPEN", "author": {"login": "productswarm-lead", "__typename": "Bot"},
                           "issueType": {"name": "Mission"}, "repository": {"nameWithOwner": REPO},
                           "parent": {"number": 3, "state": "OPEN", "author": {"login": OWNER, "__typename": "User"},
                                      "issueType": {"name": "Goal"}, "repository": {"nameWithOwner": OTHER},
                                      "parent": None}}}
        s = swarm.parse_scope(node)
        self.assertEqual(s["author"], PLANNER_APP)
        self.assertEqual(s["type"], "Task")
        self.assertIsNone(swarm.parse_scope({"author": None, "parent": None})["type"])   # no type set
        self.assertEqual(s["parents"], [parent(20, "Mission", author="productswarm-lead[bot]"),
                                        parent(3, repo=OTHER)])
        self.assertEqual(s["blocked_by"], [{"repo": REPO, "number": 5, "state": "open"},
                                           {"repo": OTHER, "number": 6, "state": "closed"}])
        self.assertTrue(s["blockers_complete"])
        self.assertFalse(s["deep"])
        self.assertIsNone(swarm.parse_scope(None))

    def test_the_query_asks_for_every_level(self):
        self.assertEqual(swarm.scope_field().count("parent {"), swarm.SCOPE_DEPTH)
        self.assertEqual((swarm.scope_field() % (7, 7)).count("i7: issue(number: 7)"), 1)

    def test_one_graphql_query_per_25_issues(self):
        calls = []

        def run(argv, **kw):
            calls.append(argv)
            q = next(a for a in argv if a.startswith("query="))
            nums = [int(x) for x in re.findall(r"\bi(\d+): issue", q)]
            data = {f"i{n}": {"author": {"login": OWNER}, "blockedBy": {"totalCount": 0, "nodes": []},
                              "parent": None} for n in nums}
            return subprocess.CompletedProcess(argv, 0, json.dumps({"data": {"repository": data}}), "")
        swarm.dashboard()
        import ghql
        with mock.patch.object(ghql.subprocess, "run", run):
            got = swarm.gh_scopes(REPO, list(range(1, 31)))
        self.assertEqual(len(calls), 2)
        self.assertEqual(sorted(got), list(range(1, 31)))
        self.assertEqual(got[30]["parents"], [])


class ScopeRefusalTest(unittest.TestCase):
    def refusal(self, it=None, s=None, comments=(), **kw):
        it = it or task(30)
        return swarm.scope_refusal(30, it, s if s is not None else scope(parent(20, "Mission"), parent(3)),
                                   OWNER, AGENTS, lambda: list(comments), repo=REPO, **kw)

    def test_go_under_a_goal_or_area_at_any_depth(self):
        self.assertIsNone(self.refusal())
        self.assertIsNone(self.refusal(s=scope(parent(3, "Area"))))
        self.assertIsNone(self.refusal(s=scope(parent(21, "Task"), parent(20, "Mission"), parent(3, repo=OTHER))))
        self.assertIsNone(self.refusal(task(30, author=OWNER)))

    def test_what_doesnt_count(self):
        cases = {
            "not a sub-issue": (task(30), scope(), "isn't a sub-issue of anything"),
            "a Goal an App opened": (task(30), scope(parent(3, author=PLANNER_APP)),
                                     f"was opened by {PLANNER_APP}, not @{OWNER}"),
            "a closed Goal": (task(30), scope(parent(3, state="closed")), "Goal #3 is closed"),
            "only a Mission above": (task(30), scope(parent(20, "Mission")), "isn't under an open Goal or Area"),
            "opened by a stranger": (task(30, author="stranger"), None, "not a swarm App or @"),
            "hold": (task(30, labels=("hold",)), None, "`hold`: the owner's veto"),
            "an open blocker": (task(30), scope(parent(3), blocked=[(5, "open"), (6, "closed")]),
                                "blocked by #5, still open"),
            "too many blockers": (task(30), scope(parent(3), complete=False), "more than 50 blocked-by"),
        }
        for case, (it, s, want) in cases.items():
            with self.subTest(case):
                self.assertIn(want, self.refusal(it, s) or "")

    def test_only_implementation_types_are_go(self):
        """#690: Task, Bug, Feature or no type; never a Mission, Brief, Question, Lesson, Goal or Area."""
        for type_ in (None, "Task", "Bug", "Feature"):
            with self.subTest(type_):
                self.assertIsNone(self.refusal(s=scope(parent(3), type_=type_)))
        for type_ in ("Mission", "Brief", "Question", "Lesson", "Goal", "Area"):
            with self.subTest(type_):
                self.assertIn(f"#30 is a {type_}, not an implementation issue",
                              self.refusal(s=scope(parent(3), type_=type_)) or "")

    def test_ready_still_works_on_any_type(self):
        it = task(30, labels=("ready",))
        r = swarm.GoReader(plan=lambda: None, state=lambda w: "closed", comments=lambda: [],
                           scope=lambda: scope(parent(3), type_="Brief"))
        self.assertEqual(swarm.go_refusals(30, it, [ev("ready")], OWNER, AGENTS, r, now=NOW), [])

    def test_an_owners_comment_vetoes_unless_comments_are_left_out(self):
        said = [{"user": {"login": OWNER}, "body": "not yet"}]
        self.assertIn("that's a veto", self.refusal(comments=said))
        self.assertIsNone(swarm.scope_refusal(30, task(30), scope(parent(3)), OWNER, AGENTS, None))

    def test_blockers_can_be_left_to_the_watcher(self):
        s = scope(parent(3), blocked=[(5, "open")])
        self.assertIsNone(self.refusal(s=s, blockers=False))

    def test_an_issue_in_another_repo_is_named_with_its_repo(self):
        self.assertIn(f"{OTHER}#3 was opened by",
                      self.refusal(s=scope(parent(3, repo=OTHER, author=PLANNER_APP))))


class GoRefusalsTest(unittest.TestCase):
    def reader(self, s=None, plan=MILESTONE_PLAN):
        return swarm.GoReader(plan=lambda: plan, state=lambda w: "closed", comments=lambda: [],
                              scope=lambda: s)

    def go(self, it, s=None, events=(), now=NOW):
        return swarm.go_refusals(it["number"], it, list(events), OWNER, AGENTS, self.reader(s), now=now, repo=REPO)

    def test_ready_still_works_on_its_own(self):
        self.assertEqual(self.go(task(30, labels=("ready",)), events=[ev("ready")]), [])

    def test_a_goal_makes_it_go(self):
        self.assertEqual(self.go(task(30), scope(parent(3))), [])

    def test_a_failed_goal_gives_its_reason_first(self):
        refused = self.go(task(30), scope(parent(3, state="closed")))
        self.assertIn("Goal #3 is closed", refused[0])
        self.assertIn("isn't labelled `ready`", " ".join(refused[1:]))

    def test_with_no_parent_and_no_milestone_only_ready_is_named(self):
        self.assertEqual(self.go(task(30), scope()), swarm.issue_refusals(30, task(30), [], OWNER))

    def test_a_gov_question_is_go_only_by_ready(self):
        self.assertTrue(self.go(task(30, labels=("gov:question",)), scope(parent(3))))

    def test_the_milestone_counts_until_the_week_ends(self):
        it = milestone_issue(49)
        before = swarm.MILESTONE_UNTIL - dt.timedelta(seconds=1)
        self.assertEqual(self.go(it, now=before), [])
        refused = self.go(it, now=swarm.MILESTONE_UNTIL)
        self.assertIn("stopped counting at 2026-11-16 13:54 UTC (GOV-0031)", refused[0])
        self.assertEqual(self.go(it, scope(parent(3)), now=swarm.MILESTONE_UNTIL), [])   # its Goal still does


class ScopeScene:
    """Wraps test_watch's Scene with each issue's scope, as gather() reads it."""

    def __init__(self, scene, scopes):
        self.scene, self.scopes = scene, scopes

    def read(self, repo, idle, now):
        return dataclasses.replace(self.scene.read(repo, idle, now), scopes=dict(self.scopes), repo=REPO)

    def get_reader(self, repo, n):
        r = self.scene.get_reader(repo, n)
        return dataclasses.replace(r, scope=lambda: self.scopes.get(n))


class WatchGoalTest(unittest.TestCase):
    """`swarm watch` starts [build] on an issue under an owner-opened Goal or Area."""

    setUp_start = tw.StartTest.setUp
    manifest, started, exit = tw.StartTest.manifest, tw.StartTest.started, tw.StartTest.exit

    def setUp(self):
        self.setUp_start()
        sc = self.scene
        sc.issues, sc.events = [task(30)], {30: []}
        sc.prs, sc.reviewed, sc.tracking, sc.comments = [], {}, [], {}
        sc.plan = None
        self.scopes = {30: scope(parent(20, "Mission"), parent(3))}

    def watcher(self, dry_run=False):
        s = ScopeScene(self.scene, self.scopes)
        return watch.Watch(self.l, REPO, OWNER, ROLES, dry_run=dry_run, manifest_path=self.path,
                           read=s.read, get_issue=self.scene.get_issue,
                           get_heartbeat=self.scene.heartbeat, get_reader=s.get_reader)

    def builds(self, w=None, at=NOW):
        return [(t.key, t.why) for t in (w or self.watcher()).tick(at) if t.kind == "build"]

    def test_an_issue_under_a_goal_builds_once(self):
        self.assertEqual(self.builds(), [(f"build:30:G{REPO}#3", "go under Goal #3 (GOV-0031)")])
        self.assertEqual(self.started(), [("builder-issue-30", "builder", "m-builder", 30, "watch")])
        self.exit("builder-issue-30")
        self.assertEqual(self.builds(), [])

    def test_dry_run_prints_it(self):
        self.builds(self.watcher(dry_run=True))
        self.assertEqual(trigger_lines(self.lines), [
            "[build] #30 go under Goal #3 (GOV-0031) -> would start `launcher/swarm launch builder --issue 30`"])

    def test_an_open_blocker_holds_it_until_it_closes(self):
        self.scopes[30] = scope(parent(3), blocked=[(5, "open")])
        self.assertEqual(self.builds(), [])
        self.assertTrue(any("held: waits on #5 (blocked by)" in x for x in self.lines), self.lines)
        self.assertEqual(self.started(), [])
        self.scopes[30] = scope(parent(3), blocked=[(5, "closed")])
        self.assertEqual([k for k, _ in self.builds()], [f"build:30:G{REPO}#3"])

    def test_a_blocker_holds_a_ready_build_too(self):
        self.scene.issues = [task(30, labels=("ready",))]
        self.scene.events = {30: [ev("ready", eid=11)]}
        self.scopes[30] = scope(blocked=[(5, "open")])
        self.assertEqual(self.builds(), [])
        self.assertTrue(any("held: waits on #5 (blocked by)" in x for x in self.lines), self.lines)

    def test_these_dont_build(self):
        cases = {
            "a Goal an App opened": lambda: self.scopes.update({30: scope(parent(3, author=PLANNER_APP))}),
            "a closed Goal": lambda: self.scopes.update({30: scope(parent(3, state="closed"))}),
            "no parent": lambda: self.scopes.update({30: scope()}),
            "a stranger's issue": lambda: setattr(self.scene, "issues", [task(30, author="stranger")]),
            "hold": lambda: setattr(self.scene, "issues", [task(30, labels=("hold",))]),
            "a Mission": lambda: self.scopes.update({30: scope(parent(3), type_="Mission")}),
            "a Brief": lambda: self.scopes.update({30: scope(parent(3), type_="Brief")}),
            "the owner commented": lambda: self.scene.comments.update(
                {30: [{"user": {"login": OWNER}, "body": "not yet"}]}),
        }
        for case, change in cases.items():
            with self.subTest(case):
                self.setUp()
                change()
                self.assertEqual(self.builds(), [], case)
                self.assertEqual(self.started(), [], case)

    def test_milestone_issues_stop_building_when_the_week_ends(self):
        self.scene.issues, self.scene.events, self.scene.plan = [milestone_issue(49)], {49: []}, MILESTONE_PLAN
        self.scopes = {}
        self.assertEqual(self.builds(self.watcher(dry_run=True), at=swarm.MILESTONE_UNTIL), [])
        self.assertEqual([k for k, _ in self.builds(at=swarm.MILESTONE_UNTIL - dt.timedelta(minutes=1))],
                         ["build:49:M1"])


class GoalCallInTest(unittest.TestCase):
    """#681: `Call in:` lines count on an issue under an owner-opened Goal or Area, as on a
    milestone issue (#594), even while it is blocked."""

    setUp_call = tw.CallInTest.setUp
    manifest, tick, called, say = tw.CallInTest.manifest, tw.CallInTest.tick, tw.CallInTest.called, tw.CallInTest.say

    def setUp(self):
        self.setUp_call()
        self.scene.prs.append(pr(73, SHA2, closes=(90,)))     # no [build] on #90 to take a slot
        self.scene.issues.append(task(90))
        self.scene.events[90] = []
        self.scopes = {90: scope(parent(3), blocked=[(5, "open")])}

    def watcher(self, dry_run=False):
        s = ScopeScene(self.scene, self.scopes)
        return watch.Watch(self.l, REPO, OWNER, ROLES, dry_run=dry_run, manifest_path=self.path,
                           read=s.read, get_issue=self.scene.get_issue,
                           get_heartbeat=self.scene.heartbeat, get_reader=s.get_reader)

    def test_a_call_on_a_goal_issue_without_ready_starts_the_role(self):
        self.say(call(501, "Call in: docs: check the wording"), n=90)
        self.assertEqual([t.key for t in self.tick()], ["call-in:90:501:docs"])
        self.assertEqual([c[0] for c in self.called()], ["docs-issue-90"])

    def test_not_under_an_app_opened_goal(self):
        self.scopes[90] = scope(parent(3, author=PLANNER_APP))
        self.say(call(501, "Call in: docs: x"), n=90)
        self.assertEqual(self.tick(), [])


if __name__ == "__main__":
    unittest.main()
