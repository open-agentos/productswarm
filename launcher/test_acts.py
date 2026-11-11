"""Tests for launcher/acts.py and `swarm acts` (#771): the owner's acts per working day, kept
from webhook deliveries and read back from GitHub (M4 readiness checks 1 and 2)."""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import sqlite3
import sys
import tempfile
import time
import unittest
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import acts  # noqa: E402
import merger  # noqa: E402
import swarm  # noqa: E402
import webhooks  # noqa: E402

UTC = dt.timezone.utc
SECRET = b"s3cret"
OWNER = "mattmcalister"
BOT = "productswarm-planner[bot]"
REPO = "o/r"
REPORT = 249
NOW = dt.datetime(2026, 11, 11, 18, 0, tzinfo=UTC)          # a Wednesday
SESSION = '[[session]]\nrole = "builder"\nmodel = "m"\n\n'
SECRET_BODY = "a private body that must never be stored"
ALWAYS = (dt.datetime(2026, 1, 1, tzinfo=UTC), dt.datetime(2027, 1, 1, tzinfo=UTC))


def user(login):
    return {"login": login}


def issue(n, type_=None, labels=(), by=OWNER, at="2026-11-11T09:00:00Z"):
    return {"number": n, "type": {"name": type_} if type_ else None, "user": user(by),
            "labels": [{"name": x} for x in labels], "created_at": at, "body": SECRET_BODY,
            "html_url": f"https://github.com/{REPO}/issues/{n}"}


# GitHub's side, as `gh api` returns it.
ISSUES = {249: issue(249, "Task", by=BOT), 686: issue(686, "Goal", at="2026-11-11T08:00:00Z"),
          800: issue(800, "Task", at="2026-11-11T09:30:00Z"), 801: issue(801, "Task", ["gov:question"], by=BOT),
          802: issue(802, "Task", by=BOT), 900: issue(900, by=BOT), 901: issue(901, by=BOT)}
COMMENTS = {
    11: {"user": user(OWNER), "created_at": "2026-11-11T10:00:00Z", "body": SECRET_BODY,
         "html_url": f"https://github.com/{REPO}/issues/249#issuecomment-11"},
    12: {"user": user(OWNER), "created_at": "2026-11-11T10:05:00Z", "body": SECRET_BODY,
         "html_url": f"https://github.com/{REPO}/issues/801#issuecomment-12"},
    13: {"user": user(OWNER), "created_at": "2026-11-11T10:10:00Z", "body": SECRET_BODY,
         "html_url": f"https://github.com/{REPO}/issues/686#issuecomment-13"},
    14: {"user": user(OWNER), "created_at": "2026-11-10T16:00:00Z", "body": SECRET_BODY,
         "html_url": f"https://github.com/{REPO}/issues/802#issuecomment-14"},
}
EVENTS = {
    800: [{"id": 501, "event": "labeled", "label": {"name": "ready"}, "actor": user(OWNER),
           "created_at": "2026-11-11T09:31:00Z"},
          {"id": 502, "event": "labeled", "label": {"name": "builder"}, "actor": user(BOT),
           "created_at": "2026-11-11T09:32:00Z"}],
    802: [{"id": 503, "event": "labeled", "label": {"name": "hold"}, "actor": user(OWNER),
           "created_at": "2026-11-11T11:00:00Z"}],
    686: [{"id": 504, "event": "labeled", "label": {"name": "priority"}, "actor": user(OWNER),
           "created_at": "2026-11-11T08:05:00Z"}],
}
PULLS = {900: {"merged_by": user(OWNER), "merged_at": "2026-11-11T12:00:00Z",
               "html_url": f"https://github.com/{REPO}/pull/900", "body": SECRET_BODY},
         901: {"merged_by": user(OWNER), "merged_at": "2026-11-11T13:00:00Z",
               "html_url": f"https://github.com/{REPO}/pull/901", "body": SECRET_BODY}}
