"""Tests for dashboard/activity.py (#402). Run: python3 -m unittest discover -s dashboard"""
import datetime as dt
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import activity as a  # noqa: E402
import generate as g  # noqa: E402
import layout  # noqa: E402
import state  # noqa: E402

REPO = "open-agentos/productswarm"
NOW = dt.datetime(2026, 11, 5, 10, 30, tzinfo=dt.timezone.utc)
OWNER = "mattmcalister"
BOT = "productswarm-builder[bot]"


def ts(minutes_ago: float) -> str:
    return (NOW - dt.timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def event(kind, minutes_ago, actor=OWNER, **payload):
    return {"type": kind, "actor": {"login": actor}, "created_at": ts(minutes_ago), "payload": payload}


def labeled(n, label, minutes_ago, actor=OWNER):
    return event("IssuesEvent", minutes_ago, actor, action="labeled", label={"name": label},
                 issue={"number": n, "html_url": f"https://github.com/{REPO}/issues/{n}"})


def acted(events, owner=OWNER):
    return a.owner_last_acted({"events": events}, owner, REPO, NOW)


class OwnerFilterTest(unittest.TestCase):
    def test_newest_owner_event_not_an_agents(self):
        o = acted([event("IssueCommentEvent", 1, BOT, action="created", issue={"number": 9}),
                   labeled(397, "ready", 12),
                   labeled(396, "ready", 30)])
        self.assertEqual(o["status"], "acted")
        self.assertEqual((o["kind"], o["text"]), ("labeled", "labelled #397 ready"))
        self.assertEqual(o["link"], f"https://github.com/{REPO}/issues/397")
        self.assertEqual(o["time"], NOW - dt.timedelta(minutes=12))

    def test_login_case_does_not_matter(self):
        self.assertEqual(acted([labeled(1, "ready", 5, actor="MattMcAlister")])["status"], "acted")

    def test_late_arriving_old_event_does_not_win(self):
        # The API lists a two-day-old push among today's events (seen 2026-11-05).
        o = acted([event("PushEvent", 2 * 24 * 60, ref="refs/heads/main", head="abc"),
                   labeled(411, "ready", 7)])
        self.assertEqual(o["text"], "labelled #411 ready")

    def test_merge_by_author_is_not_the_owners(self):
        # A merge's actor is the PR's author; the owner's close of the linked issue is theirs.
        o = acted([event("PullRequestEvent", 1, BOT, action="merged", number=427),
                   event("IssuesEvent", 0.5, action="closed",
                         issue={"number": 409, "html_url": f"https://github.com/{REPO}/issues/409"})])
        self.assertEqual((o["kind"], o["text"]), ("closed", "closed #409"))

    def test_kinds_in_words(self):
        cases = [
            (event("PullRequestEvent", 1, action="merged", number=12), "merged PR #12",
             f"https://github.com/{REPO}/pull/12"),
            (event("PushEvent", 1, ref="refs/heads/main", head="abc123"), "pushed to main",
             f"https://github.com/{REPO}/commit/abc123"),
            (event("PullRequestReviewEvent", 1, action="created", pull_request={"number": 5}),
             "reviewed PR #5", f"https://github.com/{REPO}/pull/5"),
            (event("IssueCommentEvent", 1, action="created", issue={"number": 7},
                   comment={"html_url": "https://c"}), "commented on #7", "https://c"),
            (event("CreateEvent", 1, ref_type="branch", ref="x"), "created branch x",
             f"https://github.com/{REPO}/tree/x"),
            (event("IssuesEvent", 1, action="unlabeled", label=None, issue={"number": 3}),
             "unlabelled #3", f"https://github.com/{REPO}/issues/3"),
            (event("WatchEvent", 1, action="started"), "watch", f"https://github.com/{REPO}"),
        ]
        for e, text, link in cases:
            with self.subTest(text):
                o = acted([e])
                self.assertEqual((o["text"], o["link"]), (text, link))


class WatchIssueTest(unittest.TestCase):
    """#458: swarm watch edits the [watch] issue as the owner's login; that isn't the owner acting."""

    def watch_edit(self, minutes_ago, body=a.WATCH_MARKER + " state"):
        return event("IssuesEvent", minutes_ago, OWNER, action="edited",
                     issue={"number": 300, "title": "[watch] swarm watch's state", "body": body})

    def test_edits_of_the_watch_issue_are_skipped(self):
        o = acted([self.watch_edit(1), labeled(9, "ready", 30)])
        self.assertEqual((o["text"], o["time"]), ("labelled #9 ready", NOW - dt.timedelta(minutes=30)))
        self.assertEqual(acted([self.watch_edit(1)])["status"], "none")

    def test_the_owners_other_edits_and_acts_on_it_still_count(self):
        self.assertEqual(acted([self.watch_edit(1, body="my notes")])["kind"], "edited")
        closed = event("IssuesEvent", 1, OWNER, action="closed",
                       issue={"number": 300, "body": a.WATCH_MARKER})
        self.assertEqual(acted([closed])["text"], "closed #300")

    def test_fetch_reads_on_past_a_page_of_watch_edits(self):
        edits = [self.watch_edit(i) for i in range(100)]
        gh = mock.Mock(side_effect=[edits, [labeled(1, "ready", 200)]])
        self.assertEqual(a.fetch(REPO, gh, OWNER)["pages"], 2)


class NoActivityTest(unittest.TestCase):
    def test_no_owner_event_says_how_far_back_was_read(self):
        o = acted([event("IssuesEvent", 60, BOT, action="opened", issue={"number": 1}),
                   event("IssuesEvent", 2.5 * 24 * 60, BOT, action="opened", issue={"number": 2})])
        self.assertEqual(o, {"status": "none", "days": 3})
        self.assertIn("Owner: no activity in the last 3 days", a.header(o, NOW, g.ago))

    def test_a_few_late_arrivals_do_not_stretch_the_span(self):
        events = [event("IssuesEvent", i, BOT, action="opened", issue={"number": i}) for i in range(60)]
        events.insert(5, event("PushEvent", 3 * 24 * 60, BOT, ref="refs/heads/main"))
        self.assertEqual(acted(events), {"status": "none", "days": 1})

    def test_one_day_is_singular(self):
        o = acted([event("IssuesEvent", 60, BOT, action="opened", issue={"number": 1})])
        self.assertIn("in the last 1 day<", a.header(o, NOW, g.ago))


class FailureTest(unittest.TestCase):
    def test_api_failure_reads_as_unknown(self):
        for err in (RuntimeError("gh api failed: HTTP 401"), ValueError("bad json"), OSError("no gh")):
            with self.subTest(err=err):
                got = a.fetch(REPO, mock.Mock(side_effect=err), OWNER)
                self.assertIsNone(got["events"])
                o = a.owner_last_acted(got, OWNER, REPO, NOW)
                self.assertEqual(o, {"status": "unknown"})
                self.assertIn("Owner: unknown", a.header(o, NOW, g.ago))

    def test_unreadable_owner_is_unknown(self):
        self.assertEqual(acted([labeled(1, "ready", 5)], owner=None), {"status": "unknown"})

    def test_not_fetched_is_unknown(self):
        self.assertIn("Owner: unknown", a.header(a.owner_last_acted(None, OWNER, REPO, NOW), NOW, g.ago))

    def test_page_still_builds_on_failure(self):
        m = g.build({"repo": REPO, "issues": [], "comments": {}, "prs": [],
                     "activity": {"events": None, "error": a.UNREADABLE}},
                    NOW, dt.timedelta(minutes=15))
        for name, html in g.render(m).items():
            with self.subTest(name):
                self.assertIn('<span class="live">LIVE</span>', html)
                self.assertIn("Owner: unknown", html)
        self.assertEqual(state.state(m)["owner_last_acted"], {"status": "unknown"})


class FetchTest(unittest.TestCase):
    def pages(self, *pages):
        return mock.Mock(side_effect=list(pages))

    def test_stops_at_the_first_page_with_an_owner_event(self):
        bots = [event("IssuesEvent", i, BOT, action="opened", issue={"number": i}) for i in range(100)]
        gh = self.pages(bots, bots[:99] + [labeled(1, "ready", 200)], bots)
        got = a.fetch(REPO, gh, OWNER)
        self.assertEqual((got["pages"], len(got["events"])), (2, 200))
        self.assertEqual([c.args for c in gh.call_args_list],
                         [("api", f"repos/{REPO}/events?per_page=100&page={p}") for p in (1, 2)])

    def test_reads_at_most_three_pages(self):
        bots = [event("IssuesEvent", i, BOT, action="opened", issue={"number": i}) for i in range(100)]
        gh = self.pages(bots, bots, bots, bots)
        self.assertEqual(a.fetch(REPO, gh, OWNER)["pages"], 3)
        self.assertEqual(gh.call_count, 3)

    def test_short_page_is_the_last(self):
        gh = self.pages([event("IssuesEvent", 1, BOT, action="opened", issue={"number": 1})])
        self.assertEqual(a.fetch(REPO, gh, OWNER)["pages"], 1)


class HeaderTest(unittest.TestCase):
    def test_owner_line_links_the_issue_and_codes_the_label(self):
        html = a.header(acted([labeled(397, "ready", 12)]), NOW, g.ago)
        self.assertIn("Owner last acted", html)
        self.assertIn("12m ago", html)
        self.assertIn(f'labelled <a href="https://github.com/{REPO}/issues/397">#397</a> '
                      "<code>ready</code>", html)

    def test_push_links_the_branch_name(self):
        html = a.header(acted([event("PushEvent", 3, ref="refs/heads/main", head="abc")]), NOW, g.ago)
        self.assertIn(f'pushed to <a href="https://github.com/{REPO}/commit/abc"><code>main</code></a>', html)

    def test_text_is_escaped(self):
        html = a.header(acted([labeled(1, "<b>x</b>", 1)]), NOW, g.ago)
        self.assertNotIn("<b>x</b>", html)

    def test_every_page_has_the_mark_build_time_and_owner(self):
        events = [labeled(397, "ready", 12)]
        with mock.patch.object(g.committees, "owner_login", return_value=OWNER):
            m = g.build({"repo": REPO, "issues": [], "comments": {}, "prs": [],
                         "activity": {"events": events, "pages": 1}}, NOW, dt.timedelta(minutes=15))
        pages = g.render(m)
        self.assertEqual(set(pages), {f for f, _ in layout.PAGES})
        for name, html in pages.items():
            with self.subTest(name):
                self.assertIn('<span class="live">LIVE</span>', html)
                self.assertIn('datetime="2026-11-05T10:30:00Z"', html)
                self.assertIn(">10:30 UTC</time>", html)
                self.assertIn("Owner last acted", html)
        s = state.state(m)["owner_last_acted"]
        self.assertEqual(s, {"status": "acted", "kind": "labeled", "text": "labelled #397 ready",
                             "time": "2026-11-05T10:18:00Z",
                             "link": f"https://github.com/{REPO}/issues/397"})


if __name__ == "__main__":
    unittest.main()
