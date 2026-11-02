"""Tests for launcher/swarm.py. No test opens a Terminal window or starts Claude Code.

Run: python3 -m unittest discover -s launcher
"""
import datetime as dt
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import manifest  # noqa: E402
import swarm  # noqa: E402

M = "claude-opus-5-5"


def S(role, index=1, model=M):
    return manifest.Session(role=role, index=index, model=model)


class Fake:
    """A fake runtime and process table. run() 'starts' a session by writing its pid file."""

    def __init__(self, launcher_dir: Path):
        self.dir = launcher_dir
        self.procs: dict[int, str] = {}
        self.commands: list[str] = []
        self.signals: list[tuple[int, int]] = []
        self.next_pid = 1000
        self.t = 1_000_000.0
        self.exit_on_term = True
        self.fail_for: set[str] = set()

    def run(self, command: str) -> None:
        if any(f" {r} --model" in command for r in self.fail_for):
            raise RuntimeError("osascript failed: not allowed")
        self.commands.append(command)
        sid = command.split("--session-id ")[1].split()[0]
        self.next_pid += 1
        self.procs[self.next_pid] = f"claude --model {M} --session-id {sid} You are..."
        (self.dir / f"{sid}.pid").write_text(f"{self.next_pid}\n")

    def proc(self, pid):
        return self.procs.get(pid)

    def kill(self, pid, sig):
        self.signals.append((pid, sig))
        if self.exit_on_term:
            self.procs.pop(pid, None)

    def clock(self):
        return self.t

    def sleep(self, s):
        self.t += s


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        (self.home / "launcher").mkdir()
        self.fake = Fake(self.home / "launcher")
        self.lines: list[str] = []
        self.l = swarm.Launcher(self.home, root=Path("/repo"), run=self.fake.run, proc=self.fake.proc,
                                kill=self.fake.kill, clock=self.fake.clock, sleep=self.fake.sleep,
                                out=self.lines.append)

    def names(self):
        return [e.name for e in self.l.live()]


class PlanTest(Base):
    def test_plan_is_the_shortfall_by_name(self):
        live = [swarm.Started("builder-1", "builder", M, "a", 0)]
        todo = self.l.plan([S("builder", 1), S("builder", 2), S("docs")], live)
        self.assertEqual([s.name for s in todo], ["builder-2", "docs-1"])

    def test_up_starts_everything_then_nothing(self):
        sessions = [S("planner"), S("builder", 1), S("builder", 2)]
        self.assertEqual(self.l.up(sessions), 0)
        self.assertEqual(len(self.fake.commands), 3)
        self.assertEqual(self.names(), ["planner-1", "builder-1", "builder-2"])

        self.lines.clear()
        self.assertEqual(self.l.up(sessions), 0)
        self.assertEqual(len(self.fake.commands), 3)          # nothing new started
        self.assertEqual(sum(x.startswith("already running") for x in self.lines), 3)
        self.assertIn("nothing to start", self.lines[-1])

    def test_up_restarts_only_what_exited(self):
        self.l.up([S("planner"), S("builder")])
        builder = next(e for e in self.l.live() if e.role == "builder")
        self.fake.procs.pop(self.l.pid(builder))
        self.l.up([S("planner"), S("builder")])
        self.assertEqual(len(self.fake.commands), 3)
        self.assertIn("builder", self.fake.commands[-1])
        self.assertFalse(self.l.pid_file(builder.session_id).exists())  # pruned

    def test_count_raised_starts_the_extra(self):
        self.l.up([S("builder", 1)])
        self.l.up([S("builder", 1), S("builder", 2)])
        self.assertEqual(self.names(), ["builder-1", "builder-2"])

    def test_session_not_in_manifest_is_left_running(self):
        self.l.up([S("docs")])
        self.l.up([S("builder")])
        self.assertEqual(self.names(), ["docs-1", "builder-1"])
        self.assertTrue(any("not in the manifest; left running" in x for x in self.lines))

    def test_dry_run_starts_and_records_nothing(self):
        self.assertEqual(self.l.up([S("builder"), S("docs")], dry_run=True), 0)
        self.assertEqual(self.fake.commands, [])
        self.assertEqual(self.l.load(), [])
        self.assertEqual(sum(x.startswith("would start") for x in self.lines), 2)

    def test_starting_counts_as_running_until_grace_passes(self):
        self.fake.run = lambda cmd: None   # window opened, pid file not written yet
        self.l.run = self.fake.run
        self.l.up([S("builder")])
        self.assertEqual(self.l.state(self.l.load()[0]), "starting")
        self.l.up([S("builder")])
        self.assertEqual(len(self.l.load()), 1)                 # not double-started
        self.fake.t += swarm.START_GRACE + 1
        self.assertEqual(self.l.live(), [])                     # never came up

    def test_reused_pid_is_not_the_session(self):
        self.l.up([S("builder")])
        e = self.l.load()[0]
        self.fake.procs[self.l.pid(e)] = "/usr/bin/some-other-process"
        self.assertEqual(self.l.state(e), "exited")

    def test_failed_start_is_reported_and_not_recorded(self):
        self.fake.fail_for = {"docs"}
        self.assertEqual(self.l.up([S("builder"), S("docs")]), 1)
        self.assertEqual(self.names(), ["builder-1"])
        self.assertTrue(any("failed to start docs-1" in x for x in self.lines))


