"""Tests for launcher/swarm.py. No test opens a Terminal window or starts Claude Code.

Run: python3 -m unittest discover -s launcher
"""
import datetime as dt
import json
import shlex
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from unittest import mock
from pathlib import Path
from unittest import mock

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
        self.typed: list[str] = []

    def run(self, command: str) -> None:
        # The typed line runs the window's script (#550): record what the window runs.
        self.typed.append(command)
        assert len(command.encode()) < swarm.MAX_CANON, command
        if command.startswith("exec /bin/sh "):
            command = Path(shlex.split(command)[2]).read_text().strip()
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


class FakeGit:
    """A fake git: `worktree add` makes the directory, `worktree remove` deletes it.
    Worktrees in `dirty` have uncommitted work; those in `unpushed` have commits on no remote."""

    def __init__(self):
        self.calls: list[list[str]] = []
        self.dirty: set[str] = set()
        self.unpushed: set[str] = set()
        self.fail: str | None = None          # a subcommand that fails, e.g. "fetch"

    def __call__(self, args):
        self.calls.append(args)
        sub = args[2] if args[:1] == ["-C"] else args[0]
        if sub == self.fail:
            return 1, f"fatal: {sub} failed"
        if args[2:4] == ["worktree", "add"]:
            Path(args[-2]).mkdir(parents=True)
            (Path(args[-2]) / ".git").write_text("gitdir: x\n")
        elif args[2:4] == ["worktree", "remove"]:
            import shutil
            shutil.rmtree(args[-1])
        elif sub == "status":
            return 0, " M x.py" if Path(args[1]).name in self.dirty else ""
        elif sub == "branch":
            return 0, "" if Path(args[1]).name in self.unpushed else "  origin/main"
        return 0, ""

    def subs(self):
        return [" ".join(a[2:4]) if a[2] == "worktree" else a[2] for a in self.calls]


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        (self.home / "launcher").mkdir()
        self.fake = Fake(self.home / "launcher")
        self.lines: list[str] = []
        self.root = self.home / "repo"
        self.git = FakeGit()
        self.l = swarm.Launcher(self.home, root=self.root, run=self.fake.run, proc=self.fake.proc,
                                kill=self.fake.kill, clock=self.fake.clock, sleep=self.fake.sleep,
                                out=self.lines.append, git=self.git)

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
        wt = self.root / ".worktrees" / e.session_id
        self.assertTrue(script.startswith(f"cd {wt} && "))
        self.assertEqual(argv, [f"{wt}/ops/swarm-session", "builder", "--model", "claude-sonnet-5-5",
                                "--session-id", e.session_id, swarm.opener("builder")])
        self.assertIn(f"echo $$ >| {self.home}/launcher/{e.session_id}.pid", script)

    def test_up_and_launch_commands_are_byte_for_byte_unchanged(self):
        # #147 changes only runs swarm watch starts; these are command() before it.
        l = swarm.Launcher(Path("/h"), root=Path("/r"))
        sid = "0b6c2f0e-aaaa-4bbb-8ccc-5f1d2b8e9c41"
        self.assertEqual(
            l.command(swarm.Started("builder-1", "builder", "claude-opus-5-5", sid, 0)),
            'exec /bin/bash -c \'cd /r/.worktrees/0b6c2f0e-aaaa-4bbb-8ccc-5f1d2b8e9c41 && echo $$ >| '
            '/h/launcher/0b6c2f0e-aaaa-4bbb-8ccc-5f1d2b8e9c41.pid && exec /r/.worktrees/'
            '0b6c2f0e-aaaa-4bbb-8ccc-5f1d2b8e9c41/ops/swarm-session builder --model claude-opus-5-5 '
            '--session-id 0b6c2f0e-aaaa-4bbb-8ccc-5f1d2b8e9c41 \'"\'"\'You are the builder for '
            'productswarm. Read CLAUDE.md, PRODUCT.md and roles/builder.md, then begin.\'"\'"\'\'')
        self.assertEqual(
            l.command(swarm.Started("builder-pr-72", "builder", "claude-opus-5-5", sid, 0, issue=73, pr=72)),
            'exec /bin/bash -c \'cd /r/.worktrees/0b6c2f0e-aaaa-4bbb-8ccc-5f1d2b8e9c41 && echo $$ >| '
            '/h/launcher/0b6c2f0e-aaaa-4bbb-8ccc-5f1d2b8e9c41.pid && exec /r/.worktrees/'
            '0b6c2f0e-aaaa-4bbb-8ccc-5f1d2b8e9c41/ops/swarm-session builder --model claude-opus-5-5 '
            '--session-id 0b6c2f0e-aaaa-4bbb-8ccc-5f1d2b8e9c41 \'"\'"\'You are the builder for '
            'productswarm. Read CLAUDE.md, PRODUCT.md and roles/builder.md, then respond to the '
            'requested changes on PR #72, which closes issue #73.\'"\'"\'\'')

    def watch_entry(self, **kw):
        d = dict(issue=49, by="watch", budget_usd=15.0, max_turns=200)
        d.update(kw)
        return swarm.Started("builder-issue-49", "builder", "claude-opus-5-5",
                             "0b6c2f0e-aaaa-4bbb-8ccc-5f1d2b8e9c41", 0, **d)

    def test_a_run_swarm_watch_starts_is_headless(self):
        import shlex
        e = self.watch_entry()
        (script,) = shlex.split(self.l.command(e)[len("exec /bin/bash -c "):])
        wt = self.root / ".worktrees" / e.session_id
        result = self.home / "launcher" / f"{e.session_id}.result.json"
        self.assertTrue(script.startswith(f"cd {wt} && echo $$ >| {self.home}/launcher/{e.session_id}.pid && "))
        # The window says what it is before exec, then stdout goes to the result file.
        note, rest = script.split(" && exec ", 1)
        self.assertIn("headless run (claude -p)", shlex.split(note.rsplit(" && ", 1)[1])[1])
        self.assertIn(str(result), note)
        argv, redirect = rest.split(" >| ")
        self.assertEqual(shlex.split(redirect), [str(result)])
        self.assertEqual(shlex.split(argv), [
            f"{wt}/ops/swarm-session", "builder", "--model", "claude-opus-5-5",
            "--session-id", e.session_id,
            "-p", swarm.opener("builder", 49),
            "--permission-mode", "auto",                                   # GOV-0013
            "--disallowedTools", *swarm.DENY,
            "--max-budget-usd", "15", "--max-turns", "200",               # GOV-0012
            "--output-format", "json"])

    def test_the_window_types_a_short_line_and_runs_the_long_command_from_a_file(self):
        # #550: Terminal types the command into a shell that may still be starting, and the
        # tty keeps only MAX_CANON bytes of a line. A watch run's command() is longer, and
        # cut there it never wrote a pid or a result file.
        e = self.watch_entry()
        self.assertGreater(len(self.l.command(e).encode()), swarm.MAX_CANON)
        self.assertTrue(self.l.start(e, []))
        (typed,) = self.fake.typed
        self.assertEqual(typed, f"exec /bin/sh {self.home}/launcher/{e.session_id}.window.sh "
                                f"--session-id {e.session_id}")
        self.assertEqual(self.l.window_file(e.session_id).read_text(), self.l.command(e) + "\n")
        self.fake.procs.clear()                                   # it exits
        self.fake.t += swarm.START_GRACE + 1
        self.assertEqual(self.l.live(), [])
        self.assertFalse(self.l.window_file(e.session_id).exists())

    def test_headless_budget_and_turns_come_from_the_entry(self):
        argv = swarm.Launcher.headless_args(self.watch_entry(budget_usd=2.5, max_turns=7))
        self.assertEqual(argv[argv.index("--max-budget-usd") + 1], "2.5")
        self.assertEqual(argv[argv.index("--max-turns") + 1], "7")
        # --disallowedTools takes several values: a flag must follow its last pattern.
        i = argv.index("--disallowedTools") + len(swarm.DENY) + 1
        self.assertEqual(argv[i], "--max-budget-usd")

    def test_a_watch_run_with_no_budget_or_ceiling_never_starts(self):
        for kw in ({"budget_usd": None}, {"max_turns": None}):
            with self.assertRaises(RuntimeError):
                self.l.command(self.watch_entry(**kw))
            lines = []
            self.l.out = lines.append
            self.assertFalse(self.l.start(self.watch_entry(**kw), []))
            self.assertEqual(self.fake.commands, [])
            self.assertIn("GOV-0012", lines[-1])

    def test_deny_patterns_cover_merge_and_label_edits(self):
        # GOV-0013: the two rules governance cares about most, as #147 lists them.
        for d in ("Bash(gh pr merge *)", "Bash(gh issue edit * --add-label *)",
                  "Bash(gh issue edit * --remove-label *)", "Bash(gh pr edit * --add-label *)",
                  "Bash(gh pr edit * --remove-label *)", "Bash(gh label *)",
                  "Bash(gh api *labels*)", "Bash(gh api *merge*)"):
            self.assertIn(d, swarm.DENY)

    def test_budget_and_ceiling_survive_the_state_file(self):
        e = self.watch_entry()
        self.assertEqual(swarm.Started.from_dict(json.loads(json.dumps(e.__dict__))), e)

    def test_applescript_string_escapes(self):
        self.assertEqual(swarm.applescript_string('a "b" \\c'), '"a \\"b\\" \\\\c"')


