"""Tests for launcher/ledger.py (#662): the runs ledger in swarm.db, its scopes, the daily,
monthly and per-scope totals, and `swarm spent`. Temporary directories only; never GitHub.

Per GOV-0033 the engine has no spend total that holds runs, so there are no hold tests: these
check that the totals are counted and reported."""
import datetime as dt
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger  # noqa: E402
import statedb  # noqa: E402
import swarm  # noqa: E402
import watch  # noqa: E402

REPO = "open-agentos/productswarm"
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 10, 15, 0, tzinfo=UTC)


def run(sid, ref, ended, cost, kind="build", ending="done"):
    return {"session_id": sid, "name": f"x-{sid}", "kind": kind, "ref": ref,
            "started": ended, "ended": ended, "ending": ending, "cost_usd": cost}


def parent(n, type_, repo=REPO):
    return {"repo": repo, "number": n, "state": "open", "type": type_, "author": "mattmcalister"}


def scope(*parents):
    return {"author": "productswarm-planner[bot]", "type": "Task", "parents": list(parents),
            "deep": False, "blocked_by": [], "blockers_complete": True}


class LedgerTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)

    def test_no_database_reads_as_empty_and_creates_nothing(self):
        self.assertEqual(ledger.rows(self.dir), [])
        self.assertEqual(ledger.unscoped(self.dir), [])
        self.assertFalse((self.dir / statedb.DB_FILE).exists())

    def test_records_each_run_once_with_its_issue(self):
        runs = [run("a", "#10", "2026-11-10T09:00:00+00:00", 1.5),
                run("b", "PR #20", "2026-11-10T10:00:00+00:00", 0.5, kind="review"),
                run("c", "PR #21", "2026-11-10T10:30:00+00:00", 0.25, kind="review")]
        self.assertEqual(ledger.record(self.dir, runs, {20: 11}), 3)
        self.assertEqual(ledger.record(self.dir, runs, {20: 11}), 0)   # again: no change
        got = {r["session_id"]: (r["issue"], r["pr"], r["cost_usd"], r["scopes"]) for r in ledger.rows(self.dir)}
        self.assertEqual(got, {"a": (10, None, 1.5, None), "b": (11, 20, 0.5, None),
                               "c": (None, 21, 0.25, None)})
        self.assertEqual(ledger.unresolved(self.dir), [21])   # #21 wasn't in closes

    def test_a_running_run_is_not_recorded(self):
        live = {"session_id": "a", "name": "x", "kind": "build", "ref": "#10", "started": "t"}
        self.assertEqual(ledger.record(self.dir, [live], {}), 0)

    def test_the_watch_state_save_leaves_the_ledger_alone(self):
        ledger.record(self.dir, [run("a", "#10", "2026-11-10T09:00:00+00:00", 1.0)], {})
        statedb.save(self.dir, statedb.empty())
        self.assertEqual([r["session_id"] for r in ledger.rows(self.dir)], ["a"])

    def test_scopes_are_the_mission_goal_and_area_above_nearest_first(self):
        ledger.record(self.dir, [run("a", "#10", "2026-11-10T09:00:00+00:00", 1.0),
                                 run("b", "#12", "2026-11-10T09:00:00+00:00", 1.0),
                                 run("c", "PR #9", "2026-11-10T09:00:00+00:00", 1.0)], {})
        self.assertEqual(ledger.unscoped(self.dir), [10, 12])
        ledger.set_scopes(self.dir, {
            10: scope(parent(30, "Task"), parent(40, "Mission"), parent(683, "Goal", "open-agentos/other")),
            12: None,   # couldn't be read: tried again later
        }, REPO)
        got = {r["session_id"]: (r["mission"], r["scopes"]) for r in ledger.rows(self.dir)}
        self.assertEqual(got["a"], (f"{REPO}#40", [f"{REPO}#40", "open-agentos/other#683"]))
        self.assertEqual(got["b"], (None, None))
        self.assertEqual(got["c"], (None, None))   # PR #9's issue isn't known yet: not dropped
        self.assertEqual(ledger.unscoped(self.dir), [12])
        ledger.set_scopes(self.dir, {12: scope()}, REPO)
        self.assertEqual(ledger.unscoped(self.dir), [])

    def test_a_run_with_no_issue_and_no_pr_has_nothing_above_it(self):
        ledger.record(self.dir, [run("a", "", "2026-11-10T09:00:00+00:00", 1.0)], {})
        ledger.set_scopes(self.dir, {}, REPO)
        self.assertEqual(ledger.rows(self.dir)[0]["scopes"], [])

    def test_a_pr_not_in_closes_is_resolved_later_from_github(self):
        ledger.record(self.dir, [run("b", "PR #20", "2026-11-10T09:00:00+00:00", 4.0, kind="review"),
                                 run("c", "PR #21", "2026-11-10T09:10:00+00:00", 1.0, kind="review"),
                                 run("d", "PR #22", "2026-11-10T09:20:00+00:00", 1.0, kind="review")], {})
        self.assertEqual(ledger.unresolved(self.dir), [20, 21, 22])
        # #20 closes #11 then #12: the first wins. #21 closes nothing. #22 wasn't read.
        self.assertEqual(ledger.set_prs(self.dir, {20: [11, 12], 21: []}), 2)
        got = {r["session_id"]: (r["issue"], r["scopes"]) for r in ledger.rows(self.dir)}
        self.assertEqual(got, {"b": (11, None), "c": (None, []), "d": (None, None)})
        self.assertEqual(ledger.unresolved(self.dir), [22])
        self.assertEqual(ledger.unscoped(self.dir), [11])
        ledger.set_scopes(self.dir, {11: scope(parent(40, "Mission"))}, REPO)
        self.assertEqual(ledger.rows(self.dir)[0]["mission"], f"{REPO}#40")

    def test_unscoped_reads_at_most_one_query_of_issues_per_tick(self):
        ledger.record(self.dir, [run(f"s{i}", f"#{i}", "2026-11-10T09:00:00+00:00", 0.1)
                                 for i in range(1, 40)], {})
        self.assertEqual(len(ledger.unscoped(self.dir)), ledger.SCOPES_PER_TICK)


