"""Tests for `swarm daily` (#707): the daily reports and who started them, from swarm.db and the report issue (no streak, GOV-0040)."""
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


def who(login, bot=False):
    return {"login": login, "__typename": "Bot" if bot else "User"}


def edit(at, login, bot=False):
    return {"editedAt": at, "editor": who(login, bot)}


def ev(kind, at, login, bot=False):
    return {"__typename": kind, "createdAt": at, "actor": who(login, bot)}


def goal(n, kind="Goal", author=OWNER, bot=False, repo="o/r", edits=(), events=()):
    """A search node as SCOPE_EDITS_QUERY returns it."""
    return {"number": n, "title": "M1", "repository": {"nameWithOwner": repo},
            "author": who(author, bot), "issueType": {"name": kind},
            "userContentEdits": {"totalCount": len(edits), "nodes": list(edits)},
            "timelineItems": {"totalCount": len(events), "nodes": list(events)}}


def merged(n, closes=(), by="productswarm-merger", bot=True):
    """A search node as UNCLOSED_QUERY returns it; closes is (number, state[, reopens[, repo]])."""
    def ref(number, state, reopens=0, repo="o/r"):
        return {"number": number, "state": state, "repository": {"nameWithOwner": repo},
                "timelineItems": {"totalCount": reopens}}
    return {"number": n, "mergedBy": who(by, bot) if by else None,
            "closingIssuesReferences": {"nodes": [ref(*c) for c in closes]}}


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

    def run_daily(self, comments, acted, now=NOW, scopes=(), prs=(), effort_cache=None):
        statedb.save(self.home / "launcher", {"acted": acted})
        self.since = self.merged_since = None

        def get_merged(repo, since):
            self.merged_since = since
            return list(prs)

        def get_scopes(repo, since):
            self.since = since
            return list(scopes)
        rc = swarm.daily(self.l, "o/r", self.toml, get_comments=lambda repo, n: comments, now=now,
                         tz=UTC, owner=OWNER, agents={PLANNER, "productswarm-builder[bot]"},
                         get_scopes=get_scopes, get_merged=get_merged,
                         effort_cache=effort_cache or self.home / "no-effort.json")
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
        days = out.split("\n\n")[0]
        self.assertEqual(sum(1 for line in days.splitlines() if line.startswith("  ")), 10)
        self.assertIn("  Tue 2026-10-27  missed", out)                              # 10th working day
        self.assertIn("Latest report [daily] started: Mon 2026-11-09.\n\n", out)
        self.assertNotIn("Streak", out)                             # GOV-0040: no streak as progress
        self.assertNotRegex(out, r"\bM1: day\b|\b\d+ of (5|10)\b")

    def test_missed_day_is_listed_and_breaks_nothing(self):
        comments = [c("2026-11-04T08:35:00Z", "**Daily report, Wed 2026-11-04**"),
                    c("2026-11-06T08:35:00Z", "**Daily report, Fri 2026-11-06**"),
                    c("2026-11-09T08:35:00Z", "**Daily report, Mon 2026-11-09**")]
        acted = {f"daily:249:2026-11-0{d}": "started planner-issue-249" for d in (4, 5, 6, 9)}
        out = self.run_daily(comments, acted)
        self.assertIn("  Thu 2026-11-05  missed  ([daily] ran but posted no report)", out)
        self.assertIn("  Wed 2026-11-04  posted 08:35  started by [daily]", out)
        self.assertIn("Latest report [daily] started: Mon 2026-11-09.", out)

    def test_owner_started_by_hand_doesnt_count(self):
        comments = [c("2026-11-06T10:00:00Z", "**Daily report, Fri 2026-11-06**"),
                    c("2026-11-09T08:35:00Z", "**Daily report, Mon 2026-11-09**")]
        acted = {"daily:249:2026-11-09": "started planner-issue-249"}      # no [daily] on the 6th
        out = self.run_daily(comments, acted)
        self.assertIn("  Fri 2026-11-06  posted 10:00  started by the owner, by hand (no [daily] run)", out)
        self.assertIn("Latest report [daily] started: Mon 2026-11-09.", out)

    def test_today_not_yet_posted_isnt_the_latest(self):
        early = dt.datetime(2026, 11, 9, 7, 0, tzinfo=UTC)
        out = self.run_daily(COMMENTS_249[:3], ACTED_249 | {"daily:249:2026-11-09": "x"}, now=early)
        self.assertIn("  Mon 2026-11-09  not yet posted", out)
        self.assertIn("Latest report [daily] started: Fri 2026-11-06.", out)

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

    # ---- GOV-0040: no streak, just whether [daily] started a report; #709: Goal and Area edits

    def test_no_report_daily_started_says_so(self):
        comments = [c("2026-11-06T10:00:00Z", "**Daily report, Fri 2026-11-06**")]
        out = self.run_daily(comments, {})
        self.assertIn("No report in these 10 working days was started by [daily].", out)
        self.assertNotIn("M1: day", out)

    def test_daily_started_is_the_newest_daily_row(self):
        days = swarm.working_days(dt.date(2026, 11, 9))
        rows = [{"day": d, "posted": NOW, "by": "by hand" if i < 2 else "[daily]", "ran": i >= 2}
                for i, d in enumerate(days)]
        self.assertEqual(swarm.daily_started(rows), days[2])
        self.assertIsNone(swarm.daily_started(rows[:2]))

    def test_goal_edits_by_an_app_show_and_the_owners_dont(self):
        out = self.run_daily(COMMENTS_249, ACTED_249, scopes=[
            goal(683, edits=[edit("2026-11-09T10:00:00Z", "productswarm-planner", bot=True),
                             edit("2026-11-09T09:00:00Z", OWNER),
                             edit("2026-11-05T09:00:00Z", "productswarm-builder", bot=True)],
                 events=[ev("RenamedTitleEvent", "2026-11-08T12:00:00Z", "productswarm-builder", True),
                         ev("ClosedEvent", "2026-11-09T11:00:00Z", OWNER)]),
            goal(690, author="productswarm-planner", bot=True,           # not the owner's: doesn't count
                 edits=[edit("2026-11-09T10:00:00Z", "productswarm-planner", bot=True)]),
            goal(691, kind="Area", repo="o/other",
                 events=[ev("ClosedEvent", "2026-11-09T12:00:00Z", "someone")])])
        self.assertEqual(self.since, dt.date(2026, 11, 6))
        self.assertIn("Goal and Area edits not made by @mattmcalister since Fri 2026-11-06 00:00 "
                      "(GOV-0031):\n"
                      "  Sun 2026-11-08 12:00  productswarm-builder[bot] renamed it: Goal #683 M1\n"
                      "  Mon 2026-11-09 10:00  productswarm-planner[bot] edited the body: Goal #683 M1\n"
                      "  Mon 2026-11-09 12:00  someone closed it: Area o/other#691 M1", out)
        self.assertNotIn("#690", out)
        self.assertNotIn("2026-11-05 09:00", out)               # before the window

    def test_no_goal_edits_says_none_and_a_long_history_says_check(self):
        out = self.run_daily(COMMENTS_249, ACTED_249)
        self.assertIn("(GOV-0031):\n  none\n\n", out)
        g = goal(683, edits=[edit("2026-11-09T10:00:00Z", OWNER)])
        g["userContentEdits"]["totalCount"] = 80
        out = self.run_daily(COMMENTS_249, ACTED_249, scopes=[g])
        self.assertIn("  Goal #683: history too long to read whole; check it by hand", out)

    def test_goal_edits_read_failure_is_one_line(self):
        statedb.save(self.home / "launcher", {"acted": ACTED_249})

        def boom(repo, since):
            raise RuntimeError("gh api graphql failed: rate limited")
        self.assertEqual(swarm.daily(self.l, "o/r", self.toml, get_comments=lambda r, n: COMMENTS_249,
                                     now=NOW, tz=UTC, owner=OWNER, agents={PLANNER},
                                     get_scopes=boom, get_merged=lambda r, s: []), 0)
        self.assertIn("Goal and Area edits couldn't be read: gh api graphql failed: rate limited",
                      self.lines[-1])

    # ---- #806: issues left open after a merged PR that closes them (#812, option 2)

    def test_lists_issues_a_merged_pr_left_open(self):
        out = self.run_daily(COMMENTS_249, ACTED_249, prs=[
            merged(793, [(680, "OPEN")]),
            merged(745, [(663, "OPEN"), (664, "CLOSED")]),
            merged(790, [(774, "CLOSED")], by=OWNER, bot=False),
            merged(791, [(772, "OPEN", 1)]),                       # reopened since: left alone
            merged(792, [(9, "OPEN", 0, "o/other")], by=OWNER, bot=False),
            merged(794)])
        self.assertEqual(self.merged_since, dt.date(2026, 10, 27))   # the 10th working day back
        self.assertTrue(out.endswith(
            "Issues still open after a merged PR that closes them, PRs merged since Tue 2026-10-27 (#806):\n"
            "  #663  PR #745 closes it, merged by productswarm-merger[bot]\n"
            "  o/other#9  PR #792 closes it, merged by mattmcalister\n"
            "  #680  PR #793 closes it, merged by productswarm-merger[bot]"), out)
        self.assertNotIn("#664", out)
        self.assertNotIn("#772", out)

    def test_no_issues_left_open_says_none(self):
        out = self.run_daily(COMMENTS_249, ACTED_249, prs=[merged(790, [(774, "CLOSED")])])
        self.assertTrue(out.endswith("(#806):\n  none"), out)

    def test_merged_prs_read_failure_is_one_line(self):
        statedb.save(self.home / "launcher", {"acted": ACTED_249})

        def boom(repo, since):
            raise RuntimeError("gh api graphql failed: rate limited")
        self.assertEqual(swarm.daily(self.l, "o/r", self.toml, get_comments=lambda r, n: COMMENTS_249,
                                     now=NOW, tz=UTC, owner=OWNER, agents={PLANNER},
                                     get_scopes=lambda r, s: [], get_merged=boom), 0)
        self.assertTrue(self.lines[-1].endswith(
            "Issues still open after their PR merged couldn't be read: gh api graphql failed: rate limited"))

    def test_merged_prs_read_every_page(self):
        pages = [{"data": {"search": {"pageInfo": {"hasNextPage": True, "endCursor": "c1"},
                                      "nodes": [merged(1, [(10, "OPEN")])]}}},
                 {"data": {"search": {"pageInfo": {"hasNextPage": False, "endCursor": None},
                                      "nodes": [merged(2, [(20, "OPEN")])]}}}]
        calls = []

        class G:
            @staticmethod
            def gh_json(*args):
                calls.append(args)
                return pages[len(calls) - 1]
        orig = swarm.dashboard
        swarm.dashboard = lambda: G
        try:
            nodes = swarm.gh_merged_nodes("o/r", dt.date(2026, 10, 27))
        finally:
            swarm.dashboard = orig
        self.assertEqual([n["number"] for n in nodes], [1, 2])
        self.assertIn("q=repo:o/r is:pr is:merged merged:>=2026-10-27", calls[0])
        self.assertNotIn("after=c1", calls[0])
        self.assertIn("after=c1", calls[1])

    def test_working_days(self):
        days = swarm.working_days(dt.date(2026, 11, 9))
        self.assertEqual(len(days), 10)
        self.assertEqual(days[0], dt.date(2026, 11, 9))
        self.assertEqual(days[1], dt.date(2026, 11, 6))
        self.assertTrue(all(d.weekday() < 5 for d in days))