FILES = {900: [{"filename": "governance/decisions/GOV-0036-x.md"}], 901: [{"filename": "launcher/x.py"}]}
REVIEWS = {(900, 71): {"user": user(OWNER), "state": "APPROVED", "submitted_at": "2026-11-11T11:55:00Z",
                       "html_url": f"https://github.com/{REPO}/pull/900#pullrequestreview-71",
                       "body": SECRET_BODY}}


# What a backfill finds (#844): the repo's issue events newest first, its comments, and search.
REPO_EVENTS = sorted([{**e, "issue": {"number": n}} for n, es in EVENTS.items() for e in es]
                     + [{"id": 600 + n, "event": "merged", "actor": user(OWNER), "issue": {"number": n},
                         "created_at": PULLS[n]["merged_at"]} for n in PULLS],
                     key=lambda e: e["created_at"], reverse=True)
REPO_COMMENTS = [{**c, "id": i, "issue_url": f"https://api.github.com/repos/{REPO}/issues/"
                  + c["html_url"].split("/issues/")[1].split("#")[0]} for i, c in COMMENTS.items()]
SEARCH = {"author:": [686, 800], "reviewed-by:": [900]}


class FakeGitHub:
    def __init__(self, fail: set[str] = frozenset()):
        self.calls: list[str] = []
        self.fail = fail

    def _get(self, path):
        self.calls.append(path)
        for bad in self.fail:
            if bad in path:
                raise RuntimeError(f"gh api {path} failed: {bad}")
        if path.startswith("orgs/"):
            return [{"full_name": REPO}]
        if path.startswith("search/issues"):
            q = urllib.parse.unquote(path.split("q=")[1].split("&")[0])
            assert "org:o " in q, q
            ns = next(v for k, v in SEARCH.items() if k in q)
            return [{"number": n, "repository_url": f"https://api.github.com/repos/{REPO}"} for n in ns]
        p = path.split("?")[0].split("/")[3:]          # after repos/o/r
        if p == ["issues", "events"]:
            page = int(path.split("page=")[-1])
            return REPO_EVENTS[(page - 1) * 100:page * 100]
        if p == ["issues", "comments"]:
            since = path.split("since=")[1].split("&")[0]
            return [c for c in REPO_COMMENTS if c["created_at"] >= since]
        if p[0] == "pulls" and p[2:] == ["reviews"]:
            return [{**r, "id": rid} for (n, rid), r in REVIEWS.items() if n == int(p[1])]
        if p[0] == "issues" and p[1] == "comments":
            if int(p[2]) not in COMMENTS:
                raise RuntimeError("gh api failed: HTTP 404: Not Found")
            return COMMENTS[int(p[2])]
        if p[0] == "issues" and len(p) == 2:
            return ISSUES[int(p[1])]
        if p[0] == "issues" and p[2] == "events":
            return EVENTS.get(int(p[1]), [])
        if p[0] == "pulls" and len(p) == 2:
            return PULLS[int(p[1])]
        if p[0] == "pulls" and p[2] == "files":
            return FILES[int(p[1])]
        if p[0] == "pulls" and p[2] == "reviews":
            return REVIEWS[(int(p[1]), int(p[3]))]
        raise AssertionError(path)

    def gh_json(self, *args):
        assert args[0] == "api"
        return self._get(args[1])

    def gh_items(self, path, jq=".[]"):
        return self._get(path)


def sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET, body, hashlib.sha256).hexdigest()


def payload(action, sender=OWNER, number=None, issue_key="issue", **extra) -> dict:
    p = {"action": action, "repository": {"full_name": REPO}, "sender": {"login": sender},
         issue_key: {"number": number, "body": SECRET_BODY}}
    p.update(extra)
    return p