class TotalsTest(unittest.TestCase):
    ROWS = [
        {"ended": "2026-10-31T23:00:00+00:00", "cost_usd": 100.0, "scopes": ["r#686"]},  # last month
        {"ended": "2026-11-09T12:00:00+00:00", "cost_usd": 20.0, "scopes": ["r#40", "r#686"]},
        {"ended": "2026-11-10T08:00:00+00:00", "cost_usd": 3.0, "scopes": ["r#40", "r#686"]},
        {"ended": "2026-11-10T09:00:00+00:00", "cost_usd": 2.0, "scopes": ["r#687"]},
        {"ended": "2026-11-10T10:00:00+00:00", "cost_usd": 1.0, "scopes": None},          # not read yet
        {"ended": "2026-11-10T11:00:00+00:00", "cost_usd": None, "scopes": []},           # no result
    ]

    def test_daily_monthly_and_per_scope(self):
        t = ledger.totals(self.ROWS, NOW, UTC)
        self.assertAlmostEqual(t["today"], 6.0)
        self.assertAlmostEqual(t["month"], 26.0)
        self.assertEqual(t["spent"], {"r#686": 123.0, "r#40": 23.0, "r#687": 2.0})
        self.assertAlmostEqual(t["unscoped"], 1.0)
        self.assertEqual(t["no_cost"], 1)

    def test_days_and_months_are_in_the_given_time_zone(self):
        tokyo = dt.timezone(dt.timedelta(hours=9))
        t = ledger.totals(self.ROWS, dt.datetime(2026, 10, 31, 23, 30, tzinfo=UTC), tokyo)
        # 2026-11-01 08:30 in Tokyo: October's 23:00 UTC run is November 1st's there
        self.assertAlmostEqual(t["today"], 100.0)
        self.assertAlmostEqual(t["month"], 126.0)

    def test_spent_text(self):
        text = ledger.spent_text(ledger.totals([
            {"ended": "2026-11-10T08:00:00+00:00", "cost_usd": 3.0, "scopes": [f"{REPO}#40", "other/x#9"]},
            {"ended": "2026-11-10T09:00:00+00:00", "cost_usd": None, "scopes": []},
        ], NOW, UTC), REPO, NOW, UTC)
        self.assertIn("Spent today (Tue 2026-11-10): $3.00", text)
        self.assertIn("Spent this month (November 2026): $3.00", text)
        self.assertRegex(text, r"\n  #40 +\$3\.00")
        self.assertRegex(text, r"\n  other/x#9 +\$3\.00")
        self.assertIn("1 run recorded no cost", text)
        self.assertIn("(GOV-0033)", text)
        self.assertIn("(#731)", text)


