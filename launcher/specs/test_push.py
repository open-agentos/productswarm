"""Tests for launcher/specs/push.py (#957): `swarm specs push` against the fake backend.

Uses #941's fixture and a stub GitHub; no network. Run: python3 run_tests.py launcher
"""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from specs import events, push, snapshot, sync  # noqa: E402
from specs.fake import FakeSource  # noqa: E402
from specs.push import PR, Item  # noqa: E402
from specs.source import FeatureStatus  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "testdata" / "fake_initiative.json"
OWNER = "owner-login"
REPO = "acme/productswarm"
GOAL = (REPO, 938)
REF = f"{REPO}#938"
NOW = datetime(2026, 11, 13, 9, 30, tzinfo=timezone.utc)
INIT = "init-0001-recipe-box"
MODEL = "claude-opus-5-5"
HEAD = "a" * 40
ISSUE = f"https://github.com/{REPO}/issues/101"
PR_URL = f"https://github.com/{REPO}/pull/120"


def goal_node(body=f"Outcome.\n\nSpec source: fake://{INIT}\n", author=OWNER):
    return {"state": "OPEN", "body": body, "issueType": {"name": "Goal"},
            "author": {"login": author, "__typename": "User"},
            "userContentEdits": {"totalCount": 0, "nodes": []}}


def review(state, commit=HEAD, author="productswarm-reviewer[bot]"):
    return {"author": author, "state": state, "commit": commit}


def pr(number=120, state="OPEN", reviews=(), head=HEAD):
    return PR(number, f"https://github.com/{REPO}/pull/{number}", state, head, tuple(reviews))


class StubGitHub:
    """GitHub in memory: a Goal and its sub-issues."""

    def __init__(self, items=(), node=None):
        self.node = goal_node() if node is None else node
        self.items = list(items)

    def goal(self, repo, n):
        return self.node

    def sub_issues(self, repo, n):
        return self.items


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"PRODUCTSWARM_HOME": self.tmp.name})
        env.start()
        self.addCleanup(env.stop)
        self.fixture = Path(self.tmp.name) / "fixture.json"
        self.fixture.write_text(FIXTURE.read_text())
        self.source = FakeSource(self.fixture)
        # FEAT-1 as pull leaves it: linked to its issue, In progress.
        self.source.set_links("FEAT-1", issue_url=ISSUE)
        self.source.set_status("FEAT-1", FeatureStatus.IN_PROGRESS)
        self.source.writes.clear()
        self.lines: list[str] = []

    def item(self, fid="FEAT-1", state="OPEN", prs=(), labels=(), url=ISSUE):
        f = self.source._features[fid]
        block = snapshot.render(f, self.source.get_spec(fid), "fake", NOW)
        return Item(url, state, f"{block}\n\nGoal: {REF}\n", tuple(labels), tuple(prs))

    def push(self, gh, what_shipped=None, dry_run=False, source=None):
        self.lines.clear()
        return push.push(GOAL, source or self.source, gh, what_shipped, dry_run, owner=OWNER,
                         model=MODEL, out=self.lines.append)

    def feat(self, fid="FEAT-1"):
        return self.source._features[fid]

    def line(self, fid="FEAT-1"):
        return next(ln for ln in self.lines if ln.startswith(f"  {fid}"))


