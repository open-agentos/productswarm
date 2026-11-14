"""Tests for Effort on the Desk (#1013): the Bridge's Goal-card counts, the desk's Effort panel
and effort.html, from a fixture cache. Run: python3 -m unittest discover -s dashboard"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bridge  # noqa: E402
import effort  # noqa: E402
import generate as g  # noqa: E402
import layout  # noqa: E402
import live  # noqa: E402
import state  # noqa: E402
import test_bridge  # noqa: E402

REPO = "o/r"
NOW = dt.datetime(2026, 11, 13, 12, 0, tzinfo=dt.timezone.utc)
FIXTURE = HERE.parent / "launcher" / "testdata" / "effort.json"


def goal(n, title):
    return test_bridge.scope(n, title)


def model(cache=None, scopes=None) -> dict:
    """The Bridge's test model, with the effort cache built in as generate.build() does."""
    m = test_bridge.model()
    m["now"] = NOW
    m["trouble"]["scopes"] = scopes if scopes is not None else [
        goal(987, "M7: The Desk shows what kind of work the swarm ships"),
        goal(683, "M1: Daily report runs without the owner"),
        {**goal(687, "Engine host"), "type": "Area"}]
    m["effort"] = effort.build(cache, REPO, NOW, effort.goals_of(m))
    return m


class CacheTest(unittest.TestCase):
    def test_missing_is_none_and_bad_json_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(effort.load(Path(d) / "effort.json"))
            (Path(d) / "effort.json").write_text("{not json")
            self.assertIn("isn't JSON", effort.load(Path(d) / "effort.json")["error"])
            (Path(d) / "effort.json").write_text("[]")
            self.assertIn('no "prs"', effort.load(Path(d) / "effort.json")["error"])

    def test_items_skip_unknown_labels_missing_times_and_bad_keys(self):
        prs, bad = effort.items(effort.load(FIXTURE), REPO)
        self.assertEqual(bad, 3)   # 993 (bogus label), 994 (no merge time), "x"
        self.assertNotIn(993, [p["number"] for p in prs])
        self.assertEqual(prs[0]["number"], 1006)   # newest first

    def test_goal_refs(self):
        self.assertEqual(effort.goal_ref(987, REPO), "o/r#987")
        self.assertEqual(effort.goal_ref("#987", REPO), "o/r#987")
        self.assertEqual(effort.goal_ref("a/b#5", REPO), "a/b#5")
        self.assertIsNone(effort.goal_ref(None, REPO))
        self.assertIsNone(effort.goal_ref("M7", REPO))


class ModelTest(unittest.TestCase):
    def setUp(self):
        self.e = model(effort.load(FIXTURE))["effort"]

    def test_windows_per_goal(self):
        m7 = self.e["goals"][0]
        self.assertEqual(m7["ref"], "o/r#987")
        self.assertEqual(m7["this_counts"]["total"], 5)
        self.assertEqual(m7["this_counts"]["by"], {"capability": 2, "upkeep": 1, "governance": 1, "knowledge": 1})
        self.assertEqual(m7["this_counts"]["fixes"], 1)
        self.assertEqual([p["number"] for p in m7["last"]], [990, 991])

    def test_only_goals_get_bars(self):
        self.assertEqual([r["ref"] for r in self.e["goals"]], ["o/r#987", "o/r#683"])   # not the Area

    def test_trend_is_capability_share_by_week_across_all_prs(self):
        t = self.e["trend"]
        self.assertEqual(len(t), effort.TREND_WEEKS)
        self.assertEqual(t[-1], {"week": dt.date(2026, 11, 9), "capability": 3, "total": 8})
        self.assertEqual(t[-2], {"week": dt.date(2026, 11, 2), "capability": 2, "total": 5})
        self.assertEqual(sum(x["total"] for x in t), 14)   # all readable PRs, any Goal or none

    def test_upkeep_risk_is_more_than_half(self):
        self.assertEqual(effort.risks(self.e), [
            "Upkeep risk: o/r#683: 2 of 3 PRs merged in the last 7 days were upkeep (more than half)."])
        # o/r#684's 1 of 2 is exactly half: no risk. o/r#987's 1 of 5 isn't either.
        self.assertFalse(effort.upkeep_heavy(self.e["by_goal"]["o/r#684"]))
        self.assertFalse(effort.upkeep_heavy(effort.counts([])))

    def test_daily_text(self):
        text = effort.daily_text(self.e)
        self.assertIn("classify/cache/effort.json", text)
        self.assertTrue(text.endswith("(more than half)."), text)
        self.assertIn("none checked", effort.daily_text(model(None)["effort"]))
        self.assertTrue(effort.daily_text(model({"prs": {}})["effort"]).endswith("  none"))


class BridgeTest(unittest.TestCase):
    def test_goal_cards_carry_the_counts(self):
        flights = bridge.in_flight(model(effort.load(FIXTURE)))
        by = {f["url"].rsplit("/", 1)[-1]: f for f in flights}
        self.assertEqual(by["987"]["effort"],
                         "5 PRs · 2 capability · 1 upkeep · 1 governance · 1 knowledge · 1 fix")
        self.assertEqual(by["683"]["effort"],
                         "3 PRs · 1 capability · 2 upkeep · 0 governance · 0 knowledge · 1 fix")
        self.assertNotIn("effort", by["687"])   # an Area gets no counts
        html = bridge.render(bridge.build(model(effort.load(FIXTURE)), "owner"))
        self.assertIn("5 PRs · 2 capability", html)

    def test_no_cache_adds_nothing(self):
        flights = bridge.in_flight(model(None))
        self.assertTrue(flights)
        self.assertFalse(any("effort" in f for f in flights))

    def test_a_goal_with_nothing_merged_reads_zero(self):
        m = model(effort.load(FIXTURE), scopes=[goal(1, "M9: Quiet")])
        self.assertTrue(bridge.in_flight(m)[0]["effort"].startswith("0 PRs · 0 capability"))


