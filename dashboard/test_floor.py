"""Tests for dashboard/floor.py (#403). Run: python3 -m unittest discover -s dashboard"""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import floor  # noqa: E402
import generate as g  # noqa: E402
import state as st  # noqa: E402
from test_generate import NOW, IDLE, REPO, ev, tracking, comment, issue  # noqa: E402


def model(events_by_session: dict, extra_issues=()):
    """A built model with one tracking issue per session, numbered from 50."""
    issues, comments = [*extra_issues], {}
    for n, (sid, events) in enumerate(events_by_session.items(), start=50):
        issues.append(tracking(n, sid))
        comments[n] = [comment(events)]
    return g.build({"repo": REPO, "issues": issues, "comments": comments, "prs": []}, NOW, IDLE)


def one_card(events, extra_issues=()):
    cards = model({"s1": events}, extra_issues)["floor"]["cards"]
    assert len(cards) == 1, cards
    return cards[0]


class TemplateTest(unittest.TestCase):
    """Each row of floor.TEMPLATES, through the whole build."""

    def activity(self, *events, extra_issues=()):
        return one_card([ev("s1", "session_started", 40), *events], extra_issues)["activity"]

    def test_editing(self):
        for tool in ("Edit", "Write", "NotebookEdit"):
            self.assertEqual(self.activity(ev("s1", "heartbeat", 2, issue=392, tools=["Read", tool])),
                             "Editing files on #392")

    def test_commands(self):
        self.assertEqual(self.activity(ev("s1", "heartbeat", 2, issue=392, tools=["Bash", "Grep"])),
                         "Running commands on #392")

    def test_editing_outranks_commands(self):
        self.assertEqual(self.activity(ev("s1", "heartbeat", 2, issue=392, tools=["Bash", "Edit"])),
                         "Editing files on #392")

    def test_reading_only(self):
        self.assertEqual(self.activity(ev("s1", "heartbeat", 2, issue=392,
                                          tools=["Read", "Grep", "Glob", "WebFetch"])),
                         "Reading code on #392")

    def test_pr_opened(self):
        self.assertEqual(self.activity(ev("s1", "pr_opened", 2, issue=392, pr=394, tools=["Bash"])),
                         "Opened PR #394")

    def test_blocked(self):
        q = issue(396, "GOV-Q: x?", ["gov:question"])
        words = self.activity(ev("s1", "blocked", 3, issue=392, gov_question=396),
                              ev("s1", "heartbeat", 1, issue=392, tools=["Edit"]), extra_issues=[q])
        self.assertEqual(words, "Waiting on #396")

    def test_session_started(self):
        self.assertEqual(one_card([ev("s1", "session_started", 1)])["activity"], "Starting up")

    def test_no_tool_names(self):
        self.assertEqual(self.activity(ev("s1", "working_on", 2, issue=392)), "Working on #392")
        self.assertEqual(self.activity(ev("s1", "heartbeat", 2, issue=392, tools=[])),
                         "Working on #392")
        self.assertEqual(self.activity(ev("s1", "heartbeat", 2, issue=392, tools=None)),
                         "Working on #392")

    def test_unknown_tools_only(self):
        self.assertEqual(self.activity(ev("s1", "heartbeat", 2, issue=392, tools=["WebFetch"])),
                         "Working on #392")

    def test_pr_without_issue(self):
        self.assertEqual(self.activity(ev("s1", "heartbeat", 2, pr=391, tools=["Read"])),
                         "Reading code on PR #391")

    def test_no_target(self):
        self.assertEqual(self.activity(ev("s1", "heartbeat", 2, tools=["Bash"])), "Running commands")

    def test_every_row_is_reachable(self):
        hit = {floor.template(sit, kinds) for sit in ("blocked", "pr_opened", "session_started", "heartbeat")
               for kinds in (set(), {"editing"}, {"commands"}, {"reading"})}
        self.assertEqual(hit, {w for _, _, w in floor.TEMPLATES})


