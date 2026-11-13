"""Tests for launcher/specs/sync.py (#955): `swarm specs pull` against the fake backend.

Uses #941's fixture and a stub GitHub; no network. Run: python3 run_tests.py launcher
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
from specs import events, snapshot, sync  # noqa: E402
from specs.fake import FakeSource  # noqa: E402
from specs.source import FeatureStatus, SchemaError  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "testdata" / "fake_initiative.json"
OWNER = "owner-login"
REPO = "acme/productswarm"
GOAL = (REPO, 938)
NOW = datetime(2026, 11, 13, 9, 30, tzinfo=timezone.utc)
INIT = "init-0001-recipe-box"
DRAFT_TEXT = ("Weekly meal plan", "Deciding what to cook", "seven-day grid", "Shopping lists",
              "dragged onto a day")


def goal_node(body=f"Outcome.\n\nSpec source: fake://{INIT}\n", state="OPEN", kind="Goal",
              author=OWNER, bot=False, editors=(), total=None):
    edits = [{"editor": {"login": e, "__typename": "User"}} for e in editors]
    return {"state": state, "body": body, "issueType": {"name": kind} if kind else None,
            "author": {"login": author, "__typename": "Bot" if bot else "User"},
            "userContentEdits": {"totalCount": len(edits) if total is None else total,
                                 "nodes": edits}}


class StubGitHub:
    """GitHub in memory: a Goal to read, issues opened and sub-issues added."""

    def __init__(self, node=None, fail_sub=False):
        self.node = goal_node() if node is None else node
        self.opened: list[dict] = []
        self.subs: list[tuple] = []
        self.reads: list[tuple] = []
        self.fail_sub = fail_sub

    def goal(self, repo, n):
        self.reads.append((repo, n))
        return self.node

    def open_issue(self, repo, title, body):
        n = 100 + len(self.opened)
        issue = {"id": 5000 + n, "number": n, "repo": repo, "title": title, "body": body,
                 "html_url": f"https://github.com/{repo}/issues/{n}"}
        self.opened.append(issue)
        return issue

    def add_sub_issue(self, repo, n, sub_issue_id):
        if self.fail_sub:
            raise RuntimeError("gh api failed: boom")
        self.subs.append((repo, n, sub_issue_id))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"PRODUCTSWARM_HOME": self.tmp.name})
        env.start()
        self.addCleanup(env.stop)
        self.fixture = Path(self.tmp.name) / "fixture.json"
        self.fixture.write_text(FIXTURE.read_text())
        self.source = FakeSource(self.fixture)
        self.lines: list[str] = []

    def pull(self, gh, dry_run=False, source=None, **kw):
        return sync.pull(GOAL, source or self.source, gh, NOW, dry_run, owner=OWNER,
                         out=self.lines.append, **kw)

    def assert_nothing_written(self, gh, source=None):
        self.assertEqual(gh.opened, [])
        self.assertEqual(gh.subs, [])
        self.assertEqual((source or self.source).writes, [])
        self.assertEqual(list(events.read()), [])


class PullTest(Base):
    def test_opens_one_issue_per_ready_pullable_unlinked_feature(self):
        gh = StubGitHub()
        results = self.pull(gh)
        self.assertEqual([(r.feature_id, r.outcome) for r in results], [
            ("FEAT-1", sync.OPENED), ("FEAT-2", sync.NOT_PULLABLE), ("FEAT-3", sync.SKIPPED),
            ("FEAT-4", sync.LINKED), ("FEAT-5", sync.SKIPPED)])
        self.assertEqual(len(gh.opened), 1)
        issue = gh.opened[0]
        self.assertEqual(issue["repo"], REPO)
        self.assertEqual(issue["title"], "Save a recipe from a link")
        self.assertEqual(gh.subs, [(REPO, 938, issue["id"])])

        snap = snapshot.parse(issue["body"])
        spec = self.source.get_spec("FEAT-1")
        self.assertEqual((snap.feature_id, snap.hash, snap.source, snap.pulled),
                         ("FEAT-1", spec.content_hash(), "fake", NOW))
        self.assertIn("Pasting a recipe URL saves", snap.sections["Acceptance criteria"])
        # The block, the Goal line and nothing else (#943, Part B).
        block = snapshot.render(self.source._features["FEAT-1"], spec, "fake", NOW)
        self.assertEqual(issue["body"], f"{block}\n\nGoal: {REPO}#938\n")

    def test_feature_gets_issue_url_and_in_progress(self):
        gh = StubGitHub()
        self.pull(gh)
        url = gh.opened[0]["html_url"]
        f = self.source._features["FEAT-1"]
        self.assertEqual((f.issue_url, f.status), (url, FeatureStatus.IN_PROGRESS))
        self.assertEqual([w[0] for w in self.source.writes], ["set_links", "set_status"])
        # Nothing else in the source moved.
        for fid in ("FEAT-2", "FEAT-3", "FEAT-4", "FEAT-5"):
            before = FakeSource(FIXTURE)._features[fid]
            self.assertEqual(self.source._features[fid], before)

    def test_events_logged(self):
        gh = StubGitHub()
        self.pull(gh)
        url = gh.opened[0]["html_url"]
        got = [(e["kind"], e.get("what"), e["goal"], e["feature"]) for e in events.read()]
        self.assertEqual(got, [("pull", None, f"{REPO}#938", "FEAT-1"),
                               ("write", "links", f"{REPO}#938", "FEAT-1"),
                               ("write", "status", f"{REPO}#938", "FEAT-1")])
        pull_event = events.read()[0]
        self.assertEqual(pull_event["issue_url"], url)
        self.assertEqual(pull_event["hash"], self.source.get_spec("FEAT-1").content_hash())

    def test_output_lines(self):
        gh = StubGitHub()
        self.pull(gh)
        url = gh.opened[0]["html_url"]
        self.assertEqual(self.lines[1:], [
            f"  FEAT-1 Save a recipe from a link: opened {url}",
            "  FEAT-2 Scale a recipe's servings: not pullable (no Acceptance criteria heading)",
            "  FEAT-3: skipped (Draft)",
            "  FEAT-4 Search recipes by ingredient: already linked to "
            "https://github.com/example/recipe-box/issues/7",
            "  FEAT-5: skipped (In review)",
        ])
        self.assertIn("simulated", self.lines[0])

    def test_no_draft_text_anywhere(self):
        gh = StubGitHub()
        seen = []
        orig = self.source.get_spec
        self.source.get_spec = lambda fid: (seen.append(fid), orig(fid))[1]
        self.pull(gh)
        self.assertNotIn("FEAT-3", seen)   # a Draft's spec is never even fetched
        everything = "\n".join(self.lines + [i["body"] + i["title"] for i in gh.opened])
        for text in DRAFT_TEXT:
            self.assertNotIn(text, everything)

    def test_second_run_opens_nothing(self):
        gh = StubGitHub()
        self.pull(gh)
        self.source.dump(self.fixture)
        again = FakeSource(self.fixture)
        results = self.pull(gh, source=again)
        self.assertEqual(len(gh.opened), 1)
        self.assertEqual(again.writes, [])
        self.assertEqual(dict((r.feature_id, r.outcome) for r in results)["FEAT-1"], sync.SKIPPED)

    def test_ready_linked_feature_not_reopened_even_with_empty_log(self):
        # The Issue field is the key, not the log (#942).
        gh = StubGitHub()
        results = self.pull(gh)
        self.assertEqual(dict((r.feature_id, r.outcome) for r in results)["FEAT-4"], sync.LINKED)
        self.assertNotIn("Search recipes by ingredient", [i["title"] for i in gh.opened])

    def test_dry_run_writes_nothing(self):
        gh = StubGitHub()
        before = self.fixture.read_text()
        results = self.pull(gh, dry_run=True)
        self.assert_nothing_written(gh)
        self.assertEqual(self.fixture.read_text(), before)
        self.assertFalse(events.path().exists())
        self.assertEqual([r.outcome for r in results],
                         [sync.OPENED, sync.NOT_PULLABLE, sync.SKIPPED, sync.LINKED, sync.SKIPPED])
        self.assertIn("  FEAT-1 Save a recipe from a link: would open an issue in "
                      f"{REPO}", self.lines)
        self.assertIn("dry run", self.lines[0])

    def test_repo_line_picks_the_target_repo(self):
        gh = StubGitHub(goal_node(body=f"Spec source: fake://{INIT}\nRepo: acme/scratch\n"))
        self.pull(gh)
        self.assertEqual(gh.opened[0]["repo"], "acme/scratch")
        self.assertEqual(gh.subs, [(REPO, 938, gh.opened[0]["id"])])
        self.assertTrue(gh.opened[0]["body"].endswith(f"Goal: {REPO}#938\n"))

    def test_failure_after_open_keeps_the_link(self):
        # A sub-issue failure mid-run: the link is already written, so a rerun won't duplicate.
        gh = StubGitHub(fail_sub=True)
        with self.assertRaises(RuntimeError):
            self.pull(gh)
        self.assertEqual(self.source._features["FEAT-1"].issue_url, gh.opened[0]["html_url"])
        self.assertEqual([w[0] for w in self.source.writes], ["set_links"])


class RefusalTest(Base):
    def refused(self, gh, pattern, **kw):
        with self.assertRaisesRegex(sync.Refused, pattern):
            self.pull(gh, **kw)
        self.assert_nothing_written(gh)
        self.assertEqual(self.lines, [])

    def test_missing_goal(self):
        gh = StubGitHub()
        gh.node = None
        self.refused(gh, "doesn't exist")

    def test_not_a_goal(self):
        self.refused(StubGitHub(goal_node(kind="Area")), "isn't a Goal")
        self.refused(StubGitHub(goal_node(kind=None)), "isn't a Goal")

    def test_closed_goal(self):
        self.refused(StubGitHub(goal_node(state="CLOSED")), "isn't open")

    def test_goal_not_opened_by_owner(self):
        self.refused(StubGitHub(goal_node(author="productswarm-planner", bot=True)),
                     r"opened by productswarm-planner\[bot\]")
        self.refused(StubGitHub(goal_node(author="someone")), "opened by someone")

    def test_body_edited_by_someone_else(self):
        self.refused(StubGitHub(goal_node(editors=(OWNER, "mallory"))), "edited by mallory")

    def test_owner_edits_are_fine(self):
        self.pull(StubGitHub(goal_node(editors=(OWNER, OWNER))))
        self.assertEqual(len(self.source.writes), 2)

    def test_edit_history_too_long(self):
        self.refused(StubGitHub(goal_node(editors=(OWNER,), total=150)), "too long")

    def test_no_link_line(self):
        self.refused(StubGitHub(goal_node(body="Outcome only.\n")), "no 'Spec source")

    def test_two_link_lines(self):
        body = f"Spec source: fake://{INIT}\nSpec source: fake://other\n"
        self.refused(StubGitHub(goal_node(body=body)), "2 Spec source: lines")

    def test_malformed_link(self):
        self.refused(StubGitHub(goal_node(body="Spec source: the recipe box\n")), "isn't <backend>")

    def test_scheme_must_match_backend(self):
        body = f"Spec source: notion://{INIT}\n"
        self.refused(StubGitHub(goal_node(body=body)), "notion:// source, but .* 'fake'")
        self.refused(StubGitHub(), "fake:// source, but .* 'notion'", backend="notion")

    def test_unknown_initiative(self):
        self.refused(StubGitHub(goal_node(body="Spec source: fake://nope\n")), "no initiative 'nope'")

    def test_bad_repo_line(self):
        body = f"Spec source: fake://{INIT}\nRepo: not a repo\n"
        self.refused(StubGitHub(goal_node(body=body)), "isn't owner/name")
        body = f"Spec source: fake://{INIT}\nRepo: elsewhere/thing\n"
        self.refused(StubGitHub(goal_node(body=body)), "outside acme")

    def test_schema_error_stops_before_any_write(self):
        gh = StubGitHub()

        def broken(fid):
            raise SchemaError("unknown spec heading(s): Goals")
        self.source.get_spec = broken
        with self.assertRaises(SchemaError):
            self.pull(gh)
        self.assert_nothing_written(gh)

    def test_schema_error_on_a_later_feature_still_writes_nothing(self):
        # FEAT-1 is pullable, but a feature after it breaks the layout: no issue for FEAT-1.
        data = json.loads(FIXTURE.read_text())
        extra = json.loads(json.dumps(data["features"][0]))
        extra["properties"]["ID"] = "FEAT-6"
        data["features"].append(extra)
        self.fixture.write_text(json.dumps(data))
        source = FakeSource(self.fixture)
        orig = source.get_spec

        def get_spec(fid):
            if fid == "FEAT-6":
                raise SchemaError("Acceptance criteria isn't a checklist")
            return orig(fid)
        source.get_spec = get_spec
        gh = StubGitHub()
        with self.assertRaises(SchemaError):
            self.pull(gh, source=source)
        self.assert_nothing_written(gh, source)


if __name__ == "__main__":
    unittest.main()