class StatusTableTest(Base):
    """Each row of #937 §5.4's table."""

    def test_issue_open_no_pr_is_in_progress_and_unchanged(self):
        self.push(StubGitHub([self.item()]))
        self.assertEqual(self.feat().status, FeatureStatus.IN_PROGRESS)
        self.assertEqual(self.source.writes, [])
        self.assertEqual(self.line(), "  FEAT-1 Save a recipe from a link: unchanged")

    def test_pr_open_is_in_review_with_pr_url(self):
        self.push(StubGitHub([self.item(prs=[pr()])]))
        f = self.feat()
        self.assertEqual((f.status, f.pr_url, f.issue_url),
                         (FeatureStatus.IN_REVIEW, PR_URL, ISSUE))
        self.assertEqual([w[0] for w in self.source.writes], ["set_status", "set_links"])
        self.assertEqual(self.source.writes[1][2], {"issue_url": None, "pr_url": PR_URL})
        self.assertEqual(self.line(), "  FEAT-1 Save a recipe from a link: status In progress → "
                                      f"In review; PR {PR_URL}")

    def test_changes_requested_stays_in_review(self):
        self.push(StubGitHub([self.item(prs=[pr()])]))
        self.source.writes.clear()
        self.push(StubGitHub([self.item(prs=[pr(reviews=[review("CHANGES_REQUESTED")])])]))
        self.assertEqual(self.feat().status, FeatureStatus.IN_REVIEW)
        self.assertEqual(self.source.writes, [])
        self.assertTrue(self.line().endswith(": unchanged"))

    def test_merged_and_closed_is_shipped(self):
        self.push(StubGitHub([self.item(state="CLOSED", prs=[pr(state="MERGED")])]))
        f = self.feat()
        self.assertEqual((f.status, f.pr_url), (FeatureStatus.SHIPPED, PR_URL))

    def test_merged_but_issue_left_open_is_in_review(self):
        self.push(StubGitHub([self.item(prs=[pr(state="MERGED")])]))
        self.assertEqual(self.feat().status, FeatureStatus.IN_REVIEW)

    def test_closed_unmerged_is_blocked_with_reason(self):
        self.push(StubGitHub([self.item(state="CLOSED", prs=[pr(state="CLOSED")])]))
        self.assertEqual(self.feat().status, FeatureStatus.BLOCKED)
        self.assertEqual(self.source.writes[0],
                         ("set_status", "FEAT-1", {"status": "Blocked",
                                                   "reason": f"issue closed unmerged: {ISSUE}"}))

    def test_hold_is_blocked_with_reason(self):
        self.push(StubGitHub([self.item(labels=["hold"], prs=[pr()])]))
        self.assertEqual(self.feat().status, FeatureStatus.BLOCKED)
        self.assertEqual(self.source.writes[0][2]["reason"], f"on hold: {ISSUE}")

    def test_unblocks_when_hold_comes_off(self):
        self.push(StubGitHub([self.item(labels=["hold"])]))
        self.push(StubGitHub([self.item()]))
        self.assertEqual(self.feat().status, FeatureStatus.IN_PROGRESS)

    def test_feature_without_issue_under_goal(self):
        self.push(StubGitHub([self.item()]))
        self.assertIn("  FEAT-3: no issue under the Goal", self.lines)
        # A Draft's name never reaches the output (#943).
        self.assertNotIn("Weekly meal plan", "\n".join(self.lines))
        self.assertEqual(self.feat("FEAT-4"), FakeSource(FIXTURE)._features["FEAT-4"])

    def test_other_sub_issues_are_ignored(self):
        other = Item("https://github.com/acme/productswarm/issues/5", "OPEN", "No snapshot.")
        self.push(StubGitHub([other, self.item(prs=[pr()])]))
        self.assertEqual(self.feat().status, FeatureStatus.IN_REVIEW)


class SplitFeatureTest(Base):
    def child(self, n, **kw):
        return self.item(url=f"https://github.com/{REPO}/issues/{n}", **kw)

    def test_slowest_child_wins(self):
        self.push(StubGitHub([self.child(101, state="CLOSED", prs=[pr(120, "MERGED")]),
                              self.child(102, prs=[pr(121)]),
                              self.child(103)]))
        self.assertEqual(self.feat().status, FeatureStatus.IN_PROGRESS)

    def test_in_review_before_shipped(self):
        self.push(StubGitHub([self.child(101, state="CLOSED", prs=[pr(120, "MERGED")]),
                              self.child(102, prs=[pr(121)])]))
        f = self.feat()
        self.assertEqual((f.status, f.pr_url),
                         (FeatureStatus.IN_REVIEW, f"https://github.com/{REPO}/pull/121"))

    def test_all_shipped(self):
        self.push(StubGitHub([self.child(101, state="CLOSED", prs=[pr(120, "MERGED")]),
                              self.child(102, state="CLOSED", prs=[pr(121, "MERGED")])]))
        self.assertEqual(self.feat().status, FeatureStatus.SHIPPED)

    def test_any_blocked_child_blocks(self):
        self.push(StubGitHub([self.child(101, state="CLOSED", prs=[pr(120, "MERGED")]),
                              self.child(102, labels=["hold"])]))
        f = self.feat()
        self.assertEqual(f.status, FeatureStatus.BLOCKED)
        self.assertEqual(self.source.writes[0][2]["reason"],
                         f"on hold: https://github.com/{REPO}/issues/102")


