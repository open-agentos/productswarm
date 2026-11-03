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
        self.w = watch.Watch(self.l, REPO, OWNER, ROLES, read=self.scene.read)

    def kinds(self, ts_):
        return [(t.kind, t.ref) for t in ts_]

    def test_each_trigger_prints_once(self):
        first = self.w.tick(NOW)
        self.assertEqual(self.kinds(first), [("review", "PR #70"), ("record", "#87"), ("answer", "#88"),
                                             ("build", "#49")])
        self.assertEqual(self.lines, [
            "[review] PR #70 head aaaaaaa not reviewed by the reviewer -> would start a reviewer pass",
            "[record] #87 gov:ruled by the owner, needs a record (domain governance) -> would start "
            "`launcher/swarm launch docs --issue 87`",
            "[answer] #88 ready by the owner -> would start `launcher/swarm launch planner --issue 88`",
            "[build] #49 ready by the owner -> would start `launcher/swarm launch builder --issue 49`",
        ])
        self.assertEqual(self.w.tick(NOW), [])
        self.assertEqual(self.w.tick(NOW), [])
        self.assertEqual(len(self.lines), 4)

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
        self.assertIn("-> skipped: \"Raised by\" names no known role ('someone, on #3')", t.line())
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
        self.assertEqual(watch.raised_by(question_body(raised="builder (on #75)"), ROLES), ("builder", ""))
        self.assertIsNone(watch.raised_by(question_body(raised="builder and planner"), ROLES)[0])
        self.assertIn("no \"Raised by\"", watch.raised_by("### Domain\n\nspend\n", ROLES)[1])

    def test_needs_record(self):
        self.assertIsNone(watch.needs_record(question_body()))
        self.assertEqual(watch.needs_record(question_body(blast="external")), "blast radius external")


def write_manifest(d: Path, caps: dict, max_live: int = 10, watch_table: bool = True) -> Path:
    """A swarm.toml with every role, the given caps, and a [watch] table."""
    text = ("[watch]\ninterval_minutes = 5\nmax_live = %d\n\n" % max_live) if watch_table else ""
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
        t_issue, t_comments = tracking(202, "rev-sid", "reviewer", None)
        self.scene.tracking.append(t_issue)
        self.scene.comments[202] = t_comments
        w = self.watcher()
        self.assertEqual([t.kind for t in w.tick(NOW)], ["record", "answer", "build"])   # reviewer live
        self.scene.tracking.remove(t_issue)                                               # it stops
        self.assertEqual([t.ref for t in w.tick(NOW)], ["PR #70", "PR #72"])
        self.assertEqual([e.name for e in self.l.load() if e.role == "reviewer"], ["reviewer-watch"])
        self.assertIn("[review] PR #72 head bbbbbbb not reviewed by the reviewer -> covered by "
                      "reviewer-watch", self.lines)

    def test_unknown_raised_by_is_logged_once_and_done(self):
        self.scene.issues[3]["body"] = question_body(raised="someone, on #3")
        w = self.watcher()
        w.tick(NOW)
        self.assertNotIn(88, [e.issue for e in self.l.load()])
        self.assertEqual(sum("skipped: \"Raised by\" names no known role" in x for x in self.lines), 1)
        w.tick(NOW)
        self.assertEqual(sum("skipped: \"Raised by\" names no known role" in x for x in self.lines), 1)

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
            self.exit("builder-issue-49")
            w.run(1, ticks=1, sleep=lambda s: None)
        self.assertEqual(len(self.fake.commands), 4)            # it did start sessions
        self.assertEqual(self.fake.signals, [])
        self.assertTrue(calls)
        writes = {"-X", "--method", "-f", "-F", "--field", "--raw-field", "--input"}
        for argv in calls:
            self.assertEqual(argv[0], "gh")
            if argv[1] == "api":
                self.assertFalse(writes & set(argv), argv)
            else:
                self.assertEqual(argv[1:3], ["pr", "list"], argv)


class ManifestWatchTest(unittest.TestCase):
    def test_repo_manifest_has_the_limits_from_88(self):
        import manifest
        self.assertEqual(manifest.load_watch(), manifest.WatchLimits(interval_minutes=5, max_live=2))

    def test_bad_watch_table_lists_every_problem(self):
        import manifest
        text = '[watch]\ninterval_minutes = 0\nmax_live = 1.5\nceiling = 3\n\n' \
               '[[session]]\nrole = "builder"\ncount = 1\nmodel = "m"\n'
        with self.assertRaises(manifest.ManifestError) as c:
            manifest.parse_all(text)
        self.assertEqual(c.exception.problems, [
            "watch: unknown key 'ceiling' (allowed: interval_minutes, max_live)",
            "watch: interval_minutes must be a positive number, got 0",
            "watch: max_live must be a whole number of at least 1, got 1.5"])
        with self.assertRaises(manifest.ManifestError) as c:
            manifest.parse_all('[watch]\nmax_live = 2\n[[session]]\nrole = "builder"\ncount = 1\nmodel = "m"\n')
        self.assertEqual(c.exception.problems, ["watch: missing 'interval_minutes'"])

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

    def test_script_refuses_interval_without_dry_run(self):
        r = subprocess.run([str(HERE / "swarm"), "watch", "--interval", "1", "--repo", REPO],
                           capture_output=True, text=True, timeout=30,
                           env={**os.environ, "PRODUCTSWARM_HOME": tempfile.mkdtemp()})
        self.assertEqual(r.returncode, 2)
        self.assertIn("GOV-0010", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()


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
        self.assertEqual(self.lines, ["[respond] PR #72 changes requested at aaaaaaa (round 1 of 2) "
                                      "-> would start `launcher/swarm launch builder --issue 73 --pr 72`"])
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
