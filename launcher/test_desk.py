"""Tests for launcher/desk.py: the live Desk is read-only and rebuilt from GitHub on a nudge."""
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import desk  # noqa: E402
import swarm  # noqa: E402


def fake_generate(write=True, code=0, line="wrote it"):
    """A stand-in for generate.py: records each command, and writes the pages if asked."""
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        out = Path(cmd[cmd.index("--out") + 1])
        if write:
            out.write_text(f"<p>desk {len(calls)}</p>")
            (out.parent / desk.STATE).write_text('{"built_at": "2026-11-09T08:00:00Z"}')
            (out.parent / "fonts").mkdir()
            (out.parent / "fonts" / "a.woff2").write_bytes(b"font")
        return subprocess.CompletedProcess(cmd, code, line + "\n", "")
    return run, calls


class BuildsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "desk"
        self.said = []

    def tearDown(self):
        self.tmp.cleanup()

    def builds(self, run):
        return desk.Builds(self.root, "o/r", run=run, out=self.said.append)

    def test_a_good_build_goes_live_and_old_ones_go(self):
        run, calls = fake_generate()
        b = self.builds(run)
        self.assertIsNone(b.live())
        for _ in range(3):
            self.assertTrue(b.build())
        self.assertEqual((b.live() / "index.html").read_text(), "<p>desk 3</p>")
        # The live build and the one before it (an in-flight read may still need it).
        self.assertEqual(len(list(self.root.glob("build-*"))), 2)
        self.assertTrue((self.root / desk.LIVE).is_symlink())
        self.assertIn("--repo", calls[0])
        self.assertNotIn("--prev", calls[0])
        # Later builds carry precedent forward from the served state.json.
        prev = calls[2][calls[2].index("--prev") + 1]
        self.assertTrue(prev.endswith(desk.STATE))
        self.assertIn("published", self.said[-1])

    def test_a_skipped_or_failed_build_leaves_the_last_good_desk(self):
        run, _ = fake_generate()
        b = self.builds(run)
        b.build()
        good = b.live()
        for run in (fake_generate(write=False, line="generate.py: skipped, not published: low")[0],
                    fake_generate(code=1, line="generate.py: boom")[0]):
            self.assertFalse(self.builds(run).build())
            self.assertEqual(b.live(), good)
        self.assertEqual(list(self.root.glob("build-*")), [good])
        self.assertIn("boom", self.said[-1])

    def test_a_hung_build_is_cleaned_up(self):
        def run(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, kw["timeout"])
        self.assertFalse(self.builds(run).build())
        self.assertEqual(list(self.root.glob("build-*")), [])
        self.assertIsNone(self.builds(run).live())


class FakeTime:
    def __init__(self):
        self.now = 0.0

    def clock(self):
        return self.now

    def sleep(self, s):
        self.now += s


class LoopTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.nudge = Path(self.tmp.name) / desk.NUDGE_FILE
        self.t = FakeTime()
        self.built = []

        class B:
            out = print

            def build(inner):
                self.built.append(self.t.now)
                return True
        self.loop = desk.Loop(B(), self.nudge, sweep=600, gap=120, clock=self.t.clock, sleep=self.t.sleep)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sweeps_without_a_nudge(self):
        self.loop.run(ticks=3)
        self.assertEqual(self.built, [0, 600, 1200])

    def test_a_nudge_builds_once_the_gap_has_passed(self):
        self.loop.run(ticks=1)
        self.nudge.touch()              # arrives at t=0, inside the gap
        self.loop.wait()
        self.assertEqual(self.t.now, 120)

    def test_a_nudge_after_the_gap_builds_at_once(self):
        self.loop.run(ticks=1)
        self.t.now = 300
        self.nudge.touch()
        self.loop.wait()
        self.assertEqual(self.t.now, 300)

    def test_one_build_error_doesnt_stop_the_loop(self):
        class Bad:
            said = []

            def out(self, s):
                self.said.append(s)

            def build(self):
                raise ValueError("bad")
        bad = Bad()
        desk.Loop(bad, self.nudge, sweep=1, clock=self.t.clock, sleep=self.t.sleep).run(ticks=2)
        self.assertEqual(len(bad.said), 2)


class HandleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.live = Path(self.tmp.name)
        (self.live / "index.html").write_text("<p>desk</p>")
        (self.live / "operations.html").write_text("<p>ops</p>")
        (self.live / desk.STATE).write_text("{}")
        (self.live / "fonts").mkdir()
        (self.live / "fonts" / "a.woff2").write_bytes(b"font")
        (self.live / "secret.txt").write_text("no")

    def tearDown(self):
        self.tmp.cleanup()

    def test_serves_the_pages_state_and_fonts(self):
        for path, ctype, body in (("/", "text/html", b"<p>desk</p>"),
                                  ("/index.html?t=1", "text/html", b"<p>desk</p>"),
                                  ("/operations.html", "text/html", b"<p>ops</p>"),
                                  ("/state.json?t=99", "application/json", b"{}"),
                                  ("/fonts/a.woff2", "font/woff2", b"font")):
            status, headers, got = desk.handle(self.live, "GET", path)
            self.assertEqual((status, got), (200, body), path)
            self.assertTrue(headers["Content-Type"].startswith(ctype), path)
            self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
            self.assertIn("noindex", headers["X-Robots-Tag"])
        self.assertEqual(desk.handle(self.live, "HEAD", "/")[0], 200)

    def test_no_write_route(self):
        for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS"):
            for path in ("/", "/index.html", "/webhooks/github", "/login"):
                status, headers, _ = desk.handle(self.live, method, path)
                self.assertEqual(status, 405, (method, path))
                self.assertEqual(headers["Allow"], "GET, HEAD")

    def test_only_known_files(self):
        os.symlink("/etc/hosts", self.live / "linked.html")
        for path in ("/secret.txt", "/../index.html", "/fonts/../secret.txt", "/fonts/.hidden",
                     "/nope.html", "/linked.html", "/index.htm", "//etc/passwd", "/INDEX.html",
                     "/fonts/", "/fonts/a.exe"):
            self.assertEqual(desk.handle(self.live, "GET", path)[0], 404, path)

    def test_before_the_first_build(self):
        status, headers, _ = desk.handle(None, "GET", "/")
        self.assertEqual(status, 503)
        self.assertEqual(headers["Retry-After"], "60")
        self.assertEqual(desk.handle(None, "GET", "/secret.txt")[0], 404)


class ServerTest(unittest.TestCase):
    def test_over_http(self):
        with tempfile.TemporaryDirectory() as d:
            run, _ = fake_generate()
            builds = desk.Builds(Path(d) / "desk", run=run, out=lambda s: None)
            builds.build()
            srv = desk.server(builds, "127.0.0.1", 0)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{srv.server_address[1]}"
            try:
                with urllib.request.urlopen(base + "/") as r:
                    self.assertEqual(r.read(), b"<p>desk 1</p>")
                    self.assertEqual(r.headers["Cache-Control"], "no-cache")
                req = urllib.request.Request(base + "/", data=b"x=1", method="POST")
                with self.assertRaises(urllib.error.HTTPError) as e:
                    urllib.request.urlopen(req)
                self.assertEqual(e.exception.code, 405)
                e.exception.close()
            finally:
                srv.shutdown()
                srv.server_close()


class CliTest(unittest.TestCase):
    def test_swarm_desk_calls_serve(self):
        got = {}
        orig = desk.serve
        desk.serve = lambda *a, **kw: got.setdefault("args", a) and 0
        try:
            with tempfile.TemporaryDirectory() as d:
                class L:
                    dir = Path(d)
                    out = print
                swarm.main(["desk", "--port", "9999", "--repo", "o/r"], launcher=L())
        finally:
            desk.serve = orig
        self.assertEqual(got["args"][1:], ("127.0.0.1", 9999, "o/r"))


if __name__ == "__main__":
    unittest.main()
