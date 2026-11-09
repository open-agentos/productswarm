"""Tests for `swarm daily` (#707): M1's streak counted from swarm.db and the report issue."""
from __future__ import annotations

import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import swarm  # noqa: E402
import statedb  # noqa: E402

UTC = dt.timezone.utc
OWNER = "mattmcalister"
PLANNER = "productswarm-planner[bot]"
NOW = dt.datetime(2026, 11, 9, 19, 0, tzinfo=UTC)       # a Monday
SESSION = '[[session]]\nrole = "builder"\nmodel = "m"\n\n'


def c(at, body, user=PLANNER):
    return {"created_at": at, "body": body, "user": {"login": user}}


# #249's comments from 2026-11-06 to 2026-11-09, as posted.
COMMENTS_249 = [
    c("2026-11-06T21:19:44Z", "Ask: builder: what are you working on and why?", OWNER),
    c("2026-11-06T21:48:39Z", "**Daily report, Fri 2026-11-06: M1 started today**\n\nDone: ..."),
    c("2026-11-06T21:53:00Z", "Nothing right now.", "productswarm-builder[bot]"),
    c("2026-11-09T08:34:17Z", "**Daily report, Mon 2026-11-09: you adopted operating model v2**"),
    c("2026-11-09T08:34:28Z", "**Monday check-in, week of 2026-11-09: M1 moved**"),
    c("2026-11-09T18:57:21Z", "**Here are 9 Tasks**"),
]
ACTED_249 = {"daily:249:2026-11-06": "started planner-issue-249",
             "daily:249:2026-11-09": "started planner-issue-249",
             "ask:249:6696612087": "started builder-issue-249"}


class DailyTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        (self.home / "launcher").mkdir()
        self.toml = self.home / "swarm.toml"
        self.toml.write_text(SESSION + "[watch]\ninterval_minutes = 5\nmax_live = 1\nmax_turns = 50\n"
                             "report_issue = 249\ndaily = true\ndaily_at = \"08:30\"\n")
        self.lines: list[str] = []
        self.l = swarm.Launcher(self.home, root=self.home / "repo", out=self.lines.append)

    def run_daily(self, comments, acted, now=NOW):
        statedb.save(self.home / "launcher", {"acted": acted})
        rc = swarm.daily(self.l, "o/r", self.toml, get_comments=lambda repo, n: comments, now=now,
                         tz=UTC, owner=OWNER, agents={PLANNER, "productswarm-builder[bot]"})
        self.assertEqual(rc, 0)
        return self.lines[-1]

    def test_matches_249_from_nov_6_to_9(self):
        out = self.run_daily(COMMENTS_249, ACTED_249)
        self.assertIn("Daily reports on #249, last 10 working days (local time):", out)
        self.assertIn("  Mon 2026-11-09  posted 08:34  started by [daily]", out)   # first of the two
        self.assertIn("  Fri 2026-11-06  posted 21:48  started by [daily]", out)
        self.assertIn("  Thu 2026-11-05  missed", out)
        self.assertNotIn("Sat", out)
        self.assertNotIn("Sun", out)
        self.assertEqual(sum(1 for line in out.splitlines() if line.startswith("  ")), 10)
        self.assertIn("  Tue 2026-10-27  missed", out)                              # 10th working day
        self.assertTrue(out.endswith("Streak: 2 working days in a row with a report [daily] started."))

    def test_missed_day_breaks_the_streak(self):
        comments = [c("2026-11-04T08:35:00Z", "**Daily report, Wed 2026-11-04**"),
                    c("2026-11-06T08:35:00Z", "**Daily report, Fri 2026-11-06**"),
                    c("2026-11-09T08:35:00Z", "**Daily report, Mon 2026-11-09**")]
        acted = {f"daily:249:2026-11-0{d}": "started planner-issue-249" for d in (4, 5, 6, 9)}
        out = self.run_daily(comments, acted)
        self.assertIn("  Thu 2026-11-05  missed  ([daily] ran but posted no report)", out)
        self.assertIn("  Wed 2026-11-04  posted 08:35  started by [daily]", out)
        self.assertIn("Streak: 2 working days", out)

    def test_owner_started_by_hand_doesnt_count(self):
        comments = [c("2026-11-06T10:00:00Z", "**Daily report, Fri 2026-11-06**"),
                    c("2026-11-09T08:35:00Z", "**Daily report, Mon 2026-11-09**")]
        acted = {"daily:249:2026-11-09": "started planner-issue-249"}      # no [daily] on the 6th
        out = self.run_daily(comments, acted)
        self.assertIn("  Fri 2026-11-06  posted 10:00  started by the owner, by hand (no [daily] run)", out)
        self.assertIn("Streak: 1 working day in a row", out)

    def test_today_not_yet_posted_keeps_the_streak(self):
        early = dt.datetime(2026, 11, 9, 7, 0, tzinfo=UTC)
        out = self.run_daily(COMMENTS_249[:3], ACTED_249 | {"daily:249:2026-11-09": "x"}, now=early)
        self.assertIn("  Mon 2026-11-09  not yet posted", out)
        self.assertIn("Streak: 1 working day", out)

    def test_late_report_counts_for_its_day_and_untrusted_authors_dont(self):
        comments = [c("2026-11-07T01:10:00Z", "Daily report, Fri 2026-11-06"),       # after midnight
                    c("2026-11-09T08:35:00Z", "**Daily report, Mon 2026-11-09**", "someone-else")]
        out = self.run_daily(comments, ACTED_249)
        self.assertIn("  Fri 2026-11-06  posted 01:10  started by [daily]", out)
        self.assertIn("  Mon 2026-11-09  not yet posted  ([daily] run started)", out)

    def test_needs_report_issue(self):
        self.toml.write_text(SESSION + "[watch]\ninterval_minutes = 5\nmax_live = 1\n")
        self.assertEqual(swarm.daily(self.l, "o/r", self.toml, get_comments=lambda r, n: [],
                                     owner=OWNER, agents=set()), 1)
        self.assertIn("no [watch] report_issue", self.lines[-1])

    def test_working_days(self):
        days = swarm.working_days(dt.date(2026, 11, 9))
        self.assertEqual(len(days), 10)
        self.assertEqual(days[0], dt.date(2026, 11, 9))
        self.assertEqual(days[1], dt.date(2026, 11, 6))
        self.assertTrue(all(d.weekday() < 5 for d in days))


if __name__ == "__main__":
    unittest.main()
