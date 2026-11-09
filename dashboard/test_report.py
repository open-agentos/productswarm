"""Tests for dashboard/report.py (#712). Run: python3 -m unittest discover -s dashboard"""
import datetime as dt
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import live  # noqa: E402
import report  # noqa: E402

REPO = "open-agentos/productswarm"
UTC = dt.timezone.utc
AT = dt.time(8, 30)
MON = dt.datetime(2026, 11, 9, 11, 0, tzinfo=UTC)   # a Monday, after the 10:00 cut-off

REPORT = """**Daily report, Mon 2026-11-09: you adopted operating model v2 (#651) on Saturday. M1 is on working day 2 of 5.** Since Friday's report.

**1. Done**
- **M1 (daily report):** `[daily]` started this run.

**5. Asks**
1. **#655 (GOV-0032):** merge it? It touches `governance/`, so it's yours. Yes or no.
2. **PLAN.md during v2:** may I open a `PLAN.md` PR that adds the v2 engine as a milestone, so those issues become go under GOV-0026 until GOV-0031 retires PLAN.md and the rest of this long sentence runs on? Yes or no.
3. **M4 now:** may I open two M4 issues? Yes or no.
4. **M1 counting** (carried from Friday): does Fri 2026-11-06 count as working day 1? Yes or no.
5. **#572** (carried from Friday): may I comment there? Yes or no.
6. **Sixth:** never shown.

-- planner (claude-opus-5-5)
"""
FRIDAY = "**Daily report, Fri 2026-11-06: M1 started today.** First report.\n\n**5. Asks**\n1. **Q:** yes?\n"
CHECKIN = "**Monday check-in, week of 2026-11-09: M1 moved; M2 at risk.** First check-in.\n"


def comment(body, when, login=report.PLANNER, cid=1):
    return {"user": {"login": login}, "body": body, "created_at": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "html_url": f"https://github.com/{REPO}/issues/249#issuecomment-{cid}"}


def build(comments, now=MON, issue=249, daily_at=AT):
    return report.build(comments, now, issue, daily_at, tz=UTC)


class AsksTest(unittest.TestCase):
    def test_reads_the_numbered_items_under_asks(self):
        got = report.asks(REPORT)
        self.assertEqual(len(got), 5)   # at most 5
        self.assertEqual(got[0], {"lead": "#655 (GOV-0032):", "text": "merge it?", "issue": 655})
        self.assertEqual(got[3]["lead"], "M1 counting")
        self.assertEqual(got[3]["text"], "(carried from Friday): does Fri 2026-11-06 count as working day 1?")
        self.assertIsNone(got[3]["issue"])
        self.assertEqual(got[4]["issue"], 572)

    def test_cuts_a_long_ask_to_about_120_characters(self):
        a = report.asks(REPORT)[1]
        self.assertLessEqual(len(a["lead"]) + len(a["text"]), report.ASK_CHARS + 1)
        self.assertTrue(a["text"].endswith("…"))

    def test_no_heading_or_no_items_is_none(self):
        self.assertIsNone(report.asks("**Daily report, x.**\n\nNothing else."))
        self.assertIsNone(report.asks("**Daily report, x.**\n\n**5. Asks**\nNone today.\n"))

    def test_stops_at_the_next_heading(self):
        body = "**4. Asks**\n1. **A:** one?\n\n**5. Later**\n1. **B:** not an ask.\n"
        self.assertEqual([a["lead"] for a in report.asks(body)], ["A:"])


