"""Tests for launcher/statedb.py (#659): swarm watch's state in swarm.db, watch.json's import
and `swarm backup`. Temporary directories only."""
import datetime as dt
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import statedb  # noqa: E402
import swarm  # noqa: E402
import webhooks  # noqa: E402

NOW = dt.datetime(2026, 11, 9, 14, 0, tzinfo=dt.timezone.utc)

# The shape a real watch.json has after a few days of ticks: every key, a live and an ended
# run of each kind of ending, held and skipped waiting entries, and both since-markers.
REAL_SHAPED = {
    "checked": "2026-11-09T13:55:00+00:00",
    "acted": {
        "build:49:11": "started 2026-11-09T09:00:00+00:00 builder-issue-49",
        "review:70:4f2a9c1": "started 2026-11-09T09:05:00+00:00 reviewer-pr-70",
        "answer:88": "refused: the issue is closed",
        "call-in:91:1234567": "started 2026-11-09T10:00:00+00:00 lead-issue-91",
        "ask:600:998877": "started 2026-11-09T11:00:00+00:00 planner-issue-600",
    },
    "waiting": [
        {"key": "build:60:12", "kind": "build", "ref": "#60", "since": "2026-11-09T08:00:00+00:00",
         "code": "live", "args": {"issue": 60}},
        {"key": "build:61:12", "kind": "build", "ref": "#61", "since": "2026-11-09T08:00:00+00:00",
         "code": "no_cap", "args": {}},
    ],
    "runs": {
        "build:49:11": {"session_id": "2d0c6c55-8a39-4a8e-9a43-1d1c64f2b0e1", "name": "builder-issue-49",
                        "kind": "build", "ref": "#49", "started": "2026-11-09T09:00:00+00:00",
                        "ending": "at_cap", "detail": "hit spend_cap_usd", "cost_usd": 4.87,
                        "subtype": "error_max_budget_usd", "ended": "2026-11-09T09:40:00+00:00"},
        "review:70:4f2a9c1": {"session_id": "6a1b", "name": "reviewer-pr-70", "kind": "review",
                              "ref": "PR #70", "started": "2026-11-09T09:05:00+00:00"},
        "ask:600:998877": {"session_id": "9c2e", "name": "planner-issue-600", "kind": "ask",
                           "ref": "#600", "started": "2026-11-09T11:00:00+00:00", "ending": "limited",
                           "detail": "resets 12pm (Europe/London)", "cost_usd": None,
                           "subtype": None, "ended": "2026-11-09T11:02:00+00:00",
                           "until": "2026-11-09T12:00:00+00:00", "retries": 1},
    },
    "asks_since": {"600": "2026-11-03T08:00:00+00:00"},
    "research_since": "2026-11-04T09:00:00+00:00",
}