class WorktreeTest(Base):
    """Each session gets its own worktree (#93); exited ones go only if nothing would be lost."""

    def test_each_session_gets_a_worktree_at_origin_main(self):
        self.l.up([S("builder"), S("docs")])
        # One fetch, the pinned hook copy, then a worktree per session.
        self.assertEqual(self.git.subs(), ["fetch", "worktree add", "worktree add", "worktree add"])
        self.assertEqual(self.git.calls[1][-2], str(self.home / "runtime"))
        for e in self.l.load():
            wt = self.root / ".worktrees" / e.session_id
            self.assertIn(["-C", str(self.root), "worktree", "add", "-q", "--detach", str(wt), "origin/main"],
                          self.git.calls)
            self.assertTrue(any(c.startswith(f"exec /bin/bash -c 'cd {wt} && ") for c in self.fake.commands))

    def test_hook_settings_are_written_and_other_settings_kept(self):
        (self.root / ".claude").mkdir(parents=True)
        (self.root / ".claude" / "settings.local.json").write_text(json.dumps(
            {"permissions": {"allow": ["Bash(ls)"]}}))
        self.l.up([S("builder")])
        (e,) = self.l.load()
        got = json.loads((self.root / ".worktrees" / e.session_id / ".claude" / "settings.local.json").read_text())
        self.assertEqual(got["permissions"], {"allow": ["Bash(ls)"]})
        self.assertEqual(sorted(got["hooks"]), sorted(["SessionStart", "UserPromptSubmit", "PostToolUse",
                                                       "Stop", "SessionEnd"]))

    def test_hooks_run_from_the_pinned_copy(self):
        self.l.up([S("builder")])
        (e,) = self.l.load()
        got = (self.root / ".worktrees" / e.session_id / ".claude" / "settings.local.json").read_text()
        self.assertIn(f'python3 -I \\"{self.home}/runtime/heartbeat/hook.py\\" SessionStart', got)
        self.assertNotIn("CLAUDE_PROJECT_DIR", got)

    def test_existing_pinned_copy_is_moved_to_origin_main(self):
        rt = self.home / "runtime"
        rt.mkdir()
        (rt / ".git").write_text("gitdir: x\n")
        self.l.up([S("builder")])
        self.assertIn(["-C", str(rt), "checkout", "-q", "--detach", "--force", "origin/main"], self.git.calls)

    def test_pinned_copy_failure_starts_nothing(self):
        self.git.fail = "worktree"
        self.assertEqual(self.l.up([S("builder")]), 1)
        self.assertEqual(self.fake.commands, [])
        self.assertIn("can't refresh the pinned hook copy", self.lines[-1])

    def test_git_failure_starts_nothing(self):
        self.git.fail = "fetch"
        self.assertEqual(self.l.up([S("builder")]), 1)
        self.assertEqual(self.fake.commands, [])
        self.assertEqual(self.l.load(), [])
        self.assertIn("failed to start builder-1: git", self.lines[-1])

    def test_window_failure_removes_the_new_worktree(self):
        self.fake.fail_for = {"builder"}
        self.assertEqual(self.l.up([S("builder")]), 1)
        self.assertEqual(self.git.subs()[-1], "worktree remove")
        self.assertIn("--force", self.git.calls[-1])
        self.assertEqual(list((self.root / ".worktrees").iterdir()), [])

    def test_dry_run_creates_no_worktree(self):
        self.l.up([S("builder")], dry_run=True)
        self.assertEqual(self.git.calls, [])
        self.assertFalse((self.root / ".worktrees").exists())
        self.assertIn("git worktree add --detach", self.lines[-1])

    def test_exited_sessions_worktrees_removed_only_when_nothing_would_be_lost(self):
        self.l.up([S("builder"), S("docs"), S("planner")])
        sids = {e.role: e.session_id for e in self.l.load()}
        self.git.dirty.add(sids["docs"])
        self.git.unpushed.add(sids["planner"])
        hand = self.root / ".worktrees" / "my-review"         # made by hand: never touched
        hand.mkdir()
        self.fake.procs.clear()                              # every window closed
        self.fake.t += swarm.START_GRACE + 1
        self.assertEqual(self.l.live(), [])
        wts = self.root / ".worktrees"
        self.assertFalse((wts / sids["builder"]).exists())
        self.assertEqual(self.l.kept, [wts / sids["docs"], wts / sids["planner"]] if sids["docs"] < sids["planner"]
                         else [wts / sids["planner"], wts / sids["docs"]])
        self.assertTrue(hand.exists())
        self.assertEqual(self.git.subs()[-1], "worktree prune")

    def test_live_sessions_worktree_is_never_touched(self):
        self.l.up([S("builder")])
        self.l.live()
        self.assertNotIn("worktree remove", self.git.subs())
        self.assertNotIn("status", self.git.subs())

    def test_stop_says_when_a_worktree_is_kept(self):
        self.l.up([S("builder")])
        (e,) = self.l.load()
        self.git.dirty.add(e.session_id)
        self.assertEqual(self.l.stop("builder-1"), 0)
        self.assertIn(f"worktree kept: {self.root / '.worktrees' / e.session_id} (uncommitted or unpushed work)",
                      self.lines)


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


