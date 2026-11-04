"""Tests for launcher/watch.py (`swarm watch`: --dry-run #89, real starts #90, [respond]
#113). Canned
GitHub data only; no test opens a Terminal window or starts Claude Code.

Run: python3 -m unittest discover -s launcher
"""
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import swarm  # noqa: E402
import watch  # noqa: E402
from test_swarm import Fake, FakeGit  # noqa: E402

G = swarm.dashboard()
REPO = "open-agentos/productswarm"
OWNER = "mattmcalister"
NOW = dt.datetime(2026, 11, 3, 12, 0, tzinfo=dt.timezone.utc)
ROLES = {"builder", "docs", "planner", "reviewer"}
SHA1, SHA2 = "a" * 40, "b" * 40


def trigger_lines(lines):
    """Dry-run output without the indented headless command under each trigger (#147)."""
    return [x for x in lines if not x.startswith("  ")]


def headless_argv(command: str) -> list[str]:
    """The ops/swarm-session argv in a window command, up to the result redirect."""
    import shlex
    (script,) = shlex.split(command[len("exec /bin/bash -c "):])
    return shlex.split(script.split("&& exec ", 1)[1].split(" >| ", 1)[0])


def ts(minutes_ago):
    return (NOW - dt.timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def question_body(raised="planner, on #87", domain="spend", rev="two-way", blast="repo"):
    return (f"### Domain\n\n{domain}\n\n### Context\n\nx\n\n### Reversibility\n\n{rev}\n\n"
            f"### Blast radius\n\n{blast}\n\n### Raised by\n\n{raised}\n")


def issue(n, labels=(), body="", title=None):
    return {"number": n, "title": title or f"issue {n}", "state": "open", "body": body,
            "html_url": f"https://github.com/{REPO}/issues/{n}", "created_at": ts(600),
            "labels": [{"name": x} for x in labels], "user": {"login": OWNER}}


def ev(label, actor=OWNER, eid=1, kind="labeled"):
    return {"id": eid, "event": kind, "label": {"name": label}, "actor": {"login": actor}}


def pr(n, head=SHA1, draft=False, closes=()):
    return {"number": n, "title": f"PR {n}", "url": f"https://github.com/{REPO}/pull/{n}",
            "author": {"login": "productswarm-builder[bot]"}, "isDraft": draft, "createdAt": ts(60),
            "reviewDecision": "", "closingIssuesReferences": [{"number": c} for c in closes],
            "headRefOid": head}


def review(state, commit, authority="pass"):
    """A reviewer App review, with the rubric lines roles/reviewer.md asks for."""
    return {"user": {"login": watch.REVIEWER}, "state": state, "commit_id": commit,
            "body": f"- **Bugs:** pass\n- **Scope:** pass\n- **Authority:** {authority}\n"}


def tracking(n, sid, role, on_issue, minutes_ago=1):
    """A live heartbeat session on issue `on_issue`: its tracking issue and one comment."""
    bot = f"productswarm-{role}[bot]"
    it = {**issue(n), "user": {"login": bot},
          "body": f"<!-- productswarm-heartbeat schema_version=1 session_id={sid} -->\nx"}
    e = {"schema_version": 1, "ts": ts(minutes_ago), "session_id": sid, "repo": REPO, "role": role,
         "model": "m", "event": "working_on", "issue": on_issue}
    return it, [{"user": {"login": bot}, "body": "```jsonl\n" + json.dumps(e) + "\n```\n"}]


class Scene:
    """Canned GitHub: one of each trigger, plus one session that's busy on #60."""

    def __init__(self):
        self.issues = [
            issue(49, ["ready"]),                                                      # build
            issue(60, ["ready"]),                                                      # busy
            issue(87, ["gov:question", "gov:ruled"], question_body(domain="governance")),  # record
            issue(88, ["gov:question", "ready"], question_body(raised="planner, on #87")),  # answer
        ]
        self.events = {49: [ev("ready", eid=11)], 60: [ev("ready", eid=12)],
                       87: [ev("gov:question", "productswarm-planner[bot]", 1), ev("gov:ruled", eid=13)],
                       88: [ev("ready", eid=14)]}
        self.prs = [pr(70, SHA1), pr(71, SHA2, draft=True)]
        self.reviewed = {70: set()}
        self.reviews = {}                      # PR -> reviewer reviews with state and body
        t_issue, t_comments = tracking(200, "busy-sid", "builder", 60)
        self.tracking = [t_issue]
        self.comments = {200: t_comments}
        self.reads = 0

    def data(self):
        return {"repo": REPO, "issues": self.issues + self.tracking, "comments": self.comments,
                "prs": self.prs, "reviews": self.all_reviews()}

    def all_reviews(self):
        """Every PR's reviewer reviews: bare ones for SHAs in `reviewed`, then `reviews`."""
        out = {n: [review("COMMENTED", c) for c in sorted(cs)] for n, cs in self.reviewed.items()}
        for n, rs in self.reviews.items():
            out.setdefault(n, []).extend(rs)
        return out

    def read(self, repo, idle, now):
        self.reads += 1
        model = G.build(self.data(), NOW, dt.timedelta(minutes=idle))
        return watch.World(model=model, issues=self.issues + self.tracking,
                           events={k: list(v) for k, v in self.events.items()},
                           reviewed={k: {r["commit_id"] for r in v}
                                     for k, v in self.all_reviews().items()})

    # The fresh reads `swarm watch` makes before each start (swarm launch's refusal checks).
    def heartbeat(self, repo, idle, now):
        return G.build(self.data(), NOW, dt.timedelta(minutes=idle))

    def get_issue(self, repo, n):
        found = [i for i in self.issues if i["number"] == n]
        return (found[0] if found else None), list(self.events.get(n, []))

    # The same data as `gh` output, for the test that runs the real readers.
    def gh(self, argv):
        if argv[1] == "pr":
            return json.dumps(self.prs)
        path = argv[3] if argv[2] == "--paginate" else argv[2]
        path = path.split(f"repos/{REPO}/", 1)[1].split("?")[0]
        parts = path.split("/")
        if path == "issues":
            items = self.issues + self.tracking if "state=open" in argv[3] else []
        elif parts[-1] == "comments":
            items = self.comments.get(int(parts[1]), [])
        elif parts[-1] == "events":
            items = self.events.get(int(parts[1]), [])
        elif parts[-1] == "reviews":
            items = self.all_reviews().get(int(parts[1]), [])
        else:                                    # issues/N: gh_json, one object
            return json.dumps(self.get_issue(REPO, int(parts[1]))[0])
        return "\n".join(json.dumps(i) for i in items)


class WatchTest(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        (self.home / "launcher").mkdir()
        self.fake = Fake(self.home / "launcher")
        self.lines = []
        self.l = swarm.Launcher(self.home, run=self.fake.run, proc=self.fake.proc, kill=self.fake.kill,
                                clock=self.fake.clock, sleep=lambda s: None, out=self.lines.append,
                                root=self.home / "repo", git=FakeGit())
        self.scene = Scene()
        # A fixture manifest, not the repo's: the owner's review_in_actions switch (#260)
        # mustn't change what these tests check (#285).
        (self.home / "fixture").mkdir()
        self.path = write_manifest(self.home / "fixture", ALL_CAPPED, max_live=2)
        self.w = watch.Watch(self.l, REPO, OWNER, ROLES, read=self.scene.read, manifest_path=self.path)

    def kinds(self, ts_):
        return [(t.kind, t.ref) for t in ts_]

    def test_each_trigger_prints_once(self):
        first = self.w.tick(NOW)
        self.assertEqual(self.kinds(first), [("review", "PR #70"), ("record", "#87"), ("answer", "#88"),
                                             ("build", "#49")])
        self.assertEqual(trigger_lines(self.lines), [
            "[review] PR #70 head aaaaaaa not reviewed by the reviewer -> would start a reviewer pass",
            "[record] #87 gov:ruled by the owner, needs a record (domain governance) -> would start "
            "`launcher/swarm launch docs --issue 87`",
            "[answer] #88 ready by the owner -> would start `launcher/swarm launch planner --issue 88`",
            "[build] #49 ready by the owner -> would start `launcher/swarm launch builder --issue 49`",
        ])
        self.assertEqual(self.w.tick(NOW), [])
        self.assertEqual(self.w.tick(NOW), [])
        self.assertEqual(len(self.lines), 8)       # each with its headless command (#147)

    def test_dry_run_prints_the_full_headless_command_under_each_trigger(self):
        # #147: what a real start would run, with every flag, from swarm.toml.
        path = write_manifest(self.home, {"builder": 15, "docs": 5, "planner": 5, "reviewer": 5},
                              max_turns=200)
        w = watch.Watch(self.l, REPO, OWNER, ROLES, read=self.scene.read, manifest_path=path)
        w.tick(NOW)
        self.assertEqual(len(self.lines), 8)
        build = self.lines[self.lines.index(
            "[build] #49 ready by the owner -> would start `launcher/swarm launch builder --issue 49`") + 1]
        argv = headless_argv(build.strip())
        self.assertEqual(argv[1:6], ["builder", "--model", "m-builder", "--session-id", argv[5]])
        self.assertEqual(argv[6:], ["-p", swarm.opener("builder", 49), "--permission-mode", "auto",
                                    "--disallowedTools", *swarm.DENY, "--max-budget-usd", "15",
                                    "--max-turns", "200", "--output-format", "json"])
        self.assertIn(f">| {self.home}/launcher/{argv[5]}.result.json", build)
        self.assertEqual(self.fake.commands, [])
        self.assertFalse((self.home / "launcher" / "sessions.json").exists())

    def test_dry_run_says_why_there_is_no_headless_command(self):
        path = write_manifest(self.home, {r: 5 for r in ROLES - {"docs"}})
        w = watch.Watch(self.l, REPO, OWNER, ROLES, read=self.scene.read, manifest_path=path)
        w.tick(NOW)
        self.assertIn("  (no headless command: docs has no spend_cap_usd in swarm.toml)", self.lines)
        path = write_manifest(self.home, ALL_CAPPED, max_turns=None)
        w = watch.Watch(self.l, REPO, OWNER, ROLES, read=self.scene.read, manifest_path=path)
        w.tick(NOW)
        self.assertIn("  (no headless command: swarm.toml's [watch] table has no max_turns)", self.lines)

    def test_new_push_or_fresh_owner_label_is_a_new_trigger(self):
        self.w.tick(NOW)
        self.scene.reviewed[70] = {SHA1}
        self.assertEqual(self.w.tick(NOW), [])            # reviewed at its head: nothing
        self.scene.prs[0]["headRefOid"] = SHA2
        self.scene.events[49] += [ev("ready", eid=20, kind="unlabeled"), ev("ready", eid=21)]
        self.assertEqual(self.kinds(self.w.tick(NOW)), [("review", "PR #70"), ("build", "#49")])

    def test_labels_added_by_anyone_else_print_nothing(self):
        bot = "productswarm-planner[bot]"
        self.scene.events = {49: [ev("ready", bot)], 60: [], 87: [ev("gov:ruled", bot)],
                             88: [ev("ready", eid=1), ev("ready", bot, eid=2)]}
        self.assertEqual([t.kind for t in self.w.tick(NOW)], ["review"])

    def test_issue_with_a_live_session_prints_nothing(self):
        self.assertNotIn("#60", [t.ref for t in self.w.tick(NOW)])
        # A launcher session started on #49 that has no heartbeat yet counts too.
        self.w.seen.clear()
        self.l.start(swarm.Started("builder-issue-49", "builder", "m", "sid-49", self.fake.t, issue=49), [])
        self.assertNotIn("#49", [t.ref for t in self.w.tick(NOW)])

    def reviewer_on_heartbeat(self, sid, status_minutes_ago=1):
        """A reviewer on the heartbeat (idle once it's been quiet past idle_minutes)."""
        t_issue, t_comments = tracking(202, sid, "reviewer", None, status_minutes_ago)
        self.scene.tracking.append(t_issue)
        self.scene.comments[202] = t_comments

    def test_an_idle_owner_started_reviewer_doesnt_keep_reviews_quiet(self):
        # #132: reviewer-1 from `swarm up`, idle at its prompt, held reviews up for 20 minutes.
        self.l.start(swarm.Started("reviewer-1", "reviewer", "m", "up-sid", self.fake.t), [])
        self.reviewer_on_heartbeat("up-sid", status_minutes_ago=30)
        self.assertEqual(self.w.tick(NOW)[0].ref, "PR #70")
        self.assertIn("[review] PR #70 head aaaaaaa not reviewed by the reviewer -> would start a "
                      "reviewer pass", self.lines)

    def test_a_live_loop_started_reviewer_keeps_reviews_quiet(self):
        self.l.start(swarm.Started("reviewer-watch", "reviewer", "m", "watch-sid", self.fake.t,
                                   by="watch", budget_usd=5, max_turns=50), [])
        self.assertNotIn("review", [t.kind for t in self.w.tick(NOW)])      # starting, no heartbeat
        self.w.seen.clear()
        self.reviewer_on_heartbeat("watch-sid")
        self.assertNotIn("review", [t.kind for t in self.w.tick(NOW)])      # on the heartbeat

    def test_session_on_it_stops_then_it_fires(self):
        self.w.tick(NOW)
        self.scene.comments = {200: []}                    # the #60 session goes quiet...
        self.scene.tracking[0]["state"] = "closed"         # ...and stops
        self.assertEqual(self.kinds(self.w.tick(NOW)), [("build", "#60")])

    def test_build_skips_an_issue_an_open_pr_closes(self):
        # The PR's session has stopped, so nothing is live on #49, but its work waits on a merge.
        self.scene.prs.append(pr(93, SHA2, closes=(49,)))
        self.scene.reviewed[93] = {SHA2}
        self.assertNotIn("#49", [t.ref for t in self.w.tick(NOW)])
        self.scene.prs.pop()                               # PR closed unmerged: the issue fires
        self.assertEqual(self.kinds(self.w.tick(NOW)), [("build", "#49")])

    def test_record_needs_one_and_no_open_pr(self):
        self.scene.issues[2]["body"] = question_body(domain="spend")         # two-way, repo: no record
        self.assertNotIn("record", [t.kind for t in self.w.tick(NOW)])
        self.w.seen.clear()
        self.scene.issues[2]["body"] = question_body(rev="one-way")
        self.scene.prs.append(pr(92, closes=(87,)))
        self.scene.reviewed[92] = {SHA1}
        self.assertNotIn("record", [t.kind for t in self.w.tick(NOW)])

    def test_unknown_raised_by_is_skipped_with_a_reason(self):
        self.scene.issues[3]["body"] = question_body(raised="someone, on #3")
        (t,) = [t for t in self.w.tick(NOW) if t.kind == "answer"]
        self.assertIn("-> skipped: \"Raised by\" doesn't start with a known role ('someone, on #3')",
                      t.line())
        self.assertEqual(self.w.tick(NOW), [])            # printed once

    def test_dry_run_starts_nothing_and_writes_nothing(self):
        state = self.l.state_file
        self.l.save([swarm.Started("gone-1", "docs", "m", "gone", 0)])   # exited: live() would prune it
        before = state.read_text()
        with mock.patch.object(swarm.Launcher, "start", side_effect=AssertionError("started")), \
             mock.patch.object(swarm, "launch", side_effect=AssertionError("launch")), \
             mock.patch.object(swarm, "open_terminal", side_effect=AssertionError("terminal")):
            self.w.run(1, ticks=3, sleep=lambda s: None)
        self.assertEqual(self.fake.commands, [])
        self.assertEqual(self.fake.signals, [])
        self.assertEqual(state.read_text(), before)
        self.assertEqual(sorted(p.name for p in (self.home / "launcher").iterdir()), ["sessions.json"])
        self.assertEqual(self.scene.reads, 3)

    def test_github_error_is_reported_and_the_loop_goes_on(self):
        calls = []

        def flaky(*a):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("gh api failed: offline")
            return self.scene.read(*a)
        self.w.read = flaky
        self.w.run(1, ticks=2, sleep=lambda s: None)
        self.assertIn("swarm watch: gh api failed: offline; trying again next tick", self.lines)
        self.assertTrue(any(x.startswith("[build] #49") for x in self.lines))


class HelpersTest(unittest.TestCase):
    def test_raised_by(self):
        rb = lambda raised: watch.raised_by(question_body(raised=raised), ROLES)
        self.assertEqual(rb("builder (on #75)"), ("builder", ""))
        self.assertEqual(rb("planner, on #167 (C stage 1 planning, per the owner's answer there)"),
                         ("planner", ""))
        self.assertEqual(rb("planner"), ("planner", ""))
        self.assertEqual(rb("-- docs (claude-opus-5-5)"), ("docs", ""))
        self.assertEqual(rb("Builder, on #5"), ("builder", ""))
        # #271: only the asker counts, not a role named later in the text.
        self.assertEqual(rb("owner, after the first Actions reviewer test on #251"),
                         (None, "\"Raised by\" doesn't start with a known role "
                                "('owner, after the first Actions reviewer test on #251')"))
        self.assertIsNone(rb("Claude (owner's coordinating session), drafted through the owner's account.")[0])
        self.assertIsNone(rb("someone, on #3")[0])
        self.assertIsNone(rb("builders, on #5")[0])
        self.assertIn("no \"Raised by\"", watch.raised_by("### Domain\n\nspend\n", ROLES)[1])

    def test_needs_record(self):
        self.assertIsNone(watch.needs_record(question_body()))
        self.assertEqual(watch.needs_record(question_body(blast="external")), "blast radius external")


def write_manifest(d: Path, caps: dict, max_live: int = 10, watch_table: bool = True,
                   max_turns: int | None = 50, review_in_actions: bool | None = None) -> Path:
    """A swarm.toml with every role, the given caps, and a [watch] table."""
    text = ""
    if watch_table:
        text = "[watch]\ninterval_minutes = 5\nmax_live = %d\n" % max_live
        text += "max_turns = %d\n" % max_turns if max_turns is not None else ""
        if review_in_actions is not None:
            text += f"review_in_actions = {str(review_in_actions).lower()}\n"
        text += "\n"
    for role in sorted(ROLES):
        text += f'[[session]]\nrole = "{role}"\ncount = 1\nmodel = "m-{role}"\n'
        if role in caps:
            text += f"spend_cap_usd = {caps[role]}\n"
        text += "\n"
    path = d / "swarm.toml"
    path.write_text(text)
    return path


ALL_CAPPED = {r: 10 for r in ROLES}


class StartTest(unittest.TestCase):
    """`swarm watch` without --dry-run (#90)."""

    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        (self.home / "launcher").mkdir()
        self.fake = Fake(self.home / "launcher")
        self.lines = []
        self.l = swarm.Launcher(self.home, run=self.fake.run, proc=self.fake.proc, kill=self.fake.kill,
                                clock=self.fake.clock, sleep=lambda s: None, out=self.lines.append,
                                root=self.home / "repo", git=FakeGit())
        self.scene = Scene()
        self.manifest(ALL_CAPPED)

    def manifest(self, caps, max_live=10, **kw):
        self.path = write_manifest(self.home, caps, max_live, **kw)

    def watcher(self):
        return watch.Watch(self.l, REPO, OWNER, ROLES, dry_run=False, manifest_path=self.path,
                           read=self.scene.read, get_issue=self.scene.get_issue,
                           get_heartbeat=self.scene.heartbeat)

    def started(self):
        return [(e.name, e.role, e.model, e.issue, e.by) for e in self.l.load()]

    def exit(self, name):
        """The session called `name` exits by itself."""
        (e,) = [e for e in self.l.load() if e.name == name]
        self.fake.procs.pop(self.l.pid(e))

    def inbox(self):
        return swarm.inbox_text([], NOW, G, watch.waiting(self.l))

    def test_each_trigger_starts_one_session_and_a_restart_starts_none(self):
        done = self.watcher().tick(NOW)
        self.assertEqual([(t.kind, t.ref) for t in done],
                         [("review", "PR #70"), ("record", "#87"), ("answer", "#88"), ("build", "#49")])
        self.assertEqual(self.started(), [
            ("reviewer-watch", "reviewer", "m-reviewer", None, "watch"),
            ("docs-issue-87", "docs", "m-docs", 87, "watch"),
            ("planner-issue-88", "planner", "m-planner", 88, "watch"),
            ("builder-issue-49", "builder", "m-builder", 49, "watch"),
        ])
        self.assertEqual(len(self.fake.commands), 4)
        self.assertIn("work on issue #49.", self.fake.commands[3])
        self.assertEqual(self.watcher().tick(NOW), [])              # same process, next check
        for name in ("reviewer-watch", "docs-issue-87", "planner-issue-88", "builder-issue-49"):
            self.exit(name)                                          # all stop; nothing is busy now
        self.assertEqual(self.watcher().tick(NOW), [])              # a restart over the same state
        self.assertEqual(len(self.fake.commands), 4)

    def test_each_run_is_headless_with_its_roles_budget_and_the_turn_ceiling(self):
        # #147 / GOV-0012: --max-budget-usd is the role's spend_cap_usd, --max-turns is [watch].
        self.manifest({"builder": 15, "docs": 5, "planner": 4.5, "reviewer": 3}, max_turns=120)
        self.watcher().tick(NOW)
        by_role = {}
        for c in self.fake.commands:
            argv = headless_argv(c)
            by_role[argv[1]] = argv
        self.assertEqual(sorted(by_role), ["builder", "docs", "planner", "reviewer"])
        for role, cap in (("builder", "15"), ("docs", "5"), ("planner", "4.5"), ("reviewer", "3")):
            argv = by_role[role]
            self.assertEqual(argv[argv.index("--max-budget-usd") + 1], cap)
            self.assertEqual(argv[argv.index("--max-turns") + 1], "120")
            self.assertEqual(argv[argv.index("--permission-mode") + 1], "auto")
            self.assertEqual(argv[argv.index("--output-format") + 1], "json")
            self.assertTrue(argv[argv.index("-p") + 1].startswith(f"You are the {role} "))
            i = argv.index("--disallowedTools") + 1
            self.assertEqual(tuple(argv[i:i + len(swarm.DENY)]), swarm.DENY)
        self.assertEqual({(e.budget_usd, e.max_turns) for e in self.l.load() if e.role == "builder"},
                         {(15.0, 120)})

    def test_no_max_turns_starts_nothing_and_the_loop_goes_on(self):
        self.manifest(ALL_CAPPED, max_turns=None)
        w = self.watcher()
        self.assertEqual(w.run(5, ticks=2, sleep=lambda s: None), 0)
        self.assertEqual(self.fake.commands, [])
        self.assertEqual(sum("has no max_turns; starting nothing (GOV-0012)" in x for x in self.lines), 2)

    def test_a_fresh_owner_label_starts_again(self):
        self.watcher().tick(NOW)
        self.exit("builder-issue-49")
        self.scene.events[49] += [ev("ready", eid=20, kind="unlabeled"), ev("ready", eid=21)]
        self.assertEqual([t.ref for t in self.watcher().tick(NOW)], ["#49"])
        self.assertEqual(len(self.fake.commands), 5)

    def test_ceiling_holds_then_starts_in_order_when_a_slot_frees(self):
        self.manifest(ALL_CAPPED, max_live=2)
        w = self.watcher()
        self.assertEqual([t.ref for t in w.tick(NOW)], ["PR #70", "#87"])
        self.assertIn("[answer] #88 ready by the owner -> held: 2 of 2 sessions swarm watch started "
                      "are live (GOV-0010)", self.lines)
        inbox = self.inbox()
        self.assertIn("swarm watch is holding", inbox)
        self.assertIn("- [answer] #88 ready by the owner · held: 2 of 2", inbox)
        self.assertIn("- [build] #49 ready by the owner · held: 2 of 2", inbox)
        n = len(self.lines)
        self.assertEqual(w.tick(NOW), [])                    # still full: nothing new, nothing re-logged
        self.assertEqual(len(self.lines), n)
        # Sessions started by hand don't count towards the ceiling.
        self.l.start(swarm.Started("docs-1", "docs", "m", "by-hand", self.fake.t), self.l.live())
        self.assertEqual(w.tick(NOW), [])
        self.exit("docs-issue-87")
        self.assertEqual([t.ref for t in w.tick(NOW)], ["#88"])     # held longest, in order
        self.assertNotIn("[answer] #88", self.inbox())
        self.assertIn("[build] #49", self.inbox())
        self.exit("reviewer-watch")
        self.assertEqual([t.ref for t in w.tick(NOW)], ["#49"])
        self.assertEqual(self.inbox(), "Nothing is waiting on you.")
        self.assertEqual(len(self.fake.commands), 5)                  # 4 by watch, 1 by hand

    def test_a_role_with_no_cap_is_skipped_and_listed_until_it_has_one(self):
        self.manifest({r: 10 for r in ROLES if r != "builder"})
        w = self.watcher()
        self.assertNotIn("#49", [t.ref for t in w.tick(NOW)])
        self.assertNotIn("builder", [e.role for e in self.l.load()])
        self.assertIn("- [build] #49 ready by the owner · skipped: builder has no spend_cap_usd in "
                      "swarm.toml, and swarm watch starts only capped roles (GOV-0010)", self.inbox())
        self.manifest(ALL_CAPPED)                      # the owner adds a cap; read on the next check
        self.assertEqual([t.ref for t in w.tick(NOW)], ["#49"])

    def test_refusal_on_fresh_data_is_logged_and_the_trigger_is_done(self):
        # Between the tick's read and the start, someone starts a session on #49 by hand.
        t_issue, t_comments = tracking(201, "hand-sid", "builder", 49)
        real = self.scene.heartbeat

        def fresh(*a):
            self.scene.tracking.append(t_issue)
            self.scene.comments[201] = t_comments
            return real(*a)
        self.scene.heartbeat = fresh
        w = self.watcher()
        self.assertNotIn("#49", [e.issue for e in self.l.load()])
        w.tick(NOW)
        self.assertNotIn(49, [e.issue for e in self.l.load()])
        self.assertTrue(any(x.startswith("[build] #49 ready by the owner -> refused: #49 already has a "
                                         "live session: builder (active, session hand-sid)")
                            for x in self.lines), self.lines)
        self.scene.tracking.remove(t_issue)                   # that session stops...
        self.scene.heartbeat = real
        self.assertEqual(w.tick(NOW), [])                     # ...and the trigger stays done

    def test_label_changed_before_the_start_is_refused(self):
        # The tick saw the owner's `ready`; by the fresh re-check, a bot has re-added it.
        real = self.scene.get_issue

        def fresh(repo, n):
            issue, events = real(repo, n)
            return issue, events + ([ev("ready", "productswarm-planner[bot]", eid=30)] if n == 49 else [])
        self.scene.get_issue = fresh
        self.watcher().tick(NOW)
        self.assertNotIn(49, [e.issue for e in self.l.load()])
        self.assertTrue(any("#49's `ready` label was added by productswarm-planner[bot]" in x
                            for x in self.lines), self.lines)

    def test_record_rechecks_gov_ruled_not_ready(self):
        self.watcher().tick(NOW)
        self.assertIn(("docs-issue-87", "docs", "m-docs", 87, "watch"), self.started())

    def test_one_reviewer_pass_covers_every_pr_and_waits_for_a_live_reviewer(self):
        self.scene.prs.append(pr(72, SHA2))
        self.scene.reviewed[72] = set()
        # A reviewer an earlier `swarm watch` run started, still live.
        self.l.start(swarm.Started("reviewer-watch", "reviewer", "m", "rev-sid", self.fake.t,
                                   by="watch", budget_usd=5, max_turns=50), [])
        t_issue, t_comments = tracking(202, "rev-sid", "reviewer", None)
        self.scene.tracking.append(t_issue)
        self.scene.comments[202] = t_comments
        w = self.watcher()
        self.assertEqual([t.kind for t in w.tick(NOW)], ["record", "answer", "build"])   # reviewer live
        self.exit("reviewer-watch")                                                       # it stops
        self.scene.tracking.remove(t_issue)
        self.assertEqual([t.ref for t in w.tick(NOW)], ["PR #70", "PR #72"])
        self.assertEqual([e.name for e in self.l.load() if e.role == "reviewer"], ["reviewer-watch"])
        self.assertIn("[review] PR #72 head bbbbbbb not reviewed by the reviewer -> covered by "
                      "reviewer-watch", self.lines)

    def test_an_owner_started_reviewer_doesnt_hold_reviews(self):
        # #132: triggers() and refusal() share the rule, so the pass starts.
        self.l.start(swarm.Started("reviewer-1", "reviewer", "m", "up-sid", self.fake.t), [])
        t_issue, t_comments = tracking(202, "up-sid", "reviewer", None, minutes_ago=30)
        self.scene.tracking.append(t_issue)
        self.scene.comments[202] = t_comments
        self.assertIn("PR #70", [t.ref for t in self.watcher().tick(NOW)])
        self.assertIn(("reviewer-watch", "reviewer", "m-reviewer", None, "watch"), self.started())

    def test_refusal_waits_only_for_a_loop_started_reviewer(self):
        w = self.watcher()
        t = watch.Trigger(key="review:70:x", kind="review", ref="PR #70", why="", role="reviewer",
                          command="a reviewer pass")
        hand = swarm.Started("reviewer-1", "reviewer", "m", "up-sid", self.fake.t)
        mine = swarm.Started("reviewer-watch", "reviewer", "m", "w-sid", self.fake.t, by="watch")
        self.assertEqual(w.refusal(t, [hand], NOW), (None, False))
        self.assertEqual(w.refusal(t, [hand, mine], NOW), (None, True))

    def test_unknown_raised_by_is_logged_once_and_listed_in_the_inbox(self):
        # #271: #255's text names the reviewer, but the owner asked, so nothing starts.
        raised = "owner, after the first Actions reviewer test on #251"
        self.scene.issues[3]["body"] = question_body(raised=raised)
        w = self.watcher()
        w.tick(NOW)
        self.assertNotIn(88, [e.issue for e in self.l.load()])
        why = f"skipped: \"Raised by\" doesn't start with a known role ({raised!r})"
        self.assertEqual(sum(why in x for x in self.lines), 1)
        self.assertIn(f"- [answer] #88 ready by the owner · {why}", self.inbox())
        w.tick(NOW)
        self.assertEqual(sum(why in x for x in self.lines), 1)       # logged once
        self.assertNotIn(88, [e.issue for e in self.l.load()])
        self.scene.issues[3]["state"] = "closed"                    # the owner closes it
        w.tick(NOW)
        self.assertNotIn("#88", self.inbox())

    def test_role_first_raised_by_still_starts_that_role(self):
        self.scene.issues[3]["body"] = question_body(
            raised="planner, on #167 (C stage 1 planning, per the owner's answer there)")
        self.watcher().tick(NOW)
        self.assertIn((88, "planner"), [(e.issue, e.role) for e in self.l.load()])

    def test_a_failed_start_is_held_and_retried(self):
        self.fake.fail_for = {"builder"}
        w = self.watcher()
        w.tick(NOW)
        self.assertIn("failed to start", self.inbox())
        self.fake.fail_for = set()
        self.assertEqual([t.ref for t in w.tick(NOW)], ["#49"])

    def test_bad_manifest_starts_nothing_and_the_loop_goes_on(self):
        self.manifest(ALL_CAPPED, watch_table=False)
        self.watcher().run(1, ticks=2, sleep=lambda s: None)
        self.assertEqual(self.fake.commands, [])
        self.assertEqual(sum("has no [watch] table; starting nothing (GOV-0010)" in x for x in self.lines), 2)

    def test_ls_shows_sessions_started_by_watch(self):
        self.watcher().tick(NOW)
        model = self.scene.heartbeat(REPO, 15, NOW)
        rows = swarm.ls_rows(model, self.l.live(), self.l.state, NOW, lambda t, n: "now")
        self.assertIn(["builder-issue-49", "builder", "m-builder", "-", "no heartbeat yet", "-", "-",
                       "running, by watch", self.l.load()[3].session_id], rows)

    def test_never_signals_and_only_reads_github(self):
        """The real readers (gather, gh_issue, heartbeat) over a fake `gh`: every call is a read."""
        calls = []

        def run(argv, **kw):
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, self.scene.gh(argv), "")
        fake_sub = types.SimpleNamespace(run=run, SubprocessError=subprocess.SubprocessError)
        w = watch.Watch(self.l, REPO, OWNER, ROLES, dry_run=False, manifest_path=self.path)
        with mock.patch.object(G, "subprocess", fake_sub):
            w.run(1, ticks=3, sleep=lambda s: None)
            (e,) = [e for e in self.l.load() if e.name == "builder-issue-49"]
            self.l.result_file(e.session_id).write_text(
                "swarm-session: builder\n" + json.dumps({"type": "result", "subtype": "error_max_budget_usd",
                                                         "is_error": True, "total_cost_usd": 9.87}))
            self.exit("builder-issue-49")
            w.run(1, ticks=1, sleep=lambda s: None)
        self.assertEqual(len(self.fake.commands), 4)            # it did start sessions
        # #149: the ending and cost are recorded locally, and none of it reaches GitHub.
        self.assertEqual([r.get("cost_usd") for r in watch.runs(self.l) if r["name"] == "builder-issue-49"], [9.87])
        self.assertFalse(any("9.87" in a or "ended at cap" in a for argv in calls for a in argv))
        self.assertEqual(self.fake.signals, [])
        self.assertTrue(calls)
        writes = {"-X", "--method", "-f", "-F", "--field", "--raw-field", "--input"}
        for argv in calls:
            self.assertEqual(argv[0], "gh")
            if argv[1] == "api":
                self.assertFalse(writes & set(argv), argv)
            else:
                self.assertEqual(argv[1:3], ["pr", "list"], argv)


HOLD_LOCK = """
import fcntl, os, sys, time
fd = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)
fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
os.ftruncate(fd, 0); os.write(fd, f"{os.getpid()}\\n".encode())
print("locked", flush=True)
time.sleep(60)
"""


class LockTest(unittest.TestCase):
    """One watcher at a time (#273)."""
    setUp = StartTest.setUp
    manifest = StartTest.manifest
    watcher = StartTest.watcher

    def holder(self):
        """Another process holding the lock as a running watcher does; killed at cleanup."""
        p = subprocess.Popen([sys.executable, "-c", HOLD_LOCK, str(self.l.dir / watch.LOCK_FILE)],
                             stdout=subprocess.PIPE, text=True)
        self.addCleanup(lambda: (p.kill(), p.wait(), p.stdout.close()))
        self.assertEqual(p.stdout.readline().strip(), "locked")
        return p

    def test_a_second_watcher_is_refused_naming_the_running_ones_pid(self):
        p = self.holder()
        self.assertEqual(self.watcher().run(1, ticks=1, sleep=lambda s: None), 1)
        self.assertEqual(self.fake.commands, [])
        self.assertEqual(self.scene.reads, 0)
        self.assertFalse(watch.state_path(self.l).exists())
        (line,) = self.lines
        self.assertIn(f"refused: another swarm watch is already running (pid {p.pid};", line)

    def test_a_killed_watchers_lock_is_released(self):
        p = self.holder()
        p.kill()
        p.wait()
        self.assertEqual(self.watcher().run(1, ticks=1, sleep=lambda s: None), 0)
        self.assertEqual(len(self.fake.commands), 4)

    def test_the_lock_is_held_while_running_and_released_after(self):
        w, seen = self.watcher(), []
        w.tick = lambda now=None: seen.append(watch.take_lock(self.l))
        self.assertEqual(w.run(1, ticks=1, sleep=lambda s: None), 0)
        self.assertEqual(seen, [(None, str(os.getpid()))])   # held by this process, pid written
        fd, _ = watch.take_lock(self.l)                      # free again once run() returns
        self.assertIsNotNone(fd)
        os.close(fd)

    def test_a_dry_run_beside_a_running_watcher_works_and_writes_nothing(self):
        self.holder()
        w = watch.Watch(self.l, REPO, OWNER, ROLES, read=self.scene.read)
        self.assertEqual(w.run(1, ticks=2, sleep=lambda s: None), 0)
        self.assertTrue(any(x.startswith("[build] #49") for x in self.lines))
        self.assertFalse(any("refused" in x for x in self.lines))
        self.assertEqual(self.fake.commands, [])
        self.assertFalse(watch.state_path(self.l).exists())


def _save_states(home: str, tag: str, n: int) -> None:
    """One process writing watch.json n times, as a second watcher would (#296)."""
    l = swarm.Launcher(Path(home), root=Path(home) / "repo", proc=lambda pid: None,
                       clock=time.time, out=lambda s: None, git=lambda a: (0, ""))
    for i in range(n):
        watch.save_state(l, {"checked": None, "acted": {f"{tag}-{i}": "started"}, "waiting": [],
                             "runs": {}})


class SaveStateTest(unittest.TestCase):
    """#296: watch.json is written through a temp file of each writer's own."""

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.home = Path(d.name)
        self.l = swarm.Launcher(self.home, root=self.home / "repo", proc=lambda pid: None,
                                clock=time.time, out=lambda s: None, git=lambda a: (0, ""))

    def test_round_trips_and_leaves_no_temp_file(self):
        st = {"checked": "2026-11-04T00:00:00Z", "acted": {"k": "started"}, "waiting": [], "runs": {}}
        watch.save_state(self.l, st)
        self.assertEqual(watch.load_state(self.l), st)
        self.assertEqual(list(self.l.dir.glob("*.tmp")) + list(self.l.dir.glob(".*.tmp")), [])

    def test_a_failed_write_keeps_the_old_file_and_removes_its_temp_file(self):
        watch.save_state(self.l, {"checked": None, "acted": {"old": "started"}, "waiting": [], "runs": {}})
        with self.assertRaises(TypeError):
            watch.save_state(self.l, {"checked": object()})
        self.assertEqual(watch.load_state(self.l)["acted"], {"old": "started"})
        self.assertEqual(list(self.l.dir.glob(".*.tmp")), [])

    def test_concurrent_writers_never_crash(self):
        import multiprocessing as mp
        ctx = mp.get_context("spawn")
        procs = [ctx.Process(target=_save_states, args=(str(self.home), f"w{k}", 50)) for k in range(4)]
        for p in procs:
            p.start()
        for p in procs:
            p.join(60)
        self.assertEqual([p.exitcode for p in procs], [0] * 4)        # no FileNotFoundError
        (key,) = watch.load_state(self.l)["acted"]                     # one writer's whole file
        self.assertRegex(key, r"^w[0-3]-49$")
        self.assertEqual(list(self.l.dir.glob(".*.tmp")), [])


class ManifestWatchTest(unittest.TestCase):
    def test_repo_manifest_has_the_limits_from_88(self):
        import manifest
        limits = manifest.load_watch()
        self.assertEqual((limits.interval_minutes, limits.max_live, limits.max_turns), (5, 2, 200))
        # The Actions keys are the owner's switches (#260, #257): check only that they parse (#285).
        self.assertIsInstance(limits.review_in_actions, bool)
        self.assertTrue(limits.actions_max_reviews is None or limits.actions_max_reviews >= 1)

    def test_bad_watch_table_lists_every_problem(self):
        import manifest
        text = '[watch]\ninterval_minutes = 0\nmax_live = 1.5\nceiling = 3\n\n' \
               '[[session]]\nrole = "builder"\ncount = 1\nmodel = "m"\n'
        with self.assertRaises(manifest.ManifestError) as c:
            manifest.parse_all(text)
        self.assertEqual(c.exception.problems, [
            "watch: unknown key 'ceiling' (allowed: interval_minutes, max_live, max_turns, "
            "review_in_actions, actions_max_reviews)",
            "watch: interval_minutes must be a positive number, got 0",
            "watch: max_live must be a whole number of at least 1, got 1.5"])
        with self.assertRaises(manifest.ManifestError) as c:
            manifest.parse_all('[watch]\nmax_live = 2\n[[session]]\nrole = "builder"\ncount = 1\nmodel = "m"\n')
        self.assertEqual(c.exception.problems, ["watch: missing 'interval_minutes'"])

    def test_max_turns_must_be_a_positive_whole_number(self):
        import manifest
        base = '[watch]\ninterval_minutes = 5\nmax_live = 2\n%s\n[[session]]\nrole = "builder"\ncount = 1\nmodel = "m"\n'
        for v in ("0", "-3", "1.5", '"200"', "true"):
            with self.assertRaises(manifest.ManifestError, msg=v) as c:
                manifest.parse_all(base % f"max_turns = {v}")
            self.assertEqual(len(c.exception.problems), 1)
            self.assertIn("watch: max_turns must be a whole number of at least 1", c.exception.problems[0])
        self.assertEqual(manifest.parse_all(base % "max_turns = 200")[1].max_turns, 200)

    def test_max_turns_missing_is_fine_for_up_but_not_for_watch(self):
        import manifest
        sessions, limits = manifest.parse_all(
            '[watch]\ninterval_minutes = 5\nmax_live = 2\n[[session]]\nrole = "builder"\ncount = 1\nmodel = "m"\n')
        self.assertEqual(len(sessions), 1)
        self.assertIsNone(limits.max_turns)

    def test_no_watch_table_is_fine_for_up(self):
        import manifest
        sessions, limits = manifest.parse_all('[[session]]\nrole = "builder"\ncount = 1\nmodel = "m"\n')
        self.assertIsNone(limits)
        self.assertEqual(len(sessions), 1)


class CliTest(unittest.TestCase):
    def setUp(self):
        self.lines = []
        self.l = swarm.Launcher(Path(tempfile.mkdtemp()), out=self.lines.append,
                                run=lambda c: self.fail("started"))

    def test_interval_flag_is_for_dry_run_only(self):
        self.assertEqual(swarm.main(["watch", "--interval", "1", "--repo", REPO], self.l), 2)
        self.assertIn("interval_minutes in swarm.toml", self.lines[0])

    def test_without_a_watch_table_refuses_and_names_88(self):
        path = write_manifest(Path(tempfile.mkdtemp()), ALL_CAPPED, watch_table=False)
        self.assertEqual(swarm.main(["watch", "--repo", REPO, "--manifest", str(path)], self.l), 1)
        self.assertIn("no [watch] table", self.lines[0])
        self.assertIn("GOV-0010", self.lines[0])

    def test_without_max_turns_refuses_and_names_gov_0012(self):
        path = write_manifest(Path(tempfile.mkdtemp()), ALL_CAPPED, max_turns=None)
        self.assertEqual(swarm.main(["watch", "--repo", REPO, "--manifest", str(path)], self.l), 1)
        self.assertIn("no max_turns", self.lines[0])
        self.assertIn("GOV-0012", self.lines[0])

    def test_script_refuses_interval_without_dry_run(self):
        r = subprocess.run([str(HERE / "swarm"), "watch", "--interval", "1", "--repo", REPO],
                           capture_output=True, text=True, timeout=30,
                           env={**os.environ, "PRODUCTSWARM_HOME": tempfile.mkdtemp()})
        self.assertEqual(r.returncode, 2)
        self.assertIn("GOV-0010", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()


class ReviewInActionsTest(unittest.TestCase):
    """[watch] review_in_actions (#216, GOV-0019): when on, swarm watch leaves [review] to
    the Actions reviewer; the other triggers are unchanged."""

    setUp_start = StartTest.setUp
    manifest, watcher, started, exit = StartTest.manifest, StartTest.watcher, StartTest.started, StartTest.exit
    LEFT = ("[review] PR #70 head aaaaaaa not reviewed by the reviewer -> skipped: left to Actions: "
            "review_in_actions = true in swarm.toml, so the GitHub Actions reviewer reviews this "
            "head (GOV-0019)")

    def setUp(self):
        self.setUp_start()
        self.manifest(ALL_CAPPED, review_in_actions=True)

    def test_on_starts_no_review_and_the_rest_as_before(self):
        w = self.watcher()
        self.assertEqual([(t.kind, t.ref) for t in w.tick(NOW)],
                         [("record", "#87"), ("answer", "#88"), ("build", "#49")])
        self.assertEqual([x[0] for x in self.started()],
                         ["docs-issue-87", "planner-issue-88", "builder-issue-49"])
        self.assertEqual(self.lines.count(self.LEFT), 1)
        w.tick(NOW)
        self.assertEqual(self.lines.count(self.LEFT), 1)                   # logged once per head
        self.assertNotIn("review:70:" + SHA1, watch.load_state(self.l)["acted"])
        self.assertEqual(watch.waiting(self.l)[1], [])                     # not listed as held

    def test_off_or_missing_starts_the_review(self):
        for value in (False, None):
            with self.subTest(review_in_actions=value):
                (self.home / "launcher" / "watch.json").unlink(missing_ok=True)
                self.l.save([])
                for f in (self.home / "launcher").glob("*.pid"):   # else live() recovers it (#272)
                    f.unlink()
                self.manifest(ALL_CAPPED, review_in_actions=value)
                self.assertEqual(self.watcher().tick(NOW)[0].kind, "review")
                self.assertEqual(self.l.load()[0].name, "reviewer-watch")

    def test_turning_it_off_puts_the_local_loop_back_in_charge(self):
        self.watcher().tick(NOW)
        self.assertNotIn("reviewer-watch", [x[0] for x in self.started()])
        self.manifest(ALL_CAPPED, review_in_actions=False)
        self.assertEqual([t.kind for t in self.watcher().tick(NOW)], ["review"])   # same head
        self.assertIn("reviewer-watch", [x[0] for x in self.started()])

    def test_respond_is_unchanged(self):
        sc = self.scene
        sc.issues, sc.events = [issue(73, ["ready"])], {73: [ev("ready", eid=15)]}
        sc.prs, sc.reviewed = [pr(72, SHA1, closes=[73])], {}
        sc.reviews = {72: [review("CHANGES_REQUESTED", SHA1)]}
        self.assertEqual([t.kind for t in self.watcher().tick(NOW)], ["respond"])
        self.assertEqual(self.started(), [("builder-pr-72", "builder", "m-builder", 73, "watch")])

    def test_dry_run_lists_review_as_left_to_actions_with_no_command(self):
        w = watch.Watch(self.l, REPO, OWNER, ROLES, read=self.scene.read, manifest_path=self.path)
        self.assertEqual([t.kind for t in w.tick(NOW)], ["review", "record", "answer", "build"])
        i = self.lines.index(self.LEFT)
        self.assertFalse(self.lines[i + 1].startswith("  "))               # no headless command
        self.assertEqual(sum(x.startswith("  ") for x in self.lines), 3)   # the other three keep theirs
        self.assertEqual(self.fake.commands, [])

    def test_dry_run_with_a_bad_manifest_treats_it_as_off(self):
        self.path.write_text("[watch\n")
        w = watch.Watch(self.l, REPO, OWNER, ROLES, read=self.scene.read, manifest_path=self.path)
        w.tick(NOW)
        self.assertIn("[review] PR #70 head aaaaaaa not reviewed by the reviewer -> would start a "
                      "reviewer pass", self.lines)

    def test_triggers_is_pure_and_defaults_off(self):
        w = self.scene.read(REPO, 15, NOW)
        args = (w, OWNER, [], ROLES, G.needs_you, G.is_tracking)
        self.assertIsNone(watch.triggers(*args)[0].skipped)
        self.assertEqual(watch.triggers(*args, review_in_actions=True)[0].skipped, watch.LEFT_TO_ACTIONS)


class RespondTest(unittest.TestCase):
    """GOV-0011's [respond] trigger and round bound (#113): one PR, #72, closing #73."""

    setUp_start = StartTest.setUp
    manifest, watcher, started, exit = StartTest.manifest, StartTest.watcher, StartTest.started, StartTest.exit

    def setUp(self):
        self.setUp_start()
        sc = self.scene
        sc.issues, sc.events = [issue(73, ["ready"])], {73: [ev("ready", eid=15)]}
        sc.prs, sc.reviewed = [pr(72, SHA1, closes=[73])], {}

    def request(self, *commits, state="CHANGES_REQUESTED", authority="pass"):
        self.scene.reviews.setdefault(72, []).extend(review(state, c, authority) for c in commits)

    def needs_you(self):
        items = G.needs_you(self.scene.heartbeat(REPO, 15, NOW))
        return [i["detail"] for i in items if i["ref"] == "PR #72"]

    def test_changes_requested_at_head_starts_one_builder_and_a_restart_starts_none(self):
        self.request(SHA1)
        done = self.watcher().tick(NOW)
        self.assertEqual([(t.kind, t.ref) for t in done], [("respond", "PR #72")])
        self.assertEqual(self.started(), [("builder-pr-72", "builder", "m-builder", 73, "watch")])
        self.assertEqual(self.l.load()[0].pr, 72)
        self.assertIn("respond to the requested changes on PR #72, which closes issue #73.",
                      self.fake.commands[0])
        self.assertIn("[respond] PR #72 changes requested at aaaaaaa (round 1 of 2) -> starting "
                      "builder-pr-72", self.lines)
        self.assertEqual(self.watcher().tick(NOW), [])          # next check: it's busy on #73
        self.exit("builder-pr-72")
        self.assertEqual(self.watcher().tick(NOW), [])          # a restart over the same state
        self.assertEqual(len(self.fake.commands), 1)

    def test_second_round_starts_then_third_request_lists_the_pr_and_starts_nothing(self):
        self.request(SHA1)
        self.watcher().tick(NOW)
        self.exit("builder-pr-72")
        self.scene.prs[0]["headRefOid"] = SHA2                  # the builder pushed: a review starts
        self.assertEqual([t.kind for t in self.watcher().tick(NOW)], ["review"])
        self.exit("reviewer-watch")
        self.request(SHA2)                                      # round 2
        self.assertEqual([t.kind for t in self.watcher().tick(NOW)], ["respond"])
        self.assertIn("[respond] PR #72 changes requested at bbbbbbb (round 2 of 2) -> starting "
                      "builder-pr-72", self.lines)
        self.exit("builder-pr-72")
        sha3 = "c" * 40
        self.scene.prs[0]["headRefOid"] = sha3
        self.watcher().tick(NOW)
        self.exit("reviewer-watch")
        self.request(sha3)                                      # the third request
        self.assertEqual(self.watcher().tick(NOW), [])
        self.assertEqual(len(self.fake.commands), 4)            # 2 builders, 2 reviewers
        self.assertEqual(self.needs_you(), ["changes requested 3 times: needs the owner, closes #73"])
        self.assertIn("[PR to review] PR #72 PR 72 · changes requested 3 times: needs the owner",
                      swarm.inbox_text(G.needs_you(self.scene.heartbeat(REPO, 15, NOW)), NOW, G))

    def test_overstep_starts_nothing_and_lists_the_pr(self):
        for state in ("CHANGES_REQUESTED", "COMMENTED"):
            self.scene.reviews = {}
            self.request(SHA1, state=state, authority="fail")
            self.assertEqual(self.watcher().tick(NOW), [])
            self.assertEqual(self.needs_you(), ["overstep: needs the owner, closes #73"])
        self.assertEqual(self.fake.commands, [])

    def test_changes_on_another_apps_pr_start_nothing_and_list_the_pr(self):
        """#178: a docs ruling PR with requested changes goes to the owner, not the builder."""
        self.scene.prs[0]["author"] = {"login": "app/productswarm-docs"}
        self.request(SHA1)
        self.assertEqual(self.watcher().tick(NOW), [])
        self.assertEqual(self.fake.commands, [])
        self.assertEqual(self.needs_you(), ["changes requested on a docs PR: needs the owner, closes #73"])

    def test_comment_or_approve_starts_nothing(self):
        for state in ("COMMENTED", "APPROVED"):
            self.scene.reviews = {}
            self.request(SHA1, state=state)
            self.assertEqual(self.watcher().tick(NOW), [])
            self.assertEqual(self.needs_you(), ["awaiting review, closes #73"])
        self.assertEqual(self.fake.commands, [])

    def test_request_on_an_older_head_starts_nothing(self):
        self.request(SHA2)
        self.assertEqual([t.kind for t in self.watcher().tick(NOW)], ["review"])

    def test_dry_run_prints_it(self):
        self.request(SHA1)
        w = watch.Watch(self.l, REPO, OWNER, ROLES, read=self.scene.read)
        w.tick(NOW)
        self.assertEqual(trigger_lines(self.lines),
                         ["[respond] PR #72 changes requested at aaaaaaa (round 1 of 2) "
                          "-> would start `launcher/swarm launch builder --issue 73 --pr 72`"])
        self.assertIn("respond to the requested changes on PR #72", self.lines[1])
        self.assertEqual(self.fake.commands, [])

    def test_needs_the_builders_cap_and_counts_toward_the_ceiling(self):
        self.request(SHA1)
        self.manifest({r: 10 for r in ROLES - {"builder"}})
        self.assertEqual(self.watcher().tick(NOW), [])
        self.assertIn("builder has no spend_cap_usd", self.lines[-1])
        self.manifest(ALL_CAPPED, max_live=1)
        self.scene.issues.append(issue(49, ["ready"]))
        self.scene.events[49] = [ev("ready", eid=11)]
        self.assertEqual([t.kind for t in self.watcher().tick(NOW)], ["respond"])
        self.assertIn("held: 1 of 1 sessions swarm watch started are live", self.lines[-1])

    def test_a_pr_that_closes_no_issue_is_skipped_with_a_reason(self):
        self.scene.prs, self.scene.issues = [pr(72, SHA1)], []
        self.request(SHA1)
        self.assertEqual([t.kind for t in self.watcher().tick(NOW)], ["respond"])
        self.assertIn("skipped: it closes 0 issues", self.lines[-1])
        self.assertEqual(self.fake.commands, [])

    def test_a_live_session_on_the_issue_holds_it_until_it_stops(self):
        self.request(SHA1)
        self.scene.tracking[0], self.scene.comments[200] = tracking(200, "busy-sid", "builder", 73)
        self.assertEqual(self.watcher().tick(NOW), [])
        self.scene.tracking, self.scene.comments = [], {}
        self.assertEqual([t.kind for t in self.watcher().tick(NOW)], ["respond"])


class OverlapTest(unittest.TestCase):
    """#136 (the owner's answer on #127): a [build] waits while a live builder or an open PR
    shares a GOV id in its issue's title."""

    setUp_start = StartTest.setUp
    manifest, watcher, started, exit, inbox = (StartTest.manifest, StartTest.watcher, StartTest.started,
                                               StartTest.exit, StartTest.inbox)

    def setUp(self):
        self.setUp_start()
        sc = self.scene
        sc.issues = [issue(49, ["ready"], title="GOV-0011 R1: reviewer states"),
                     issue(50, ["ready"], title="GOV-0011 R2: builder responds"),
                     issue(60, ["ready"], title="GOV-0010 W2: limits")]
        sc.events = {49: [ev("ready", eid=11)], 50: [ev("ready", eid=16)], 60: [ev("ready", eid=12)]}
        sc.prs, sc.reviewed = [], {}
        sc.tracking, sc.comments = [], {}

    def refs(self, w):
        return [t.ref for t in w.tick(NOW)]

    def busy_on(self, n, sid="busy-sid"):
        """A builder started by hand, on the heartbeat, working on #n."""
        it, comments = tracking(200, sid, "builder", n)
        self.scene.tracking, self.scene.comments = [it], {200: comments}

    def stop_heartbeat(self):
        self.scene.tracking[0]["state"] = "closed"
        self.scene.comments = {200: []}

    def test_two_new_builds_sharing_an_id_in_one_check_start_one_and_hold_the_other(self):
        w = self.watcher()
        self.assertEqual(self.refs(w), ["#49", "#60"])
        reason = "held: #50 shares GOV-0011 with live builder-issue-49 (on #49) (#127)"
        self.assertIn(f"[build] #50 ready by the owner -> {reason}", self.lines)
        self.assertIn(f"- [build] #50 ready by the owner · {reason}", self.inbox())
        n = len(self.lines)
        self.assertEqual(w.tick(NOW), [])                    # logged once per reason
        self.assertEqual(len(self.lines), n)
        self.exit("builder-issue-49")
        self.assertEqual(self.refs(w), ["#50"])
        self.assertEqual(self.inbox(), "Nothing is waiting on you.")

    def test_a_heartbeat_builder_started_by_hand_holds_until_it_stops(self):
        self.scene.issues = [issue(49, ["ready"], title="GOV-0011 R1: reviewer states"),
                             issue(61, title="GOV-0011 R3: watch respond")]
        self.busy_on(61)
        w = self.watcher()
        self.assertEqual(w.tick(NOW), [])
        self.assertIn("- [build] #49 ready by the owner · held: #49 shares GOV-0011 with live "
                      "builder session busy-sid (on #61) (#127)", self.inbox())
        self.stop_heartbeat()
        self.assertEqual(self.refs(w), ["#49"])

    def test_a_launcher_builder_with_no_heartbeat_yet_holds(self):
        self.scene.issues = [issue(49, ["ready"], title="GOV-0011 R1"), issue(61, title="GOV-0011 R3")]
        self.l.start(swarm.Started("builder-1", "builder", "m", "sid-61", self.fake.t, issue=61), [])
        w = self.watcher()
        self.assertEqual(w.tick(NOW), [])
        self.assertIn("held: #49 shares GOV-0011 with live builder-1 (on #61) (#127)", self.lines[-1])
        self.exit("builder-1")
        self.assertEqual(self.refs(w), ["#49"])

    def test_an_open_pr_holds_draft_or_not_until_it_closes(self):
        for draft in (False, True):
            with self.subTest(draft=draft):
                self.setUp()
                self.scene.issues = [issue(49, ["ready"], title="GOV-0011 R1"),
                                     issue(61, title="GOV-0011 R3")]
                self.scene.prs = [pr(120, SHA1, draft=draft, closes=[61])]
                self.scene.reviewed = {120: {SHA1}}
                w = self.watcher()
                self.assertEqual(w.tick(NOW), [])
                self.assertIn("held: #49 shares GOV-0011 with open PR #120 (#127)", self.lines[-1])
                self.scene.prs = []                          # merged or closed
                self.assertEqual(self.refs(w), ["#49"])

    def test_the_reason_names_every_builder_and_pr_it_waits_on(self):
        self.scene.issues = [issue(49, ["ready"], title="GOV-0011 GOV-0012: both"),
                             issue(61, title="GOV-0011 R3"), issue(62, title="GOV-0012 B1")]
        self.busy_on(62)
        self.scene.prs, self.scene.reviewed = [pr(120, SHA1, closes=[61])], {120: {SHA1}}
        self.assertEqual(self.watcher().tick(NOW), [])
        self.assertIn("held: #49 shares GOV-0011, GOV-0012 with live builder session busy-sid (on #62) "
                      "/ open PR #120 (#127)", self.lines[-1])

    def test_no_shared_id_or_no_id_or_an_id_only_in_the_body_runs_side_by_side(self):
        self.scene.issues = [issue(49, ["ready"], title="GOV-0011 R1"),
                             issue(50, ["ready"], title="GOV-0012 B1"),
                             issue(51, ["ready"], body="per GOV-0011 and GOV-0010", title="plain one"),
                             issue(52, ["ready"], body="per GOV-0011", title="plain two")]
        self.scene.events = {n: [ev("ready", eid=n)] for n in (49, 50, 51, 52)}
        self.assertEqual(self.refs(self.watcher()), ["#49", "#50", "#51", "#52"])

    def test_review_record_and_answer_are_never_held(self):
        sc = self.scene
        sc.issues = [issue(49, ["ready"], title="GOV-0011 R1"), issue(61, title="GOV-0011 R3"),
                     issue(87, ["gov:question", "gov:ruled"], question_body(domain="governance"),
                           title="GOV-Q: GOV-0011 follow-up"),
                     issue(88, ["gov:question", "ready"], question_body(), title="GOV-Q: GOV-0011 too")]
        sc.events = {49: [ev("ready", eid=11)], 87: [ev("gov:ruled", eid=13)], 88: [ev("ready", eid=14)]}
        sc.prs, sc.reviewed = [pr(70, SHA1)], {70: set()}
        self.busy_on(61)
        done = self.watcher().tick(NOW)
        self.assertEqual([(t.kind, t.ref) for t in done], [("review", "PR #70"), ("record", "#87"),
                                                           ("answer", "#88")])
        self.assertIn("held: #49 shares GOV-0011", self.lines[-1])

    def test_respond_is_never_held(self):
        sc = self.scene
        sc.issues = [issue(73, ["ready"], title="GOV-0011 R1"), issue(74, title="GOV-0011 R2")]
        sc.events = {73: [ev("ready", eid=15)]}
        sc.prs, sc.reviews = [pr(72, SHA1, closes=[73])], {72: [review("CHANGES_REQUESTED", SHA1)]}
        self.busy_on(74)
        self.assertEqual([(t.kind, t.ref) for t in self.watcher().tick(NOW)], [("respond", "PR #72")])

    def test_overlap_is_pure(self):
        w = self.scene.read(REPO, 15, NOW)
        self.assertIsNone(watch.overlap(49, w, []))
        b = swarm.Started("builder-issue-50", "builder", "m", "sid-50", 0.0, issue=50)
        self.assertEqual(watch.overlap(49, w, [b]),
                         "held: #49 shares GOV-0011 with live builder-issue-50 (on #50) (#127)")
        self.assertIsNone(watch.overlap(60, w, [b]))
        self.assertIsNone(watch.overlap(49, w, [swarm.Started("r", "reviewer", "m", "s", 0.0, issue=50)]))
        self.assertEqual(watch.gov_ids("GOV-0011 R3: x (GOV-0012)"), {"GOV-0011", "GOV-0012"})
        self.assertEqual(watch.gov_ids("GOV-Q: a question"), set())


# ---------------------------------------------------------------- run results (#149)

BANNER = "swarm-session: builder as productswarm-builder[bot]\n"   # ops/swarm-session's stdout (#147)


def result_json(subtype, cost, is_error=None, errors=None, sid="run-sid"):
    """A trimmed --output-format json result, with the fields of real Claude Code 2.1.317
    runs (`success`, `error_max_budget_usd`, `error_max_turns`; see the PR for #149)."""
    d = {"type": "result", "subtype": subtype, "is_error": subtype != "success" if is_error is None else is_error,
         "num_turns": 2, "session_id": sid, "total_cost_usd": cost, "stop_reason": "end_turn"}
    if subtype == "success":
        d["result"] = "Opened PR #160."
    else:
        d["errors"] = errors or []
    return json.dumps(d) + "\n"


CANNED = {
    "success": result_json("success", 1.234),
    "budget": result_json("error_max_budget_usd", 15.02, errors=["Reached maximum budget ($15)"]),
    "turns": result_json("error_max_turns", 3.5, errors=["Reached maximum number of turns (200)"]),
    "error": result_json("error_during_execution", 0.42, errors=["API Error: 529 overloaded"]),
}


class ReadResultTest(unittest.TestCase):
    """watch.read_result() on canned result files, one per way a run can end."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def read(self, text=None, raw=None):
        p = self.dir / "r.result.json"
        if raw is not None:
            p.write_bytes(raw)
        elif text is not None:
            p.write_text(text)
        return watch.read_result(p)

    def test_success_is_done(self):
        self.assertEqual(self.read(BANNER + CANNED["success"]),
                         {"ending": "done", "detail": "", "cost_usd": 1.234, "subtype": "success"})

    def test_budget_reached_is_at_cap(self):
        self.assertEqual(self.read(BANNER + CANNED["budget"]),
                         {"ending": "ended at cap", "detail": "budget (--max-budget-usd)", "cost_usd": 15.02,
                          "subtype": "error_max_budget_usd"})

    def test_turns_reached_is_at_cap(self):
        r = self.read(BANNER + CANNED["turns"])
        self.assertEqual((r["ending"], r["detail"], r["cost_usd"]), ("ended at cap", "turns (--max-turns)", 3.5))

    def test_other_error_is_error_with_its_messages(self):
        r = self.read(BANNER + CANNED["error"])
        self.assertEqual((r["ending"], r["detail"], r["cost_usd"]), ("error", "API Error: 529 overloaded", 0.42))

    def test_success_with_is_error_is_an_error(self):
        r = self.read(BANNER + result_json("success", 0.1, is_error=True))
        self.assertEqual((r["ending"], r["detail"]), ("error", "subtype success"))

    def test_without_the_banner_still_reads(self):
        self.assertEqual(self.read(CANNED["success"])["ending"], "done")

    def test_missing_file_is_no_result(self):
        self.assertEqual(self.read(), {"ending": "no result", "detail": "no result file", "cost_usd": None,
                                       "subtype": None})

    def test_unreadable_or_partial_file_is_no_result(self):
        for case in (dict(raw=b"\xff\xfe\x00bad"), dict(text=BANNER), dict(text=""),
                     dict(text=BANNER + CANNED["success"][:40]), dict(text=BANNER + '{"type": "assistant"}\n')):
            with self.subTest(case=case):
                r = self.read(**case)
                self.assertEqual((r["ending"], r["cost_usd"]), ("no result", None))
        (self.dir / "d.result.json").mkdir()                     # a path that can't be read as a file
        self.assertEqual(watch.read_result(self.dir / "d.result.json")["ending"], "no result")

    def test_a_non_number_cost_is_no_cost(self):
        self.assertIsNone(self.read(result_json("success", "lots"))["cost_usd"])
        self.assertIsNone(self.read(result_json("success", True))["cost_usd"])


class RunRecordTest(unittest.TestCase):
    """swarm watch records how each run it started ended, and `swarm inbox` lists it (#149)."""

    setUp = StartTest.setUp
    manifest = StartTest.manifest
    watcher = StartTest.watcher
    exit = StartTest.exit

    def entry(self, name):
        (e,) = [e for e in self.l.load() if e.name == name]
        return e

    def end(self, name, text=None):
        """`name` exits, leaving `text` as its result file (none if text is None)."""
        e = self.entry(name)
        if text is not None:
            self.l.result_file(e.session_id).write_text(text)
        self.exit(name)
        return e

    def state(self):
        return json.loads((self.home / "launcher" / "watch.json").read_text())

    def inbox(self, now=NOW):
        return swarm.inbox_text([], now, G, watch.waiting(self.l), watch.runs(self.l))

    def test_each_ending_is_recorded_against_its_trigger_and_nothing_restarts(self):
        self.watcher().tick(NOW)
        ends = {"builder-issue-49": BANNER + CANNED["budget"], "docs-issue-87": BANNER + CANNED["success"],
                "planner-issue-88": BANNER + CANNED["error"], "reviewer-watch": None}
        sids = {name: self.end(name, text).session_id for name, text in ends.items()}
        later = NOW + dt.timedelta(minutes=5)
        self.assertEqual(self.watcher().tick(later), [])
        self.assertEqual(len(self.fake.commands), 4)               # the triggers stay done
        st = self.state()
        self.assertTrue(all(v.startswith("started ") for v in st["acted"].values()))
        runs = st["runs"]
        self.assertEqual(runs["build:49:11"], {
            "session_id": sids["builder-issue-49"], "name": "builder-issue-49", "kind": "build", "ref": "#49",
            "started": NOW.isoformat(), "ending": "ended at cap", "detail": "budget (--max-budget-usd)",
            "cost_usd": 15.02, "subtype": "error_max_budget_usd", "ended": later.isoformat()})
        got = {r["name"]: (r["ending"], r["cost_usd"]) for r in runs.values()}
        self.assertEqual(got, {"builder-issue-49": ("ended at cap", 15.02), "docs-issue-87": ("done", 1.234),
                               "planner-issue-88": ("error", 0.42), "reviewer-watch": ("no result", None)})
        self.assertIn("[build] #49 builder-issue-49 · ended at cap (budget (--max-budget-usd)) · $15.02 (est.)"
                      " -> recorded", self.lines)
        self.watcher().tick(later + dt.timedelta(minutes=5))       # recorded once
        self.assertEqual(sum(x.endswith("-> recorded") for x in self.lines), 4)

    def test_a_live_run_is_not_recorded_yet(self):
        self.watcher().tick(NOW)
        self.watcher().tick(NOW)
        self.assertTrue(all("ending" not in r for r in self.state()["runs"].values()))
        self.assertEqual(len(self.state()["runs"]), 4)

    def test_inbox_lists_a_run_that_ended_at_cap_with_its_ref_and_cost_and_every_cost(self):
        self.watcher().tick(NOW)
        self.end("builder-issue-49", BANNER + CANNED["turns"])
        self.end("docs-issue-87", BANNER + CANNED["success"])
        self.watcher().tick(NOW)
        text = self.inbox()
        capped = text.split("swarm watch runs that ended at cap (restart one if its work should go on):\n")[1]
        self.assertTrue(capped.startswith("- [build] #49 builder-issue-49 · ended at cap (turns (--max-turns))"
                                          " · $3.50 (est.) · ended "))
        self.assertNotIn("Nothing is waiting on you.", text)
        recent = text.split("swarm watch runs in the last 7 days (cost is Claude Code's local estimate):\n")[1]
        self.assertIn("- [build] #49 builder-issue-49 · ended at cap", recent)
        self.assertIn("- [record] #87 docs-issue-87 · done · $1.23 (est.)", recent)

    def test_only_costs_still_says_nothing_is_waiting(self):
        self.watcher().tick(NOW)
        self.end("docs-issue-87", BANNER + CANNED["success"])
        self.watcher().tick(NOW)
        self.assertTrue(self.inbox().startswith("Nothing is waiting on you.\n\nswarm watch runs in the last"))

    def test_a_later_run_on_the_same_ref_clears_the_cap_item(self):
        self.watcher().tick(NOW)
        self.end("builder-issue-49", BANNER + CANNED["budget"])
        self.scene.events[49] += [ev("ready", eid=20, kind="unlabeled"), ev("ready", eid=21)]  # the owner restarts it
        later = NOW + dt.timedelta(minutes=5)
        self.assertEqual([t.ref for t in self.watcher().tick(later)], ["#49"])
        text = self.inbox(later)
        self.assertNotIn("ended at cap (restart", text)
        self.assertIn("- [build] #49 builder-issue-49 · ended at cap", text)  # its cost is still listed

    def test_records_older_than_runs_days_drop_out(self):
        self.watcher().tick(NOW)
        self.end("builder-issue-49", BANNER + CANNED["budget"])
        self.watcher().tick(NOW)
        week = NOW + dt.timedelta(days=watch.RUNS_DAYS, minutes=1)
        self.assertNotIn("#49", self.inbox(week))
        self.watcher().tick(week)
        self.assertNotIn("build:49:11", self.state()["runs"])

    def test_an_ended_at_cap_runs_unpushed_work_keeps_its_worktree(self):
        self.watcher().tick(NOW)
        e = self.entry("builder-issue-49")
        self.l.git.unpushed.add(e.session_id)
        self.end("builder-issue-49", BANNER + CANNED["budget"])
        self.watcher().tick(NOW)
        wt = self.home / "repo" / ".worktrees" / e.session_id
        self.assertTrue(wt.exists())
        self.assertIn(wt, self.l.kept)
        self.assertEqual(self.state()["runs"]["build:49:11"]["ending"], "ended at cap")

    def test_dry_run_records_nothing(self):
        self.watcher().tick(NOW)
        self.end("builder-issue-49", BANNER + CANNED["budget"])
        before = self.state()
        watch.Watch(self.l, REPO, OWNER, ROLES, dry_run=True, manifest_path=self.path,
                    read=self.scene.read).tick(NOW)
        self.assertEqual(self.state(), before)

    def test_old_state_without_runs_still_loads(self):
        (self.home / "launcher" / "watch.json").write_text(json.dumps({"checked": None, "acted": {}, "waiting": []}))
        self.assertEqual(watch.load_state(self.l)["runs"], {})
        self.assertEqual(watch.runs(self.l), [])
