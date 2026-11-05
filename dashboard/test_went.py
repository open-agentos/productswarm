"""Tests for the desk's "How the questions went" (#407, questions.went and render_went).
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
import committees  # noqa: E402
import generate as g  # noqa: E402
import questions as q  # noqa: E402
import state  # noqa: E402

REPO = "open-agentos/productswarm"
OWNER = "mattmcalister"
NOW = dt.datetime(2026, 11, 5, 12, 0, tzinfo=dt.timezone.utc)
DAYS = 14
BOT = "productswarm-builder[bot]"


def at(days_ago: float, hour: int = 9) -> str:
    d = NOW.date() - dt.timedelta(days=days_ago)
    return f"{d.isoformat()}T{hour:02d}:00:00Z"


def issue(n, author=BOT, raised=None, labels=(), state="open", created=None):
    body = f"### Domain\n\nspend\n\n### Raised by\n\n{raised}\n" if raised else "### Domain\n\nspend\n"
    return {"number": n, "title": f"GOV-Q {n}", "state": state, "created_at": created or at(2),
            "html_url": f"https://x/{n}", "user": {"login": author}, "body": body,
            "labels": [{"name": "gov:question"}] + [{"name": x} for x in labels]}


def labeled(name, when, actor=OWNER):
    return {"__typename": "LabeledEvent", "createdAt": when, "label": {"name": name},
            "actor": {"login": actor}}


def closed(when):
    return {"__typename": "ClosedEvent", "createdAt": when}


def history(issues, timelines=None):
    return q.build({"issues": issues, "timelines": timelines or {}, "merged": [], "records": []},
                   NOW, DAYS, OWNER)


def rec(rid, shape="authoritative"):
    return {"id": rid, "status": "in-force", "file": f"{rid}-x.md", "date": "2026-11-04",
            "shape": shape}


def cats(w):
    return {r["number"]: (r["asked_by"], r["decided_by"], r["became"]) for r in w["questions"]}


class RaisedByTest(unittest.TestCase):
    def test_reads_the_template_answer(self):
        self.assertEqual(q.raised_by("### Raised by\n\nowner (drafted by the coordinator)\n\n### X\n"),
                         "owner (drafted by the coordinator)")
        self.assertIsNone(q.raised_by("no such heading"))
        self.assertIsNone(q.raised_by(None))


class AskedByTest(unittest.TestCase):
    def asked(self, it):
        return cats(q.went(history([it]), {}, set(), OWNER))[it["number"]][0]

    def test_bot_author_is_agents(self):
        self.assertEqual(self.asked(issue(1, raised="builder, on #407")), "agents")

    def test_owner_author_is_owner(self):
        self.assertEqual(self.asked(issue(1, author=OWNER)), "owner")

    def test_raised_by_owner_is_owner_even_from_a_bot(self):
        # #396: opened by a bot, "Raised by: owner (drafted by the coordinator)".
        self.assertEqual(self.asked(issue(1, raised="owner (drafted by the coordinator)")), "owner")
        self.assertEqual(self.asked(issue(2, raised="@mattmcalister")), "owner")

    def test_owner_word_later_in_the_line_does_not_count(self):
        self.assertEqual(self.asked(issue(1, raised="builder, for the owner")), "agents")

    def test_someone_else(self):
        self.assertEqual(self.asked(issue(1, author="a-human", raised="me")), "other")


class DecidedAndBecameTest(unittest.TestCase):
    def setUp(self):
        issues = [
            issue(1),                                                 # nothing has happened
            issue(2, state="closed"),                                 # ruled, record merged
            issue(3, labels=["gov:ruled"]),                           # ruled, no record yet
            issue(4, labels=["gov:lapsed"], state="closed"),          # lapsed
            issue(5, state="closed"),                                 # committee Discussion
            issue(6, state="closed"),                                 # record shape: committee
            issue(7, labels=["ready"]),                               # ready added by an agent
            issue(8, state="closed"),                                 # closed, no label or record
        ]
        timelines = {2: [labeled("gov:ruled", at(1)), closed(at(0))],
                     3: [labeled("gov:ruled", at(1))],
                     4: [labeled("gov:lapsed", at(1), actor=BOT), closed(at(1))],
                     5: [labeled("gov:ruled", at(1)), closed(at(0))],
                     6: [closed(at(0))],
                     7: [labeled("ready", at(1), actor=BOT)],
                     8: [closed(at(1))]}
        records = {2: rec("GOV-0030"), 5: rec("GOV-0031"), 6: rec("GOV-0032", shape="committee")}
        self.w = q.went(history(issues, timelines), records, {5}, OWNER)
        self.c = cats(self.w)

    def test_each_question(self):
        self.assertEqual({n: c[1:] for n, c in self.c.items()}, {
            1: ("open", "nothing"),
            2: ("owner", "record"),
            3: ("owner", "direction"),     # ruled with no record: direction only (GOV-0006)
            4: ("lapsed", "nothing"),
            5: ("committee", "record"),
            6: ("committee", "record"),
            7: ("open", "nothing"),        # an agent's `ready` decides nothing
            8: ("owner", "nothing"),
        })

    def test_counts(self):
        self.assertEqual(self.w["total"], 8)
        self.assertEqual(self.w["decided_by"], {"owner": 3, "committee": 2, "lapsed": 1, "open": 2})
        self.assertEqual(self.w["became"], {"record": 3, "direction": 1, "nothing": 4})
        self.assertEqual(self.w["asked_by"], {"agents": 8, "owner": 0, "other": 0})

    def test_sentences(self):
        html = q.render_went(self.w)
        self.assertIn("<h2>How the questions went</h2>", html)
        self.assertIn("8 questions asked in the last 14 days (from 23 Oct).", html)
        self.assertIn("Asked by: agents 8, the owner 0.", html)   # "someone else" only when > 0
        self.assertIn("Decided by: the owner 3, a committee 2, lapsed 1, still open 2.", html)
        self.assertIn("Became: a record 3, direction only 1, nothing yet 4.", html)
        self.assertEqual(html.count('class="went-bar"'), 3)
        self.assertIn('<span class="committee" style="flex:2">', html)


class EmptyTest(unittest.TestCase):
    def test_no_history_no_panel(self):
        self.assertIsNone(q.went(None, {}, set(), OWNER))
        self.assertEqual(q.render_went(None), "")

    def test_no_questions(self):
        w = q.went(history([]), {}, set(), OWNER)
        self.assertEqual(w["total"], 0)
        html = q.render_went(w)
        self.assertIn("0 questions asked", html)
        self.assertIn('<span class="went-bar" aria-hidden="true"></span>', html)


class RecordsShapeTest(unittest.TestCase):
    def test_records_carry_shape(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "GOV-0040-x.md").write_text(
                '---\nid: GOV-0040\nstatus: in-force\nquestion: "#311"\nshape: committee\n'
                "date: 2026-11-04\n---\nbody\n")
            self.assertEqual(committees.records(Path(d))[311]["shape"], "committee")


class PageTest(unittest.TestCase):
    def model(self):
        data = {"repo": REPO, "issues": [], "comments": {}, "prs": [],
                "questions": {"issues": [issue(1), issue(2, author=OWNER, state="closed")],
                              "timelines": {2: [labeled("ready", at(1)), closed(at(1))]},
                              "merged": [], "records": []}}
        with mock.patch.object(committees, "records", return_value={2: rec("GOV-0050")}), \
                mock.patch.object(committees, "owner_login", return_value=OWNER):
            return g.build(data, NOW, dt.timedelta(minutes=15))

    def test_desk_shows_the_three_breakdowns_after_the_trends(self):
        pages = g.render(self.model())
        desk = pages["index.html"]
        self.assertIn("Asked by: agents 1, the owner 1.", desk)
        self.assertIn("Became: a record 1, direction only 0, nothing yet 1.", desk)
        self.assertLess(desk.index("What the numbers say"), desk.index("How the questions went"))
        self.assertNotIn("How the questions went", pages["operations.html"])

    def test_state_json_has_the_counts(self):
        s = json.loads(json.dumps(state.state(self.model())))["questions_went"]
        self.assertEqual(s["asked_by"], {"agents": 1, "owner": 1, "other": 0})
        self.assertEqual(s["decided_by"], {"owner": 1, "committee": 0, "lapsed": 0, "open": 1})
        self.assertEqual(s["became"], {"record": 1, "direction": 0, "nothing": 1})
        self.assertEqual((s["total"], s["days"], s["first_day"]), (2, 14, "2026-10-23"))
        self.assertEqual(s["questions"][1],
                         {"number": 2, "asked_by": "owner", "decided_by": "owner", "became": "record"})

    def test_no_panel_without_history(self):
        m = g.build({"repo": REPO, "issues": [], "comments": {}, "prs": []}, NOW,
                    dt.timedelta(minutes=15))
        self.assertIsNone(m["questions_went"])
        self.assertNotIn("How the questions went", g.render(m)["index.html"])


if __name__ == "__main__":
    unittest.main()
