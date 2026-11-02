"""Tests for dashboard/spend.py and the spend parts of the page.

Run: python3 -m unittest discover -s dashboard
"""
import datetime as dt
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import generate as g  # noqa: E402
import spend  # noqa: E402
from test_generate import NOW, IDLE, ev, tracking, comment, build  # noqa: E402

M = 1_000_000


def tok(i=0, o=0, cr=0, cc=0):
    return {"input": i, "output": o, "cache_read": cr, "cache_creation": cc}


class EstimateTest(unittest.TestCase):
    def test_each_token_type_priced(self):
        e = {"model": "claude-opus-5-5", "token_counts": tok(i=M, o=M, cr=M, cc=M)}
        self.assertAlmostEqual(spend.event_cost(e), 4 + 20 + 0.20 + 8)  # cache write at 1h rate

    def test_reported_cost_wins(self):
        e = {"model": "claude-opus-5-5", "token_counts": tok(i=M), "cost_usd": 1.5}
        self.assertEqual(spend.event_cost(e), 1.5)

    def test_model_suffixes_are_ignored(self):
        for m, base in (("claude-opus-4-8[1m]", "claude-opus-4-8"),
                        ("claude-haiku-4-5-20251001", "claude-haiku-4-5"),
                        ("Claude-Opus-4-8", "claude-opus-4-8")):
            self.assertEqual(spend.rates(m), spend.PRICES[base])

    def test_unknown_model_or_missing_tokens_is_none(self):
        self.assertIsNone(spend.event_cost({"model": "gpt-9", "token_counts": tok(i=M)}))
        self.assertIsNone(spend.event_cost({"model": "claude-opus-5-5"}))
        self.assertIsNone(spend.event_cost({"model": "claude-opus-5-5", "token_counts": {"input": 1}}))

    def test_session_cost_takes_latest_known(self):
        events = [{"model": "claude-opus-5-5", "token_counts": tok(o=M)},
                  {"model": "claude-opus-5-5"}]
        self.assertEqual(spend.session_cost(events), 20)
        self.assertIsNone(spend.session_cost([]))

    def test_usd(self):
        self.assertEqual([spend.usd(x) for x in (None, 0, 0.004, 0.42, 1234.5)],
                         ["—", "$0.00", "<$0.01", "$0.42", "$1,234.50"])


class DailyTest(unittest.TestCase):
    def test_increase_split_at_utc_midnight(self):
        def e(ts, out):
            return {"ts": ts, "model": "claude-opus-5-5", "token_counts": tok(o=out)}
        events = [e("2026-11-01T23:00:00Z", M), e("2026-11-01T23:50:00Z", 2 * M),
                  {"ts": "2026-11-02T00:10:00Z", "model": "claude-opus-5-5"},
                  e("2026-11-02T01:00:00Z", 3 * M)]
        d = spend.daily(events, g.parse_ts)
        self.assertEqual(d, {dt.date(2026, 11, 1): 40.0, dt.date(2026, 11, 2): 20.0})

    def test_counter_reset_is_not_negative(self):
        def e(ts, out):
            return {"ts": ts, "model": "claude-opus-5-5", "token_counts": tok(o=out)}
        d = spend.daily([e("2026-11-02T01:00:00Z", 2 * M), e("2026-11-02T02:00:00Z", M),
                         e("2026-11-02T03:00:00Z", 3 * M)], g.parse_ts)
        self.assertEqual(d, {dt.date(2026, 11, 2): 60.0})


class PageTest(unittest.TestCase):
    def model(self):
        a = [ev("s1", "session_started", 26 * 60, token_counts=tok()),
             ev("s1", "heartbeat", 25 * 60, token_counts=tok(o=M)),            # yesterday: $20
             ev("s1", "working_on", 5, issue=4, token_counts=tok(o=M, i=M))]   # today: +$4
        b = [ev("s2", "working_on", 3, issue=6, role="builder")]               # no tokens
        return build([tracking(50, "s1"), tracking(51, "s2")],
                     {50: [comment(a)], 51: [comment(b)]})

    def test_totals(self):
        m = self.model()
        self.assertAlmostEqual(m["spend"]["today"], 4.0)
        self.assertAlmostEqual(m["spend"]["per_day"][NOW.date() - dt.timedelta(days=1)], 20.0)
        self.assertEqual(len(m["spend"]["per_day"]), g.SPEND_DAYS)
        self.assertEqual([s["session_id"] for s in m["spend"]["unpriced"]], ["s2"])
        self.assertEqual({s["session_id"]: s["cost"] for s in m["sessions"]}, {"s1": 24.0, "s2": None})

    def test_page_states_method_and_figures(self):
        page = g.render(self.model())
        self.assertIn("spent today (est.)", page)
        self.assertIn("$24.00", page)
        self.assertIn("API list-price equivalent", page)
        self.assertIn(spend.PRICES_AS_OF, page)
        self.assertIn("Left out of totals", page)


if __name__ == "__main__":
    unittest.main()