def _writer(home: str, tag: str, n: int) -> None:
    """One `swarm` process: n launches, each followed by a watcher-style live() (#272)."""
    l = swarm.Launcher(Path(home), root=Path(home) / "repo", proc=lambda pid: None,
                       clock=time.time, out=lambda s: None, git=lambda a: (0, ""))
    for i in range(n):
        l.add(swarm.Started(f"{tag}-{i}", "builder", M, f"{tag}-{i}", time.time()))
        l.live()


class StateLockTest(Base):
    """#272: concurrent swarm processes share sessions.json without losing entries."""

    def test_concurrent_writers_lose_nothing(self):
        import multiprocessing as mp
        ctx = mp.get_context("spawn")
        procs = [ctx.Process(target=_writer, args=(str(self.home), f"w{k}", 25)) for k in range(4)]
        for p in procs:
            p.start()
        for p in procs:
            p.join(60)
        self.assertEqual([p.exitcode for p in procs], [0] * 4)        # no FileNotFoundError
        names = {e.name for e in self.l.load()}
        self.assertEqual(names, {f"w{k}-{i}" for k in range(4) for i in range(25)})
        self.assertEqual(list((self.home / "launcher").glob("*.tmp")), [])

    def orphan(self, opener="You are the docs for productswarm. Read CLAUDE.md, PRODUCT.md "
                            "and roles/docs.md, then work on issue #255.", flags=""):
        sid = str(uuid.uuid4())
        self.fake.procs[4242] = f"claude --model {M} --session-id {sid} {flags}{opener}"
        (self.home / "launcher" / f"{sid}.pid").write_text("4242\n")
        return sid

    def test_running_pid_file_with_no_entry_is_recovered(self):
        sid = self.orphan(flags="-p ")
        (e,) = self.l.live()
        self.assertEqual((e.name, e.role, e.model, e.session_id, e.issue, e.pr, e.by),
                         (f"docs-recovered-{sid[:8]}", "docs", M, sid, 255, None, "watch"))
        self.assertEqual(self.l.load(), [e])                           # written back
        self.assertTrue(any(x.startswith(f"recovered: docs-recovered-{sid[:8]}") for x in self.lines))
        self.lines.clear()
        self.l.live()
        self.assertFalse(any(x.startswith("recovered") for x in self.lines))   # reported once
        self.assertEqual(self.l.stop(e.name), 0)                       # and stoppable again
        self.assertEqual(self.fake.signals, [(4242, signal.SIGTERM)])

    def test_recovered_entry_keeps_issue_and_pr(self):
        self.orphan(opener=swarm.opener("builder", 73, 72))
        (e,) = self.l.running()                                        # dry run: nothing written
        self.assertEqual((e.role, e.issue, e.pr, e.by), ("builder", 73, 72, None))
        self.assertEqual(self.l.load(), [])

    def test_pid_file_of_an_ended_process_is_not_recovered(self):
        sid = self.orphan()
        self.fake.procs[4242] = "/usr/bin/other"                       # pid reused
        self.assertEqual(self.l.live(), [])
        self.assertTrue((self.home / "launcher" / f"{sid}.pid").exists())   # left alone

    def test_entry_is_recorded_before_the_window_opens(self):
        seen = []
        run = self.fake.run
        self.l.run = lambda cmd: (seen.append([e.name for e in self.l.load()]), run(cmd))
        self.l.up([S("builder")])
        self.assertEqual(seen, [["builder-1"]])


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
            ["builder-1", "builder", M, "#48", "active", "now", "-", "running", "sid-b"],
            ["-", "planner", M, "-", "blocked on #43", "now", "-", "not launcher", "sid-x"],
            ["docs-1", "docs", M, "-", "no heartbeat yet", "-", "-", "running", "sid-d"],
        ])

    def test_never_acted_only_with_all(self):   # #454
        now = dt.datetime(2026, 11, 2, 18, 0, tzinfo=dt.timezone.utc)
        model = {"sessions": [
            {"session_id": "sid-new", "role": "builder", "model": None, "issue": None, "status": "idle",
             "gov_question": None, "last_ts": None, "never_acted": False},
            {"session_id": "sid-empty", "role": "reviewer", "model": None, "issue": None, "status": "idle",
             "gov_question": None, "last_ts": None, "never_acted": True},
        ]}
        rows = swarm.ls_rows(model, [], lambda e: "running", now, lambda t, n: "never")
        self.assertEqual([r[-1] for r in rows], ["sid-new"])
        rows = swarm.ls_rows(model, [], lambda e: "running", now, lambda t, n: "never", show_all=True)
        self.assertEqual([(r[4], r[-1]) for r in rows],
                         [("idle", "sid-new"), ("idle, never acted", "sid-empty")])

    def test_ls_all_flag_reaches_ls_rows(self):
        seen = []
        with mock.patch.object(swarm, "ls", lambda l, repo, idle, show_all=False: seen.append(show_all) or 0):
            swarm.main(["ls", "--repo", "o/r"], self.l)
            swarm.main(["ls", "--all", "--repo", "o/r"], self.l)
        self.assertEqual(seen, [False, True])

    def test_spend_column(self):
        usd = lambda x: "-" if x is None else f"${x:,.2f}"  # noqa: E731
        self.assertEqual(swarm.spend_cell({"cost": 3.2, "cap": None}, usd), "$3.20")
        self.assertEqual(swarm.spend_cell({"cost": 3.2, "cap": 15.0, "over_cap": False}, usd), "$3.20 / $15.00")
        self.assertEqual(swarm.spend_cell({"cost": 20.0, "cap": 15.0, "over_cap": True}, usd),
                         "$20.00 / $15.00 OVER CAP")
        self.assertEqual(swarm.spend_cell({"cost": None, "cap": 15.0}, usd), "- / $15.00")

    def test_over_cap_from_canned_tokens_in_ls_and_inbox(self):
        g = swarm.dashboard()
        sys.path.insert(0, str(Path(g.__file__).parent))
        import test_cap
        m = test_cap.model({"builder": 15, "reviewer": 5},
                           [("b-over", "builder", False, [test_cap.spent(test_cap.M)])])
        (row,) = swarm.ls_rows(m, [], lambda e: "running", m["now"], g.ago, g.spend.usd)
        self.assertEqual(row[6], "$20.00 / $15.00 OVER CAP")
        self.assertIn("[over cap] builder session b-over", swarm.inbox_text(g.needs_you(m), m["now"], g))

    def test_only_stop_signals_a_session(self):   # GOV-0008: no automatic stop
        import ast
        tree = ast.parse((HERE / "swarm.py").read_text())
        callers = {f.name for f in ast.walk(tree) if isinstance(f, ast.FunctionDef)
                   for c in ast.walk(f) if isinstance(c, ast.Call)
                   and isinstance(c.func, ast.Attribute) and c.func.attr == "kill"}
        self.assertEqual(callers, {"stop"})
        stop_callers = {f.name for f in ast.walk(tree) if isinstance(f, ast.FunctionDef)
                        for c in ast.walk(f) if isinstance(c, ast.Call)
                        and isinstance(c.func, ast.Attribute) and c.func.attr == "stop"}
        self.assertEqual(stop_callers, {"main"})   # only the owner's `swarm stop` command

    def test_table(self):
        self.assertEqual(swarm.table(["A", "BB"], [["xxx", "y"]]), "A    BB\nxxx  y")