class CommandTest(Base):
    def test_calls_swarm_session_unchanged_with_model_session_id_and_opener(self):
        e = swarm.Started("builder-1", "builder", "claude-sonnet-5-5", "0b6c2f0e-aaaa-4bbb-8ccc-5f1d2b8e9c41", 0)
        cmd = self.l.command(e)
        self.assertTrue(cmd.startswith("exec /bin/bash -c "))
        inner = cmd[len("exec /bin/bash -c "):]
        import shlex
        (script,) = shlex.split(inner)
        argv = shlex.split(script.split("&& exec ", 1)[1])
        self.assertEqual(argv, ["/repo/ops/swarm-session", "builder", "--model", "claude-sonnet-5-5",
                                "--session-id", e.session_id, swarm.opener("builder")])
        self.assertIn(f"echo $$ >| {self.home}/launcher/{e.session_id}.pid", script)

    def test_applescript_string_escapes(self):
        self.assertEqual(swarm.applescript_string('a "b" \\c'), '"a \\"b\\" \\\\c"')


class StopTest(Base):
    def setUp(self):
        super().setUp()
        self.l.up([S("builder", 1), S("builder", 2)])
        self.b1 = self.l.live()[0]

    def test_stop_by_name_sends_sigterm_and_forgets_it(self):
        state = self.home / "state"
        state.mkdir()
        (state / f"{self.b1.session_id}.json").write_text(json.dumps({"stopped": True}))
        pid = self.l.pid(self.b1)
        self.assertEqual(self.l.stop("builder-1"), 0)
        self.assertEqual(self.fake.signals, [(pid, signal.SIGTERM)])
        self.assertEqual(self.names(), ["builder-2"])
        self.assertIn("heartbeat recorded `stopped`", self.lines[-1])

    def test_stop_by_session_id_prefix(self):
        self.assertEqual(self.l.stop(self.b1.session_id[:8]), 0)
        self.assertIn("heartbeat has no `stopped`", self.lines[-1])

    def test_unknown_session(self):
        self.assertEqual(self.l.stop("docs-1"), 1)
        self.assertIn("no running session 'docs-1'", self.lines[-1])
        self.assertIn("builder-1, builder-2", self.lines[-1])
        self.assertEqual(self.fake.signals, [])

    def test_still_running_after_wait(self):
        self.fake.exit_on_term = False
        self.assertEqual(self.l.stop("builder-1"), 1)
        self.assertIn("still running", self.lines[-1])
        self.assertEqual(self.names(), ["builder-1", "builder-2"])

    def test_never_signals_a_reused_pid(self):
        self.fake.procs[self.l.pid(self.b1)] = "/usr/bin/other"
        self.assertEqual(self.l.stop("builder-1"), 1)
        self.assertEqual(self.fake.signals, [])


