"""Tests for evals/gather.py (#173). Canned `gh` JSON only; nothing calls GitHub.

Run: python3 -m unittest discover -s evals
"""
import json
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gather  # noqa: E402

HEAD, OLD = "a" * 40, "b" * 40
BOT = {"login": "productswarm-reviewer"}          # GraphQL shape (gh pr list/view)
BOT_REST = {"login": "productswarm-reviewer[bot]"}  # REST shape (gh api)
OWNER = {"login": "mattmcalister"}


class DoneWhen(unittest.TestCase):
    def test_heading_section_to_next_heading(self):
        body = ("## What\n\nThing.\n\n## Done when\n\n- `x` works.\n- tests pass.\n\n"
                "### Sub-point\n\nkept\n\n## Files\n\n`a.py`\n")
        self.assertEqual(gather.done_when(body),
                         "- `x` works.\n- tests pass.\n\n### Sub-point\n\nkept")

    def test_acceptance_heading(self):
        body = "## Scope\n\nA.\n\n### Acceptance criteria\n\n1. one\n2. two\n\n### Order\n\nlast\n"
        self.assertEqual(gather.done_when(body), "1. one\n2. two")

    def test_heading_last_section_drops_signature(self):
        body = "## Done when\n\n- it works.\n\n-- planner (claude-opus-5-5)\n"
        self.assertEqual(gather.done_when(body), "- it works.")

    def test_bold_label_with_list(self):
        body = ("Intro.\n**Done when:**\n- a\n- b\n\nBest taken after #75.\n\n"
                "-- planner (claude-opus-5-5)\n")
        self.assertEqual(gather.done_when(body), "**Done when:**\n- a\n- b")

    def test_bold_label_inline(self):
        body = "Context.\n\n**Done when:** the test checks it.\n\nFound while working on #113.\n"
        self.assertEqual(gather.done_when(body), "**Done when:** the test checks it.")

    def test_paragraph(self):
        body = "Build it.\n\nDone when a session produces events\nin the store.\n\nMore.\n"
        self.assertEqual(gather.done_when(body), "Done when a session produces events\nin the store.")

    def test_heading_wins_over_label(self):
        body = "**Done when:** old\n\n## Done when\n\nnew\n"
        self.assertEqual(gather.done_when(body), "new")

    def test_none(self):
        self.assertIsNone(gather.done_when("Log the rulings in PHASE0.md.\n\n-- planner (x)\n"))
        self.assertIsNone(gather.done_when(None))
        self.assertIsNone(gather.done_when("## Done when\n\n## Files\n"))

    def test_crlf(self):
        self.assertEqual(gather.done_when("## Done when\r\n\r\n- a\r\n"), "- a")


class GovIds(unittest.TestCase):
    def test_extracts_sorted_unique_from_pr_and_issue(self):
        self.assertEqual(
            gather.gov_ids("per GOV-0011 and GOV-0006.", "(GOV-0006, GOV-0012) see GOV-NNNN"),
            ["GOV-0006", "GOV-0011", "GOV-0012"])

    def test_none_and_word_boundaries(self):
        self.assertEqual(gather.gov_ids(None, "", "XGOV-0001 GOV-00012"), [])


def review(rid, state, commit, at, user=BOT_REST):
    return {"id": rid, "user": user, "state": state, "commit_id": commit, "submitted_at": at}


class Reviews(unittest.TestCase):
    def test_matches_merge_head_and_skips_other_reviewers(self):
        reviews = [review(2, "APPROVED", HEAD, "2026-11-02T10:00:00Z"),
                   review(1, "COMMENTED", OLD, "2026-11-01T10:00:00Z"),
                   review(3, "APPROVED", HEAD, "2026-11-02T11:00:00Z", user=OWNER)]
        out = gather.reviewer_reviews(reviews, [], HEAD)
        self.assertEqual([(r["id"], r["state"], r["at_merge_head"]) for r in out],
                         [(1, "COMMENTED", False), (2, "APPROVED", True)])

    def test_no_reviews(self):
        self.assertEqual(gather.reviewer_reviews([], [{"user": BOT_REST, "body": "Overstep: x"}], HEAD), [])

    def test_overstep_comments_attach_to_their_review(self):
        reviews = [review(1, "COMMENTED", OLD, "2026-11-01T10:00:00Z"),
                   review(2, "COMMENTED", HEAD, "2026-11-02T10:00:00Z")]
        comments = [
            # PR comments: belong to the first review at or after them
            {"id": 10, "user": BOT_REST, "body": "Overstep: chose a format (architecture).",
             "created_at": "2026-11-01T09:59:00Z", "html_url": "u10"},
            {"id": 11, "user": BOT_REST, "body": "Overstep: late one",
             "created_at": "2026-11-03T00:00:00Z", "html_url": "u11"},
            # inline comment: belongs to the review it names
            {"id": 12, "user": BOT_REST, "body": "Overstep: inline", "pull_request_review_id": 2,
             "created_at": "2026-11-01T09:00:00Z", "html_url": "u12"},
            # not oversteps, or not the reviewer
            {"id": 13, "user": BOT_REST, "body": "Nit: see Overstep: rule",
             "created_at": "2026-11-01T09:00:00Z"},
            {"id": 14, "user": OWNER, "body": "Overstep: from the owner",
             "created_at": "2026-11-01T09:00:00Z"},
        ]
        out = gather.reviewer_reviews(reviews, comments, HEAD)
        self.assertEqual([c["url"] for c in out[0]["overstep_comments"]], ["u10"])
        self.assertEqual([c["url"] for c in out[1]["overstep_comments"]], ["u12", "u11"])


