"""Tests for launcher/watch.py (`swarm watch --dry-run`, #89). Canned GitHub data only.

Run: python3 -m unittest discover -s launcher
"""
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import swarm  # noqa: E402
import watch  # noqa: E402
from test_swarm import Fake, FakeGit  # noqa: E402

G = swarm.dashboard()
REPO = "open-agentos/productswarm"
OWNER = "mattmcalister"
NOW = dt.datetime(2026, 11, 3, 12, 0, tzinfo=dt.timezone.utc)
ROLES = {"builder", "docs", "planner", "reviewer"}
SHA1, SHA2 = "a" * 40, "b" * 40


def ts(minutes_ago):
    return (NOW - dt.timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def question_body(raised="planner, on #87", domain="spend", rev="two-way", blast="repo"):
    return (f"### Domain\n\n{domain}\n\n### Context\n\nx\n\n### Reversibility\n\n{rev}\n\n"
            f"### Blast radius\n\n{blast}\n\n### Raised by\n\n{raised}\n")


def issue(n, labels=(), body="", title=None):
    return {"number": n, "title": title or f"issue {n}", "state": "open", "body": body,
            "html_url": f"https://github.com/{REPO}/issues/{n}", "created_at": ts(600),
            "labels": [{"name": x} for x in labels], "user": {"login": OWNER}}


def ev(label, actor=OWNER, eid=1, kind="labeled"):
    return {"id": eid, "event": kind, "label": {"name": label}, "actor": {"login": actor}}


def pr(n, head=SHA1, draft=False, closes=()):
    return {"number": n, "title": f"PR {n}", "url": f"https://github.com/{REPO}/pull/{n}",
            "author": {"login": "productswarm-builder[bot]"}, "isDraft": draft, "createdAt": ts(60),
            "reviewDecision": "", "closingIssuesReferences": [{"number": c} for c in closes],
            "headRefOid": head}


def tracking(n, sid, role, on_issue, minutes_ago=1):
    """A live heartbeat session on issue `on_issue`: its tracking issue and one comment."""
    bot = f"productswarm-{role}[bot]"
    it = {**issue(n), "user": {"login": bot},
          "body": f"<!-- productswarm-heartbeat schema_version=1 session_id={sid} -->\nx"}
    e = {"schema_version": 1, "ts": ts(minutes_ago), "session_id": sid, "repo": REPO, "role": role,
         "model": "m", "event": "working_on", "issue": on_issue}
    return it, [{"user": {"login": bot}, "body": "```jsonl\n" + json.dumps(e) + "\n```\n"}]


class Scene:
    """Canned GitHub: one of each trigger, plus one session that's busy on #60."""

    def __init__(self):
        self.issues = [
            issue(49, ["ready"]),                                                      # build
            issue(60, ["ready"]),                                                      # busy
            issue(87, ["gov:question", "gov:ruled"], question_body(domain="governance")),  # record
            issue(88, ["gov:question", "ready"], question_body(raised="planner, on #87")),  # answer
        ]
        self.events = {49: [ev("ready", eid=11)], 60: [ev("ready", eid=12)],
                       87: [ev("gov:question", "productswarm-planner[bot]", 1), ev("gov:ruled", eid=13)],
                       88: [ev("ready", eid=14)]}
        self.prs = [pr(70, SHA1), pr(71, SHA2, draft=True)]
        self.reviewed = {70: set()}
        t_issue, t_comments = tracking(200, "busy-sid", "builder", 60)
        self.tracking = [t_issue]
        self.comments = {200: t_comments}
        self.reads = 0

    def read(self, repo, idle, now):
        self.reads += 1
        data = {"repo": REPO, "issues": self.issues + self.tracking, "comments": self.comments,
                "prs": self.prs}
        model = G.build(data, NOW, dt.timedelta(minutes=idle))
        return watch.World(model=model, issues=self.issues + self.tracking,
                           events={k: list(v) for k, v in self.events.items()},
                           reviewed={k: set(v) for k, v in self.reviewed.items()})


class WatchTest(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        (self.home / "launcher").mkdir()
        self.fake = Fake(self.home / "launcher")
        self.lines = []
        self.l = swarm.Launcher(self.home, run=self.fake.run, proc=self.fake.proc, kill=self.fake.kill,
                                clock=self.fake.clock, sleep=lambda s: None, out=self.lines.append,
                                root=self.home / "repo", git=FakeGit())
        self.scene = Scene()
        self.w = watch.Watch(self.l, REPO, OWNER, ROLES, read=self.scene.read)

    def kinds(self, ts_):
        return [(t.kind, t.ref) for t in ts_]

    def test_each_trigger_prints_once(self):
        first = self.w.tick(NOW)
        self.assertEqual(self.kinds(first), [("review", "PR #70"), ("record", "#87"), ("answer", "#88"),
                                             ("build", "#49")])
        self.assertEqual(self.lines, [
            "[review] PR #70 head aaaaaaa not reviewed by the reviewer -> would start a reviewer pass "
            "(`swarm launch` has no PR form yet; #90)",
            "[record] #87 gov:ruled by the owner, needs a record (domain governance) -> would start "
            "`launcher/swarm launch docs --issue 87`",
            "[answer] #88 ready by the owner -> would start `launcher/swarm launch planner --issue 88`",
            "[build] #49 ready by the owner -> would start `launcher/swarm launch builder --issue 49`",
        ])
        self.assertEqual(self.w.tick(NOW), [])
        self.assertEqual(self.w.tick(NOW), [])
        self.assertEqual(len(self.lines), 4)

    def test_new_push_or_fresh_owner_label_is_a_new_trigger(self):
        self.w.tick(NOW)
        self.scene.reviewed[70] = {SHA1}
        self.assertEqual(self.w.tick(NOW), [])            # reviewed at its head: nothing
        self.scene.prs[0]["headRefOid"] = SHA2
        self.scene.events[49] += [ev("ready", eid=20, kind="unlabeled"), ev("ready", eid=21)]
        self.assertEqual(self.kinds(self.w.tick(NOW)), [("review", "PR #70"), ("build", "#49")])

    def test_labels_added_by_anyone_else_print_nothing(self):
        bot = "productswarm-planner[bot]"
        self.scene.events = {49: [ev("ready", bot)], 60: [], 87: [ev("gov:ruled", bot)],
                             88: [ev("ready", eid=1), ev("ready", bot, eid=2)]}
        self.assertEqual([t.kind for t in self.w.tick(NOW)], ["review"])

    def test_issue_with_a_live_session_prints_nothing(self):
        self.assertNotIn("#60", [t.ref for t in self.w.tick(NOW)])
        # A launcher session started on #49 that has no heartbeat yet counts too.
        self.w.seen.clear()
        self.l.start(swarm.Started("builder-issue-49", "builder", "m", "sid-49", self.fake.t, issue=49), [])
        self.assertNotIn("#49", [t.ref for t in self.w.tick(NOW)])

    def test_session_on_it_stops_then_it_fires(self):
        self.w.tick(NOW)
        self.scene.comments = {200: []}                    # the #60 session goes quiet...
        self.scene.tracking[0]["state"] = "closed"         # ...and stops
        self.assertEqual(self.kinds(self.w.tick(NOW)), [("build", "#60")])

    def test_record_needs_one_and_no_open_pr(self):
        self.scene.issues[2]["body"] = question_body(domain="spend")         # two-way, repo: no record
        self.assertNotIn("record", [t.kind for t in self.w.tick(NOW)])
        self.w.seen.clear()
        self.scene.issues[2]["body"] = question_body(rev="one-way")
        self.scene.prs.append(pr(92, closes=(87,)))
        self.scene.reviewed[92] = {SHA1}
        self.assertNotIn("record", [t.kind for t in self.w.tick(NOW)])

    def test_unknown_raised_by_is_skipped_with_a_reason(self):
        self.scene.issues[3]["body"] = question_body(raised="someone, on #3")
        (t,) = [t for t in self.w.tick(NOW) if t.kind == "answer"]
        self.assertIn("-> skipped: \"Raised by\" names no known role ('someone, on #3')", t.line())
        self.assertEqual(self.w.tick(NOW), [])            # printed once

    def test_dry_run_starts_nothing_and_writes_nothing(self):
        state = self.l.state_file
        self.l.save([swarm.Started("gone-1", "docs", "m", "gone", 0)])   # exited: live() would prune it
        before = state.read_text()
        with mock.patch.object(swarm.Launcher, "start", side_effect=AssertionError("started")), \
             mock.patch.object(swarm, "launch", side_effect=AssertionError("launch")), \
             mock.patch.object(swarm, "open_terminal", side_effect=AssertionError("terminal")):
            self.w.run(1, ticks=3, sleep=lambda s: None)
        self.assertEqual(self.fake.commands, [])
        self.assertEqual(self.fake.signals, [])
        self.assertEqual(state.read_text(), before)
        self.assertEqual(sorted(p.name for p in (self.home / "launcher").iterdir()), ["sessions.json"])
        self.assertEqual(self.scene.reads, 3)

    def test_github_error_is_reported_and_the_loop_goes_on(self):
        calls = []

        def flaky(*a):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("gh api failed: offline")
            return self.scene.read(*a)
        self.w.read = flaky
        self.w.run(1, ticks=2, sleep=lambda s: None)
        self.assertIn("swarm watch: gh api failed: offline; trying again next tick", self.lines)
        self.assertTrue(any(x.startswith("[build] #49") for x in self.lines))


class HelpersTest(unittest.TestCase):
    def test_raised_by(self):
        self.assertEqual(watch.raised_by(question_body(raised="builder (on #75)"), ROLES), ("builder", ""))
        self.assertIsNone(watch.raised_by(question_body(raised="builder and planner"), ROLES)[0])
        self.assertIn("no \"Raised by\"", watch.raised_by("### Domain\n\nspend\n", ROLES)[1])

    def test_needs_record(self):
        self.assertIsNone(watch.needs_record(question_body()))
        self.assertEqual(watch.needs_record(question_body(blast="external")), "blast radius external")


class CliTest(unittest.TestCase):
    def test_without_dry_run_refuses_and_names_88(self):
        lines = []
        l = swarm.Launcher(Path(tempfile.mkdtemp()), out=lines.append,
                           run=lambda c: self.fail("started"))
        self.assertEqual(swarm.main(["watch", "--repo", REPO], l), 1)
        self.assertIn("#88", lines[0])

    def test_script_refuses_without_dry_run(self):
        r = subprocess.run([str(HERE / "swarm"), "watch"], capture_output=True, text=True, timeout=30,
                           env={**os.environ, "PRODUCTSWARM_HOME": tempfile.mkdtemp()})
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("#88", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