class CliTest(Base):
    def test_bad_manifest_fails_before_starting(self):
        bad = self.home / "swarm.toml"
        bad.write_text('[[session]]\nrole = "builder"\ncount = 0\nmodel = "m"\n')
        self.assertEqual(swarm.main(["up", "--manifest", str(bad)], self.l), 1)
        self.assertIn("count must be at least 1", self.lines[-1])
        self.assertEqual(self.fake.commands, [])

    def test_launch_unknown_role(self):
        self.l.root = Path(__file__).resolve().parent.parent
        self.assertEqual(swarm.main(["launch", "juggler", "--issue", "1", "--repo", "o/r"], self.l), 1)
        self.assertIn("unknown role 'juggler'", self.lines[-1])
        self.assertEqual(swarm.main(["launch", "../roles/builder", "--issue", "1", "--repo", "o/r"], self.l), 1)

    def test_corrupt_state_file(self):
        (self.home / "launcher" / "sessions.json").write_text("{")
        self.assertEqual(swarm.main(["stop", "builder-1"], self.l), 1)
        self.assertIn("not valid JSON", self.lines[-1])


OWNER = "mattmcalister"


def issue(n=49, state="open", labels=("ready",), pr=False):
    it = {"number": n, "state": state, "labels": [{"name": x} for x in labels]}
    if pr:
        it["pull_request"] = {}
    return it


def labeled(name, actor, event="labeled"):
    return {"event": event, "label": {"name": name}, "actor": {"login": actor}}


def hb(sid, issue_n, status="active", role="builder"):
    return {"session_id": sid, "role": role, "model": M, "issue": issue_n, "status": status,
            "gov_question": None, "last_ts": None}


