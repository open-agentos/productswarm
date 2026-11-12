"""Tests for the desk's trouble panel (#903): generate.py builds `swarm trouble`'s report
without the owner-acts sync and draws launcher/desk.py's panel under the plan."""
from __future__ import annotations

import datetime as dt
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import generate as g  # noqa: E402
import live  # noqa: E402
import state as st  # noqa: E402

sys.path.insert(0, str(HERE.parent / "launcher"))
import trouble  # noqa: E402

REPORT = json.loads((HERE.parent / "launcher" / "testdata" / "trouble.json").read_text())
NOW = dt.datetime(2026, 11, 12, 12, 0, tzinfo=dt.timezone.utc)


def model(t) -> dict:
    m = {k: None for k in ("report", "plan", "floor", "watcher", "grants", "wire", "trends",
                           "questions_went", "precedent", "committees")}
    return m | {"repo": "o/r", "trouble": t}


class PanelTest(unittest.TestCase):
    def test_on_the_desk_right_after_the_plan(self):
        names = list(g.desk_panels(model(REPORT)))
        self.assertEqual(names.index("trouble"), names.index("plan") + 1)

    def test_the_panel_refreshes_live(self):
        html = g.desk_panels(model(REPORT))["trouble"]
        self.assertIn("<h2>Trouble</h2>", html)
        self.assertIn("unmeasured: not known to be on track", html)
        tree = live.tree(html)   # raises if the markup leaves live.py's allow lists
        self.assertTrue(tree)
        self.assertEqual(live.trees({"trouble": html})["trouble"], tree)

    def test_a_failed_read_says_so_and_the_desk_still_builds(self):
        html = g.trouble_panel({"error": "gh: HTTP 502 <bad>"})
        self.assertIn('<p class="error">not read: gh: HTTP 502 &lt;bad&gt;</p>', html)
        self.assertTrue(live.tree(html))

    def test_off_is_an_empty_box(self):
        self.assertEqual(g.trouble_panel(None), "")


class FetchTest(unittest.TestCase):
    def test_reads_without_the_acts_sync(self):
        seen = {}

        def gather(launcher, repo, owner, manifest_path, **kw):
            seen.update(kw, repo=repo)
            return "data"

        with mock.patch.object(trouble, "gather", gather), \
                mock.patch.object(trouble, "report", lambda d: {"scopes": [], "from": d}):
            r = g.fetch_trouble("o/r", NOW)
        self.assertEqual(r, {"scopes": [], "from": "data"})
        self.assertEqual(seen, {"now": NOW, "sync_acts": False, "repo": "o/r"})

    def test_github_down_is_an_error_not_a_failed_build(self):
        with mock.patch.object(trouble, "gather", side_effect=RuntimeError("gh: rate limited")):
            self.assertEqual(g.fetch_trouble("o/r", NOW), {"error": "gh: rate limited"})

    def test_state_json_carries_the_box_but_no_spend(self):
        from test_live import desk_model
        r = json.loads(json.dumps(REPORT))
        r["scopes"][0]["spend_usd"] = 98.76
        s = st.state(desk_model() | {"trouble": r})
        self.assertIsInstance(s["desk"]["trouble"], list)
        self.assertNotIn("trouble", {k for k in s if k != "desk"})
        self.assertNotIn("98.76", json.dumps(s))   # GOV-0014: no cost in state.json
        self.assertNotIn("98.76", g.trouble_panel(r))   # nor on the public page


if __name__ == "__main__":
    unittest.main()
