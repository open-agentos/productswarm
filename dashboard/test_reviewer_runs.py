"""Tests for dashboard/reviewer_runs.py (#356). Run: python3 -m unittest discover -s dashboard

Canned API data, and a fake `gh` on PATH for fetch(); the fake refuses any logs endpoint.
"""
import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import generate as g  # noqa: E402
import reviewer_runs as rr  # noqa: E402

REPO = "open-agentos/productswarm"
NOW = dt.datetime(2026, 11, 4, 12, 0, tzinfo=dt.timezone.utc)
A, B, C = "a" * 40, "b" * 40, "c" * 40


def ts(minutes_ago: float) -> str:
    return (NOW - dt.timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(i, event="schedule", actor="mattmcalister", minutes_ago=10, conclusion="success"):
    return {"id": i, "event": event, "created_at": ts(minutes_ago), "status": "completed",
            "conclusion": conclusion, "html_url": f"https://x/runs/{i}",
            "actor": {"login": actor}, "triggering_actor": {"login": actor}}


def job(name, conclusion="success", status="completed"):
    return {"name": name, "status": status, "conclusion": conclusion, "html_url": f"https://x/job/{name}"}


def review(sha, minutes_ago, login="productswarm-reviewer[bot]", state="APPROVED"):
    return {"user": {"login": login}, "commit_id": sha, "submitted_at": ts(minutes_ago), "state": state}


def commit(sha, minutes_ago):
    return {"sha": sha, "commit": {"committer": {"date": ts(minutes_ago)}}}


def model(runs, jobs, reviews=None, commits=None, unreviewed=()):
    return rr.build({"runs": runs, "jobs": jobs, "reviews": reviews or {}, "commits": commits or {}},
                    list(unreviewed), NOW)


def page(m):
    return rr.render(m, REPO, NOW, g.ago, g.stamp)


class StartedByTest(unittest.TestCase):
    def test_each_way_a_run_starts(self):
        self.assertEqual(rr.started_by(run(1, "schedule", "github-actions[bot]")), "schedule")
        self.assertEqual(rr.started_by(run(2, "workflow_dispatch", "github-actions[bot]")), "nudge")
        self.assertEqual(rr.started_by(run(3, "workflow_dispatch", "mattmcalister")),
                         "manual (mattmcalister)")
        # The triggering actor decides: a re-run by a person of a nudged run is manual.
        r = {**run(4, "workflow_dispatch", "github-actions[bot]"),
             "triggering_actor": {"login": "mattmcalister"}}
        self.assertEqual(rr.started_by(r), "manual (mattmcalister)")


class SweepTest(unittest.TestCase):
    def test_reviewed_jobs_and_nothing_to_review(self):
        m = model([run(1, minutes_ago=20), run(2, minutes_ago=5)],
                  {1: [job("plan"), job(f"review #7 {A}")], 2: [job("plan")]})
        newest, older = m["sweeps"]
        self.assertEqual(newest["reviewed"], [])
        self.assertEqual([(j["pr"], j["head"]) for j in older["reviewed"]], [(7, A)])
        html = page(m)
        self.assertIn("nothing to review", html)
        self.assertIn(f"https://github.com/{REPO}/pull/7", html)
        self.assertIn("schedule", html)

    def test_failed_review_job_counts_against_rate_and_is_listed(self):
        m = model([run(1, conclusion="failure")],
                  {1: [job("plan"), job(f"review #7 {A}"), job(f"review #8 {B}", "failure"),
                       job(f"review #9 {C}", None, "in_progress")]})
        self.assertEqual((m["jobs_ok"], m["jobs_done"]), (1, 2))   # in progress isn't counted
        self.assertEqual([(j["pr"], j["outcome"]) for j in m["failed"]], [(8, "failure")])
        html = page(m)
        self.assertIn("1 of 2 review jobs succeeded", html)
        self.assertIn("Failed: <a href=\"https://x/job/review #8", html)

    def test_plan_failure_without_review_jobs_isnt_nothing_to_review(self):
        html = page(model([run(1, conclusion="failure")], {1: [job("plan", "failure")]}))
        self.assertIn("no review jobs", html)
        self.assertNotIn("nothing to review", html)


class TimeTest(unittest.TestCase):
    def test_commit_to_review_median_and_longest(self):
        reviews = {7: [review(A, 50), review(A, 10)],    # second review of A doesn't count again
                   8: [review(B, 30)],
                   9: [review(C, 40, login="mattmcalister")]}   # not the reviewer App
        commits = {7: [commit(A, 60)], 8: [commit(B, 90)], 9: [commit(C, 45)]}
        m = model([], {}, reviews, commits)
        self.assertEqual(sorted(t["seconds"] for t in m["times"]), [600, 3600])
        self.assertEqual(m["median"], 2100)
        self.assertEqual((m["longest"]["pr"], m["longest"]["seconds"]), (8, 3600))
        self.assertIn("median 35m, longest 1h 0m", page(m))

    def test_review_on_older_head_times_that_head_not_the_current_one(self):
        # PR 7: reviewed at A, then B pushed and not reviewed.
        reviews = {7: [review(A, 50)]}
        commits = {7: [commit(A, 60), commit(B, 20)]}
        times = model([], {}, reviews, commits)["times"]
        self.assertEqual([(t["head"], t["seconds"]) for t in times], [(A, 600)])
        # and generate's rule still calls the current head unreviewed
        rv = g.reviewer_state(reviews[7], B)
        pr = {"number": 7, "author": "app/productswarm-builder", "head": B, "reviewer": rv}
        self.assertEqual(g.unreviewed(pr), f"no reviewer review at {B[:7]}")
        html = page(model([], {}, reviews, commits, unreviewed=[pr]))
        self.assertIn("1 builder PR with no reviewer review at its head", html)

    def test_reviews_before_the_window_dont_count(self):
        old = 8 * 24 * 60
        m = model([], {}, {7: [review(A, old)]}, {7: [commit(A, old + 5)]})
        self.assertEqual(m["times"], [])
        self.assertIn("no reviewer reviews in the window", page(m))

    def test_duration(self):
        self.assertEqual([rr.duration(s) for s in (5, 120, 3720, 90000)], ["5s", "2m", "1h 2m", "1d 1h"])


FAKE_GH = r"""#!/usr/bin/env python3
import json, os, sys
a = sys.argv[1:]
if a[:2] == ["api", "graphql"]:
    with open(os.environ["FAKE_GH_LOG"], "a") as f:
        f.write("graphql\n")
    print(json.dumps(json.load(open(os.environ["FAKE_GH_DATA"])).get("graphql", {})))
    sys.exit(0)
path = next(x for x in a[1:] if not x.startswith("-") and "/" in x)
with open(os.environ["FAKE_GH_LOG"], "a") as f:
    f.write(path + "\n")
if "/logs" in path:
    sys.exit("fake gh: logs endpoint refused")
data = json.load(open(os.environ["FAKE_GH_DATA"]))
if "error" in data:
    sys.stderr.write(data["error"]); sys.exit(1)
items = data.get(path.split("?")[0], [])
for item in items:
    print(json.dumps(item))
"""


class FetchTest(unittest.TestCase):
    def fetch(self, data, reviews=None):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "gh").write_text(FAKE_GH)
            (d / "gh").chmod(0o755)
            (d / "data.json").write_text(json.dumps(data))
            env = {"PATH": f"{d}{os.pathsep}{os.environ['PATH']}",
                   "FAKE_GH_DATA": str(d / "data.json"), "FAKE_GH_LOG": str(d / "log")}
            old = {k: os.environ.get(k) for k in env}
            os.environ.update(env)
            try:
                out = rr.fetch(REPO, NOW, reviews or {})
            finally:
                for k, v in old.items():
                    os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
            log = (d / "log").read_text().splitlines() if (d / "log").exists() else []
        return out, log

    def test_reads_runs_jobs_reviews_and_commits_but_no_logs(self):
        base = f"repos/{REPO}"
        out, log = self.fetch({
            f"{base}/actions/workflows/reviewer.yml/runs": [run(1)],
            f"{base}/actions/runs/1/jobs": [job("plan"), job(f"review #7 {A}")],
            "graphql": {"data": {"repository": {"p7": {
                "reviews": {"totalCount": 1, "nodes": [
                    {"author": {"login": "productswarm-reviewer", "__typename": "Bot"},
                     "commit": {"oid": A}, "submittedAt": ts(5), "state": "APPROVED"}]},
                "commits": {"totalCount": 1, "nodes": [{"commit": {"oid": A, "committedDate": ts(15)}}]},
            }}}},
        }, reviews={8: []})
        self.assertNotIn("error", out)
        self.assertEqual(set(out["reviews"]), {7, 8})       # open PR 8's reviews reused, not re-read
        self.assertEqual(out["reviews"][7], [review(A, 5)])  # GraphQL's Bot login gets REST's [bot]
        self.assertEqual(list(out["commits"]), [7])          # no reviewer review on 8: no commit read
        self.assertFalse(any("/logs" in p for p in log), log)
        self.assertFalse(any("pulls/" in p for p in log), log)   # one GraphQL query, no REST per PR
        self.assertEqual(log.count("graphql"), 1)
        self.assertEqual(model(out["runs"], out["jobs"], out["reviews"], out["commits"])["times"][0]["seconds"], 600)

    def test_pr_with_over_100_reviews_falls_back_to_rest(self):
        base = f"repos/{REPO}"
        out, log = self.fetch({
            f"{base}/actions/workflows/reviewer.yml/runs": [run(1)],
            f"{base}/actions/runs/1/jobs": [job(f"review #7 {A}")],
            "graphql": {"data": {"repository": {"p7": {
                "reviews": {"totalCount": 101, "nodes": []},
                "commits": {"totalCount": 0, "nodes": []}}}}},
            f"{base}/pulls/7/reviews": [review(A, 5)],
        })
        self.assertEqual(out["reviews"][7], [review(A, 5)])
        paths = [x.split("?")[0] for x in log]
        self.assertIn(f"{base}/pulls/7/reviews", paths)
        self.assertNotIn(f"{base}/pulls/7/commits", paths)

    def test_refuses_a_logs_path(self):
        with self.assertRaises(ValueError):
            rr._gh(f"repos/{REPO}/actions/runs/1/logs", ".", False)

    def test_token_without_actions_read_degrades(self):
        out, _ = self.fetch({"error": "gh: Resource not accessible by integration (HTTP 403)"})
        self.assertEqual(out, {"error": rr.NO_ACTIONS})
        html = page(rr.build(out, [], NOW))
        self.assertIn("can&#x27;t read Actions runs: the token needs `actions: read`", html)
        self.assertIn("0 builder PRs with no reviewer review", html)

    def test_page_still_builds_without_actions(self):
        m = g.build({"repo": REPO, "issues": [], "comments": {}, "prs": [],
                     "actions": {"error": rr.NO_ACTIONS}}, NOW, dt.timedelta(minutes=15))
        html = g.render(m)
        self.assertIn("<h2>Actions reviewer</h2>", html)
        self.assertIn("actions: read", html)
        self.assertNotIn("cost", html.split("<h2>Actions reviewer</h2>")[1].split("<h2>")[0]
                         .replace("No cost is shown", ""))


if __name__ == "__main__":
    unittest.main()
