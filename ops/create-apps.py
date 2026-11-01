#!/usr/bin/env python3
"""Create one GitHub App per agent role, using GitHub's App manifest flow.

Run it, open the printed URL, and click each role's button. GitHub asks you
to confirm the App, then redirects back here. This script exchanges the
one-time code for the App's credentials and saves them to
~/.config/productswarm/apps/<role>.json and <role>.pem (mode 0600).
It never prints the private key.

Usage: ops/create-apps.py [--org open-agentos] [--port 8765]
"""
import argparse
import html
import json
import os
import secrets
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

REPO_URL = "https://github.com/open-agentos/productswarm"
APPS_DIR = Path(os.environ.get("PRODUCTSWARM_APPS_DIR", Path.home() / ".config/productswarm/apps"))

# No `workflows` or `administration` permission for any role: Apps cannot change
# .github/workflows or repo settings, so ci-and-workflows and security stay with humans.
ROLES = {
    "planner": {"contents": "read", "issues": "write", "pull_requests": "read"},
    "builder": {"contents": "write", "issues": "write", "pull_requests": "write"},
    "reviewer": {"contents": "read", "issues": "write", "pull_requests": "write"},
    "docs": {"contents": "write", "issues": "write", "pull_requests": "write"},
}


def manifest(role, port):
    return {
        "name": f"productswarm-{role}",
        "url": REPO_URL,
        "description": f"productswarm {role} agent. Sessions act as this App; see GOVERNANCE.md.",
        "public": False,
        "redirect_url": f"http://127.0.0.1:{port}/callback",
        "hook_attributes": {"url": REPO_URL, "active": False},
        "default_permissions": {"metadata": "read", **ROLES[role]},
        "default_events": [],
    }


def convert(code):
    req = urllib.request.Request(
        f"https://api.github.com/app-manifests/{urllib.parse.quote(code)}/conversions",
        method="POST",
        headers={"Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def save(role, app):
    APPS_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(APPS_DIR, 0o700)
    pem = APPS_DIR / f"{role}.pem"
    fd = os.open(pem, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(app["pem"])
    (APPS_DIR / f"{role}.json").write_text(
        json.dumps({"app_id": app["id"], "slug": app["slug"]}, indent=2) + "\n"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--org", default="open-agentos")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    nonce = secrets.token_urlsafe(16)
    done = {r for r in ROLES if (APPS_DIR / f"{r}.json").exists()}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def page(self, body):
            data = f"<!doctype html><meta charset=utf-8><title>productswarm Apps</title><body style='font:16px system-ui;max-width:40em;margin:2em auto'>{body}</body>".encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            url = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(url.query)
            if url.path == "/callback":
                role, _, got = q.get("state", [""])[0].partition(".")
                if role not in ROLES or not secrets.compare_digest(got, nonce) or "code" not in q:
                    return self.page("<p>Unexpected callback. Ignored.</p><p><a href='/'>Back</a></p>")
                app = convert(q["code"][0])
                save(role, app)
                done.add(role)
                print(f"saved {role}: {app['slug']} (id {app['id']})", flush=True)
                install = f"https://github.com/apps/{app['slug']}/installations/new"
                return self.page(
                    f"<h2>Created {html.escape(app['slug'])}</h2>"
                    f"<p>1. <a href='{install}' target=_blank>Install it on productswarm</a> (choose <b>Only select repositories</b> → productswarm).</p>"
                    "<p>2. <a href='/'>Back to the list</a></p>"
                )
            action = f"https://github.com/organizations/{args.org}/settings/apps/new"
            rows = []
            for role in ROLES:
                if role in done:
                    rows.append(f"<li>{role}: created ✓</li>")
                    continue
                m = html.escape(json.dumps(manifest(role, args.port)), quote=True)
                rows.append(
                    f"<li><form method=post action='{action}?state={role}.{nonce}' style='display:inline'>"
                    f"<input type=hidden name=manifest value=\"{m}\">"
                    f"<button>Create productswarm-{role}</button></form></li>"
                )
            self.page("<h2>productswarm role Apps</h2><ul>" + "".join(rows) + "</ul>"
                      "<p>Install each App on productswarm after creating it. Press Ctrl-C in the terminal when all are done.</p>")

    print(f"Open http://127.0.0.1:{args.port}/  (credentials go to {APPS_DIR})", flush=True)
    HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
