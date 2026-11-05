"""Tests for dashboard/governance.py (#355). Run: python3 -m unittest discover -s dashboard"""
import datetime as dt
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import generate as g  # noqa: E402
import governance as gv  # noqa: E402

REPO = "open-agentos/productswarm"
NOW = dt.datetime(2026, 11, 4, 12, 0, tzinfo=dt.timezone.utc)
TODAY = NOW.date()

INDEX = """# Governance index

| ID | Ruling (one line) | Domain | Shape | Status | Review by |
|---|---|---|---|---|---|
| [GOV-0001](decisions/GOV-0001-a.md) | Plain ruling | governance | authoritative | in-force | 2027-01-31 |
| [GOV-0002](decisions/GOV-0002-b.md) | Uses `a | b` in code and an escaped \\| pipe | security | authoritative | in-force | 2026-11-30 |
| [GOV-0003](decisions/GOV-0003-c.md) | Expired | architecture | committee | in-force | 2026-10-01 |
| [GOV-0010](decisions/GOV-0010-d.md) | Newest | spend | authoritative | in-force | soon-ish |
| not a record | x | x | x | x | x |
"""


def body(domain="security", blocking="no — proceeding on default", ttl="2026-11-18",
         shape="authoritative"):
    return (f"### Domain\n\n{domain}\n\n### Context\n\nx\n\n### Blocking?\n\n{blocking}\n\n"
            f"### Time to live\n\n{ttl}\n\n### Suggested shape\n\n{shape}\n")


def question(n, labels=(), state="open", closed_at=None, **kw):
    return {"number": n, "title": f"GOV-Q: q{n}", "state": state, "closed_at": closed_at,
            "user": {"login": "productswarm-builder[bot]"}, "html_url": f"https://x/{n}",
            "labels": [{"name": lb} for lb in ("gov:question", *labels)],
            "created_at": "2026-11-01T12:00:00Z", "body": body(**kw)}


def build(issues, index=INDEX):
    return g.build({"repo": REPO, "issues": issues, "comments": {}, "prs": [], "index": index},
                   NOW, dt.timedelta(minutes=15), window=14)


class IndexTest(unittest.TestCase):
    def test_parses_rows_with_pipes_in_code_and_escaped(self):
        rows = gv.parse_index(INDEX)
        self.assertEqual([r["id"] for r in rows], ["GOV-0001", "GOV-0002", "GOV-0003", "GOV-0010"])
        r = rows[1]
        self.assertEqual(r["ruling"], "Uses `a | b` in code and an escaped | pipe")
        self.assertEqual((r["domain"], r["shape"], r["status"], r["review_by"]),
                         ("security", "authoritative", "in-force", dt.date(2026, 11, 30)))
        self.assertEqual(r["file"], "decisions/GOV-0002-b.md")

    def test_unparseable_review_by_is_none(self):
        self.assertIsNone(gv.parse_index(INDEX)[3]["review_by"])

    def test_recent_newest_first_with_flags(self):
        recent = gv.recent_records(gv.parse_index(INDEX), TODAY, n=3)
        self.assertEqual([r["id"] for r in recent], ["GOV-0010", "GOV-0003", "GOV-0002"])
        self.assertEqual([r["flag"] for r in recent], [None, "passed", "soon"])

    def test_older_flagged_records_still_shown(self):
        older = gv.older_flagged(gv.parse_index(INDEX), TODAY, n=1)
        self.assertEqual([(r["id"], r["flag"]) for r in older],
                         [("GOV-0003", "passed"), ("GOV-0002", "soon")])

    def test_review_flag(self):
        self.assertEqual(gv.review_flag(dt.date(2026, 11, 3), TODAY), "passed")
        self.assertEqual(gv.review_flag(TODAY, TODAY), "soon")
        self.assertEqual(gv.review_flag(TODAY + dt.timedelta(days=30), TODAY), "soon")
        self.assertIsNone(gv.review_flag(TODAY + dt.timedelta(days=31), TODAY))

    def test_real_index_parses(self):
        rows = gv.parse_index(gv.INDEX.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(rows), 21)
        self.assertTrue(all(r["review_by"] for r in rows))


