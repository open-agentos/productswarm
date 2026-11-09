"""Tests for staying inside the API rate limit (#392). Run: python3 -m unittest discover -s dashboard

The spacing skip for nudged rebuilds, the low-allowance exit (page and digest), the batched
GraphQL reads, and the call count of one rebuild against canned data through a fake `gh`
that logs every call. Nothing touches GitHub.
"""
import contextlib
import datetime as dt
import io
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import digest as d  # noqa: E402
import generate as g  # noqa: E402
import ghql  # noqa: E402

REPO = "open-agentos/productswarm"
NOW = dt.datetime(2026, 11, 4, 21, 0, tzinfo=dt.timezone.utc)
SHA = "a" * 40
NUDGE = {"GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_TRIGGERING_ACTOR": "github-actions[bot]"}


def ts(minutes_ago: float) -> str:
    return (NOW - dt.timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def limits(core=1000, graphql=1000):
    return {"resources": {"core": {"limit": 1000, "remaining": core, "reset": 1793830131},
                          "graphql": {"limit": 1000, "remaining": graphql, "reset": 1793830131}}}


def runs(*ids):
    """The newest successful dashboard.yml runs, newest first."""
    return {"workflow_runs": [{"id": i, "updated_at": ts(1)} for i in ids]}


def jobs(published_minutes_ago=None):
    """One run's jobs: deployed that long ago, or (None) a run that skipped and didn't deploy."""
    deploy = ({"name": "Run actions/deploy-pages@368f825", "conclusion": "success",
               "completed_at": ts(published_minutes_ago)} if published_minutes_ago is not None
              else {"name": "Run actions/deploy-pages@368f825", "conclusion": "skipped", "completed_at": None})
    return {"jobs": [{"name": "publish", "conclusion": "success",
                      "steps": [{"name": "Generate", "conclusion": "success"}, deploy]}]}


class SpacingTest(unittest.TestCase):
    def test_only_a_nudge_dispatch_counts_as_nudged(self):
        self.assertTrue(g.nudged(NUDGE))
        self.assertTrue(g.nudged({"GITHUB_EVENT_NAME": "workflow_dispatch",
                                  "GITHUB_ACTOR": "github-actions[bot]"}))
        self.assertFalse(g.nudged({**NUDGE, "GITHUB_TRIGGERING_ACTOR": "mattmcalister"}))
        self.assertFalse(g.nudged({**NUDGE, "GITHUB_EVENT_NAME": "schedule"}))
        self.assertFalse(g.nudged({}))

    def test_skip_when_last_publish_is_recent(self):
        with mock.patch.object(g, "gh_json", side_effect=[runs(7), jobs(2)]) as gh:
            self.assertIn("last published 2m ago", g.too_soon(REPO, NOW))
        self.assertEqual(gh.call_count, 2)
        self.assertIn("actions/workflows/dashboard.yml/runs?status=success&per_page=5", gh.call_args_list[0][0][1])
        self.assertIn("actions/runs/7/jobs", gh.call_args_list[1][0][1])

    def test_skipped_runs_do_not_restart_the_wait(self):
        # The two newest successes skipped (their deploy step was skipped); the last publish was
        # 6 minutes ago, so this nudge rebuilds rather than skipping against a skip.
        with mock.patch.object(g, "gh_json", side_effect=[runs(9, 8, 7), jobs(), jobs(), jobs(6)]) as gh:
            self.assertIsNone(g.too_soon(REPO, NOW))
        self.assertEqual(gh.call_count, 4)
        with mock.patch.object(g, "gh_json", side_effect=[runs(9, 8), jobs(), jobs(3)]):
            self.assertIn("last published 3m ago", g.too_soon(REPO, NOW))

    def test_runs_when_nothing_published_recently_or_unreadable(self):
        for answers in ([runs(7), jobs(6)], [runs()], [runs(1, 2, 3, 4, 5)] + [jobs()] * 5):
            with mock.patch.object(g, "gh_json", side_effect=answers):
                self.assertIsNone(g.too_soon(REPO, NOW))
        with mock.patch.object(g, "gh_json", side_effect=RuntimeError("HTTP 403")):
            self.assertIsNone(g.too_soon(REPO, NOW))
        with mock.patch.object(g, "gh_json", side_effect=[runs(7), RuntimeError("HTTP 403")]):
            self.assertIsNone(g.too_soon(REPO, NOW))


class MainSkipTest(unittest.TestCase):
    """main() exits 0 without writing the page and without fetching anything."""

    def main(self, env, gh_answers):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "index.html"
            buf = io.StringIO()
            with mock.patch.dict(os.environ, env, clear=False), \
                    mock.patch.object(g, "gh_json", side_effect=gh_answers), \
                    mock.patch.object(g, "fetch", side_effect=AssertionError("fetched")) as fetch, \
                    contextlib.redirect_stdout(buf):
                for k in ("GITHUB_EVENT_NAME", "GITHUB_TRIGGERING_ACTOR", "GITHUB_ACTOR"):
                    if k not in env:
                        os.environ.pop(k, None)
                try:
                    rc = g.main(["--repo", REPO, "--out", str(out)])
                except AssertionError:
                    rc = "fetched"
            return rc, out.exists(), buf.getvalue(), fetch.call_count

    def test_nudge_soon_after_a_rebuild_skips(self):
        stamp = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        recent = {"jobs": [{"steps": [{"name": "Run actions/deploy-pages@368f825", "conclusion": "success",
                                       "completed_at": stamp}]}]}
        rc, written, printed, fetched = self.main(NUDGE, [runs(7), recent])
        self.assertEqual((rc, written, fetched), (0, False, 0))
        self.assertEqual(printed.count("\n"), 1)
        self.assertIn("skipped, not published", printed)

    def test_manual_dispatch_never_checks_spacing(self):
        # The only gh call is rate_limit; a low one proves the spacing call never happened.
        rc, written, printed, _ = self.main({**NUDGE, "GITHUB_TRIGGERING_ACTOR": "mattmcalister"},
                                            [limits(core=10)])
        self.assertEqual((rc, written), (0, False))
        self.assertIn("core API allowance low (10 of 1000 left", printed)

    def test_low_graphql_allowance_skips(self):
        rc, written, printed, fetched = self.main({}, [limits(graphql=3)])
        self.assertEqual((rc, written, fetched), (0, False, 0))
        self.assertIn("graphql API allowance low (3 of 1000 left", printed)

    def test_enough_allowance_fetches(self):
        rc, *_ = self.main({}, [limits()])
        self.assertEqual(rc, "fetched")

    def test_unreadable_rate_limit_goes_ahead(self):
        rc, *_ = self.main({}, RuntimeError("gh api rate_limit failed"))
        self.assertEqual(rc, "fetched")


class DigestSkipTest(unittest.TestCase):
    def test_update_with_low_allowance_exits_0_without_reading_or_writing(self):
        buf = io.StringIO()
        with mock.patch.object(g, "gh_json", side_effect=[limits(core=5)]), \
                mock.patch.object(g, "fetch", side_effect=AssertionError("fetched")), \
                mock.patch.object(d, "update", side_effect=AssertionError("edited")), \
                contextlib.redirect_stdout(buf):
            rc = d.main(["--update", "--repo", REPO])
        self.assertEqual(rc, 0)
        self.assertIn("digest.py: skipped, not edited: core API allowance low", buf.getvalue())


# ---------------------------------------------------------------- call count of one rebuild

FAKE_GH = r"""#!/usr/bin/env python3
import json, os, re, sys
a = sys.argv[1:]
data = json.load(open(os.environ["FAKE_GH_DATA"]))
with open(os.environ["FAKE_GH_LOG"], "a") as f:
    f.write(json.dumps(a) + "\n")
if a[:2] == ["api", "graphql"]:
    q = next(x for x in a if x.startswith("query="))
    repo = {}
    for n in map(int, re.findall(r"\bi(\d+): issue\(", q)):
        cs = data["comments"].get(str(n), [])
        repo[f"i{n}"] = {"comments": {"totalCount": len(cs), "nodes": cs}}
    for n in map(int, re.findall(r"\bp(\d+): pullRequest\(", q)):
        repo[f"p{n}"] = {"reviews": {"totalCount": 0, "nodes": []},
                         "commits": {"totalCount": 0, "nodes": []}}
    print(json.dumps({"data": {"repository": repo}}))
elif a[:2] == ["api", "rate_limit"]:
    print(json.dumps(data["rate_limit"]))
elif a[:2] == ["pr", "list"]:
    print(json.dumps(data["prs"]))
elif a[:2] == ["issue", "view"]:
    print("{}")
elif a[:1] == ["api"]:
    path = next(x for x in a[1:] if not x.startswith("-") and "/" in x)
    key = "open" if "state=open" in path else "closed" if "state=closed" in path else path.split("?")[0]
    items = data.get(key, [])
    jq = a[a.index("--jq") + 1] if "--jq" in a else None
    if jq is None:
        print(json.dumps(items))
    else:
        for item in items:
            print(json.dumps(item))
else:
    sys.exit(1)
"""


def tracking(n):
    return {"number": n, "title": f"[heartbeat] builder s{n}", "state": "open",
            "user": {"login": "productswarm-builder[bot]"}, "labels": [], "html_url": f"https://x/{n}",
            "created_at": ts(60),
            "body": f"<!-- productswarm-heartbeat schema_version=1 session_id=s{n} -->\n"}


def gql_comment(n, login="productswarm-builder", typename="Bot"):
    ev = {"schema_version": 1, "ts": ts(5), "session_id": f"s{n}", "repo": REPO, "role": "builder",
          "model": "claude-opus-5-5", "event": "working_on", "issue": 1}
    return {"author": {"login": login, "__typename": typename},
            "body": f"```jsonl\n{json.dumps(ev)}\n```\n"}


class CallCountTest(unittest.TestCase):
    SESSIONS = 60
    RUNS = 15
    OPEN_PRS = 3
    QUESTIONS = 30

    def rebuild(self):
        base = f"repos/{REPO}"
        runs_ = [{"id": i, "event": "schedule", "created_at": ts(i), "status": "completed",
                  "conclusion": "success", "html_url": f"https://x/runs/{i}",
                  "actor": {"login": "x"}, "triggering_actor": {"login": "x"}}
                 for i in range(1, self.RUNS + 1)]
        data = {
            "open": [tracking(n) for n in range(100, 100 + self.SESSIONS)],
            "closed": [],
            "comments": {str(n): [gql_comment(n)] for n in range(100, 100 + self.SESSIONS)},
            "prs": [{"number": 500 + i, "title": "p", "url": "u", "author": {"login": "app/productswarm-builder"},
                     "isDraft": False, "createdAt": ts(30), "reviewDecision": "",
                     "closingIssuesReferences": [], "headRefOid": SHA} for i in range(self.OPEN_PRS)],
            "rate_limit": limits(),
            # #406's question history: QUESTIONS gov questions in the window, PRs merged.
            f"{base}/issues": [{"number": 600 + i, "title": "q", "state": "open",
                                "created_at": ts(60), "html_url": "u", "labels": []}
                               for i in range(self.QUESTIONS)],
            "search/issues": [{"number": 700, "pull_request": {"merged_at": ts(30)}}],
            f"{base}/actions/workflows/reviewer.yml/runs": runs_,
            **{f"{base}/actions/runs/{i}/jobs": [
                {"name": "plan", "status": "completed", "conclusion": "success", "html_url": "j"},
                {"name": f"review #{200 + i} {SHA}", "status": "completed", "conclusion": "success",
                 "html_url": "j"}] for i in range(1, self.RUNS + 1)},
        }
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "gh").write_text(FAKE_GH)
            (tmp / "gh").chmod(0o755)
            (tmp / "data.json").write_text(json.dumps(data))
            env = {"PATH": f"{tmp}{os.pathsep}{os.environ['PATH']}",
                   "FAKE_GH_DATA": str(tmp / "data.json"), "FAKE_GH_LOG": str(tmp / "log")}
            buf = io.StringIO()
            with mock.patch.dict(os.environ, env), contextlib.redirect_stdout(buf), \
                    contextlib.redirect_stderr(io.StringIO()), \
                    mock.patch.object(g.precedent, "published", return_value=None) as pub:
                for k in ("GITHUB_EVENT_NAME", "GITHUB_TRIGGERING_ACTOR", "GITHUB_ACTOR"):
                    os.environ.pop(k, None)
                rc = g.main(["--repo", REPO, "--out", str(tmp / "index.html")])
                page = (tmp / "index.html").read_text() if (tmp / "index.html").exists() else ""
            calls = [json.loads(ln) for ln in (tmp / "log").read_text().splitlines()]
        self.assertEqual(pub.call_count, 1)   # the Pages copy, not an API call
        return rc, page, calls

    def test_rebuild_call_count(self):
        rc, page, calls = self.rebuild()
        self.assertEqual(rc, 0)
        self.assertIn("s-active", page)   # the sessions came through the GraphQL comments
        rest = [c for c in calls if c[:2] not in (["api", "graphql"], ["api", "rate_limit"])
                and c[:2] != ["pr", "list"] and c[:2] != ["issue", "view"]]
        graphql = [c for c in calls if c[:2] == ["api", "graphql"]]
        queries = [next(x for x in c if x.startswith("query=")) for c in graphql]
        # 60 tracking issues: 3 GraphQL queries of 25, never one REST call per issue.
        self.assertEqual(sum(bool(re.search(r"\bi\d+: issue\(\w+: \d+\) { comments", q))
                             for q in queries), 3)
        self.assertFalse([c for c in rest if "/comments" in " ".join(c)
                          and "/comments?since=" not in " ".join(c)], rest)
        # Precedent (#408): one paginated read each of issue and review comments, and one
        # GraphQL query of PR reviews per 25 PRs in the window (none here). Grants in use
        # (#713): one read of the last 24 hours' issue comments, and no titles (no merger calls).
        self.assertEqual(len([c for c in rest if "/comments?since=" in " ".join(c)
                              and "/issues/249/" not in " ".join(c)]), 3)
        # Today's report (#712): one read of the report issue's last 4 days of comments.
        self.assertEqual(len([c for c in rest if f"repos/{REPO}/issues/249/comments?since=" in " ".join(c)]), 1)
        # The plan (#712): one query searching for Goals and Areas (none here, so no more).
        self.assertEqual(sum("type:Goal" in q and "type:Area" in q for q in queries), 1)
        # 15 reviewed PRs: one GraphQL query, no REST reviews or commits per PR. Open PRs'
        # reviews stay one REST call each (generate.fetch() needs their bodies).
        self.assertEqual(sum("pullRequest(" in q for q in queries), 1)
        self.assertEqual(len([c for c in rest if "/reviews" in " ".join(c)]), self.OPEN_PRS)
        self.assertFalse([c for c in rest if "/commits" in " ".join(c)], rest)
        # Runs: one list call, then one jobs call per run, at most MAX_RUNS.
        self.assertEqual(len([c for c in rest if "/jobs" in " ".join(c)]), self.RUNS)
        # #406's trends: one REST list of gov questions, one search for merged PRs, and one
        # GraphQL query per 25 questions for their label and close events.
        self.assertEqual(len([c for c in rest if "labels=gov:question" in " ".join(c)]), 1)
        self.assertEqual(len([c for c in rest if "search/issues" in " ".join(c)]), 1)
        self.assertEqual(sum("timelineItems(" in q for q in queries), 2)
        # #402's header: the repo's events, one page here (fewer than 100, so the last).
        self.assertEqual([c for c in rest if "/events?" in " ".join(c)],
                         [["api", f"repos/{REPO}/events?per_page=100&page=1"]])
        # The whole rebuild: 40 calls (30 before #406 added 4, #408 added 2, #402 added 1,
        # #712 added 2 and #713 added 1). On main before #392 the same data took 100.
        self.assertLessEqual(len(calls), 40, "\n".join(map(str, calls)))
        self.assertLess(len(rest), g.PAGE_NEEDS["core"])
        self.assertLess(len(graphql), g.PAGE_NEEDS["graphql"])

    def test_comment_authors_keep_rest_logins(self):
        nodes = [gql_comment(1), gql_comment(1, login="productswarm-builder", typename="User")]
        with mock.patch.object(g.ghql, "batched", return_value={1: {"comments": {"totalCount": 2, "nodes": nodes}}}):
            got = g.tracking_comments(REPO, [1])
        self.assertEqual([c["user"]["login"] for c in got[1]],
                         ["productswarm-builder[bot]", "productswarm-builder"])

    def test_issue_with_over_100_comments_or_missing_falls_back_to_rest(self):
        with mock.patch.object(g.ghql, "batched", return_value={
                1: {"comments": {"totalCount": 101, "nodes": [gql_comment(1)] * 100}}, 2: None}), \
                mock.patch.object(g, "gh_items", side_effect=lambda path: [path]) as items:
            got = g.tracking_comments(REPO, [1, 2])
        self.assertEqual(got, {1: [f"repos/{REPO}/issues/1/comments?per_page=100"],
                               2: [f"repos/{REPO}/issues/2/comments?per_page=100"]})
        self.assertEqual(items.call_count, 2)