class LaunchTest(Base):
    def go(self, it=None, events=None, sessions=(), force=False, n=49, dry_run=False, pr=None):
        it = issue(n) if it is None else it
        events = [labeled("ready", OWNER)] if events is None else events
        return swarm.launch(self.l, "builder", n, "claude-sonnet-5-5", repo="o/r", force=force,
                            dry_run=dry_run, pr=pr,
                            get_issue=lambda repo, num: (it if it != "missing" else None, events),
                            get_heartbeat=lambda repo, idle, now: {"sessions": list(sessions)},
                            owner=lambda: OWNER, agents=lambda: AGENTS,
                            get_reader=lambda repo, num: self.reader)

    reader = None   # set by a test that reaches the milestone go

    def refused(self, *a, **kw):
        self.assertEqual(self.go(*a, **kw), 1)
        self.assertEqual(self.fake.commands, [])
        self.assertTrue(self.lines[-1].startswith("swarm launch: refused: "), self.lines[-1])
        return self.lines[-1]

    def test_starts_with_the_issue_in_the_opener(self):
        self.assertEqual(self.go(), 0)
        (cmd,) = self.fake.commands
        self.assertIn("then work on issue #49.", cmd)
        self.assertIn("--model claude-sonnet-5-5", cmd)
        (e,) = self.l.live()
        self.assertEqual((e.name, e.issue), ("builder-issue-49", 49))

    def test_pr_names_it_in_the_opener_and_the_session(self):
        self.assertEqual(self.go(pr=70), 0)
        (cmd,) = self.fake.commands
        self.assertIn("then respond to the requested changes on PR #70, which closes issue #49.", cmd)
        (e,) = self.l.live()
        self.assertEqual((e.name, e.issue, e.pr), ("builder-pr-70", 49, 70))

    def test_opener_matches_the_heartbeat_working_on_rule(self):
        hook = Path(__file__).resolve().parent.parent / "heartbeat" / "hook.py"
        import importlib.util
        spec = importlib.util.spec_from_file_location("hook", hook)
        h = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(h)
        self.assertEqual(h.ISSUE_IN_PROMPT_RE.findall(swarm.opener("builder", 49)), ["49"])
        self.assertEqual(h.ISSUE_IN_PROMPT_RE.findall(swarm.opener("builder")), [])
        self.assertEqual(h.ISSUE_IN_PROMPT_RE.findall(swarm.opener("builder", 49, 70)), ["49"])
        # A call-in's why naming another issue mustn't give the heartbeat two issues (#520).
        called = swarm.opener("docs", 49, None, "the builder", "see issue #12 and Issue 13")
        self.assertEqual(h.ISSUE_IN_PROMPT_RE.findall(called), ["49"])
        self.assertIn("see #12 and #13", called)
        self.assertEqual(h.ISSUE_IN_PROMPT_RE.findall(swarm.opener("planner", 600,
                                                                   daily="the daily report")), ["600"])

    def test_ask_opener_quotes_the_question_and_says_one_comment(self):
        o = swarm.opener("builder", 600, ask="why is issue #12 still open?", ask_comment=901)
        self.assertEqual(o, "You are the builder for productswarm. Read CLAUDE.md, PRODUCT.md and "
                            "roles/builder.md, then answer the owner's question on issue #600 "
                            "(comment 901): \"why is #12 still open?\". swarm watch started this run "
                            "from its [ask] trigger (GOV-0029). Answer in plain words in one comment "
                            "on #600, and stop.")
        # "issue #12" in the question mustn't give the heartbeat two issues (#590).
        hook = Path(__file__).resolve().parent.parent / "heartbeat" / "hook.py"
        import importlib.util
        spec = importlib.util.spec_from_file_location("hook", hook)
        h = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(h)
        self.assertEqual(h.ISSUE_IN_PROMPT_RE.findall(o), ["600"])

    def test_research_opener_quotes_the_question_and_says_research_pr(self):
        o = swarm.opener("analyst", 300, research="who ships issue #12's report?", research_comment=901)
        self.assertEqual(o, "You are the analyst for productswarm. Read CLAUDE.md, PRODUCT.md and "
                            "roles/analyst.md, then research the question posted on issue #300 "
                            "(comment 901): \"who ships #12's report?\". swarm watch started this "
                            "run from its [research] trigger (GOV-0029). Write the brief in "
                            "research/<slug>.md as roles/analyst.md says, open a PR that closes "
                            "#300, link it in one comment on #300, and stop. If you can't, say why "
                            "in one comment on #300, and stop.")
        hook = Path(__file__).resolve().parent.parent / "heartbeat" / "hook.py"
        import importlib.util
        spec = importlib.util.spec_from_file_location("hook", hook)
        h = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(h)
        self.assertEqual(h.ISSUE_IN_PROMPT_RE.findall(o), ["300"])     # one issue for the heartbeat

    def test_daily_opener_names_the_report_and_the_report_issue(self):
        o = swarm.opener("planner", 600, daily="the daily report")
        self.assertEqual(o, "You are the planner for productswarm. Read CLAUDE.md, PRODUCT.md and "
                            "roles/planner.md, then write the daily report on issue #600, as "
                            "roles/planner.md says. swarm watch started this run from its [daily] "
                            "trigger (GOV-0029); post on #600 and stop.")
        self.assertIn("write the daily report and the Monday check-in on issue #600",
                      swarm.opener("planner", 600, daily="the daily report and the Monday check-in"))

    def test_call_in_opener_says_who_why_and_one_comment(self):
        o = swarm.opener("docs", 49, None, "the planner (productswarm-planner[bot])", "wording check")
        self.assertIn("then answer a call-in on issue #49: the planner (productswarm-planner[bot]) "
                      "called you in (GOV-0023) because: wording check.", o)
        self.assertIn("post one comment on it", o)
        self.assertIn("counts as asking you in", o)
        self.assertNotIn("because", swarm.opener("docs", 49, None, "the owner"))

    def test_missing_closed_or_pr(self):
        self.assertIn("#49 doesn't exist", self.refused("missing"))
        self.assertIn("#49 is closed", self.refused(issue(state="closed")))
        self.assertIn("is a pull request", self.refused(issue(pr=True)))

    def test_not_ready(self):
        self.assertIn("isn't labelled `ready`", self.refused(issue(labels=()), events=[]))

    def test_ready_added_by_someone_else(self):
        msg = self.refused(events=[labeled("ready", "productswarm-planner[bot]")])
        self.assertIn("added by productswarm-planner[bot], not @mattmcalister", msg)

    def test_most_recent_ready_event_counts(self):
        self.refused(events=[labeled("ready", OWNER), labeled("ready", OWNER, "unlabeled"),
                             labeled("ready", "someone-else")])
        self.lines.clear()
        self.assertEqual(self.go(events=[labeled("ready", "someone-else"), labeled("bug", "x"),
                                         labeled("ready", OWNER)]), 0)

    def test_milestone_issue_launches_without_ready(self):
        self.reader = swarm.GoReader(plan=lambda: PLAN, state=lambda n: "closed",
                                     comments=lambda: [])
        self.assertEqual(self.go(milestone_issue(), events=[]), 0)
        self.lines.clear()
        self.fake.commands.clear()
        msg = self.refused(milestone_issue("M2"), events=[])
        self.assertIn("#49's milestone M2 is marked done in PLAN.md", msg)

    def test_force_does_not_override_issue_rules(self):
        self.refused(issue(labels=()), events=[], force=True)
        self.refused(issue(state="closed"), force=True)

    def test_refused_while_a_live_session_has_the_issue(self):
        msg = self.refused(sessions=[hb("sid-a", 49, "idle")])
        self.assertIn("#49 already has a live session: builder (idle, session sid-a)", msg)
        self.assertIn("--force", msg)

    def test_stopped_or_other_issue_sessions_dont_count(self):
        self.assertEqual(self.go(sessions=[hb("a", 49, "stopped"), hb("b", 50)]), 0)

    def test_second_launch_refused_before_its_heartbeat_arrives(self):
        self.assertEqual(self.go(), 0)
        self.assertEqual(self.go(), 1)
        self.assertIn("builder-issue-49 (starting", self.lines[-1])
        self.assertEqual(len(self.fake.commands), 1)

    def test_launcher_session_is_named_in_the_refusal(self):
        self.go()
        (e,) = self.l.live()
        self.assertEqual(self.go(sessions=[hb(e.session_id, 49)]), 1)
        self.assertIn("builder-issue-49 (active", self.lines[-1])

    def test_force_starts_a_second_with_a_new_name(self):
        self.go()
        self.assertEqual(self.go(force=True), 0)
        self.assertEqual(self.names(), ["builder-issue-49", "builder-issue-49-2"])
        self.assertTrue(any(x.startswith("--force: starting another") for x in self.lines))

    def test_dry_run(self):
        self.assertEqual(self.go(dry_run=True), 0)
        self.assertEqual(self.fake.commands, [])
        self.assertTrue(self.lines[-1].startswith("would start: builder-issue-49"))

    def test_launch_entries_are_not_manifest_slots(self):
        self.go()
        self.l.up([S("builder")])
        self.assertEqual(self.names(), ["builder-issue-49", "builder-1"])

    def test_old_state_without_issue_still_loads(self):
        (self.home / "launcher" / "sessions.json").write_text(json.dumps(
            [{"name": "docs-1", "role": "docs", "model": M, "session_id": "s", "started": 0}]))
        self.assertIsNone(self.l.load()[0].issue)