class WatchLedgerTest(unittest.TestCase):
    """The watcher's tick adds ended runs to the ledger and reads their scopes (#662)."""

    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home, True)
        self.lines, self.asked = [], []
        self.l = swarm.Launcher(self.home, out=self.lines.append)

    def watcher(self, get_scopes, get_pr_closes=None):
        return watch.Watch(self.l, REPO, "mattmcalister", set(), dry_run=False, get_scopes=get_scopes,
                           get_pr_closes=get_pr_closes or self.no_prs)

    def no_prs(self, repo, numbers):
        raise AssertionError(f"read PRs {numbers}: every PR here is in the open-PR model")

    def world(self, scopes=None):
        return watch.World(model={"prs": [{"number": 20, "closes": [{"number": 11}]}]}, issues=[],
                           scopes=scopes or {}, repo=REPO)

    def read(self, ret):
        def get(repo, numbers):
            self.asked.append(list(numbers))
            if isinstance(ret, Exception):
                raise ret
            return ret
        return get

    def test_ended_runs_are_recorded_with_scopes_from_the_tick_then_github(self):
        runs = {"build:10": run("a", "#10", "2026-11-10T09:00:00+00:00", 1.0),
                "review:20:abc": run("b", "PR #20", "2026-11-10T09:30:00+00:00", 0.5, kind="review"),
                "build:12": {"session_id": "c", "name": "x", "kind": "build", "ref": "#12",
                             "started": "2026-11-10T09:00:00+00:00"}}   # still running
        w = self.watcher(self.read({11: scope(parent(686, "Goal"))}))
        w.record_ledger(runs, self.world({10: scope(parent(40, "Mission"), parent(686, "Goal"))}))
        self.assertEqual(self.asked, [[11]])          # #10's scope came with the tick
        got = {r["session_id"]: (r["issue"], r["mission"], r["scopes"]) for r in ledger.rows(self.home / "launcher")}
        self.assertEqual(got, {"a": (10, f"{REPO}#40", [f"{REPO}#40", f"{REPO}#686"]),
                               "b": (11, None, [f"{REPO}#686"])})
        w.record_ledger(runs, self.world())           # next tick: nothing new, nothing to read
        self.assertEqual(self.asked, [[11]])
        self.assertEqual(len(ledger.rows(self.home / "launcher")), 2)

    def test_a_github_failure_is_said_once_and_retried(self):
        runs = {"build:10": run("a", "#10", "2026-11-10T09:00:00+00:00", 1.0)}
        w = self.watcher(self.read(RuntimeError("GitHub is down")))
        w.record_ledger(runs, self.world())
        w.record_ledger(runs, self.world())
        self.assertEqual(len(self.asked), 2)
        self.assertEqual(self.lines, ["swarm watch: the runs ledger couldn't be updated: GitHub is "
                                      "down; trying again next check"])
        self.assertEqual([r["cost_usd"] for r in ledger.rows(self.home / "launcher")], [1.0])  # still recorded
        w.get_scopes = self.read({10: scope()})
        w.record_ledger(runs, self.world())
        self.assertEqual(ledger.rows(self.home / "launcher")[0]["scopes"], [])

    def test_a_pr_merged_before_its_run_was_recorded_still_reaches_its_mission(self):
        # The reviewer's approval run ended, then the merger merged #20 before the next check:
        # the open-PR model no longer has it, so the ledger reads #20's issue from GitHub.
        runs = {"review:20:abc": run("b", "PR #20", "2026-11-10T09:30:00+00:00", 4.0, kind="review")}
        prs_read = []

        def closes(repo, numbers):
            prs_read.append(list(numbers))
            return {20: [11]}
        w = self.watcher(self.read({11: scope(parent(40, "Mission"))}), closes)
        merged = watch.World(model={"prs": []}, issues=[], scopes={}, repo=REPO)
        w.record_ledger(runs, merged)
        w.record_ledger(runs, merged)
        self.assertEqual(prs_read, [[20]])
        self.assertEqual(self.asked, [[11]])
        r = ledger.rows(self.home / "launcher")[0]
        self.assertEqual((r["issue"], r["mission"], r["scopes"]), (11, f"{REPO}#40", [f"{REPO}#40"]))
        t = ledger.totals(ledger.rows(self.home / "launcher"), NOW, UTC)
        self.assertEqual((t["spent"], t["unscoped"]), ({f"{REPO}#40": 4.0}, 0.0))

    def test_a_pr_read_failure_is_retried(self):
        runs = {"review:20:abc": run("b", "PR #20", "2026-11-10T09:30:00+00:00", 4.0, kind="review")}
        w = self.watcher(self.read({}), self.read(RuntimeError("GitHub is down")))
        merged = watch.World(model={"prs": []}, issues=[], scopes={}, repo=REPO)
        w.record_ledger(runs, merged)
        self.assertEqual(ledger.rows(self.home / "launcher")[0]["scopes"], None)  # not dropped
        w.get_pr_closes = lambda repo, numbers: {20: [11]}
        w.get_scopes = lambda repo, numbers: {11: scope(parent(686, "Goal"))}
        w.record_ledger(runs, merged)
        self.assertEqual(ledger.rows(self.home / "launcher")[0]["scopes"], [f"{REPO}#686"])


