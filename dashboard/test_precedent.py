"""Tests for dashboard/precedent.py (#408). Run: python3 -m unittest discover -s dashboard"""
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import precedent as p  # noqa: E402
import state as st  # noqa: E402

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
OWNER = "mattmcalister"
BUILDER = "productswarm-builder[bot]"
REVIEWER = "productswarm-reviewer[bot]"
REPO = "open-agentos/productswarm"


def day(d, h=9):
    return dt.datetime(2026, 11, d, h, tzinfo=UTC)


def text(d, login, body, h=9):
    return {"ts": day(d, h), "login": login, "body": body}


def rec(rid, d, status="in-force"):
    return {"id": rid, "date": dt.date(2026, 11, d), "status": status, "file": f"{rid}-x.md"}


RECORDS = {r["id"]: r for r in (rec("GOV-0001", 1), rec("GOV-0020", 3), rec("GOV-0021", 4),
                                 rec("GOV-0005", 1, status="superseded"))}


class CitedTest(unittest.TestCase):
    def test_once_per_text(self):
        self.assertEqual(p.cited("per GOV-0021, and GOV-0021 again; GOV-0001"),
                         {"GOV-0021", "GOV-0001"})

    def test_signature_lines_dont_cite(self):
        body = "Done.\n\n-- docs (claude-opus-5-5)\n-- builder (per GOV-0007)\n"
        self.assertEqual(p.cited(body), set())
        # Only a whole signature line is dropped: prose starting with "--" still cites.
        self.assertEqual(p.cited("-- see GOV-0007 for why"), {"GOV-0007"})

    def test_needs_four_digits_and_word_edges(self):
        self.assertEqual(p.cited("GOV-001, GOV-00211, XGOV-0001, GOV-0002."), {"GOV-0002"})


class CountTest(unittest.TestCase):
    def test_only_on_or_after_the_record_was_made(self):
        found = [text(3, BUILDER, "GOV-0021 is coming"),       # the day before: not counted
                 text(4, BUILDER, "per GOV-0021", h=0),          # its first day: counted
                 text(5, BUILDER, "per GOV-0021")]
        c = p.count(found, RECORDS, OWNER)
        self.assertEqual(sorted(c["GOV-0021"]), ["2026-11-04", "2026-11-05"])
        self.assertEqual(c["GOV-0021"]["2026-11-04"]["n"], 1)

    def test_unknown_records_dont_count(self):
        self.assertEqual(p.count([text(4, BUILDER, "GOV-0099 and GOV-0000")], RECORDS, OWNER), {})

    def test_who_and_the_reviewer_column(self):
        found = [text(4, REVIEWER, "GOV-0001"), text(4, BUILDER, "GOV-0001"),
                 text(4, OWNER, "GOV-0001"), text(4, "someone", "GOV-0001")]
        c = p.count(found, RECORDS, OWNER)["GOV-0001"]["2026-11-04"]
        self.assertEqual(c, {"n": 4, "agents": 2, "owner": 1, "reviewer": 1})

    def test_no_owner_known(self):
        c = p.count([text(4, OWNER, "GOV-0001")], RECORDS, None)["GOV-0001"]["2026-11-04"]
        self.assertEqual(c, {"n": 1, "agents": 0, "owner": 0, "reviewer": 0})

    def test_adds_to_carried_counts_without_changing_them(self):
        kept = {"GOV-0001": {"2026-11-02": {"n": 5, "agents": 5, "owner": 0, "reviewer": 1}}}
        c = p.count([text(4, BUILDER, "GOV-0001")], RECORDS, OWNER, kept)
        self.assertEqual(c["GOV-0001"]["2026-11-02"]["n"], 5)
        self.assertEqual(c["GOV-0001"]["2026-11-04"]["n"], 1)
        self.assertNotIn("2026-11-04", kept["GOV-0001"])