# Deliveries as the receiver gets them. Two Apps deliver the same act, so some come twice.
DELIVERIES = [
    ("issues", payload("opened", number=686)),                                  # a Goal: not counted
    ("issues", payload("edited", number=686)),                                  # editing it: no lead
    ("issues", payload("labeled", number=686, label={"name": "priority"})),    # editing it: not counted
    ("issue_comment", payload("created", number=686, comment={"id": 13, "body": SECRET_BODY})),
    ("issues", payload("opened", number=800)),                                  # a Task: other
    ("issues", payload("labeled", number=800, label={"name": "ready"})),       # ready on a Task: other
    ("issues", payload("labeled", number=800, label={"name": "ready"})),       # the second App's copy
    ("issues", payload("labeled", sender=BOT, number=800, label={"name": "builder"})),
    ("issue_comment", payload("created", number=REPORT, comment={"id": 11, "body": SECRET_BODY})),
    ("issue_comment", payload("created", number=801, comment={"id": 12, "body": SECRET_BODY})),
    ("issue_comment", payload("created", sender=BOT, number=801, comment={"id": 99})),
    ("issues", payload("labeled", number=802, label={"name": "hold"})),
    ("pull_request_review", payload("submitted", number=900, issue_key="pull_request",
                                    review={"id": 71, "body": SECRET_BODY})),
    ("pull_request", payload("closed", number=900, issue_key="pull_request")),
    ("pull_request", payload("closed", number=901, issue_key="pull_request")),
    ("issue_comment", payload("created", number=802, comment={"id": 14})),      # yesterday
    ("issue_comment", payload("created", number=802, comment={"id": 15})),      # deleted since: 404
]
for _, p in DELIVERIES:
    if "pull_request" in p:
        p["pull_request"]["merged"] = True


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self.dir = self.home / "launcher"
        self.dir.mkdir()
        self.store = webhooks.Store(self.dir / webhooks.DB_FILE)
        self.addCleanup(self.store.db.close)

    def deliver(self, deliveries=DELIVERIES):
        for i, (event, p) in enumerate(deliveries):
            body = json.dumps(p).encode()
            headers = {"x-github-delivery": f"d-{i}", "x-github-event": event,
                       "x-hub-signature-256": sign(body)}
            got = webhooks.handle(self.store, SECRET, self.dir / webhooks.NUDGE_FILE, "POST",
                                  webhooks.PATH, headers, body, NOW)
            self.assertEqual(got, (202, "accepted"))

    def sync(self, gh=None):
        self.gh = gh or FakeGitHub()
        return acts.sync(self.dir, OWNER, (REPO, REPORT), self.gh.gh_json, self.gh.gh_items,
                         merger.is_protected, now=NOW)

    def day(self, d="2026-11-11"):
        """The day as counted once it is over and backfilled."""
        return acts.per_day(acts.stored(self.dir), [dt.date.fromisoformat(d)], UTC,
                            now=dt.datetime(2026, 11, 20, tzinfo=UTC), backfills=[ALWAYS])[0]


