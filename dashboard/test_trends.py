"""Tests for dashboard/questions.py and dashboard/trends.py (#406).
Run: python3 -m unittest discover -s dashboard
"""
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import generate as g  # noqa: E402
import questions as q  # noqa: E402
import state  # noqa: E402
import trends as t  # noqa: E402

REPO = "open-agentos/productswarm"
OWNER = "mattmcalister"
NOW = dt.datetime(2026, 11, 5, 12, 0, tzinfo=dt.timezone.utc)   # a Thursday
DAYS = 14


def at(days_ago: float, hour: int = 9) -> str:
    d = NOW.date() - dt.timedelta(days=days_ago)
    return f"{d.isoformat()}T{hour:02d}:00:00Z"


def issue(n, created, state="open"):
    return {"number": n, "title": f"GOV-Q {n}", "state": state, "created_at": created,
            "html_url": f"https://x/{n}", "labels": [{"name": "gov:question"}]}


def labeled(name, when, actor=OWNER):
    return {"__typename": "LabeledEvent", "createdAt": when, "label": {"name": name},
            "actor": {"login": actor}}


def closed(when):
    return {"__typename": "ClosedEvent", "createdAt": when}


def history(issues=(), timelines=None, merged=(), records=(), days=DAYS):
    data = {"issues": list(issues), "timelines": timelines or {}, "merged": list(merged),
            "records": list(records)}
    return q.build(data, NOW, days, OWNER)


def sentence(h, name):
    return next(x for x in t.build(h)["trends"] if x["name"] == name)


class DecidedTest(unittest.TestCase):
    def test_owner_label_decides(self):
        when, how = q.decided([labeled("gov:ruled", at(1)), closed(at(0))], OWNER)
        self.assertEqual((when.isoformat(), how), ("2026-11-04T09:00:00+00:00", "label"))

    def test_first_of_ruled_or_ready(self):
        when, _ = q.decided([labeled("ready", at(1, 10)), labeled("gov:ruled", at(1, 8))], OWNER)
        self.assertEqual(when.hour, 8)

    def test_closed_with_no_label(self):
        when, how = q.decided([closed(at(2))], OWNER)
        self.assertEqual((when.date(), how), (dt.date(2026, 11, 3), "closed"))

    def test_someone_elses_label_is_not_a_decision(self):
        when, how = q.decided([labeled("ready", at(3), actor="productswarm-planner[bot]"),
                               labeled("gov:question", at(3)), closed(at(1))], OWNER)
        self.assertEqual((when.date(), how), (dt.date(2026, 11, 4), "closed"))

    def test_undecided(self):
        self.assertEqual(q.decided([labeled("ready", at(1), actor="someone")], OWNER), (None, None))

    def test_build_hours_and_window(self):
        h = history([issue(1, at(2, 9)), issue(2, at(20))],
                    {1: [closed(at(2, 15))]})
        self.assertEqual([x["number"] for x in h["questions"]], [1])   # #2 is before the window
        self.assertEqual((h["questions"][0]["hours"], h["questions"][0]["decided_by"]),
                         (6.0, "closed"))
        self.assertEqual(h["start"], dt.datetime(2026, 10, 23, tzinfo=dt.timezone.utc))