class LsTest(Base):
    def test_rows_join_heartbeat_with_launcher_state(self):
        now = dt.datetime(2026, 11, 2, 18, 0, tzinfo=dt.timezone.utc)
        started = [swarm.Started("builder-1", "builder", M, "sid-b", 0),
                   swarm.Started("docs-1", "docs", M, "sid-d", 0)]
        model = {"sessions": [
            {"session_id": "sid-b", "role": "builder", "model": M, "issue": 48, "status": "active",
             "gov_question": None, "last_ts": now},
            {"session_id": "sid-x", "role": "planner", "model": M, "issue": None, "status": "blocked",
             "gov_question": 43, "last_ts": now},
            {"session_id": "sid-old", "role": "docs", "model": M, "issue": 1, "status": "stopped",
             "gov_question": None, "last_ts": now},
        ]}
        rows = swarm.ls_rows(model, started, lambda e: "running", now, lambda t, n: "now")
        self.assertEqual(rows, [
            ["builder-1", "builder", M, "#48", "active", "now", "running", "sid-b"],
            ["-", "planner", M, "-", "blocked on #43", "now", "not launcher", "sid-x"],
            ["docs-1", "docs", M, "-", "no heartbeat yet", "-", "running", "sid-d"],
        ])

    def test_table(self):
        self.assertEqual(swarm.table(["A", "BB"], [["xxx", "y"]]), "A    BB\nxxx  y")


class CliTest(Base):
    def test_bad_manifest_fails_before_starting(self):
        bad = self.home / "swarm.toml"
        bad.write_text('[[session]]\nrole = "builder"\ncount = 0\nmodel = "m"\n')
        self.assertEqual(swarm.main(["up", "--manifest", str(bad)], self.l), 1)
        self.assertIn("count must be at least 1", self.lines[-1])
        self.assertEqual(self.fake.commands, [])

    def test_corrupt_state_file(self):
        (self.home / "launcher" / "sessions.json").write_text("{")
        self.assertEqual(swarm.main(["stop", "builder-1"], self.l), 1)
        self.assertIn("not valid JSON", self.lines[-1])


@unittest.skipUnless(os.path.exists("/bin/bash"), "needs /bin/bash")
class RealShellTest(unittest.TestCase):
    """Runs the real window command through a shell, with a stand-in ops/swarm-session
    that just sleeps: checks the pid file names the process that carries --session-id,
    and that stop() ends it. No Terminal, no Claude Code."""

    def test_pid_chain_and_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, home = Path(tmp) / "repo", Path(tmp) / "home"
            (root / "ops").mkdir(parents=True)
            fake = root / "ops" / "swarm-session"
            fake.write_text('#!/bin/bash\nexec python3 -c "import time; time.sleep(30)" "$@"\n')
            fake.chmod(0o755)
            procs = []
            l = swarm.Launcher(home, root=root, out=lambda s: None,
                               run=lambda cmd: procs.append(subprocess.Popen(["/bin/sh", "-c", cmd])))
            try:
                self.assertEqual(l.up([S("builder")]), 0)
                e = l.load()[0]
                for _ in range(50):
                    if l.state(e) == "running":
                        break
                    time.sleep(0.1)
                self.assertEqual(l.state(e), "running")
                self.assertEqual(l.pid(e), procs[0].pid)       # both exec's kept the pid
                self.assertEqual(l.up([S("builder")]), 0)      # already running
                self.assertEqual(len(procs), 1)
                l.clock = time.time
                self.assertEqual(l.stop("builder-1"), 0)
                self.assertIsNotNone(procs[0].wait(timeout=5))
                self.assertEqual(l.load(), [])
            finally:
                for p in procs:
                    if p.poll() is None:
                        p.kill()


if __name__ == "__main__":
    unittest.main()
