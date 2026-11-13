#!/usr/bin/env python3
"""swarm: start, list and stop the sessions in swarm.toml (v1 launcher, GOV-0005 item L2).

    launcher/swarm up [--dry-run]   start every manifest session that isn't already running
    launcher/swarm ls [--all]       list live sessions from the heartbeat tracking issues;
                                    --all adds sessions that never acted (#454)
    launcher/swarm stop <session>   end one session the launcher started (name or session id)
    launcher/swarm launch <role> --issue N [--pr M] [--model M] [--force] [--dry-run]
                                    start one session on issue N (L3); with --pr, it
                                    responds to requested changes on PR M (GOV-0011)
    launcher/swarm inbox            what's waiting on the owner, most urgent first (L5)
    launcher/swarm cost             cost per PR of the runs swarm watch recorded (#176; local only)
    launcher/swarm status           swarm watch's state with cost, from local files only (#457)
    launcher/swarm merges [--last]  this UTC week's merges into main by the merger and by the
                                    owner, and each revert and whether it was reviewed (#710);
                                    --last for the week before
    launcher/swarm daily            the last 10 working days' daily reports and who started
                                    each, and the latest one [daily] started (#707, GOV-0040)
    launcher/swarm acts [--day D] [--json]
                                    the owner's acts on each working day of the last two
                                    weeks, or on day D, with count and kind, or "not counted"
                                    for a day not yet read back from GitHub; counted, with no
                                    limit (#771, #844, GOV-0040; acts.py)
    launcher/swarm watch [--dry-run] [--serve] [--container IMAGE]
                                    the v2 wake-up loop: start sessions on triggers, within
                                    the [watch] limits in swarm.toml (#90, GOV-0010; watch.py)
    launcher/swarm webhooks         the GitHub webhook receiver on the engine host (#658)
    launcher/swarm desk             the live, read-only Desk on the engine host, rebuilt on
                                    each webhook nudge (#664; desk.py)
    launcher/swarm backup [--out P] a consistent copy of swarm.db (#659; statedb.py)
    launcher/swarm specs pull <goal> [--dry-run]
                                    open a sub-issue under the Goal for each Ready feature of
                                    the initiative its `Spec source:` line links, from the
                                    [specs] backend in swarm.toml (#955; specs/sync.py)
    launcher/swarm specs push <goal> [--what-shipped FEAT-n=TEXT ...] [--dry-run]
                                    write each linked feature's status, Issue and PR links
                                    and one delivery comment per merged PR back to the
                                    source (#957; specs/push.py)
    launcher/swarm specs diff [<goal>] [--json]
    launcher/swarm specs diff <goal> --adopt FEAT-n | --defer FEAT-n | --ask FEAT-n
                                    specs edited since their snapshot was pulled, under the
                                    Goal or every linked one, and the lead's decision on one
                                    (#956; specs/drift.py)

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
A session on another org repo's issue gets its worktree from that repo's own clone,
~/.productswarm/repos/<owner>/<name>, made on first use and fetched as this checkout is
(#853, #820 stage 2). Its opener names the repo, our CLAUDE.md and role prompt go in as
--append-system-prompt, and the worktree gets git-excluded copies of ops/ and the role
prompt, which ops/swarm-session needs (#912, #820 stage 3, GOV-0039).

What the launcher started is recorded locally, never on GitHub:
    ~/.productswarm/launcher/sessions.json   name, role, model, session id, start time;
                                             every read-change-write holds an flock on
                                             sessions.lock beside it (#272)
    ~/.productswarm/launcher/<id>.pid        written by the window's shell before exec
    ~/.productswarm/launcher/<id>.result.json  a headless run's stdout: ops/swarm-session's
                                             one-line banner, then the JSON result (#147)
    ~/.productswarm/launcher/swarm.db        triggers `swarm watch` acted on or is holding,
                                             how each run it started ended (#149), and the
                                             webhook deliveries (#658); watch.json before #659
    ~/.productswarm/launcher/backups/        `swarm backup`'s copies of swarm.db (#659)
    ~/.productswarm/launcher/desk/           `swarm desk`'s builds and the live symlink (#664)
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
import shutil
import signal
import sqlite3
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
import statedb  # noqa: E402

sys.path.insert(0, str(ROOT / "heartbeat"))
import install  # noqa: E402

SWARM_SESSION = ROOT / "ops" / "swarm-session"
WORKTREES = ".worktrees"   # under the checkout root; gitignored
REPOS = "repos"            # under the launcher home: a clone per other org repo (#853)
REPO_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", re.ASCII)
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
MAX_CANON = 1024      # macOS's tty line limit: a longer line typed into a starting shell is cut (#550)
IMAGE_RE = re.compile(r"^(?:[^\s@]+@)?sha256:[0-9a-f]{64}$")
CONTAINER_HOME = "/home/run"   # HOME inside a run's container: a tmpfs, gone when it ends (#661)
CONTAINER_TOKEN_DIR = "/run/swarm-token"   # where a container run reads its App token (#680)
TOKEN_REFRESH = 300   # seconds between a container run's token refreshes on the host (#680)
STOP_WAIT = 20        # seconds to wait for a session to exit after SIGTERM


def opener(role: str, issue: int | None = None, pr: int | None = None,
           called_by: str | None = None, call_why: str | None = None,
           daily: str | None = None, ask: str | None = None,
           ask_comment: int | None = None, research: str | None = None,
           research_comment: int | None = None, ruling: str | None = None,
           ruling_comment: int | None = None, conflict: bool = False,
           repo: str | None = None, home: str | None = None) -> str:
    """The prompt ops/swarm-session uses when given no args (it passes args on unchanged).

    With an issue, it names it: the heartbeat's `working_on` detection matches
    "issue #N" in a prompt, so the session's current issue is set with no hook change.
    With a PR too, the session responds to requested changes on it (GOV-0011). With only a
    PR, it reviews that PR once (a reviewer run in Actions, #215). With called_by, the
    role was called in to the issue (GOV-0023, #520): the prompt says by whom and why, and
    that it posts one comment. With daily, a [daily] run (GOV-0029, #588): the planner posts
    `daily` ("the daily report", or on Mondays "the daily report and the Monday check-in")
    on the report issue, with its Trouble section built from `swarm trouble --json` (#804).
    With ask, an [ask] run (GOV-0029, #590): the role answers the
    owner's question, from comment ask_comment on the report issue, in one comment there.
    With research, a [research] run (GOV-0029, #591): the analyst writes a brief on the
    question from comment research_comment in research/, as a PR that closes the issue. With
    ruling and a PR, a [ruling] run (#739, the owner's answer on #781): the PR's author role
    applies the owner's comment ruling_comment on an overstep on the PR (#738). With conflict
    and a PR, a [conflict] run (#893): the PR's author role brings the base into its branch.
    With repo, the session works in that other org repo (#912): other_repo_opener(), with
    home, this repo's owner/name, for where governance is."""
    if issue and research:
        # As for an ask: "issue #M" in the question would give the heartbeat two issues.
        safe = ISSUE_WORD_RE.sub(r"#\1", research)
        where = f" (comment {research_comment})" if research_comment else ""
        then = (f"research the question posted on issue #{issue}{where}: \"{safe}\". swarm watch "
                f"started this run from its [research] trigger (GOV-0029). Write the brief in "
                f"research/<slug>.md as roles/{role}.md says, open a PR that closes #{issue}, link it "
                f"in one comment on #{issue}, and stop. If you can't, say why in one comment on "
                f"#{issue}, and stop")
    elif issue and ask:
        # As for a call-in's why: "issue #M" in the question would give the heartbeat two issues.
        safe = ISSUE_WORD_RE.sub(r"#\1", ask)
        where = f" (comment {ask_comment})" if ask_comment else ""
        then = (f"answer the owner's question on issue #{issue}{where}: \"{safe}\". swarm watch started "
                f"this run from its [ask] trigger (GOV-0029). Answer in plain words in one comment "
                f"on #{issue}, and stop")
    elif issue and daily:
        then = (f"write {daily} on issue #{issue}, as roles/{role}.md says. swarm watch started "
                f"this run from its [daily] trigger (GOV-0029). Run launcher/swarm daily first: its "
                f"Goal and Area edits go under Risks (#709). Then run launcher/swarm trouble --json and build the Trouble "
                f"section from it, not by hand (#804). Post on #{issue} and stop")
    elif issue and called_by:
        # "issue #M" in the why would give the heartbeat two issues and so none: say "#M".
        safe = ISSUE_WORD_RE.sub(r"#\1", call_why) if call_why else ""
        why = f" because: {safe}" if safe else ""
        then = (f"answer a call-in on issue #{issue}: {called_by} called you in (GOV-0023){why}. "
                f"That call counts as asking you in (GOVERNANCE.md section 8). Read the issue, post "
                f"one comment on it with your contribution, and stop")
    elif issue and pr and ruling is not None:
        where = f" (comment {ruling_comment})" if ruling_comment else ""
        then = (f"apply the owner's ruling on the overstep on PR #{pr}, which closes issue #{issue}. "
                f"swarm watch started this run from its [ruling] trigger (#739): the owner commented "
                f"on the PR after the reviewer's Authority: fail review{where}: \"{ruling}\". Read the "
                f"review and that comment in full, then push a fix that follows the ruling to the PR's "
                f"branch, or reply on the PR saying why you can't, as roles/{role}.md says, and stop")
    elif issue and pr and conflict:
        then = (f"resolve the conflict between PR #{pr}, which closes issue #{issue}, and its base. "
                f"swarm watch started this run from its [conflict] trigger (#893): GitHub reports the "
                f"PR as conflicting, so it can't merge. Merge or rebase the base into the PR's branch, "
                f"resolve the conflicts inside the PR's issue, run the tests and push. If you can't "
                f"resolve them, say why in one comment on the PR, and stop")
    elif issue and pr:
        then = f"respond to the requested changes on PR #{pr}, which closes issue #{issue}"
    elif pr:     # a reviewer on one PR: a run in GitHub Actions (#215)
        then = f"review PR #{pr} only, in one pass, and stop"
    else:
        then = f"work on issue #{issue}" if issue else "begin"
    if repo:
        return other_repo_opener(role, repo, then, home)
    return f"You are the {role} for productswarm. Read CLAUDE.md, PRODUCT.md and roles/{role}.md, then {then}."


def other_repo_instructions(role: str, repo: str, home: str | None = None) -> str:
    """The header of a session's instructions file in another org repo (#912, GOV-0039)."""
    there = home or "productswarm's repo"
    return (f"# productswarm's rules for this session\n\nYou are productswarm's {role}, working in "
            f"{repo}. Below are productswarm's CLAUDE.md and roles/{role}.md, from {there}'s "
            f"origin/main. They are your working rules. {repo}'s own CLAUDE.md, if it has one, "
            f"still applies to its code conventions; where it disagrees with these rules, these "
            f"win (GOV-0039). Paths they name (GOVERNANCE.md, governance/, PRODUCT.md, roles/, "
            f"launcher/) are in {there}, not {repo}: read them there with gh. The ops/ and "
            f"roles/{role}.md in your worktree are the launcher's copies for ops/swarm-session, "
            f"kept out of git: never commit or edit them.")


def other_repo_opener(role: str, repo: str, then: str, home: str | None = None) -> str:
    """The opener for a session in another org repo's worktree (#912, GOV-0036 stage 3). It
    names the repo the session works in, and home, this repo's owner/name. Our CLAUDE.md and
    roles/<role>.md come in the appended system prompt (other_repo_instructions(), GOV-0039),
    so it doesn't tell the session to read files that aren't in its repo. A bare #N in
    `then` stays bare: in this run it means an issue or PR in repo, and the heartbeat, which
    tracks the repo its worktree is cut from, reads "issue #N" from the prompt as it does here."""
    there = home or "productswarm's repo"
    return (f"You are the {role} for productswarm, working in {repo}, another repo of the org, not "
            f"productswarm's own. Your working rules and role prompt, productswarm's CLAUDE.md and "
            f"roles/{role}.md, are in your system prompt; where {repo}'s own CLAUDE.md disagrees, "
            f"they win (GOV-0039). In this run a bare #N means an issue or PR in {repo}: pass "
            f"--repo {repo} to gh for it. GOVERNANCE.md, governance/ and gov:questions stay in "
            f"{there}, which you reach with gh. Now {then}.")


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


def run_detached(command: str) -> None:
    """Run a shell command in the background, in its own session: the engine host's
    counterpart of open_terminal() (#661), for runs in containers. The outer shell exits
    at once, so its child is reparented and a long-lived watcher leaves no zombies; the
    child's stderr goes to the watcher's log."""
    subprocess.run(["/bin/sh", "-c", f"( {command} ) </dev/null >/dev/null &"],
                   start_new_session=True, check=True, timeout=30)


def pinned_image(ref: str) -> bool:
    """A container image named by its content digest (#661): `name@sha256:<hex>`, or a
    local image id `sha256:<hex>`. A tag can move under a running watcher; a digest can't."""
    return bool(IMAGE_RE.match(ref))


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


def run_docker(args: list[str]) -> tuple[int, str]:
    """`docker <args>`: (exit code, stdout and stderr). Used only to check a container
    run's clone from inside a container (#661), never to start a run."""
    try:
        r = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)
    return r.returncode, (r.stdout + r.stderr).strip()


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
    daily: str | None = None          # a [daily] run (GOV-0029, #588): what it writes
    ask: str | None = None            # an [ask] run (GOV-0029, #590): the owner's question
    ask_comment: int | None = None    # and the id of the comment that asked it
    research: str | None = None       # a [research] run (GOV-0029, #591): the question
    research_comment: int | None = None   # and the id of the comment that asked it
    ruling: str | None = None         # a [ruling] run (#739): the owner's comment on the overstep
    ruling_comment: int | None = None     # and that comment's id
    conflict: bool = False            # a [conflict] run (#893): bring the base into the PR's branch
    repo: str | None = None           # owner/name of the issue's repo; None: this repo (#829)

    @classmethod
    def from_dict(cls, d: dict) -> "Started":
        return cls(**{k: d[k] for k in ("name", "role", "model", "session_id", "started")},
                   issue=d.get("issue"), by=d.get("by"), pr=d.get("pr"),
                   budget_usd=d.get("budget_usd"), max_turns=d.get("max_turns"),
                   called_by=d.get("called_by"), call_why=d.get("call_why"),
                   daily=d.get("daily"), ask=d.get("ask"), ask_comment=d.get("ask_comment"),
                   research=d.get("research"), research_comment=d.get("research_comment"),
                   ruling=d.get("ruling"), ruling_comment=d.get("ruling_comment"),
                   conflict=bool(d.get("conflict")), repo=d.get("repo"))


def recovered(sid: str, cmd: str, started: float) -> Started:
    """An entry for a running session that sessions.json lost (#272), from its command
    line: `claude --model M --session-id SID [-p] <opener> ...`."""
    model = re.search(r"--model (\S+)", cmd)
    role = re.search(r"You are the (\w+) for productswarm", cmd)
    issue = re.search(r"issue #(\d+)", cmd)
    pr = re.search(r"PR #(\d+)", cmd)
    repo = re.search(r"for productswarm, working in ([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+),", cmd)   # #912
    r = role.group(1) if role else "unknown"
    return Started(name=f"{r}-recovered-{sid[:8]}", role=r, model=model.group(1) if model else "unknown",
                   session_id=sid, started=started, issue=int(issue.group(1)) if issue else None,
                   pr=int(pr.group(1)) if pr else None, by="watch" if " -p " in cmd else None,
                   repo=repo.group(1) if repo else None)


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
    docker: Callable[[list[str]], tuple[int, str]] = run_docker
    kept: list[Path] = field(default_factory=list)   # exited sessions' worktrees with work in them
    fetched: bool = False
    fetched_repos: set[str] = field(default_factory=set)   # other repos' clones fetched (#853)
    home_name: str | None = None      # this repo's owner/name, for other repos' sessions (#912)
    hook: str | None = None         # the pinned hook path, once refreshed in this run
    claude_dir: Path = field(default_factory=lambda: Path(
        os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude").expanduser())   # transcripts (#550)
    container: str | None = None    # a pinned image: runs swarm watch starts go in containers (#661)

    def use_container(self, image: str) -> None:
        """Start each run swarm watch starts in its own container from image (#661), in the
        background rather than in a Terminal window. Their transcripts land in
        the run's own home, run_home(), so transcript() looks there too (#550)."""
        if not pinned_image(image):
            raise ValueError(f"--container takes an image pinned by digest (name@sha256:<64 hex> "
                             f"or sha256:<64 hex>), not '{image}'")
        self.container, self.run = image, run_detached

    def in_container(self, s: Started) -> bool:
        """Whether s runs in a container: only runs swarm watch starts, under --container."""
        return bool(self.container) and s.by == "watch"

    def run_home(self, sid: str) -> Path:
        """A container run's own PRODUCTSWARM_HOME (#661): its heartbeat state and spool,
        its Stop hook's count and log, and its transcripts. The only part of the host's
        home it can write, and it can't see any other run's."""
        return self.home / "runs" / sid

    def token_dir(self, sid: str) -> Path:
        """A container run's token directory (#680, per the owner on #749): the host
        rewrites the role App's token there every TOKEN_REFRESH seconds while the run
        lives, and the container sees it read-only. Outside run_home(), which the run can
        write: it could plant a symlink there for the host to write the token through."""
        return self.dir / "tokens" / sid

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

    def instructions_file(self, sid: str) -> Path:
        """A session in another org repo: our CLAUDE.md and its role prompt, from origin/main,
        which its command passes as --append-system-prompt (#912, GOV-0039)."""
        return self.dir / f"{sid}.instructions.md"

    def window_file(self, sid: str) -> Path:
        """The script a session's window runs: command(), kept out of the typed line (#550)."""
        return self.dir / f"{sid}.window.sh"

    def typed(self, s: Started) -> str:
        """The line typed into a session's new window: run its window_file().

        Terminal types the command into a shell that may still be starting, and a tty in
        that state keeps only the first MAX_CANON bytes of a line. command() is longer, and
        cut there it left the shell waiting on an open quote: no pid file, no result (#550).
        This line is short. The session id after the path is unused by the script; it puts
        the id in the process's command line, as state() needs, until the script exec's."""
        return f"exec /bin/sh {shlex.quote(str(self.window_file(s.session_id)))} --session-id {s.session_id}"

    def transcript(self, sid: str) -> Path | None:
        """Claude Code's transcript of session sid, if it wrote one (#550)."""
        found = (sorted((self.run_home(sid) / "claude" / "projects").glob(f"*/{sid}.jsonl"))
                 or sorted((self.claude_dir / "projects").glob(f"*/{sid}.jsonl")))
        return found[0] if found else None

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
                    self.window_file(e.session_id).unlink(missing_ok=True)
                    (self.dir / f"{e.session_id}.stop.json").unlink(missing_ok=True)   # stophook.py
                    shutil.rmtree(self.token_dir(e.session_id), ignore_errors=True)   # #680
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

    def refetch(self) -> None:
        """Fetch origin/main now, and refresh the pinned hook copy on the next start: a
        long-lived `swarm watch` calls this every check (#550), not once per process.
        Other repos' clones are fetched again on their next start too (#853)."""
        self.fetched, self.hook = False, None
        self.fetched_repos.clear()
        self.fetch_main()

    # ------------------------------------------------------------ other repos' clones (#853)

    def repo_clone(self, repo: str) -> Path:
        """Where the launcher keeps its clone of another org repo, owner/name: under its
        home, in lower case, since GitHub repo names ignore case. Raises ValueError for a
        name that isn't owner/name or would leave the clones' directory (`..`)."""
        parts = repo.split("/")
        if not REPO_RE.fullmatch(repo) or any(p in (".", "..") for p in parts):
            raise ValueError(f"'{repo}' isn't an owner/name repo")
        return self.home / REPOS / parts[0].lower() / parts[1].lower()

    def home_repo(self) -> str | None:
        """This checkout's owner/name (#912): home_name, which `swarm launch` and `swarm watch`
        set from their --repo, else from its origin, or None if git can't say."""
        if self.home_name:
            return self.home_name
        rc, url = self.git(["-C", str(self.root), "remote", "get-url", "origin"])
        m = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?/?$", url.strip()) if rc == 0 else None
        return m[1] if m else None

    def repo_url(self, repo: str) -> str:
        """repo's URL on the same host and scheme as this checkout's origin: its owner/name
        swapped for repo's, so the clone fetches with the credentials this one does."""
        url = self.git_ok("-C", str(self.root), "remote", "get-url", "origin").strip()
        m = re.fullmatch(r"(.*[:/])[^/:]+/[^/]+?(\.git)?/?", url)
        if not m:
            raise RuntimeError(f"can't tell another repo's URL from this checkout's origin ({url})")
        return f"{m[1]}{repo}{m[2] or ''}"

    def fetch_repo(self, repo: str) -> Path:
        """repo's clone, made on first use and fetched once per launcher run or watch check,
        as this checkout is (fetch_main()). The clone has no checkout of its own: sessions'
        worktrees are cut from it at origin/main."""
        d = self.repo_clone(repo)
        if not (d / ".git").is_dir():
            d.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.rmtree(d, ignore_errors=True)   # a clone that failed part-way
            self.git_ok("clone", "-q", "--no-checkout", self.repo_url(repo), str(d))
            self.fetched_repos.add(repo.lower())
        if repo.lower() not in self.fetched_repos:
            self.git_ok("-C", str(d), "fetch", "-q", "origin", "main")
            self.fetched_repos.add(repo.lower())
        return d

    def source(self, s: Started) -> Path:
        """The checkout s's worktree is cut from: this one, or its repo's clone (#853)."""
        return self.fetch_repo(s.repo) if s.repo else self.root

    def owner_of(self, wt: Path) -> Path:
        """The checkout a worktree belongs to, from its `.git` file (gitdir: <checkout>/.git/
        worktrees/<id>): this one or one of the launcher's clones of other repos (#853).
        Anything else is taken to be this checkout's, whose git then refuses to remove it."""
        try:
            gitdir = (wt / ".git").read_text().strip()
        except OSError:
            return self.root
        m = re.fullmatch(r"gitdir: (.+)/\.git/worktrees/[^/]+", gitdir)
        found = Path(m[1]).resolve() if m else None
        if found and found.parent.parent == (self.home / REPOS).resolve() and (found / ".git").is_dir():
            return self.home / REPOS / found.parent.name / found.name
        return self.root

    def prepare(self, s: Started) -> None:
        """Create the session's worktree at origin/main and write its hook settings. A run
        in a container gets a clone instead, and its own home (#661). Both come from the
        session's repo: this checkout, or that repo's clone (#853)."""
        hook = self.hook_path()          # fetches, and refreshes the pinned copy first
        wt = self.worktree(s.session_id)
        src = self.source(s)
        if self.in_container(s):
            self.clone(wt, src)
            self.prepare_run_home(s)
        else:
            self.git_ok("-C", str(src), "worktree", "add", "-q", "--detach", str(wt), "origin/main")
            if s.repo:
                self.add_session_files(s, wt, src)
        if s.repo:
            self.write_instructions(s)
        base = install.read_settings(self.root / ".claude" / "settings.local.json")
        settings = install.with_hooks(base, hook=hook)
        if s.by == "watch":      # loop-started runs keep going until they're done (#148)
            import stophook      # here, not at the top: stophook imports this module
            settings = stophook.with_stop_hook(settings, stophook.script_for(hook))
        install.write_settings(wt / ".claude" / "settings.local.json", settings)

    def runtime(self) -> Path:
        """The pinned copy of this repo at origin/main that hook_path() refreshes (#93)."""
        return self.home / "runtime"

    def write_instructions(self, s: Started) -> None:
        """instructions_file() for a session in another org repo (#912): our CLAUDE.md and
        roles/<role>.md from the pinned copy, which hook_path() has just refreshed to this
        repo's origin/main (GOV-0039), under a header saying they win where that repo's own
        CLAUDE.md disagrees."""
        rt = self.runtime()
        parts = [other_repo_instructions(s.role, s.repo or "", self.home_repo()),
                 (rt / "CLAUDE.md").read_text(), (rt / "roles" / f"{s.role}.md").read_text()]
        self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.instructions_file(s.session_id).write_text("\n\n".join(p.strip() for p in parts) + "\n")

    def add_session_files(self, s: Started, wt: Path, src: Path) -> None:
        """What ops/swarm-session needs in a worktree of another org repo (#912), which it
        doesn't change: it runs from <root>/ops, cd's to <root> and checks <root>/roles/<role>.md
        is there. So the worktree gets a copy of ops/ and of roles/<role>.md from the pinned
        copy (origin/main, as this repo's own sessions run them), listed in the clone's
        info/exclude with the hook settings prepare() writes (this repo's .gitignore covers
        those; that repo's needn't), so `git status` stays clean, tidy() can remove the
        worktree and a `git add -A` leaves them out. A repo that tracks either path is refused: copying
        over its files would change its work."""
        rt = self.runtime()
        mine = ["ops", f"roles/{s.role}.md"]
        clash = [p for p in mine if (wt / p).exists()]
        if clash:
            raise RuntimeError(f"{s.repo} has its own {' and '.join(clash)}, where ops/swarm-session "
                               f"needs ours; a session can't start there (#912)")
        shutil.copytree(rt / "ops", wt / "ops", symlinks=True)
        (wt / "roles").mkdir(exist_ok=True)
        shutil.copy2(rt / "roles" / f"{s.role}.md", wt / "roles" / f"{s.role}.md")
        exclude = src / ".git" / "info" / "exclude"
        have = exclude.read_text().splitlines() if exclude.is_file() else []
        want = [x for x in ("/ops/", f"/roles/{s.role}.md", "/.claude/settings.local.json")
                if x not in have]
        if want:
            exclude.parent.mkdir(parents=True, exist_ok=True)
            with open(exclude, "a") as f:
                f.write("".join(f"{x}\n" for x in want))

    def prepare_line(self, s: Started) -> str:
        """What prepare() will do for s, for --dry-run."""
        wt = self.worktree(s.session_id)
        src = self.repo_clone(s.repo) if s.repo else self.root
        made = (f" (from {s.repo}'s clone, {src}, made on first use)"
                if s.repo and not (src / ".git").is_dir() else "")
        if self.in_container(s):
            return f"git clone --no-hardlinks {src} {wt} (at origin/main; origin set to GitHub){made}"
        if s.repo:
            return (f"git -C {src} worktree add --detach {wt} origin/main{made}; then copy ops/ and "
                    f"roles/{s.role}.md into it from {self.runtime()} (#912)")
        return f"git worktree add --detach {wt} origin/main"

    def clone(self, wt: Path, src: Path | None = None) -> None:
        """A container run's own clone of the checkout at origin/main (#661), in place of a
        worktree. A worktree keeps its index, HEAD and commits in the shared `.git`, so a
        container would need that mounted read-write, and could then plant a hook that the
        host runs on its next `git worktree add` as the user who can read every App's key.
        A clone has its own `.git`; the host's is never mounted. `--no-hardlinks` so the
        clone shares no object file with the checkout. origin then points at GitHub, so the
        run pushes there and the heartbeat hook finds the repo from it. src is the checkout
        to clone: this one, or another repo's clone (#853)."""
        root = str(src or self.root)
        url = self.git_ok("-C", root, "remote", "get-url", "origin").strip()
        self.git_ok("clone", "-q", "--no-hardlinks", "--no-checkout", root, str(wt))
        self.git_ok("-C", str(wt), "fetch", "-q", root, "+refs/remotes/origin/main:refs/remotes/origin/main")
        self.git_ok("-C", str(wt), "checkout", "-q", "--detach", "origin/main")
        self.git_ok("-C", str(wt), "remote", "set-url", "origin", url)

    def prepare_run_home(self, s: Started) -> None:
        """run_home() for s, made before docker run so docker doesn't create the mount
        sources as root: the transcript folder, and a sessions.json holding only s's entry,
        which the Stop hook reads (mounted read-only, so the run can't change its own)."""
        rh = self.run_home(s.session_id)
        for d in (rh / "launcher", rh / "claude" / "projects", self.token_dir(s.session_id)):
            d.mkdir(parents=True, exist_ok=True, mode=0o700)
        (rh / "launcher" / "sessions.json").write_text(json.dumps([s.__dict__], indent=1) + "\n")

    def is_clone(self, wt: Path) -> bool:
        """A container run's clone: its `.git` is a directory, where a worktree's is a file."""
        return (wt / ".git").is_dir()

    def clone_removable(self, wt: Path) -> bool:
        """removable() for a container run's clone (#661), checked inside a container from
        the same image, with no network and the clone mounted read-only. The run could
        write the clone's `.git/config` (core.fsmonitor, a filter), and the host must never
        run git there, or it would run that as itself. Without --container there is no
        image to check with, so the clone is kept."""
        if not self.container:
            return False
        check = ('test -z "$(git --no-optional-locks status --porcelain)" '
                 '&& test -n "$(git branch -r --contains HEAD)"')
        rc, _ = self.docker(["run", "--rm", "--network", "none", "--user", f"{os.getuid()}:{os.getgid()}",
                             "-e", "HOME=/tmp", "-v", f"{wt}:{wt}:ro", "-w", str(wt),
                             "--entrypoint", "sh", self.container, "-c", check])
        return rc == 0

    def discard(self, wt: Path) -> None:
        """Remove a new, unused worktree or clone: nothing in it to lose."""
        if self.is_clone(wt):
            shutil.rmtree(wt, ignore_errors=True)
        else:
            self.git(["-C", str(self.owner_of(wt)), "worktree", "remove", "--force", str(wt)])

    def removable(self, wt: Path) -> bool:
        """Clean (nothing uncommitted or untracked) and HEAD is on a remote branch."""
        if self.is_clone(wt):
            return self.clone_removable(wt)
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
        kept, removed = [], set()
        for wt in sorted(d.iterdir()) if d.is_dir() else []:
            if not wt.is_dir() or not UUID_RE.match(wt.name) or wt.name in alive:
                continue
            if self.is_clone(wt):
                if self.removable(wt):
                    shutil.rmtree(wt, ignore_errors=True)   # its run_home() stays: logs, cost, transcript
                else:
                    kept.append(wt)
                continue
            src = self.owner_of(wt)
            if self.removable(wt) and self.git(["-C", str(src), "worktree", "remove", str(wt)])[0] == 0:
                removed.add(src)
            else:
                kept.append(wt)
        for src in sorted(removed):
            self.git(["-C", str(src), "worktree", "prune"])
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
        prompt = shlex.quote(opener(s.role, s.issue, s.pr, s.called_by, s.call_why, s.daily,
                                    s.ask, s.ask_comment, s.research, s.research_comment,
                                    s.ruling, s.ruling_comment, s.conflict, s.repo,
                                    self.home_repo() if s.repo else None))
        if s.repo:   # #912, GOV-0039: our CLAUDE.md and role prompt, read when the window runs
            prompt += (" --append-system-prompt \"$(cat "
                       + shlex.quote(str(self.instructions_file(s.session_id))) + ')"')
        if s.by == "watch":
            result = shlex.quote(str(self.result_file(s.session_id)))
            where = f" in container swarm-{s.session_id}" if self.container else ""
            note = shlex.quote(f"swarm: headless run (claude -p){where}; it ends when done or at its "
                               f"budget, and its result is written to {self.result_file(s.session_id)}")
            if self.in_container(s):
                session = [*self.token_refresher(s), *self.docker_run(s)]
            tail = ["echo", note, "&&", *session, "-p", prompt, *self.headless_args(s), ">|", result]
        else:
            tail = [*session, prompt]
        inner = " ".join([
            "cd", shlex.quote(str(wt)), "&&",
            "echo $$ >|", shlex.quote(str(self.pid_file(s.session_id))), "&&", *tail,
        ])
        return "exec /bin/bash -c " + shlex.quote(inner)

    def token_refresher(self, s: Started) -> list[str]:
        """The start of a container run's command (#680, per the owner on #749), up to its
        `exec docker run`: write the role App's token to token_dir(), then rewrite it every
        TOKEN_REFRESH seconds in the background for as long as the run's pid ($$, the
        docker client's once it exec's) is alive and its pid file is there; then remove
        the directory. The token is minted here, on the host, by the pinned copy's
        ops/swarm-token (runtime/, only merged code), never the clone's, which the run can
        change. swarm-token reuses a token while it has over 10 minutes left, so the file
        always holds one with at least 5. Each write goes to a temporary file and is moved
        into place, so the container never reads half a token."""
        d = self.token_dir(s.session_id)
        mint = shlex.quote(str(self.home / "runtime" / "ops" / "swarm-token"))
        tmp, tok, q = shlex.quote(str(d / "token.tmp")), shlex.quote(str(d / "token")), shlex.quote(str(d))
        pid = shlex.quote(str(self.pid_file(s.session_id)))
        failed = shlex.quote(f"swarm: {s.name}: token refresh failed; retrying in {TOKEN_REFRESH}s")
        return ["umask 077", "&&",
                f"mint() {{ {mint} {shlex.quote(s.role)} >| {tmp} && mv -f {tmp} {tok}; }}", "&&",
                "mint", "&&",
                f"{{ {{ while sleep {TOKEN_REFRESH} && kill -0 $$ 2>/dev/null && test -e {pid}; do "
                f"mint || echo {failed} >&2; done; rm -rf {q}; }} </dev/null >/dev/null & }}", "&&"]

    def docker_run(self, s: Started) -> list[str]:
        """`exec docker run ...` for a run in a container (#661), shell-quoted, up to the
        claude args. The image's entrypoint sets up git and gh as the role's App from
        the token file and exec's claude with the rest.

        Only ANTHROPIC_API_KEY goes in from the host's environment, and of secrets only
        the token directory (token_refresher(); the role App's token, kept fresh on the
        host) is mounted, read-only at CONTAINER_TOKEN_DIR (#680). Read-write, at the same paths as on the host so the hook paths in its
        settings resolve: the run's own clone (prepare(); never the checkout's .git) and
        its own home, run_home(), as PRODUCTSWARM_HOME. Read-only: its sessions.json entry,
        the pinned hook copy (runtime/) and its token directory. Nothing else from the host's PRODUCTSWARM_HOME
        is mounted: not sessions.json, other runs' state or transcripts, swarm.db or the
        result files. HOME is a tmpfs. It runs as the host user, so its files stay the
        watcher's.

        The docker client stays in the foreground with --rm: its pid is the run's pid
        (state() finds --session-id in its command line), `swarm stop`'s SIGTERM reaches
        claude through it and --init, and the container goes when the run ends."""
        wt, rh, runtime = self.worktree(s.session_id), self.run_home(s.session_id), self.home / "runtime"
        entry, tokens = rh / "launcher" / "sessions.json", self.token_dir(s.session_id)
        uid, gid = os.getuid(), os.getgid()
        argv = ["docker", "run", "--rm", "--init", "--name", f"swarm-{s.session_id}",
                "--user", f"{uid}:{gid}",
                "--tmpfs", f"{CONTAINER_HOME}:uid={uid},gid={gid},mode=0700",
                "-e", "ANTHROPIC_API_KEY", "-e", f"SWARM_ROLE={s.role}",
                "-e", f"SWARM_TOKEN_FILE={CONTAINER_TOKEN_DIR}/token",
                "-e", f"HOME={CONTAINER_HOME}", "-e", f"PRODUCTSWARM_HOME={rh}",
                "-v", f"{wt}:{wt}", "-v", f"{rh}:{rh}", "-v", f"{entry}:{entry}:ro",
                "-v", f"{runtime}:{runtime}:ro", "-v", f"{tokens}:{CONTAINER_TOKEN_DIR}:ro",
                "-v", f"{rh}/claude/projects:{CONTAINER_HOME}/.claude/projects",
                "-w", str(wt), self.container or "",
                "--model", s.model, "--session-id", s.session_id]
        return ["exec", *(shlex.quote(a) for a in argv)]

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
        on = f"  on {ref_text(entry.issue, entry.repo)}" if entry.issue else ""
        on += (f", PR {ref_text(entry.pr, entry.repo)}" if entry.issue else
               f"  on PR {ref_text(entry.pr, entry.repo)}") if entry.pr else ""
        if dry_run:
            self.out(f"would start: {entry.name}  {entry.model}{on}\n"
                     f"  {self.prepare_line(entry)}\n"
                     f"  {self.command(entry)}")
            return True
        self.dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            self.prepare(entry)
        except (RuntimeError, OSError) as e:
            self.out(f"failed to start {entry.name}: {e}")
            if self.worktree(entry.session_id).exists():
                self.discard(self.worktree(entry.session_id))   # new and unused: nothing to lose
            return False
        self.add(entry)   # before the window opens, so its pid file never has no entry (#272)
        try:
            script = self.window_file(entry.session_id)
            script.write_text(self.command(entry) + "\n")
            self.run(self.typed(entry))
        except (RuntimeError, OSError, subprocess.SubprocessError) as e:
            self.out(f"failed to start {entry.name}: {e}")
            self.remove(entry.session_id)
            self.window_file(entry.session_id).unlink(missing_ok=True)
            self.discard(self.worktree(entry.session_id))   # new and unused: nothing to lose
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
        for home in (self.run_home(sid), self.home):   # a container run's state is in its own (#661)
            try:
                return bool(json.loads((home / "state" / f"{sid}.json").read_text()).get("stopped"))
            except (FileNotFoundError, ValueError):
                continue
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
            now: dt.datetime, ago: Callable, usd: Callable = lambda x: "-" if x is None else f"${x:,.2f}",
            show_all: bool = False) -> list[list[str]]:
    """One row per live heartbeat session, plus launcher sessions with no heartbeat yet.
    Sessions that never acted (#454) are left out unless show_all, which marks them.

    model is dashboard/generate.py's build() output, so status, current issue and last
    activity are read exactly as the dashboard reads them."""
    by_sid = {e.session_id: e for e in started}
    rows, seen = [], set()
    for s in model["sessions"]:
        if s["status"] == "stopped" or (s.get("never_acted") and not show_all):
            continue
        e = by_sid.get(s["session_id"])
        seen.add(s["session_id"])
        rows.append([e.name if e else "-", s["role"], s["model"] or "-",
                     f"#{s['issue']}" if s["issue"] else "-",
                     s["status"] + (f" on #{s['gov_question']}" if s["gov_question"] else "")
                     + (", never acted" if s.get("never_acted") else ""),
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


def ls(launcher: Launcher, repo: str, idle_minutes: int, show_all: bool = False,
       manifest_path: Path | str = manifest.DEFAULT_PATH) -> int:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    model = heartbeat(repo, idle_minutes, now)
    g = dashboard()
    rows = ls_rows(model, launcher.live(), launcher.state, now, g.ago, g.spend.usd, show_all)
    if not rows:
        launcher.out("no live sessions")
    else:
        launcher.out(table(["NAME", "ROLE", "MODEL", "ISSUE", "STATUS", "LAST", "SPEND (EST.)", "PROCESS",
                            "SESSION"], rows))
    for wt in launcher.kept:
        launcher.out(f"worktree kept: {wt} (uncommitted or unpushed work)")
    for line in paused_lines(manifest_path):
        launcher.out(line)
    return 0


def paused_lines(manifest_path: Path | str) -> list[str]:
    """One line per repo paused in swarm.toml's [org] paused (#892), for `swarm ls`."""
    paused, problems = manifest.load_paused(manifest_path)
    if paused is None:
        return [f"paused: every repo, until swarm.toml is fixed: {p}" for p in problems]
    return [f"paused: {r} (swarm.toml's [org] paused): swarm watch starts nothing there and "
            f"the merger merges nothing" for r in sorted(paused)]


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
    try:
        limits = manifest.load_watch(manifest_path)
    except manifest.ManifestError:
        limits = None
    try:
        acted = watch.load_state(launcher)["acted"]
    except RuntimeError:
        acted = {}
    daily = watch.daily_text(limits, acted, now)
    launcher.out(inbox_text(items, now, g, watch.waiting(launcher), watch.runs(launcher),
                            review_in_actions(manifest_path), daily))
    return 0


def inbox_text(items: list[dict], now: dt.datetime, g, held: tuple | None = None,
               runs: list[dict] | None = None, review_in_actions: bool = False,
               daily: str | None = None) -> str:
    """The needs-you list, then a line if swarm watch leaves [review] to Actions (#216),
    then when [daily] is next due if it is on (watch.daily_text(), #588),
    then runs `swarm watch` started that ended at cap (#149) or never started (#550), then any triggers it is
    holding or skipping (#90), then each recorded run's cost (#149).

    held is watch.waiting(): (when swarm watch last checked, its waiting triggers); runs
    is watch.runs(). Both come from local state, not GitHub, so the dashboard (built and
    published by a GitHub Action) doesn't show them, and the costs never leave this machine
    (GOV-0002, GOV-0003, GOV-0004)."""
    import watch
    checked, waiting = held or (None, [])
    capped, recent, failed = watch.runs_text(runs or [], now, g.ago) if runs else ([], [], [])
    out = [f"{n}. {g.needs_line(i, now)}\n   {i['url']}" for n, i in enumerate(items, 1)]
    if not items and not waiting and not capped and not failed:
        out.append(g.NEEDS_EMPTY)
    if review_in_actions:
        out.append(f"\n{REVIEW_IN_ACTIONS}")
    if daily:
        out.append(f"\n{daily}")
    if capped:
        out.append("\nswarm watch runs that ended at cap (restart one if its work should go on):")
        out += capped
    if failed:
        out.append(f"\nswarm watch runs that failed: they never started, after {watch.MAX_RETRIES} "
                   f"retries (#550; re-add the label to try again):")
        out += failed
    if waiting:
        out.append(f"\nswarm watch is holding (last check {g.ago(checked, now)}):")
        out += [f"- [{w['kind']}] {w['ref']} {w['why']} · {w['reason']}" for w in waiting]
    if recent:
        out.append(f"\nswarm watch runs in the last {watch.RUNS_DAYS} days (cost is Claude Code's local estimate):")
        out += recent
    return "\n".join(out).lstrip("\n")


def cost(launcher: Launcher, repo: str, get_prs: Callable | None = None) -> int:
    """`swarm cost` (#176): the runs in the watch state, costed per PR. Only prints: no cost
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


# ---------------------------------------------------------------- merges (#710)

MERGER_LOGIN = "productswarm-merger[bot]"     # merger.MERGER; not imported, merger imports swarm
REVIEWER_LOGIN = "productswarm-reviewer[bot]"
REVERT_TITLE_RE = re.compile(r'^\s*Revert\b', re.IGNORECASE)
REVERTS_RE = re.compile(r'^\s*(?:Reverts\s+(?:[\w.-]+/[\w.-]+)?#(\d+)|This reverts commit\b)',
                        re.IGNORECASE | re.MULTILINE)
MERGE_FIELDS = "number,title,body,mergedAt,mergedBy,headRefOid,reviews,comments"
ENQUEUED = "Enqueued under"   # merger.ENQUEUED: the merger's comment when it enqueues (#663)


def bare(login: str | None) -> str:
    """A login without GitHub's `[bot]` suffix: GraphQL (and so `gh pr list`) drops it, REST
    keeps it, and the two must compare equal."""
    return (login or "").removesuffix("[bot]")


def week_of(now: dt.datetime, last: bool = False) -> tuple[dt.datetime, dt.datetime]:
    """The UTC week (Monday 00:00 to the next Monday 00:00) holding now, or the one before."""
    monday = (now.astimezone(dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
              - dt.timedelta(days=now.astimezone(dt.timezone.utc).weekday()))
    if last:
        monday -= dt.timedelta(days=7)
    return monday, monday + dt.timedelta(days=7)


def reverted(pr: dict) -> int | None | bool:
    """False if pr isn't a revert; else the PR number it reverts (GitHub's Revert button
    writes `Reverts owner/repo#N`), or None when it reverts by commit or names no PR."""
    m = REVERTS_RE.search(pr.get("body") or "")
    if m:
        return int(m.group(1)) if m.group(1) else None
    return None if REVERT_TITLE_RE.match(pr.get("title") or "") else False


def reviewed_at_head(pr: dict, owner: str) -> bool:
    """Whether the reviewer App or the owner approved at the merged head: their latest
    approve-or-request-changes review on that commit is an approval (GOV-0027's test)."""
    head, who = pr.get("headRefOid"), {bare(REVIEWER_LOGIN), bare(owner)}
    latest: dict[str, str] = {}
    for r in pr.get("reviews") or []:
        login = bare((r.get("author") or {}).get("login"))
        if (login in who and (r.get("commit") or {}).get("oid") == head
                and r.get("state") in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED")):
            latest[login] = r["state"]
    return "APPROVED" in latest.values() and "CHANGES_REQUESTED" not in latest.values()


def enqueued_by_merger(pr: dict) -> bool:
    """Whether the merger App enqueued this PR at its merged head: its `Enqueued under ... at
    <sha>` comment for that head (merger.enqueued_body)."""
    head = pr.get("headRefOid")
    return bool(head) and any(
        bare((c.get("author") or {}).get("login")) == bare(MERGER_LOGIN)
        and (c.get("body") or "").startswith(ENQUEUED) and f" at {head}" in (c.get("body") or "")
        for c in pr.get("comments") or [] if isinstance(c, dict))


def merged_by(pr: dict, owner: str) -> str:
    """Who merged pr, bare. Under a merge queue GitHub merges, so `mergedBy` may not be the
    merger (#746): a PR the merger enqueued at its merged head counts as the merger's unless
    `mergedBy` is the owner."""
    who = bare((pr.get("mergedBy") or {}).get("login"))
    if who != bare(owner) and enqueued_by_merger(pr):
        return bare(MERGER_LOGIN)
    return who


def merges_text(prs: list[dict], owner: str, start: dt.datetime, end: dt.datetime) -> str:
    """`swarm merges`' report: the week's merges into main split by who clicked merge, then
    each revert and whether it was reviewed at head. A merge the merger enqueued counts as the
    merger's (merged_by). PRs merged outside [start, end) are dropped, so the caller's search
    may be loose."""
    def merged_at(p):
        return dt.datetime.fromisoformat((p.get("mergedAt") or "").replace("Z", "+00:00"))
    week = sorted((p for p in prs if p.get("mergedAt") and start <= merged_at(p) < end),
                  key=lambda p: (p["mergedAt"], p["number"]))
    by = [merged_by(p, owner) for p in week]
    n_merger, n_owner = by.count(bare(MERGER_LOGIN)), by.count(bare(owner))
    others = sorted({b or "unknown" for b in by} - {bare(MERGER_LOGIN), bare(owner)})
    last_day = (end - dt.timedelta(days=1)).date()
    out = [f"Merges into main, week of {start.date()} to {last_day} (UTC): {len(week)}",
           f"  by the merger ({MERGER_LOGIN}): {n_merger}",
           f"  by the owner (@{owner}): {n_owner}"]
    if others:
        out.append(f"  by anyone else: {len(week) - n_merger - n_owner} "
                   f"({', '.join('@' + o for o in others)})")
    reverts = [(p, reverted(p)) for p in week if reverted(p) is not False]
    unreviewed = sum(not reviewed_at_head(p, owner) for p, _ in reverts)
    out.append(f"Reverts: {len(reverts)}" + (f", {unreviewed} unreviewed" if reverts else ""))
    for p, of in reverts:
        who = merged_by(p, owner) or "unknown"
        what = f"reverts #{of}" if of else "reverts a commit"
        state = ("reviewed (approved at head)" if reviewed_at_head(p, owner)
                 else "not reviewed (no approval at head by the reviewer or the owner)")
        out.append(f"  #{p['number']} {what}, merged by @{who}: {state}")
    return "\n".join(out)


def gh_merged(repo: str, start: dt.datetime, end: dt.datetime) -> list[dict]:
    """PRs merged into main in [start, end), from GitHub search (at most 1000)."""
    span = f"{start:%Y-%m-%dT%H:%M:%SZ}..{end:%Y-%m-%dT%H:%M:%SZ}"
    return dashboard().gh_json("pr", "list", "--repo", repo, "--state", "merged", "--base", "main",
                               "--search", f"merged:{span}", "--limit", "1000",
                               "--json", MERGE_FIELDS) or []


def merges(launcher: Launcher, repo: str, last: bool = False, now: dt.datetime | None = None,
           get_merged: Callable | None = None, owner: Callable[[], str] | None = None) -> int:
    """`swarm merges` (#710): this week's (or last week's) merges by the merger and by the
    owner, and its reverts. Reads GitHub; writes nothing."""
    start, end = week_of(now or dt.datetime.now(dt.timezone.utc), last)
    prs = (get_merged or gh_merged)(repo, start, end)
    launcher.out(merges_text(prs, (owner or owner_login)(), start, end))
    return 0


# ---------------------------------------------------------------- daily (#707)

DAILY_DAYS = 10                # how far back `swarm daily` lists reports; a lookback, not a streak (GOV-0040)
REPORT_RE = re.compile(r"^\W*daily report\b", re.IGNORECASE)
REPORT_DATE_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")


def working_days(today: dt.date, n: int = DAILY_DAYS) -> list[dt.date]:
    """The last n working days (Monday to Friday) up to and including today, newest first."""
    out, day = [], today
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day)
        day -= dt.timedelta(days=1)
    return out


def report_day(c: dict, tz: dt.tzinfo | None = None) -> tuple[dt.date, dt.datetime] | None:
    """(the day it reports on, when it was posted, local) for a daily report comment, else None.
    A report is a comment whose first line starts "Daily report" (bold or not). Its day is the
    first date on that line, so a late report still counts for its day; else the posting date."""
    first = ((c.get("body") or "").strip().splitlines() or [""])[0]
    if not REPORT_RE.match(first) or not c.get("created_at"):
        return None
    posted = dt.datetime.fromisoformat(c["created_at"].replace("Z", "+00:00"))
    posted = posted.astimezone(tz) if tz else posted.astimezone()
    m = REPORT_DATE_RE.search(first)
    try:
        return (dt.date.fromisoformat(m.group(1)) if m else posted.date()), posted
    except ValueError:
        return posted.date(), posted


def daily_rows(days: list[dt.date], comments: list[dict], acted: dict, report_issue: int,
               trusted: set[str], tz: dt.tzinfo | None = None) -> list[dict]:
    """One row per day: {day, posted (local time of the first report, or None), by}. by is
    "[daily]" when swarm.db records a [daily] start for that day (its `daily:<issue>:<date>` key
    in watch_acted, which the watcher never prunes), "by hand" when a report was posted without
    one, and None when there was no report. Only comments by a swarm App or the owner count."""
    first: dict[dt.date, dt.datetime] = {}
    for c in comments:
        if (c.get("user") or {}).get("login") not in trusted:
            continue
        r = report_day(c, tz)
        if r and (r[0] not in first or r[1] < first[r[0]]):
            first[r[0]] = r[1]
    rows = []
    for day in days:
        started = str(acted.get(f"daily:{report_issue}:{day}", "")).startswith("started")
        posted = first.get(day)
        by = None if posted is None else "[daily]" if started else "by hand"
        rows.append({"day": day, "posted": posted, "by": by, "ran": started})
    return rows


def daily_started(rows: list[dict]) -> dt.date | None:
    """The latest day whose report a [daily] run started, else None. M1's criterion "a daily
    report posts without the owner starting it" is shown once such a report exists (GOV-0040)."""
    return next((r["day"] for r in rows if r["by"] == "[daily]"), None)


def daily_text(rows: list[dict], report_issue: int, today: dt.date) -> str:
    """`swarm daily`'s output: a line per working day, newest first, then the latest report
    [daily] started. No streak: a Goal's capability is shown once (GOV-0040)."""
    out = [f"Daily reports on #{report_issue}, last {len(rows)} working days (local time):"]
    for r in rows:
        when = f"{r['day']:%a %Y-%m-%d}"
        if r["posted"] is not None:
            who = "[daily]" if r["by"] == "[daily]" else "the owner, by hand (no [daily] run)"
            out.append(f"  {when}  posted {r['posted']:%H:%M}  started by {who}")
        elif r["day"] == today:
            out.append(f"  {when}  not yet posted" + ("  ([daily] run started)" if r["ran"] else ""))
        else:
            out.append(f"  {when}  missed" + ("  ([daily] ran but posted no report)" if r["ran"] else ""))
    last = daily_started(rows)
    out.append(f"\nLatest report [daily] started: {last:%a %Y-%m-%d}." if last else
               f"\nNo report in these {len(rows)} working days was started by [daily].")
    return "\n".join(out)


# Goal and Area edits (#709, GOV-0031): the report flags any edit to one by anyone but the owner.
SCOPE_EDITS_QUERY = (
    "query($q: String!) { search(query: $q, type: ISSUE, first: 100) { issueCount nodes { "
    "... on Issue { number title repository { nameWithOwner } author { login __typename } "
    "issueType { name } userContentEdits(first: 50) { totalCount nodes { editedAt "
    "editor { login __typename } } } timelineItems(last: 50, itemTypes: [RENAMED_TITLE_EVENT, "
    "CLOSED_EVENT, REOPENED_EVENT]) { totalCount nodes { __typename "
    "... on RenamedTitleEvent { createdAt actor { login __typename } } "
    "... on ClosedEvent { createdAt actor { login __typename } } "
    "... on ReopenedEvent { createdAt actor { login __typename } } } } } } } }")
SCOPE_EDIT_WHAT = {"edit": "edited the body", "RenamedTitleEvent": "renamed it",
                   "ClosedEvent": "closed it", "ReopenedEvent": "reopened it"}


def scope_edits(nodes: list[dict], owner: str, since: dt.datetime) -> tuple[list[dict], list[dict]]:
    """Edits since `since` to a Goal or Area the owner opened, by anyone but the owner (GOV-0031):
    body edits, title renames, closes and reopens. Returns (edits oldest first, each {repo,
    number, title, type, what, by, at}; the issues whose history was too long to read whole)."""
    def login(a: dict | None) -> str:
        return "ghost" if not a else a["login"] + "[bot]" if a.get("__typename") == "Bot" else a["login"]

    def when(s: str) -> dt.datetime:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    out, partial = [], []
    for n in nodes:
        kind = ((n or {}).get("issueType") or {}).get("name")
        if kind not in SCOPE_TYPES or login(n.get("author")) != owner:
            continue
        ref = {"repo": (n.get("repository") or {}).get("nameWithOwner"), "number": n.get("number"),
               "title": n.get("title"), "type": kind}
        edits = n.get("userContentEdits") or {}
        items = n.get("timelineItems") or {}
        if (edits.get("totalCount", 0) > len(edits.get("nodes") or [])
                or items.get("totalCount", 0) > len(items.get("nodes") or [])):
            partial.append(ref)
        found = [("edit", e.get("editor"), e.get("editedAt")) for e in edits.get("nodes") or []]
        found += [(t.get("__typename"), t.get("actor"), t.get("createdAt"))
                  for t in items.get("nodes") or []]
        for what, who, at in found:
            if at and login(who) != owner and when(at) >= since and what in SCOPE_EDIT_WHAT:
                out.append({**ref, "what": SCOPE_EDIT_WHAT[what], "by": login(who), "at": when(at)})
    return sorted(out, key=lambda e: e["at"]), partial


def gh_scope_nodes(repo: str, since: dt.date) -> list[dict]:
    """The Goal and Area issues in the repo owner's account updated since `since`, open or closed:
    one search per type (search can't OR two types)."""
    g = dashboard()
    nodes = []
    for kind in sorted(SCOPE_TYPES):
        q = f"user:{repo.split('/', 1)[0]} is:issue type:{kind} updated:>={since}"
        d = g.gh_json("api", "graphql", "-f", f"query={SCOPE_EDITS_QUERY}", "-f", f"q={q}")
        nodes += ((d or {}).get("data") or {}).get("search", {}).get("nodes") or []
    return nodes


def scope_edits_text(edits: list[dict], partial: list[dict], owner: str, since: dt.datetime,
                     repo: str | None = None, tz: dt.tzinfo | None = None) -> str:
    """The Goal and Area edits for the report's Risks, or a line saying there were none."""
    head = f"Goal and Area edits not made by @{owner} since {since:%a %Y-%m-%d %H:%M} (GOV-0031):"
    lines = [f"  {e['at'].astimezone(tz) if tz else e['at'].astimezone():%a %Y-%m-%d %H:%M}  "
             f"{e['by']} {e['what']}: {e['type']} {scope_ref(e, repo)} {e['title']}" for e in edits]
    lines += [f"  {r['type']} {scope_ref(r, repo)}: history too long to read whole; check it by hand" for r in partial]
    return "\n".join([head, *(lines or ["  none"])])


# Merged PRs whose closing issues are still open (#806). GitHub closes a PR's closing issues as
# whoever merged it, and the merger's token holds only `issues: read` (GOV-0028), so its merges
# leave them open. Per the owner's answer on #812 (option 2), the planner closes them in its
# daily run; this lists them. An issue reopened since is left out: someone meant it to be open.
UNCLOSED_QUERY = (
    "query($q: String!, $after: String) { search(query: $q, type: ISSUE, first: 100, after: $after) { "
    "pageInfo { hasNextPage endCursor } nodes { ... on PullRequest { number mergedBy { login __typename } "
    "closingIssuesReferences(first: 10) { nodes { number state repository { nameWithOwner } "
    "timelineItems(itemTypes: [REOPENED_EVENT]) { totalCount } } } } } } }")


def unclosed(nodes: list[dict], repo: str | None = None) -> list[dict]:
    """The still-open, never-reopened closing issues of the merged PRs in `nodes`, oldest PR
    first: each {repo, number, pr, merged_by}."""
    out = []
    for n in sorted((n for n in nodes if n and n.get("number")), key=lambda n: n["number"]):
        by = n.get("mergedBy") or {}
        merged_by = "ghost" if not by else by["login"] + ("[bot]" if by.get("__typename") == "Bot" else "")
        for i in (n.get("closingIssuesReferences") or {}).get("nodes") or []:
            if (i or {}).get("state") != "OPEN" or ((i.get("timelineItems") or {}).get("totalCount") or 0):
                continue
            out.append({"repo": (i.get("repository") or {}).get("nameWithOwner") or repo,
                        "number": i["number"], "pr": n["number"], "merged_by": merged_by})
    return out


def gh_merged_nodes(repo: str, since: dt.date) -> list[dict]:
    """The repo's PRs merged since `since`, with their closing issues, a page of 100 at a time."""
    g, nodes, after = dashboard(), [], []
    for _ in range(10):
        d = g.gh_json("api", "graphql", "-f", f"query={UNCLOSED_QUERY}",
                      "-f", f"q=repo:{repo} is:pr is:merged merged:>={since}", *after)
        search = ((d or {}).get("data") or {}).get("search") or {}
        nodes += search.get("nodes") or []
        page = search.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            break
        after = ["-f", f"after={page['endCursor']}"]
    return nodes


def unclosed_text(issues: list[dict], since: dt.date, repo: str | None = None) -> str:
    """The issues the planner closes before posting the daily report, or a line saying none."""
    head = f"Issues still open after a merged PR that closes them, PRs merged since {since:%a %Y-%m-%d} (#806):"
    lines = [f"  {scope_ref(i, repo)}  PR #{i['pr']} closes it, merged by {i['merged_by']}" for i in issues]
    return "\n".join([head, *(lines or ["  none"])])


def daily(launcher: Launcher, repo: str, manifest_path: Path | str = manifest.DEFAULT_PATH,
          get_comments: Callable | None = None, now: dt.datetime | None = None,
          tz: dt.tzinfo | None = None, owner: str | None = None,
          agents: set[str] | None = None, get_scopes: Callable | None = None,
          get_merged: Callable | None = None, effort_cache: Path | str | None = None) -> int:
    """`swarm daily` (#707): for each of the last 10 working days, whether a daily report was
    posted on the report issue, when, and who started it, and the latest one [daily] started
    (as information, not a streak: GOV-0040). Who started it comes from swarm.db; the reports
    and their times come from the report issue's comments (swarm.db holds no comments). Then
    the edits to a Goal or Area by anyone but the owner since the last working day began
    (#709), and the issues still open after a PR that closes them merged in those 10 working
    days (#806), and the upkeep risk per Goal from the effort cache (#1013). Only reads."""
    import watch
    try:
        limits = manifest.load_watch(manifest_path)
    except manifest.ManifestError as e:
        launcher.out(f"swarm daily: {e}")
        return 1
    if not (limits and limits.report_issue):
        launcher.out(f"swarm daily: {manifest_path} has no [watch] report_issue to count reports on")
        return 1
    n = limits.report_issue
    now = now or dt.datetime.now(dt.timezone.utc)
    today = (now.astimezone(tz) if tz else now.astimezone()).date()
    owner = owner or owner_login()
    trusted = (agents if agents is not None else agent_logins()) | {owner}
    acted = watch.load_state(launcher)["acted"]
    comments = (get_comments or watch.gh_comments)(repo, n)
    days = working_days(today)
    rows = daily_rows(days, comments, acted, n, trusted, tz)
    # From the start of the working day before the latest one, so a weekend's edits count Monday.
    prev = days[1] if days[0] == today else days[0]
    since = dt.datetime.combine(prev, dt.time(), tz or now.astimezone().tzinfo)
    try:
        edits = scope_edits_text(*scope_edits((get_scopes or gh_scope_nodes)(repo, prev), owner, since),
                                 owner, since, repo, tz)
    except RuntimeError as e:
        edits = f"Goal and Area edits couldn't be read: {e}"
    try:
        stale = unclosed_text(unclosed((get_merged or gh_merged_nodes)(repo, days[-1]), repo), days[-1], repo)
    except RuntimeError as e:
        stale = f"Issues still open after their PR merged couldn't be read: {e}"
    dashboard()   # puts effort.py on the path
    import effort
    cache = effort.load(effort_cache) if effort_cache else effort.load()
    effort_risks = effort.daily_text(effort.build(cache, repo, now, []), effort_cache or effort.CACHE_NAME)
    launcher.out(f"{daily_text(rows, n, today)}\n\n{edits}\n\n{effort_risks}\n\n{stale}")
    return 0


# ---------------------------------------------------------------- acts (#771)

ACTS_DAYS = 10                 # `swarm acts`' default window, two weeks of working days: what
                               # it shows, not a run to pass (per GOV-0040)

def owner_acts(launcher: Launcher, repo: str, manifest_path: Path | str = manifest.DEFAULT_PATH,
               day: dt.date | None = None, as_json: bool = False, now: dt.datetime | None = None,
               tz: dt.tzinfo | None = None, owner: str | None = None, gh_json: Callable | None = None,
               gh_items: Callable | None = None) -> int:
    """`swarm acts`: read the owner's acts back from GitHub (the webhook leads, and a backfill of
    each finished day not yet counted, acts.refresh), then print them for each working day in
    the last ACTS_DAYS, or for `day`, from swarm.db. A day not backfilled reads `not counted`
    (#844). Acts are counted with no limit (per GOV-0040)."""
    import acts
    import merger
    try:
        limits = manifest.load_watch(manifest_path)
    except manifest.ManifestError as e:
        launcher.out(f"swarm acts: {e}")
        return 1
    report = (repo, limits.report_issue) if limits and limits.report_issue else None
    owner = owner or owner_login()
    g = None if gh_json and gh_items else dashboard()
    now = now or dt.datetime.now(dt.timezone.utc)
    days = [day] if day else working_days((now.astimezone(tz) if tz else now.astimezone()).date(),
                                            ACTS_DAYS)
    rows, errors = acts.refresh(launcher.dir, owner, report, repo, gh_json or g.gh_json,
                                gh_items or g.gh_items, merger.is_protected, days, now, tz)
    if as_json:
        launcher.out(json.dumps({"owner": owner, "days": rows, "unread_errors": errors}, indent=2))
    else:
        launcher.out(acts.text(rows, owner, repo))
        for e in errors:
            launcher.out(f"swarm acts: not read yet, will retry: {e}")
        if not report:
            launcher.out(f"swarm acts: {manifest_path} has no [watch] report_issue, so no act "
                         f"is counted as 'report'")
    return 0


# ---------------------------------------------------------------- trouble (#803)

def trouble(launcher: Launcher, repo: str, manifest_path: Path | str = manifest.DEFAULT_PATH,
            hours: int = 24, as_json: bool = False, owner: str | None = None,
            read: Callable | None = None) -> int:
    """`swarm trouble`: per open Goal and Area, progress, stuck work, what waits on the owner
    and authority used (trouble.py). Only reads."""
    import trouble as t
    owner = owner or owner_login()
    data = (read or t.gather)(launcher, repo, owner, manifest_path, hours)
    r = t.report(data)
    launcher.out(json.dumps(r, indent=2) if as_json else t.text(r))
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


# GOV-0026: an issue under an open PLAN.md milestone is go without `ready` (#582).
MILESTONE_RE = re.compile(r"^\s*\*\*Milestone:\*\*[ \t]*M(\d+)\b", re.MULTILINE | re.IGNORECASE)
PLAN_HEADING_RE = re.compile(r"^##[ \t]+M(\d+)\b(.*)$", re.MULTILINE)
# PLAN.md's format (#574) doesn't yet say how a milestone is marked done. Either of these
# counts, so a milestone someone has tried to close fails closed: a heading with "(done)"
# or "✅", or a `**Status:** done` line in the milestone's section.
DONE_HEADING_RE = re.compile(r"\(done\b[^)]*\)|✅", re.IGNORECASE)
DONE_STATUS_RE = re.compile(r"^\s*(?:[-*]\s*)?\*\*Status:\*\*[ \t]*done\b", re.MULTILINE | re.IGNORECASE)
AGENTS_RE = re.compile(r"^([ \t]+)agents:[ \t]*\n((?:\1[ \t]+\S.*\n?)+)", re.MULTILINE)
AGENT_LOGIN_RE = re.compile(r':[ \t]*"([^"]+)"')


def agent_logins(path: Path = JURISDICTIONS) -> set[str]:
    """identities.agents from jurisdictions.yml: every swarm App's login."""
    m = AGENTS_RE.search(path.read_text())
    if not m:
        raise RuntimeError(f"can't find identities.agents in {path}")
    return set(AGENT_LOGIN_RE.findall(m.group(2)))


def milestone_of(body: str | None) -> int | None:
    """n from the body's first `**Milestone:** M<n>` line, or None ("no milestone yet")."""
    m = MILESTONE_RE.search(body or "")
    return int(m.group(1)) if m else None


def plan_milestones(plan: str) -> dict[int, bool]:
    """Each `## M<n>` section of PLAN.md, and whether it is marked done."""
    heads = list(PLAN_HEADING_RE.finditer(plan))
    out = {}
    for i, h in enumerate(heads):
        section = plan[h.end():heads[i + 1].start() if i + 1 < len(heads) else len(plan)]
        out[int(h.group(1))] = bool(DONE_HEADING_RE.search(h.group(2))
                                    or DONE_STATUS_RE.search(section))
    return out


@dataclass
class GoReader:
    """What the go needs beyond the issue and its events, read only when asked: PLAN.md on
    main (None if it isn't there), an issue's state, the issue's comments, and its scope
    (GOV-0031: its sub-issue parents and blocked-by links, parse_scope(); None if unread)."""
    plan: Callable[[], str | None]
    state: Callable[[int], str | None]
    comments: Callable[[], list[dict]]
    scope: Callable[[], dict | None] = lambda: None


# GOV-0031 (#681): an issue under an open Goal or Area the owner opened is go. For one week
# after it merged (#668, 2026-11-09 13:54 UTC) the GOV-0026 milestone lines count too.
SCOPE_TYPES = {"Goal", "Area"}
BUILD_TYPES = {None, "Task", "Bug", "Feature"}   # implementation issues (#690); None: no type set
SCOPE_DEPTH = 6               # sub-issue levels read above an issue; deeper ones don't count
BLOCKERS_MAX = 50             # blocked-by issues read; an issue with more isn't go
MILESTONE_UNTIL = dt.datetime(2026, 11, 16, 13, 54, 22, tzinfo=dt.timezone.utc)
_SCOPE_NODE = "number state author { login __typename } issueType { name } repository { nameWithOwner }"


def scope_field(depth: int = SCOPE_DEPTH) -> str:
    """The GraphQL for one issue's scope, as `field % (n, n)` for ghql.batched()."""
    chain = ""
    for _ in range(depth):
        chain = f"parent {{ {_SCOPE_NODE} {chain} }}"
    return ("i%d: issue(number: %d) { author { login __typename } issueType { name } "
            f"blockedBy(first: {BLOCKERS_MAX}) {{ totalCount nodes {{ number state "
            f"repository {{ nameWithOwner }} }} }} {chain} }}")


def parse_scope(node: dict | None) -> dict | None:
    """An issue's scope from scope_field()'s data: {"author", "type", "parents": [nearest first, each
    {repo, number, state, type, author}], "deep": the chain may go on past SCOPE_DEPTH,
    "blocked_by": [{repo, number, state}], "blockers_complete"}. States are lower case and
    logins are REST's. None if the query didn't return the issue."""
    if not node:
        return None

    def login(a: dict | None) -> str:   # REST's login, as dashboard/ghql.login (the stop hook can't import it)
        return "ghost" if not a else a["login"] + "[bot]" if a.get("__typename") == "Bot" else a["login"]
    parents, p = [], node.get("parent")
    while p:
        parents.append({"repo": (p.get("repository") or {}).get("nameWithOwner"),
                        "number": p.get("number"), "state": (p.get("state") or "").lower(),
                        "type": (p.get("issueType") or {}).get("name"),
                        "author": login(p.get("author"))})
        p = p.get("parent")
    conn = node.get("blockedBy") or {}
    nodes = conn.get("nodes") or []
    return {"author": login(node.get("author")), "type": (node.get("issueType") or {}).get("name"),
            "parents": parents,
            "deep": len(parents) >= SCOPE_DEPTH,
            "blocked_by": [{"repo": (b.get("repository") or {}).get("nameWithOwner"),
                            "number": b.get("number"), "state": (b.get("state") or "").lower()}
                           for b in nodes],
            "blockers_complete": conn.get("totalCount", 0) <= len(nodes)}


def scope_ref(x: dict, repo: str | None = None) -> str:
    """#n, or owner/name#n for an issue in another repo."""
    return f"#{x['number']}" if x.get("repo") in (None, repo) else f"{x['repo']}#{x['number']}"


def scope_goal(scope: dict | None, owner: str) -> dict | None:
    """The nearest open Goal or Area above the issue that the owner opened, or None."""
    return next((p for p in (scope or {}).get("parents") or []
                 if p["state"] == "open" and p["type"] in SCOPE_TYPES and p["author"] == owner), None)


def scope_refusal(n: int, issue: dict, scope: dict | None, owner: str, agents: set[str],
                  comments: Callable[[], list[dict]] | None, blockers: bool = True,
                  repo: str | None = None) -> str | None:
    """Why issue n isn't go under a Goal or Area (GOV-0031), or None if it is. blockers=False
    leaves its open blocked-by issues out (the watcher holds those, #490), and comments=None
    leaves the owner's comments out (a call-in's own comment mustn't veto it, #594)."""
    if scope is None:
        return f"#{n}'s sub-issue links couldn't be read"
    author = (issue.get("user") or {}).get("login")
    if author != owner and author not in agents:
        return (f"#{n} was opened by {author or 'nobody we can see'}, not a swarm App or "
                f"@{owner}, so a Goal or Area above it doesn't make it go")
    if scope.get("type") not in BUILD_TYPES:
        return (f"#{n} is a {scope['type']}, not an implementation issue (Task, Bug or Feature), "
                f"so a Goal or Area above it doesn't make it go (GOV-0031)")
    if scope_goal(scope, owner) is None:
        if not scope["parents"]:
            return f"#{n} isn't a sub-issue of anything, so no Goal or Area makes it go"
        near = next((p for p in scope["parents"] if p["type"] in SCOPE_TYPES), None)
        if near and near["author"] != owner:
            return (f"#{n}'s {near['type']} {scope_ref(near, repo)} was opened by {near['author']}, "
                    f"not @{owner}, so it doesn't count (GOV-0031)")
        if near:
            return f"#{n}'s {near['type']} {scope_ref(near, repo)} is closed"
        deep = f" within {SCOPE_DEPTH} levels" if scope["deep"] else ""
        return f"#{n} isn't under an open Goal or Area that @{owner} opened{deep}"
    labels = {lb.get("name") for lb in issue.get("labels") or []}
    if "hold" in labels:
        return f"#{n} is labelled `hold`: the owner's veto"
    if blockers:
        if not scope["blockers_complete"]:
            return f"#{n} has more than {BLOCKERS_MAX} blocked-by issues; not all could be read"
        still = [b for b in scope["blocked_by"] if b["state"] != "closed"]
        if still:
            return f"#{n} is blocked by {', '.join(scope_ref(b, repo) for b in still)}, still open"
    if comments is not None and any((c.get("user") or {}).get("login") == owner for c in comments()):
        return (f"@{owner} commented on #{n}: that's a veto until @{owner} labels it `ready`")
    return None


def milestone_open(now: dt.datetime | None) -> bool:
    """Whether GOV-0031's week for the GOV-0026 milestone lines is still running."""
    return (now or dt.datetime.now(dt.timezone.utc)) < MILESTONE_UNTIL


def milestone_refusal(n: int, issue: dict, owner: str, agents: set[str], r: GoReader) -> str | None:
    """Why issue n isn't go by its milestone (GOV-0026), or None if it is."""
    m = milestone_of(issue.get("body"))
    if m is None:
        return f"#{n} has no `**Milestone:** M<n>` line"
    author = (issue.get("user") or {}).get("login")
    if author != owner and author not in agents:
        return (f"#{n} was opened by {author or 'nobody we can see'}, not a swarm App or "
                f"@{owner}, so its milestone doesn't make it go")
    plan = r.plan()
    if plan is None:
        return f"#{n}'s milestone M{m} can't count: PLAN.md isn't on main"
    done = plan_milestones(plan)
    if m not in done:
        return f"#{n}'s milestone M{m} isn't in PLAN.md on main"
    if done[m]:
        return f"#{n}'s milestone M{m} is marked done in PLAN.md"
    labels = {lb.get("name") for lb in issue.get("labels") or []}
    if "hold" in labels:
        return f"#{n} is labelled `hold`: the owner's veto"
    import watch
    still = [w for w in watch.waits_on(issue.get("body")) if r.state(w) != "closed"]
    if still:
        return f"#{n} waits on {', '.join(f'#{w}' for w in still)}, still open"
    if any((c.get("user") or {}).get("login") == owner for c in r.comments()):
        return (f"@{owner} commented on #{n}: that's a veto until @{owner} labels it `ready`")
    return None


def go_refusals(n: int, issue: dict | None, events: list[dict], owner: str,
                agents: set[str], r: GoReader, now: dt.datetime | None = None,
                repo: str | None = None) -> list[str]:
    """Reasons issue n isn't go for a [build], or [] if it is (GOV-0031).

    Go is the owner's `ready` (GOV-0006), or, for an implementation issue, its scope: opened
    by a swarm App or the owner, under an open Goal or Area the owner opened (at any depth
    of sub-issues), none of its blocked-by issues open, and no veto (a `hold` label or any
    owner comment; a closed issue is refused anyway). Until MILESTONE_UNTIL its GOV-0026
    milestone still counts as well. A gov:question is go only by `ready`. When the issue
    names a milestone, the first reason is why that failed; then why its scope did, if it
    has a parent at all."""
    refused = issue_refusals(n, issue, events, owner)
    if not refused or issue is None or "pull_request" in issue or issue.get("state") != "open":
        return refused
    labels = {lb.get("name") for lb in issue.get("labels") or []}
    if "gov:question" in labels:
        return refused
    reasons = []
    if milestone_of(issue.get("body")) is not None:
        if milestone_open(now):
            why = milestone_refusal(n, issue, owner, agents, r)
            if why is None:
                return []
            reasons.append(why)
        else:
            reasons.append(f"#{n}'s `**Milestone:**` line stopped counting at "
                           f"{MILESTONE_UNTIL:%Y-%m-%d %H:%M} UTC (GOV-0031)")
    scope = r.scope() if r is not None else None
    if scope is not None and scope["parents"]:
        why = scope_refusal(n, issue, scope, owner, agents, r.comments, repo=repo)
        if why is None:
            return []
        reasons.append(why)
    return [*reasons, *refused]


def gh_plan(repo: str) -> str | None:
    """PLAN.md on main, or None if it isn't there."""
    import base64
    try:
        d = dashboard().gh_json("api", f"repos/{repo}/contents/PLAN.md?ref=main")
    except RuntimeError as e:
        if "Not Found" in str(e) or "404" in str(e):
            return None
        raise
    return base64.b64decode(d["content"]).decode()


def gh_scopes(repo: str, numbers: list[int]) -> dict[int, dict | None]:
    """parse_scope() for each issue: one GraphQL query per 25 issues (ghql.batched)."""
    dashboard()
    import ghql
    return {n: parse_scope(x) for n, x in ghql.batched(repo, numbers, scope_field(), 25).items()}


def gh_go_reader(repo: str, n: int) -> GoReader:
    g = dashboard()
    return GoReader(plan=lambda: gh_plan(repo),
                    state=lambda w: (g.gh_json("api", f"repos/{repo}/issues/{w}") or {}).get("state"),
                    comments=lambda: g.gh_items(f"repos/{repo}/issues/{n}/comments?per_page=100"),
                    scope=lambda: gh_scopes(repo, [n]).get(n))


def holders(n: int, model: dict, started: list[Started], role: str | None = None,
            repo: str | None = None, model_repo: str | None = None) -> list[str]:
    """Live sessions already on issue n of repo (None: this repo): heartbeat sessions whose
    current issue is n, plus launcher sessions started on n that have no heartbeat yet. With
    role, only that role's (a call-in waits only for its own role, #520).

    A session holds repo plus number (#829): one on open-agentos/scratch#5 doesn't hold this
    repo's #5, nor the reverse. A heartbeat session's repo is its launcher entry's; one the
    launcher didn't start is on the repo the heartbeat model reads: model_repo (None: this
    repo), so swarm watch can pass another repo's heartbeat model (#912)."""
    names = {e.session_id: e.name for e in started}
    repos = {e.session_id: e.repo for e in started}
    seen = {s["session_id"] for s in model["sessions"]}
    want = same_repo_key(repo)
    out = [f"{names.get(s['session_id'], s['role'])} ({s['status']}, session {s['session_id']})"
           for s in model["sessions"] if s["status"] != "stopped" and s["issue"] == n
           and same_repo_key(repos.get(s["session_id"], model_repo)) == want and role in (None, s["role"])]
    out += [f"{e.name} (starting, session {e.session_id})"
            for e in started if e.issue == n and same_repo_key(e.repo) == want
            and e.session_id not in seen and role in (None, e.role)]
    return out


def same_repo_key(repo: str | None) -> str | None:
    """repo as holders() compares it: GitHub repo names ignore case."""
    return repo.lower() if repo else None


# `swarm launch --issue`: N, #N or owner/name#N (#829). A bare N or #N is this repo.
ISSUE_REF_RE = re.compile(r"(?:(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)?#)?(?P<n>[1-9][0-9]*)",
                          re.ASCII)


def parse_ref(ref: str, repo: str) -> tuple[str | None, int]:
    """(owner/name, N) for an issue ref, with None for this repo (`repo`), so a bare N, #N
    and this repo's own owner/name#N all come back the same. Raises ValueError if malformed."""
    m = ISSUE_REF_RE.fullmatch(ref.strip())
    if not m:
        raise ValueError(f"'{ref}' isn't an issue ref: use N, #N or owner/name#N")
    other = m["repo"]
    return (None if other is None or other.lower() == repo.lower() else other), int(m["n"])


def ref_text(n: int, repo: str | None) -> str:
    """#n for this repo (None), owner/name#n for another."""
    return f"{repo}#{n}" if repo else f"#{n}"


def launch_name(role: str, n: int, taken: set[str], pr: int | None = None,
                repo: str | None = None) -> str:
    """<role>-issue-<n>, or <role>-<name>-issue-<n> for another repo's issue (#829)."""
    where = f"{role}-{repo.split('/')[-1]}" if repo else role
    base = f"{where}-pr-{pr}" if pr else f"{where}-issue-{n}"
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
           owner: Callable[[], str] = owner_login, agents: Callable[[], set[str]] = agent_logins,
           get_reader: Callable[[str, int], GoReader] = gh_go_reader,
           issue_repo: str | None = None) -> int:
    """Start a session on issue n of issue_repo (None: this repo, `repo`). A session on
    another org repo's issue works in a worktree of that repo's clone, with its opener and
    our CLAUDE.md and role prompt naming the repo (#912, GOV-0036, GOV-0039)."""
    where = issue_repo or repo
    launcher.home_name = launcher.home_name or repo
    issue, events = get_issue(where, n)
    refused = go_refusals(n, issue, events, owner(), agents(), get_reader(where, n),
                          now=dt.datetime.fromtimestamp(launcher.clock(), dt.timezone.utc), repo=where)
    if refused:
        launcher.out(f"swarm launch: refused: {refused[0]}")
        return 1
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    live = launcher.live()
    ref = ref_text(n, issue_repo)
    # The heartbeat of the issue's repo: a session there tracks it in that repo (#912).
    taken = holders(n, get_heartbeat(where, idle_minutes, now), live, repo=issue_repo,
                    model_repo=issue_repo)
    if taken and not force:
        launcher.out(f"swarm launch: refused: {ref} already has a live session: {'; '.join(taken)}. "
                     f"Stop it (swarm stop <name>) or pass --force")
        return 1
    if taken:
        launcher.out(f"--force: starting another session on {ref} alongside {'; '.join(taken)}")
    entry = Started(name=launch_name(role, n, {e.name for e in live}, pr, issue_repo), role=role,
                    model=model, session_id=str(uuid.uuid4()), started=launcher.clock(), issue=n,
                    pr=pr, repo=issue_repo)
    return 0 if launcher.start(entry, live, dry_run) else 1


# ---------------------------------------------------------------- specs bridge (#955, #956, #937)

SPECS_GOAL_QUERY = (
    "query($owner: String!, $name: String!, $n: Int!) { repository(owner: $owner, name: $name) { "
    "issue(number: $n) { state body author { login __typename } issueType { name } "
    "userContentEdits(first: 100) { totalCount nodes { editor { login __typename } } } } } }")

# The Goal's sub-issues with the PRs that close them and their reviews (specs/push.py).
SPECS_SUB_ISSUES_QUERY = (
    "query($owner: String!, $name: String!, $n: Int!) { repository(owner: $owner, name: $name) { "
    "issue(number: $n) { subIssues(first: 100) { totalCount nodes { url state body "
    "labels(first: 50) { nodes { name } } "
    "closedByPullRequestsReferences(first: 10, includeClosedPrs: true) { totalCount nodes { "
    "number url state headRefOid reviews(last: 50) { nodes { author { login __typename } "
    "state commit { oid } } } } } } } } } }")
SPECS_GOALS_QUERY = (
    "query($owner: String!, $name: String!, $author: String!, $after: String) { "
    "repository(owner: $owner, name: $name) { issues(first: 100, after: $after, states: OPEN, "
    "filterBy: {createdBy: $author}) { nodes { number issueType { name } } "
    "pageInfo { hasNextPage endCursor } } } }")
SPECS_CLOSING_PRS_QUERY = (
    "query($owner: String!, $name: String!, $n: Int!) { repository(owner: $owner, name: $name) { "
    "issue(number: $n) { closedByPullRequestsReferences(first: 50, includeClosedPrs: false) { "
    "nodes { number state repository { nameWithOwner } } } } } }")


class GhSpecs:
    """specs/sync.py's GitHub, through the gh CLI as the session's App."""

    def goal(self, repo: str, n: int) -> dict | None:
        owner, name = repo.split("/", 1)
        d = dashboard().gh_json("api", "graphql", "-f", f"query={SPECS_GOAL_QUERY}",
                                "-f", f"owner={owner}", "-f", f"name={name}", "-F", f"n={n}")
        return (((d or {}).get("data") or {}).get("repository") or {}).get("issue")

    def open_issue(self, repo: str, title: str, body: str) -> dict:
        return dashboard().gh_json("api", "-X", "POST", f"repos/{repo}/issues",
                                   "-f", f"title={title}", "-f", f"body={body}")

    def add_sub_issue(self, repo: str, n: int, sub_issue_id: int) -> None:
        dashboard().gh_json("api", "-X", "POST", f"repos/{repo}/issues/{n}/sub_issues",
                            "-F", f"sub_issue_id={sub_issue_id}")

    # specs/drift.py's reads and writes (#956)

    def open_goals(self, repo: str, owner: str) -> list[int]:
        owner_name, name = repo.split("/", 1)
        out, after = [], None
        while True:
            args = ["api", "graphql", "-f", f"query={SPECS_GOALS_QUERY}", "-f", f"owner={owner_name}",
                    "-f", f"name={name}", "-f", f"author={owner}"]
            if after:
                args += ["-f", f"after={after}"]
            issues = dashboard().gh_json(*args)["data"]["repository"]["issues"]
            out += [i["number"] for i in issues["nodes"]
                    if (i.get("issueType") or {}).get("name") == "Goal"]
            if not issues["pageInfo"]["hasNextPage"]:
                return out
            after = issues["pageInfo"]["endCursor"]

    def sub_issues_rest(self, repo: str, n: int) -> list[dict]:
        return dashboard().gh_items(f"repos/{repo}/issues/{n}/sub_issues?per_page=100")

    def edit_body(self, repo: str, n: int, body: str) -> None:
        dashboard().gh_json("api", "-X", "PATCH", f"repos/{repo}/issues/{n}", "-f", f"body={body}")

    def comment(self, repo: str, n: int, body: str) -> None:
        dashboard().gh_json("api", "-X", "POST", f"repos/{repo}/issues/{n}/comments",
                            "-f", f"body={body}")

    def open_prs_closing(self, repo: str, n: int) -> list[tuple[str, int]]:
        owner, name = repo.split("/", 1)
        d = dashboard().gh_json("api", "graphql", "-f", f"query={SPECS_CLOSING_PRS_QUERY}",
                                "-f", f"owner={owner}", "-f", f"name={name}", "-F", f"n={n}")
        nodes = d["data"]["repository"]["issue"]["closedByPullRequestsReferences"]["nodes"]
        return [(p["repository"]["nameWithOwner"], p["number"]) for p in nodes
                if p.get("state") == "OPEN"]

    def add_blocked_by(self, repo: str, n: int, blocking_id: int) -> None:
        dashboard().gh_json("api", "-X", "POST", f"repos/{repo}/issues/{n}/dependencies/blocked_by",
                            "-F", f"issue_id={blocking_id}")

    # specs/push.py's read (#957)

    def sub_issues(self, repo: str, n: int) -> list:
        from specs import push
        owner, name = repo.split("/", 1)
        d = dashboard().gh_json("api", "graphql", "-f", f"query={SPECS_SUB_ISSUES_QUERY}",
                                "-f", f"owner={owner}", "-f", f"name={name}", "-F", f"n={n}")
        return push.items_from_graphql(
            (((d or {}).get("data") or {}).get("repository") or {}).get("issue"))


def _specs_backend(launcher: Launcher, cmd: str, repo: str, goal: str,
                   manifest_path: Path | str):
    """((owner/name, N), [specs] config, its SpecSource) for `swarm specs <cmd>`, or None
    after saying why."""
    from specs import config as specs_config
    from specs.source import SchemaError
    try:
        goal_repo, n = parse_ref(goal, repo)
        cfg = specs_config.load(manifest_path)
        if cfg is None:
            launcher.out(f"swarm specs {cmd}: {manifest_path} has no [specs] table")
            return None
        return (goal_repo or repo, n), cfg, specs_config.source(cfg)
    except (ValueError, SchemaError) as e:   # SpecsConfigError is a ValueError
        launcher.out(f"swarm specs {cmd}: {e}")
        return None


def specs_pull(launcher: Launcher, repo: str, goal: str, manifest_path: Path | str,
               dry_run: bool = False, gh=None, owner: Callable[[], str] = owner_login) -> int:
    """`swarm specs pull <goal>`: the backend from swarm.toml's [specs] (#952), then sync.pull.
    A fake backend's state is saved back to its fixture after a real run, so the next manual
    run carries on from it, even if the run stopped part-way."""
    from specs import sync
    from specs.source import SchemaError
    loaded = _specs_backend(launcher, "pull", repo, goal, manifest_path)
    if loaded is None:
        return 1
    goal_ref, cfg, source = loaded
    try:
        sync.pull(goal_ref, source, gh or GhSpecs(), dry_run=dry_run,
                  owner=owner(), backend=cfg.backend, out=launcher.out)
    except sync.Refused as e:
        launcher.out(f"swarm specs pull: refused: {e}")
        return 1
    except SchemaError as e:
        launcher.out(f"swarm specs pull: stopped, nothing written: the {cfg.backend} source's "
                     f"layout doesn't match #937 §6: {e}")
        return 1
    finally:
        if not dry_run and getattr(source, "writes", None) and cfg.fixture:
            source.dump(cfg.fixture)
    return 0


def specs_push(launcher: Launcher, repo: str, goal: str, manifest_path: Path | str,
               what_shipped=(), dry_run: bool = False, model: str | None = None, gh=None,
               owner: Callable[[], str] = owner_login) -> int:
    """`swarm specs push <goal>`: the backend from swarm.toml's [specs] (#952), then push.push.
    The delivery comment ends `-- lead (<model>)`: --model, else the planner's model in the
    manifest. A fake backend's state is saved back to its fixture after a real run."""
    from specs import push, sync
    from specs.source import SchemaError
    try:
        paragraphs = push.parse_what_shipped(what_shipped)
        model = model_for("planner", model, str(manifest_path))
    except (ValueError, LookupError, manifest.ManifestError) as e:
        launcher.out(f"swarm specs push: {e}")
        return 1
    loaded = _specs_backend(launcher, "push", repo, goal, manifest_path)
    if loaded is None:
        return 1
    goal_ref, cfg, source = loaded
    try:
        push.push(goal_ref, source, gh or GhSpecs(), paragraphs, dry_run, owner=owner(),
                  model=model, backend=cfg.backend, out=launcher.out)
    except sync.Refused as e:
        launcher.out(f"swarm specs push: refused: {e}")
        return 1
    except SchemaError as e:
        launcher.out(f"swarm specs push: stopped, nothing written: the {cfg.backend} source's "
                     f"layout doesn't match #937 §6: {e}")
        return 1
    finally:
        if not dry_run and getattr(source, "writes", None) and cfg.fixture:
            source.dump(cfg.fixture)
    return 0


def specs_diff(launcher: Launcher, repo: str, goal: str | None, manifest_path: Path | str,
               as_json: bool = False, decision: tuple[str, str] | None = None, gh=None,
               owner: Callable[[], str] = owner_login) -> int:
    """`swarm specs diff [<goal>]` and its decisions (#956): the backend from swarm.toml's
    [specs] (#952), then drift.diff, or drift.decide for `decision` ((choice, FEAT-n))."""
    from specs import config as specs_config, drift, sync
    from specs.source import SchemaError
    try:
        target = None
        if goal is not None:
            goal_repo, n = parse_ref(goal, repo)
            target = (goal_repo or repo, n)
        if decision and target is None:
            launcher.out(f"swarm specs diff: --{decision[0]} needs the Goal")
            return 2
        cfg = specs_config.load(manifest_path)
        if cfg is None:
            launcher.out(f"swarm specs diff: {manifest_path} has no [specs] table")
            return 1
        source = specs_config.source(cfg)
    except (ValueError, SchemaError) as e:   # SpecsConfigError is a ValueError
        launcher.out(f"swarm specs diff: {e}")
        return 1
    gh = gh or GhSpecs()
    try:
        if decision:
            drift.decide(target, decision[1], decision[0], source, gh, owner=owner(),
                         backend=cfg.backend, out=launcher.out)
        else:
            drift.diff(target, source, gh, owner=owner(), repo=repo, backend=cfg.backend,
                       as_json=as_json, out=launcher.out)
    except (sync.Refused, drift.Undecidable) as e:
        launcher.out(f"swarm specs diff: refused: {e}")
        return 1
    except SchemaError as e:
        launcher.out(f"swarm specs diff: stopped, nothing written: the {cfg.backend} source's "
                     f"layout doesn't match #937 §6: {e}")
        return 1
    return 0


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
    p_ls.add_argument("--all", action="store_true", dest="show_all",
                      help="also list sessions that never acted, marked (#454)")
    p_ls.add_argument("--manifest", default=str(manifest.DEFAULT_PATH), help="default: swarm.toml")
    p_stop = sub.add_parser("stop", help="end one session the launcher started")
    p_stop.add_argument("session", help="its name (builder-1) or session id")
    p_inbox = sub.add_parser("inbox", help="what's waiting on the owner, most urgent first")
    p_inbox.add_argument("--repo", help="owner/name (default: this checkout's origin)")
    p_inbox.add_argument("--idle-minutes", type=int, default=15)
    p_inbox.add_argument("--manifest", default=str(manifest.DEFAULT_PATH), help="default: swarm.toml")
    p_cost = sub.add_parser("cost", help="cost per PR of the runs swarm watch recorded (local only)")
    p_cost.add_argument("--repo", help="owner/name (default: this checkout's origin)")
    p_merges = sub.add_parser("merges", help="this week's merges by the merger and by the owner, and reverts")
    p_merges.add_argument("--last", action="store_true", help="last week (Monday to Sunday, UTC) instead")
    p_merges.add_argument("--repo", help="owner/name (default: this checkout's origin)")
    p_status = sub.add_parser("status", help="swarm watch's state with cost, from local files only")
    p_status.add_argument("--manifest", default=str(manifest.DEFAULT_PATH), help="default: swarm.toml")
    p_daily = sub.add_parser("daily", help="the last 10 working days' daily reports and who started each")
    p_daily.add_argument("--repo", help="owner/name (default: this checkout's origin)")
    p_daily.add_argument("--manifest", default=str(manifest.DEFAULT_PATH), help="default: swarm.toml")
    p_acts = sub.add_parser("acts", help="the owner's acts per working day, with count and kind (no limit)")
    p_acts.add_argument("--day", type=dt.date.fromisoformat, help="YYYY-MM-DD (default: the last two weeks' working days)")
    p_acts.add_argument("--json", action="store_true", dest="as_json", help="the same per-day list as JSON")
    p_acts.add_argument("--repo", help="owner/name (default: this checkout's origin)")
    p_acts.add_argument("--manifest", default=str(manifest.DEFAULT_PATH), help="default: swarm.toml")
    p_trouble = sub.add_parser("trouble", help="per Goal and Area: progress, stuck work, what waits on "
                                                "the owner, authority used (#803)")
    p_trouble.add_argument("--json", action="store_true", dest="as_json", help="the report as JSON")
    p_trouble.add_argument("--hours", type=int, default=24,
                           help="window for what agents did on the owner's authority (default: 24)")
    p_trouble.add_argument("--repo", help="owner/name (default: this checkout's origin)")
    p_trouble.add_argument("--manifest", default=str(manifest.DEFAULT_PATH), help="default: swarm.toml")
    p_launch = sub.add_parser("launch", help="start one session on a given issue")
    p_launch.add_argument("role")
    p_launch.add_argument("--issue", required=True,
                          help="the issue to work on: N or #N (this repo), or owner/name#N")
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
    p_watch.add_argument("--serve", action="store_true",
                         help="also check on each webhook nudge from `swarm webhooks` (engine host, #660)")
    p_watch.add_argument("--container", metavar="IMAGE",
                         help="start each run in its own container from IMAGE, pinned by digest "
                              "(engine host, #661)")
    p_hooks = sub.add_parser("webhooks", help="receive GitHub webhooks and nudge the watcher (engine host)")
    p_hooks.add_argument("--host", default="127.0.0.1", help="default: 127.0.0.1 (Caddy in front)")
    p_hooks.add_argument("--port", type=int, default=8081)
    p_desk = sub.add_parser("desk", help="serve the Desk read-only, rebuilt on each webhook nudge (engine host)")
    p_desk.add_argument("--host", default="127.0.0.1", help="default: 127.0.0.1 (Caddy in front)")
    p_desk.add_argument("--port", type=int, default=8080)
    p_desk.add_argument("--repo", help="owner/name (default: this checkout's origin)")
    sub.add_parser("spent", help="today's and this month's run spend, and Spent per Mission, Goal and Area (#662)")
    p_specs = sub.add_parser("specs", help="the specs bridge: specs in a source ship through the swarm (#937)")
    specs_sub = p_specs.add_subparsers(dest="specs_cmd", required=True)
    p_pull = specs_sub.add_parser("pull", help="open a sub-issue under the Goal for each Ready feature "
                                               "of its linked initiative (#955)")
    p_pull.add_argument("goal", help="the Goal: N or #N (this repo), or owner/name#N")
    p_pull.add_argument("--dry-run", action="store_true",
                        help="print what would happen; write nothing to GitHub or the source")
    p_pull.add_argument("--manifest", default=str(manifest.DEFAULT_PATH), help="default: swarm.toml")
    p_pull.add_argument("--repo", help="owner/name (default: this checkout's origin)")
    p_push = specs_sub.add_parser("push", help="write each linked feature's status, links and "
                                               "delivery comments back to the source (#957)")
    p_push.add_argument("goal", help="the Goal: N or #N (this repo), or owner/name#N")
    p_push.add_argument("--what-shipped", action="append", default=[], metavar="FEAT-n=TEXT",
                        help="the lead's one-paragraph 'what shipped' for a merged feature "
                             "(repeatable); a merge without one gets no comment yet")
    p_push.add_argument("--model", help="the lead's model, for the comment's '-- lead (<model>)' "
                                        "(default: the planner's in the manifest)")
    p_push.add_argument("--dry-run", action="store_true",
                        help="print what would be written; write nothing to the source")
    p_push.add_argument("--manifest", default=str(manifest.DEFAULT_PATH), help="default: swarm.toml")
    p_push.add_argument("--repo", help="owner/name (default: this checkout's origin)")
    p_diff = specs_sub.add_parser("diff", help="specs edited since their snapshot was pulled, and "
                                               "the lead's decision on one (#956)")
    p_diff.add_argument("goal", nargs="?", help="the Goal: N or #N (this repo), or owner/name#N; "
                                                "default: every open Goal with a Spec source line")
    p_diff.add_argument("--json", action="store_true", help="print the drift as JSON")
    decide = p_diff.add_mutually_exclusive_group()
    for choice, what in (("adopt", "replace the snapshot (open issue) or open a new sub-issue "
                                   "(closed issue)"),
                         ("defer", "open a follow-up sub-issue that waits on the issue"),
                         ("ask", "print the ask for the lead's report; write nothing on GitHub")):
        decide.add_argument(f"--{choice}", metavar="FEAT-n", help=what)
    p_diff.add_argument("--manifest", default=str(manifest.DEFAULT_PATH), help="default: swarm.toml")
    p_diff.add_argument("--repo", help="owner/name (default: this checkout's origin)")
    p_backup = sub.add_parser("backup", help="copy swarm.db consistently, for the nightly timer")
    p_backup.add_argument("--out", help=f"default: backups/swarm-<UTC time>.db, keeping the newest "
                                        f"{statedb.KEEP_BACKUPS}")
    args = ap.parse_args(argv)

    launcher = launcher or Launcher(home())
    if args.cmd == "backup":
        try:
            out = statedb.backup(launcher.dir, Path(args.out) if args.out else None)
        except (RuntimeError, OSError, sqlite3.Error) as e:
            launcher.out(f"swarm backup: {e}")
            return 1
        launcher.out(f"swarm backup: wrote {out}")
        return 0
    if args.cmd == "spent":
        import ledger
        try:
            rows = ledger.rows(launcher.dir)
        except (OSError, ValueError, sqlite3.Error) as e:
            launcher.out(f"swarm spent: can't read the runs ledger: {e}")
            return 1
        now = dt.datetime.now(dt.timezone.utc)
        launcher.out(ledger.spent_text(ledger.totals(rows, now), dashboard().default_repo() or "", now))
        return 0
    if args.cmd == "webhooks":
        import webhooks
        return webhooks.serve(launcher.dir, os.environ.get("WEBHOOK_SECRET", ""), args.host,
                              args.port, out=launcher.out)
    if args.cmd == "desk":
        import desk
        return desk.serve(launcher.dir, args.host, args.port, args.repo, out=launcher.out)
    if args.cmd == "watch" and not args.dry_run and args.interval is not None:
        launcher.out("swarm watch: --interval works only with --dry-run; the interval for real "
                     "starts is interval_minutes in swarm.toml's [watch] table (GOV-0010)")
        return 2
    if args.cmd == "watch" and args.container:
        try:
            launcher.use_container(args.container)
        except ValueError as e:
            launcher.out(f"swarm watch: {e}")
            return 2
    repo = None
    if args.cmd in ("ls", "launch", "inbox", "watch", "cost", "merges", "daily", "acts", "trouble", "specs"):
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
            try:
                issue_repo, n = parse_ref(args.issue, repo)
            except ValueError as e:
                launcher.out(f"swarm launch: {e}")
                return 1
            return launch(launcher, args.role, n, model, repo=repo, force=args.force,
                          dry_run=args.dry_run, idle_minutes=args.idle_minutes, pr=args.pr,
                          issue_repo=issue_repo)
        if args.cmd == "specs" and args.specs_cmd == "push":
            return specs_push(launcher, repo, args.goal, args.manifest, args.what_shipped,
                              args.dry_run, args.model)
        if args.cmd == "specs" and args.specs_cmd == "diff":
            decision = next(((c, getattr(args, c)) for c in ("adopt", "defer", "ask")
                             if getattr(args, c)), None)
            return specs_diff(launcher, repo, args.goal, args.manifest, args.json, decision)
        if args.cmd == "specs":
            return specs_pull(launcher, repo, args.goal, args.manifest, args.dry_run)
        if args.cmd == "up":
            try:
                sessions = manifest.load(args.manifest)
            except manifest.ManifestError as e:
                launcher.out(f"swarm up: {e}")
                return 1
            return launcher.up(sessions, dry_run=args.dry_run)
        if args.cmd == "ls":
            return ls(launcher, repo, args.idle_minutes, args.show_all, args.manifest)
        if args.cmd == "inbox":
            return inbox(launcher, repo, args.idle_minutes, args.manifest)
        if args.cmd == "cost":
            return cost(launcher, repo)
        if args.cmd == "merges":
            return merges(launcher, repo, args.last)
        if args.cmd == "status":
            return status(launcher, args.manifest)
        if args.cmd == "daily":
            return daily(launcher, repo, args.manifest)
        if args.cmd == "acts":
            return owner_acts(launcher, repo, args.manifest, args.day, args.as_json)
        if args.cmd == "trouble":
            return trouble(launcher, repo, args.manifest, args.hours, args.as_json)
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
                            manifest_path=Path(args.manifest), roles_from=launcher.root,
                            list_issues=watch.owner_issues, edit_issue=watch.edit_body, serve=args.serve)
            interval = args.interval or (limits.interval_minutes if limits else watch.DEFAULT_INTERVAL)
            return w.run(interval)
        return launcher.stop(args.session)
    except RuntimeError as e:   # GitHub unreachable, or an unreadable state file
        launcher.out(f"swarm {args.cmd}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
