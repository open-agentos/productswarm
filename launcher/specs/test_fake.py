"""Tests for launcher/specs/fake.py (#941): the fake backend over JSON fixtures.

Run: python3 run_tests.py launcher
"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from specs.fake import FakeSource  # noqa: E402
from specs.source import FeatureStatus, SchemaError, SpecSource  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "testdata" / "fake_initiative.json"
INIT = "init-0001-recipe-box"


class FixtureCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.src = FakeSource(FIXTURE)

    def write(self, data, name="f.json") -> Path:
        p = Path(self.tmp.name) / name
        p.write_text(json.dumps(data), encoding="utf-8")
        return p


class ProtocolTest(FixtureCase):
    def test_satisfies_spec_source(self):
        self.assertIsInstance(self.src, SpecSource)
        self.assertEqual(self.src.name, "fake")
        self.assertTrue(self.src.simulated)


class FixtureCasesTest(FixtureCase):
    def feature(self, fid):
        return {f.id: f for f in self.src.list_features(INIT)}[fid]

    def test_lists_every_feature_in_order(self):
        self.assertEqual([f.id for f in self.src.list_features(INIT)],
                         ["FEAT-1", "FEAT-2", "FEAT-3", "FEAT-4", "FEAT-5"])

    def test_unknown_initiative(self):
        with self.assertRaises(KeyError):
            self.src.list_features("init-nope")

    def test_ready_with_criteria_is_pullable(self):
        f = self.feature("FEAT-1")
        self.assertEqual(f.status, FeatureStatus.READY)
        self.assertIsNone(f.issue_url)
        self.assertEqual(f.last_edited, "2026-11-01T09:00:00Z")
        spec = self.src.get_spec("FEAT-1")
        self.assertEqual(spec.pullable(), (True, None))
        self.assertEqual(len(spec.acceptance_criteria), 2)

    def test_ready_without_criteria_is_not_pullable(self):
        self.assertEqual(self.feature("FEAT-2").status, FeatureStatus.READY)
        spec = self.src.get_spec("FEAT-2")
        self.assertIsNone(spec.acceptance_criteria)
        self.assertFalse(spec.pullable()[0])

    def test_draft(self):
        self.assertEqual(self.feature("FEAT-3").status, FeatureStatus.DRAFT)

    def test_ready_with_issue_linked(self):
        f = self.feature("FEAT-4")
        self.assertEqual(f.status, FeatureStatus.READY)
        self.assertEqual(f.issue_url, "https://github.com/example/recipe-box/issues/7")
        self.assertIsNone(f.pr_url)
        self.assertEqual(f.last_synced, "2026-10-29T09:00:00Z")

    def test_in_review_with_pr(self):
        f = self.feature("FEAT-5")
        self.assertEqual(f.status, FeatureStatus.IN_REVIEW)
        self.assertEqual(f.pr_url, "https://github.com/example/recipe-box/pull/9")
        self.assertEqual(self.src.comments("FEAT-5"),
                         [{"body": "Index cards in our drawer are 5x8, not 4x6.",
                           "marker": None}])

    def test_unknown_feature(self):
        with self.assertRaises(KeyError):
            self.src.get_spec("FEAT-99")


class WritesTest(FixtureCase):
    def test_set_status_refuses_draft_and_ready(self):
        for s in (FeatureStatus.DRAFT, FeatureStatus.READY, "Draft", "Ready", "Done"):
            with self.assertRaises(ValueError):
                self.src.set_status("FEAT-1", s)
        self.assertEqual(self.src.writes, [])
        self.assertEqual(self.src.list_features(INIT)[0].status, FeatureStatus.READY)

    def test_set_status_writes_and_logs(self):
        self.src.set_status("FEAT-1", "In progress")
        self.src.set_status("FEAT-4", FeatureStatus.BLOCKED, reason="issue closed unmerged")
        by_id = {f.id: f for f in self.src.list_features(INIT)}
        self.assertEqual(by_id["FEAT-1"].status, FeatureStatus.IN_PROGRESS)
        self.assertEqual(by_id["FEAT-4"].status, FeatureStatus.BLOCKED)
        self.assertEqual(self.src.writes, [
            ("set_status", "FEAT-1", {"status": "In progress", "reason": None}),
            ("set_status", "FEAT-4", {"status": "Blocked", "reason": "issue closed unmerged"}),
        ])

    def test_set_links_none_leaves_a_link(self):
        self.src.set_links("FEAT-5", issue_url="https://github.com/example/recipe-box/issues/6")
        f = self.src.list_features(INIT)[4]
        self.assertEqual(f.issue_url, "https://github.com/example/recipe-box/issues/6")
        self.assertEqual(f.pr_url, "https://github.com/example/recipe-box/pull/9")
        self.assertEqual(self.src.writes, [("set_links", "FEAT-5", {
            "issue_url": "https://github.com/example/recipe-box/issues/6", "pr_url": None})])

    def test_repeated_comment_with_same_marker_writes_once(self):
        self.assertTrue(self.src.comment("FEAT-5", "Shipped in #9.", "swarm:pr=9"))
        self.assertFalse(self.src.comment("FEAT-5", "Shipped again.", "swarm:pr=9"))
        self.assertTrue(self.src.comment("FEAT-5", "Follow-up shipped.", "swarm:pr=10"))
        self.assertEqual([w for w in self.src.writes if w[0] == "comment"], [
            ("comment", "FEAT-5", {"body": "Shipped in #9.", "marker": "swarm:pr=9"}),
            ("comment", "FEAT-5", {"body": "Follow-up shipped.", "marker": "swarm:pr=10"}),
        ])
        self.assertEqual(len(self.src.comments("FEAT-5")), 3)

    def test_writes_to_unknown_feature_raise(self):
        for call in (lambda: self.src.set_status("FEAT-99", "Shipped"),
                     lambda: self.src.set_links("FEAT-99", pr_url="x"),
                     lambda: self.src.comment("FEAT-99", "x", "swarm:pr=1")):
            with self.assertRaises(KeyError):
                call()
        self.assertEqual(self.src.writes, [])


class EditSpecTest(FixtureCase):
    def test_edit_changes_hash_and_last_edited(self):
        before = self.src.get_spec("FEAT-1")
        edited_before = self.src.list_features(INIT)[0].last_edited
        after = self.src.edit_spec("FEAT-1", scope="Paste a URL or a photo of a card.")
        self.assertEqual(self.src.get_spec("FEAT-1"), after)
        self.assertNotEqual(after.content_hash(), before.content_hash())
        self.assertEqual(after.problem, before.problem)                 # the rest stays
        self.assertEqual(after.acceptance_criteria, before.acceptance_criteria)
        edited_after = self.src.list_features(INIT)[0].last_edited
        self.assertGreater(edited_after, edited_before)                 # ISO 8601 Z sorts
        self.assertEqual(self.src.writes, [])                           # owner's edit, not ours

    def test_edit_moves_forward_past_a_future_timestamp(self):
        data = json.loads(FIXTURE.read_text())
        data["features"][0]["last_edited_time"] = "2999-01-01T00:00:00Z"
        src = FakeSource(self.write(data))
        src.edit_spec("FEAT-1", notes="later")
        self.assertEqual(src.list_features(INIT)[0].last_edited, "2999-01-01T00:00:01Z")

    def test_edit_can_add_criteria(self):
        spec = self.src.edit_spec("FEAT-2", acceptance_criteria=[("Six servings doubles 3/4", False)])
        self.assertEqual(spec.pullable(), (True, None))

    def test_unknown_field(self):
        with self.assertRaises(TypeError):
            self.src.edit_spec("FEAT-1", requirements="x")


class DumpTest(FixtureCase):
    def snapshot(self, src):
        return [(f, src.get_spec(f.id), src.comments(f.id)) for f in src.list_features(INIT)]

    def test_untouched_dump_reproduces_fixture(self):
        out = Path(self.tmp.name) / "out.json"
        self.src.dump(out)
        self.assertEqual(json.loads(out.read_text()), json.loads(FIXTURE.read_text()))

    def test_round_trip_after_writes_and_edits(self):
        self.src.set_status("FEAT-1", "In progress")
        self.src.set_links("FEAT-1", issue_url="https://github.com/example/recipe-box/issues/11")
        self.src.comment("FEAT-5", "Shipped in #9.", "swarm:pr=9")
        self.src.edit_spec("FEAT-4", out_of_scope="")
        out = Path(self.tmp.name) / "out.json"
        self.src.dump(out)
        again = FakeSource(out)
        self.assertEqual(self.snapshot(again), self.snapshot(self.src))
        self.assertEqual(again.initiatives, self.src.initiatives)
        self.assertEqual(again.writes, [])
        self.assertFalse(again.comment("FEAT-5", "dup", "swarm:pr=9"))  # marker survives


class SchemaErrorTest(FixtureCase):
    def broken(self, mutate):
        data = copy.deepcopy(json.loads(FIXTURE.read_text()))
        mutate(data)
        with self.assertRaises(SchemaError):
            FakeSource(self.write(data))

    def test_missing_property(self):
        self.broken(lambda d: d["features"][2]["properties"].pop("Status"))
        self.broken(lambda d: d["features"][0]["properties"].pop("PR"))
        self.broken(lambda d: d["initiatives"][0]["properties"].pop("Goal"))

    def test_unknown_status(self):
        self.broken(lambda d: d["features"][1]["properties"].update(Status="Done"))
        self.broken(lambda d: d["initiatives"][0]["properties"].update(Status="Paused"))

    def test_other_layout_breaks(self):
        self.broken(lambda d: d["features"][0]["properties"].update(Stauts="Ready"))
        self.broken(lambda d: d["features"][0]["properties"].update(ID="F-1"))
        self.broken(lambda d: d["features"][0]["properties"].update(Name=""))
        self.broken(lambda d: d["features"][0]["properties"].update(Initiative="init-nope"))
        self.broken(lambda d: d["features"][1]["properties"].update(ID="FEAT-1"))
        self.broken(lambda d: d["features"][0]["spec"].update(Requirements="x"))
        self.broken(lambda d: d["features"][0]["spec"].update(
            {"Acceptance criteria": ["not a checklist item"]}))
        self.broken(lambda d: d["features"][0]["spec"].update({"Acceptance criteria": 5}))
        self.broken(lambda d: d["features"][0]["spec"].update({"Acceptance criteria": "abc"}))
        self.broken(lambda d: d["features"][0]["spec"].update(
            {"Acceptance criteria": [{"text": None, "checked": False}]}))
        self.broken(lambda d: d["features"][0]["spec"].update(
            {"Acceptance criteria": [{"text": "x", "checked": "yes"}]}))
        self.broken(lambda d: d["features"][0]["spec"].update(
            {"Acceptance criteria": [{"text": "x"}]}))
        self.broken(lambda d: d["features"][0]["spec"].update(Problem={"x": 1}))
        self.broken(lambda d: d["features"][0]["spec"].update(Notes=3))
        self.broken(lambda d: d["features"][0].update(last_edited_time="yesterday"))
        self.broken(lambda d: d["features"][0].update(last_edited_time=5))
        self.broken(lambda d: d["features"][0].update(last_edited_time=[]))
        self.broken(lambda d: d["features"][0].pop("comments"))
        self.broken(lambda d: d.pop("initiatives"))

    def test_unknown_heading_reported_before_its_value(self):
        data = json.loads(FIXTURE.read_text())
        data["features"][0]["spec"]["Requirements"] = {}
        with self.assertRaises(SchemaError) as cm:
            FakeSource(self.write(data))
        self.assertIn("unknown spec heading", str(cm.exception))
        self.assertIn("Requirements", str(cm.exception))

    def test_not_json(self):
        p = Path(self.tmp.name) / "bad.json"
        p.write_text("{not json", encoding="utf-8")
        with self.assertRaises(SchemaError):
            FakeSource(p)

    def test_break_late_in_the_file_loads_nothing(self):
        # The last feature is broken; the error comes before any state exists to use.
        data = json.loads(FIXTURE.read_text())
        data["features"][-1]["properties"]["Status"] = "Done"
        with self.assertRaises(SchemaError) as cm:
            FakeSource(self.write(data))
        self.assertIn("features[4]", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