class QuestionTest(unittest.TestCase):
    def test_shape_label_wins_over_suggested(self):
        f = gv.question_fields(body(shape="committee"), ["gov:shape/consent"])
        self.assertEqual((f["shape"], f["shape_suggested"]), ("consent", False))

    def test_suggested_shape_only(self):
        f = gv.question_fields(body(shape="committee"), [])
        self.assertEqual((f["shape"], f["shape_suggested"], f["domain"]),
                         ("committee", True, "security"))

    def test_blocking_from_body_or_label(self):
        self.assertFalse(gv.question_fields(body(), [])["blocking"])
        self.assertTrue(gv.question_fields(body(blocking="yes — work stopped on this path"),
                                           [])["blocking"])
        self.assertTrue(gv.question_fields(body(), ["gov:blocking"])["blocking"])
        self.assertIsNone(gv.question_fields("free text", [])["blocking"])

    def test_ttl_states(self):
        m = build([question(1), question(2, ttl="2026-11-01"), question(3, ttl="_No response_"),
                   question(4, ttl="when #9 merges")])
        q = {x["number"]: x for x in m["governance"]["questions"]}
        self.assertEqual((q[1]["days_left"], q[1]["past_ttl"]), (14, False))
        self.assertEqual((q[2]["days_left"], q[2]["past_ttl"]), (-3, True))
        self.assertEqual((q[3]["ttl"], q[3]["ttl_date"], q[3]["past_ttl"]), (None, None, False))
        self.assertEqual((q[4]["ttl"], q[4]["ttl_date"]), ("when #9 merges", None))

    def test_counts(self):
        m = build([question(1), question(2, domain="spend"), question(3, labels=["gov:shape/vote"])])
        self.assertEqual(m["governance"]["by_shape"], [("authoritative", 2), ("vote", 1)])
        self.assertEqual(m["governance"]["by_domain"], [("security", 2), ("spend", 1)])


class LapsedTest(unittest.TestCase):
    def test_open_and_recently_closed_only(self):
        m = build([question(1, labels=["gov:lapsed"]),
                   question(2, labels=["gov:lapsed"], state="closed", closed_at="2026-11-01T00:00:00Z"),
                   question(3, labels=["gov:lapsed"], state="closed", closed_at="2026-10-01T00:00:00Z"),
                   question(4)])
        self.assertEqual([q["number"] for q in m["governance"]["lapsed"]], [2, 1])
        self.assertEqual(m["governance"]["lapsed"][0]["ttl"], "2026-11-18")


class PageTest(unittest.TestCase):
    def test_section_replaces_old_table(self):
        page = g.render(build([question(5, labels=["gov:deliberating"], ttl="2026-11-01"),
                               question(6, labels=["gov:lapsed"])]))["decisions.html"]
        self.assertNotIn("<h2>Open gov questions</h2>", page)
        self.assertIn("<h2>Governance</h2>", page)
        self.assertIn('href="https://github.com/open-agentos/productswarm/blob/main/governance/'
                      'decisions/GOV-0010-d.md">GOV-0010</a>', page)
        self.assertLess(page.index("GOV-0010"), page.index("GOV-0003"))
        self.assertIn("review date passed", page)
        self.assertIn("not precedent until re-affirmed", page)
        self.assertIn("<code>a | b</code>", page)
        self.assertNotIn("Older records to review", page)   # the full log hides none (#401)
        self.assertIn("past TTL", page)
        self.assertIn("gov:deliberating", page)   # labels the old table showed stay
        self.assertIn("By shape: authoritative 2", page)
        self.assertIn("is not precedent", page)
        self.assertNotIn("<script", page)

    def test_missing_index_and_no_questions(self):
        page = g.render(build([], index=None))["decisions.html"]
        self.assertIn("governance/INDEX.md not found", page)
        self.assertIn("None open or closed in the last 14 days.", page)


if __name__ == "__main__":
    unittest.main()
