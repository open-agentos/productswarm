"""swarm webhooks: receive GitHub App webhooks on the engine host and nudge the watcher.

A webhook only nudges (operating model v2, #651). The receiver never trusts a payload for who
did what and never starts a session: it checks the signature, records the delivery, and touches
~/.productswarm/launcher/nudge so the watcher re-reads state from GitHub now rather than at its
next sweep. This is the same rule as the reviewer reconciler (GOV-0020): events may only nudge.
A forged or replayed event can at most cause one extra read.

    POST /webhooks/github   verified with X-Hub-Signature-256 (HMAC-SHA256 of the raw body with
                            WEBHOOK_SECRET), at most 1 MB; 202 when accepted or a duplicate
    GET  /healthz           200

Each accepted delivery is one row in swarm.db's `deliveries` table: delivery id, event, action,
repo, number and when it arrived. No payload body is kept (GOV-0002, GOV-0004). GitHub's
X-GitHub-Delivery id is the key, so a redelivery is recorded once and nudges once.

Usage: swarm webhooks [--host 127.0.0.1] [--port 8081], with WEBHOOK_SECRET in the environment.
It listens on localhost only by default; Caddy terminates TLS in front of it (ops/vps).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import http.server
import json
import re
import sqlite3
import threading
from pathlib import Path

PATH = "/webhooks/github"
MAX_BODY = 1_000_000
DB_FILE = "swarm.db"
NUDGE_FILE = "nudge"
DELIVERY_RE = re.compile(r"[0-9A-Za-z-]{1,64}")
EVENT_RE = re.compile(r"[a-z_]{1,64}")
QUIET = {"ping"}   # recorded, but nothing for the watcher to read


def signature_ok(secret: bytes, body: bytes, header: str | None) -> bool:
    """True only for a well-formed sha256 signature of `body` under a non-empty `secret`."""
    if not secret or not header or not header.startswith("sha256="):
        return False
    want = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(want.encode(), header.encode())


def summary(payload: object) -> tuple[str | None, str | None, int | None]:
    """(action, repo, number) for the log row. Read from an untrusted payload: never acted on."""
    if not isinstance(payload, dict):
        return None, None, None
    action = payload.get("action") if isinstance(payload.get("action"), str) else None
    repo_obj = payload.get("repository")
    repo = repo_obj.get("full_name") if isinstance(repo_obj, dict) else None
    number = None
    for key in ("issue", "pull_request", "discussion"):
        obj = payload.get(key)
        if isinstance(obj, dict) and isinstance(obj.get("number"), int):
            number = obj["number"]
            break
    return (action[:64] if action else None,
            repo[:140] if isinstance(repo, str) else None, number)


class Store:
    """The deliveries log in swarm.db. Safe to share across the server's threads."""

    def __init__(self, path: Path):
        self.lock = threading.Lock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        with self.lock, self.db:
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS deliveries (id TEXT PRIMARY KEY, event TEXT NOT NULL,"
                " action TEXT, repo TEXT, number INTEGER, received_at TEXT NOT NULL)")

    def record(self, delivery: str, event: str, action: str | None, repo: str | None,
               number: int | None, now: dt.datetime) -> bool:
        """Add a delivery; False if its id was already recorded."""
        with self.lock, self.db:
            cur = self.db.execute(
                "INSERT OR IGNORE INTO deliveries VALUES (?, ?, ?, ?, ?, ?)",
                (delivery, event, action, repo, number, now.isoformat(timespec="seconds")))
            return cur.rowcount == 1

    def rows(self) -> list[tuple]:
        with self.lock:
            return self.db.execute(
                "SELECT id, event, action, repo, number FROM deliveries ORDER BY received_at, id"
            ).fetchall()


def nudge(path: Path) -> None:
    """Touch the nudge file; the watcher checks its mtime."""
    path.touch()


def handle(store: Store, secret: bytes, nudge_path: Path, method: str, path: str,
           headers: dict[str, str], body: bytes, now: dt.datetime) -> tuple[int, str]:
    """One request -> (status, short text). `headers` keys are lower-case."""
    if path == "/healthz":
        return (200, "ok") if method in ("GET", "HEAD") else (405, "method not allowed")
    if path != PATH:
        return 404, "not found"
    if method != "POST":
        return 405, "method not allowed"
    if len(body) > MAX_BODY:
        return 413, "too large"
    if not signature_ok(secret, body, headers.get("x-hub-signature-256")):
        return 401, "bad signature"
    delivery = headers.get("x-github-delivery", "")
    event = headers.get("x-github-event", "")
    if not DELIVERY_RE.fullmatch(delivery) or not EVENT_RE.fullmatch(event):
        return 400, "missing or unusual delivery headers"
    try:
        payload = json.loads(body)
    except ValueError:
        return 400, "body is not JSON"
    if not store.record(delivery, event, *summary(payload), now):
        return 202, "duplicate"
    if event not in QUIET:
        nudge(nudge_path)
    return 202, "accepted"


def make_handler(store: Store, secret: bytes, nudge_path: Path):
    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "productswarm"
        sys_version = ""

        def _answer(self, method: str) -> None:
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if length < 0 or length > MAX_BODY:
                status, text = 413, "too large"   # never read an oversized body
                self.close_connection = True
            else:
                body = self.rfile.read(length) if length else b""
                headers = {k.lower(): v for k, v in self.headers.items()}
                status, text = handle(store, secret, nudge_path, method, self.path.split("?")[0],
                                      headers, body, dt.datetime.now(dt.timezone.utc))
            data = (text + "\n").encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if method != "HEAD":
                self.wfile.write(data)

        def do_GET(self):
            self._answer("GET")

        def do_HEAD(self):
            self._answer("HEAD")

        def do_POST(self):
            self._answer("POST")

        def do_PUT(self):
            self._answer("PUT")

        def do_DELETE(self):
            self._answer("DELETE")

        def log_message(self, fmt, *args):   # silent: no request lines or headers in logs
            pass

    return Handler


class Server(http.server.ThreadingHTTPServer):
    store: Store

    def server_close(self):
        super().server_close()
        self.store.db.close()


def server(state_dir: Path, secret: bytes, host: str = "127.0.0.1", port: int = 8081) -> Server:
    state_dir.mkdir(parents=True, exist_ok=True)
    store = Store(state_dir / DB_FILE)
    srv = Server((host, port), make_handler(store, secret, state_dir / NUDGE_FILE))
    srv.store = store
    return srv


def serve(state_dir: Path, secret: str, host: str, port: int, out=print) -> int:
    if not secret:
        out("swarm webhooks: WEBHOOK_SECRET is not set; refusing to start")
        return 2
    srv = server(state_dir, secret.encode(), host, port)
    out(f"swarm webhooks: listening on {host}:{srv.server_address[1]}{PATH}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0