class IdempotenceTest(Base):
    def merged_gh(self):
        return StubGitHub([self.item(state="CLOSED",
                                     prs=[pr(state="MERGED", reviews=[review("APPROVED")])])])

    def test_second_run_writes_nothing_even_with_log_deleted(self):
        gh = self.merged_gh()
        self.push(gh, {"FEAT-1": "Recipes save from a link."})
        self.assertEqual([w[0] for w in self.source.writes],
                         ["set_status", "set_links", "comment"])
        self.source.dump(self.fixture)
        events.path().unlink()
        again = FakeSource(self.fixture)
        results = self.push(gh, {"FEAT-1": "Recipes save from a link."}, source=again)
        self.assertEqual(again.writes, [])
        self.assertEqual(dict((r.feature_id, r.writes) for r in results)["FEAT-1"], [])
        self.assertEqual(self.line(), "  FEAT-1 Save a recipe from a link: unchanged")
        self.assertEqual(len(again.comments("FEAT-1")), 1)
        self.assertFalse(events.path().exists())

    def test_writes_are_logged(self):
        self.push(self.merged_gh(), {"FEAT-1": "Recipes save from a link."})
        got = [(e["kind"], e["what"], e["goal"], e["feature"]) for e in events.read()]
        self.assertEqual(got, [("write", "status", REF, "FEAT-1"),
                               ("write", "links", REF, "FEAT-1"),
                               ("write", "comment", REF, "FEAT-1")])
        self.assertEqual(events.read()[2]["pr"], 120)


class DeliveryCommentTest(Base):
    def test_comment_carries_pr_verdict_and_paragraph_once(self):
        gh = StubGitHub([self.item(state="CLOSED", prs=[pr(state="MERGED", reviews=[
            review("CHANGES_REQUESTED", commit="b" * 40), review("APPROVED"),
            review("COMMENTED", author="someone")])])])
        self.push(gh, {"FEAT-1": "Pasting a recipe link now saves it."})
        comments = self.source.comments("FEAT-1")
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["marker"], "swarm:pr=120")
        self.assertEqual(comments[0]["body"],
                         f"Shipped in {PR_URL}.\n\n"
                         f"Reviewer verdict at the merged head ({HEAD[:12]}): approved.\n\n"
                         "Pasting a recipe link now saves it.\n\n"
                         f"-- lead ({MODEL})")
        self.assertIn("delivery comment for PR #120", self.line())
        self.push(gh, {"FEAT-1": "Pasting a recipe link now saves it."})
        self.assertEqual(len(self.source.comments("FEAT-1")), 1)

    def test_no_review_at_head(self):
        gh = StubGitHub([self.item(state="CLOSED", prs=[pr(state="MERGED", reviews=[
            review("APPROVED", commit="b" * 40)])])])
        self.push(gh, {"FEAT-1": "It ships."})
        self.assertIn("): no review at head.", self.source.comments("FEAT-1")[0]["body"])

    def test_merged_without_paragraph_is_listed_and_gets_no_comment(self):
        gh = StubGitHub([self.item(state="CLOSED", prs=[pr(state="MERGED")])])
        results = self.push(gh)
        self.assertEqual(self.source.comments("FEAT-1"), [])
        self.assertEqual(results[0].waiting, [120])
        self.assertIn("PR #120 merged, delivery comment waiting on the lead's paragraph "
                      "(--what-shipped FEAT-1=<text>)", self.line())
        # Status and links still go.
        self.assertEqual(self.feat().status, FeatureStatus.SHIPPED)

    def test_paragraph_for_unknown_feature_is_refused(self):
        with self.assertRaisesRegex(sync.Refused, "FEAT-9"):
            self.push(StubGitHub([self.item()]), {"FEAT-9": "x"})
        self.assertEqual(self.source.writes, [])

    def test_parse_what_shipped(self):
        self.assertEqual(push.parse_what_shipped(["FEAT-1= It ships. ", "FEAT-2=a=b"]),
                         {"FEAT-1": "It ships.", "FEAT-2": "a=b"})
        for bad in (["FEAT-1"], ["FEAT-1="], ["feat-1=x"], ["FEAT-1=a", "FEAT-1=b"]):
            with self.assertRaises(ValueError):
                push.parse_what_shipped(bad)


