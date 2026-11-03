#!/usr/bin/env python3
"""Enable (or disable) the heartbeat hook for this checkout in one step.

    python3 heartbeat/install.py              # enable
    python3 heartbeat/install.py --uninstall  # disable

Writes the hooks into .claude/settings.local.json, which is per-machine and not
committed. Other settings in that file are kept. Running it twice is harmless.
The hook only does anything in sessions started with ops/swarm-session.

The launcher writes the same entries into each session's worktree with with_hooks().
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = ROOT / ".claude" / "settings.local.json"
EVENTS = ["SessionStart", "UserPromptSubmit", "PostToolUse", "Stop", "SessionEnd"]
MARK = "heartbeat/hook.py"
PROJECT_HOOK = f"$CLAUDE_PROJECT_DIR/{MARK}"


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
    write_settings(SETTINGS, with_hooks(read_settings(SETTINGS), uninstall=uninstall))
    print(f"heartbeat {'disabled' if uninstall else 'enabled'} in {SETTINGS.relative_to(ROOT)}. "
          "Takes effect in sessions started from now on.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
