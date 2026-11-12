"""swarm desk: serve the Desk live on the engine host, rebuilt on each webhook nudge (#664).

Operating model v2 (#651) moves the Desk off GitHub Pages and onto the engine host, behind
Caddy (ops/vps). It is public and read-only, and shows only what GitHub already shows
(GOV-0002, GOV-0004): the same pages dashboard/generate.py has always built.

A webhook only nudges. `swarm webhooks` touches ~/.productswarm/launcher/nudge and never
passes a payload on. This loop watches that file's mtime, as `swarm watch --serve` does, and
on a change it runs generate.py, which re-reads everything from GitHub. So a forged or
replayed event can at most cause one extra build (the reconciler's rule, GOV-0020).

    builds   at start, on each nudge (at most one build every MIN_GAP seconds; a nudge inside
             the gap builds when it ends) and every SWEEP_MINUTES as a backstop. Each build
             runs generate.py into a fresh desk/build-<n>/ and, only if it wrote the pages and
             state.json, swaps the desk/live symlink to it, so a reader never sees half a
             build. A skipped or failed build leaves the last good desk up. generate.py's own
             allowance check (PAGE_NEEDS) still applies.
    serves   GET and HEAD only, on 127.0.0.1:8080 by default: /, the four pages, state.json
             and fonts/. Any other method is 405 and any other path 404. There is no form
             and no POST route until Google login.
    trouble  trouble_panel(report) renders `swarm trouble --json` per Goal and Area as a
             read-only HTML section (#889). It is not served yet.

Usage: swarm desk [--host 127.0.0.1] [--port 8080] [--repo owner/name]. generate.py reads
GitHub with `gh`, so it uses GH_TOKEN from the environment: on the host, a read-only token.
"""
from __future__ import annotations

import html
import http.server
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
GENERATE = ROOT / "dashboard" / "generate.py"
DESK_DIR = "desk"            # under ~/.productswarm/launcher
LIVE = "live"                # symlink to the build being served
STATE = "state.json"
NUDGE_FILE = "nudge"         # webhooks.NUDGE_FILE; not imported so the desk needs no db
MIN_GAP = 120                # seconds from one build's start before a nudge starts another
SWEEP_MINUTES = 10           # a build this often with no nudge, inside the desk's 15-min stale mark
POLL = 0.5                   # seconds between looks at the nudge file
BUILD_TIMEOUT = 600          # seconds before a hung generate.py run is killed

# The only paths served: a page, state.json or a font file. Nothing else, so no traversal.
PATH_RE = re.compile(r"/(?:[a-z]+\.html|state\.json|fonts/[A-Za-z0-9][A-Za-z0-9._-]*)")
TYPES = {".html": "text/html; charset=utf-8", ".json": "application/json",
         ".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8"}
HEADERS = {"X-Content-Type-Options": "nosniff", "X-Robots-Tag": "noindex, nofollow",
           "Referrer-Policy": "no-referrer",
           # The pages' own meta CSP can't say frame-ancestors; this adds only that.
           "Content-Security-Policy": "frame-ancestors 'none'"}


class Builds:
    """desk/build-<n>/ directories and the desk/live symlink to the one being served."""

    def __init__(self, root: Path, repo: str | None = None, run=subprocess.run, out=print):
        self.root, self.repo, self.run, self.out = Path(root), repo, run, out
        self.root.mkdir(parents=True, exist_ok=True)

    def live(self) -> Path | None:
        """The build being served, or None before the first good one."""
        link = self.root / LIVE
        if not link.is_symlink():
            return None
        target = self.root / os.readlink(link)
        return target if target.is_dir() else None

    def command(self, new: Path) -> list[str]:
        cmd = [sys.executable, str(GENERATE), "--out", str(new / "index.html")]
        if self.repo:
            cmd += ["--repo", self.repo]
        live = self.live()
        if live is not None:
            cmd += ["--prev", str(live / STATE)]   # precedent carries its counts forward
        return cmd

    def build(self) -> bool:
        """Run generate.py into a new build and serve it if it wrote the pages. True if it did."""
        new = self.root / f"build-{time.time_ns()}"
        new.mkdir()
        try:
            r = self.run(self.command(new), capture_output=True, text=True, timeout=BUILD_TIMEOUT)
        except (OSError, subprocess.SubprocessError) as e:
            self.out(f"swarm desk: build failed: {e}; the last good desk stays up")
            shutil.rmtree(new, ignore_errors=True)
            return False
        lines = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
        if r.returncode != 0 or not (new / "index.html").is_file() or not (new / STATE).is_file():
            why = lines[-1] if lines else f"exit {r.returncode}"
            self.out(f"swarm desk: not published: {why}")
            shutil.rmtree(new, ignore_errors=True)
            return False
        self.publish(new)
        self.out(f"swarm desk: published {new.name}" + (f": {lines[-1]}" if lines else ""))
        return True

    def publish(self, new: Path) -> None:
        """Point desk/live at `new` in one rename, then remove builds older than the last one,
        which an in-flight request may still be reading."""
        old = self.live()
        tmp = self.root / f".{LIVE}.tmp"
        tmp.unlink(missing_ok=True)
        os.symlink(new.name, tmp)
        os.replace(tmp, self.root / LIVE)
        keep = {new.name} | ({old.name} if old else set())
        for d in self.root.glob("build-*"):
            if d.name not in keep:
                shutil.rmtree(d, ignore_errors=True)