class DryRunTest(Base):
    def test_dry_run_writes_nothing(self):
        gh = StubGitHub([self.item(state="CLOSED", prs=[pr(state="MERGED")])])
        before = self.fixture.read_text()
        results = self.push(gh, {"FEAT-1": "It ships."}, dry_run=True)
        self.assertEqual(self.source.writes, [])
        self.assertEqual(self.feat().status, FeatureStatus.IN_PROGRESS)
        self.assertEqual(self.source.comments("FEAT-1"), [])
        self.assertFalse(events.path().exists())
        self.assertEqual(self.fixture.read_text(), before)
        self.assertIn("dry run", self.lines[0])
        self.assertTrue(self.line().startswith(
            "  FEAT-1 Save a recipe from a link: would write status In progress → Shipped"))
        self.assertEqual(len(results[0].writes), 3)


class RefusalTest(Base):
    def test_goal_checks_as_pull(self):
        with self.assertRaisesRegex(sync.Refused, "opened by someone"):
            self.push(StubGitHub([self.item()], node=goal_node(author="someone")))
        with self.assertRaisesRegex(sync.Refused, "no 'Spec source"):
            self.push(StubGitHub([self.item()], node=goal_node(body="Outcome.\n")))
        self.assertEqual(self.lines, [])

    def test_unreadable_snapshot_stops_before_any_write(self):
        good = self.item(prs=[pr()])
        bad = Item("https://github.com/acme/productswarm/issues/9", "OPEN",
                   good.body + "\n" + good.body)
        with self.assertRaisesRegex(sync.Refused, "issues/9's snapshot block"):
            self.push(StubGitHub([good, bad]))
        self.assertEqual(self.source.writes, [])

    def test_too_many_sub_issues(self):
        class Gh(StubGitHub):
            def sub_issues(self, repo, n):
                raise ValueError("the Goal has 150 sub-issues; push reads at most 100")
        with self.assertRaisesRegex(sync.Refused, "150 sub-issues"):
            self.push(Gh())


class GraphQLTest(unittest.TestCase):
    def test_items_from_graphql(self):
        node = {"subIssues": {"totalCount": 1, "nodes": [{
            "url": ISSUE, "state": "CLOSED", "body": "b",
            "labels": {"nodes": [{"name": "hold"}]},
            "closedByPullRequestsReferences": {"totalCount": 1, "nodes": [{
                "number": 120, "url": PR_URL, "state": "MERGED", "headRefOid": HEAD,
                "reviews": {"nodes": [{"author": {"login": "productswarm-reviewer",
                                                  "__typename": "Bot"},
                                       "state": "APPROVED", "commit": {"oid": HEAD}}]}}]}}]}}
        self.assertEqual(push.items_from_graphql(node), [
            Item(ISSUE, "CLOSED", "b", ("hold",), (pr(state="MERGED",
                                                        reviews=[review("APPROVED")]),))])

    def test_truncated_pages_raise(self):
        with self.assertRaisesRegex(ValueError, "150 sub-issues"):
            push.items_from_graphql({"subIssues": {"totalCount": 150, "nodes": []}})
        node = {"subIssues": {"totalCount": 1, "nodes": [{
            "url": ISSUE, "state": "OPEN",
            "closedByPullRequestsReferences": {"totalCount": 11, "nodes": []}}]}}
        with self.assertRaisesRegex(ValueError, "closing PRs"):
            push.items_from_graphql(node)
        self.assertEqual(push.items_from_graphql(None), [])


if __name__ == "__main__":
    unittest.main()
