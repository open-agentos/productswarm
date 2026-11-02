#!/usr/bin/env python3
"""swarm: start, list and stop the sessions in swarm.toml (v1 launcher, GOV-0005 item L2).

    launcher/swarm up [--dry-run]   start every manifest session that isn't already running
    launcher/swarm ls               list live sessions from the heartbeat tracking issues
    launcher/swarm stop <session>   end one session the launcher started (name or session id)

Each session runs `ops/swarm-session <role> --model <model> --session-id <uuid> <opener>`,
unchanged, in a new Terminal window: the owner's answer on #43. That runtime is kept
behind one function, open_terminal(). Choosing the session id up front is what ties a
window to its heartbeat tracking issue: the hook uses Claude Code's session id.

What the launcher started is recorded locally, never on GitHub:
    ~/.productswarm/launcher/sessions.json   name, role, model, session id, start time
    ~/.productswarm/launcher/<id>.pid        written by the window's shell before exec
(PRODUCTSWARM_HOME moves ~/.productswarm, as for the heartbeat.)

`stop` sends SIGTERM. Claude Code then runs its SessionEnd hook, so the heartbeat
records `stopped` with no change to the hook (GOV-0002 to GOV-0004).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shlex
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import manifest  # noqa: E402

SWARM_SESSION = ROOT / "ops" / "swarm-session"
HOOK_SETTINGS = ROOT / ".claude" / "settings.local.json"
START_GRACE = 60      # seconds a session may take to write its pid file before it counts as failed
STOP_WAIT = 20        # seconds to wait for a session to exit after SIGTERM


def opener(role: str) -> str:
    """The prompt ops/swarm-session uses when given no args; given args, it passes them on."""
    return f"You are the {role} for productswarm. Read CLAUDE.md, PRODUCT.md and roles/{role}.md, then begin."


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


# ---------------------------------------------------------------- local state

@dataclass
class Started:
    """A session the launcher started."""
    name: str               # e.g. builder-1
    role: str
    model: str
    session_id: str
    started: float          # unix time the window was opened

    @classmethod
    def from_dict(cls, d: dict) -> "Started":
        return cls(**{k: d[k] for k in ("name", "role", "model", "session_id", "started")})


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

    @property
    def dir(self) -> Path:
        return self.home / "launcher"

    @property
    def state_file(self) -> Path:
        return self.dir / "sessions.json"

    def pid_file(self, sid: str) -> Path:
        return self.dir / f"{sid}.pid"

    def load(self) -> list[Started]:
        try:
            data = json.loads(self.state_file.read_text())
        except FileNotFoundError:
            return []
        except ValueError as e:
            raise RuntimeError(f"{self.state_file} is not valid JSON: {e}") from None
        return [Started.from_dict(d) for d in data]

    def save(self, entries: list[Started]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps([e.__dict__ for e in entries], indent=1) + "\n")
        tmp.replace(self.state_file)

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

    def live(self) -> list[Started]:
        """Entries still running or starting. Exited ones are dropped from the state file."""
        entries = self.load()
        live = [e for e in entries if self.state(e) != "exited"]
        if len(live) != len(entries):
            for e in entries:
                if e not in live:
                    self.pid_file(e.session_id).unlink(missing_ok=True)
            self.save(live)
        return live

    # ------------------------------------------------------------ up

    def command(self, s: Started) -> str:
        """The shell command a window runs: record the pid, then exec swarm-session unchanged.

        Run through /bin/bash so `$$` means the same whatever the owner's login shell is;
        both exec's keep that pid, so it ends up being claude's."""
        inner = " ".join([
            "cd", shlex.quote(str(self.root)), "&&",
            "echo $$ >|", shlex.quote(str(self.pid_file(s.session_id))), "&&",
            "exec", shlex.quote(str(self.root / "ops" / "swarm-session")), shlex.quote(s.role),
            "--model", shlex.quote(s.model), "--session-id", s.session_id, shlex.quote(opener(s.role)),
        ])
        return "exec /bin/bash -c " + shlex.quote(inner)

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
        if not dry_run:
            self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        failed = 0
        for s in todo:
            entry = Started(name=s.name, role=s.role, model=s.model,
                            session_id=str(uuid.uuid4()), started=self.clock())
            if dry_run:
                self.out(f"would start: {s.name}  {s.model}\n  {self.command(entry)}")
                continue
            try:
                self.run(self.command(entry))
            except (RuntimeError, OSError, subprocess.SubprocessError) as e:
                self.out(f"failed to start {s.name}: {e}")
                failed += 1
                continue
            live.append(entry)
            self.save(live)   # after each start, so a later failure doesn't lose it
            self.out(f"started: {s.name}  {s.model}  {entry.session_id}")
        return 1 if failed else 0

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
        self.save([e for e in live if e is not s])
        if self.heartbeat_stopped(s.session_id):
            self.out(f"stopped: {s.name}; the heartbeat recorded `stopped`")
        else:
            self.out(f"stopped: {s.name}, but the heartbeat has no `stopped` for {s.session_id} "
                     f"(is the hook installed? python3 heartbeat/install.py)")
        return 0


# ---------------------------------------------------------------- ls

def ls_rows(model: dict, started: list[Started], local_state: Callable[[Started], str],
            now: dt.datetime, ago: Callable) -> list[list[str]]:
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
                     ago(s["last_ts"], now), local_state(e) if e else "not launcher",
                     s["session_id"]])
    for e in started:
        if e.session_id not in seen:
            rows.append([e.name, e.role, e.model, "-", "no heartbeat yet", "-", local_state(e),
                         e.session_id])
    return rows


def table(header: list[str], rows: list[list[str]]) -> str:
    widths = [max(len(r[i]) for r in [header] + rows) for i in range(len(header))]
    return "\n".join("  ".join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in [header] + rows)


def ls(launcher: Launcher, repo: str | None, idle_minutes: int) -> int:
    sys.path.insert(0, str(ROOT / "dashboard"))
    import generate as g   # the dashboard's reader, not a second parser

    repo = repo or g.default_repo()
    if not repo:
        launcher.out("swarm ls: can't tell the repo; pass --repo owner/name")
        return 2
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    try:
        data = g.fetch(repo, now, days=1)
    except (RuntimeError, OSError, subprocess.SubprocessError, ValueError) as e:
        launcher.out(f"swarm ls: {e}")
        return 1
    model = g.build(data, now, dt.timedelta(minutes=idle_minutes))
    rows = ls_rows(model, launcher.live(), launcher.state, now, g.ago)
    if not rows:
        launcher.out("no live sessions")
        return 0
    launcher.out(table(["NAME", "ROLE", "MODEL", "ISSUE", "STATUS", "LAST", "PROCESS", "SESSION"], rows))
    return 0


# ---------------------------------------------------------------- CLI

def hook_installed() -> bool:
    try:
        return "heartbeat/hook.py" in HOOK_SETTINGS.read_text()
    except OSError:
        return False


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
    args = ap.parse_args(argv)

    launcher = launcher or Launcher(home())
    try:
        if args.cmd == "up":
            try:
                sessions = manifest.load(args.manifest)
            except manifest.ManifestError as e:
                launcher.out(f"swarm up: {e}")
                return 1
            if not hook_installed():
                launcher.out("warning: the heartbeat hook isn't installed, so `swarm ls` won't see "
                             "these sessions (python3 heartbeat/install.py)")
            return launcher.up(sessions, dry_run=args.dry_run)
        if args.cmd == "ls":
            return ls(launcher, args.repo, args.idle_minutes)
        return launcher.stop(args.session)
    except RuntimeError as e:   # an unreadable state file
        launcher.out(f"swarm {args.cmd}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
