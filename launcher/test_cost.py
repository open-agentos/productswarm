"""Tests for `swarm cost` (#176): recorded run costs from swarm.db, grouped by PR.
Canned state and PR data only; nothing reads or writes GitHub.

Run: python3 -m unittest discover -s launcher
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import swarm  # noqa: E402
import watch  # noqa: E402

REPO = "open-agentos/productswarm"


def run(kind, ref, cost, started="2026-11-01T10:00:00+00:00", ended="2026-11-01T11:00:00+00:00"):
    r = {"session_id": f"sid-{kind}-{ref}", "name": f"{kind}-x", "kind": kind, "ref": ref,
         "started": started}
    if ended:
        r.update({"ended": ended, "ending": "done", "detail": "", "cost_usd": cost, "subtype": "success"})
    return r


def pr(n, state, closes=(), merged_at=None):
    return {"number": n, "state": state, "mergedAt": merged_at,
            "closingIssuesReferences": [{"number": c} for c in closes]}


PRS = [pr(70, "MERGED", [49], "2026-11-02T09:00:00Z"),
       pr(68, "CLOSED", [49]),                                 # an abandoned earlier attempt
       pr(72, "OPEN", [51]),
       pr(80, "MERGED", [60], "2026-11-02T12:00:00Z"),          # no loop run: owner-started
       pr(40, "MERGED", [30], "2026-10-20T12:00:00Z")]          # merged before the runs


class CostTextTest(unittest.TestCase):
    def setUp(self):
        self.runs = {
            "build:49:1": run("build", "#49", 4.5),
            "review:70:a": run("review", "PR #70", 0.75, started="2026-11-02T08:00:00+00:00",
                               ended="2026-11-02T08:20:00+00:00"),
            "respond:70:b": run("respond", "PR #70", 1.25),
            "review:72:a": run("review", "PR #72", None),       # a run with no cost recorded
            "build:51:1": run("build", "#51", None, started="2026-11-03T09:00:00+00:00",
                              ended=None),                # still running: no cost yet
            "build:90:1": run("build", "#90", 3.0),             # no PR closes #90 yet
        }

    def text(self, runs=None, prs=PRS):
        return watch.cost_text(list((self.runs if runs is None else runs).values()), prs)

    def row(self, text, label):
        (line,) = [x for x in text.splitlines() if x.startswith(label + " ")]
        return line.split()

    def test_build_review_and_respond_runs_group_by_the_pr_they_served(self):
        t = self.text()
        self.assertEqual(self.row(t, "PR #70"), ["PR", "#70", "merged", "3", "$6.50", "0"])
        self.assertEqual(self.row(t, "PR #72"), ["PR", "#72", "open", "2", "-", "2"])
        self.assertNotIn("PR #68", t)    # the merged PR wins over a closed one on the same issue

    def test_a_run_with_no_cost_counts_as_a_run_but_adds_nothing(self):
        t = self.text({"review:72:a": run("review", "PR #72", None)})
        self.assertEqual(self.row(t, "PR #72"), ["PR", "#72", "open", "1", "-", "1"])
        self.assertIn("1 run with no cost recorded", t)

    def test_an_issue_with_no_closing_pr_is_its_own_row(self):
        self.assertEqual(self.row(self.text(), "#90"), ["#90", "(no", "PR)", "-", "1", "$3.00", "0"])

    def test_total_date_range_and_merged_prs_with_no_record(self):
        t = self.text()
        self.assertIn("total: $9.50 over 6 runs, runs started 2026-11-01 to 2026-11-03", t)
        self.assertIn("2 runs with no cost recorded", t)
        self.assertIn("1 PR merged since 2026-11-01 has no run recorded: #80", t)

    def test_limits_are_stated(self):
        t = self.text()
        self.assertIn("sessions you start by hand have none", t)
        self.assertIn(f"keeps runs for {watch.RUNS_DAYS} days", t)

    def test_no_runs(self):
        t = self.text({}, [])
        self.assertTrue(t.startswith("no runs recorded in swarm.db"))
        self.assertIn("sessions you start by hand have none", t)

    def test_prs_come_first_then_issues_with_no_pr(self):
        labels = [x.split()[0] + " " + x.split()[1] for x in self.text().splitlines()[1:4]]
        self.assertEqual(labels, ["PR #70", "PR #72", "#90 (no"])

    def test_a_pr_missing_from_the_list_shows_an_unknown_state(self):
        self.assertEqual(self.row(self.text(prs=[]), "PR #70"), ["PR", "#70", "?", "2", "$2.00", "0"])


class CostCommandTest(unittest.TestCase):
    def setUp(self):
        self.lines = []
        self.l = swarm.Launcher(Path(tempfile.mkdtemp()), out=self.lines.append,
                                run=lambda c: self.fail("started"))

    def write(self, runs):
        self.l.dir.mkdir(parents=True, exist_ok=True)
        watch.save_state(self.l, {"checked": None, "acted": {}, "waiting": [], "runs": runs})

    def test_empty_file_prints_no_runs_and_reads_nothing_from_github(self):
        self.write({})
        self.assertEqual(swarm.cost(self.l, REPO, get_prs=lambda r: self.fail("read GitHub")), 0)
        self.assertIn("no runs recorded", self.lines[0])

    def test_missing_file_prints_no_runs(self):
        self.assertEqual(swarm.cost(self.l, REPO, get_prs=lambda r: self.fail("read GitHub")), 0)
        self.assertIn("no runs recorded", self.lines[0])

    def test_prints_and_writes_nothing(self):
        self.write({"review:70:a": run("review", "PR #70", 0.75)})
        before = watch.state_path(self.l).read_bytes()
        files = sorted(self.l.dir.iterdir())
        self.assertEqual(swarm.cost(self.l, REPO, get_prs=lambda r: PRS), 0)
        self.assertIn("PR #70", self.lines[0])
        self.assertEqual(watch.state_path(self.l).read_bytes(), before)
        self.assertEqual(sorted(self.l.dir.iterdir()), files)

    def test_cli_dispatches_cost(self):
        self.write({})
        self.assertEqual(swarm.main(["cost", "--repo", REPO], self.l), 0)
        self.assertIn("no runs recorded", self.lines[0])


if __name__ == "__main__":
    unittest.main()
