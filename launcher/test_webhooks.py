"""Tests for launcher/webhooks.py: the receiver only verifies, records and nudges."""
import datetime as dt
import hashlib
import hmac
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import swarm  # noqa: E402
import webhooks  # noqa: E402

SECRET = b"s3cret"
NOW = dt.datetime(2026, 11, 9, 8, 30, tzinfo=dt.timezone.utc)


def sign(body: bytes, secret: bytes = SECRET) -> str:
    return "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()


def payload(**kw) -> bytes:
    p = {"action": "labeled", "repository": {"full_name": "open-agentos/productswarm"},
         "issue": {"number": 651}}
    p.update(kw)
    return json.dumps(p).encode()


class Handle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.store = webhooks.Store(self.dir / webhooks.DB_FILE)
        self.nudge = self.dir / webhooks.NUDGE_FILE

    def tearDown(self):
        self.store.db.close()
        self.tmp.cleanup()

    def post(self, body: bytes, sig: str | None = "auto", delivery="d-1", event="issues",
             path=webhooks.PATH, method="POST"):
        headers = {"x-github-delivery": delivery, "x-github-event": event}
        if sig is not None:
            headers["x-hub-signature-256"] = sign(body) if sig == "auto" else sig
        return webhooks.handle(self.store, SECRET, self.nudge, method, path, headers, body, NOW)

    def test_good_signature_records_and_nudges(self):
        self.assertEqual(self.post(payload()), (202, "accepted"))
        self.assertTrue(self.nudge.exists())
        self.assertEqual(self.store.rows(),
                         [("d-1", "issues", "labeled", "open-agentos/productswarm", 651)])

    def test_bad_signature_is_refused_without_a_trace(self):
        self.assertEqual(self.post(payload(), sig=sign(payload(), b"other")), (401, "bad signature"))
        self.assertEqual(self.post(payload(), sig=None), (401, "bad signature"))
        self.assertEqual(self.post(payload(), sig="sha1=abc"), (401, "bad signature"))
        self.assertFalse(self.nudge.exists())
        self.assertEqual(self.store.rows(), [])

    def test_empty_secret_refuses_everything(self):
        body = payload()
        r = webhooks.handle(self.store, b"", self.nudge, "POST", webhooks.PATH,
                            {"x-hub-signature-256": sign(body, b""), "x-github-delivery": "d",
                             "x-github-event": "issues"}, body, NOW)
        self.assertEqual(r, (401, "bad signature"))

    def test_duplicate_delivery_is_recorded_and_nudges_once(self):
        self.post(payload())
        self.nudge.unlink()
        self.assertEqual(self.post(payload()), (202, "duplicate"))
        self.assertFalse(self.nudge.exists())
        self.assertEqual(len(self.store.rows()), 1)

    def test_oversized_body(self):
        body = b"x" * (webhooks.MAX_BODY + 1)
        self.assertEqual(self.post(body), (413, "too large"))

    def test_unusual_headers_and_bad_json(self):
        self.assertEqual(self.post(payload(), delivery="a b")[0], 400)
        self.assertEqual(self.post(payload(), event="Issues; rm")[0], 400)
        self.assertEqual(self.post(b"not json"), (400, "body is not JSON"))

    def test_ping_is_recorded_but_does_not_nudge(self):
        self.assertEqual(self.post(b'{"zen": "x"}', event="ping"), (202, "accepted"))
        self.assertFalse(self.nudge.exists())
        self.assertEqual(self.store.rows(), [("d-1", "ping", None, None, None)])

    def test_payload_fields_are_only_logged_when_well_typed(self):
        self.post(payload(action=["x"], repository="r", issue={"number": "7"},
                          pull_request={"number": 8}))
        self.assertEqual(self.store.rows(), [("d-1", "issues", None, None, 8)])

    def test_routes(self):
        self.assertEqual(self.post(b"", path="/healthz", method="GET"), (200, "ok"))
        self.assertEqual(self.post(b"", path="/other", method="GET"), (404, "not found"))
        self.assertEqual(self.post(payload(), method="GET"), (405, "method not allowed"))


class Server(unittest.TestCase):
    """The real HTTP server on an ephemeral localhost port."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.srv = webhooks.server(self.dir, SECRET, port=0)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.tmp.cleanup()

    def request(self, path, body=None, headers=None, method=None):
        req = urllib.request.Request(self.url + path, data=body, headers=headers or {},
                                     method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.read().decode().strip()
        except urllib.error.HTTPError as e:
            with e:
                return e.code, e.read().decode().strip()

    def test_accepts_a_signed_delivery(self):
        body = payload()
        got = self.request(webhooks.PATH, body, {
            "X-Hub-Signature-256": sign(body), "X-GitHub-Delivery": "abc-1",
            "X-GitHub-Event": "issues", "Content-Type": "application/json"})
        self.assertEqual(got, (202, "accepted"))
        self.assertTrue((self.dir / webhooks.NUDGE_FILE).exists())

    def test_refuses_an_oversized_length_without_reading_it(self):
        got = self.request(webhooks.PATH, b"{}", {
            "Content-Length": str(webhooks.MAX_BODY + 1), "X-GitHub-Event": "issues"})
        self.assertEqual(got, (413, "too large"))

    def test_healthz(self):
        self.assertEqual(self.request("/healthz"), (200, "ok"))


class Cli(unittest.TestCase):
    def test_refuses_to_start_without_a_secret(self):
        out = []
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("WEBHOOK_SECRET", None)
            launcher = mock.Mock(dir=Path(d), out=out.append)
            self.assertEqual(swarm.main(["webhooks", "--port", "0"], launcher=launcher), 2)
        self.assertIn("WEBHOOK_SECRET is not set", out[0])


if __name__ == "__main__":
    unittest.main()
