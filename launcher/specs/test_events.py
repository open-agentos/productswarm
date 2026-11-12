"""Tests for launcher/specs/events.py (#954): the bridge's append-only event log.

Run: python3 run_tests.py launcher
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from specs import events  # noqa: E402


class EventsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"PRODUCTSWARM_HOME": self.tmp.name})
        env.start()
        self.addCleanup(env.stop)

    def test_path_is_under_home(self):
        self.assertEqual(events.path(), Path(self.tmp.name) / "specs" / "events.jsonl")

    def test_default_home(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop("PRODUCTSWARM_HOME", None)
            self.assertEqual(events.path(),
                             Path("~/.productswarm").expanduser() / "specs" / "events.jsonl")

    def test_read_without_a_log_is_empty(self):
        got = events.read()
        self.assertEqual(list(got), [])
        self.assertEqual(got.skipped, 0)

    def test_round_trip_each_kind_in_order(self):
        events.append("pull", 938, "FEAT-1", hash="abc123",
                      issue_url="https://github.com/o/r/issues/1")
        events.append("write", 938, "FEAT-1", what="status", value="In progress")
        events.append("write", 938, "FEAT-1", what="links",
                      issue_url="https://github.com/o/r/issues/1", pr_url=None)
        events.append("write", 938, "FEAT-1", what="comment", marker="swarm:pr=7",
                      body="PR opened")
        events.append("decision", 938, "FEAT-1", choice="adopt", where="#7")
        events.append("decision", 938, "FEAT-1", choice="defer", where="#8")
        events.append("decision", 938, "FEAT-1", choice="ask", where="report issue")
        got = events.read()
        self.assertEqual(got.skipped, 0)
        self.assertEqual([e["kind"] for e in got],
                         ["pull", "write", "write", "write", "decision", "decision", "decision"])
        self.assertEqual(got[0]["hash"], "abc123")
        self.assertEqual(got[0]["issue_url"], "https://github.com/o/r/issues/1")
        self.assertEqual([e.get("what") for e in got[1:4]], ["status", "links", "comment"])
        self.assertEqual(got[1]["value"], "In progress")
        self.assertIsNone(got[2]["pr_url"])
        self.assertEqual([e.get("choice") for e in got[4:]], ["adopt", "defer", "ask"])
        self.assertEqual(got[4]["where"], "#7")
        for e in got:
            self.assertEqual((e["goal"], e["feature"]), (938, "FEAT-1"))
            self.assertTrue(e["ts"].endswith("+00:00"), e["ts"])

    def test_read_filters_by_goal(self):
        events.append("pull", 938, "FEAT-1", hash="a", issue_url="u1")
        events.append("pull", 999, "FEAT-2", hash="b", issue_url="u2")
        events.append("decision", 938, "FEAT-1", choice="ask", where="#9")
        self.assertEqual([e["feature"] for e in events.read(goal=938)], ["FEAT-1", "FEAT-1"])
        self.assertEqual([e["feature"] for e in events.read(goal="999")], ["FEAT-2"])
        self.assertEqual(len(events.read()), 3)

    def test_unknown_kind_raises_and_writes_nothing(self):
        with self.assertRaises(ValueError):
            events.append("merge", 938, "FEAT-1")
        with self.assertRaises(ValueError):
            events.append("write", 938, "FEAT-1", what="body")
        with self.assertRaises(ValueError):
            events.append("decision", 938, "FEAT-1", choice="ignore")
        with self.assertRaises(ValueError):
            events.append("pull", 938, "FEAT-1", hash="a", issue_url="u", ts="x")
        self.assertFalse(events.path().exists())

    def test_corrupt_line_is_skipped_and_counted(self):
        events.append("pull", 938, "FEAT-1", hash="a", issue_url="u1")
        with events.path().open("a", encoding="utf-8") as f:
            f.write('{"kind": "pull", "goal": 938, trunc\n')
            f.write("[1, 2]\n")
            f.write('{"kind": "nope"}\n')
            f.write("\n")
        events.append("decision", 938, "FEAT-1", choice="adopt", where="#7")
        got = events.read()
        self.assertEqual([e["kind"] for e in got], ["pull", "decision"])
        self.assertEqual(got.skipped, 3)
        self.assertEqual(events.read(goal=938).skipped, 3)

    def test_append_only_appends(self):
        events.append("pull", 938, "FEAT-1", hash="a", issue_url="u1")
        before = events.path().read_bytes()
        events.append("pull", 938, "FEAT-2", hash="b", issue_url="u2")
        self.assertTrue(events.path().read_bytes().startswith(before))


if __name__ == "__main__":
    unittest.main()