class Leads(Base):
    def test_only_possible_acts_leave_a_lead(self):
        self.deliver()
        leads = self.store.leads()
        self.assertEqual(len(leads), len(DELIVERIES) - 1)       # the Goal edit has none
        self.assertIn(("d-0", "issues", "opened", REPO, 686, None, OWNER), leads)
        self.assertIn(("d-2", "issues", "labeled", REPO, 686, "priority", OWNER), leads)
        self.assertIn(("d-13", "pull_request", "merged", REPO, 900, None, OWNER), leads)

    def test_unmerged_close_and_odd_payloads_leave_none(self):
        self.assertIsNone(acts.lead("pull_request", payload("closed", number=5, issue_key="pull_request")))
        self.assertIsNone(acts.lead("issues", payload("closed", number=5)))
        self.assertIsNone(acts.lead("issue_comment", payload("created", number=5)))   # no comment id
        self.assertIsNone(acts.lead("issues", {"action": "opened"}))
        self.assertIsNone(acts.lead("issues", ["not", "a", "dict"]))

    def test_no_body_is_stored(self):
        self.deliver()
        self.sync()
        db = sqlite3.connect(self.dir / webhooks.DB_FILE)
        self.addCleanup(db.close)
        for (table,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall():
            for row in db.execute(f"SELECT * FROM {table}"):
                self.assertNotIn(SECRET_BODY, json.dumps(row), table)


class Counts(Base):
    def test_counts_and_kinds(self):
        self.deliver()
        self.assertEqual(self.sync(), [])
        d = self.day()
        got = [(a["at"][11:16], a["act"], a["kind"], a["what"], a["number"]) for a in d["acts"]]
        self.assertEqual(got, [
            ("09:30", "open", "other", "opened Task", 800),
            ("09:31", "label", "other", "labelled ready", 800),
            ("10:00", "comment", "report", "commented", REPORT),
            ("10:05", "comment", "ask", "commented", 801),
            ("10:10", "comment", "plan", "commented", 686),
            ("11:00", "label", "plan", "labelled hold", 802),
            ("11:55", "review", "ask", "reviewed: approved", 900),
            ("12:00", "merge", "protected-merge", "merged", 900),
            ("13:00", "merge", "other", "merged", 901),
        ])
        self.assertEqual((d["count"], d["other"], d["under_limit"], d["c_team"]), (9, 3, False, False))
        self.assertEqual(self.day("2026-11-10")["count"], 1)

    def test_goal_and_area_opens_and_edits_dont_count(self):
        self.deliver(DELIVERIES[:3])        # the Goal opened, edited and labelled
        self.sync()
        self.assertEqual(self.day()["count"], 0)

    def test_duplicate_deliveries_count_once_and_read_once(self):
        self.deliver()
        self.sync()
        self.assertEqual(self.gh.calls.count(f"repos/{REPO}/issues/800/events?per_page=100"), 1)
        self.assertEqual(sum(a["what"] == "labelled ready" for a in self.day()["acts"]), 1)

    def test_others_leads_are_never_read(self):
        self.deliver()
        self.sync()
        self.assertNotIn(f"repos/{REPO}/issues/comments/99", self.gh.calls)

    def test_a_failed_read_is_retried_and_a_404_is_not(self):
        self.deliver()
        errors = self.sync(FakeGitHub(fail={"pulls/901"}))
        self.assertEqual(len(errors), 1)
        self.assertEqual(self.day()["count"], 8)
        self.assertEqual(self.sync(), [])
        self.assertEqual(self.day()["count"], 9)
        self.assertNotIn(f"repos/{REPO}/issues/comments/15", self.gh.calls)   # read once, gone

    def test_sync_twice_changes_nothing(self):
        self.deliver()
        self.sync()
        before = acts.stored(self.dir)
        self.sync()
        self.assertEqual(self.gh.calls, [])
        self.assertEqual(acts.stored(self.dir), before)


class Command(Base):
    def run_acts(self, *args):
        toml = self.home / "swarm.toml"
        toml.write_text(SESSION + "[watch]\ninterval_minutes = 5\nmax_live = 1\nmax_turns = 50\n"
                        f"report_issue = {REPORT}\n")
        lines: list[str] = []
        launcher = swarm.Launcher(self.home, root=self.home / "repo", out=lines.append)
        self.assertEqual(launcher.dir, self.dir)
        gh = FakeGitHub()
        rc = swarm.owner_acts(launcher, REPO, toml, *args, now=NOW, tz=UTC, owner=OWNER,
                              gh_json=gh.gh_json, gh_items=gh.gh_items)
        self.assertEqual(rc, 0, lines)
        return "\n".join(lines)

    def test_json_lists_ten_working_days(self):
        self.deliver()
        out = json.loads(self.run_acts(None, True))
        self.assertEqual(out["owner"], OWNER)
        self.assertEqual([d["day"] for d in out["days"]][:3], ["2026-11-11", "2026-11-10", "2026-11-09"])
        self.assertEqual(len(out["days"]), 10)
        self.assertEqual([(d["status"], d["count"]) for d in out["days"]][:3],
                         [("in progress", 9), ("counted", 1), ("counted", 0)])
        self.assertEqual(out["days"][0]["acts"][0]["url"], f"https://github.com/{REPO}/issues/800")

    def test_one_day_as_text(self):
        self.deliver()
        out = self.run_acts(dt.date(2026, 11, 10), False)
        self.assertIn("Tue 2026-11-10  1 act  (1 not C-team)", out)
        self.assertIn("16:00  other            commented on #802", out)
        self.assertNotIn("2026-11-11", out)

    def test_cli_parses(self):
        self.deliver()
        lines: list[str] = []
        launcher = swarm.Launcher(self.home, out=lines.append)
        orig = swarm.owner_acts
        seen = {}
        swarm.owner_acts = lambda l, repo, m, day, as_json: seen.update(day=day, as_json=as_json) or 0
        try:
            self.assertEqual(swarm.main(["acts", "--day", "2026-11-10", "--json", "--repo", REPO], launcher), 0)
        finally:
            swarm.owner_acts = orig
        self.assertEqual(seen, {"day": dt.date(2026, 11, 10), "as_json": True})


class NotCounted(Base):
    """#844: a day with no data reads `not counted`, never 0; a backfilled day counts, even at 0."""

    def refresh(self, days, now=NOW, gh=None):
        self.gh = gh or FakeGitHub()
        return acts.refresh(self.dir, OWNER, (REPO, REPORT), REPO, self.gh.gh_json, self.gh.gh_items,
                            merger.is_protected, [dt.date.fromisoformat(d) for d in days], now, UTC)

    def test_no_backfill_reads_not_counted_never_zero(self):
        rows = acts.per_day(acts.stored(self.dir), [dt.date(2026, 11, 9)], UTC, now=NOW)
        self.assertEqual((rows[0]["status"], rows[0]["count"], rows[0]["under_limit"], rows[0]["c_team"]),
                         ("not counted", None, None, None))
        self.assertIn("Mon 2026-11-09  not counted (not read back from GitHub yet)",
                      acts.text(rows, OWNER, REPO))

    def test_webhook_leads_alone_dont_count_a_day(self):
        self.deliver()
        self.sync()
        rows = acts.per_day(acts.stored(self.dir), [dt.date(2026, 11, 10)], UTC, now=NOW)
        self.assertEqual((rows[0]["status"], rows[0]["count"], len(rows[0]["acts"])), ("not counted", None, 1))

    def test_backfill_finds_the_same_acts_with_the_same_keys(self):
        rows, errors = self.refresh(["2026-11-11", "2026-11-10", "2026-11-09"])
        self.assertEqual(errors, [])
        self.assertEqual([(r["status"], r["count"]) for r in rows],
                         [("in progress", 9), ("counted", 1), ("counted", 0)])   # 0 still counts
        self.assertIsNone(rows[0]["under_limit"])
        before = acts.stored(self.dir)
        self.deliver()                                   # the same acts arrive by webhook too
        self.sync()
        self.assertEqual(acts.stored(self.dir), before)

    def test_a_counted_day_isnt_read_again(self):
        self.refresh(["2026-11-10"])
        rows, errors = self.refresh(["2026-11-10"])
        self.assertEqual((errors, rows[0]["status"]), ([], "counted"))
        self.assertEqual(self.gh.calls, [])

    def test_a_failed_backfill_counts_nothing_and_is_retried(self):
        rows, errors = self.refresh(["2026-11-10"], gh=FakeGitHub(fail={"search/issues"}))
        self.assertEqual(rows[0]["status"], "not counted")
        self.assertTrue(errors and errors[0].startswith("backfill from 2026-11-10T00:00:00Z"), errors)
        rows, errors = self.refresh(["2026-11-10"])
        self.assertEqual((errors, rows[0]["status"], rows[0]["count"]), ([], "counted", 1))

    def test_an_unread_backfilled_act_holds_the_day(self):
        rows, errors = self.refresh(["2026-11-10"], now=NOW + dt.timedelta(days=1),
                                    gh=FakeGitHub(fail={"pulls/901"}))
        self.assertEqual((len(errors), rows[0]["status"]), (1, "not counted"))
        rows, errors = self.refresh(["2026-11-10"], now=NOW + dt.timedelta(days=1))
        self.assertEqual((errors, rows[0]["status"]), ([], "counted"))

    def test_a_day_is_read_back_only_once_it_has_settled(self):
        now = dt.datetime(2026, 11, 11, 0, 30, tzinfo=UTC)
        rows, _ = self.refresh(["2026-11-10"], now=now)
        self.assertEqual((rows[0]["status"], rows[0]["why"]),
                         ("not counted", "read back from GitHub 1h after the day ends"))
        self.assertEqual(self.gh.calls, [])
        rows, _ = self.refresh(["2026-11-10"], now=now + acts.SETTLE)
        self.assertEqual(rows[0]["status"], "counted")

    def test_old_days_and_future_days_arent_read_back(self):
        rows, _ = self.refresh(["2026-09-01", "2026-11-12"])
        self.assertEqual([r["status"] for r in rows], ["not counted", "not counted"])
        self.assertIn("older than 31 days", rows[0]["why"])
        self.assertEqual(self.gh.calls, [])

    def test_out_of_time_search_stores_nothing_and_the_next_run_finishes(self):
        # #858: `swarm trouble` passes a deadline; a backfill past it counts nothing yet.
        gone = time.monotonic() - 1
        rows, errors = acts.refresh(self.dir, OWNER, (REPO, REPORT), REPO, *self.fake(), merger.is_protected,
                                    [dt.date(2026, 11, 10)], NOW, UTC, deadline=gone)
        self.assertEqual(rows[0]["status"], "not counted")
        self.assertTrue(any(acts.OUT_OF_TIME in e for e in errors), errors)
        self.assertEqual(acts.stored(self.dir), [])
        rows, errors = self.refresh(["2026-11-10"])
        self.assertEqual((errors, rows[0]["status"], rows[0]["count"]), ([], "counted", 1))

    def test_out_of_time_sync_leaves_its_leads_for_the_next_run(self):
        self.deliver()
        gh = FakeGitHub()
        errors = acts.sync(self.dir, OWNER, (REPO, REPORT), gh.gh_json, gh.gh_items, merger.is_protected,
                           now=NOW, deadline=time.monotonic() - 1)
        self.assertEqual(gh.calls, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("not read back yet (out of time); the next run reads them", errors[0])
        self.assertEqual(self.sync(), [])
        self.assertTrue(acts.stored(self.dir))

    def fake(self):
        self.gh = FakeGitHub()
        return self.gh.gh_json, self.gh.gh_items

    def test_each_keeps_order_and_hands_back_errors(self):
        def f(x):
            if x == 3:
                raise RuntimeError("three")
            time.sleep(0.01 * (10 - x))        # later items finish first
            return x * 2
        got = acts.each(f, list(range(10)))
        self.assertEqual([g if not isinstance(g, Exception) else "err" for g in got],
                         [0, 2, 4, "err", 8, 10, 12, 14, 16, 18])

    def test_issue_events_stop_at_the_window(self):
        pages = {1: [{"created_at": f"2026-11-11T{h:02d}:00:00Z"} for h in range(23, 23 - 100, -1)
                     if h >= 0] + [{"created_at": "2026-11-09T00:00:00Z"}] * 77}
        calls = []

        def gh_json(_api, path):
            calls.append(path)
            return pages.get(int(path.rsplit("=", 1)[1]), [])
        got = acts.recent_events(REPO, "2026-11-10T00:00:00Z", gh_json)
        self.assertEqual((len(got), len(calls)), (24, 1))
        with self.assertRaises(RuntimeError):
            acts.recent_events(REPO, "2026-11-10T00:00:00Z",
                               lambda *a: [{"created_at": "2026-11-10T01:00:00Z"},
                                           {"created_at": "2026-11-11T01:00:00Z"}])


if __name__ == "__main__":
    unittest.main()