class TextsTest(unittest.TestCase):
    def test_sources_and_what_is_left_out(self):
        since = day(4, 0)
        items = [{"number": 1, "created_at": "2026-11-04T10:00:00Z", "user": {"login": BUILDER},
                  "body": "issue body"},
                 {"number": 2, "created_at": "2026-11-04T10:00:00Z", "user": {"login": BUILDER},
                  "body": "tracking"},
                 {"number": 3, "created_at": "2026-11-03T10:00:00Z", "user": {"login": BUILDER},
                  "body": "too old"}]
        comments = [{"issue_url": "https://api.github.com/repos/x/y/issues/1",
                     "created_at": "2026-11-04T11:00:00Z", "user": {"login": OWNER}, "body": "comment"},
                    {"issue_url": "https://api.github.com/repos/x/y/issues/2",
                     "created_at": "2026-11-04T11:00:00Z", "user": {"login": BUILDER}, "body": "heartbeat"},
                    {"issue_url": "https://api.github.com/repos/x/y/issues/1",
                     "created_at": "2026-11-03T23:59:59Z", "user": {"login": OWNER}, "body": "edited old"}]
        review_comments = [{"path": "dashboard/x.py", "created_at": "2026-11-04T12:00:00Z",
                            "user": {"login": REVIEWER}, "body": "inline"},
                           {"path": "governance/decisions/GOV-0021-x.md",
                            "created_at": "2026-11-04T12:00:00Z", "user": {"login": REVIEWER},
                            "body": "on a record"}]
        reviews = {7: [{"login": REVIEWER, "body": "review", "ts": "2026-11-04T13:00:00Z"},
                       {"login": REVIEWER, "body": "pending", "ts": None}],
                   2: [{"login": REVIEWER, "body": "skipped issue", "ts": "2026-11-04T13:00:00Z"}]}
        got = p.texts(items, comments, review_comments, reviews, since, skip={2})
        self.assertEqual([t["body"] for t in got], ["issue body", "comment", "inline", "review"])


class CarryTest(unittest.TestCase):
    START = dt.date(2026, 10, 23)

    def prev(self, **kw):
        block = {"version": p.VERSION, "from": "2026-10-20", "counts": {
            "GOV-0001": {"2026-10-22": {"n": 9}, "2026-11-02": {"n": 3, "agents": 3},
                         "2026-11-05": {"n": 1}}}}
        block.update(kw)
        return {"built_at": "2026-11-05T08:00:00Z", "precedent": block}

    def test_keeps_days_before_the_build_day_and_inside_the_window(self):
        first, kept = p.carry(self.prev(), self.START, NOW)
        self.assertEqual(first, dt.date(2026, 11, 5))   # the build day is read again
        self.assertEqual(kept, {"GOV-0001": {"2026-11-02": {"n": 3, "agents": 3, "owner": 0,
                                                            "reviewer": 0}}})

    def test_reads_the_whole_window_without_a_usable_copy(self):
        for prev in (None, {}, self.prev(version=0), self.prev(counts=None),
                     self.prev(**{"from": "2026-10-25"}),   # doesn't reach back to the window's start
                     {**self.prev(), "built_at": "2026-11-06T00:00:00Z"},   # from the future
                     {**self.prev(), "built_at": "2026-10-01T00:00:00Z"}):  # older than the window
            self.assertEqual(p.carry(prev, self.START, NOW), (self.START, {}), prev)

    def test_fetch_reads_since_the_build_day(self):
        calls = []

        def gh_items(path):
            calls.append(path)
            if "/issues/comments" in path:
                return [{"issue_url": "u/issues/1", "created_at": "2026-11-05T09:00:00Z",
                         "user": {"login": BUILDER}, "body": "GOV-0001"}]
            return []

        class Q:
            @staticmethod
            def batched(*a):
                raise AssertionError("no PRs, no query")

        data = p.fetch(REPO, NOW, 14, [], set(), gh_items, Q, OWNER, self.prev())
        self.assertTrue(all("since=2026-11-05T00:00:00Z" in c for c in calls), calls)
        self.assertEqual(data["carried_from"], "2026-11-05T08:00:00Z")
        self.assertEqual(data["calls"], {"rest": 2, "graphql": 0})
        m = p.build(data, RECORDS, NOW, 14)
        self.assertEqual(m["totals"]["GOV-0001"]["n"], 4)   # 3 carried + 1 read

    def test_round_trips_through_state_json(self):
        data = {"start": self.START, "first": self.START, "kept": {}, "owner": OWNER,
                "texts": [text(2, BUILDER, "GOV-0001"), text(4, REVIEWER, "GOV-0021")]}
        block = st.plain(p.state(p.build(data, RECORDS, NOW, 14)))
        prev = json.loads(json.dumps({"built_at": "2026-11-05T08:00:00Z", "precedent": block}))
        first, kept = p.carry(prev, dt.date(2026, 10, 24), NOW.replace(hour=13))
        self.assertEqual(first, dt.date(2026, 11, 5))
        self.assertEqual(kept["GOV-0001"]["2026-11-02"]["n"], 1)
        self.assertEqual(kept["GOV-0021"]["2026-11-04"]["reviewer"], 1)


