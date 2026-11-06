#!/usr/bin/env python3
"""Heartbeat hook for productswarm agent sessions.

Claude Code runs this on session and tool events (see heartbeat/install.py):

    hook.py <SessionStart|UserPromptSubmit|PostToolUse|Stop|SessionEnd>   (hook payload on stdin)

Agents or the owner can also record a change by hand:

    hook.py emit working_on --issue 3
    hook.py emit blocked --gov-question 15 [--issue 3]
    hook.py sweep               record `stopped` for this role's vanished sessions (below)

What is captured follows GOV-0002 and where it goes follows GOV-0003; the event
format is heartbeat/SCHEMA.md. Every event is appended to the local spool. Every
event except `prompt` is queued for the session's GitHub tracking issue and posted
in batches by a detached `hook.py flush <session_id>` process, via `gh`, which in a
swarm session is ops/shims/gh acting as the role's App.

The hook does nothing unless SWARM_ROLE is set (i.e. outside ops/swarm-session).
A session whose window is closed gets SIGHUP or is killed, so SessionEnd never runs
and its tracking issue would stay open, idle, forever (#75). So each new session sweeps
this machine's other sessions of the same role: one that has vanished gets the
`stopped` event it never posted, and its issue is closed. Same role only, because the
dashboard accepts a session's events only from that role's App, which is who we act as.

It never prints to stdout (UserPromptSubmit and SessionStart stdout would become
model context) and always exits 0, so a heartbeat failure never disturbs a session.
Errors go to ~/.productswarm/heartbeat.log.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import json
import os
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path

SCHEMA_VERSION = 1
PROMPT_MAX = 2000                  # GOV-0002
HEARTBEAT_EVERY = 300              # seconds between liveness events while working
FLUSH_EVERY = 300                  # post queued non-state-change events at least this often
MAX_EVENTS_PER_COMMENT = 50
STALE_AFTER = 6 * 3600             # a session we can't see in `ps` counts as gone after this silence
STATE_CHANGES = {"session_started", "working_on", "pr_opened", "blocked", "stopped"}
MARKER = "<!-- productswarm-heartbeat schema_version={v} session_id={sid} -->"

SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
ROLE_RE = re.compile(r"^[a-z][a-z0-9-]*$")
TOOL_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
REPO_RE = re.compile(r"github\.com[:/]([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?$")
ISSUE_IN_PROMPT_RE = re.compile(r"\bissue\s+#?(\d+)\b", re.IGNORECASE)

# GOV-0002 redaction list, applied to prompt text before it is written anywhere.
REDACTIONS = [
    (re.compile(r"-----BEGIN [A-Z0-9 ]+-----.*?(?:-----END [A-Z0-9 ]+-----|\Z)", re.DOTALL), "[REDACTED PEM]"),
    (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{16,})"), "[REDACTED]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"), "[REDACTED]"),
    (re.compile(r"\b([A-Za-z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)[A-Za-z0-9_]*)(\s*=\s*)(\"[^\"]*\"|'[^']*'|\S+)",
                re.IGNORECASE), r"\1\2[REDACTED]"),
]


def redact(text: str) -> str:
    for pattern, repl in REDACTIONS:
        text = pattern.sub(repl, text)
    return text


def clean_prompt(text: str) -> str:
    """Redact, then truncate (GOV-0002, in that order)."""
    return redact(text)[:PROMPT_MAX]


# ---------------------------------------------------------------- paths and state

def home() -> Path:
    return Path(os.environ.get("PRODUCTSWARM_HOME", "~/.productswarm")).expanduser()


def path(kind: str, sid: str, suffix: str = ".jsonl") -> Path:
    d = home() / kind
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    return d / f"{sid}{suffix}"


def log(msg: str) -> None:
    try:
        home().mkdir(parents=True, exist_ok=True, mode=0o700)
        with open(home() / "heartbeat.log", "a") as f:
            f.write(f"{now_iso()} {msg}\n")
    except OSError:
        pass


@contextlib.contextmanager
def locked(sid: str, name: str = "state", blocking: bool = True):
    with open(path("state", sid, f".{name}.lock"), "w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError:
            yield False
            return
        yield True


def load_state(sid: str) -> dict | None:
    p = path("state", sid, ".json")
    return json.loads(p.read_text()) if p.exists() else None


def save_state(state: dict) -> None:
    p = path("state", state["session_id"], ".json")
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(p)


def append_line(p: Path, obj: dict) -> None:
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a") as f:
        f.write(json.dumps(obj, separators=(",", ":")) + "\n")


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- session facts

def repo_for(cwd: str) -> str | None:
    try:
        url = subprocess.run(["git", "-C", cwd, "remote", "get-url", "origin"],
                             capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    m = REPO_RE.search(url)
    return m.group(1) if m else None


def read_usage(state: dict, transcript: str | None) -> None:
    """Fold new transcript lines into cumulative token counts.

    Reads the transcript locally; only the four counts and the model id are kept
    (allowed by GOV-0002). Streaming writes several lines per message id, each with
    that message's usage so far, so a repeat of the last id replaces its usage.
    """
    if not transcript or not os.path.exists(transcript):
        return
    with open(transcript, "rb") as f:
        f.seek(state.get("tx_offset", 0))
        data = f.read()
    end = data.rfind(b"\n") + 1          # only complete lines
    tokens = state["tokens"]
    for raw in data[:end].splitlines():
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        msg = entry.get("message") if isinstance(entry, dict) else None
        if entry.get("type") != "assistant" or not isinstance(msg, dict):
            continue
        if isinstance(msg.get("model"), str) and msg["model"] and not msg["model"].startswith("<"):
            state["model"] = msg["model"]
        u = msg.get("usage")
        if not isinstance(u, dict):
            continue
        usage = {
            "input": int(u.get("input_tokens") or 0),
            "output": int(u.get("output_tokens") or 0),
            "cache_read": int(u.get("cache_read_input_tokens") or 0),
            "cache_creation": int(u.get("cache_creation_input_tokens") or 0),
        }
        if msg.get("id") and msg.get("id") == state.get("last_msg_id"):
            for k, v in state["last_msg_usage"].items():
                tokens[k] -= v
        for k, v in usage.items():
            tokens[k] += v
        state["last_msg_id"], state["last_msg_usage"] = msg.get("id"), usage
    state["tx_offset"] = state.get("tx_offset", 0) + end


def new_state(sid: str, payload: dict, role: str) -> dict:
    cwd = payload.get("cwd") or os.getcwd()
    return {
        "session_id": sid,
        "role": role,
        "repo": repo_for(cwd),
        "model": payload.get("model") if isinstance(payload.get("model"), str) and payload.get("model")
                 else os.environ.get("ANTHROPIC_MODEL") or "unknown",
        "tracking_issue": None,
        "current_issue": None,
        "tools": [],
        "tokens": {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0},
        "tx_offset": 0,
        "last_event_at": 0,
        "last_flush_at": 0,
    }


# ---------------------------------------------------------------- events

def record(state: dict, event: str, transcript: str | None = None, **fields) -> dict:
    """Build an event, append it to the spool, and queue its remote copy."""
    read_usage(state, transcript)
    ev = {
        "schema_version": SCHEMA_VERSION,
        "ts": now_iso(),
        "session_id": state["session_id"],
        "repo": state["repo"] or "unknown/unknown",
        "role": state["role"],
        "model": state["model"],
        "event": event,
    }
    if state.get("current_issue") and "issue" not in fields:
        fields["issue"] = state["current_issue"]
    ev.update({k: v for k, v in fields.items() if v is not None})
    ev["cost_usd"] = None                      # estimation is #6
    ev["token_counts"] = dict(state["tokens"])
    if state["tools"]:
        ev["tools"] = state["tools"]
        state["tools"] = []
    append_line(path("events", state["session_id"]), ev)
    if state["repo"]:
        remote = {k: v for k, v in ev.items() if k != "prompt"}   # prompt stays local (GOV-0002)
        append_line(path("outbox", state["session_id"]), remote)
    state["last_event_at"] = time.time()
    return ev


def should_flush(state: dict, events: list[dict]) -> bool:
    if not state["repo"] or not events:
        return False
    return any(e["event"] in STATE_CHANGES for e in events) or time.time() - state["last_flush_at"] >= FLUSH_EVERY


def spawn_flush(state: dict) -> None:
    state["last_flush_at"] = time.time()
    spawn("flush", state["session_id"])


def spawn(*args: str) -> None:
    """Run `hook.py <args>` detached, so the session never waits on it."""
    if os.environ.get("HEARTBEAT_SYNC_FLUSH"):       # tests
        main(list(args))
        return
    subprocess.Popen([sys.executable, "-I", os.path.abspath(__file__), *args],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)


def gh(*args: str, stdin: str | None = None) -> str:
    r = subprocess.run(["gh", *args], input=stdin or "", capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"gh {args[0]} {args[1]} failed: {r.stderr.strip()[:300]}")
    return r.stdout


def number_from_url(text: str, repo: str, kind: str) -> int | None:
    m = re.search(rf"https://github\.com/{re.escape(repo)}/{kind}/(\d+)", text or "")
    return int(m.group(1)) if m else None


def signature(state: dict) -> str:
    return f"-- {state['role']} ({state['model']})"


def ensure_tracking_issue(sid: str) -> dict:
    with locked(sid):
        state = load_state(sid)
        if state["tracking_issue"]:
            return state
        body = (MARKER.format(v=SCHEMA_VERSION, sid=sid) + "\n"
                f"Heartbeat events for one {state['role']} session, posted automatically. "
                "See heartbeat/SCHEMA.md.\n\n" + signature(state) + "\n")
        out = gh("issue", "create", "--repo", state["repo"],
                 "--title", f"[heartbeat] {state['role']} {sid}", "--body-file", "-", stdin=body)
        state["tracking_issue"] = number_from_url(out, state["repo"], "issues")
        if not state["tracking_issue"]:
            raise RuntimeError(f"could not read tracking issue number from: {out.strip()[:200]}")
        save_state(state)
        return state


def mentions(state: dict, chunk: list[str]) -> tuple[list[str], list[int]]:
    """Prose lines naming the issues in a chunk's `working_on` / `pr_opened` events,
    and the issues whose `working_on` they name for the first time this session.

    GitHub turns each `#N` into a "mentioned this" reference on issue N's timeline, so
    the issue shows the session working on it (#453). `working_on` is named once per
    issue per session (`state["mentioned"]`); readers ignore text outside the fence.
    """
    seen, new, out = set(state.get("mentioned") or []), [], []
    for line in chunk:
        ev = json.loads(line)
        issue = ev.get("issue")
        if not isinstance(issue, int):
            continue
        if ev.get("event") == "working_on" and issue not in seen:
            seen.add(issue)
            new.append(issue)
            out.append(f"{state['role']} session working on #{issue}")
        elif ev.get("event") == "pr_opened" and isinstance(ev.get("pr"), int):
            out.append(f"{state['role']} opened PR #{ev['pr']} for #{issue}")
    return list(dict.fromkeys(out)), new


def mark_mentioned(sid: str, issues: list[int]) -> None:
    with locked(sid):
        state = load_state(sid)
        state["mentioned"] = list(dict.fromkeys((state.get("mentioned") or []) + issues))
        save_state(state)


def flush(sid: str) -> None:
    """Post queued events to the tracking issue. One flusher per session at a time."""
    with locked(sid, "flush", blocking=False) as got:
        if not got:
            return                                   # another flusher is running; it loops
        outbox, sending = path("outbox", sid), path("outbox", sid, ".sending.jsonl")
        while True:
            with locked(sid):
                if not sending.exists():
                    if not outbox.exists() or outbox.stat().st_size == 0:
                        return
                    outbox.replace(sending)          # appenders start a fresh outbox
            lines = [l for l in sending.read_text().splitlines() if l.strip()]
            existed = bool((load_state(sid) or {}).get("tracking_issue"))
            state = ensure_tracking_issue(sid)
            for i in range(0, len(lines), MAX_EVENTS_PER_COMMENT):
                chunk = lines[i:i + MAX_EVENTS_PER_COMMENT]
                said, new = mentions(load_state(sid), chunk)
                prose = "".join(l + "\n" for l in said)
                body = (prose + ("\n" if prose else "") + "```jsonl\n" + "\n".join(chunk) + "\n```\n\n"
                        + signature(state) + "\n")
                gh("issue", "comment", str(state["tracking_issue"]), "--repo", state["repo"],
                   "--body-file", "-", stdin=body)
                if new:
                    mark_mentioned(sid, new)
                remaining = lines[i + len(chunk):]
                sending.write_text("".join(l + "\n" for l in remaining))   # don't repost on retry
            sending.unlink()
            # Keep the issue open exactly while the session is live: close after
            # `stopped`, reopen if a resumed session posts `session_started` again.
            kinds = [json.loads(l).get("event") for l in lines]
            if kinds and kinds[-1] == "stopped":
                gh("issue", "close", str(state["tracking_issue"]), "--repo", state["repo"])
            elif existed and "session_started" in kinds:
                gh("issue", "reopen", str(state["tracking_issue"]), "--repo", state["repo"])


# ---------------------------------------------------------------- vanished sessions (#75)

def running_commands() -> str | None:
    """Every process's command line, or None if `ps` can't be run."""
    try:
        r = subprocess.run(["ps", "-axww", "-o", "command="], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def vanished(state: dict, procs: str, now: float) -> bool:
    """Whether a session that never posted `stopped` is gone.

    Alive while any process's command line names its session id: launcher sessions
    (`--session-id`) and resumed ones (`--resume`) always do. Otherwise it is gone if
    the launcher started it (its pid file is there, so it should have been visible),
    or if it has been silent for STALE_AFTER. A wrong call is undone by the session's
    next event: a stopped session that does anything posts `session_started` and its
    issue reopens."""
    sid = state["session_id"]
    if sid in procs:
        return False
    if (home() / "launcher" / f"{sid}.pid").exists():
        return True
    return now - state.get("last_event_at", 0) >= STALE_AFTER


def sweep(role: str, keep: str | None = None) -> list[str]:
    """Record `stopped` for this role's sessions on this machine that have vanished.

    Their queued events and the `stopped` go out through the normal flush, which
    closes each tracking issue. Returns the swept session ids."""
    procs = running_commands()
    if procs is None:
        log("sweep: can't run ps; skipped")
        return []
    swept = []
    for p in sorted((home() / "state").glob("*.json")):
        sid = p.stem
        if sid == keep or not SESSION_ID_RE.match(sid):
            continue
        with locked(sid):
            state = load_state(sid)
            if (not state or state.get("stopped") or state.get("role") != role
                    or not vanished(state, procs, time.time())):
                continue
            state["stopped"] = True
            record(state, "stopped")
            state["last_flush_at"] = time.time()
            save_state(state)
        swept.append(sid)
        if state["repo"]:
            spawn_flush(state)
    if swept:
        log(f"sweep: recorded `stopped` for vanished {role} sessions {', '.join(swept)}")
    return swept


# ---------------------------------------------------------------- hook handlers

def detect_from_bash(state: dict, payload: dict) -> list[tuple[str, dict]]:
    """Derive pr_opened / blocked from a Bash call.

    The command and its output are read here, in memory, only to find PR and issue
    numbers; neither is stored or sent (GOV-0002 allows only the numbers).
    """
    if payload.get("tool_name") != "Bash" or not state["repo"]:
        return []
    cmd = str((payload.get("tool_input") or {}).get("command") or "")
    resp = payload.get("tool_response")
    out = json.dumps(resp) if not isinstance(resp, str) else resp
    out = out.replace("\\/", "/")
    found = []
    if re.search(r"\bgh\s+pr\s+create\b", cmd):
        pr = number_from_url(out, state["repo"], "pull")
        if pr:
            issue = state.get("current_issue")
            if not issue:
                with contextlib.suppress(Exception):
                    n = gh("pr", "view", str(pr), "--repo", state["repo"], "--json", "closingIssuesReferences",
                           "-q", ".closingIssuesReferences[0].number").strip()
                    issue = int(n) if n.isdigit() else None
            found.append(("pr_opened", {"pr": pr, "issue": issue}) if issue else ("heartbeat", {"pr": pr}))
    if re.search(r"\bgh\s+issue\s+create\b", cmd) and "gov:blocking" in cmd:
        q = number_from_url(out, state["repo"], "issues")
        if q:
            found.append(("blocked", {"gov_question": q}))
    return found


def handle(hook: str, payload: dict, role: str) -> None:
    sid = str(payload.get("session_id") or "")
    if not SESSION_ID_RE.match(sid):
        return
    transcript = payload.get("transcript_path")
    with locked(sid):
        state = load_state(sid)
        events = []
        if state is None:
            state = new_state(sid, payload, role)
            events.append(record(state, "session_started", transcript))
        elif state.get("stopped") and hook != "SessionEnd":          # resumed after it ended
            state["stopped"] = False
            events.append(record(state, "session_started", transcript))
        if hook == "UserPromptSubmit":
            prompt = payload.get("prompt")
            events.append(record(state, "prompt_submitted", transcript,
                                 prompt=clean_prompt(prompt) if isinstance(prompt, str) else None))
            nums = {int(n) for n in ISSUE_IN_PROMPT_RE.findall(prompt or "")}
            if len(nums) == 1 and (n := nums.pop()) != state.get("current_issue"):
                state["current_issue"] = n
                events.append(record(state, "working_on", transcript, issue=n))
        elif hook == "PostToolUse":
            name = payload.get("tool_name")
            if isinstance(name, str) and TOOL_RE.match(name) and name not in state["tools"]:
                state["tools"].append(name)
            for event, fields in detect_from_bash(state, payload):
                if event == "blocked":
                    fields.setdefault("issue", state.get("current_issue"))
                events.append(record(state, event, transcript, **fields))
        elif hook == "SessionEnd":
            state["stopped"] = True
            events.append(record(state, "stopped", transcript))
        if hook in ("PostToolUse", "Stop") and not events and time.time() - state["last_event_at"] >= HEARTBEAT_EVERY:
            events.append(record(state, "heartbeat", transcript))
        flush_now = should_flush(state, events)
        if flush_now:
            state["last_flush_at"] = time.time()
        save_state(state)
    if flush_now:
        spawn_flush(state)
    if hook == "SessionStart":
        spawn("sweep", sid)


def latest_session(role: str) -> str | None:
    """The session `emit` applies to: $HEARTBEAT_SESSION_ID, else this role's most recent live session."""
    sid = os.environ.get("HEARTBEAT_SESSION_ID")
    if sid:
        return sid
    states = sorted((home() / "state").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in states:
        s = json.loads(p.read_text())
        if s.get("role") == role and not s.get("stopped"):
            return s["session_id"]
    return None


def emit(argv: list[str], role: str) -> int:
    ap = argparse.ArgumentParser(prog="hook.py emit")
    ap.add_argument("event", choices=["working_on", "blocked", "heartbeat"])
    ap.add_argument("--issue", type=int)
    ap.add_argument("--pr", type=int)
    ap.add_argument("--gov-question", type=int)
    a = ap.parse_args(argv)
    if a.event == "working_on" and not a.issue:
        ap.error("working_on needs --issue")
    if a.event == "blocked" and not a.gov_question:
        ap.error("blocked needs --gov-question")
    sid = latest_session(role)
    if not sid or not SESSION_ID_RE.match(sid):
        print("heartbeat: no live session found for this role", file=sys.stderr)
        return 1
    with locked(sid):
        state = load_state(sid)
        if state is None:
            print(f"heartbeat: no state for session {sid}", file=sys.stderr)
            return 1
        if a.issue:
            state["current_issue"] = a.issue
        ev = record(state, a.event, issue=a.issue, pr=a.pr, gov_question=a.gov_question)
        state["last_flush_at"] = time.time()
        save_state(state)
    spawn_flush(state)
    print(json.dumps(ev))
    return 0


def main(argv: list[str]) -> int:
    role = os.environ.get("SWARM_ROLE", "")
    if not ROLE_RE.match(role):
        return 0                                     # not a swarm session: do nothing
    try:
        if argv[:1] == ["emit"]:
            return emit(argv[1:], role)
        if argv[:1] == ["flush"] and len(argv) == 2 and SESSION_ID_RE.match(argv[1]):
            flush(argv[1])
            return 0
        if argv[:1] == ["sweep"] and len(argv) <= 2:
            keep = argv[1] if len(argv) == 2 and SESSION_ID_RE.match(argv[1]) else None
            for sid in sweep(role, keep):
                print(f"stopped: {sid}", file=sys.stderr)
            return 0
        if len(argv) == 1:
            payload = json.load(sys.stdin)
            handle(argv[0], payload if isinstance(payload, dict) else {}, role)
    except SystemExit:
        raise
    except Exception:
        log(f"{' '.join(argv[:1])}: {traceback.format_exc(limit=3)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
