"""swarm watch's state in ~/.productswarm/launcher/swarm.db (#659), replacing watch.json.

The meaning is unchanged: load() returns the same dict watch.json held (watch.load_state()
documents it) and save() replaces it whole in one transaction, so a reader never sees half a
tick and two writers can't mix their states (#296). Tables:

    watch_meta        key -> JSON value: "checked", "research_since"
    watch_acted       trigger key -> outcome
    watch_waiting     position -> waiting entry (JSON)
    watch_runs        trigger key -> run record (JSON)
    watch_asks_since  report issue -> ISO time

The same file holds the webhook receiver's `deliveries` (webhooks.py) and the runs ledger
(ledger.py, #662), which save() leaves alone. The database uses WAL, so `swarm status` can
read while the watcher or the receiver writes.

watch.json is imported once. While it exists, load() reads it rather than the database, so a
dry run still writes nothing. The next save() writes its state to the database and renames the
file to watch.json.bak. watch-public.json (#456) and the [watch] issue (GOV-0025) are unchanged.

`swarm backup` writes a consistent copy with SQLite's online backup API.
"""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path

DB_FILE = "swarm.db"
JSON_FILE = "watch.json"      # the state before #659, imported once
BACKUP_DIR = "backups"
KEEP_BACKUPS = 14
TIMEOUT = 30                  # seconds a writer waits for another writer's transaction

SCHEMA = """
CREATE TABLE IF NOT EXISTS watch_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS watch_acted (key TEXT PRIMARY KEY, outcome TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS watch_waiting (pos INTEGER PRIMARY KEY, item TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS watch_runs (key TEXT PRIMARY KEY, run TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS watch_asks_since (report TEXT PRIMARY KEY, at TEXT NOT NULL);
"""
TABLES = ("watch_meta", "watch_acted", "watch_waiting", "watch_runs", "watch_asks_since")


def empty() -> dict:
    return {"checked": None, "acted": {}, "waiting": [], "runs": {}, "asks_since": {},
            "research_since": None}


def normal(data: dict) -> dict:
    """The six keys of watch state, with defaults for any an older watch.json lacks."""
    return {"checked": data.get("checked"), "acted": dict(data.get("acted") or {}),
            "waiting": list(data.get("waiting") or []), "runs": dict(data.get("runs") or {}),
            "asks_since": dict(data.get("asks_since") or {}),
            "research_since": data.get("research_since")}


def connect(path: Path) -> sqlite3.Connection:
    """A writer's connection, with the schema in place. Transactions are explicit."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(path, timeout=TIMEOUT, isolation_level=None)
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(SCHEMA)
    return db


def load(state_dir: Path) -> dict:
    """The watch state. Read-only: it never creates the database (a dry run writes nothing)."""
    legacy = state_dir / JSON_FILE
    try:
        return normal(json.loads(legacy.read_text()))
    except FileNotFoundError:
        pass
    except ValueError as e:
        raise RuntimeError(f"{legacy} is not valid JSON: {e}") from None
    path = state_dir / DB_FILE
    if not path.exists():
        return empty()
    db = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True, timeout=TIMEOUT)
    try:
        have = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if not set(TABLES) <= have:
            return empty()           # only the receiver's table so far
        db.execute("BEGIN")          # one snapshot across the five tables
        meta = {k: json.loads(v) for k, v in db.execute("SELECT key, value FROM watch_meta")}
        st = {"checked": meta.get("checked"),
              "acted": dict(db.execute("SELECT key, outcome FROM watch_acted ORDER BY rowid")),
              "waiting": [json.loads(v) for (v,) in
                          db.execute("SELECT item FROM watch_waiting ORDER BY pos")],
              "runs": {k: json.loads(v) for k, v in
                       db.execute("SELECT key, run FROM watch_runs ORDER BY rowid")},
              "asks_since": dict(db.execute("SELECT report, at FROM watch_asks_since ORDER BY rowid")),
              "research_since": meta.get("research_since")}
        db.execute("COMMIT")
        return st
    finally:
        db.close()


def save(state_dir: Path, st: dict) -> None:
    """Replace the watch state in one transaction; on any error the old state stays. Then, if
    watch.json is still there, it has now been imported: rename it to watch.json.bak."""
    st = normal(st)
    rows = {   # encoded before the transaction, so a value JSON can't hold fails early
        "watch_meta": [("checked", json.dumps(st["checked"])),
                       ("research_since", json.dumps(st["research_since"]))],
        "watch_acted": [(str(k), str(v)) for k, v in st["acted"].items()],
        "watch_waiting": [(i, json.dumps(x)) for i, x in enumerate(st["waiting"])],
        "watch_runs": [(str(k), json.dumps(v)) for k, v in st["runs"].items()],
        "watch_asks_since": [(str(k), str(v)) for k, v in st["asks_since"].items()],
    }
    db = connect(state_dir / DB_FILE)
    try:
        db.execute("BEGIN IMMEDIATE")
        try:
            for table in TABLES:
                db.execute(f"DELETE FROM {table}")
                if rows[table]:
                    db.executemany(f"INSERT INTO {table} VALUES (?, ?)", rows[table])
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
    finally:
        db.close()
    legacy = state_dir / JSON_FILE
    if legacy.exists():
        legacy.replace(state_dir / (JSON_FILE + ".bak"))


def backup(state_dir: Path, out: Path | None = None, now: dt.datetime | None = None,
           keep: int = KEEP_BACKUPS) -> Path:
    """Copy swarm.db to `out`, or to backups/swarm-<UTC time>.db keeping the newest `keep`.
    SQLite's backup API copies a consistent snapshot while the watcher and receiver write."""
    src_path = state_dir / DB_FILE
    if not src_path.exists():
        raise RuntimeError(f"{src_path} doesn't exist yet: nothing to back up")
    default = out is None
    if default:
        stamp = (now or dt.datetime.now(dt.timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
        out = state_dir / BACKUP_DIR / f"swarm-{stamp}.db"
    out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = out.with_name(out.name + ".tmp")
    src = sqlite3.connect(src_path, timeout=TIMEOUT)
    try:
        dst = sqlite3.connect(tmp)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    tmp.chmod(0o600)
    tmp.replace(out)
    if default:
        for old in sorted(out.parent.glob("swarm-*.db"))[:-keep]:
            old.unlink()
    return out
