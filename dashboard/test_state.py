"""Tests for dashboard/state.py (#400). Run: python3 -m unittest discover -s dashboard"""
import datetime as dt
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import generate as g  # noqa: E402
import state as st  # noqa: E402
from test_generate import NOW, IDLE, REPO, ev, tracking, comment, issue, ts  # noqa: E402
from test_cap import spent, M  # noqa: E402
from test_rate import NUDGE, limits, runs  # noqa: E402

COST_WORDS = ("cost", "usd", "spend")


def model():
    """Priced sessions, one over its cap, a blocked one, a question and a PR: everything
    the page shows, and every place cost could leak from."""
    bot = "productswarm-builder[bot]"
    issues = [tracking(50, "s-over"), tracking(51, "s-blocked"), tracking(52, "s-done", state="closed"),
              issue(4, "Dashboard"), issue(26, "GOV-Q: x?", ["gov:question"])]
    comments = {50: [comment([ev("s-over", "heartbeat", e.pop("minutes_ago"), **e)
                              for e in [spent(M, issue=4)]], login=bot)],
                51: [comment([ev("s-blocked", "blocked", 2, issue=4, gov_question=26,
                                 cost_usd=3.5)])],
                52: [comment([ev("s-done", "stopped", 300, cost_usd=9.0)])]}
    prs = [{"number": 30, "title": "A PR", "url": "https://x/pull/30",
            "author": {"login": "app/productswarm-builder"}, "isDraft": False, "createdAt": ts(5),
            "reviewDecision": "", "closingIssuesReferences": [{"number": 4}], "headRefOid": "abc"}]
    return g.build({"repo": REPO, "issues": issues, "comments": comments, "prs": prs}, NOW, IDLE,
                   caps={"builder": 5.0})


def keys(x, path=""):
    """Every key in a nested dict/list, with its path."""
    if isinstance(x, dict):
        for k, v in x.items():
            yield f"{path}.{k}", k
            yield from keys(v, f"{path}.{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from keys(v, f"{path}[{i}]")


class Recording(dict):
    """A dict that notes which keys were read."""
    def __init__(self, d, seen):
        super().__init__(d)
        self.seen = seen

    def __getitem__(self, k):
        self.seen.add(k)
        return super().__getitem__(k)

    def get(self, k, default=None):
        self.seen.add(k)
        return super().get(k, default)


class StateTest(unittest.TestCase):
    def setUp(self):
        self.m = model()
        self.s = st.state(self.m)

    def test_top_level(self):
        self.assertEqual(self.s["schema"], 1)
        self.assertEqual(self.s["repo"], REPO)
        self.assertEqual(self.s["built_at"], "2026-11-02T12:00:00Z")
        for k in ("sessions", "needs_you", "prs", "gov_questions", "governance", "committees",
                  "progress", "reviewer_runs"):
            self.assertIn(k, self.s)

    def test_is_json(self):
        self.assertEqual(json.loads(json.dumps(self.s)), self.s)

    def test_model_has_cost_but_state_has_none(self):
        self.assertTrue(any(s["over_cap"] for s in self.m["sessions"]))   # the fixture is priced
        bad = [p for p, k in keys(self.s) if any(w in k.lower() for w in COST_WORDS)]
        self.assertEqual(bad, [])
        self.assertNotIn("over_cap", [i["kind"] for i in self.s["needs_you"]])
        self.assertNotIn("$", json.dumps(self.s))

    def test_session_fields_are_ones_the_page_renders(self):
        seen = set()
        g.session_rows(self.m, [Recording(s, seen) for s in self.m["sessions"]])
        for s in self.s["sessions"]:
            self.assertLessEqual(set(s), seen)
        self.assertEqual(set(self.s["sessions"][0]), set(st.SESSION_FIELDS))

    def test_no_html(self):
        self.assertNotIn("<", json.dumps(self.s))

    def test_timestamps_round_trip(self):
        for s_model, s_state in zip(self.m["sessions"], self.s["sessions"]):
            for k in ("last_ts", "started_ts"):
                self.assertEqual(g.parse_ts(s_state[k]), s_model[k])
        self.assertEqual(g.parse_ts(self.s["built_at"]), NOW)
        self.assertEqual(g.parse_ts(self.s["prs"][0]["created_ts"]), self.m["prs"][0]["created_ts"])

    def test_waiting_sessions_by_id(self):
        q = self.s["gov_questions"][0]
        self.assertEqual((q["number"], q["waiting"]), (26, ["s-blocked"]))

    def test_unknown_types_are_an_error(self):
        with self.assertRaises(TypeError):
            st.plain({"x": object()})

    def test_rfc3339_is_utc(self):
        t = dt.datetime(2026, 11, 2, 13, 0, tzinfo=dt.timezone(dt.timedelta(hours=1)))
        self.assertEqual(st.rfc3339(t), "2026-11-02T12:00:00Z")


class SkippedBuildTest(unittest.TestCase):
    """A skipped build writes neither the page nor state.json."""

    def run_main(self, env, answers):
        import tempfile, io, os, contextlib  # noqa: E401
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "index.html"
            with mock.patch.dict(os.environ, env, clear=False), \
                    mock.patch.object(g, "gh_json", side_effect=answers), \
                    contextlib.redirect_stdout(io.StringIO()):
                for k in ("GITHUB_EVENT_NAME", "GITHUB_TRIGGERING_ACTOR", "GITHUB_ACTOR"):
                    if k not in env:
                        os.environ.pop(k, None)
                rc = g.main(["--repo", REPO, "--out", str(out)])
            return rc, sorted(p.name for p in Path(tmp).iterdir())

    def test_low_allowance_writes_neither(self):
        self.assertEqual(self.run_main({}, [limits(graphql=3)]), (0, []))

    def test_nudge_too_soon_writes_neither(self):
        stamp = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        recent = {"jobs": [{"steps": [{"name": "deploy-pages", "conclusion": "success",
                                       "completed_at": stamp}]}]}
        self.assertEqual(self.run_main(NUDGE, [runs(7), recent]), (0, []))


if __name__ == "__main__":
    unittest.main()
