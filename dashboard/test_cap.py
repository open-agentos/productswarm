"""Tests for the warn-only spend cap (L4, #52; GOV-0008), with canned token counts.

Run: python3 -m unittest discover -s dashboard
"""
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import generate as g  # noqa: E402
from test_generate import NOW, IDLE, REPO, ev, tracking, comment  # noqa: E402

M = 1_000_000


def spent(output_tokens, minutes_ago=1, **fields):
    """An event whose cumulative tokens cost output_tokens x $20/M on claude-opus-5-5."""
    return {"token_counts": {"input": 0, "output": output_tokens, "cache_read": 0, "cache_creation": 0},
            "minutes_ago": minutes_ago, **fields}


def model(caps, sessions):
    """sessions: (sid, role, closed, [spent(...)...])."""
    issues, comments = [], {}
    for n, (sid, role, closed, evs) in enumerate(sessions, 50):
        t = tracking(n, sid, login=f"productswarm-{role}[bot]", state="closed" if closed else "open")
        issues.append(t)
        events = [ev(sid, "heartbeat", e.pop("minutes_ago"), role=role, **e) for e in evs]
        comments[n] = [comment(events, login=f"productswarm-{role}[bot]")]
    return g.build({"repo": REPO, "issues": issues, "comments": comments, "prs": []}, NOW, IDLE,
                   caps=caps)


class OverCapTest(unittest.TestCase):
    def sessions(self, caps):
        m = model(caps, [
            ("b-over", "builder", False, [spent(M // 2, 3), spent(M)]),        # $20 > $15
            ("b-under", "builder", False, [spent(M // 2)]),                    # $10
            ("r-way-over", "reviewer", False, [spent(3 * M)]),                 # $60 > $5
            ("d-nocap", "docs", False, [spent(10 * M)]),                       # $200, no cap
            ("b-stopped", "builder", True, [spent(5 * M)]),                    # stopped
            ("b-unpriced", "builder", False, [{"minutes_ago": 1}]),            # no tokens
        ])
        return m, {s["session_id"]: s for s in m["sessions"]}

    def test_flags_only_live_priced_sessions_past_their_roles_cap(self):
        m, s = self.sessions({"builder": 15, "reviewer": 5})
        self.assertEqual({k for k, v in s.items() if v["over_cap"]}, {"b-over", "r-way-over"})
        self.assertAlmostEqual(s["b-over"]["cost"], 20)
        self.assertEqual(s["b-over"]["cap"], 15)
        self.assertIsNone(s["d-nocap"]["cap"])          # no default cap (#45)
        self.assertFalse(s["b-unpriced"]["over_cap"])   # unknown spend is never over

    def test_exactly_at_cap_is_not_over(self):
        _, s = self.sessions({"builder": 20})
        self.assertFalse(s["b-over"]["over_cap"])

    def test_no_caps_no_flags(self):
        for caps in (None, {}):
            _, s = self.sessions(caps)
            self.assertFalse(any(v["over_cap"] for v in s.values()))

    def test_in_needs_you_last_and_furthest_over_first(self):
        m, _ = self.sessions({"builder": 15, "reviewer": 5})
        items = g.needs_you(m)
        over = [i for i in items if i["kind"] == "over_cap"]
        self.assertEqual([i["ref"] for i in over], ["reviewer session r-way-ov", "builder session b-over"])
        self.assertEqual(items[-len(over):], over)      # after every other kind
        self.assertEqual(g.needs_line(over[1], m["now"]),
                         "[over cap] builder session b-over · est. $20.00, cap $15.00; "
                         "warn only: swarm stop ends it (GOV-0008)")

    def test_page_marks_over_cap(self):
        m, _ = self.sessions({"builder": 15, "reviewer": 5})
        page = g.render(m)["operations.html"]
        self.assertIn("[over cap] reviewer session r-way-ov", page)
        self.assertIn('<span class="pill s-blocked">over cap $15.00</span>', page)


class LoadCapsTest(unittest.TestCase):
    def write(self, text):
        f = tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False)
        f.write(text)
        f.close()
        self.addCleanup(Path(f.name).unlink)
        return Path(f.name)

    def test_caps_by_role(self):
        p = self.write('[[session]]\nrole = "builder"\ncount = 2\nmodel = "m"\nspend_cap_usd = 15\n'
                       '[[session]]\nrole = "docs"\ncount = 1\nmodel = "m"\n')
        self.assertEqual(g.load_caps(p), {"builder": 15.0})

    def test_bad_or_missing_manifest_gives_no_caps(self):
        self.assertEqual(g.load_caps(self.write("[[session]\n")), {})
        self.assertEqual(g.load_caps(Path("/nonexistent/swarm.toml")), {})

    def test_repo_manifest_caps_load(self):   # #45, #110
        sys.path.insert(0, str(HERE.parent / "launcher"))
        import manifest
        want = {s.role: s.spend_cap_usd for s in manifest.load() if s.spend_cap_usd is not None}
        self.assertTrue(want, "swarm.toml sets per-role caps since #110")
        self.assertEqual(g.load_caps(), want)


if __name__ == "__main__":
    unittest.main()