class QuestionsPerPrTest(unittest.TestCase):
    def h(self, asked_now, merged_now, asked_before=0, merged_before=0, days=DAYS):
        qs = [issue(i, at(1)) for i in range(asked_now)]
        qs += [issue(100 + i, at(9)) for i in range(asked_before)]
        merged = [at(2)] * merged_now + [at(10)] * merged_before
        return history(qs, merged=merged, days=days)

    def test_down_from(self):
        s = sentence(self.h(4, 5, 7, 5), "questions_per_merged_pr")
        self.assertEqual(s["sentence"],
                         "0.8 questions per merged PR this week, down from 1.4 the week before.")
        self.assertFalse(s["too_few"])

    def test_up_from(self):
        self.assertEqual(sentence(self.h(6, 4, 2, 4), "questions_per_merged_pr")["sentence"],
                         "1.5 questions per merged PR this week, up from 0.5 the week before.")

    def test_same_as(self):
        self.assertEqual(sentence(self.h(3, 3, 4, 4), "questions_per_merged_pr")["sentence"],
                         "1.0 questions per merged PR this week, the same as the week before.")

    def test_no_direction_when_week_before_is_thin(self):
        self.assertEqual(sentence(self.h(4, 5, 1, 2), "questions_per_merged_pr")["sentence"],
                         "0.8 questions per merged PR this week (4 questions, 5 PRs); "
                         "too few the week before to compare.")

    def test_no_direction_when_window_is_one_week(self):
        s = sentence(self.h(4, 5, days=7), "questions_per_merged_pr")["sentence"]
        self.assertIn("too few the week before to compare", s)

    def test_too_few(self):
        s = sentence(self.h(4, 2, 7, 5), "questions_per_merged_pr")
        self.assertEqual(s["sentence"], "Questions per merged PR: too few to tell (2 merged PRs this week).")
        self.assertTrue(s["too_few"])

    def test_series_has_gaps_on_days_without_merges(self):
        s = sentence(self.h(4, 5), "questions_per_merged_pr")["series"]
        self.assertEqual(len(s), DAYS)
        self.assertEqual(s[-3]["value"], 0.0)   # 5 merged, nothing asked that day
        self.assertIsNone(s[-2]["value"])       # 4 asked, nothing merged: no ratio, a gap
        self.assertIsNone(s[0]["value"])


class HoursToDecideTest(unittest.TestCase):
    def test_median(self):
        qs = [issue(i, at(3, 6)) for i in range(4)]
        tl = {0: [labeled("ready", at(3, 8))], 1: [labeled("gov:ruled", at(3, 10))],
              2: [closed(at(3, 18))], 3: []}
        s = sentence(history(qs, tl), "hours_to_decide")
        self.assertEqual(s["sentence"], "Median 4.0 hours to decide (3 questions; 1 not decided yet).")

    def test_too_few(self):
        qs = [issue(1, at(3, 6)), issue(2, at(3, 6))]
        s = sentence(history(qs, {1: [closed(at(3, 7))]}), "hours_to_decide")
        self.assertEqual(s["sentence"],
                         "Hours to decide: too few to tell (1 question decided; 1 not decided yet).")
        self.assertTrue(s["too_few"])

    def test_decided_by_close_with_no_label_counts(self):
        qs = [issue(i, at(2, 0)) for i in range(3)]
        tl = {i: [closed(at(2, 6 * (i + 1)))] for i in range(3)}
        s = sentence(history(qs, tl), "hours_to_decide")
        self.assertEqual(s["sentence"], "Median 12.0 hours to decide (3 questions).")
        self.assertEqual(s["series"][-3]["value"], 12.0)   # the day they were decided


class RecordsTest(unittest.TestCase):
    def dates(self, *ago):
        return [NOW.date() - dt.timedelta(days=a) for a in ago]

    def test_rate_and_none_since(self):
        s = sentence(history(records=self.dates(2, 2, 3, 3, 3, 30)), "records_per_day")
        self.assertEqual(s["sentence"], "0.4 records a day; none since 3 Nov.")
        self.assertEqual(s["series"][-3:], [{"date": dt.date(2026, 11, 3), "value": 2},
                                             {"date": dt.date(2026, 11, 4), "value": 0},
                                             {"date": dt.date(2026, 11, 5), "value": 0}])

    def test_latest_today(self):
        self.assertEqual(sentence(history(records=self.dates(0, 1, 2)), "records_per_day")["sentence"],
                         "0.2 records a day; the latest today.")

    def test_too_few(self):
        s = sentence(history(records=self.dates(5, 20)), "records_per_day")
        self.assertEqual(s["sentence"], "Records a day: too few to tell (1 in 14 days); none since 31 Oct.")
        self.assertTrue(s["too_few"])

    def test_no_records(self):
        self.assertEqual(sentence(history(), "records_per_day")["sentence"],
                         "Records a day: too few to tell (0 in 14 days); no records yet.")

    def test_record_dates_from_front_matter(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "GOV-0000-template.md").write_text("---\ndate: YYYY-MM-DD\n---\n")
            (d / "GOV-0002-b.md").write_text("---\nid: GOV-0002\ndate: 2026-11-03\n---\nx\n")
            (d / "GOV-0001-a.md").write_text('---\nid: GOV-0001\ndate: "2026-11-01"\n---\n')
            (d / "GOV-0003-c.md").write_text("---\nid: GOV-0003\n---\ndate: 2026-11-04\n")
            (d / "GOV-0004-d.md").write_text("---\ndate: 2026-13-01\n---\n")
            self.assertEqual(q.record_dates(d), [dt.date(2026, 11, 1), dt.date(2026, 11, 3)])

    def test_real_records_parse(self):
        self.assertGreaterEqual(len(q.record_dates()), 21)