class InboxTest(unittest.TestCase):
    """`swarm inbox` and the dashboard's first section show the same items in the same order."""

    def test_same_lines_as_the_page(self):
        import html
        import re
        g = swarm.dashboard()
        sys.path.insert(0, str(Path(g.__file__).parent))
        import test_needs
        m = test_needs.model()
        cli = swarm.inbox_text(g.needs_you(m), m["now"], g).splitlines()
        self.assertEqual(cli[0], "1. [blocked] #28 GOV-Q: someone waits · builder session blocked- "
                                 "is blocked on it · 50m ago")
        self.assertEqual(cli[1], "   https://github.com/open-agentos/productswarm/issues/28")
        page = g.render(m)["operations.html"]   # the needs-you list (#401)
        section = page[page.index('<ol class="inbox">'):page.index("</ol>")]
        shown = [html.unescape(re.sub(r"<[^>]+>", "", li)).split(" · session")[0]
                 for li in re.findall(r"<li[^>]*>(.*?)</li>", section)]
        self.assertEqual([line.split(". ", 1)[1] for line in cli[0::2]], shown)

    def test_empty(self):
        g = swarm.dashboard()
        self.assertEqual(swarm.inbox_text([], None, g), "Nothing is waiting on you.")

    def test_says_when_reviews_are_left_to_actions(self):
        # #216, GOV-0019: the owner can see the local fallback for reviews is off.
        g = swarm.dashboard()
        self.assertEqual(swarm.inbox_text([], None, g, review_in_actions=True),
                         "Nothing is waiting on you.\n\n" + swarm.REVIEW_IN_ACTIONS)
        self.assertNotIn("Actions", swarm.inbox_text([], None, g, review_in_actions=False))

    def test_reads_the_switch_from_swarm_toml(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "swarm.toml"
            base = ('[watch]\ninterval_minutes = 5\nmax_live = 2\n%s\n'
                    '[[session]]\nrole = "builder"\ncount = 1\nmodel = "m"\n')
            for line, want in (("review_in_actions = true", True), ("review_in_actions = false", False),
                               ("", False), ("review_in_actions = 1", False)):
                path.write_text(base % line)
                self.assertIs(swarm.review_in_actions(path), want, line)
            self.assertIs(swarm.review_in_actions(Path(d) / "missing.toml"), False)


AGENTS = {"productswarm-planner[bot]", "productswarm-builder[bot]"}
PLAN = """# Plan: x

## M1: Daily report runs without the owner

- **Outcome:** a report.
- **Done test:** 5 working days in a row.

## M2: Merges under delegation

- **Status:** done
- **Done test:** over half.

## M3: The desk shows the plan (done)

## M4: Readiness review

- **Done test:** the review is held.
"""


def milestone_issue(m="M1", author="productswarm-planner[bot]", labels=(), waits="nothing.",
                    state="open"):
    it = issue(labels=labels, state=state)
    it["user"] = {"login": author}
    it["body"] = f"Do it.\n\n**Milestone:** {m}\n\n**Files:** `x.py`\n**Waits on:** {waits}\n"
    return it


class GoTest(unittest.TestCase):
    """GOV-0026 (#582): an issue under an open PLAN.md milestone is go without `ready`."""

    def setUp(self):
        self.plan, self.states, self.comments = PLAN, {}, []
        self.reads = []
        # GOV-0031's week for milestone lines (swarm.MILESTONE_UNTIL): read here as still open,
        # since these tests use the real clock (#681).
        self.enterContext(mock.patch.object(swarm, "MILESTONE_UNTIL", swarm.MILESTONE_UNTIL.replace(year=2100)))

    def reader(self):
        def plan():
            self.reads.append("plan")
            return self.plan
        return swarm.GoReader(plan=plan, state=lambda n: self.states.get(n, "open"),
                              comments=lambda: self.comments)

    def go(self, it, events=()):
        return swarm.go_refusals(49, it, list(events), OWNER, AGENTS, self.reader())

    def refusal(self, it, events=()):
        out = self.go(it, events)
        self.assertTrue(out, "expected a refusal")
        return out[0]

    def test_milestone_issue_is_go_without_ready(self):
        self.assertEqual(self.go(milestone_issue()), [])
        self.assertEqual(self.go(milestone_issue("M4", author=OWNER)), [])

    def test_owners_ready_is_still_enough(self):
        self.assertEqual(self.go(issue(), [labeled("ready", OWNER)]), [])
        # ...and is read first: a milestone that would fail doesn't matter.
        self.assertEqual(self.go(milestone_issue("M2", labels=("ready",)), [labeled("ready", OWNER)]), [])
        self.assertEqual(self.reads, [])

    def test_no_milestone_line_needs_ready_as_before(self):
        it = issue(labels=())
        it["body"] = "**Milestone:** no milestone yet (PLAN.md isn't on main).\n"
        (only,) = self.go(it)
        self.assertIn("isn't labelled `ready`", only)
        self.assertEqual(self.reads, [])

    def test_opened_by_someone_else(self):
        msg = self.refusal(milestone_issue(author="stranger"))
        self.assertIn("#49 was opened by stranger, not a swarm App or @mattmcalister", msg)

    def test_milestone_not_in_plan(self):
        self.assertIn("#49's milestone M7 isn't in PLAN.md on main", self.refusal(milestone_issue("M7")))

    def test_no_plan_on_main(self):
        self.plan = None
        self.assertIn("PLAN.md isn't on main", self.refusal(milestone_issue()))

    def test_milestone_marked_done(self):
        self.assertIn("#49's milestone M2 is marked done in PLAN.md", self.refusal(milestone_issue("M2")))
        self.assertIn("M3 is marked done", self.refusal(milestone_issue("M3")))

    def test_waits_on_an_open_issue(self):
        self.states = {456: "closed"}
        self.assertEqual(self.go(milestone_issue(waits="#456.")), [])
        msg = self.refusal(milestone_issue(waits="#456 and #457."))
        self.assertIn("#49 waits on #457, still open", msg)

    def test_hold_label_is_a_veto(self):
        self.assertIn("labelled `hold`", self.refusal(milestone_issue(labels=("hold",))))

    def test_any_owner_comment_is_a_veto(self):
        self.comments = [{"user": {"login": "productswarm-builder[bot]"}, "body": "on it"}]
        self.assertEqual(self.go(milestone_issue()), [])
        self.comments.append({"user": {"login": OWNER}, "body": "looks good"})
        self.assertIn("@mattmcalister commented on #49", self.refusal(milestone_issue()))

    def test_closed_is_refused(self):
        self.assertEqual(self.go(milestone_issue(state="closed")), ["#49 is closed"])

    def test_ready_by_someone_else_falls_back_to_the_milestone(self):
        it = milestone_issue(labels=("ready",))
        self.assertEqual(self.go(it, [labeled("ready", "productswarm-planner[bot]")]), [])
        self.plan = None
        out = self.go(it, [labeled("ready", "productswarm-planner[bot]")])
        self.assertIn("PLAN.md isn't on main", out[0])
        self.assertIn("added by productswarm-planner[bot]", out[1])

    def test_a_question_with_a_milestone_line_is_not_go(self):
        (only,) = self.go(milestone_issue(labels=("gov:question",)))
        self.assertIn("isn't labelled `ready`", only)
        self.assertEqual(self.reads, [])

    def test_milestone_line(self):
        for body, want in [("**Milestone:** M2\n", 2), ("**milestone:** m12 (the desk)\n", 12),
                           ("**Milestone:** no milestone yet\n", None), (None, None),
                           ("See `**Milestone:** M1` in prose.\n", None)]:
            self.assertEqual(swarm.milestone_of(body), want, body)

    def test_plan_on_main_has_four_open_milestones(self):
        text = (Path(__file__).resolve().parent.parent / "PLAN.md").read_text()
        self.assertEqual(swarm.plan_milestones(text), {1: False, 2: False, 3: False, 4: False})

    def test_agent_logins_from_jurisdictions(self):
        logins = swarm.agent_logins()
        self.assertIn("productswarm-builder[bot]", logins)
        self.assertIn("productswarm-planner[bot]", logins)
        self.assertNotIn(OWNER, logins)


class LaunchHelpersTest(unittest.TestCase):
    def test_owner_login_from_jurisdictions(self):
        self.assertEqual(swarm.owner_login(), OWNER)

    def test_model_for(self):
        path = str(manifest.DEFAULT_PATH)
        self.assertEqual(swarm.model_for("builder", "claude-haiku-5-5", path), "claude-haiku-5-5")
        self.assertEqual(swarm.model_for("builder", None, path), manifest.load()[1].model)
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as f:
            f.write('[[session]]\nrole = "docs"\ncount = 1\nmodel = "m"\n')
        self.addCleanup(os.unlink, f.name)
        with self.assertRaises(LookupError):
            swarm.model_for("builder", None, f.name)

    def test_launch_name(self):
        self.assertEqual(swarm.launch_name("docs", 7, set()), "docs-issue-7")
        self.assertEqual(swarm.launch_name("docs", 7, {"docs-issue-7", "docs-issue-7-2"}),
                         "docs-issue-7-3")


@unittest.skipUnless(os.path.exists("/bin/bash"), "needs /bin/bash")
class RealShellTest(unittest.TestCase):
    """Runs the real window command through a shell, with a stand-in ops/swarm-session
    that just sleeps: checks the pid file names the process that carries --session-id,
    and that stop() ends it. No Terminal, no Claude Code."""

    def git(self, *args, cwd=None):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd,
                       check=True, capture_output=True)

    SLEEPS = '#!/bin/bash\nexec python3 -c "import time; time.sleep(30)" "$@"\n'

    def repo(self, tmp: Path, script: str = SLEEPS) -> Path:
        """A real checkout whose origin's main has a stand-in ops/swarm-session that sleeps."""
        origin, seed, root = tmp / "origin.git", tmp / "seed", tmp / "repo"
        self.git("init", "-q", "--bare", "-b", "main", str(origin))
        self.git("clone", "-q", str(origin), str(seed))
        (seed / "ops").mkdir()
        fake = seed / "ops" / "swarm-session"
        fake.write_text(script)
        fake.chmod(0o755)
        (seed / ".gitignore").write_text(".worktrees/\n.claude/settings.local.json\n")
        self.git("add", "-A", cwd=seed)
        self.git("commit", "-q", "-m", "seed", cwd=seed)
        self.git("push", "-q", "origin", "HEAD:main", cwd=seed)
        self.git("clone", "-q", str(origin), str(root))
        return root

    def wait_running(self, l, e):
        for _ in range(50):
            if l.state(e) == "running":
                break
            time.sleep(0.1)
        self.assertEqual(l.state(e), "running")

    def test_pid_chain_worktree_and_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp).resolve()
            root, home = self.repo(tmp), tmp / "home"
            procs, lines = [], []
            l = swarm.Launcher(home, root=root, out=lines.append,
                               run=lambda cmd: procs.append(subprocess.Popen(["/bin/sh", "-c", cmd])))
            try:
                self.assertEqual(l.up([S("builder")]), 0)
                e = l.load()[0]
                wt = root / ".worktrees" / e.session_id
                self.wait_running(l, e)
                self.assertEqual(l.pid(e), procs[0].pid)       # both exec's kept the pid
                # #550: the typed line is short and runs the window's script, which is command().
                self.assertEqual(procs[0].args[2], l.typed(e))
                self.assertLess(len(l.typed(e).encode()), swarm.MAX_CANON)
                self.assertEqual(l.window_file(e.session_id).read_text(), l.command(e) + "\n")
                settings = json.loads((wt / ".claude" / "settings.local.json").read_text())
                self.assertIn(f"{home}/runtime/heartbeat/hook.py", json.dumps(settings["hooks"]["SessionStart"]))
                rev = lambda d, r: subprocess.run(["git", "-C", str(d), "rev-parse", r],
                                                  capture_output=True, text=True).stdout
                self.assertEqual(rev(home / "runtime", "HEAD"), rev(root, "origin/main"))   # pinned copy
                self.assertEqual(subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                                                capture_output=True, text=True).stdout, "")
                self.assertEqual(l.up([S("builder")]), 0)      # already running
                self.assertEqual(len(procs), 1)
                l.clock = time.time
                self.assertEqual(l.stop("builder-1"), 0)
                self.assertIsNotNone(procs[0].wait(timeout=5))
                self.assertEqual(l.load(), [])
                self.assertFalse(wt.exists())                  # clean and on origin: removed

                # A session that leaves a commit nobody pushed: its worktree is kept and listed.
                self.assertEqual(l.up([S("builder")]), 0)
                e = l.load()[0]
                wt = root / ".worktrees" / e.session_id
                self.wait_running(l, e)
                (wt / "work.txt").write_text("x")
                self.git("add", "work.txt", cwd=wt)
                self.git("commit", "-q", "-m", "unpushed", cwd=wt)
                self.assertEqual(l.stop("builder-1"), 0)
                procs[1].wait(timeout=5)
                self.assertTrue(wt.exists())
                self.assertIn(f"worktree kept: {wt} (uncommitted or unpushed work)", lines)
                self.assertEqual(l.live(), [])
                self.assertEqual(l.kept, [wt])
            finally:
                for p in procs:
                    if p.poll() is None:
                        p.kill()


    def test_headless_run_writes_its_result_and_keeps_the_pid(self):
        # #147: a stand-in swarm-session that prints its banner as the real one does, then
        # its argv as JSON, as claude -p --output-format json prints one JSON result.
        script = ('#!/bin/bash\necho "swarm-session: $1 as stand-in[bot]"\n'
                  'exec python3 -c "import json, os, sys; print(json.dumps({\'pid\': os.getpid(), '
                  '\'argv\': sys.argv[1:]}))" "$@"\n')
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp).resolve()
            root, home = self.repo(tmp, script), tmp / "home"
            procs, lines = [], []
            l = swarm.Launcher(home, root=root, out=lines.append,
                               run=lambda cmd: procs.append(subprocess.Popen(
                                   ["/bin/sh", "-c", cmd], stdout=subprocess.PIPE, text=True)))
            e = swarm.Started("builder-issue-49", "builder", "m", str(uuid.uuid4()), time.time(),
                              issue=49, by="watch", budget_usd=15, max_turns=200)
            self.assertTrue(l.start(e, []))
            window = procs[0].communicate(timeout=10)[0]
            self.assertIn("headless run (claude -p)", window)
            self.assertIn(str(l.result_file(e.session_id)), window)
            banner, result = l.result_file(e.session_id).read_text().splitlines()
            self.assertEqual(banner, "swarm-session: builder as stand-in[bot]")
            result = json.loads(result)
            self.assertEqual(result["pid"], l.pid(e))                 # both exec's kept the pid
            self.assertEqual(result["argv"], ["builder", "--model", "m", "--session-id", e.session_id,
                                              "-p", swarm.opener("builder", 49),
                                              "--permission-mode", "auto", "--disallowedTools", *swarm.DENY,
                                              "--max-budget-usd", "15", "--max-turns", "200",
                                              "--output-format", "json"])


