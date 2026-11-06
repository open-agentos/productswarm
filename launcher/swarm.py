#!/usr/bin/env python3
"""swarm: start, list and stop the sessions in swarm.toml (v1 launcher, GOV-0005 item L2).

    launcher/swarm up [--dry-run]   start every manifest session that isn't already running
    launcher/swarm ls               list live sessions from the heartbeat tracking issues
    launcher/swarm stop <session>   end one session the launcher started (name or session id)
    launcher/swarm launch <role> --issue N [--pr M] [--model M] [--force] [--dry-run]
                                    start one session on issue N (L3); with --pr, it
                                    responds to requested changes on PR M (GOV-0011)
    launcher/swarm inbox            what's waiting on the owner, most urgent first (L5)
    launcher/swarm cost             cost per PR of the runs swarm watch recorded (#176; local only)
    launcher/swarm status           swarm watch's state with cost, from local files only (#457)
    launcher/swarm watch [--dry-run]
                                    the v2 wake-up loop: start sessions on triggers, within
                                    the [watch] limits in swarm.toml (#90, GOV-0010; watch.py)

Each session runs `ops/swarm-session <role> --model <model> --session-id <uuid> <opener>`,
unchanged, in a new Terminal window: the owner's answer on #43.

A run that `swarm watch` starts (by="watch") is headless instead (#147): the same call
with `-p <opener>`, `--permission-mode auto` and `--disallowedTools` for merging and label
edits (GOV-0013, patterns in DENY), `--max-budget-usd <the role's spend_cap_usd>` and
`--max-turns <[watch] max_turns>` (GOV-0012), and `--output-format json`, with stdout
written to ~/.productswarm/launcher/<session id>.result.json. It still opens its own
window, so the pid file, `ls` and `stop` work unchanged; the window prints one line
saying the run is headless and where its result goes, then shows only stderr. The run
ends when it is done or at either limit. `swarm up` and `swarm launch` stay interactive. That runtime is kept
behind one function, open_terminal(). Choosing the session id up front is what ties a
window to its heartbeat tracking issue: the hook uses Claude Code's session id.

Each session runs in its own git worktree, `.worktrees/<session id>` in this checkout,
detached at origin/main, so sessions never share a working tree (#93). The launcher
writes the heartbeat hook entries into the worktree's .claude/settings.local.json,
pointing at the pinned copy in ~/.productswarm/runtime (heartbeat/install.py), which
each launcher run first refreshes to origin/main. For a run `swarm watch` started, it
also writes a Stop hook from the same pinned copy (stophook.py, #148) that keeps the run
going until its role's done-condition is met.
Once a session has exited, its worktree is removed if it is clean and its HEAD is on
origin; otherwise it is kept and `swarm ls` lists it. Work is never deleted.

What the launcher started is recorded locally, never on GitHub:
    ~/.productswarm/launcher/sessions.json   name, role, model, session id, start time;
                                             every read-change-write holds an flock on
                                             sessions.lock beside it (#272)
    ~/.productswarm/launcher/<id>.pid        written by the window's shell before exec
    ~/.productswarm/launcher/<id>.result.json  a headless run's stdout: ops/swarm-session's
                                             one-line banner, then the JSON result (#147)
    ~/.productswarm/launcher/watch.json      triggers `swarm watch` acted on or is holding,
                                             and how each run it started ended (#149)
(PRODUCTSWARM_HOME moves ~/.productswarm, as for the heartbeat.)

`stop` sends SIGTERM. Claude Code then runs its SessionEnd hook, so the heartbeat
records `stopped` with no change to the hook (GOV-0002 to GOV-0004).
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import manifest  # noqa: E402

sys.path.insert(0, str(ROOT / "heartbeat"))
import install  # noqa: E402

SWARM_SESSION = ROOT / "ops" / "swarm-session"
WORKTREES = ".worktrees"   # under the checkout root; gitignored
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
# GOV-0013's backstop for headless runs: agents never merge (GOV-0011) and never add or
# remove labels (GOV-0006). Auto mode's classifier covers the rest; this is not a fence.
# The `=` forms are here because `--add-label=ready` doesn't match `--add-label *`.
DENY = (
    "Bash(gh pr merge *)",
    "Bash(gh issue edit * --add-label *)", "Bash(gh issue edit * --remove-label *)",
    "Bash(gh issue edit * --add-label=*)", "Bash(gh issue edit * --remove-label=*)",
    "Bash(gh pr edit * --add-label *)", "Bash(gh pr edit * --remove-label *)",
    "Bash(gh pr edit * --add-label=*)", "Bash(gh pr edit * --remove-label=*)",
    "Bash(gh label *)",
    "Bash(gh api *labels*)", "Bash(gh api *merge*)",
)
ISSUE_WORD_RE = re.compile(r"\bissue\s+#?(\d+)\b", re.IGNORECASE)   # heartbeat/hook.py's rule
START_GRACE = 60      # seconds a session may take to write its pid file before it counts as failed
STOP_WAIT = 20        # seconds to wait for a session to exit after SIGTERM


def opener(role: str, issue: int | None = None, pr: int | None = None,
           called_by: str | None = None, call_why: str | None = None) -> str:
    """The prompt ops/swarm-session uses when given no args (it passes args on unchanged).

    With an issue, it names it: the heartbeat's `working_on` detection matches
    "issue #N" in a prompt, so the session's current issue is set with no hook change.
    With a PR too, the session responds to requested changes on it (GOV-0011). With only a
    PR, it reviews that PR once (a reviewer run in Actions, #215). With called_by, the
    role was called in to the issue (GOV-0023, #520): the prompt says by whom and why, and
    that it posts one comment."""
    if issue and called_by:
        # "issue #M" in the why would give the heartbeat two issues and so none: say "#M".
        safe = ISSUE_WORD_RE.sub(r"#\1", call_why) if call_why else ""
        why = f" because: {safe}" if safe else ""
        then = (f"answer a call-in on issue #{issue}: {called_by} called you in (GOV-0023){why}. "
                f"That call counts as asking you in (GOVERNANCE.md section 8). Read the issue, post "
                f"one comment on it with your contribution, and stop")
    elif issue and pr:
        then = f"respond to the requested changes on PR #{pr}, which closes issue #{issue}"
    elif pr:     # a reviewer on one PR: a run in GitHub Actions (#215)
        then = f"review PR #{pr} only, in one pass, and stop"
    else:
        then = f"work on issue #{issue}" if issue else "begin"
    return f"You are the {role} for productswarm. Read CLAUDE.md, PRODUCT.md and roles/{role}.md, then {then}."


def headless_flags(budget_usd: float, max_turns: int, extra_deny: tuple[str, ...] = ()) -> list[str]:
    """The flags after `-p <opener>` for a headless run, as an argv (not shell-quoted):
    GOV-0013's permission mode and denies, GOV-0012's budget and turn ceiling, and a JSON
    result. Shared by runs `swarm watch` starts and reviewer runs in Actions (#215).
    extra_deny adds patterns after DENY for one kind of run only: reviewer runs in Actions
    pass actions_review.REVIEWER_DENY (#389); runs `swarm watch` starts pass none.

    --disallowedTools takes several values, so another flag must follow it: otherwise
    claude would read the next word as one more pattern."""
    return ["--permission-mode", "auto",
            "--disallowedTools", *DENY, *extra_deny,
            "--max-budget-usd", f"{budget_usd:g}", "--max-turns", str(max_turns),
            "--output-format", "json"]


def home() -> Path:
    return Path(os.environ.get("PRODUCTSWARM_HOME", "~/.productswarm")).expanduser()


# ---------------------------------------------------------------- the runtime (#43)

def applescript_string(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def open_terminal(command: str) -> None:
    """Run a shell command in a new macOS Terminal window (#43, option 1).

    The only place that knows how sessions run. Swap this to change the runtime."""
    if sys.platform != "darwin":
        raise RuntimeError("swarm up opens Terminal windows, which needs macOS (#43)")
    script = f"tell application \"Terminal\"\n  do script {applescript_string(command)}\n  activate\nend tell"
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(f"osascript failed: {r.stderr.strip()[:300]}")


def process_command(pid: int) -> str | None:
    """The command line of a running process, or None if there is none."""
    try:
        r = subprocess.run(["ps", "-o", "command=", "-p", str(pid)],
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return r.stdout.strip() or None


run_git = install.run_git


# ---------------------------------------------------------------- local state

@dataclass
class Started:
    """A session the launcher started."""
    name: str               # e.g. builder-1
    role: str
    model: str
    session_id: str
    started: float          # unix time the window was opened
    issue: int | None = None  # set by `swarm launch --issue`
    by: str | None = None     # "watch" if `swarm watch` started it (counts toward its ceiling)
    pr: int | None = None     # set by `swarm launch --pr`: respond on this PR (GOV-0011)
    budget_usd: float | None = None   # by="watch": --max-budget-usd, the role's spend_cap_usd (GOV-0012)
    max_turns: int | None = None      # by="watch": --max-turns, [watch] max_turns (GOV-0012)
    called_by: str | None = None      # a call-in run (GOV-0023, #520): who called it in
    call_why: str | None = None       # and why, from the `Call in:` line

    @classmethod
    def from_dict(cls, d: dict) -> "Started":
        return cls(**{k: d[k] for k in ("name", "role", "model", "session_id", "started")},
                   issue=d.get("issue"), by=d.get("by"), pr=d.get("pr"),
                   budget_usd=d.get("budget_usd"), max_turns=d.get("max_turns"),
                   called_by=d.get("called_by"), call_why=d.get("call_why"))


def recovered(sid: str, cmd: str, started: float) -> Started:
    """An entry for a running session that sessions.json lost (#272), from its command
    line: `claude --model M --session-id SID [-p] <opener> ...`."""
    model = re.search(r"--model (\S+)", cmd)
    role = re.search(r"You are the (\w+) for productswarm", cmd)
    issue = re.search(r"issue #(\d+)", cmd)
    pr = re.search(r"PR #(\d+)", cmd)
    r = role.group(1) if role else "unknown"
    return Started(name=f"{r}-recovered-{sid[:8]}", role=r, model=model.group(1) if model else "unknown",
                   session_id=sid, started=started, issue=int(issue.group(1)) if issue else None,
                   pr=int(pr.group(1)) if pr else None, by="watch" if " -p " in cmd else None)


@dataclass
class Launcher:
    home: Path
    root: Path = ROOT
    run: Callable[[str], None] = open_terminal
    proc: Callable[[int], str | None] = process_command
    kill: Callable[[int, int], None] = os.kill
    clock: Callable[[], float] = time.time
    sleep: Callable[[float], None] = time.sleep
    out: Callable[[str], None] = print
    git: Callable[[list[str]], tuple[int, str]] = run_git
    kept: list[Path] = field(default_factory=list)   # exited sessions' worktrees with work in them
    fetched: bool = False
    hook: str | None = None         # the pinned hook path, once refreshed in this run

    @property
    def dir(self) -> Path:
        return self.home / "launcher"

    @property
    def state_file(self) -> Path:
        return self.dir / "sessions.json"

    def pid_file(self, sid: str) -> Path:
        return self.dir / f"{sid}.pid"

    def result_file(self, sid: str) -> Path:
        """Where a headless run's stdout goes: the banner, then its JSON result (#147)."""
        return self.dir / f"{sid}.result.json"

    def load(self) -> list[Started]:
        try:
            data = json.loads(self.state_file.read_text())
        except FileNotFoundError:
            return []
        except ValueError as e:
            raise RuntimeError(f"{self.state_file} is not valid JSON: {e}") from None
        return [Started.from_dict(d) for d in data]

    def save(self, entries: list[Started]) -> None:
        """Write the state file atomically through a temp file of its own, so two writers
        never rename each other's (#272). A read-change-write must also hold locked()."""
        self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, tmp = tempfile.mkstemp(dir=self.dir, prefix=".sessions.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(json.dumps([e.__dict__ for e in entries], indent=1) + "\n")
            os.replace(tmp, self.state_file)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    @property
    def lock_file(self) -> Path:
        return self.dir / "sessions.lock"

    @contextlib.contextmanager
    def locked(self):
        """Hold an exclusive lock on the state file across a read-change-write, so a
        `swarm launch` during a `swarm watch` tick is never lost (#272). Not re-entrant."""
        self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        with open(self.lock_file, "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def add(self, entry: Started) -> None:
        """Record one entry, replacing any with the same session id (a recovered one)."""
        with self.locked():
            self.save([e for e in self.load() if e.session_id != entry.session_id] + [entry])

    def remove(self, sid: str) -> None:
        with self.locked():
            entries = self.load()
            rest = [e for e in entries if e.session_id != sid]
            if len(rest) != len(entries):
                self.save(rest)

    def pid(self, s: Started) -> int | None:
        try:
            return int(self.pid_file(s.session_id).read_text().strip())
        except (FileNotFoundError, ValueError):
            return None

    def state(self, s: Started) -> str:
        """running, starting (window opened, no pid yet) or exited.

        A pid counts only while its command line still carries this session's id, so a
        reused pid is never mistaken for the session (or sent a signal)."""
        pid = self.pid(s)
        if pid is None:
            return "starting" if self.clock() - s.started < START_GRACE else "exited"
        cmd = self.proc(pid)
        return "running" if cmd and f"--session-id {s.session_id}" in cmd else "exited"

    def orphans(self, entries: list[Started]) -> list[Started]:
        """Sessions with a pid file and a running process but no entry: an entry lost to a
        concurrent write before #272. Rebuilt from the process's command line, which
        carries the model, the session id and the opener (role, issue, PR)."""
        known = {e.session_id for e in entries}
        found = []
        for f in sorted(self.dir.glob("*.pid")) if self.dir.is_dir() else []:
            sid = f.stem
            if sid in known or not UUID_RE.match(sid):
                continue
            try:
                cmd = self.proc(int(f.read_text().strip()))
                started = f.stat().st_mtime
            except (OSError, ValueError):
                continue
            if not cmd or f"--session-id {sid}" not in cmd:
                continue
            found.append(recovered(sid, cmd, started))
        return found

    def running(self) -> list[Started]:
        """Entries still running or starting, without touching the state file (for dry runs)."""
        entries = self.load()
        return [e for e in entries + self.orphans(entries) if self.state(e) != "exited"]

    def live(self) -> list[Started]:
        """Entries still running or starting. Exited ones are dropped from the state file,
        lost ones recovered into it (orphans), and exited sessions' worktrees removed if
        nothing would be lost (tidy)."""
        with self.locked():
            entries = self.load()
            live = [e for e in entries if self.state(e) != "exited"]
            for e in entries:
                if e not in live:
                    self.pid_file(e.session_id).unlink(missing_ok=True)
                    (self.dir / f"{e.session_id}.stop.json").unlink(missing_ok=True)   # stophook.py
            found = self.orphans(entries)
            for e in found:
                self.out(f"recovered: {e.name}  {e.session_id} (running, but missing from "
                         f"{self.state_file.name}; #272)")
            live += found
            if live != entries:
                self.save(live)
        self.tidy(live)
        return live

    # ------------------------------------------------------------ worktrees (#93)

    def worktree(self, sid: str) -> Path:
        return self.root / WORKTREES / sid

    def hook_path(self) -> str:
        """The hook script every session runs: the pinned copy at origin/main (#93, step C),
        refreshed once per launcher run, so only merged code runs as a hook."""
        if self.hook is None:
            self.fetch_main()
            self.hook = install.refresh_runtime(self.root, self.home / "runtime", self.git)
        return self.hook

    def git_ok(self, *args: str) -> str:
        rc, out = self.git(list(args))
        if rc:
            raise RuntimeError(f"git {' '.join(a for a in args if not a.startswith('/'))[:80]} failed: {out[:300]}")
        return out

    def fetch_main(self) -> None:
        if not self.fetched:
            self.git_ok("-C", str(self.root), "fetch", "-q", "origin", "main")
            self.fetched = True

    def prepare(self, s: Started) -> None:
        """Create the session's worktree at origin/main and write its hook settings."""
        hook = self.hook_path()          # fetches, and refreshes the pinned copy first
        wt = self.worktree(s.session_id)
        self.git_ok("-C", str(self.root), "worktree", "add", "-q", "--detach", str(wt), "origin/main")
        base = install.read_settings(self.root / ".claude" / "settings.local.json")
        settings = install.with_hooks(base, hook=hook)
        if s.by == "watch":      # loop-started runs keep going until they're done (#148)
            import stophook      # here, not at the top: stophook imports this module
            settings = stophook.with_stop_hook(settings, stophook.script_for(hook))
        install.write_settings(wt / ".claude" / "settings.local.json", settings)

    def removable(self, wt: Path) -> bool:
        """Clean (nothing uncommitted or untracked) and HEAD is on a remote branch."""
        rc, status = self.git(["-C", str(wt), "status", "--porcelain"])
        if rc or status:
            return False
        rc, remote = self.git(["-C", str(wt), "branch", "-r", "--contains", "HEAD"])
        return rc == 0 and bool(remote)

    def tidy(self, live: list[Started]) -> list[Path]:
        """Remove exited sessions' worktrees that hold no unpushed work; keep the rest.

        Only touches `.worktrees/<uuid>` with no live entry, so a worktree someone made
        by hand, or a session still starting, is never removed."""
        d = self.root / WORKTREES
        alive = {e.session_id for e in live}
        kept, removed = [], False
        for wt in sorted(d.iterdir()) if d.is_dir() else []:
            if not wt.is_dir() or not UUID_RE.match(wt.name) or wt.name in alive:
                continue
            if self.removable(wt) and self.git(["-C", str(self.root), "worktree", "remove", str(wt)])[0] == 0:
                removed = True
            else:
                kept.append(wt)
        if removed:
            self.git(["-C", str(self.root), "worktree", "prune"])
        self.kept = kept
        return kept

    # ------------------------------------------------------------ up

    def command(self, s: Started) -> str:
        """The shell command a window runs: record the pid, then exec the worktree's
        ops/swarm-session, unchanged. It cd's to its own root, so the session runs there.

        Run through /bin/bash so `$$` means the same whatever the owner's login shell is;
        both exec's keep that pid, so it ends up being claude's.

        A run `swarm watch` started (by="watch") is headless (#147): see headless_args()."""
        wt = self.worktree(s.session_id)
        session = ["exec", shlex.quote(str(wt / "ops" / "swarm-session")), shlex.quote(s.role),
                   "--model", shlex.quote(s.model), "--session-id", s.session_id]
        prompt = shlex.quote(opener(s.role, s.issue, s.pr, s.called_by, s.call_why))
        if s.by == "watch":
            result = shlex.quote(str(self.result_file(s.session_id)))
            note = shlex.quote(f"swarm: headless run (claude -p); it ends when done or at its budget, "
                               f"and its result is written to {self.result_file(s.session_id)}")
            tail = ["echo", note, "&&", *session, "-p", prompt, *self.headless_args(s), ">|", result]
        else:
            tail = [*session, prompt]
        inner = " ".join([
            "cd", shlex.quote(str(wt)), "&&",
            "echo $$ >|", shlex.quote(str(self.pid_file(s.session_id))), "&&", *tail,
        ])
        return "exec /bin/bash -c " + shlex.quote(inner)

    @staticmethod
    def headless_args(s: Started) -> list[str]:
        """headless_flags() for a loop-started run, shell-quoted (#147)."""
        if s.budget_usd is None or s.max_turns is None:
            raise RuntimeError(f"{s.name}: a run swarm watch starts needs a budget and a turn "
                               f"ceiling (GOV-0012)")
        return [shlex.quote(a) for a in headless_flags(s.budget_usd, s.max_turns)]

    def plan(self, sessions: list[manifest.Session], live: list[Started]) -> list[manifest.Session]:
        """Manifest sessions with no live launcher session of the same name: the shortfall."""
        running = {e.name for e in live}
        return [s for s in sessions if s.name not in running]

    def up(self, sessions: list[manifest.Session], dry_run: bool = False) -> int:
        live = self.live()
        wanted = {s.name for s in sessions}
        for e in live:
            note = "" if e.name in wanted else "  (not in the manifest; left running)"
            self.out(f"already {self.state(e)}: {e.name}  {e.model}  {e.session_id}{note}")
        todo = self.plan(sessions, live)
        if not todo:
            self.out("nothing to start: every manifest session is running")
            return 0
        failed = sum(not self.start(Started(name=s.name, role=s.role, model=s.model,
                                            session_id=str(uuid.uuid4()), started=self.clock()),
                                    live, dry_run)
                     for s in todo)
        return 1 if failed else 0

    def start(self, entry: Started, live: list[Started], dry_run: bool = False) -> bool:
        """Open one session's window and record it. Returns False if it couldn't start."""
        on = f"  on #{entry.issue}" if entry.issue else ""
        on += f", PR #{entry.pr}" if entry.pr else ""
        if dry_run:
            self.out(f"would start: {entry.name}  {entry.model}{on}\n"
                     f"  git worktree add --detach {self.worktree(entry.session_id)} origin/main\n"
                     f"  {self.command(entry)}")
            return True
        self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            self.prepare(entry)
        except (RuntimeError, OSError) as e:
            self.out(f"failed to start {entry.name}: {e}")
            return False
        self.add(entry)   # before the window opens, so its pid file never has no entry (#272)
        try:
            self.run(self.command(entry))
        except (RuntimeError, OSError, subprocess.SubprocessError) as e:
            self.out(f"failed to start {entry.name}: {e}")
            self.remove(entry.session_id)
            self.git(["-C", str(self.root), "worktree", "remove", "--force",
                      str(self.worktree(entry.session_id))])   # new and unused: nothing to lose
            return False
        live.append(entry)
        self.out(f"started: {entry.name}  {entry.model}{on}  {entry.session_id}")
        return True

    # ------------------------------------------------------------ stop

    def find(self, ref: str, entries: list[Started]) -> Started:
        exact = [e for e in entries if ref in (e.name, e.session_id)]
        matches = exact or [e for e in entries if len(ref) >= 6 and e.session_id.startswith(ref)]
        if len(matches) == 1:
            return matches[0]
        names = ", ".join(e.name for e in entries) or "none"
        if not matches:
            raise LookupError(f"no running session '{ref}' started by the launcher (running: {names})")
        raise LookupError(f"'{ref}' matches more than one session: {', '.join(e.name for e in matches)}")

    def heartbeat_stopped(self, sid: str) -> bool:
        try:
            return bool(json.loads((self.home / "state" / f"{sid}.json").read_text()).get("stopped"))
        except (FileNotFoundError, ValueError):
            return False

    def stop(self, ref: str) -> int:
        live = self.live()
        try:
            s = self.find(ref, live)
        except LookupError as e:
            self.out(f"swarm stop: {e}")
            return 1
        pid = self.pid(s)
        if self.state(s) != "running" or pid is None:
            self.out(f"swarm stop: {s.name} hasn't started yet; try again in a few seconds")
            return 1
        self.kill(pid, signal.SIGTERM)   # Claude Code runs SessionEnd on SIGTERM
        deadline = self.clock() + STOP_WAIT
        while self.state(s) == "running" and self.clock() < deadline:
            self.sleep(0.5)
        if self.state(s) == "running":
            self.out(f"swarm stop: sent SIGTERM to {s.name} (pid {pid}) but it is still running; "
                     f"check its Terminal window")
            return 1
        self.pid_file(s.session_id).unlink(missing_ok=True)
        self.remove(s.session_id)
        rest = [e for e in live if e is not s]
        if self.worktree(s.session_id) in self.tidy(rest):
            self.out(f"worktree kept: {self.worktree(s.session_id)} (uncommitted or unpushed work)")
        if self.heartbeat_stopped(s.session_id):
            self.out(f"stopped: {s.name}; the heartbeat recorded `stopped`")
        else:
            self.out(f"stopped: {s.name}, but the heartbeat has no `stopped` for {s.session_id} "
                     f"(is the hook installed? python3 heartbeat/install.py)")
        return 0


# ---------------------------------------------------------------- ls

def spend_cell(s: dict, usd: Callable) -> str:
    """Estimated spend, the role's cap if it has one, and OVER CAP past it (warn only, GOV-0008)."""
    cell = usd(s.get("cost"))
    if s.get("cap") is not None:
        cell += f" / {usd(s['cap'])}" + (" OVER CAP" if s.get("over_cap") else "")
    return cell


def process_cell(e: Started, local_state: Callable[[Started], str]) -> str:
    return local_state(e) + (", by watch" if e.by == "watch" else "")


def ls_rows(model: dict, started: list[Started], local_state: Callable[[Started], str],
            now: dt.datetime, ago: Callable, usd: Callable = lambda x: "-" if x is None else f"${x:,.2f}"
            ) -> list[list[str]]:
    """One row per live heartbeat session, plus launcher sessions with no heartbeat yet.

    model is dashboard/generate.py's build() output, so status, current issue and last
    activity are read exactly as the dashboard reads them."""
    by_sid = {e.session_id: e for e in started}
    rows, seen = [], set()
    for s in model["sessions"]:
        if s["status"] == "stopped":
            continue
        e = by_sid.get(s["session_id"])
        seen.add(s["session_id"])
        rows.append([e.name if e else "-", s["role"], s["model"] or "-",
                     f"#{s['issue']}" if s["issue"] else "-",
                     s["status"] + (f" on #{s['gov_question']}" if s["gov_question"] else ""),
                     ago(s["last_ts"], now), spend_cell(s, usd),
                     process_cell(e, local_state) if e else "not launcher", s["session_id"]])
    for e in started:
        if e.session_id not in seen:
            rows.append([e.name, e.role, e.model, "-", "no heartbeat yet", "-", "-",
                         process_cell(e, local_state), e.session_id])
    return rows


def table(header: list[str], rows: list[list[str]]) -> str:
    widths = [max(len(r[i]) for r in [header] + rows) for i in range(len(header))]
    return "\n".join("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in [header] + rows)


def dashboard():
    sys.path.insert(0, str(ROOT / "dashboard"))
    import generate   # the dashboard's reader, not a second parser
    return generate


def snapshot(repo: str, idle_minutes: int, now: dt.datetime) -> tuple[dict, dict]:
    """The dashboard's raw GitHub data and the model it builds from it. Raises RuntimeError."""
    g = dashboard()
    try:
        data = g.fetch(repo, now, days=1)
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        raise RuntimeError(str(e)) from None
    return data, g.build(data, now, dt.timedelta(minutes=idle_minutes), caps=g.load_caps())


def heartbeat(repo: str, idle_minutes: int, now: dt.datetime) -> dict:
    """Live heartbeat state, exactly as the dashboard builds it. Raises RuntimeError."""
    return snapshot(repo, idle_minutes, now)[1]


def ls(launcher: Launcher, repo: str, idle_minutes: int) -> int:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    model = heartbeat(repo, idle_minutes, now)
    g = dashboard()
    rows = ls_rows(model, launcher.live(), launcher.state, now, g.ago, g.spend.usd)
    if not rows:
        launcher.out("no live sessions")
    else:
        launcher.out(table(["NAME", "ROLE", "MODEL", "ISSUE", "STATUS", "LAST", "SPEND (EST.)", "PROCESS",
                            "SESSION"], rows))
    for wt in launcher.kept:
        launcher.out(f"worktree kept: {wt} (uncommitted or unpushed work)")
    return 0


REVIEW_IN_ACTIONS = ("swarm watch leaves [review] to the GitHub Actions reviewer "
                     "(review_in_actions = true in swarm.toml, GOV-0019): the local fallback for "
                     "reviews is off. Set it to false to bring it back.")


def review_in_actions(path: Path | str) -> bool:
    """swarm.toml's [watch] review_in_actions (#216), or False if it can't be read: inbox
    still lists what needs the owner when swarm.toml is broken."""
    try:
        limits = manifest.load_watch(path)
    except manifest.ManifestError:
        return False
    return bool(limits and limits.review_in_actions)


def inbox(launcher: Launcher, repo: str, idle_minutes: int,
          manifest_path: Path | str = manifest.DEFAULT_PATH) -> int:
    """The dashboard's "Needs you" list, from the same function (generate.needs_you)."""
    g = dashboard()
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    items = g.needs_you(heartbeat(repo, idle_minutes, now))
    import watch
    launcher.out(inbox_text(items, now, g, watch.waiting(launcher), watch.runs(launcher),
                            review_in_actions(manifest_path)))
    return 0


def inbox_text(items: list[dict], now: dt.datetime, g, held: tuple | None = None,
               runs: list[dict] | None = None, review_in_actions: bool = False) -> str:
    """The needs-you list, then a line if swarm watch leaves [review] to Actions (#216),
    then runs `swarm watch` started that ended at cap (#149), then any triggers it is
    holding or skipping (#90), then each recorded run's cost (#149).

    held is watch.waiting(): (when swarm watch last checked, its waiting triggers); runs
    is watch.runs(). Both come from local state, not GitHub, so the dashboard (built and
    published by a GitHub Action) doesn't show them, and the costs never leave this machine
    (GOV-0002, GOV-0003, GOV-0004)."""
    import watch
    checked, waiting = held or (None, [])
    capped, recent = watch.runs_text(runs or [], now, g.ago) if runs else ([], [])
    out = [f"{n}. {g.needs_line(i, now)}\n   {i['url']}" for n, i in enumerate(items, 1)]
    if not items and not waiting and not capped:
        out.append(g.NEEDS_EMPTY)
    if review_in_actions:
        out.append(f"\n{REVIEW_IN_ACTIONS}")
    if capped:
        out.append("\nswarm watch runs that ended at cap (restart one if its work should go on):")
        out += capped
    if waiting:
        out.append(f"\nswarm watch is holding (last check {g.ago(checked, now)}):")
        out += [f"- [{w['kind']}] {w['ref']} {w['why']} · {w['reason']}" for w in waiting]
    if recent:
        out.append(f"\nswarm watch runs in the last {watch.RUNS_DAYS} days (cost is Claude Code's local estimate):")
        out += recent
    return "\n".join(out).lstrip("\n")


def cost(launcher: Launcher, repo: str, get_prs: Callable | None = None) -> int:
    """`swarm cost` (#176): the runs in watch.json, costed per PR. Only prints: no cost
    goes to GitHub or the repo (GOV-0002, GOV-0003, GOV-0004, GOV-0014)."""
    import watch
    runs = watch.runs(launcher)
    prs = (get_prs or watch.gh_prs)(repo) if runs else []
    launcher.out(watch.cost_text(runs, prs))
    return 0


def status(launcher: Launcher, manifest_path: Path | str = manifest.DEFAULT_PATH) -> int:
    """`swarm status` (#457): what swarm watch is running, holding, skipping and has seen
    fail, with cost, at once. Local files only: no GitHub call, so it works offline. It
    reads sessions without touching them (Launcher.running(), not live())."""
    import watch
    try:
        limits = manifest.load_watch(manifest_path)
    except manifest.ManifestError:
        limits = None
    interval = limits.interval_minutes if limits else watch.DEFAULT_INTERVAL
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    launcher.out(watch.status_text(watch.load_state(launcher), launcher.running(), now,
                                   holder=watch.lock_holder(launcher), interval=interval,
                                   cost_of=lambda sid: watch.spool_cost(launcher.home, sid),
                                   ago=dashboard().ago))
    return 0


# ---------------------------------------------------------------- launch (L3)

JURISDICTIONS = ROOT / "governance" / "jurisdictions.yml"
OWNER_RE = re.compile(r'^\s*owner:\s*"?@([A-Za-z0-9-]+)"?\s*$', re.M)


def owner_login(path: Path = JURISDICTIONS) -> str:
    """humans.owner from jurisdictions.yml: the first `owner: "@login"` line."""
    m = OWNER_RE.search(path.read_text())
    if not m:
        raise RuntimeError(f"can't find the owner's login in {path}")
    return m.group(1)


def label_event(events: list[dict], name: str) -> dict | None:
    """The most recent `labeled` event for label `name` (GOV-0006 counts only that one)."""
    labeled = [e for e in events if e.get("event") == "labeled"
               and (e.get("label") or {}).get("name") == name]
    return labeled[-1] if labeled else None


def issue_refusals(n: int, issue: dict | None, events: list[dict], owner: str,
                   label: str = "ready") -> list[str]:
    """Reasons not to start a session on issue n. --force overrides none of these.

    `swarm launch` always checks `ready`. `swarm watch` checks `gov:ruled` instead when it
    starts docs on a question that needs a record (GOV-0007)."""
    if issue is None:
        return [f"#{n} doesn't exist"]
    if "pull_request" in issue:
        return [f"#{n} is a pull request, not an issue"]
    if issue.get("state") != "open":
        return [f"#{n} is closed"]
    labels = {lb.get("name") for lb in issue.get("labels") or []}
    if label not in labels:
        return [f"#{n} isn't labelled `{label}`; the launcher starts sessions only on `{label}` "
                f"issues (per GOV-0006)"]
    e = label_event(events, label)
    actor = (e.get("actor") or {}).get("login") if e else None
    if actor != owner:
        return [f"#{n}'s `{label}` label was added by {actor or 'nobody we can see'}, not @{owner}, "
                f"so it doesn't count (per GOV-0006)"]
    return []


def holders(n: int, model: dict, started: list[Started], role: str | None = None) -> list[str]:
    """Live sessions already on issue n: heartbeat sessions whose current issue is n, plus
    launcher sessions started on n that have no heartbeat yet. With role, only that role's
    (a call-in waits only for its own role, #520)."""
    names = {e.session_id: e.name for e in started}
    seen = {s["session_id"] for s in model["sessions"]}
    out = [f"{names.get(s['session_id'], s['role'])} ({s['status']}, session {s['session_id']})"
           for s in model["sessions"] if s["status"] != "stopped" and s["issue"] == n
           and role in (None, s["role"])]
    out += [f"{e.name} (starting, session {e.session_id})"
            for e in started if e.issue == n and e.session_id not in seen and role in (None, e.role)]
    return out


def launch_name(role: str, n: int, taken: set[str], pr: int | None = None) -> str:
    base = f"{role}-pr-{pr}" if pr else f"{role}-issue-{n}"
    name, k = base, 2
    while name in taken:
        name, k = f"{base}-{k}", k + 1
    return name


def gh_issue(repo: str, n: int) -> tuple[dict | None, list[dict]]:
    """The issue and its events, or (None, []) if there is no such issue."""
    g = dashboard()
    try:
        issue = g.gh_json("api", f"repos/{repo}/issues/{n}")
    except RuntimeError as e:
        if "Not Found" in str(e) or "404" in str(e):
            return None, []
        raise
    return issue, g.gh_items(f"repos/{repo}/issues/{n}/events?per_page=100")


def launch(launcher: Launcher, role: str, n: int, model: str, *, repo: str, force: bool = False,
           dry_run: bool = False, idle_minutes: int = 15, pr: int | None = None,
           get_issue: Callable = gh_issue, get_heartbeat: Callable = heartbeat,
           owner: Callable[[], str] = owner_login) -> int:
    issue, events = get_issue(repo, n)
    refused = issue_refusals(n, issue, events, owner())
    if refused:
        launcher.out(f"swarm launch: refused: {refused[0]}")
        return 1
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    live = launcher.live()
    taken = holders(n, get_heartbeat(repo, idle_minutes, now), live)
    if taken and not force:
        launcher.out(f"swarm launch: refused: #{n} already has a live session: {'; '.join(taken)}. "
                     f"Stop it (swarm stop <name>) or pass --force")
        return 1
    if taken:
        launcher.out(f"--force: starting another session on #{n} alongside {'; '.join(taken)}")
    entry = Started(name=launch_name(role, n, {e.name for e in live}, pr), role=role, model=model,
                    session_id=str(uuid.uuid4()), started=launcher.clock(), issue=n, pr=pr)
    return 0 if launcher.start(entry, live, dry_run) else 1


def model_for(role: str, given: str | None, path: str) -> str:
    """--model if given, else the manifest's model for the role. Raises ManifestError/LookupError."""
    if given:
        return given
    for s in manifest.load(path):
        if s.role == role:
            return s.model
    raise LookupError(f"{role} isn't in {path}; pass --model")


# ---------------------------------------------------------------- CLI

def main(argv: list[str], launcher: Launcher | None = None) -> int:
    ap = argparse.ArgumentParser(prog="swarm", description="Start, list and stop the swarm in swarm.toml.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_up = sub.add_parser("up", help="start every manifest session that isn't running")
    p_up.add_argument("--dry-run", action="store_true", help="print what would start; start nothing")
    p_up.add_argument("--manifest", default=str(manifest.DEFAULT_PATH), help="default: swarm.toml")
    p_ls = sub.add_parser("ls", help="list live sessions from heartbeat data")
    p_ls.add_argument("--repo", help="owner/name (default: this checkout's origin)")
    p_ls.add_argument("--idle-minutes", type=int, default=15)
    p_stop = sub.add_parser("stop", help="end one session the launcher started")
    p_stop.add_argument("session", help="its name (builder-1) or session id")
    p_inbox = sub.add_parser("inbox", help="what's waiting on the owner, most urgent first")
    p_inbox.add_argument("--repo", help="owner/name (default: this checkout's origin)")
    p_inbox.add_argument("--idle-minutes", type=int, default=15)
    p_inbox.add_argument("--manifest", default=str(manifest.DEFAULT_PATH), help="default: swarm.toml")
    p_cost = sub.add_parser("cost", help="cost per PR of the runs swarm watch recorded (local only)")
    p_cost.add_argument("--repo", help="owner/name (default: this checkout's origin)")
    p_status = sub.add_parser("status", help="swarm watch's state with cost, from local files only")
    p_status.add_argument("--manifest", default=str(manifest.DEFAULT_PATH), help="default: swarm.toml")
    p_launch = sub.add_parser("launch", help="start one session on a given issue")
    p_launch.add_argument("role")
    p_launch.add_argument("--issue", type=int, required=True, help="the issue to work on")
    p_launch.add_argument("--pr", type=int,
                          help="respond to requested changes on this PR, which closes --issue (GOV-0011)")
    p_launch.add_argument("--model", help="default: the manifest's model for the role")
    p_launch.add_argument("--force", action="store_true",
                          help="start even if a live session is already on the issue")
    p_launch.add_argument("--dry-run", action="store_true", help="check and print; start nothing")
    p_launch.add_argument("--manifest", default=str(manifest.DEFAULT_PATH), help="default: swarm.toml")
    p_launch.add_argument("--repo", help="owner/name (default: this checkout's origin)")
    p_launch.add_argument("--idle-minutes", type=int, default=15)
    p_watch = sub.add_parser("watch", help="start sessions on triggers, within swarm.toml's [watch] limits")
    p_watch.add_argument("--dry-run", action="store_true", help="print triggers; start nothing")
    p_watch.add_argument("--interval", type=float, default=None,
                         help="--dry-run only: minutes between checks (default: swarm.toml's)")
    p_watch.add_argument("--manifest", default=str(manifest.DEFAULT_PATH), help="default: swarm.toml")
    p_watch.add_argument("--repo", help="owner/name (default: this checkout's origin)")
    p_watch.add_argument("--idle-minutes", type=int, default=15)
    args = ap.parse_args(argv)

    launcher = launcher or Launcher(home())
    if args.cmd == "watch" and not args.dry_run and args.interval is not None:
        launcher.out("swarm watch: --interval works only with --dry-run; the interval for real "
                     "starts is interval_minutes in swarm.toml's [watch] table (GOV-0010)")
        return 2
    repo = None
    if args.cmd in ("ls", "launch", "inbox", "watch", "cost"):
        repo = args.repo or dashboard().default_repo()
        if not repo:
            launcher.out(f"swarm {args.cmd}: can't tell the repo; pass --repo owner/name")
            return 2
    try:
        if args.cmd == "launch":
            if "/" in args.role or not (launcher.root / "roles" / f"{args.role}.md").is_file():
                launcher.out(f"swarm launch: unknown role '{args.role}' (no roles/{args.role}.md)")
                return 1
            try:
                model = model_for(args.role, args.model, args.manifest)
            except (manifest.ManifestError, LookupError) as e:
                launcher.out(f"swarm launch: {e}")
                return 1
            return launch(launcher, args.role, args.issue, model, repo=repo, force=args.force,
                          dry_run=args.dry_run, idle_minutes=args.idle_minutes, pr=args.pr)
        if args.cmd == "up":
            try:
                sessions = manifest.load(args.manifest)
            except manifest.ManifestError as e:
                launcher.out(f"swarm up: {e}")
                return 1
            return launcher.up(sessions, dry_run=args.dry_run)
        if args.cmd == "ls":
            return ls(launcher, repo, args.idle_minutes)
        if args.cmd == "inbox":
            return inbox(launcher, repo, args.idle_minutes, args.manifest)
        if args.cmd == "cost":
            return cost(launcher, repo)
        if args.cmd == "status":
            return status(launcher, args.manifest)
        if args.cmd == "watch":
            import watch
            try:
                limits = manifest.load_watch(args.manifest)
            except manifest.ManifestError as e:
                launcher.out(f"swarm watch: {e}")
                return 1
            if limits is None and not args.dry_run:
                launcher.out(f"swarm watch: refused: {args.manifest} has no [watch] table, so there "
                             f"are no limits to start sessions within (GOV-0010); use --dry-run")
                return 1
            if limits and limits.max_turns is None and not args.dry_run:
                launcher.out(f"swarm watch: refused: {args.manifest}'s [watch] table has no max_turns, "
                             f"so runs would have no turn ceiling (GOV-0012); use --dry-run")
                return 1
            w = watch.Watch(launcher, repo, owner_login(), watch.roles_in(launcher.root),
                            idle_minutes=args.idle_minutes, dry_run=args.dry_run,
                            manifest_path=Path(args.manifest), roles_from=launcher.root)
            interval = args.interval or (limits.interval_minutes if limits else watch.DEFAULT_INTERVAL)
            return w.run(interval)
        return launcher.stop(args.session)
    except RuntimeError as e:   # GitHub unreachable, or an unreadable state file
        launcher.out(f"swarm {args.cmd}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