class BatchedTest(unittest.TestCase):
    def gh(self, stdout, returncode=0):
        return mock.patch.object(ghql.subprocess, "run", return_value=mock.Mock(
            stdout=json.dumps(stdout), stderr="gh: Could not resolve", returncode=returncode))

    def test_partial_errors_keep_the_rest(self):
        # gh exits 1 when one alias errors; the other aliases' data still counts.
        with self.gh({"data": {"repository": {"p1": {"x": 1}, "p2": None}}, "errors": [{}]}, 1):
            self.assertEqual(ghql.batched(REPO, [1, 2], "p%d: pullRequest(number: %d) { x }", 20),
                             {1: {"x": 1}, 2: None})

    def test_no_data_raises(self):
        with self.gh({"errors": [{"message": "rate limited"}]}, 1), self.assertRaises(RuntimeError):
            ghql.batched(REPO, [1], "p%d: pullRequest(number: %d) { x }", 20)

    def test_batches_of_size(self):
        with self.gh({"data": {"repository": {}}}) as run:
            out = ghql.batched(REPO, list(range(1, 52)), "i%d: issue(number: %d) { x }", 25)
        self.assertEqual(run.call_count, 3)
        self.assertEqual(len(out), 51)
        self.assertIn("i26: issue(number: 26)", run.call_args_list[1][0][0][4])

    def test_bot_login(self):
        self.assertEqual(ghql.login({"login": "productswarm-reviewer", "__typename": "Bot"}),
                         "productswarm-reviewer[bot]")
        self.assertEqual(ghql.login({"login": "mattmcalister", "__typename": "User"}), "mattmcalister")
        self.assertEqual(ghql.login(None), "ghost")


class RedReviewsTest(unittest.TestCase):
    def test_rest_shape_and_over_100_left_for_rest(self):
        import progress
        node = {"author": {"login": "productswarm-reviewer", "__typename": "Bot"},
                "submittedAt": ts(5), "state": "CHANGES_REQUESTED", "body": "block 2"}
        with mock.patch.object(ghql, "batched", return_value={
                7: {"reviews": {"totalCount": 1, "nodes": [node]}},
                8: {"reviews": {"totalCount": 101, "nodes": [node] * 100}}, 9: None}):
            got = progress.red_reviews(REPO, [7, 8, 9])
        self.assertEqual(got, {7: [{"user": {"login": "productswarm-reviewer[bot]"}, "submitted_at": ts(5),
                                    "state": "CHANGES_REQUESTED", "body": "block 2"}]})

if __name__ == "__main__":
    unittest.main()