class StatusTest(Base):
    """#457: `swarm status`, swarm watch's state with cost, from local files only."""

    NOW = dt.datetime(2026, 11, 6, 12, 0, tzinfo=dt.timezone.utc)

    def write(self, st):
        (self.home / "launcher" / "watch.json").write_text(json.dumps(st))

    def text(self, st, live=(), holder=None, interval=5, costs=None):
        import watch
        g = swarm.dashboard()
        return watch.status_text(st, list(live), self.NOW, holder=holder, interval=interval,
                                 cost_of=lambda sid: (costs or {}).get(sid), ago=g.ago)

    def at(self, **kw):
        return (self.NOW - dt.timedelta(**kw)).isoformat()

    def test_empty_state(self):
        import watch
        out = self.text(watch.load_state(self.l))
        self.assertTrue(out.startswith("swarm watch: not running (nothing holds watch.lock) · last check never"))
        for title in ("running", "held", "skipped", f"failed in the last {watch.RUNS_DAYS} days"):
            self.assertIn(f"\n{title}: none", out)
        self.assertNotIn("stale", out)

    def test_held_and_skipped_triggers_with_their_reason(self):
        w = lambda code, ref, args=None: {"key": ref, "kind": "build", "ref": ref, "why": "<secret why>",
                                          "reason": "free text", "code": code, "args": args or {},
                                          "since": self.at(hours=2)}
        st = {"checked": self.at(minutes=1), "runs": {},
              "waiting": [w("waits_on", "#9"), w("no_role", "#10")]}
        out = self.text(st, holder=4242)
        self.assertIn("swarm watch: running (pid 4242) · last check 1m ago", out)
        self.assertIn(f"held (1):\n- [build] #9 · {watch_reason('waits_on')} · since 2h ago", out)
        self.assertIn(f"skipped (1):\n- [build] #10 · {watch_reason('no_role')} · since 2h ago", out)
        self.assertNotIn("secret", out)

    def test_failed_run_with_cost_and_running_with_cost_so_far(self):
        run = {"name": "builder-issue-1", "kind": "build", "ref": "#1", "started": self.at(hours=1, minutes=5)}
        st = {"checked": self.at(minutes=2), "waiting": [], "runs": {
            "a": {**run, "session_id": "live-sid"},
            "b": {**run, "session_id": "s2", "ref": "#2", "ending": "ended at cap", "ended": self.at(hours=3),
                  "cost_usd": 3.5},
            "c": {**run, "session_id": "s3", "ref": "#3", "ending": "done", "ended": self.at(hours=1),
                  "cost_usd": 1.0},
        }}
        live = [swarm.Started("builder-issue-1", "builder", M, "live-sid", 0, issue=1, by="watch")]
        out = self.text(st, live, costs={"live-sid": 2.25})
        self.assertIn("running (1):\n- [build] #1 builder · 1h 05m · $2.25 so far (est.)", out)
        self.assertIn("failed in the last 7 days (1):\n- [build] #2 · at cap · ended 3h ago · $3.50 (est.)", out)
        self.assertNotIn("#3", out)                      # done is not failed

    def test_stale_checked(self):
        st = {"checked": self.at(minutes=11), "runs": {}, "waiting": []}
        self.assertIn("last check 11m ago · stale: checks are every 5 min", self.text(st))
        self.assertNotIn("stale", self.text(st, interval=10))

    def test_spool_cost_reads_the_last_event(self):
        import watch
        (self.home / "events").mkdir()
        ev = {"model": M, "token_counts": {"input": 0, "cache_creation": 0, "cache_read": 0,
                                           "output": 1_000_000}}
        (self.home / "events" / "sid.jsonl").write_text(json.dumps({**ev, "model": "unknown"}) + "\n"
                                                          + json.dumps(ev) + "\n")
        self.assertEqual(watch.spool_cost(self.home, "sid"), 20.0)
        self.assertIsNone(watch.spool_cost(self.home, "missing"))

    def test_lock_holder_needs_a_live_swarm_watch(self):
        import watch
        lock = self.home / "launcher" / watch.LOCK_FILE
        self.assertIsNone(watch.lock_holder(self.l))
        lock.write_text("77\n")
        self.fake.procs[77] = "python3 /r/launcher/swarm.py watch"
        self.assertEqual(watch.lock_holder(self.l), 77)
        self.fake.procs[77] = "vim notes.txt"            # the pid was reused
        self.assertIsNone(watch.lock_holder(self.l))

    def test_cli_makes_no_network_calls(self):
        self.write({"checked": self.at(minutes=1), "acted": {}, "waiting": [], "runs": {}})
        toml = self.home / "swarm.toml"
        toml.write_text("")
        with mock.patch.object(subprocess, "run", side_effect=AssertionError("no subprocess")):
            self.assertEqual(swarm.main(["status", "--manifest", str(toml)], self.l), 0)
        self.assertIn("swarm watch: not running", self.lines[-1])
        self.assertIn("running: none", self.lines[-1])

    def test_bad_watch_json_fails_cleanly(self):
        (self.home / "launcher" / "watch.json").write_text("{")
        self.assertEqual(swarm.main(["status"], self.l), 1)
        self.assertIn("not valid JSON", self.lines[-1])


def watch_reason(code):
    import watch
    return watch.REASONS[code]


class SnapshotTest(unittest.TestCase):
    """swarm ls, inbox and every watch tick go through snapshot(); only the page reads the
    Actions API (#356, the review on #378)."""

    def actions_calls(self, call):
        calls = []

        def fake(cmd, **_):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        with mock.patch.object(subprocess, "run", fake):
            call()
        return [c for c in calls if any("/actions/" in str(a) for a in c)]

    def test_snapshot_makes_no_actions_api_calls(self):
        now = dt.datetime(2026, 11, 4, tzinfo=dt.timezone.utc)
        self.assertEqual(self.actions_calls(lambda: swarm.snapshot("o/r", 15, now)), [])

    def test_the_page_still_reads_them(self):
        now = dt.datetime(2026, 11, 4, tzinfo=dt.timezone.utc)
        g = swarm.dashboard()
        self.assertTrue(self.actions_calls(lambda: g.fetch("o/r", now, days=1, with_actions=True)))


if __name__ == "__main__":
    unittest.main()