class SparkTest(unittest.TestCase):
    def test_gap_and_text_alternative(self):
        tr = {"name": "hours_to_decide", "series": [
            {"date": dt.date(2026, 11, 1), "value": 1.0}, {"date": dt.date(2026, 11, 2), "value": 3.0},
            {"date": dt.date(2026, 11, 3), "value": None}, {"date": dt.date(2026, 11, 4), "value": 2.5}]}
        svg = t.spark(tr)
        self.assertEqual(svg.count("<polyline"), 1)   # days 1-2
        self.assertEqual(svg.count("<circle"), 1)     # day 4 stands alone after the gap
        self.assertIn('role="img"', svg)
        self.assertIn("<title>Median hours to decide by day, 1 Nov to 4 Nov: 1, 3, none, 2.5</title>", svg)
        self.assertNotIn("<line", svg)
        self.assertNotIn("<text", svg)

    def test_all_empty(self):
        tr = {"name": "records_per_day",
              "series": [{"date": dt.date(2026, 11, d), "value": 0} for d in (1, 2)]}
        self.assertIn("<polyline", t.spark(tr))


class PageTest(unittest.TestCase):
    def model(self):
        m = g.build({"repo": REPO, "issues": [], "comments": {}, "prs": []}, NOW,
                    dt.timedelta(minutes=15))
        m["trends"] = t.build(history([issue(1, at(1))], {1: [closed(at(1, 12))]},
                                      merged=[at(1)] * 3, records=[NOW.date()]))
        return m

    def test_desk_shows_three_sentences_with_sparklines(self):
        pages = g.render(self.model())
        desk = pages["index.html"]
        self.assertIn("<h2>What the numbers say</h2>", desk)
        self.assertEqual(desk.count('<svg class="spark"'), 3)
        self.assertIn("0.3 questions per merged PR this week", desk)
        self.assertNotIn("What the numbers say", pages["operations.html"])

    def test_no_panel_without_history(self):
        m = self.model()
        m["trends"] = None
        self.assertNotIn("What the numbers say", g.render(m)["index.html"])

    def test_state_json_has_series_and_sentences(self):
        s = json.loads(json.dumps(state.state(self.model())))["trends"]
        self.assertEqual([x["name"] for x in s["trends"]],
                         ["questions_per_merged_pr", "hours_to_decide", "records_per_day"])
        self.assertEqual(s["trends"][2]["series"][-1], {"date": "2026-11-05", "value": 1})
        self.assertEqual((s["days"], s["first_day"], s["min_count"]), (14, "2026-10-23", 3))
        self.assertTrue(all("sentence" in x for x in s["trends"]))


class FetchTest(unittest.TestCase):
    def test_calls(self):
        calls = []

        def items(path, jq):
            calls.append((path, jq))
            if path.startswith("search/"):
                return [{"number": 9, "pull_request": {"merged_at": at(1)}, "closed_at": at(1)}]
            return [issue(1, at(1)), issue(2, at(30)), {**issue(3, at(1)), "pull_request": {}}]

        with mock.patch.object(q.ghql, "batched", return_value={1: {"timelineItems": {
                "nodes": [closed(at(0))]}}}) as batched:
            raw = q.fetch(REPO, NOW, DAYS, items)
        self.assertEqual(calls, [
            (f"repos/{REPO}/issues?labels=gov:question&state=all&since=2026-10-23T00:00:00Z"
             "&per_page=100", ".[]"),
            (f"search/issues?q=repo:{REPO}+is:pr+is:merged+merged:>=2026-10-23&per_page=100",
             ".items[]")])
        self.assertEqual(batched.call_args.args[1], [1])   # only #1 was created in the window
        self.assertEqual(raw["timelines"], {1: [closed(at(0))]})
        self.assertEqual(raw["merged"], [at(1)])

    def test_no_questions_no_graphql(self):
        with mock.patch.object(q.ghql, "batched") as batched:
            q.fetch(REPO, NOW, DAYS, lambda path, jq: [])
        batched.assert_not_called()


if __name__ == "__main__":
    unittest.main()
