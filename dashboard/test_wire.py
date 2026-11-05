"""Tests for dashboard/wire.py (#405). Run: python3 -m unittest discover -s dashboard"""
import datetime as dt
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import activity  # noqa: E402
import generate as g  # noqa: E402
import state  # noqa: E402
import wire  # noqa: E402

REPO = "open-agentos/productswarm"
BASE = f"https://github.com/{REPO}"
NOW = dt.datetime(2026, 11, 5, 10, 30, tzinfo=dt.timezone.utc)
OWNER = "mattmcalister"
BOT = "productswarm-builder[bot]"
RECORDS = {396: {"id": "GOV-0021", "file": "GOV-0021-wire.md"}}


def ts(minutes_ago: float) -> str:
    return (NOW - dt.timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def at(minutes_ago: float) -> dt.datetime:
    return NOW - dt.timedelta(minutes=minutes_ago)


def issues_event(action, n, minutes_ago, actor=OWNER, labels=("gov:question",), label=None):
    p = {"action": action, "issue": {"number": n, "html_url": f"{BASE}/issues/{n}",
                                     "labels": [{"name": x} for x in labels]}}
    if label:
        p["label"] = {"name": label}
    return {"type": "IssuesEvent", "actor": {"login": actor}, "created_at": ts(minutes_ago), "payload": p}


def review_event(n, state_, minutes_ago, user=wire.REVIEWER):
    return {"type": "PullRequestReviewEvent", "actor": {"login": user}, "created_at": ts(minutes_ago),
            "payload": {"action": "created", "pull_request": {"number": n},
                        "review": {"state": state_, "user": {"login": user}, "submitted_at": ts(minutes_ago),
                                   "html_url": f"{BASE}/pull/{n}#pullrequestreview-1"}}}


def build(events=(), questions=None, reviews=None, comms=None, records=RECORDS, unreadable=False):
    act = {"events": None} if unreadable else {"events": list(events)}
    return wire.build(act, questions, reviews, comms, records, OWNER, REPO, NOW)


def kinds(w):
    return [(i["kind"], i["number"]) for i in w["items"]]


class EventsTest(unittest.TestCase):
    def test_each_kind_from_events(self):
        w = build([issues_event("opened", 439, 10, actor=BOT),
                   issues_event("labeled", 396, 20, label="gov:ruled", labels=("gov:question", "gov:ruled")),
                   issues_event("labeled", 388, 30, label="gov:lapsed", labels=("gov:question", "gov:lapsed")),
                   issues_event("closed", 396, 40),
                   review_event(438, "changes_requested", 50)])
        self.assertEqual(kinds(w), [("opened", 439), ("ruled", 396), ("lapsed", 388), ("record", 396),
                                    ("red", 438)])
        texts = {i["kind"]: (i["text"], i["link"]) for i in w["items"]}
        self.assertEqual(texts["opened"], ("Question #439 opened", f"{BASE}/issues/439"))
        self.assertEqual(texts["ruled"], ("Owner ruled on #396", f"{BASE}/issues/396"))
        self.assertEqual(texts["lapsed"], ("Question #388 lapsed", f"{BASE}/issues/388"))
        self.assertEqual(texts["record"], ("GOV-0021 merged, answering #396",
                                           f"{BASE}/blob/main/governance/decisions/GOV-0021-wire.md"))
        self.assertEqual(texts["red"], ("Reviewer requested changes on PR #438",
                                        f"{BASE}/pull/438#pullrequestreview-1"))
        self.assertTrue(w["events"])

    def test_what_is_not_news(self):
        w = build([issues_event("opened", 440, 1, actor=BOT, labels=()),             # not a question
                   issues_event("labeled", 405, 2, label="ready", labels=("ready",)),  # not gov:ruled
                   issues_event("labeled", 396, 3, actor=BOT, label="gov:ruled"),      # not the owner
                   issues_event("closed", 397, 4),                                     # no record
                   issues_event("closed", 396, 5, labels=()),                          # not a question
                   review_event(438, "approved", 6),
                   review_event(438, "changes_requested", 7, user=BOT),                # not the reviewer
                   issues_event("opened", 441, 11 * 60)])                              # yesterday
        self.assertEqual(w["items"], [])

    def test_one_item_per_kind_and_number_at_its_earliest(self):
        w = build([review_event(438, "changes_requested", 5), review_event(438, "changes_requested", 50)])
        self.assertEqual([i["time"] for i in w["items"]], [at(50)])

    def test_newest_first_even_when_listed_out_of_order(self):
        w = build([issues_event("opened", 1, 30, actor=BOT), issues_event("opened", 2, 5, actor=BOT),
                   issues_event("opened", 3, 60, actor=BOT)])
        self.assertEqual([i["number"] for i in w["items"]], [2, 1, 3])


class FallbackTest(unittest.TestCase):
    def test_question_history_gives_opened_ruled_lapsed_and_record(self):
        q = {"issues": [{"number": 439, "created_at": ts(10), "html_url": f"{BASE}/issues/439"},
                        {"number": 300, "created_at": ts(3 * 24 * 60)}],
             "timelines": {396: [{"__typename": "LabeledEvent", "createdAt": ts(20),
                                  "label": {"name": "gov:ruled"}, "actor": {"login": OWNER}},
                                 {"__typename": "ClosedEvent", "createdAt": ts(40)}],
                           388: [{"__typename": "LabeledEvent", "createdAt": ts(30),
                                  "label": {"name": "gov:lapsed"}, "actor": {"login": OWNER}},
                                 {"__typename": "ClosedEvent", "createdAt": ts(31)}],   # no record
                           300: [{"__typename": "LabeledEvent", "createdAt": ts(1),
                                  "label": {"name": "gov:ruled"}, "actor": {"login": BOT}}]}}
        w = build(questions=q, unreadable=True)
        self.assertEqual(kinds(w), [("opened", 439), ("ruled", 396), ("lapsed", 388), ("record", 396)])
        self.assertFalse(w["events"])

    def test_reviews_give_red(self):
        reviews = {438: [{"state": "CHANGES_REQUESTED", "submitted_at": ts(15), "user": {"login": wire.REVIEWER},
                          "html_url": "https://r"},
                         {"state": "APPROVED", "submitted_at": ts(5), "user": {"login": wire.REVIEWER}},
                         {"state": "CHANGES_REQUESTED", "submitted_at": ts(24 * 60), "user": {"login": wire.REVIEWER}}]}
        w = build(reviews=reviews)
        self.assertEqual([(i["kind"], i["number"], i["link"], i["time"]) for i in w["items"]],
                         [("red", 438, "https://r", at(15))])

    def test_committees_give_convened(self):
        comms = {"committees": [
            {"question": 311, "owner_comments": {"convening": {"ts": at(25), "url": "https://conv"}}},
            {"question": 200, "owner_comments": {"convening": {"ts": at(2 * 24 * 60), "url": "x"}}},
            {"question": 201, "owner_comments": {"convening": None}},
            {"status": "unparsed"}]}
        w = build(comms=comms)
        self.assertEqual([(i["kind"], i["number"], i["text"], i["link"]) for i in w["items"]],
                         [("convened", 311, "Committee convened on #311", "https://conv")])

    def test_events_and_fallback_agree_on_one_item(self):
        q = {"issues": [{"number": 439, "created_at": ts(10)}], "timelines": {}}
        w = build([issues_event("opened", 439, 10, actor=BOT)], questions=q)
        self.assertEqual(kinds(w), [("opened", 439)])


class EmptyDayTest(unittest.TestCase):
    def test_quiet_day(self):
        w = build()
        self.assertEqual(w["items"], [])
        self.assertIn("Quiet so far today.", wire.render(w))
        self.assertEqual(wire.state(w), {"day": NOW.date(), "events": True, "items": []})

    def test_unreadable_events_say_so(self):
        html = wire.render(build(unreadable=True))
        self.assertIn("Quiet so far today.", html)
        self.assertIn("couldn&#x27;t be read", html)

    def test_not_fetched_draws_nothing(self):
        self.assertEqual(wire.render(None), "")
        self.assertIsNone(wire.state(None))


class RenderTest(unittest.TestCase):
    def test_items_show_time_and_link(self):
        html = wire.render(build([issues_event("labeled", 396, 76, label="gov:ruled")]))
        self.assertIn('<h2>The wire</h2>', html)
        self.assertIn('<li class="ruled"><time datetime="2026-11-05T09:14:00Z">09:14</time> '
                      f'<a href="{BASE}/issues/396">Owner ruled on #396</a></li>', html)


class PageTest(unittest.TestCase):
    def test_desk_and_state_json_carry_the_wire(self):
        data = {"repo": REPO, "issues": [], "comments": {}, "prs": [],
                "activity": {"events": [issues_event("labeled", 396, 76, label="gov:ruled")], "pages": 1}}
        with mock.patch.object(g.committees, "owner_login", return_value=OWNER):
            m = g.build(data, NOW, dt.timedelta(minutes=15))
        self.assertIn("Owner ruled on #396", g.render(m)["index.html"])
        s = json.loads(json.dumps(state.state(m)))
        self.assertEqual(s["wire"]["items"], [{"kind": "ruled", "time": "2026-11-05T09:14:00Z", "number": 396,
                                               "text": "Owner ruled on #396", "link": f"{BASE}/issues/396"}])
        self.assertEqual(s["wire"]["day"], "2026-11-05")

    def test_no_wire_without_events_or_questions(self):
        m = g.build({"repo": REPO, "issues": [], "comments": {}, "prs": []}, NOW, dt.timedelta(minutes=15))
        self.assertNotIn("The wire", g.render(m)["index.html"])
        self.assertIsNone(state.state(m)["wire"])


class FetchSinceTest(unittest.TestCase):
    """activity.fetch reads on to UTC midnight for the wire, still at most 3 pages."""

    def page(self, newest, oldest, owner_at=None):
        out = [{"type": "IssuesEvent", "actor": {"login": BOT}, "created_at": ts(newest + i * (oldest - newest) / 99),
                "payload": {}} for i in range(100)]
        if owner_at is not None:
            out[owner_at]["actor"] = {"login": OWNER}
        return out

    def test_reads_past_the_owner_page_until_midnight(self):
        gh = mock.Mock(side_effect=[self.page(0, 100, owner_at=3), self.page(100, 500), self.page(500, 900)])
        got = activity.fetch(REPO, gh, OWNER, wire.midnight(NOW))
        # Midnight is 630 minutes ago; page 2 ends 500 minutes ago, still today, so page 3 is read.
        self.assertEqual(got["pages"], 3)
        self.assertEqual(gh.call_count, 3)

    def test_stops_once_a_page_ends_before_midnight(self):
        gh = mock.Mock(side_effect=[self.page(0, 100, owner_at=3), self.page(100, 700), self.page(700, 900)])
        self.assertEqual(activity.fetch(REPO, gh, OWNER, wire.midnight(NOW))["pages"], 2)

    def test_without_since_stops_at_the_owner_page(self):
        gh = mock.Mock(side_effect=[self.page(0, 100, owner_at=3), self.page(100, 700)])
        self.assertEqual(activity.fetch(REPO, gh, OWNER)["pages"], 1)

    def test_still_reads_on_for_the_owner_after_midnight(self):
        gh = mock.Mock(side_effect=[self.page(0, 700), self.page(700, 800, owner_at=5), self.page(800, 900)])
        self.assertEqual(activity.fetch(REPO, gh, OWNER, wire.midnight(NOW))["pages"], 2)


if __name__ == "__main__":
    unittest.main()
