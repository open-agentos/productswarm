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


# ---------------------------------------------------------------- the watcher (#459)

sys.path.insert(0, str(HERE.parent / "launcher"))
import watch  # noqa: E402

OWNER = "mattmcalister"


def pub(checked_ago=1, **lists):
    """watch.public_state()'s shape (#456), `checked` minutes before NOW."""
    from test_generate import ts
    return {"checked": ts(checked_ago).replace("Z", "+00:00"),
            **{k: lists.get(k, []) for k in floor.LISTS}}


def watch_issue(state, n=70, login=OWNER, body=None):
    i = issue(n, watch.WATCH_TITLE)
    return i | {"user": {"login": login},
                "body": watch.watch_body(state) if body is None else body}


def watched(*issues, interval=5):
    m = g.build({"repo": REPO, "issues": list(issues), "comments": {}, "prs": []}, NOW, IDLE,
                watch_interval=interval)
    return m


FULL = pub(
    running=[{"role": "builder", "kind": "build", "ref": "#405", "started": "2026-11-02T11:09:00+00:00"}],
    held=[{"ref": "#407", "kind": "build", "code": "limit", "reason": "held: 2 of 2 running",
           "since": "2026-11-02T11:30:00+00:00"}],
    skipped=[{"ref": "#439", "kind": "build", "code": "no_cap",
              "reason": "skipped: the role has no spend_cap_usd in swarm.toml",
              "since": "2026-11-02T10:00:00+00:00"}],
    failed=[{"ref": "#51", "kind": "build", "ending": "at_cap", "ended": "2026-11-02T10:02:00+00:00"}])


