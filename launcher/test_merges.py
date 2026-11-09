"""Tests for `swarm merges` (#710): a week's merges by the merger and by the owner, and its
reverts. Canned PR data only; no test calls GitHub.

Run: python3 -m unittest discover -s launcher
"""
import datetime as dt
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import swarm  # noqa: E402

OWNER = "mattmcalister"
HEAD, OLD = "a" * 40, "b" * 40
UTC = dt.timezone.utc
START, END = dt.datetime(2026, 11, 2, tzinfo=UTC), dt.datetime(2026, 11, 9, tzinfo=UTC)


def pr(n, by, at="2026-11-03T10:00:00Z", title="A change", body="", reviews=()):
    # gh pr list's shape: GraphQL logins, so bots have no [bot] suffix
    return {"number": n, "title": title, "body": body, "mergedAt": at, "headRefOid": HEAD,
            "mergedBy": {"login": by}, "reviews": list(reviews)}


def review(login, state="APPROVED", oid=HEAD):
    return {"author": {"login": login}, "state": state, "commit": {"oid": oid}}


class WeekTest(unittest.TestCase):
    def test_this_week_starts_monday_utc(self):
        now = dt.datetime(2026, 11, 9, 19, 30, tzinfo=UTC)   # a Monday
        self.assertEqual(swarm.week_of(now), (START + dt.timedelta(days=7), END + dt.timedelta(days=7)))
        self.assertEqual(swarm.week_of(dt.datetime(2026, 11, 8, 23, 59, tzinfo=UTC)), (START, END))

    def test_last_week(self):
        self.assertEqual(swarm.week_of(dt.datetime(2026, 11, 11, tzinfo=UTC), last=True), (START, END))

    def test_other_timezones_use_the_utc_week(self):
        now = dt.datetime(2026, 11, 8, 20, 0, tzinfo=dt.timezone(dt.timedelta(hours=-5)))  # Mon 01:00 UTC
        self.assertEqual(swarm.week_of(now)[0], END)


class MergesTextTest(unittest.TestCase):
    def text(self, prs):
        return swarm.merges_text(prs, OWNER, START, END)

    def test_splits_by_merger_and_owner(self):
        out = self.text([pr(1, OWNER), pr(2, "productswarm-merger"), pr(3, "productswarm-merger[bot]")])
        self.assertIn("week of 2026-11-02 to 2026-11-08 (UTC): 3", out)
        self.assertIn("by the merger (productswarm-merger[bot]): 2", out)
        self.assertIn(f"by the owner (@{OWNER}): 1", out)
        self.assertNotIn("anyone else", out)
        self.assertIn("Reverts: 0", out)

    def test_all_by_the_owner(self):
        out = self.text([pr(n, OWNER) for n in range(5)])
        self.assertIn("by the merger (productswarm-merger[bot]): 0", out)
        self.assertIn(f"by the owner (@{OWNER}): 5", out)

    def test_someone_else(self):
        out = self.text([pr(1, "someone"), pr(2, OWNER)])
        self.assertIn("by anyone else: 1 (@someone)", out)

    def test_outside_the_week_is_dropped(self):
        out = self.text([pr(1, OWNER, at="2026-11-01T23:59:59Z"), pr(2, OWNER, at="2026-11-09T00:00:00Z"),
                         pr(3, OWNER, at="2026-11-02T00:00:00Z"), pr(4, OWNER, at=None)])
        self.assertIn(": 1\n", out)

    def test_unreviewed_revert(self):
        out = self.text([pr(646, OWNER, title='Revert "Update swarm.toml"',
                            body="Reverts open-agentos/productswarm#640\n\n"), pr(1, OWNER)])
        self.assertIn("Reverts: 1, 1 unreviewed", out)
        self.assertIn(f"#646 reverts #640, merged by @{OWNER}: not reviewed", out)

    def test_reviewed_revert(self):
        out = self.text([pr(9, "productswarm-merger", title='Revert "x"', body="Reverts #8",
                            reviews=[review("productswarm-reviewer")])])
        self.assertIn("Reverts: 1, 0 unreviewed", out)
        self.assertIn("#9 reverts #8, merged by @productswarm-merger: reviewed (approved at head)", out)

    def test_revert_by_commit(self):
        out = self.text([pr(9, OWNER, title="Undo it", body="This reverts commit abc123.",
                            reviews=[review(OWNER)])])
        self.assertIn("#9 reverts a commit", out)
        self.assertIn("reviewed (approved at head)", out)

    def test_not_a_revert(self):
        self.assertIs(swarm.reverted(pr(1, OWNER, title="Reverting is hard", body="Docs on reverts.")), False)


class ReviewedAtHeadTest(unittest.TestCase):
    def ok(self, reviews):
        return swarm.reviewed_at_head(pr(1, OWNER, reviews=reviews), OWNER)

    def test_approval_at_head_by_the_reviewer_or_owner(self):
        self.assertTrue(self.ok([review("productswarm-reviewer")]))
        self.assertTrue(self.ok([review("productswarm-reviewer[bot]")]))
        self.assertTrue(self.ok([review(OWNER)]))

    def test_older_commit_or_other_reviewer_doesnt_count(self):
        self.assertFalse(self.ok([review("productswarm-reviewer", oid=OLD)]))
        self.assertFalse(self.ok([review("someone")]))
        self.assertFalse(self.ok([review("productswarm-reviewer", state="COMMENTED")]))
        self.assertFalse(self.ok([]))

    def test_latest_decisive_review_wins(self):
        self.assertFalse(self.ok([review("productswarm-reviewer"),
                                  review("productswarm-reviewer", "CHANGES_REQUESTED")]))
        self.assertFalse(self.ok([review("productswarm-reviewer"), review("productswarm-reviewer", "DISMISSED")]))
        self.assertFalse(self.ok([review(OWNER), review("productswarm-reviewer", "CHANGES_REQUESTED")]))


class CommandTest(unittest.TestCase):
    def test_reads_the_week_and_prints(self):
        lines, asked = [], []

        class L:
            def out(self, s):
                lines.append(s)

        def get(repo, start, end):
            asked.append((repo, start, end))
            return [pr(1, OWNER)]

        rc = swarm.merges(L(), "o/r", last=True, now=dt.datetime(2026, 11, 9, 19, tzinfo=UTC),
                          get_merged=get, owner=lambda: OWNER)
        self.assertEqual(rc, 0)
        self.assertEqual(asked, [("o/r", START, END)])
        self.assertIn(f"by the owner (@{OWNER}): 1", lines[0])


if __name__ == "__main__":
    unittest.main()
