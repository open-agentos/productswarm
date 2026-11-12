"""The specs bridge's append-only event log (#954, per #942's ruling; #937 §5.5, §7).

One JSON object per line in `$PRODUCTSWARM_HOME/specs/events.jsonl`, for the manual runs.
`swarm specs render` reads it to draw each feature's timeline. Moving it into `swarm.db` is
left for R4.

Three kinds of event:

- `pull`: a spec was read. Fields: `hash` (the spec's hash) and `issue_url`.
- `write`: the bridge wrote to the source. Field `what` is `status`, `links` or `comment`,
  with what was written in further fields.
- `decision`: the lead decided on drift. Field `choice` is `adopt`, `defer` or `ask`, and
  `where` says where it went.

Every event also carries `ts` (UTC, ISO 8601), `kind`, `goal` and `feature`.

**Not the idempotence key.** Per #942's ruling, push never relies on this log alone. The
feature's Issue and PR fields and the `swarm:pr=<n>` comment markers are the keys, so a lost,
truncated or split log must never cause a duplicate write. The log is a record, not a lock.

This module only appends: nothing here rewrites or truncates the file. Standard library only.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Each kind and the field that names its sub-kind, with the values that field may take.
KINDS = {
    "pull": None,
    "write": ("what", frozenset({"status", "links", "comment"})),
    "decision": ("choice", frozenset({"adopt", "defer", "ask"})),
}
RESERVED = frozenset({"ts", "kind", "goal", "feature"})


def path() -> Path:
    """`$PRODUCTSWARM_HOME/specs/events.jsonl`; the home defaults as in `swarm.py`'s `home()`."""
    home = Path(os.environ.get("PRODUCTSWARM_HOME", "~/.productswarm")).expanduser()
    return home / "specs" / "events.jsonl"


def append(kind: str, goal, feature: str, **fields) -> dict:
    """Append one event and return it. Raises ValueError on an unknown kind or sub-kind."""
    if kind not in KINDS:
        raise ValueError(f"unknown event kind {kind!r}; choose from {', '.join(KINDS)}")
    sub = KINDS[kind]
    if sub is not None:
        key, allowed = sub
        if fields.get(key) not in allowed:
            raise ValueError(
                f"a {kind} event needs {key} in {', '.join(sorted(allowed))}, "
                f"not {fields.get(key)!r}")
    clash = RESERVED & fields.keys()
    if clash:
        raise ValueError(f"reserved event field(s): {', '.join(sorted(clash))}")
    event = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kind": kind, "goal": goal, "feature": feature, **fields,
    }
    line = json.dumps(event, ensure_ascii=False) + "\n"
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(line)
    return event


class Events(list):
    """The events read, in file order. `skipped` counts the lines that didn't parse."""

    skipped: int = 0


def read(goal: Optional[object] = None) -> Events:
    """Every event in order, or only `goal`'s. A missing log reads as empty.

    A line that isn't a JSON object with a known `kind` is skipped and counted in
    `.skipped`, so one bad line can't hide the rest.
    """
    out = Events()
    p = path()
    if not p.exists():
        return out
    with p.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except ValueError:
                out.skipped += 1
                continue
            if not isinstance(event, dict) or event.get("kind") not in KINDS:
                out.skipped += 1
                continue
            if goal is None or str(event.get("goal")) == str(goal):
                out.append(event)
    return out
