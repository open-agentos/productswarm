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
import unittest
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


class FakeGitHub:
    def __init__(self, fail: set[str] = frozenset()):
        self.calls: list[str] = []
        self.fail = fail

    def _get(self, path):
        self.calls.append(path)
        for bad in self.fail:
            if bad in path:
                raise RuntimeError(f"gh api {path} failed: {bad}")
        p = path.split("?")[0].split("/")[3:]          # after repos/o/r
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
        return acts.per_day(acts.stored(self.dir), [dt.date.fromisoformat(d)], UTC)[0]


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
        self.assertEqual([d["count"] for d in out["days"]][:3], [9, 1, 0])
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


if __name__ == "__main__":
    unittest.main()