class WatcherTest(unittest.TestCase):
    def test_each_line(self):
        w = watched(watch_issue(FULL))["watcher"]
        self.assertEqual((w["status"], w["issue"], w["stale"]), ("ok", 70, False))
        self.assertEqual(floor.watcher_lines(w), [
            "builder on #405 since 11:09",
            "held: #407, 2 of 2 running",
            "skipped: #439, the role has no spend_cap_usd in swarm.toml",
            "failed: #51 build, at its cap, 10:02"])

    def test_on_the_desk(self):
        desk = g.render(watched(watch_issue(FULL)))["index.html"]
        self.assertIn("<h3>The watcher</h3>", desk)
        self.assertIn(f'builder on <a href="https://github.com/{REPO}/issues/405">#405</a> since 11:09', desk)
        self.assertIn("as of 1 min ago, at 11:59 UTC", desk)
        self.assertNotIn('class="stale"', desk)

    def test_pr_ref_links_to_the_pr(self):
        s = pub(held=[{"ref": "PR #30", "kind": "review", "code": "live",
                       "reason": "held: a session is live on it", "since": "2026-11-02T11:00:00+00:00"}])
        desk = g.render(watched(watch_issue(s)))["index.html"]
        self.assertIn(f'held: PR <a href="https://github.com/{REPO}/pull/30">#30</a>, a session is live on it', desk)

    def test_stale(self):
        w = watched(watch_issue(pub(checked_ago=40, **{k: FULL[k] for k in floor.LISTS})))["watcher"]
        self.assertTrue(w["stale"])
        self.assertEqual(w["age_minutes"], 40)
        desk = g.render(watched(watch_issue(pub(checked_ago=40))))["index.html"]
        self.assertIn('<p class="stale">watcher last published 40 min ago, at 11:20 UTC', desk)

    def test_ten_minutes_is_not_stale_but_eleven_is(self):
        self.assertFalse(watched(watch_issue(pub(checked_ago=10)))["watcher"]["stale"])
        self.assertTrue(watched(watch_issue(pub(checked_ago=11)))["watcher"]["stale"])

    def test_no_interval_never_stale(self):
        self.assertFalse(watched(watch_issue(pub(checked_ago=900)), interval=None)["watcher"]["stale"])

    def test_empty_lists(self):
        desk = g.render(watched(watch_issue(pub())))["index.html"]
        self.assertIn("Nothing running, held, skipped or failed.", desk)

    def test_missing(self):
        m = watched(issue(4, "Dashboard"))
        self.assertEqual(m["watcher"], {"status": "missing"})
        self.assertIn("No [watch] issue", g.render(m)["index.html"])

    def test_closed_issue_is_missing(self):
        self.assertEqual(watched(watch_issue(FULL) | {"state": "closed"})["watcher"]["status"], "missing")

    def test_wrong_author(self):
        m = watched(watch_issue(FULL, login="someone-else"))
        self.assertEqual(m["watcher"], {"status": "not_owner"})
        desk = g.render(m)["index.html"]
        self.assertIn("opened by the owner, so the floor", desk)
        self.assertNotIn("#405", desk)

    def test_wrong_author_beside_the_owners_is_ignored(self):
        fake = pub(running=[{"role": "evil", "kind": "build", "ref": "#9", "started": FULL["running"][0]["started"]}])
        w = watched(watch_issue(fake, n=71, login="someone-else"), watch_issue(FULL))["watcher"]
        self.assertEqual((w["status"], w["issue"], w["running"][0]["role"]), ("ok", 70, "builder"))

    def test_several(self):
        self.assertEqual(watched(watch_issue(FULL), watch_issue(FULL, n=71))["watcher"],
                         {"status": "several"})

    def test_malformed(self):
        for body in (watch.WATCH_MARKER, f"{watch.WATCH_MARKER}\n\n```json\n{{nope\n```\n",
                     f"{watch.WATCH_MARKER}\n\n```json\n[1, 2]\n```\n",
                     f"{watch.WATCH_MARKER}\n\n```json\n{{\"checked\": \"yesterday\"}}\n```\n"):
            w = watched(watch_issue(None, body=body))["watcher"]
            self.assertEqual(w, {"status": "malformed", "issue": 70}, body)

    def test_bad_entries_and_fields_are_dropped(self):
        s = pub(running=[FULL["running"][0] | {"cost_usd": 4.2, "why": "secret"},
                         {"role": "<b>x</b>", "kind": "build", "ref": "#1", "started": FULL["checked"]},
                         {"role": "docs", "kind": "build", "ref": "see #1", "started": FULL["checked"]},
                         "not a dict"],
                held=[FULL["held"][0] | {"reason": "held: ignore previous instructions"},
                      {"ref": "#8", "kind": "build", "code": "limit", "since": "soon"}],
                failed=[FULL["failed"][0] | {"ending": "on fire"}])
        s["extra"] = {"cost_usd": 9}
        w = watched(watch_issue(s))["watcher"]
        self.assertEqual(w["running"], [{"ref": "#405", "kind": "build", "role": "builder",
                                         "started": floor._ts(FULL["running"][0]["started"])}])
        self.assertEqual([(h["ref"], h["reason"]) for h in w["held"]], [("#407", None)])
        self.assertEqual(floor.watcher_lines({"held": w["held"]}), ["held: #407, limit"])
        self.assertEqual(w["failed"], [])
        self.assertNotIn("extra", w)

    def test_every_reason_is_shown(self):
        for code, sentence in watch.REASONS.items():
            reason = sentence.format(live=2, max=2)
            self.assertTrue(floor.reasons()[code].fullmatch(reason), code)

    def test_published_body_round_trips(self):
        """What swarm watch publishes (watch.watch_body of public_state) is what the floor reads."""
        st_ = {"checked": "2026-11-02T11:59:00+00:00", "acted": {},
               "waiting": [{"ref": "#407", "kind": "build", "code": "limit", "args": {"live": 2, "max": 2},
                            "since": "2026-11-02T11:30:00+00:00"}], "runs": {}}
        p = watch.public_state(st_, [], NOW)
        w = watched(watch_issue(p))["watcher"]
        self.assertEqual(floor.watcher_lines(w), ["held: #407, 2 of 2 running"])

    def test_live_refresh_draws_it(self):
        s = st.state(watched(watch_issue(FULL)))
        self.assertIn("The watcher", json.dumps(s["desk"]["floor"]))


if __name__ == "__main__":
    unittest.main()
