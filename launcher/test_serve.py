"""Tests for #660: `swarm watch --serve` (a webhook nudge starts a check early, the interval
is a backstop sweep) and the owner's `swarm:halt` on the report issue."""
import datetime as dt
import hashlib
import hmac
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import swarm  # noqa: E402
import watch  # noqa: E402


def setUpModule():
    # #662: the runs ledger reads its scopes with swarm.gh_scopes; never GitHub in a test.
    patcher = mock.patch.object(swarm, "gh_scopes", lambda repo, numbers: {})
    patcher.start()
    unittest.addModuleCleanup(patcher.stop)
import webhooks  # noqa: E402
from test_swarm import Fake, FakeGit  # noqa: E402
from test_watch import ALL_CAPPED, NOW, OWNER, REPO, ROLES, Scene, ev, issue, write_manifest  # noqa: E402


class Clock:
    """A fake monotonic clock that sleep() advances, running `at` callbacks on the way."""

    def __init__(self):
        self.t = 1000.0
        self.at = []            # (time, fn), fired once the clock reaches time
        self.slept = []

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s
        for when, fn in [x for x in self.at if x[0] <= self.t]:
            self.at.remove((when, fn))
            fn()


class ServeTest(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.home = Path(d.name)
        self.l = swarm.Launcher(self.home, root=self.home / "repo", proc=lambda pid: None,
                                clock=time.time, out=lambda s: None, git=lambda a: (0, ""))
        self.l.dir.mkdir(parents=True)
        self.clock = Clock()
        self.nudge = self.l.dir / webhooks.NUDGE_FILE
        self.checks = []

    def watcher(self, serve=True):
        w = watch.Watch(self.l, REPO, OWNER, ROLES, serve=serve, clock=self.clock)
        w.tick = lambda now=None: self.checks.append(self.clock())
        return w

    def touch(self, at):
        """Touch the nudge file at clock time `at`, as webhooks.nudge() does on a delivery."""
        stamp = 10**9 * (len(self.clock.at) + 1)      # a distinct mtime for each delivery

        def fn():
            self.nudge.touch()
            os.utime(self.nudge, ns=(stamp, stamp))
        self.clock.at.append((at, fn))

    def test_without_serve_it_sleeps_the_interval(self):
        self.watcher(serve=False).loop(5, ticks=2, sleep=self.clock.sleep)
        self.assertEqual(self.clock.slept, [300])

    def test_with_no_nudge_the_sweep_still_runs_every_interval(self):
        self.watcher().loop(5, ticks=3, sleep=self.clock.sleep)
        self.assertEqual([t - self.checks[0] for t in self.checks], [0, 300, 600])

    def test_a_nudge_starts_a_check_within_a_second(self):
        self.touch(1000 + 100.2)                  # 100 s after the first check started
        self.watcher().loop(5, ticks=2, sleep=self.clock.sleep)
        self.assertLessEqual(self.checks[1] - 1100.2, 1.0)
        self.assertGreaterEqual(self.checks[1], 1100.2)

    def test_a_nudge_from_before_the_check_doesnt_start_another(self):
        self.nudge.touch()                        # an old nudge, already there at the first check
        self.watcher().loop(5, ticks=2, sleep=self.clock.sleep)
        self.assertEqual(self.checks[1] - self.checks[0], 300)

    def test_a_burst_of_nudges_right_after_a_check_waits_for_the_gap(self):
        for k in range(5):
            self.touch(1000 + 1 + k)              # five deliveries in the first five seconds
        self.watcher().loop(5, ticks=3, sleep=self.clock.sleep)
        self.assertEqual(self.checks[1] - self.checks[0], watch.MIN_GAP)
        self.assertEqual(self.checks[2] - self.checks[1], 300)   # one check covered the burst

    def test_a_real_delivery_wakes_the_wait_within_a_second(self):
        """End to end with real time: a signed delivery to the receiver touches the nudge
        file, and the waiting watcher returns well before its interval."""
        w = watch.Watch(self.l, REPO, OWNER, ROLES, serve=True)
        w.nudged, w.checked_at = w.nudge_mtime(), time.monotonic() - watch.MIN_GAP
        store = webhooks.Store(self.l.dir / webhooks.DB_FILE)
        self.addCleanup(store.db.close)
        body = json.dumps({"action": "labeled", "issue": {"number": 7}}).encode()
        sig = "sha256=" + hmac.new(b"s", body, hashlib.sha256).hexdigest()

        def deliver():
            time.sleep(0.3)
            webhooks.handle(store, b"s", self.nudge, "POST", webhooks.PATH,
                            {"x-hub-signature-256": sig, "x-github-delivery": "d-1",
                             "x-github-event": "issues"}, body, dt.datetime.now(dt.timezone.utc))
        threading.Thread(target=deliver).start()
        start = time.monotonic()
        w.wait(30, time.sleep)
        self.assertLess(time.monotonic() - start, 1.3)


class HaltTest(unittest.TestCase):
    """swarm:halt on report issue #600 holds every start, but only when the owner added it."""

    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        (self.home / "launcher").mkdir()
        self.fake = Fake(self.home / "launcher")
        self.lines = []
        self.l = swarm.Launcher(self.home, run=self.fake.run, proc=self.fake.proc, kill=self.fake.kill,
                                clock=self.fake.clock, sleep=lambda s: None, out=self.lines.append,
                                root=self.home / "repo", git=FakeGit(), claude_dir=self.home / "claude")
        self.scene = Scene()
        self.report = issue(600, title="Needs you")
        self.scene.issues.append(self.report)
        self.path = write_manifest(self.home, ALL_CAPPED, 10, extra="report_issue = 600\n")

    def watcher(self):
        return watch.Watch(self.l, REPO, OWNER, ROLES, dry_run=False, manifest_path=self.path,
                           read=self.scene.read, get_issue=self.scene.get_issue,
                           get_heartbeat=self.scene.heartbeat, get_reader=self.scene.get_reader)

    def halt(self, *actors):
        self.report["labels"] = [{"name": watch.HALT}]
        self.scene.events[600] = [ev(watch.HALT, actor=a, eid=900 + i) for i, a in enumerate(actors)]

    def test_the_owners_halt_holds_every_start(self):
        self.halt(OWNER)
        self.assertEqual(self.watcher().tick(NOW), [])
        self.assertEqual(self.fake.commands, [])
        waiting = watch.load_state(self.l)["waiting"]
        self.assertTrue(waiting)
        codes = {x["key"]: x["code"] for x in waiting}
        self.assertEqual(codes.pop("build:60:12"), "live")       # the scene's busy issue, as before
        self.assertEqual(set(codes.values()), {"halted"})
        self.assertEqual(sum("swarm:halt on #600" in x for x in self.lines), 1)   # said once
        self.watcher().tick(NOW + dt.timedelta(minutes=5))
        self.assertEqual(sum("swarm:halt on #600" in x for x in self.lines), 1)

    def test_starts_again_once_the_owner_takes_it_off(self):
        self.halt(OWNER)
        self.watcher().tick(NOW)
        self.report["labels"] = []
        self.scene.events[600].append(ev(watch.HALT, eid=999, kind="unlabeled"))
        self.assertTrue(self.watcher().tick(NOW + dt.timedelta(minutes=5)))
        self.assertTrue(self.fake.commands)

    def test_a_halt_anyone_else_added_is_ignored_and_said_once(self):
        for actors in ((("productswarm-planner[bot]",)), (OWNER, "productswarm-lead[bot]")):
            with self.subTest(actors=actors):
                self.setUp()
                self.halt(*actors)
                w = self.watcher()
                self.assertTrue(w.tick(NOW))
                self.assertTrue(self.fake.commands)
                self.assertEqual(sum("wasn't added by the owner" in x for x in self.lines), 1)

    def test_a_halt_on_another_issue_does_nothing(self):
        self.scene.issues[0]["labels"].append({"name": watch.HALT})
        self.scene.events[49].append(ev(watch.HALT, eid=950))
        self.assertTrue(self.watcher().tick(NOW))

    def test_the_public_state_shows_the_hold_without_detail(self):
        self.halt(OWNER)
        self.watcher().tick(NOW)
        pub = json.loads((self.l.dir / watch.PUBLIC_FILE).read_text())
        halted = [h for h in pub["held"] if h["ref"] != "#60"]
        self.assertTrue(halted)
        self.assertEqual({(h["code"], h["reason"]) for h in halted}, {("halted", watch.REASONS["halted"])})


if __name__ == "__main__":
    unittest.main()
