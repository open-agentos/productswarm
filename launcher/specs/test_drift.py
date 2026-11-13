"""Tests for launcher/specs/drift.py (#956): `swarm specs diff` and the lead's decisions,
against the fake backend.

Uses #941's fixture, `FakeSource.edit_spec` and a stub GitHub; no network.
Run: python3 run_tests.py launcher
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from specs import drift, events, snapshot, sync  # noqa: E402
from specs.fake import FakeSource  # noqa: E402
from specs.test_sync import FIXTURE, INIT, OWNER, REPO, goal_node  # noqa: E402

GOAL = (REPO, 938)
GOAL_REF = f"{REPO}#938"
PULLED = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)   # after every fixture edit
NOW = datetime(2026, 11, 13, 9, 30, tzinfo=timezone.utc)
NEW_SCOPE = "Paste a recipe URL or a photo; the box stores its title, ingredients and steps."


class StubGitHub:
    """GitHub in memory: Goals, issues with bodies and states, sub-issues and every write."""

    def __init__(self, goals=None):
        self.goals = {938: goal_node()} if goals is None else goals
        self.issues: dict[int, dict] = {}
        self.subs: dict[int, list[int]] = {}           # Goal number → sub-issue numbers
        self.writes: list[tuple] = []
        self.prs: dict[int, list[tuple]] = {}

    def add(self, n, body, state="open", goal=938):
        self.issues[n] = {"id": 5000 + n, "number": n, "state": state, "body": body,
                          "html_url": f"https://github.com/{REPO}/issues/{n}"}
        self.subs.setdefault(goal, []).append(n)

    def goal(self, repo, n):
        return self.goals.get(n)

    def open_goals(self, repo, owner):
        return sorted(self.goals)

    def sub_issues(self, repo, n):
        return [dict(self.issues[i]) for i in self.subs.get(n, [])]

    def open_issue(self, repo, title, body):
        n = 200 + len([w for w in self.writes if w[0] == "open_issue"])
        self.writes.append(("open_issue", repo, title))
        self.issues[n] = {"id": 5000 + n, "number": n, "state": "open", "body": body,
                          "title": title, "html_url": f"https://github.com/{repo}/issues/{n}"}
        return self.issues[n]

    def add_sub_issue(self, repo, n, sub_issue_id):
        self.writes.append(("add_sub_issue", repo, n, sub_issue_id))
        self.subs.setdefault(n, []).append(sub_issue_id - 5000)

    def edit_body(self, repo, n, body):
        self.writes.append(("edit_body", repo, n))
        self.issues[n]["body"] = body

    def comment(self, repo, n, body):
        self.writes.append(("comment", repo, n, body))

    def open_prs_closing(self, repo, n):
        return self.prs.get(n, [])

    def add_blocked_by(self, repo, n, blocking_id):
        self.writes.append(("add_blocked_by", repo, n, blocking_id))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"PRODUCTSWARM_HOME": self.tmp.name})
        env.start()
        self.addCleanup(env.stop)
        self.source = FakeSource(FIXTURE)
        self.reads: list[str] = []
        orig = self.source.get_spec
        self.source.get_spec = lambda fid: (self.reads.append(fid), orig(fid))[1]
        self.lines: list[str] = []
        self.gh = StubGitHub()
        # FEAT-1 pulled into open #101; FEAT-4 into #7, since closed.
        self.gh.add(101, self.body("FEAT-1"))
        self.gh.add(7, self.body("FEAT-4"), state="closed")
        self.gh.add(102, "A sub-issue with no snapshot.\n")

    def body(self, fid, when=PULLED):
        f = self.source._features[fid]
        block = snapshot.render(f, self.source._specs[fid], "fake", when)
        return sync.issue_body(block, GOAL_REF)

    def check(self):
        return drift.check(GOAL, self.source, self.gh, owner=OWNER, now=NOW)

    def diff(self, goal=GOAL, **kw):
        return drift.diff(goal, self.source, self.gh, owner=OWNER, repo=REPO, now=NOW,
                          out=self.lines.append, **kw)

    def decide(self, fid, choice):
        return drift.decide(GOAL, fid, choice, self.source, self.gh, owner=OWNER, now=NOW,
                            out=self.lines.append)

    def decisions(self):
        return [(e["feature"], e["choice"]) for e in events.read() if e["kind"] == "decision"]


class DiffTest(Base):
    def test_no_edit_nothing_changes_and_no_spec_is_read(self):
        d = self.check()
        self.assertEqual([(c.feature_id, c.ref, c.changed) for c in d.checks],
                         [("FEAT-1", f"{REPO}#101", False), ("FEAT-4", f"{REPO}#7", False)])
        self.assertEqual(self.reads, [])
        self.diff()
        self.assertEqual(self.lines, [f"swarm specs diff: Goal {GOAL_REF}, fake://{INIT}, "
                                      "simulated: 0 changed, 2 unchanged"])
        self.assertEqual(self.gh.writes, [])
        self.assertEqual(self.source.writes, [])
        self.assertEqual(list(events.read()), [])

    def test_an_edit_is_caught_with_the_diff(self):
        self.source.edit_spec("FEAT-1", scope=NEW_SCOPE)
        d = self.check()
        [c] = d.changes
        self.assertEqual((c.feature_id, c.state, c.sections), ("FEAT-1", "open", ["Scope"]))
        self.assertIn(f"+{NEW_SCOPE}", c.diff)
        self.assertTrue(any(ln.startswith("-Paste a recipe URL; the box") for ln in c.diff))
        self.assertLessEqual(len(c.diff), drift.MAX_DIFF_LINES)
        self.assertEqual(self.reads, ["FEAT-1"])          # FEAT-4 untouched: not read

        self.diff()
        self.assertIn("1 changed, 1 unchanged", self.lines[0])
        self.assertIn(f"  FEAT-1 Save a recipe from a link: {REPO}#101 (open) changed in Scope",
                      self.lines)
        report = [ln.strip() for ln in self.lines if "Spec changed:" in ln]
        self.assertEqual(report, [
            f"Spec changed: FEAT-1 Save a recipe from a link ({REPO}#101, open) since its "
            f"snapshot of 2026-11-05: Scope. Lead decides: swarm specs diff {GOAL_REF} "
            "--adopt | --defer | --ask FEAT-1"])
        self.assertEqual(self.gh.writes, [])
        self.assertEqual(list(events.read()), [])

    def test_long_diff_is_cut(self):
        self.source.edit_spec("FEAT-1", notes="\n".join(f"line {i}" for i in range(40)))
        [c] = self.check().changes
        self.assertEqual(len(c.diff), drift.MAX_DIFF_LINES)
        self.assertTrue(c.diff[-1].startswith("… "))

    def test_a_touch_with_the_same_content_is_unchanged(self):
        same = self.source._specs["FEAT-1"].scope
        self.source.edit_spec("FEAT-1", scope=same)
        d = self.check()
        self.assertEqual(d.changes, [])
        self.assertEqual(self.reads, ["FEAT-1"])          # read, compared, unchanged

    def test_closed_issue_drift_is_reported_as_closed(self):
        self.source.edit_spec("FEAT-4", notes="Also match plurals.")
        [c] = self.check().changes
        self.assertEqual((c.feature_id, c.state, c.sections), ("FEAT-4", "closed", ["Notes"]))

    def test_json(self):
        self.source.edit_spec("FEAT-1", scope=NEW_SCOPE)
        self.diff(as_json=True)
        data = json.loads("\n".join(self.lines))
        [g] = data["goals"]
        self.assertEqual(g["goal"], GOAL_REF)
        self.assertEqual(g["unchanged"], ["FEAT-4"])
        [ch] = g["changes"]
        self.assertEqual((ch["feature"], ch["issue"], ch["state"], ch["sections"]),
                         ("FEAT-1", f"{REPO}#101", "open", ["Scope"]))
        self.assertTrue(ch["report"].startswith("Spec changed: FEAT-1"))
        self.assertEqual(ch["live_hash"], self.source._specs["FEAT-1"].content_hash())

    def test_every_linked_goal_without_a_goal(self):
        self.gh.goals[939] = goal_node(body="No link here.\n")
        self.gh.goals[940] = goal_node(body=f"Spec source: fake://{INIT}\n", author="someone")
        self.source.edit_spec("FEAT-1", scope=NEW_SCOPE)
        results = self.diff(goal=None)
        self.assertEqual([d.ref for d in results], [GOAL_REF])
        self.assertIn(f"swarm specs diff: skipped {REPO}#940: {REPO}#940 was opened by someone, "
                      f"not the owner (@{OWNER})", self.lines)
        self.assertFalse(any("#939" in ln for ln in self.lines))

    def test_bad_snapshot_is_listed_not_fatal(self):
        self.gh.add(103, "<!-- swarm:spec feature=FEAT-9 -->\n")
        d = self.check()
        self.assertEqual(len(d.checks), 2)
        self.assertEqual(len(d.problems), 1)
        self.assertIn(f"{REPO}#103", d.problems[0])

    def test_feature_gone_from_the_source(self):
        self.gh.add(104, self.body("FEAT-1").replace("feature=FEAT-1", "feature=FEAT-99"))
        d = self.check()
        c = next(c for c in d.checks if c.feature_id == "FEAT-99")
        self.assertIn("no longer in fake://", c.note)

    def test_refusals_are_pulls(self):
        self.gh.goals[938] = goal_node(body=f"Spec source: notion://{INIT}\n")
        with self.assertRaisesRegex(sync.Refused, "notion:// source"):
            self.check()
        self.gh.goals[938] = goal_node(editors=("mallory",))
        with self.assertRaisesRegex(sync.Refused, "edited by mallory"):
            self.check()


class DecisionTest(Base):
    def test_adopt_on_an_open_issue(self):
        self.gh.prs[101] = [(REPO, 150)]
        self.source.edit_spec("FEAT-1", scope=NEW_SCOPE)
        event = self.decide("FEAT-1", "adopt")
        snap = snapshot.parse(self.gh.issues[101]["body"])
        new_hash = self.source._specs["FEAT-1"].content_hash()
        self.assertEqual((snap.hash, snap.pulled), (new_hash, NOW))
        self.assertTrue(self.gh.issues[101]["body"].endswith(f"Goal: {GOAL_REF}\n"))
        comments = [(w[2], w[3]) for w in self.gh.writes if w[0] == "comment"]
        self.assertEqual([n for n, _ in comments], [101, 150])
        for _, text in comments:
            self.assertIn("Changed: Scope.", text)
            self.assertIn(f"+{NEW_SCOPE}", text)
        self.assertEqual([w[0] for w in self.gh.writes if w[0] != "comment"], ["edit_body"])
        self.assertEqual((event["choice"], event["where"], event["hash"], event["prs"]),
                         ("adopt", f"https://github.com/{REPO}/issues/101", new_hash,
                          [f"{REPO}#150"]))
        self.assertEqual(self.decisions(), [("FEAT-1", "adopt")])
        self.assertEqual(self.source.writes, [])
        # Settled: the next diff finds nothing, and the same decision has nothing to do.
        self.assertEqual(self.check().changes, [])
        with self.assertRaisesRegex(drift.Undecidable, "hasn't changed"):
            self.decide("FEAT-1", "adopt")

    def test_adopt_on_a_closed_issue_opens_a_new_sub_issue(self):
        before = self.gh.issues[7]["body"]
        self.source.edit_spec("FEAT-4", notes="Also match plurals.")
        event = self.decide("FEAT-4", "adopt")
        self.assertEqual([w[0] for w in self.gh.writes], ["open_issue", "add_sub_issue"])
        self.assertEqual(self.gh.issues[7]["state"], "closed")     # never reopened
        self.assertEqual(self.gh.issues[7]["body"], before)
        new = self.gh.issues[200]
        snap = snapshot.parse(new["body"])
        self.assertEqual(snap.hash, self.source._specs["FEAT-4"].content_hash())
        self.assertEqual(new["title"], "Search recipes by ingredient: spec change after #7")
        self.assertNotIn("Waits on", new["body"])
        self.assertEqual(self.gh.writes[1], ("add_sub_issue", REPO, 938, new["id"]))
        self.assertEqual((event["choice"], event["where"]),
                         ("adopt", new["html_url"]))
        self.assertEqual(self.decisions(), [("FEAT-4", "adopt")])
        self.assertEqual(self.check().changes, [])                  # the new snapshot counts

    def test_defer_on_an_open_issue(self):
        before = self.gh.issues[101]["body"]
        self.source.edit_spec("FEAT-1", scope=NEW_SCOPE)
        event = self.decide("FEAT-1", "defer")
        self.assertEqual([w[0] for w in self.gh.writes],
                         ["open_issue", "add_sub_issue", "add_blocked_by"])
        new = self.gh.issues[200]
        self.assertEqual(self.gh.writes[2], ("add_blocked_by", REPO, 200, 5101))
        self.assertTrue(new["body"].endswith(f"Goal: {GOAL_REF}\n**Waits on:** #101\n"))
        self.assertEqual(snapshot.parse(new["body"]).hash,
                         self.source._specs["FEAT-1"].content_hash())
        self.assertEqual(self.gh.issues[101]["body"], before)   # left as it was
        self.assertEqual((event["choice"], event["where"]), ("defer", new["html_url"]))
        self.assertEqual(self.decisions(), [("FEAT-1", "defer")])
        self.assertEqual(self.check().changes, [])

    def test_defer_on_a_closed_issue(self):
        self.source.edit_spec("FEAT-4", notes="Also match plurals.")
        self.decide("FEAT-4", "defer")
        self.assertEqual([w[0] for w in self.gh.writes],
                         ["open_issue", "add_sub_issue", "add_blocked_by"])
        self.assertIn("**Waits on:** #7", self.gh.issues[200]["body"])
        self.assertEqual(self.gh.issues[7]["state"], "closed")
        self.assertEqual(self.decisions(), [("FEAT-4", "defer")])

    def test_ask_writes_nothing_on_github(self):
        for fid, state in (("FEAT-1", "open"), ("FEAT-4", "closed")):
            with self.subTest(fid):
                self.source.edit_spec(fid, notes="Changed.")
                self.lines.clear()
                event = self.decide(fid, "ask")
                self.assertEqual(self.gh.writes, [])
                [line] = self.lines
                self.assertIn(f"{fid} ", line)
                self.assertIn("the spec changed after", line)
                self.assertIn("(Notes)", line)
                self.assertEqual((event["choice"], event["where"], event["ask"]),
                                 ("ask", "report", line))
        self.assertEqual(self.decisions(), [("FEAT-1", "ask"), ("FEAT-4", "ask")])
        self.assertEqual(len(self.check().changes), 2)     # an ask settles nothing

    def test_no_decision_without_a_change(self):
        for choice in drift.CHOICES:
            with self.assertRaisesRegex(drift.Undecidable, "hasn't changed"):
                self.decide("FEAT-1", choice)
        with self.assertRaisesRegex(drift.Undecidable, "holds a snapshot of FEAT-3"):
            self.decide("FEAT-3", "adopt")
        self.assertEqual(self.gh.writes, [])
        self.assertEqual(list(events.read()), [])

    def test_latest_snapshot_counts(self):
        # An older snapshot of FEAT-1 on a closed issue doesn't make FEAT-1 drift.
        old = self.source._specs["FEAT-1"]
        self.source.edit_spec("FEAT-1", scope=NEW_SCOPE)
        self.gh.add(99, sync.issue_body(snapshot.render(
            self.source._features["FEAT-1"], old, "fake", datetime(2026, 10, 1, tzinfo=timezone.utc)),
            GOAL_REF), state="closed")
        self.gh.issues[101]["body"] = self.body("FEAT-1", when=NOW)
        self.assertEqual(self.check().changes, [])


if __name__ == "__main__":
    unittest.main()