class DailyEffortTest(unittest.TestCase):
    """#1013: the upkeep risk line, from the effort cache, for the report's Risks."""
    FIXTURE = Path(__file__).resolve().parent / "testdata" / "effort.json"
    setUp = DailyTest.setUp
    run_daily = DailyTest.run_daily

    def section(self, out: str) -> list[str]:
        return out[out.index("Effort risks"):out.index("Issues still open")].strip().splitlines()

    def test_upkeep_risk_line_from_the_fixture(self):
        friday = dt.datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
        out = self.run_daily(COMMENTS_249, ACTED_249, now=friday, effort_cache=self.FIXTURE)
        # o/r#683: 2 of 3 upkeep. o/r#684 is exactly half and o/r#987 1 of 5: no line.
        self.assertEqual(self.section(out)[1:], [
            "  Upkeep risk: o/r#683: 2 of 3 PRs merged in the last 7 days were upkeep (more than half)."])

    def test_no_cache_says_none_checked(self):
        out = self.run_daily(COMMENTS_249, ACTED_249)
        self.assertEqual(len(self.section(out)), 1)
        self.assertIn("Effort risks: no effort cache yet", out)

    def test_nothing_in_the_window_says_none(self):
        later = dt.datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
        out = self.run_daily(COMMENTS_249, ACTED_249, now=later, effort_cache=self.FIXTURE)
        self.assertEqual(self.section(out)[1:], ["  none"])

if __name__ == "__main__":
    unittest.main()