class CardTest(unittest.TestCase):
    def test_fields(self):
        c = one_card([ev("s1", "session_started", 80),
                      ev("s1", "working_on", 29, issue=392, tools=["Read"]),
                      ev("s1", "heartbeat", 24, issue=392, tools=["Edit"]),
                      ev("s1", "heartbeat", 22, issue=392, tools=["Bash"]),
                      ev("s1", "heartbeat", 2, issue=392, tools=["Edit", "Bash"])])
        self.assertEqual((c["role"], c["model"], c["status"], c["run_minutes"]),
                         ("builder", "claude-opus-5-5", "active", 80))
        # Oldest slot first: 30-25 min ago, 25-20, ..., 5-0.
        self.assertEqual(c["events_per_slot"], [1, 2, 0, 0, 0, 1])
        self.assertEqual(c["slots_used"], {"editing": 2, "reading": 1, "commands": 2})

    def test_event_before_window_is_left_out(self):
        c = one_card([ev("s1", "working_on", 30, issue=1), ev("s1", "heartbeat", 0, issue=1)])
        self.assertEqual(c["events_per_slot"], [0, 0, 0, 0, 0, 1])

    def test_stopped_and_idle_get_no_card(self):
        m = model({"s-idle": [ev("s-idle", "working_on", 40, issue=1)],
                   "s-stop": [ev("s-stop", "working_on", 5, issue=1), ev("s-stop", "stopped", 1)]})
        self.assertEqual(m["floor"]["cards"], [])
        self.assertEqual([i["session_id"] for i in m["floor"]["idle"]], ["s-idle"])


class NeverActedTest(unittest.TestCase):
    """#454: a tracking issue with no events, older than the idle threshold, never acted."""

    def built(self, created_minutes_ago):
        from test_generate import ts
        t = tracking(60, "empty") | {"created_at": ts(created_minutes_ago)}
        return g.build({"repo": REPO, "issues": [t], "comments": {}, "prs": []}, NOW, IDLE)

    def test_never_acted_leaves_the_floor(self):
        m = self.built(60)
        (s,) = m["sessions"]
        self.assertEqual((s["status"], s["never_acted"]), ("idle", True))
        self.assertEqual(m["floor"], {"cards": [], "idle": []})

    def test_new_session_without_events_stays(self):
        m = self.built(5)   # younger than IDLE: its first event may not have flushed
        (s,) = m["sessions"]
        self.assertFalse(s["never_acted"])
        self.assertEqual(floor.idle_line(m["floor"]["idle"]), "idle: builder no events")

    def test_a_session_with_events_is_never_never_acted(self):
        m = model({"old": [ev("old", "session_started", 300)]})
        self.assertFalse(m["sessions"][0]["never_acted"])
        self.assertEqual([i["session_id"] for i in m["floor"]["idle"]], ["old"])


class IdleLineTest(unittest.TestCase):
    def test_line(self):
        m = model({"a": [ev("a", "working_on", 40, issue=1, role="builder")],
                   "b": [ev("b", "working_on", 125, issue=1, role="builder")]})
        self.assertEqual(floor.idle_line(m["floor"]["idle"]), "idle: builder 40 min, builder 2 h 5 min")

    def test_spans(self):
        self.assertEqual([floor.span(n) for n in (0, 40, 120, 125, 3000, None)],
                         ["0 min", "40 min", "2 h", "2 h 5 min", "2 d", "no events"])

    def test_on_the_desk(self):
        m = model({"a": [ev("a", "working_on", 40, issue=1)],
                   "b": [ev("b", "heartbeat", 2, issue=392, tools=["Edit"])]})
        desk = g.render(m)["index.html"]
        self.assertIn("<h2>On the floor</h2>", desk)
        self.assertIn("idle: builder 40 min", desk)
        self.assertIn(f'Editing files on <a href="https://github.com/{REPO}/issues/392">#392</a>', desk)
        self.assertIn("<svg", desk)
        self.assertNotIn("On the floor", g.render(m)["operations.html"])

    def test_nobody_working(self):
        desk = g.render(model({}))["index.html"]
        self.assertIn("No session is working.", desk)
        self.assertNotIn("idle:", desk)


class StateTest(unittest.TestCase):
    def test_cards_in_state_without_cost(self):
        m = model({"s1": [ev("s1", "heartbeat", 2, issue=392, tools=["Edit"], cost_usd=4.2,
                             token_counts={"input": 1, "output": 1, "cache_read": 1,
                                           "cache_creation": 1})]})
        out = st.state(m)["floor"]
        self.assertEqual(out["cards"][0]["activity"], "Editing files on #392")
        self.assertEqual(set(out["cards"][0]), set(st.CARD_FIELDS))
        text = json.dumps(out)
        for word in ("cost", "token", "usd", "4.2"):
            self.assertNotIn(word, text)


if __name__ == "__main__":
    unittest.main()