class Loop:
    """Build at start, then on each nudge (spaced by MIN_GAP) and every `sweep` seconds."""

    def __init__(self, builds: Builds, nudge: Path, sweep: float = SWEEP_MINUTES * 60,
                 gap: float = MIN_GAP, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.builds, self.nudge, self.sweep, self.gap = builds, Path(nudge), sweep, gap
        self.clock, self.sleep = clock, sleep
        self.nudged: int | None = None
        self.started: float | None = None

    def mtime(self) -> int | None:
        try:
            return self.nudge.stat().st_mtime_ns
        except FileNotFoundError:
            return None

    def wait(self) -> None:
        """Until the nudge file changes (and MIN_GAP has passed since the last build started)
        or the sweep is due, whichever comes first. A burst of nudges makes one more build."""
        end = self.clock() + self.sweep
        while (left := end - self.clock()) > 0:
            m = self.mtime()
            if m is not None and m != self.nudged:
                gap = (self.started if self.started is not None else float("-inf")) + self.gap - self.clock()
                if gap <= 0:
                    return
                self.sleep(min(gap, left))
                continue
            self.sleep(min(POLL, left))

    def run(self, ticks: int | None = None) -> None:
        n = 0
        while ticks is None or n < ticks:
            if n:
                self.wait()
            self.nudged, self.started = self.mtime(), self.clock()
            try:
                self.builds.build()
            except Exception as e:   # never let one bad build stop the desk refreshing
                self.builds.out(f"swarm desk: build error: {e}")
            n += 1


def handle(live: Path | None, method: str, path: str) -> tuple[int, dict[str, str], bytes]:
    """One request -> (status, headers, body). Read-only: GET and HEAD, known files only."""
    headers = dict(HEADERS)
    if method not in ("GET", "HEAD"):
        headers["Allow"] = "GET, HEAD"
        return 405, headers | {"Content-Type": "text/plain; charset=utf-8"}, b"read-only\n"
    path = path.split("?", 1)[0].split("#", 1)[0]
    if path == "/":
        path = "/index.html"
    ctype = TYPES.get(Path(path).suffix)
    if not PATH_RE.fullmatch(path) or ctype is None:
        return 404, headers | {"Content-Type": "text/plain; charset=utf-8"}, b"not found\n"
    if live is None:
        headers |= {"Content-Type": "text/plain; charset=utf-8", "Retry-After": "60"}
        return 503, headers, b"the desk's first build hasn't finished; try again in a minute\n"
    file = live / path.lstrip("/")
    try:
        body = file.read_bytes() if file.is_file() and not file.is_symlink() else None
    except OSError:
        body = None
    if body is None:
        return 404, headers | {"Content-Type": "text/plain; charset=utf-8"}, b"not found\n"
    cache = "public, max-age=86400" if path.startswith("/fonts/") else "no-cache"
    return 200, headers | {"Content-Type": ctype, "Cache-Control": cache}, body


# ---------------------------------------------------------------- trouble panel (#889)
#
# A read-only panel per open Goal and Area from `swarm trouble --json` (trouble.report()):
# #760's four questions. How does each done-test criterion stand? What is stuck, and since
# when? What waits on the owner, and for how long? What was done on the owner's authority?
# An `unmeasured` criterion is shown as unmeasured, never as on track. Pure: dict in, HTML out.

STATUS = {"met": "met", "progress": "in progress", "failing": "failing", "counted": "counted",
          "unmeasured": "unmeasured: not known to be on track"}
LINK_RE = re.compile(r"https://github\.com/[^\s\"'<>]*")


def _esc(x) -> str:
    return html.escape("" if x is None else str(x))


def _link(url: str | None, text: str) -> str:
    """A link only to github.com: the report's URLs come from GitHub, but don't trust them."""
    if url and LINK_RE.fullmatch(url):
        return f'<a href="{_esc(url)}">{_esc(text)}</a>'
    return _esc(text)


def _age(hours) -> str:
    if hours is None:
        return "age unknown"
    return f"{hours / 24:.0f}d" if hours >= 48 else f"{hours:.0f}h"


def _items(head: str, xs: list[dict], since_word: str) -> str:
    if not xs:
        return f'<h4>{_esc(head)}</h4><p class="none">none</p>'
    rows = "".join(
        f'<li class="{_esc(x.get("kind"))}">{_link(x.get("url"), x.get("ref") or "")} '
        f'{_esc(x.get("reason"))} <span class="age">({since_word} '
        f'{_esc((x.get("since") or "")[:10] or "?")}, {_age(x.get("age_hours"))})</span></li>'
        for x in xs)
    return f"<h4>{_esc(head)}</h4><ul>{rows}</ul>"


def _sections(s: dict, hours) -> str:
    return (_items("Stuck", s.get("stuck") or [], "since")
            + _items("Waiting on the owner", s.get("waiting") or [], "waiting since")
            + _items(f"On the owner's authority, last {hours}h", s.get("authority") or [], "at"))


def trouble_panel(report: dict) -> str:
    """The trouble panel as an HTML <section>, from `swarm trouble --json`."""
    hours = report.get("authority_hours", 24)
    out = [f'<section class="trouble"><h2>Trouble</h2><p class="muted">{_esc(report.get("repo"))}, '
           f'from swarm trouble at {_esc(report.get("generated_at"))}</p>']
    scopes = report.get("scopes") or []
    if not scopes:
        out.append('<p class="none">No open Goal or Area.</p>')
    for s in scopes:
        date = ""
        if s.get("date"):
            date = f' <span class="date">date {_esc(s["date"])}'
            date += ' <strong class="missed">MISSED</strong></span>' if s.get("date_missed") else "</span>"
        out.append(f'<article class="scope"><h3>{_esc(s.get("type"))} '
                   f'{_link(s.get("url"), s.get("ref") or "")} {_esc(s.get("title"))}{date}</h3>')
        crit = s.get("progress") or []
        if crit:
            out.append("<h4>Progress</h4><ul>" + "".join(
                f'<li class="status-{_esc(c.get("status"))}"><strong>'
                f'{_esc(STATUS.get(c.get("status"), c.get("status")))}</strong> '
                f'{_esc(c.get("criterion"))} <span class="muted">({_esc(c.get("detail"))})</span></li>'
                for c in crit) + "</ul>")
        else:
            out.append('<h4>Progress</h4><p class="none">no done-test criteria found</p>')
        out.append(_sections(s, hours) + "</article>")
    outside = report.get("outside") or {}
    if any(outside.values()):
        out.append('<article class="scope outside"><h3>Under no Goal or Area</h3>'
                   + _sections(outside, hours) + "</article>")
    for e in report.get("errors") or []:
        out.append(f'<p class="error">not read: {_esc(e)}</p>')
    out.append("</section>")
    return "\n".join(out)


def make_handler(builds: Builds):
    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "productswarm"
        sys_version = ""

        def _answer(self, method: str) -> None:
            if method not in ("GET", "HEAD"):
                self.close_connection = True   # never read a body
            status, headers, body = handle(builds.live(), method, self.path)
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if method != "HEAD":
                self.wfile.write(body)

        def do_GET(self):
            self._answer("GET")

        def do_HEAD(self):
            self._answer("HEAD")

        def do_POST(self):
            self._answer("POST")

        def do_PUT(self):
            self._answer("PUT")

        def do_PATCH(self):
            self._answer("PATCH")

        def do_DELETE(self):
            self._answer("DELETE")

        def do_OPTIONS(self):
            self._answer("OPTIONS")

        def log_message(self, fmt, *args):   # silent: no request lines in logs
            pass

    return Handler


def server(builds: Builds, host: str = "127.0.0.1", port: int = 8080) -> http.server.ThreadingHTTPServer:
    return http.server.ThreadingHTTPServer((host, port), make_handler(builds))


def serve(state_dir: Path, host: str, port: int, repo: str | None = None, out=print) -> int:
    builds = Builds(Path(state_dir) / DESK_DIR, repo, out=out)
    srv = server(builds, host, port)
    loop = Loop(builds, Path(state_dir) / NUDGE_FILE)
    threading.Thread(target=loop.run, name="desk-builds", daemon=True).start()
    out(f"swarm desk: serving {builds.root / LIVE} on {host}:{srv.server_address[1]}, read-only; "
        f"rebuilt on each webhook nudge (at most every {MIN_GAP} s) and every {SWEEP_MINUTES} min")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0