class StatesTest(unittest.TestCase):
    def test_posted_today(self):
        r = build([comment(FRIDAY, dt.datetime(2026, 11, 6, 21, 48), cid=1),
                   comment(REPORT, dt.datetime(2026, 11, 9, 8, 34), cid=2),
                   comment(CHECKIN, dt.datetime(2026, 11, 9, 8, 35), cid=3)])
        self.assertEqual(r["state"], "posted")
        self.assertTrue(r["report"]["line"].startswith("Daily report, Mon 2026-11-09: you adopted"))
        self.assertEqual(r["report"]["url"][-1], "2")
        self.assertEqual(r["checkin"]["url"][-1], "3")
        html = report.render(r, REPO)
        self.assertIn("posted 08:34", html)
        self.assertIn(f"https://github.com/{REPO}/issues/655", html)
        self.assertIn("Monday check-in: ", html)
        self.assertIn("<code>governance/</code>", report.inline("`governance/`"))
        live.tree(html)   # the live refresh can draw it

    def test_other_authors_and_non_reports_dont_count(self):
        r = build([comment(REPORT, dt.datetime(2026, 11, 9, 8, 34), login="mattmcalister"),
                   comment("Ask: builder: why?", dt.datetime(2026, 11, 9, 9, 0))])
        self.assertEqual(r["state"], "late")
        self.assertIsNone(r["last"])
        self.assertIn("No daily report found on #249.", report.render(r, REPO))

    def test_due_before_ten_shows_the_last_report(self):
        r = build([comment(FRIDAY, dt.datetime(2026, 11, 6, 21, 48))],
                  now=dt.datetime(2026, 11, 10, 9, 0, tzinfo=UTC))
        self.assertEqual(r["state"], "due")
        html = report.render(r, REPO)
        self.assertIn("Today's report is due at 08:30.", html)
        self.assertIn("Last report, Fri 11-06:", html)

    def test_late_after_ten(self):
        r = build([comment(FRIDAY, dt.datetime(2026, 11, 6, 21, 48))],
                  now=dt.datetime(2026, 11, 10, 10, 0, tzinfo=UTC))
        html = report.render(r, REPO)
        self.assertIn('<p class="ask"><b>No report yet today.</b> It was due at 08:30.</p>', html)
        self.assertIn("Last report, Fri 11-06:", html)

    def test_weekend(self):
        r = build([comment(FRIDAY, dt.datetime(2026, 11, 6, 21, 48))],
                  now=dt.datetime(2026, 11, 8, 12, 0, tzinfo=UTC))
        self.assertEqual(r["state"], "weekend")
        self.assertIn("No report on weekends.", report.render(r, REPO))

    def test_report_without_asks_says_so(self):
        body = "**Daily report, Mon 2026-11-09: quiet.**\n\nNothing to ask.\n"
        r = build([comment(body, dt.datetime(2026, 11, 9, 8, 34))])
        self.assertIn("Asks: couldn't read them; <a", report.render(r, REPO))

    def test_unread_and_unset(self):
        self.assertIn("Couldn't read #249; the report may be there.", report.render(build(None), REPO))
        self.assertIn("No report issue", report.render(build([], issue=None), REPO))

    def test_a_late_report_counts_for_the_day_on_its_first_line(self):
        late = "**Daily report, Fri 2026-11-06: late.**\n"
        r = build([comment(late, dt.datetime(2026, 11, 9, 8, 0))])   # posted Monday, for Friday
        self.assertIsNone(r["report"])
        self.assertEqual(r["last"]["day"], dt.date(2026, 11, 6))

    def test_check_in_only_on_mondays(self):
        r = build([comment(REPORT.replace("Mon 2026-11-09", "Tue 2026-11-10"), dt.datetime(2026, 11, 10, 8, 34)),
                   comment(CHECKIN, dt.datetime(2026, 11, 10, 8, 35))],
                  now=dt.datetime(2026, 11, 10, 11, 0, tzinfo=UTC))
        self.assertIsNone(r["checkin"])

    def test_escapes_report_text(self):
        body = "**Daily report, Mon 2026-11-09: <script>x</script>.**\n\n**Asks**\n1. **<b>:** hi?\n"
        html = report.render(build([comment(body, dt.datetime(2026, 11, 9, 8, 34))]), REPO)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        live.tree(html)

    def test_state_is_plain(self):
        s = report.state(build([comment(REPORT, dt.datetime(2026, 11, 9, 8, 34))]))
        self.assertEqual(s["daily_at"], "08:30")
        self.assertEqual(s["state"], "posted")


class FetchTest(unittest.TestCase):
    def test_reads_four_days_of_comments(self):
        paths = []
        report.fetch(REPO, 249, MON, lambda p: paths.append(p) or [])
        self.assertEqual(paths, [f"repos/{REPO}/issues/249/comments?since=2026-11-05T11:00:00Z&per_page=100"])

    def test_a_failed_read_is_none(self):
        def boom(p):
            raise RuntimeError("gh api failed")
        self.assertIsNone(report.fetch(REPO, 249, MON, boom))
        self.assertIsNone(report.fetch(REPO, None, MON, boom))


if __name__ == "__main__":
    unittest.main()