class FindingsTest(unittest.TestCase):
    START = dt.date(2026, 10, 23)

    def findings(self, found, records=RECORDS, start=START, days=14):
        return p.findings(p.count(found, records, OWNER), records, start, days)

    def test_newest_law_in_use(self):
        found = [text(4, BUILDER, "GOV-0021")] * 27 + [text(5, BUILDER, "GOV-0021")] * 3
        self.assertEqual(self.findings(found)[0],
                         "GOV-0021, the newest record, was cited 27 times on its first day "
                         "(2026-11-04) and 30 in all.")
        self.assertEqual(self.findings(found[:1])[0],
                         "GOV-0021, the newest record, was cited 1 time on its first day (2026-11-04).")

    def test_newest_made_before_the_window(self):
        got = self.findings([text(5, BUILDER, "GOV-0021")], start=dt.date(2026, 11, 5), days=1)
        self.assertEqual(got[0], "GOV-0021, the newest record, was cited 1 time today.")

    def test_share_by_agents(self):
        found = [text(4, BUILDER, "GOV-0001")] * 9 + [text(4, OWNER, "GOV-0001")]
        self.assertEqual(self.findings(found)[1],
                         "90% of citations are by agents (9 of 10); 10% are by the owner.")
        self.assertEqual(self.findings([])[1], "No record was cited in the last 14 days.")

    def test_quiet_records(self):
        # GOV-0005 isn't in force, so it isn't called quiet.
        self.assertEqual(self.findings([text(4, BUILDER, "GOV-0021")])[2],
                         "Not cited in the last 14 days: GOV-0001, GOV-0020.")
        self.assertEqual(self.findings([text(4, BUILDER, "GOV-0001 GOV-0020 GOV-0021")])[2],
                         "Every in-force record was cited in the last 14 days.")


class RenderTest(unittest.TestCase):
    def test_grid(self):
        data = {"start": dt.date(2026, 11, 2), "first": dt.date(2026, 11, 2), "kept": {},
                "owner": OWNER, "texts": [text(4, REVIEWER, "GOV-0021"), text(4, BUILDER, "GOV-0021")]}
        m = p.build(data, RECORDS, NOW, 4)
        page = p.render(m, REPO)
        self.assertIn('<div class="scroll"><table class="precedent">', page)   # its own box
        self.assertIn("<th>Record</th>", page)
        self.assertIn(">By reviewer</th>", page)
        self.assertIn('<li>GOV-0021, the newest record, was cited 2 times', page)
        row = next(r for r in page.split("<tr>") if ">GOV-0021<" in r)
        cells = row.split("</td>")
        # 11-02 and 11-03 are before it was made: blank. 11-04: 2. 11-05: none yet.
        self.assertTrue(cells[1].endswith(">") and cells[2].endswith(">"), row)
        self.assertTrue(cells[3].endswith(">2"), row)
        self.assertTrue(cells[4].endswith(">·"), row)
        self.assertEqual([c.rsplit(">", 1)[1] for c in cells[5:9]], ["2", "2", "0", "1"])
        self.assertIn("governance/decisions/GOV-0021-x.md", row)
        self.assertEqual(p.render(None, REPO), "")

    def test_grid_starts_at_the_first_record(self):
        data = {"start": dt.date(2026, 10, 23), "first": dt.date(2026, 10, 23), "kept": {},
                "owner": OWNER, "texts": []}
        m = p.build(data, RECORDS, NOW, 14)
        self.assertEqual((m["days"][0], m["days"][-1]), (dt.date(2026, 11, 1), NOW.date()))
        self.assertEqual(m["from"], dt.date(2026, 10, 23))   # what was read, for carrying


class RecordsTest(unittest.TestCase):
    def test_front_matter_and_template(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "GOV-0000-template.md").write_text("---\nid: GOV-0000\ndate: YYYY-MM-DD\n---\n")
            (d / "GOV-0003-x.md").write_text(
                "---\nid: GOV-0003\ntitle: \"t: x\"\nstatus: in-force\ndate: 2026-11-02\n"
                "classification:\n  date: 1999-01-01\n---\nbody\n")
            got = p.load_records(d)
        self.assertEqual(got, {"GOV-0003": {"id": "GOV-0003", "date": dt.date(2026, 11, 2),
                                            "status": "in-force", "file": "GOV-0003-x.md"}})

    def test_this_repos_records_all_have_dates(self):
        recs = p.load_records()
        self.assertIn("GOV-0021", recs)
        self.assertEqual(recs["GOV-0021"]["date"], dt.date(2026, 11, 4))


if __name__ == "__main__":
    unittest.main()