class StateDbTest(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name)
        self.db = self.dir / statedb.DB_FILE
        self.legacy = self.dir / statedb.JSON_FILE

    def test_no_state_loads_empty_and_creates_nothing(self):
        self.assertEqual(statedb.load(self.dir), statedb.empty())
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_round_trip_keeps_values_and_order(self):
        statedb.save(self.dir, REAL_SHAPED)
        got = statedb.load(self.dir)
        self.assertEqual(got, REAL_SHAPED)
        self.assertEqual(list(got["acted"]), list(REAL_SHAPED["acted"]))
        self.assertEqual(list(got["runs"]), list(REAL_SHAPED["runs"]))
        self.assertEqual([w["key"] for w in got["waiting"]], ["build:60:12", "build:61:12"])

    def test_a_save_replaces_the_whole_state(self):
        statedb.save(self.dir, REAL_SHAPED)
        statedb.save(self.dir, {"checked": None, "acted": {"k": "started"}})
        self.assertEqual(statedb.load(self.dir), {**statedb.empty(), "acted": {"k": "started"}})

    def test_watch_json_is_read_until_the_first_save_imports_it(self):
        self.legacy.write_text(json.dumps(REAL_SHAPED, indent=1))
        self.assertEqual(statedb.load(self.dir), REAL_SHAPED)
        self.assertFalse(self.db.exists())                       # a dry run writes nothing
        statedb.save(self.dir, statedb.load(self.dir))
        self.assertFalse(self.legacy.exists())
        self.assertEqual(json.loads((self.dir / "watch.json.bak").read_text()), REAL_SHAPED)
        self.assertEqual(statedb.load(self.dir), REAL_SHAPED)    # now from swarm.db

    def test_an_old_watch_json_without_newer_keys_imports_with_defaults(self):
        self.legacy.write_text(json.dumps({"checked": None, "acted": {"a": "started"}, "waiting": []}))
        statedb.save(self.dir, statedb.load(self.dir))
        self.assertEqual(statedb.load(self.dir), {**statedb.empty(), "acted": {"a": "started"}})

    def test_a_broken_watch_json_is_an_error_not_an_empty_state(self):
        self.legacy.write_text("{")
        with self.assertRaisesRegex(RuntimeError, "is not valid JSON"):
            statedb.load(self.dir)

    def test_shares_swarm_db_with_the_webhook_receiver(self):
        store = webhooks.Store(self.db)                          # the receiver came first
        self.addCleanup(store.db.close)
        store.record("d-1", "issues", "labeled", "o/r", 7, NOW)
        self.assertEqual(statedb.load(self.dir), statedb.empty())
        statedb.save(self.dir, REAL_SHAPED)
        self.assertEqual(statedb.load(self.dir), REAL_SHAPED)
        self.assertEqual(store.rows(), [("d-1", "issues", "labeled", "o/r", 7)])

    def test_a_value_json_cant_hold_fails_before_touching_the_state(self):
        statedb.save(self.dir, REAL_SHAPED)
        with self.assertRaises(TypeError):
            statedb.save(self.dir, {"runs": {"k": {"started": object()}}})
        self.assertEqual(statedb.load(self.dir), REAL_SHAPED)

    def test_uses_wal_so_readers_dont_block_the_writer(self):
        statedb.save(self.dir, REAL_SHAPED)
        db = sqlite3.connect(self.db)
        self.addCleanup(db.close)
        self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "wal")


class BackupTest(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name)

    def test_nothing_to_back_up_is_an_error(self):
        with self.assertRaisesRegex(RuntimeError, "nothing to back up"):
            statedb.backup(self.dir)

    def test_writes_a_private_consistent_copy(self):
        statedb.save(self.dir, REAL_SHAPED)
        out = statedb.backup(self.dir, now=NOW)
        self.assertEqual(out, self.dir / "backups" / "swarm-20261109T140000Z.db")
        self.assertEqual(out.stat().st_mode & 0o777, 0o600)
        restored = Path(tempfile.mkdtemp(dir=self.dir))
        out.replace(restored / statedb.DB_FILE)
        self.assertEqual(statedb.load(restored), REAL_SHAPED)

    def test_keeps_the_newest_backups_only(self):
        statedb.save(self.dir, REAL_SHAPED)
        for day in range(1, 5):
            statedb.backup(self.dir, now=NOW.replace(day=day), keep=2)
        self.assertEqual(sorted(p.name for p in (self.dir / "backups").iterdir()),
                         ["swarm-20261103T140000Z.db", "swarm-20261104T140000Z.db"])

    def test_an_explicit_out_path_is_never_pruned(self):
        statedb.save(self.dir, REAL_SHAPED)
        out = statedb.backup(self.dir, self.dir / "copy.db")
        self.assertTrue(out.exists())
        self.assertFalse((self.dir / "backups").exists())


class CliTest(unittest.TestCase):
    def run_backup(self, d: Path, *args: str) -> tuple[int, list[str]]:
        out = []
        launcher = mock.Mock(dir=d, out=out.append)
        return swarm.main(["backup", *args], launcher=launcher), out

    def test_swarm_backup(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            self.assertEqual(self.run_backup(d)[0], 1)              # nothing yet
            statedb.save(d, REAL_SHAPED)
            code, out = self.run_backup(d, "--out", str(d / "x.db"))
            self.assertEqual(code, 0)
            self.assertEqual(out, [f"swarm backup: wrote {d / 'x.db'}"])


if __name__ == "__main__":
    unittest.main()