def pr_row(n, merged="2026-11-01T00:00:00Z", closes=(1,), files=("launcher/x.py",), reviewed=False):
    return {"number": n, "mergedAt": merged,
            "closingIssuesReferences": [{"number": i} for i in closes],
            "files": [{"path": f} for f in files],
            "reviews": [{"author": BOT, "state": "COMMENTED"}] if reviewed else
                       [{"author": OWNER, "state": "COMMENTED"}]}


class Sampling(unittest.TestCase):
    def test_rule(self):
        rows = [
            pr_row(10, reviewed=True),                       # kept: reviewer reviewed it
            pr_row(11, closes=(47,)),                         # kept: v1 issue, no reviewer pass
            pr_row(12, closes=(53,)),                         # dropped: not v1, not reviewed
            pr_row(13, closes=(), reviewed=True),             # dropped: closes no issue
            pr_row(14, reviewed=True, files=("governance/decisions/GOV-0001-x.md",
                                              "governance/INDEX.md")),  # dropped: ruling PR
            pr_row(15, reviewed=True, files=("governance/PHASE0.md",)),  # kept: not a ruling
            pr_row(16, merged=None, reviewed=True),           # dropped: not merged
        ]
        self.assertEqual([p["number"] for p in gather.select_sample(rows)], [10, 11, 15])

    def test_cap_keeps_most_recent_sorted_by_number(self):
        rows = [pr_row(n, merged=f"2026-10-{n:02d}T00:00:00Z", reviewed=True) for n in range(1, 26)]
        rows.reverse()
        got = [p["number"] for p in gather.select_sample(rows, cap=20)]
        self.assertEqual(got, list(range(6, 26)))


class Record(unittest.TestCase):
    def test_record_shape(self):
        pr = {"number": 120, "title": "t", "mergedAt": "2026-11-02T00:00:00Z", "headRefOid": HEAD,
              "body": "Closes #113. Per GOV-0011.",
              "closingIssuesReferences": [{"number": 113}],
              "files": [{"path": "b.py"}, {"path": "a.py"}]}
        issue = {"number": 113, "title": "i", "body": "Needs GOV-0009.\n\n## Done when\n\n- x\n"}
        rec = gather.record(pr, issue, [review(1, "APPROVED", HEAD, "2026-11-01T00:00:00Z")], [])
        self.assertEqual(rec, {
            "number": 120, "title": "t", "merged_at": "2026-11-02T00:00:00Z", "head_sha": HEAD,
            "closed_issues": [113],
            "issue": {"number": 113, "title": "i", "done_when": "- x"},
            "gov_ids": ["GOV-0009", "GOV-0011"], "files": ["a.py", "b.py"],
            "reviews": [{"id": 1, "state": "APPROVED", "submitted_at": "2026-11-01T00:00:00Z",
                         "commit_id": HEAD, "at_merge_head": True, "overstep_comments": []}]})


class ReadOnly(unittest.TestCase):
    def test_refuses_writes(self):
        for args in (["pr", "merge", "1"], ["pr", "comment", "1", "-b", "x"],
                     ["issue", "edit", "1", "--add-label", "ready"], ["label", "create", "x"],
                     ["api", "-X", "POST", "repos/o/r/issues"], ["api", "--method=PATCH", "x"],
                     ["api", "repos/o/r/issues/1/labels", "-f", "labels[]=ready"],
                     ["api", "graphql", "-F", "query=mutation{}"], ["api", "x", "--input", "f"]):
            with self.assertRaises(gather.ReadOnlyError, msg=args):
                gather.check_read_only(args)

    def test_gather_makes_only_read_calls_and_writes_the_file(self):
        """A full run against canned gh output: every call is a read, the file is sorted."""
        calls = []
        pr = {"number": 7, "title": "t", "mergedAt": "2026-11-01T00:00:00Z", "headRefOid": HEAD,
              "body": "Closes #47", "closingIssuesReferences": [{"number": 47}],
              "files": [{"path": "launcher/x.py"}]}
        canned = {
            ("pr", "list"): [pr_row(9, reviewed=True), pr_row(7, closes=(47,))],
            ("pr", "view"): pr,
            ("issue", "view"): {"number": 47, "title": "i", "body": "## Done when\n\n- y\n"},
            ("api", "--paginate"): [[]],
        }

        def run(argv, **kw):
            self.assertEqual(argv[0], "gh")
            gather.check_read_only(argv[1:])
            calls.append(argv[1:])
            out = canned[tuple(argv[1:3])]
            if argv[1:3] == ["pr", "view"]:
                out = dict(out, number=int(argv[3]))
            return subprocess.CompletedProcess(argv, 0, json.dumps(out), "")

        fake = types.SimpleNamespace(run=run)
        with tempfile.TemporaryDirectory() as d, mock.patch.object(gather, "subprocess", fake), \
                mock.patch("sys.stderr"):
            out = Path(d) / "data" / "sample.json"
            self.assertEqual(gather.main(["--repo", "o/r", "--out", str(out)]), 0)
            data = json.loads(out.read_text())
        self.assertEqual([p["number"] for p in data["prs"]], [7, 9])
        self.assertEqual(data["prs"][0]["issue"]["done_when"], "- y")
        self.assertTrue(all(c[:2] in (["pr", "list"], ["pr", "view"], ["issue", "view"])
                            or c[0] == "api" for c in calls))


class Committed(unittest.TestCase):
    def test_committed_sample_is_sorted_and_complete(self):
        data = json.loads((HERE / "data" / "sample.json").read_text())
        nums = [p["number"] for p in data["prs"]]
        self.assertEqual(nums, sorted(nums))
        self.assertLessEqual(len(nums), gather.CAP)
        for p in data["prs"]:
            self.assertTrue(p["closed_issues"])
            self.assertEqual(len(p["head_sha"]), 40)


if __name__ == "__main__":
    unittest.main()
