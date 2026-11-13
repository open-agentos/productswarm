"""Tests for `swarm classify eval` (#1010): the replay report against the checked-in one, with
no network and no model credential, and the live run's caps and refusals."""
import io
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import classifier
import evalrun

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "testdata"
EXPECTED = FIXTURE / "expected" / "fixture-dev-claude-haiku-5-5.md"


def no_model(*a, **k):
    raise AssertionError("a model call was made")


def committed(paths):
    return []


class EvalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.said = []
        self.manifest = self.tmp / "swarm.toml"
        self.manifest.write_text("[classify]\nmodel = \"claude-haiku-5-5\"\neval_budget_usd = 5\n")

    def eval(self, *argv, runner=no_model, uncommitted=committed, dir=FIXTURE):
        ap = evalrun.argparse.ArgumentParser()
        evalrun.add_eval_args(ap)
        args = ap.parse_args(["fixture", "--dir", str(dir), "--manifest", str(self.manifest),
                              "--out", str(self.tmp / "report.md"), *argv])
        return evalrun.eval_main(args, say=self.said.append, runner=runner, uncommitted=uncommitted)

    def copy_fixture(self):
        d = self.tmp / "classify"
        shutil.copytree(FIXTURE, d)
        shutil.rmtree(d / "recordings")
        return d

    def test_replay_report_matches_the_checked_in_one_with_no_network_or_credential(self):
        env = {k: v for k, v in os.environ.items() if "ANTHROPIC" not in k and "CLAUDE" not in k}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(classifier.subprocess, "run", side_effect=AssertionError("ran a command")):
            self.assertEqual(self.eval("--replay"), 0)
        self.assertEqual((self.tmp / "report.md").read_text(), EXPECTED.read_text())
        self.assertIn("wrote", self.said[-1])

    def test_replay_is_the_default(self):
        self.assertEqual(self.eval(), 0)
        self.assertEqual((self.tmp / "report.md").read_text(), EXPECTED.read_text())

    def test_the_report_carries_both_hashes_and_no_cost(self):
        self.eval()
        text = (self.tmp / "report.md").read_text()
        from labelset import sha256
        self.assertIn(sha256(FIXTURE / "labelsets" / "fixture.yml"), text)
        self.assertIn(sha256(FIXTURE / "data" / "fixture.jsonl"), text)
        self.assertNotIn("$", text)
        self.assertNotIn("cost", text.lower())

    def test_replay_without_recordings_fails_clearly_and_writes_nothing(self):
        self.assertEqual(self.eval("--split", "test"), 2)
        self.assertIn("no recording of sample 1 for item 't1'", self.said[-1])
        self.assertFalse((self.tmp / "report.md").exists())

    def test_baseline_majority(self):
        self.assertEqual(self.eval("--baseline", "majority"), 1)   # 3 of 8: fails the pass mark
        text = (self.tmp / "report.md").read_text()
        self.assertIn("baseline `majority`", text)
        self.assertIn("| Accuracy | 37.5% (3 of 8) |", text)
        self.assertIn("**Result: FAIL**", text)

    def test_unknown_baseline_and_baseline_with_live_are_refused(self):
        self.assertEqual(self.eval("--baseline", "nope"), 2)
        self.assertIn("unknown baseline 'nope' (known: majority)", self.said[-1])
        self.assertEqual(self.eval("--baseline", "majority", "--live"), 2)

    def test_live_run_stops_at_max_calls_with_a_clear_message(self):
        d = self.copy_fixture()
        ls = d / "labelsets" / "fixture.yml"
        ls.write_text(ls.read_text().replace("max_calls: 30", "max_calls: 7"))
        calls = []

        def runner(model, system, user, budget):
            calls.append(model)
            return '{"label": "bug", "flags": {}, "evidence": "x"}', 0.001
        self.assertEqual(self.eval("--live", runner=runner, dir=d), 2)
        self.assertEqual(len(calls), 7)
        self.assertIn("stopped at the label set's max_calls (7) after 7 model calls: "
                      "2 of 8 items classified, replies recorded, no report written", self.said[-1])
        self.assertFalse((self.tmp / "report.md").exists())
        recorded = (d / "recordings" / "fixture" / "claude-haiku-5-5.jsonl").read_text().splitlines()
        self.assertEqual(len(recorded), 7)

    def test_live_run_records_then_replays_the_same_report(self):
        d = self.copy_fixture()

        def runner(model, system, user, budget):
            return '{"label": "docs", "flags": {"urgent": false}, "evidence": "x"}', 0.001
        self.assertEqual(self.eval("--live", runner=runner, dir=d), 1)
        live = (self.tmp / "report.md").read_text()
        self.assertIn("live (replies recorded)", live)
        self.assertEqual(self.eval("--replay", dir=d), 1)
        self.assertEqual((self.tmp / "report.md").read_text(),
                         live.replace("live (replies recorded)", "replay (recordings only)"))

    def test_live_run_refuses_uncommitted_pass_mark_or_data(self):
        self.assertEqual(self.eval("--live", uncommitted=lambda paths: [str(paths[0])]), 2)
        self.assertIn("commit the pass mark and labelled set before a live run (GOV-0044)", self.said[-1])

    def test_live_run_refuses_without_a_budget(self):
        self.manifest.write_text("[classify]\nmodel = \"m\"\n")
        self.assertEqual(self.eval("--live"), 2)
        self.assertIn("no [classify] eval_budget_usd", self.said[-1])

    def test_bad_classify_table_is_refused(self):
        self.manifest.write_text("[classify]\nbudget = 5\n")
        self.assertEqual(self.eval(), 2)
        self.assertIn("unknown key 'budget'", self.said[-1])

    def test_runs_below_one_is_refused(self):
        self.assertEqual(self.eval("--runs", "0"), 2)
        self.assertIn("--runs must be at least 1", self.said[-1])

    def test_model_flag_picks_the_recordings(self):
        self.assertEqual(self.eval("--model", "claude-sonnet-5-5"), 2)
        self.assertIn("claude-sonnet-5-5.jsonl", self.said[-1])

    def test_default_report_path(self):
        out = io.StringIO()
        d = self.copy_fixture()
        shutil.copytree(FIXTURE / "recordings", d / "recordings")
        ok = evalrun.run("fixture", d, manifest=self.manifest, runner=no_model, say=out.write)
        self.assertTrue(ok)
        self.assertTrue((d / "reports" / "fixture-dev-claude-haiku-5-5.md").is_file())

    def test_uncommitted_checks_git(self):
        d = self.tmp / "repo"
        d.mkdir()
        run = lambda *a: evalrun.subprocess.run(["git", *a], cwd=d, capture_output=True, check=True)
        run("init", "-q")
        f = d / "x.yml"
        f.write_text("a: 1\n")
        self.assertEqual(evalrun.uncommitted([f]), [str(f)])
        run("add", "x.yml")
        run("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x")
        self.assertEqual(evalrun.uncommitted([f]), [])
        f.write_text("a: 2\n")
        self.assertEqual(evalrun.uncommitted([f]), [str(f)])


if __name__ == "__main__":
    unittest.main()