class DeskTest(unittest.TestCase):
    def setUp(self):
        self.m = model(effort.load(FIXTURE))
        self.html = effort.render(self.m["effort"])

    def test_bars_trend_and_links(self):
        self.assertIn("<h2>Effort</h2>", self.html)
        self.assertEqual(self.html.count('class="ef-row"'), 4)   # 2 Goals, this window and the last
        self.assertIn('href="effort.html#e-o-r-987-this-capability"', self.html)
        self.assertIn('href="effort.html#e-o-r-987-last-upkeep"', self.html)
        self.assertIn('class="ef-fix" style="width:50%"', self.html)   # 1 of 987's 2 capability PRs
        # The widest bar is 5 PRs: one of 987's two capability PRs is 20% of it.
        self.assertIn('class="ef-seg ef-capability" style="width:40%"', self.html)
        self.assertIn("<polyline", self.html)
        self.assertIn("This week 38% of 8 merged PRs were capability", self.html)
        self.assertIn("the paths baseline", self.html)
        self.assertIn("3 cache entries left out as unreadable", self.html)

    def test_panel_converts_for_the_live_refresh(self):
        live.tree(self.html)   # raises on a tag, attribute or link the live refresh refuses
        live.tree(effort.render(model(None)["effort"]))

    def test_empty_state_when_the_cache_is_missing(self):
        html = effort.render(model(None)["effort"])
        self.assertIn("isn't there", html)
        self.assertNotIn("ef-row", html)
        self.assertIn("couldn't be read", effort.render(model({"error": "bad"})["effort"]))

    def test_no_new_colours(self):
        css = layout.CSS[layout.CSS.index("/* Effort (#1013)"):]
        css = css[css.index("*/"):]
        self.assertEqual(re.findall(r"#[0-9A-Fa-f]{3,6}\b", css), [])   # only layout.py's variables
        self.assertEqual(set(re.findall(r"var\(--(\w+)\)", css)) - set(layout.PALETTE), set())
        self.assertNotRegex(self.html, r"#[0-9A-Fa-f]{6}")

    def test_phone_width(self):
        # Bars are shares of the row, the line scales down, and nothing sets a fixed page width.
        self.assertNotRegex(self.html, r'style="[^"]*width:\d+px')
        self.assertIn("svg.ef-line { display:block; max-width:100%; height:auto;", layout.CSS)

    def test_effort_page_lists_each_segments_prs(self):
        body = effort.page_body(self.m["effort"], REPO)
        for frag in re.findall(r'effort\.html#([\w-]+)', self.html):
            self.assertIn(f'id="{frag}"', body)
        sec = body[body.index('id="e-o-r-987-this-capability"'):]
        sec = sec[:sec.index("</ul>")]
        self.assertIn("#1001", sec)
        self.assertIn("#1002", sec)
        self.assertIn("· fix", sec)
        self.assertIn("isn't there", effort.page_body(model(None)["effort"], REPO))


class GenerateTest(unittest.TestCase):
    """The pages build from the cache with no model credential and no network beyond today's."""

    def test_build_and_render_from_a_fixture(self):
        # generate.build() as main() calls it, with only the cache and the trouble report: no
        # model, no credential and no API call (the fixture data stands in for fetch()).
        trouble = {"scopes": [goal(987, "M7: The Desk shows what kind of work the swarm ships")]}
        m = g.build({"repo": REPO, "issues": [], "comments": {}, "prs": [], "trouble": trouble,
                     "effort": effort.load(FIXTURE)}, NOW, dt.timedelta(minutes=15))
        pages = g.render(m)
        self.assertIn("ef-row", pages["index.html"])
        self.assertIn('data-panel="effort"', pages["index.html"])
        self.assertIn('id="e-o-r-987-this-capability"', pages["effort.html"])
        self.assertIn("5 PRs · 2 capability", pages["bridge.html"])
        self.assertIsNotNone(state.state(m)["desk"]["effort"])   # the live refresh can draw it
        self.assertEqual(state.state(m)["effort"]["goals"][0]["this"]["total"], 5)

    def test_build_without_a_cache_shows_the_empty_state(self):
        m = g.build({"repo": REPO, "issues": [], "comments": {}, "prs": []}, NOW, dt.timedelta(minutes=15))
        self.assertIn("isn't there", g.render(m)["index.html"])

    def test_state_json_carries_counts_not_html(self):
        s = effort.state(model(effort.load(FIXTURE))["effort"])
        self.assertEqual(s["goals"][0]["this"]["total"], 5)
        self.assertEqual(s["trend"][-1], {"week": "2026-11-09", "capability": 3, "total": 8})
        json.dumps(s)
        self.assertEqual(effort.state(model(None)["effort"]), {"status": "missing", "error": None})


if __name__ == "__main__":
    unittest.main()
