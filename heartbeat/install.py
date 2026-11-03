#!/usr/bin/env python3
"""Enable (or disable) the heartbeat hook for this checkout in one step.

    python3 heartbeat/install.py              # enable
    python3 heartbeat/install.py --uninstall  # disable

Writes the hooks into .claude/settings.local.json, which is per-machine and not
committed. Other settings in that file are kept. Running it twice is harmless.
The hook only does anything in sessions started with ops/swarm-session.

The hooks run from a pinned copy, not from the session's own files (#93): a detached
git worktree at ~/.productswarm/runtime (or $PRODUCTSWARM_HOME/runtime), checked out
at origin/main. So only code merged to main ever runs as a hook, and a session
editing heartbeat/hook.py on a branch doesn't run its own edits with its App's
credentials. Installing refreshes the copy, and so does every launcher start.

The launcher writes the same entries into each session's worktree with with_hooks().
"""
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = ROOT / ".claude" / "settings.local.json"
EVENTS = ["SessionStart", "UserPromptSubmit", "PostToolUse", "Stop", "SessionEnd"]
MARK = "heartbeat/hook.py"
PROJECT_HOOK = f"$CLAUDE_PROJECT_DIR/{MARK}"


def runtime_dir() -> Path:
    return Path(os.environ.get("PRODUCTSWARM_HOME", "~/.productswarm")).expanduser() / "runtime"


def run_git(args: list[str]) -> tuple[int, str]:
    """Run git; (exit code, combined output)."""
    try:
        r = subprocess.run(["git", *args], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)
    return r.returncode, (r.stdout + r.stderr).strip()


def refresh_runtime(root: Path, runtime: Path,
                    git: Callable[[list[str]], tuple[int, str]] = run_git) -> str:
    """Point the pinned copy at origin/main, creating it if needed; return its hook path.

    The caller fetches origin first. Raises RuntimeError if git fails."""
    if (runtime / ".git").exists():
        args = ["-C", str(runtime), "checkout", "-q", "--detach", "--force", "origin/main"]
    else:
        args = ["-C", str(root), "worktree", "add", "-q", "--detach", str(runtime), "origin/main"]
    rc, out = git(args)
    if rc:
        raise RuntimeError(f"can't refresh the pinned hook copy at {runtime}: {out[:300]}")
    return str(runtime / MARK)


def entry(event: str, hook: str = PROJECT_HOOK) -> dict:
    h = {"type": "command", "command": f'python3 -I "{hook}" {event}', "timeout": 15}
    e = {"hooks": [h]}
    if event == "PostToolUse":
        e["matcher"] = "*"
    return e


def without_ours(groups: list) -> list:
    out = []
    for g in groups:
        hooks = [h for h in g.get("hooks", []) if MARK not in h.get("command", "")]
        if hooks:
            out.append({**g, "hooks": hooks})
    return out


def with_hooks(settings: dict, hook: str = PROJECT_HOOK, uninstall: bool = False) -> dict:
    """A copy of settings with our hook entries replaced (or removed); other settings kept."""
    settings = json.loads(json.dumps(settings))
    hooks = settings.setdefault("hooks", {})
    for event in EVENTS:
        groups = without_ours(hooks.get(event, []))
        if not uninstall:
            groups.append(entry(event, hook))
        if groups:
            hooks[event] = groups
        else:
            hooks.pop(event, None)
    if not hooks:
        settings.pop("hooks")
    return settings


def read_settings(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def write_settings(path: Path, settings: dict) -> None:
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n")


def main(argv: list[str]) -> int:
    uninstall = "--uninstall" in argv
    hook = PROJECT_HOOK
    if not uninstall:
        rc, out = run_git(["-C", str(ROOT), "fetch", "-q", "origin", "main"])
        if rc:
            print(f"heartbeat: git fetch failed: {out[:300]}", file=sys.stderr)
            return 1
        try:
            hook = refresh_runtime(ROOT, runtime_dir())
        except RuntimeError as e:
            print(f"heartbeat: {e}", file=sys.stderr)
            return 1
    write_settings(SETTINGS, with_hooks(read_settings(SETTINGS), hook=hook, uninstall=uninstall))
    print(f"heartbeat {'disabled' if uninstall else f'enabled (hooks run from {runtime_dir()})'} "
          f"in {SETTINGS.relative_to(ROOT)}. Takes effect in sessions started from now on.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
