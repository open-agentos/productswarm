"""Tests for evals/red_check.py (#330). Canned review lists only; nothing calls GitHub.

Run: python3 -m unittest discover -s evals
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gather  # noqa: E402
import red_check as rc  # noqa: E402

START = {"number": 400, "mergedAt": "2026-11-10T12:00:00Z",
         "closingIssuesReferences": [{"number": rc.START_ISSUE}]}
BUILDER = {"login": "app/productswarm-builder"}
DOCS = {"login": "app/productswarm-docs"}
REVIEWER = {"login": "productswarm-reviewer[bot]"}


def review(state, day, hour=0, user=REVIEWER, body=""):
    return {"user": user, "state": state, "body": body,
            "submitted_at": f"2026-11-{day:02d}T{hour:02d}:00:00Z"}


def red(day, hour=0, body=""):
    return review("CHANGES_REQUESTED", day, hour, body=body)


def ok(day, hour=0):
    return review("APPROVED", day, hour)


def pr(n, reviews, state="OPEN", author=BUILDER, closes=(1,)):
    return {"number": n, "state": state, "author": author, "reviews": reviews,
            "closingIssuesReferences": [{"number": c} for c in closes]}


def run(*prs, start=START):
    data = {"start": start, "prs": list(prs)}
    rows = rc.count(data)
    return rows, rc.report(data, rows)


class Start(unittest.TestCase):
    def test_not_merged_yet_counts_nothing(self):
        rows, lines = run(pr(1, [red(12)]), start=None)
        self.assertEqual(rows, [])
        self.assertIn("hasn't merged yet", lines[0])
        self.assertEqual(lines[-1], "red check (#311): 0 of 5 counted, 0 reached the "
                                    "2-round bound; revisit if more than 2")

    def test_start_is_the_merged_pr_closing_329(self):
        open_pr = {"number": 401, "mergedAt": None,
                   "closingIssuesReferences": [{"number": rc.START_ISSUE}]}
        other = {"number": 402, "mergedAt": "2026-11-01T00:00:00Z",
                 "closingIssuesReferences": [{"number": 1}]}
        self.assertIsNone(rc.start_of([open_pr, other]))
        self.assertEqual(rc.start_of([open_pr, other, START])["number"], 400)

    def test_reds_before_the_start_ignored(self):
        rows, _ = run(pr(1, [red(9), ok(9, 5)]), pr(2, [red(9), red(11)]))
        self.assertEqual([r["number"] for r in rows], [2])
        self.assertEqual(rows[0]["reds"], 1)


class Counting(unittest.TestCase):
    def test_non_builder_pr_ignored(self):
        rows, _ = run(pr(1, [red(11)], author=DOCS),
                      pr(2, [red(11)], author={"login": "mattmcalister"}))
        self.assertEqual(rows, [])

    def test_other_reviewers_ignored(self):
        rows, _ = run(pr(1, [review("CHANGES_REQUESTED", 11, user={"login": "mattmcalister"})]))
        self.assertEqual(rows, [])

    def test_several_reds_count_once(self):
        rows, lines = run(pr(1, [red(11), red(12), ok(13)], state="MERGED"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reds"], 2)
        self.assertIn("1 of 5 counted", lines[-1])

    def test_fixed_in_one_round(self):
        rows, lines = run(pr(1, [red(11, body="**Block 1:** unmet"), ok(12)], state="MERGED"))
        self.assertEqual(rows[0]["outcome"], "fixed in 1 round")
        self.assertIn("PR #1  merged  1 red (block 1)  fixed in 1 round", lines)

    def test_fixed_in_two_rounds(self):
        rows, _ = run(pr(1, [red(11), red(12), review("COMMENTED", 13)]))
        self.assertEqual(rows[0]["outcome"], "fixed in 2 rounds")
        self.assertFalse(rows[0]["settled"])

    def test_reached_the_bound(self):
        rows, _ = run(pr(1, [red(11), red(12), red(13)]))
        self.assertEqual(rows[0]["outcome"], "reached the bound")
        self.assertTrue(rows[0]["settled"])

    def test_still_open(self):
        rows, _ = run(pr(1, [red(11)]))
        self.assertEqual(rows[0]["outcome"], "still open")

    def test_merged_while_red(self):
        rows, _ = run(pr(1, [red(11)], state="MERGED"))
        self.assertEqual(rows[0]["outcome"], "ended while red")

    def test_respond_skips_pr_not_closing_one_issue(self):
        rows, lines = run(pr(1, [red(11, body="Block 6: closes no issue")], closes=()),
                          pr(2, [red(12)], closes=(1, 2)))
        self.assertEqual([r["outcome"] for r in rows], ["not responded: [respond] skips it"] * 2)
        self.assertIn("PR #1  open  1 red (block 6)  not responded: [respond] skips it", lines)

    def test_only_first_five_by_first_red(self):
        prs = [pr(n, [red(11, hour=10 - n)]) for n in range(1, 8)]
        rows, _ = run(*prs)
        self.assertEqual([r["number"] for r in rows], [7, 6, 5, 4, 3])


class Summary(unittest.TestCase):
    def five(self, at_bound, settled=True):
        prs = []
        for n in range(1, 6):
            reds = [red(11, n)] + ([red(12, n), red(13, n)] if n <= at_bound else [])
            prs.append(pr(n, reds + [ok(14, n)], state="MERGED" if settled else "OPEN"))
        return run(*prs)[1]

    def test_two_of_five_at_bound(self):
        lines = self.five(2)
        self.assertEqual(lines[-2], "red check (#311): 5 of 5 counted, 2 reached the "
                                    "2-round bound; revisit if more than 2")
        self.assertEqual(lines[-1], "revisit: no")

    def test_three_of_five_at_bound(self):
        lines = self.five(3)
        self.assertIn("5 of 5 counted, 3 reached", lines[-2])
        self.assertEqual(lines[-1], "revisit: yes")

    def test_no_verdict_until_all_settled(self):
        lines = self.five(2, settled=False)
        self.assertTrue(lines[-1].startswith("red check (#311): 5 of 5 counted"))


class ReadOnly(unittest.TestCase):
    def test_fetch_makes_only_read_calls(self):
        """Every call goes through gather.gh(), whose guard refuses writes."""
        def fake(cmd, **_):
            args = cmd[1:]
            gather.check_read_only(args)   # the real guard; raises on a write
            out = ({"closedByPullRequestsReferences": [{"number": 400}]} if args[:2] == ["issue", "view"]
                   else START if args[:2] == ["pr", "view"]
                   else [pr(1, [])] if args[:2] == ["pr", "list"]
                   else [[red(11)]])
            calls.append(args)
            return subprocess.CompletedProcess(cmd, 0, json.dumps(out), "")

        calls = []
        with mock.patch.object(gather.subprocess, "run", side_effect=fake):
            data = rc.fetch("o/r")
        self.assertEqual([c[:2] for c in calls],
                         [["issue", "view"], ["pr", "view"], ["pr", "list"], ["api", "--paginate"]])
        self.assertEqual(data["start"]["number"], 400)
        self.assertEqual(data["prs"][0]["reviews"], [red(11)])


if __name__ == "__main__":
    unittest.main()
