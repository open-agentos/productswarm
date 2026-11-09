"""swarm watch's local state in ~/.productswarm/launcher/swarm.db (#659).

watch.json's keys, with the same meaning, as tables beside the webhook receiver's
`deliveries` (webhooks.py, #658):

    watch_meta        name -> JSON value: "checked" and "research_since"
    watch_acted       trigger key -> outcome
    watch_waiting     the held and skipped triggers, in order: pos, key, JSON entry
    watch_runs        trigger key -> JSON run record (#149)
    watch_asks_since  report issue -> when asks was first seen on (#590)

A save replaces every watch_ table in one IMMEDIATE transaction, so a reader or a second
writer sees one whole state, never half of two (#296). A read opens the file read-only and
never creates it, so `--dry-run`, `swarm inbox`, `swarm status` and `swarm cost` write
nothing.

An existing watch.json is imported once: the first save copies it into the tables, then
renames it watch.json.bak. Until then, reads come from watch.json, so nothing it holds is
lost or hidden. `swarm backup` copies swarm.db through SQLite's backup API, which is
consistent even while the watcher or the receiver is writing.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
from pathlib import Path

DB_FILE = "swarm.db"            # shared with webhooks.DB_FILE
JSON_FILE = "watch.json"        # the old store, imported once
BAK_SUFFIX = ".bak"
BACKUP_DIR = "backups"
TIMEOUT = 30                    # seconds a writer waits for another's transaction

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS watch_meta (name TEXT PRIMARY KEY, value TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS watch_acted (key TEXT PRIMARY KEY, outcome TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS watch_waiting (pos INTEGER PRIMARY KEY, key TEXT NOT NULL,"
    " entry TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS watch_runs (key TEXT PRIMARY KEY, record TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS watch_asks_since (issue TEXT PRIMARY KEY, since TEXT NOT NULL)",
)
TABLES = ("watch_meta", "watch_acted", "watch_waiting", "watch_runs", "watch_asks_since")


def empty() -> dict:
    return {"checked": None, "acted": {}, "waiting": [], "runs": {}, "asks_since": {},
            "research_since": None}


def normal(data: dict) -> dict:
    """A state dict with every key, as load_state() has always returned it."""
    return {"checked": data.get("checked"), "acted": dict(data.get("acted") or {}),
            "waiting": list(data.get("waiting") or []), "runs": dict(data.get("runs") or {}),
            "asks_since": dict(data.get("asks_since") or {}),
            "research_since": data.get("research_since")}


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except ValueError as e:
        raise RuntimeError(f"{path} is not valid JSON: {e}") from None
    if not isinstance(data, dict):
        raise RuntimeError(f"{path} is not valid JSON: not an object")
    return normal(data)


def load(state_dir: Path) -> dict:
    """The watcher's state: from watch.json while it is still waiting to be imported, else
    from swarm.db, else empty. Writes nothing. Raises RuntimeError on an unreadable store."""
    old, db = state_dir / JSON_FILE, state_dir / DB_FILE
    if old.exists():
        return read_json(old)
    if not db.exists():
        return empty()
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=TIMEOUT)
    except sqlite3.Error as e:
        raise RuntimeError(f"can't open {db}: {e}") from None
    try:
        have = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if not set(TABLES) <= have:
            return empty()                    # only the receiver has used it so far
        meta = {k: json.loads(v) for k, v in con.execute("SELECT name, value FROM watch_meta")}
        return {
            "checked": meta.get("checked"),
            "acted": dict(con.execute("SELECT key, outcome FROM watch_acted ORDER BY rowid")),
            "waiting": [json.loads(e) for (e,) in
                        con.execute("SELECT entry FROM watch_waiting ORDER BY pos")],
            "runs": {k: json.loads(r) for k, r in
                     con.execute("SELECT key, record FROM watch_runs ORDER BY rowid")},
            "asks_since": dict(con.execute("SELECT issue, since FROM watch_asks_since ORDER BY rowid")),
            "research_since": meta.get("research_since"),
        }
    except (sqlite3.Error, ValueError) as e:
        raise RuntimeError(f"{db} is not a readable state database: {e}") from None
    finally:
        con.close()


def rows(st: dict) -> dict[str, list[tuple]]:
    """st as each table's rows. Serialises everything first, so a value that can't be
    stored raises (TypeError) before the database is touched."""
    st = normal(st)
    return {
        "watch_meta": [("checked", json.dumps(st["checked"])),
                       ("research_since", json.dumps(st["research_since"]))],
        "watch_acted": [(str(k), str(v)) for k, v in st["acted"].items()],
        "watch_waiting": [(i, str(x.get("key", "")), json.dumps(x)) for i, x in enumerate(st["waiting"])],
        "watch_runs": [(str(k), json.dumps(r)) for k, r in st["runs"].items()],
        "watch_asks_since": [(str(k), str(v)) for k, v in st["asks_since"].items()],
    }


def connect(db: Path) -> sqlite3.Connection:
    """A connection with explicit transactions (isolation_level None)."""
    return sqlite3.connect(db, timeout=TIMEOUT, isolation_level=None)


def write(db: Path, st: dict) -> None:
    """Replace the whole watcher state in one transaction."""
    data = rows(st)
    try:
        replace_all(db, data)
    except sqlite3.Error as e:
        raise RuntimeError(f"writing {db} failed: {e}") from None


def replace_all(db: Path, data: dict[str, list[tuple]]) -> None:
    con = connect(db)
    try:
        con.execute("BEGIN IMMEDIATE")
        try:
            for stmt in SCHEMA:
                con.execute(stmt)
            for table, values in data.items():
                con.execute(f"DELETE FROM {table}")
                if values:
                    marks = ", ".join("?" * len(values[0]))
                    con.executemany(f"INSERT INTO {table} VALUES ({marks})", values)
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
    finally:
        con.close()


def import_json(state_dir: Path) -> bool:
    """Copy watch.json into swarm.db and rename it watch.json.bak. True if there was one.
    Safe to repeat: a crash before the rename imports the same file again next time."""
    old = state_dir / JSON_FILE
    if not old.exists():
        return False
    write(state_dir / DB_FILE, read_json(old))
    os.replace(old, old.with_name(old.name + BAK_SUFFIX))
    return True


def save(state_dir: Path, st: dict) -> None:
    """Write st to swarm.db, after importing a watch.json that is still waiting."""
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    import_json(state_dir)
    write(state_dir / DB_FILE, st)


def backup(state_dir: Path, dest: Path | None = None, now: dt.datetime | None = None) -> Path:
    """Copy swarm.db to dest (default backups/swarm-<UTC time>.db beside it) through SQLite's
    backup API, so the copy is consistent while others write. Written to a temp file and
    renamed, so dest is never half a copy. Returns dest. Raises RuntimeError."""
    db = state_dir / DB_FILE
    if not db.exists():
        raise RuntimeError(f"{db} doesn't exist yet; nothing to back up")
    if dest is None:
        now = now or dt.datetime.now(dt.timezone.utc)
        dest = state_dir / BACKUP_DIR / f"swarm-{now.astimezone(dt.timezone.utc):%Y%m%dT%H%M%SZ}.db"
    dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = dest.with_name(f".{dest.name}.{os.getpid()}.tmp")
    try:
        src = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=TIMEOUT)
        try:
            out = sqlite3.connect(tmp)
            try:
                src.backup(out)
            finally:
                out.close()
        finally:
            src.close()
        os.chmod(tmp, 0o600)
        os.replace(tmp, dest)
    except sqlite3.Error as e:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"backing up {db} failed: {e}") from None
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return dest
