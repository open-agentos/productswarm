"""Tests for dashboard/generate.py. Run: python3 -m unittest discover -s dashboard

Uses canned API data and, for the end-to-end test, a fake `gh` on PATH, so nothing
touches GitHub.
"""
import datetime as dt
import json
import os
import stat
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import generate as g  # noqa: E402
import live  # noqa: E402

REPO = "open-agentos/productswarm"
NOW = dt.datetime(2026, 11, 2, 12, 0, tzinfo=dt.timezone.utc)
IDLE = dt.timedelta(minutes=15)
BOT = "productswarm-builder[bot]"


def ts(minutes_ago: int) -> str:
    return (NOW - dt.timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def ev(sid, event, minutes_ago, role="builder", **fields):
    return {"schema_version": 1, "ts": ts(minutes_ago), "session_id": sid, "repo": REPO,
            "role": role, "model": "claude-opus-5-5", "event": event, **fields}


def tracking(n, sid, login=BOT, state="open"):
    return {"number": n, "title": f"[heartbeat] builder {sid}", "state": state,
            "user": {"login": login}, "labels": [], "html_url": f"https://x/{n}",
            "created_at": ts(60),
            "body": f"<!-- productswarm-heartbeat schema_version=1 session_id={sid} -->\nHeartbeat.\n"}


def issue(n, title, labels=(), state="open"):
    return {"number": n, "title": title, "state": state, "user": {"login": "mattmcalister"},
            "labels": [{"name": lb} for lb in labels], "html_url": f"https://x/{n}",
            "created_at": ts(120), "body": ""}


def comment(events, login=BOT):
    lines = "\n".join(json.dumps(e) for e in events)
    return {"user": {"login": login}, "body": f"```jsonl\n{lines}\n```\n\n-- builder (claude-opus-5-5)\n"}


def build(issues, comments, prs=()):
    return g.build({"repo": REPO, "issues": issues, "comments": comments, "prs": list(prs)}, NOW, IDLE)


class StatusTest(unittest.TestCase):
    def status(self, events, closed=False, issues=()):
        data = [tracking(50, "s1", state="closed" if closed else "open"), *issues]
        return build(data, {50: [comment(events)]})["sessions"][0]

    def test_active(self):
        s = self.status([ev("s1", "session_started", 10), ev("s1", "working_on", 5, issue=4)])
        self.assertEqual((s["status"], s["issue"], s["last_event"]), ("active", 4, "working_on"))

    def test_idle_after_threshold(self):
        self.assertEqual(self.status([ev("s1", "working_on", 16, issue=4)])["status"], "idle")

    def test_stopped(self):
        self.assertEqual(self.status([ev("s1", "working_on", 5, issue=4),
                                      ev("s1", "stopped", 1)])["status"], "stopped")

    def test_closed_tracking_issue_is_stopped(self):
        self.assertEqual(self.status([ev("s1", "heartbeat", 1)], closed=True)["status"], "stopped")

    def test_blocked_on_open_question_even_when_quiet(self):
        s = self.status([ev("s1", "blocked", 60, issue=4, gov_question=26),
                         ev("s1", "prompt_submitted", 40), ev("s1", "heartbeat", 30)],
                        issues=[issue(26, "GOV-Q: x", ["gov:question"])])
        self.assertEqual((s["status"], s["gov_question"]), ("blocked", 26))

    def test_not_blocked_once_question_closed(self):
        s = self.status([ev("s1", "blocked", 5, gov_question=26)],
                        issues=[issue(26, "GOV-Q: x", ["gov:question"], state="closed")])
        self.assertEqual((s["status"], s["gov_question"]), ("active", None))

    def test_working_on_after_blocked_unblocks(self):
        s = self.status([ev("s1", "blocked", 10, gov_question=26), ev("s1", "working_on", 5, issue=6)],
                        issues=[issue(26, "GOV-Q: x", ["gov:question"])])
        self.assertEqual((s["status"], s["issue"]), ("active", 6))

    def test_pr_shown_while_on_its_issue(self):
        s = self.status([ev("s1", "pr_opened", 10, issue=4, pr=27), ev("s1", "heartbeat", 5, issue=4)])
        self.assertEqual((s["issue"], s["pr"]), (4, 27))

    def test_old_pr_dropped_after_moving_to_new_issue(self):
        s = self.status([ev("s1", "pr_opened", 10, issue=4, pr=27), ev("s1", "working_on", 5, issue=6)])
        self.assertEqual((s["issue"], s["pr"]), (6, None))

    def test_no_events_is_idle(self):
        self.assertEqual(self.status([])["status"], "idle")


class TrustTest(unittest.TestCase):
    def test_ignores_comments_from_other_authors(self):
        m = build([tracking(50, "s1")], {50: [comment([ev("s1", "session_started", 30)]),
                                              comment([ev("s1", "stopped", 1)], login="mallory")]})
        self.assertEqual(m["sessions"][0]["status"], "idle")

    def test_ignores_issues_without_marker_or_bot_author(self):
        m = build([tracking(50, "s1", login="mallory"), issue(51, "[heartbeat] builder s2")], {})
        self.assertEqual(m["sessions"], [])

    def test_drops_events_for_other_sessions_roles_or_with_prompt(self):
        events = [ev("s1", "working_on", 3, issue=4),
                  ev("other", "working_on", 2, issue=9),
                  ev("s1", "working_on", 2, role="planner", issue=9),
                  ev("s1", "prompt_submitted", 1, prompt="secret")]
        s = build([tracking(50, "s1")], {50: [comment(events)]})["sessions"][0]
        self.assertEqual((s["issue"], s["last_event"]), (4, "working_on"))

    def test_bad_lines_and_later_fences_are_skipped(self):
        body = ("```jsonl\nnot json\n" + json.dumps(ev("s1", "working_on", 2, issue=4)) + "\n```\n"
                "```jsonl\n" + json.dumps(ev("s1", "stopped", 1)) + "\n```\n")
        s = build([tracking(50, "s1")], {50: [{"user": {"login": BOT}, "body": body}]})["sessions"][0]
        self.assertEqual(s["status"], "active")

    def test_events_are_ordered_by_timestamp(self):
        s = build([tracking(50, "s1")], {50: [comment([ev("s1", "working_on", 1, issue=6)]),
                                              comment([ev("s1", "working_on", 9, issue=4)])]})
        self.assertEqual(s["sessions"][0]["issue"], 6)


class PageTest(unittest.TestCase):
    def model(self):
        issues = [tracking(50, "s1"), tracking(51, "s2"), tracking(52, "s3", state="closed"),
                  issue(4, "Dashboard <generator>"), issue(26, "GOV-Q: build?", ["gov:question", "gov:deliberating"])]
        comments = {50: [comment([ev("s1", "blocked", 2, issue=4, gov_question=26)])],
                    51: [comment([ev("s2", "working_on", 1, issue=4)])],
                    52: [comment([ev("s3", "stopped", 300)])]}
        prs = [{"number": 30, "title": "Add <b>generator</b>", "url": "https://x/pull/30",
                "author": {"login": "app/productswarm-builder"}, "isDraft": False,
                "createdAt": ts(5), "reviewDecision": "", "closingIssuesReferences": [{"number": 4}]}]
        return build(issues, comments, prs)

    def test_model(self):
        m = self.model()
        self.assertEqual([s["status"] for s in m["sessions"]], ["blocked", "active", "stopped"])
        self.assertEqual([g_["number"] for g_ in m["gov"]], [26])
        self.assertEqual([s["session_id"] for s in m["gov"][0]["waiting"]], ["s1"])
        self.assertEqual(m["gov"][0]["labels"], ["gov:deliberating"])
        self.assertEqual(m["prs"][0]["closes"], [{"number": 4, "title": "Dashboard <generator>"}])

    def test_read_state_for_the_hosted_desk(self):
        # --prev (#664): the hosted desk carries precedent forward from its own state.json.
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "state.json"
            self.assertIsNone(g.read_state(f))
            f.write_text("not json")
            self.assertIsNone(g.read_state(f))
            f.write_text("[1]")
            self.assertIsNone(g.read_state(f))
            f.write_text('{"built_at": "2026-11-09T08:00:00Z"}')
            self.assertEqual(g.read_state(f), {"built_at": "2026-11-09T08:00:00Z"})

    def test_render_escapes_and_links(self):
        page = g.render(self.model())["operations.html"]
        self.assertNotIn("<b>generator</b>", page)
        self.assertIn("Add &lt;b&gt;generator&lt;/b&gt;", page)
        self.assertIn("Dashboard &lt;generator&gt;", page)
        self.assertIn(f"https://github.com/{REPO}/issues/26", page)
        self.assertIn("1 stopped", page)

    def test_every_page_keeps_the_shell(self):
        pages = g.render(self.model())
        self.assertEqual(list(pages), ["bridge.html", "commissions.html", "index.html", "operations.html", "decisions.html",
                                       "authority.html"])   # the Bridge (#926) leads the footer
        for name, page in pages.items():
            head = page.split("</head>")[0]
            self.assertIn('<meta name="robots" content="noindex, nofollow">', head, name)
            self.assertIn('<meta http-equiv="refresh" content="300">', head, name)
            self.assertIn('<meta name="viewport" content="width=device-width, initial-scale=1">', head, name)
            # Only the desk carries a script: the live refresh, allowed by hash (#411).
            rest = page.replace(f"<script>{live.script()}</script>", "") if name == "index.html" else page
            self.assertNotIn("<script", rest.lower(), name)
            # Read-only until Google login (#664): no form or button to post anything with.
            for tag in ("<form", "<button", "<input"):
                self.assertNotIn(tag, page.lower(), name)
            self.assertIn('http-equiv="Content-Security-Policy"', head, name)
            self.assertIn("#F4F3EE", head, name)   # one look (layout.py)
            self.assertIn('src:url("fonts/IBMPlexSans-Regular-Latin1.woff2")', head, name)
            # Nothing loaded from a third party: the only URLs in the head are the fonts.
            self.assertNotIn("//", head.replace("http-equiv", ""), name)
            foot = page.split('<footer class="foot">')[1]
            for other in pages:
                if other == name:
                    self.assertIn('aria-current="page"', foot)
                else:
                    self.assertIn(f'href="{other}"', foot, name)

    def test_each_section_lands_on_its_page(self):
        m = self.model()
        m["progress"] = None   # progress.render's own tests cover it; it needs its own data
        pages = g.render(m)
        where = {
            "index.html": ["<h1>The desk</h1>"],
            "operations.html": ["<h2>Needs you (", "spent today (est.)", "<h2>Sessions</h2>",
                                "<h2>Open pull requests</h2>", "<h2>Actions reviewer</h2>",
                                "<h2>Spend per day (est.)</h2>"],
            "decisions.html": ["<h2>Governance</h2>", "<h3>Decision log (",
                               "<h3>Open gov questions (", "<h3>Lapsed questions</h3>"],
        }
        for name, heads in where.items():
            for h in heads:
                self.assertIn(h, pages[name], h)
                for other in set(pages) - {name}:
                    self.assertNotIn(h, pages[other], f"{h} also on {other}")
        self.assertIn('href="operations.html"', pages["index.html"].split("<footer")[0])
        self.assertIn('href="decisions.html"', pages["index.html"].split("<footer")[0])

    def test_decisions_page_has_the_full_log(self):
        rows = "\n".join(f"| [GOV-{n:04d}](decisions/GOV-{n:04d}-x.md) | Ruling {n} | ops | rule | in force | 2027-06-01 |"
                         for n in range(1, 13))
        index = "| ID | Ruling | Domain | Shape | Status | Review by |\n|---|---|---|---|---|---|\n" + rows
        m = g.build({"repo": REPO, "issues": [], "comments": {}, "prs": [], "index": index}, NOW, IDLE)
        pages = g.render(m)
        self.assertIn("<h3>Decision log (12)</h3>", pages["decisions.html"])
        for n in range(1, 13):
            self.assertIn(f">GOV-{n:04d}</a>", pages["decisions.html"])
        self.assertNotIn("Decision log", pages["operations.html"] + pages["index.html"])


FAKE_GH = r"""#!/usr/bin/env python3
import json, os, sys
a = sys.argv[1:]
data = json.load(open(os.environ["FAKE_GH_DATA"]))
if a[:2] == ["api", "graphql"]:
    print(json.dumps(data.get("graphql", {})))
elif a[:2] == ["issue", "view"]:
    print(json.dumps(data.get("issue_view", {})))
elif a[:1] == ["api"]:
    path = a[2]
    key = "open" if "state=open" in path else "closed" if "state=closed" in path else path.split("?")[0]
    for item in data.get(key, []):
        print(json.dumps(item))
elif a[:2] == ["pr", "list"]:
    print(json.dumps(data["prs"]))
else:
    sys.exit(1)
"""


class EndToEndTest(unittest.TestCase):
    def test_main_writes_page(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            fake = d / "gh"
            fake.write_text(FAKE_GH)
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
            now = dt.datetime.now(dt.timezone.utc)
            recent = (now - dt.timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
            e = {**ev("s1", "working_on", 0, issue=4), "ts": recent}
            (d / "data.json").write_text(json.dumps({
                "open": [tracking(50, "s1"), issue(4, "Dashboard generator"),
                         {"number": 30, "pull_request": {}, "title": "a PR"}],
                "closed": [],
                f"repos/{REPO}/issues/50/comments": [comment([e])],
                "prs": [],
                "graphql": {"data": {"repository": {"i331": {"state": "OPEN"}}}},
                "issue_view": {"closedByPullRequestsReferences": []},
            }))
            env = {"PATH": f"{d}{os.pathsep}{os.environ['PATH']}", "FAKE_GH_DATA": str(d / "data.json")}
            old = {k: os.environ.get(k) for k in env}
            os.environ.update(env)
            try:
                with mock.patch.object(g.precedent, "published", return_value=None):   # no Pages fetch in tests
                    rc = g.main(["--repo", REPO, "--out", str(d / "out" / "index.html")])
            finally:
                for k, v in old.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
            self.assertEqual(rc, 0)
            out = d / "out"
            self.assertIn("<h1>The desk</h1>", (out / "index.html").read_text())
            self.assertIn("<h2>Governance</h2>", (out / "decisions.html").read_text())
            self.assertIn("<h1>Authority map</h1>", (out / "authority.html").read_text())
            for f in g.layout.FONT_FILES:   # self-hosted beside the pages
                self.assertEqual((out / "fonts" / f).read_bytes(),
                                 (g.layout.FONTS_SRC / f).read_bytes())
            page = (out / "operations.html").read_text()
            self.assertIn("#4 Dashboard generator", page)
            self.assertIn("s-active", page)
            self.assertIn("<h2>v3 progress</h2>", page)
            self.assertIn("(<a href=\"https://github.com/open-agentos/productswarm/issues/331\">#331</a>): not run", page)
            self.assertIn("not started: no reds count until", page)
            st = json.loads((d / "out" / "state.json").read_text())   # beside the page (#400)
            self.assertEqual((st["schema"], st["repo"]), (1, REPO))
            self.assertEqual([s["issue"] for s in st["sessions"]], [4])


if __name__ == "__main__":
    unittest.main()
