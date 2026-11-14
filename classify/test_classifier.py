"""Tests for the baselines, the model classifier's vote, recordings and caps (#1010)."""
import json
import tempfile
import unittest
from pathlib import Path

import classifier as c
import labelset as l

HERE = Path(__file__).resolve().parent
LS = l.load_labelset(HERE / "testdata" / "labelsets" / "fixture.yml")


def reply(label, evidence="line", urgent=False):
    return json.dumps({"label": label, "flags": {"urgent": urgent}, "evidence": evidence})


def item(i="x1", label="bug", split="dev"):
    return l.Item(i, "Some text.", label, split, "owner")


class VoteTest(unittest.TestCase):
    def test_majority_label_confidence_and_evidence(self):
        p = c.vote(LS, [reply("bug", "a", True), reply("docs", "b"), reply("bug", "c", True)])
        self.assertEqual((p.label, p.confidence, p.evidence, p.flags), ("bug", 0.6667, "a", {"urgent": True}))

    def test_below_threshold_is_needs_human(self):
        ls = l.LabelSet(**{**LS.__dict__, "threshold": 0.7})
        self.assertIsNone(c.vote(ls, [reply("bug"), reply("bug"), reply("docs")]).label)

    def test_a_tie_is_needs_human(self):
        p = c.vote(LS, [reply("bug"), reply("docs"), reply("feature")])
        self.assertEqual((p.label, p.confidence), (None, 0.3333))

    def test_a_reply_with_no_known_label_is_no_vote(self):
        self.assertIsNone(c.parse_reply(LS, "it's a bug"))
        self.assertIsNone(c.parse_reply(LS, reply("chore")))
        p = c.vote(LS, ["nonsense", reply("bug"), "{bad json"])
        self.assertEqual((p.label, p.confidence), (None, 0.3333))   # 1 of 3 is below 0.6
        self.assertEqual(c.vote(LS, ["x", "y", "z"]).label, None)

    def test_a_fenced_reply_parses(self):
        self.assertEqual(c.parse_reply(LS, "```json\n" + reply("docs") + "\n```")["label"], "docs")


class BaselineTest(unittest.TestCase):
    def test_majority_is_registered_and_picks_the_commonest_dev_label(self):
        dev = [item("1", "docs"), item("2", "docs"), item("3", "bug")]
        self.assertIs(c.BASELINES["majority"], c.majority)
        self.assertEqual(c.majority(LS, dev, item()).label, "docs")

    def test_majority_breaks_ties_by_label_order(self):
        dev = [item("1", "docs"), item("2", "feature")]
        self.assertEqual(c.majority(LS, dev, item()).label, "feature")

    def test_a_new_baseline_is_a_plain_function(self):
        @c.baseline("always-docs")
        def always_docs(labelset, dev, it):
            return c.Prediction("docs")
        try:
            self.assertEqual(c.BASELINES["always-docs"](LS, [], item()).label, "docs")
        finally:
            del c.BASELINES["always-docs"]


class ModelClassifierTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.rec = c.Recordings(Path(self.tmp.name), "fixture", "m")
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def runner(self, model, system, user, budget):
        self.calls.append((model, budget))
        return reply("bug", "Some text."), 0.01

    def test_live_samples_n_times_and_records_only_replies(self):
        clf = c.ModelClassifier(LS, "m", self.rec, 3, live=True, cap=c.Cap(10, 1.0), runner=self.runner)
        p = clf(item())
        self.assertEqual((p.label, p.confidence), ("bug", 1.0))
        self.assertEqual(len(self.calls), 3)
        lines = [json.loads(x) for x in self.rec.path.read_text().splitlines()]
        self.assertEqual([d["sample"] for d in lines], [0, 1, 2])
        self.assertEqual(set(lines[0]), {"item", "sample", "prompt", "reply"})
        self.assertNotIn("Labels:", self.rec.path.read_text())   # no prompt text (GOV-0044)

    def test_replay_uses_only_recordings_and_makes_no_calls(self):
        c.ModelClassifier(LS, "m", self.rec, 3, live=True, cap=c.Cap(10, 1.0), runner=self.runner)(item())
        self.calls.clear()

        def no_calls(*a):
            raise AssertionError("replay made a model call")
        fresh = c.Recordings(Path(self.tmp.name), "fixture", "m")
        p = c.ModelClassifier(LS, "m", fresh, 3, runner=no_calls)(item())
        self.assertEqual(p.label, "bug")

    def test_replay_of_an_unrecorded_item_or_changed_text_says_so(self):
        c.ModelClassifier(LS, "m", self.rec, 3, live=True, cap=c.Cap(10, 1.0), runner=self.runner)(item())
        changed = l.Item("x1", "Other text.", "bug", "dev", "owner")
        with self.assertRaisesRegex(c.ReplayMissing, "--live run records it"):
            c.ModelClassifier(LS, "m", self.rec, 3)(changed)

    def test_calls_stop_at_max_calls(self):
        clf = c.ModelClassifier(LS, "m", self.rec, 3, live=True, cap=c.Cap(4, 1.0), runner=self.runner)
        clf(item("a"))
        with self.assertRaisesRegex(c.CapReached, r"max_calls \(4\) after 4 model calls"):
            clf(item("b"))
        self.assertEqual(len(self.calls), 4)

    def test_each_call_gets_what_is_left_of_the_budget_and_calls_stop_when_it_is_spent(self):
        clf = c.ModelClassifier(LS, "m", self.rec, 3, live=True, cap=c.Cap(100, 0.025), runner=self.runner)
        clf(item("a"))
        with self.assertRaisesRegex(c.CapReached, "budget"):
            clf(item("b"))
        self.assertEqual([b for _, b in self.calls], [0.025, 0.015, 0.005])

    def test_the_claude_command_has_no_tools_and_a_budget(self):
        cmd = c.claude_command("claude-haiku-5-5", "sys", 0.5)
        self.assertEqual(cmd[:2], ["claude", "-p"])
        self.assertEqual(cmd[cmd.index("--tools") + 1], "")
        self.assertEqual(cmd[cmd.index("--max-budget-usd") + 1], "0.5000")
        self.assertEqual(cmd[cmd.index("--model") + 1], "claude-haiku-5-5")


if __name__ == "__main__":
    unittest.main()