class GhPrClosesTest(unittest.TestCase):
    def test_issues_in_githubs_order_and_none_for_a_number_that_isnt_a_pr(self):
        swarm.dashboard()
        import ghql
        data = {20: {"closingIssuesReferences": {"nodes": [{"number": 11}, {"number": 12}]}},
                21: {"closingIssuesReferences": {"nodes": []}}, 22: None}
        with mock.patch.object(ghql, "batched", lambda repo, numbers, field, size: data) as _:
            self.assertEqual(watch.gh_pr_closes(REPO, [20, 21, 22]), {20: [11, 12], 21: [], 22: []})


class SpentCommandTest(unittest.TestCase):
    def test_swarm_spent_prints_the_ledger_totals(self):
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home, True)
        lines = []
        l = swarm.Launcher(home, out=lines.append)
        now = dt.datetime.now(UTC).replace(microsecond=0)
        ledger.record(l.dir, [run("a", "#10", now.isoformat(), 2.5)], {})
        self.assertEqual(swarm.main(["spent"], launcher=l), 0)
        self.assertIn("$2.50", lines[0].splitlines()[0])

    def test_an_unreadable_ledger_says_so(self):
        home = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home, True)
        lines = []
        l = swarm.Launcher(home, out=lines.append)
        l.dir.mkdir(parents=True)
        (l.dir / statedb.DB_FILE).write_text("not a database")
        self.assertEqual(swarm.main(["spent"], launcher=l), 1)
        self.assertTrue(lines[0].startswith("swarm spent: can't read the runs ledger"))


if __name__ == "__main__":
    unittest.main()
