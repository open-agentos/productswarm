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


def setUpModule():
    # #662: the runs ledger reads its scopes with swarm.gh_scopes and its PRs' issues with
    # watch.gh_pr_closes; never GitHub in a test.
    for target, name in ((swarm, "gh_scopes"), (watch, "gh_pr_closes")):
        patcher = mock.patch.object(target, name, lambda repo, numbers: {})
        patcher.start()
        unittest.addModuleCleanup(patcher.stop)
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
        self.plan = "# Plan\n"                # PLAN.md on main, None if absent (#583)

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
                                     for k, v in self.all_reviews().items()},
                           comments={k: list(v) for k, v in self.comments.items()},
                           plan=self.plan)

    # The fresh reads `swarm watch` makes before each start (swarm launch's refusal checks).
    def heartbeat(self, repo, idle, now):
        return G.build(self.data(), NOW, dt.timedelta(minutes=idle))

    def get_issue(self, repo, n):
        found = [i for i in self.issues if i["number"] == n]
        return (found[0] if found else None), list(self.events.get(n, []))

    def get_reader(self, repo, n):
        """swarm.go_refusals' fresh reads (#583): PLAN.md, issue states, n's comments."""
        open_ = {i["number"] for i in self.issues}
        return swarm.GoReader(plan=lambda: self.plan,
                              state=lambda w: "open" if w in open_ else "closed",
                              comments=lambda: list(self.comments.get(n, [])))

    # The same data as `gh` output, for the test that runs the real readers.
    def gh(self, argv):
        if argv[1] == "pr":
            return json.dumps(self.prs)
        if argv[2] == "graphql":                 # #392's batched comments: none returned, so
            return json.dumps({"data": {"repository": {}}})   # each issue falls back to REST
        path = argv[3] if argv[2] == "--paginate" else argv[2]
        path = path.split(f"repos/{REPO}/", 1)[1].split("?")[0]
        if path == "contents/PLAN.md":           # #583: gh_plan, once per check
            import base64
            return json.dumps({"content": base64.b64encode(self.plan.encode()).decode()})
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
                                root=self.home / "repo", git=FakeGit(), claude_dir=self.home / "claude")
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
            "[build] #60 ready by the owner -> held: builder session busy-sid is live on #60 (active)",
        ])
        self.assertEqual(self.w.tick(NOW), [])
        self.assertEqual(self.w.tick(NOW), [])
        self.assertEqual(len(self.lines), 9)       # each start with its headless command (#147)

    def test_dry_run_prints_the_full_headless_command_under_each_trigger(self):
        # #147: what a real start would run, with every flag, from swarm.toml.
        path = write_manifest(self.home, {"builder": 15, "docs": 5, "planner": 5, "reviewer": 5},
                              max_turns=200)
        w = watch.Watch(self.l, REPO, OWNER, ROLES, read=self.scene.read, manifest_path=path)
        w.tick(NOW)
        self.assertEqual(len(self.lines), 9)       # 4 starts with a command each, 1 held (#488)
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

    def test_a_bad_entry_is_reported_every_tick_and_the_others_still_run(self):
        # #487: one [[session]] naming a role with no roles/<role>.md used to stop everything.
        path = write_manifest(self.home, ALL_CAPPED)
        path.write_text(path.read_text() + '[[session]]\nrole = "ghost"\ncount = 1\nmodel = "m"\n')
        w = watch.Watch(self.l, REPO, OWNER, ROLES, read=self.scene.read, manifest_path=path)
        problem = "swarm.toml: session 5 (ghost): unknown role 'ghost' (no roles/ghost.md)"
        self.assertEqual(self.kinds(w.tick(NOW)), [("review", "PR #70"), ("record", "#87"),
                                                   ("answer", "#88"), ("build", "#49")])
        self.assertEqual(self.lines[0], problem)
        self.assertFalse(any("no headless command" in x for x in self.lines), self.lines)
        self.lines.clear()
        self.assertEqual(w.tick(NOW), [])
        self.assertEqual(self.lines, [problem])

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

    def owner_asks_for_a_record(self, login=OWNER, body="Approved as drafted.\n\nRecord: yes\n"):
        """Question #87 becomes two-way, repo and spend; `login` comments `body` on it (#501)."""
        self.scene.issues[2]["body"] = question_body(domain="spend")
        self.scene.comments[87] = [{"user": {"login": login}, "body": body}]

    def test_record_when_the_owner_asks_in_the_answer(self):
        self.owner_asks_for_a_record()
        (t,) = [t for t in self.w.tick(NOW) if t.kind == "record"]
        self.assertEqual((t.key, t.ref, t.role), ("record:87:13", "#87", "docs"))
        self.assertIn("[record] #87 gov:ruled by the owner, needs a record (the owner asked in the answer) "
                      "-> would start `launcher/swarm launch docs --issue 87`", self.lines)

    def test_record_for_an_always_one_way_domain_rated_two_way(self):
        # #519 (#491's case): a security question rated two-way, repo in its body.
        self.scene.issues[2]["body"] = question_body(domain="security", rev="two-way", blast="repo")
        (t,) = [t for t in self.w.tick(NOW) if t.kind == "record"]
        self.assertEqual((t.key, t.role), ("record:87:13", "docs"))
        self.assertIn("[record] #87 gov:ruled by the owner, needs a record (domain security is always "
                      "one-way) -> would start `launcher/swarm launch docs --issue 87`", self.lines)

    def test_record_for_a_domain_the_owner_marks_later(self):
        # #519: spend isn't always_one_way today; once the file marks it, it counts next tick.
        self.scene.issues[2]["body"] = question_body(domain="spend")
        self.assertNotIn("record", [t.kind for t in self.w.tick(NOW)])
        self.w.jurisdictions = jurisdictions_marking(self.home, "spend")
        self.assertEqual([t.kind for t in self.w.tick(NOW)], ["record"])

    def test_unreadable_jurisdictions_says_so_and_keeps_the_body_ratings(self):
        self.w.jurisdictions = self.home / "missing.yml"
        self.assertIn("record", [t.kind for t in self.w.tick(NOW)])     # #87 is domain governance
        self.assertIn("swarm watch: can't read governance/jurisdictions.yml (FileNotFoundError); "
                      "only a question's own ratings count for [record]", self.lines)

    def test_record_line_from_anyone_else_starts_nothing(self):
        for login in ("productswarm-planner[bot]", "someone-else"):
            self.w.seen.clear()
            self.owner_asks_for_a_record(login=login)
            self.assertNotIn("record", [t.kind for t in self.w.tick(NOW)], login)

    def test_no_record_line_starts_nothing(self):
        self.owner_asks_for_a_record(body="Approved as drafted. A record would be nice, but no.")
        self.assertNotIn("record", [t.kind for t in self.w.tick(NOW)])

    def test_record_line_posted_after_the_ruling(self):
        self.scene.issues[2]["body"] = question_body(domain="spend")
        self.assertNotIn("record", [t.kind for t in self.w.tick(NOW)])   # ruled, no line yet
        self.owner_asks_for_a_record()
        self.assertEqual([t.key for t in self.w.tick(NOW) if t.kind == "record"], ["record:87:13"])
        # The key is still the ruling's, so a second line doesn't fire it again.
        self.scene.comments[87].append({"user": {"login": OWNER}, "body": "record: YES"})
        self.assertEqual([t.kind for t in self.w.tick(NOW) if t.kind == "record"], [])

    def test_unknown_raised_by_is_skipped_with_a_reason(self):
        self.scene.issues[3]["body"] = question_body(raised="someone, on #3")
        (t,) = [t for t in self.w.tick(NOW) if t.kind == "answer"]
        self.assertIn("-> skipped: \"Raised by\" doesn't start with a known role or the owner "
                      "('someone, on #3')", t.line())
        self.assertEqual(self.w.tick(NOW), [])            # printed once

    def test_owner_raised_question_starts_the_planner(self):
        # #455: #396 and #439 were skipped; the planner now reads the owner's answer.
        self.scene.issues[3]["body"] = question_body(raised="owner (drafted by the coordinator)")
        self.w.tick(NOW)
        self.assertIn("[answer] #88 ready by the owner -> would start "
                      "`launcher/swarm launch planner --issue 88`", trigger_lines(self.lines))

    def rule(self, n=88, eid=30, **body):
        """The owner adds `gov:ruled` to question n, which is already `ready` (#495)."""
        q = [i for i in self.scene.issues if i["number"] == n][0]
        q["labels"].append({"name": "gov:ruled"})
        if body:
            q["body"] = question_body(**body)
        self.scene.events[n].append(ev("gov:ruled", eid=eid))

    def test_a_ruling_on_a_ready_question_fires_answer_again(self):
        # #495: #480 was ruled while ready, and nothing started.
        self.scene.issues[3]["body"] = question_body(raised="owner")
        self.w.tick(NOW)
        self.rule()
        (t,) = self.w.tick(NOW)
        self.assertEqual((t.key, t.role, t.after), ("answer:88:30", "planner", None))
        self.assertEqual(trigger_lines(self.lines)[-1], "[answer] #88 gov:ruled by the owner -> would "
                         "start `launcher/swarm launch planner --issue 88`")
        self.assertEqual(self.w.tick(NOW), [])            # printed once

    def test_ruled_key_is_the_later_owner_label(self):
        # Ruled first, `ready` added after: the ready event is the key, as before #495.
        self.scene.issues[3]["labels"].append({"name": "gov:ruled"})
        self.scene.events[88] = [ev("gov:ruled", eid=13), ev("ready", eid=14)]
        (t,) = [t for t in self.w.tick(NOW) if t.kind == "answer"]
        self.assertEqual((t.key, t.why), ("answer:88:14", "ready by the owner"))
        # Someone else's gov:ruled doesn't count (GOV-0006); `ready` is still the key.
        self.w.seen.clear()
        self.scene.events[88] = [ev("ready", eid=14), ev("gov:ruled", "productswarm-planner[bot]", 15)]
        (t,) = [t for t in self.w.tick(NOW) if t.kind == "answer"]
        self.assertEqual(t.key, "answer:88:14")
        # A ruling without the owner's `ready` starts no [answer].
        self.w.seen.clear()
        self.scene.issues[3]["labels"] = [{"name": "gov:question"}, {"name": "gov:ruled"}]
        self.scene.events[88] = [ev("gov:ruled", eid=16)]
        self.assertNotIn("answer", [t.kind for t in self.w.tick(NOW)])

    def test_dry_run_says_docs_goes_before_the_planner(self):
        self.w.tick(NOW)
        self.rule(raised="owner", domain="governance")
        self.assertEqual([(t.kind, t.after) for t in self.w.tick(NOW)],
                         [("record", None), ("answer", "record:88:30")])
        self.assertEqual(trigger_lines(self.lines)[-1], "[answer] #88 gov:ruled by the owner -> would "
                         "start `launcher/swarm launch planner --issue 88` once docs has stopped "
                         "([record] first)")

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
        # #271: only the asker counts, not a role named later in the text. #455: an
        # owner-raised question starts the planner, whatever roles its text names.
        self.assertEqual(rb("owner, after the first Actions reviewer test on #251"), ("planner", ""))
        self.assertIsNone(rb("Claude (owner's coordinating session), drafted through the owner's account.")[0])
        self.assertIsNone(rb("someone, on #3")[0])
        self.assertEqual(rb("someone, on #3"),
                         (None, "\"Raised by\" doesn't start with a known role or the owner "
                                "('someone, on #3')"))
        self.assertIsNone(rb("builders, on #5")[0])
        self.assertIn("no \"Raised by\"", watch.raised_by("### Domain\n\nspend\n", ROLES)[1])

    def test_raised_by_the_owner_is_the_planner(self):
        # #455: "owner", the owner's login (any case, with or without @) and the `-- role` form.
        rb = lambda raised: watch.raised_by(question_body(raised=raised), ROLES, OWNER)
        self.assertEqual(rb("owner (drafted by the coordinator)"), ("planner", ""))
        self.assertEqual(rb("owner, directly rather than from a task issue (context: #397)."),
                         ("planner", ""))
        self.assertEqual(rb("Owner"), ("planner", ""))
        self.assertEqual(rb("mattmcalister"), ("planner", ""))
        self.assertEqual(rb("@MattMcAlister, on #444"), ("planner", ""))
        self.assertEqual(rb("-- owner"), ("planner", ""))
        self.assertEqual(rb("-- builder (claude-opus-5-5)"), ("builder", ""))
        self.assertIsNone(rb("owner's coordinating session")[0])
        self.assertIsNone(rb("owners, on #5")[0])
        self.assertIsNone(rb("someone-else")[0])
        self.assertIsNone(rb("mattmcalister2")[0])
        # Without the planner in the repo's roles, nothing starts.
        self.assertIsNone(watch.raised_by(question_body(raised="owner"), ROLES - {"planner"}, OWNER)[0])

    def test_needs_record(self):
        self.assertIsNone(watch.needs_record(question_body()))
        self.assertEqual(watch.needs_record(question_body(blast="external")), "blast radius external")
        said = lambda body, login=OWNER: [{"user": {"login": login}, "body": body}]
        asked = "the owner asked in the answer"
        self.assertEqual(watch.needs_record(question_body(), said("Yes.\n  RECORD: Yes  \n"), OWNER), asked)
        self.assertIsNone(watch.needs_record(question_body(), said("Record: yes"), None))
        self.assertIsNone(watch.needs_record(question_body(), said("Record: yes", "bot[bot]"), OWNER))
        self.assertIsNone(watch.needs_record(question_body(), said("I'd say Record: yes here"), OWNER))
        self.assertIsNone(watch.needs_record(question_body(), said("Record: no"), OWNER))


    def test_needs_record_for_an_always_one_way_domain(self):
        # #519: the domain's rating in jurisdictions.yml counts, whatever the body says.
        body = question_body(domain="Security", rev="two-way", blast="repo")
        self.assertIsNone(watch.needs_record(body))
        self.assertEqual(watch.needs_record(body, one_way=frozenset({"security"})),
                         "domain security is always one-way")
        self.assertIsNone(watch.needs_record(question_body(domain="spend"), one_way=frozenset({"security"})))

    def test_one_way_domains_come_from_jurisdictions(self):
        # #519: read from the file, not a hard-coded list.
        domains, why = watch.one_way_domains()
        self.assertIsNone(why)
        self.assertLessEqual({"security", "external"}, domains)
        self.assertNotIn("spend", domains)
        with tempfile.TemporaryDirectory() as d:
            path = jurisdictions_marking(Path(d), "spend")
            self.assertEqual(watch.one_way_domains(path), (domains | {"spend"}, None))
            missing, why = watch.one_way_domains(Path(d) / "nope.yml")
            self.assertEqual(missing, frozenset())
            self.assertIn("can't read governance/jurisdictions.yml (FileNotFoundError)", why)


def jurisdictions_marking(d: Path, domain: str) -> Path:
    """A copy of the repo's jurisdictions.yml with `domain` marked always_one_way too."""
    text = swarm.JURISDICTIONS.read_text()
    head = f"\n  {domain}:\n"
    assert head in text
    path = d / "jurisdictions.yml"
    path.write_text(text.replace(head, f"{head}    always_one_way: true\n", 1))
    return path


def write_manifest(d: Path, caps: dict, max_live: int = 10, watch_table: bool = True,
                   max_turns: int | None = 50, review_in_actions: bool | None = None,
                   stale_minutes: int | None = None, call_ins: bool | None = None,
                   extra: str = "") -> Path:
    """A swarm.toml with every role, the given caps, and a [watch] table."""
    text = ""
    if watch_table:
        text = "[watch]\ninterval_minutes = 5\nmax_live = %d\n" % max_live
        text += "max_turns = %d\n" % max_turns if max_turns is not None else ""
        if review_in_actions is not None:
            text += f"review_in_actions = {str(review_in_actions).lower()}\n"
        if stale_minutes is not None:
            text += f"stale_minutes = {stale_minutes}\n"
        if call_ins is not None:
            text += f"call_ins = {str(call_ins).lower()}\n"
        text += extra + "\n"
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
                                root=self.home / "repo", git=FakeGit(), claude_dir=self.home / "claude")
        self.scene = Scene()
        self.manifest(ALL_CAPPED)

    def manifest(self, caps, max_live=10, **kw):
        self.path = write_manifest(self.home, caps, max_live, **kw)

    def watcher(self):
        return watch.Watch(self.l, REPO, OWNER, ROLES, dry_run=False, manifest_path=self.path,
                           read=self.scene.read, get_issue=self.scene.get_issue,
                           get_heartbeat=self.scene.heartbeat, get_reader=self.scene.get_reader)

    def started(self):
        return [(e.name, e.role, e.model, e.issue, e.by) for e in self.l.load()]

    def exit(self, name, ran=True):
        """The session called `name` exits by itself. With ran, it leaves a done result if
        it left none: a run with no result file never started, and is tried again (#550)."""
        (e,) = [e for e in self.l.load() if e.name == name]
        result = self.l.result_file(e.session_id)
        if ran and not result.exists():
            result.write_text(BANNER + CANNED["success"])
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

    def test_a_bad_entry_starts_the_other_roles(self):
        # #487: the bad entry is skipped and reported; every other role still starts.
        self.path.write_text(self.path.read_text()
                             + '[[session]]\nrole = "ghost"\ncount = 1\nmodel = "m"\n')
        done = self.watcher().tick(NOW)
        self.assertEqual([(t.kind, t.ref) for t in done],
                         [("review", "PR #70"), ("record", "#87"), ("answer", "#88"), ("build", "#49")])
        self.assertEqual(len(self.fake.commands), 4)
        self.assertIn("swarm.toml: session 5 (ghost): unknown role 'ghost' (no roles/ghost.md)",
                      self.lines)

    def test_a_bad_watch_table_still_starts_nothing(self):
        # #487: only [[session]] entries are skipped; a bad [watch] stops every start (GOV-0010).
        self.path.write_text(self.path.read_text().replace("max_live = 10", "max_live = 0"))
        w = self.watcher()
        self.assertEqual(w.run(5, ticks=2, sleep=lambda s: None), 0)
        self.assertEqual(self.fake.commands, [])
        self.assertEqual(sum("max_live must be a whole number of at least 1" in x
                             and "trying again next tick" in x for x in self.lines), 2)

    def test_a_role_file_added_while_watching_is_seen_next_tick(self):
        # #487: roles/ is re-read every tick, so a watcher started before a role existed learns it.
        roles = self.l.root / "roles"
        roles.mkdir(parents=True)
        for r in ROLES - {"planner"}:
            (roles / f"{r}.md").write_text(f"# Role: {r}\n")
        w = watch.Watch(self.l, REPO, OWNER, set(), dry_run=False, manifest_path=self.path,
                        read=self.scene.read, get_issue=self.scene.get_issue,
                        get_heartbeat=self.scene.heartbeat, roles_from=self.l.root)
        self.assertNotIn("#88", [t.ref for t in w.tick(NOW)])
        self.assertNotIn("planner-issue-88", [x[0] for x in self.started()])
        (roles / "planner.md").write_text("# Role: planner\n")
        self.assertEqual([t.ref for t in w.tick(NOW)], ["#88"])
        self.assertIn(("planner-issue-88", "planner", "m-planner", 88, "watch"), self.started())

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
        self.assertEqual(self.inbox(), "swarm watch is holding (last check just now):\n"   # only #488's
                         "- [build] #60 ready by the owner · held: builder session busy-sid is live on "
                         "#60 (active)")
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

    def test_a_ruling_on_a_ready_question_starts_the_planner_again(self):
        # #495: the owner rules a question that is already ready; no record is needed.
        self.scene.issues[3]["body"] = question_body(raised="owner")
        self.watcher().tick(NOW)
        self.exit("planner-issue-88")
        self.scene.issues[3]["labels"].append({"name": "gov:ruled"})
        self.scene.events[88].append(ev("gov:ruled", eid=30))
        (t,) = self.watcher().tick(NOW)
        self.assertEqual((t.key, t.ref), ("answer:88:30", "#88"))
        self.assertEqual(sum("starting planner-issue-88" in x for x in self.lines), 2)

    def test_docs_records_the_ruling_before_the_planner_starts(self):
        # #495: [record] and [answer] on one question run one after the other, docs first.
        self.scene.issues = [self.scene.issues[3]]
        self.scene.issues[0]["labels"].append({"name": "gov:ruled"})
        self.scene.issues[0]["body"] = question_body(raised="owner", domain="governance")
        self.scene.events = {88: [ev("ready", eid=14), ev("gov:ruled", eid=30)]}
        self.scene.prs, self.scene.reviewed = [], {}
        self.manifest(ALL_CAPPED, max_live=1)
        w = self.watcher()
        self.assertEqual([t.kind for t in w.tick(NOW)], ["record"])
        self.assertEqual([e.name for e in self.l.load()], ["docs-issue-88"])
        self.assertEqual(w.tick(NOW), [])                         # docs live: busy()
        self.assertNotIn("planner", [e.role for e in self.l.load()])
        self.exit("docs-issue-88")
        self.scene.prs = [pr(95, closes=(88,))]                   # docs opened the ruling PR
        self.scene.reviewed = {95: {SHA1}}
        self.assertEqual([t.kind for t in w.tick(NOW)], ["answer"])
        self.assertEqual([e.name for e in self.l.load()], ["planner-issue-88"])

    def test_answer_starts_after_docs_even_when_held_first(self):
        # A ceiling held [answer] before [record] existed in the list; docs still goes first.
        self.scene.issues = [self.scene.issues[3]]
        self.scene.issues[0]["labels"].append({"name": "gov:ruled"})
        self.scene.issues[0]["body"] = question_body(raised="owner", domain="governance")
        self.scene.events = {88: [ev("ready", eid=14), ev("gov:ruled", eid=30)]}
        self.scene.prs, self.scene.reviewed = [], {}
        self.manifest(ALL_CAPPED, max_live=1)
        self.l.start(swarm.Started("reviewer-watch", "reviewer", "m", "rev-sid", self.fake.t,
                                   by="watch", budget_usd=5, max_turns=50), [])
        w = self.watcher()
        w.tick(NOW)                                               # the one slot is taken
        self.assertIn("[answer] #88 gov:ruled by the owner -> held: docs records the ruling on #88 "
                      "first, then planner starts", self.lines)
        st = watch.load_state(self.l)                             # [answer] has waited longest
        for x in st["waiting"]:
            x["since"] = "2026-11-01T00:00:00+00:00" if x["kind"] == "answer" else x["since"]
        watch.save_state(self.l, st)
        self.exit("reviewer-watch")
        self.assertEqual([t.kind for t in w.tick(NOW)], ["record"])
        self.assertEqual([e.name for e in self.l.load()], ["docs-issue-88"])
        self.exit("docs-issue-88")                                # docs stopped without a PR
        self.assertEqual([t.kind for t in w.tick(NOW)], ["answer"])
        self.assertEqual([e.name for e in self.l.load()], ["planner-issue-88"])

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
        # #271: the text names the reviewer, but an unknown asker starts nothing.
        raised = "someone, after the first Actions reviewer test on #251"
        self.scene.issues[3]["body"] = question_body(raised=raised)
        w = self.watcher()
        w.tick(NOW)
        self.assertNotIn(88, [e.issue for e in self.l.load()])
        why = f"skipped: \"Raised by\" doesn't start with a known role or the owner ({raised!r})"
        self.assertEqual(sum(why in x for x in self.lines), 1)
        self.assertIn(f"- [answer] #88 ready by the owner · {why}", self.inbox())
        w.tick(NOW)
        self.assertEqual(sum(why in x for x in self.lines), 1)       # logged once
        self.assertNotIn(88, [e.issue for e in self.l.load()])
        self.scene.issues[3]["state"] = "closed"                    # the owner closes it
        w.tick(NOW)
        self.assertNotIn("#88", self.inbox())

    def test_owner_raised_question_starts_the_planner_not_a_named_role(self):
        # #455 (and #271): the owner asked, so the planner starts, not the reviewer it names.
        self.scene.issues[3]["body"] = question_body(
            raised="owner, after the first Actions reviewer test on #251")
        self.watcher().tick(NOW)
        self.assertIn((88, "planner"), [(e.issue, e.role) for e in self.l.load()])
        self.assertNotIn((88, "reviewer"), [(e.issue, e.role) for e in self.l.load()])

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
        with mock.patch.object(G, "subprocess", fake_sub), mock.patch.object(G.ghql, "subprocess", fake_sub):
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
            if argv[1:3] == ["api", "graphql"]:          # its -f flags carry a query, not a write
                self.assertTrue(argv[4].startswith("query=query("), argv)
            elif argv[1] == "api":
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
        w = watch.Watch(self.l, REPO, OWNER, ROLES, manifest_path=self.path, read=self.scene.read)
        self.assertEqual(w.run(1, ticks=2, sleep=lambda s: None), 0)
        self.assertTrue(any(x.startswith("[build] #49") for x in self.lines))
        self.assertFalse(any("refused" in x for x in self.lines))
        self.assertEqual(self.fake.commands, [])
        self.assertFalse(watch.state_path(self.l).exists())


def _save_states(home: str, tag: str, n: int) -> None:
    """One process writing the watch state n times, as a second watcher would (#296)."""
    l = swarm.Launcher(Path(home), root=Path(home) / "repo", proc=lambda pid: None,
                       clock=time.time, out=lambda s: None, git=lambda a: (0, ""))
    for i in range(n):
        watch.save_state(l, {"checked": None, "acted": {f"{tag}-{i}": "started"}, "waiting": [],
                             "runs": {}})


class SaveStateTest(unittest.TestCase):
    """#296 and #659: the watch state is replaced whole, one writer at a time."""

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.home = Path(d.name)
        self.l = swarm.Launcher(self.home, root=self.home / "repo", proc=lambda pid: None,
                                clock=time.time, out=lambda s: None, git=lambda a: (0, ""))

    def test_round_trips_and_leaves_no_temp_file(self):
        st = {"checked": "2026-11-04T00:00:00Z", "acted": {"k": "started"}, "waiting": [], "runs": {},
              "asks_since": {"600": "2026-11-03T08:00:00+00:00"},
              "research_since": "2026-11-03T09:00:00+00:00"}
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
            "review_in_actions, actions_max_reviews, stale_minutes, call_ins, daily, daily_at, "
            "report_issue, asks, research)",
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



SCRATCH = "open-agentos/scratch"


class OtherReposTest(unittest.TestCase):
    """#772: swarm.toml's [org] repos are watched beside this one."""
    kinds = WatchTest.kinds

    def setUp(self):
        WatchTest.setUp(self)
        self.read_repos = []
        task = {**issue(5), "user": {"login": "productswarm-planner[bot]"},
                "html_url": f"https://github.com/{SCRATCH}/issues/5"}
        self.other = {"issues": [task], "prs": [{**pr(7, SHA2), "url": f"https://github.com/{SCRATCH}/pull/7"}]}
        # #5 is a Task under the owner's open Goal #686 in this repo (GOV-0031).
        self.scopes = {5: {"author": "productswarm-planner[bot]", "type": "Task", "deep": False,
                           "parents": [{"repo": REPO, "number": 686, "state": "open", "type": "Goal",
                                        "author": OWNER}],
                           "blockers_complete": True, "blocked_by": []}}

    def read(self, repo, idle, now):
        self.read_repos.append(repo)
        if repo == REPO:
            return self.scene.read(repo, idle, now)
        if repo != SCRATCH:
            raise RuntimeError("gh failed")
        data = {"repo": SCRATCH, "issues": self.other["issues"], "comments": {},
                "prs": self.other["prs"], "reviews": {}}
        return watch.World(model=G.build(data, NOW, dt.timedelta(minutes=idle)),
                           issues=self.other["issues"], scopes=self.scopes, repo=SCRATCH)

    def watch(self, org, dry_run=True):
        path = write_manifest(self.home / "fixture", ALL_CAPPED, max_live=2)
        path.write_text(path.read_text() + org)
        return watch.Watch(self.l, REPO, OWNER, ROLES, read=self.read, manifest_path=path,
                           dry_run=dry_run, get_issue=self.scene.get_issue,
                           get_heartbeat=self.scene.heartbeat, get_reader=self.scene.get_reader)

    def test_no_org_table_reads_this_repo_only(self):
        self.watch("").tick(NOW)
        self.assertEqual(self.read_repos, [REPO])

    def test_dry_run_shows_go_work_in_both_repos(self):
        got = self.watch(f'[org]\nrepos = ["{SCRATCH}"]\n').tick(NOW)
        self.assertEqual(self.read_repos, [REPO, SCRATCH])
        self.assertEqual(self.kinds(got)[-2:], [("review", f"PR {SCRATCH}#7"), ("build", f"{SCRATCH}#5")])
        self.assertEqual(got[-1].key, f"{SCRATCH}|build:5:G{REPO}#686")
        self.assertIn(f"[build] {SCRATCH}#5 go under Goal {REPO}#686 (GOV-0031) -> would start "
                      f"builder on {SCRATCH}#5", self.lines)
        self.assertIn(f"  (no headless command: {watch.OTHER_REPO})", self.lines)
        self.assertIn(("build", "#49"), self.kinds(got))          # this repo's work as before

    def test_real_check_lists_other_repo_work_once_and_starts_nothing_there(self):
        w = self.watch(f'[org]\nrepos = ["{SCRATCH}", "elsewhere/x"]\n', dry_run=False)
        w.tick(NOW)
        line = f"[build] {SCRATCH}#5 go under Goal {REPO}#686 (GOV-0031) -> {watch.OTHER_REPO}"
        self.assertIn(line, self.lines)
        self.assertIn("swarm watch: elsewhere/x isn't in the open-agentos org, so it is left out "
                      "(GOV-0031 covers one org)", self.lines)
        self.assertFalse(any(e.issue == 5 for e in self.l.running()))
        self.assertFalse(any(k.startswith(SCRATCH) for k in watch.load_state(self.l)["acted"]))
        w.tick(NOW)
        self.assertEqual(self.lines.count(line), 1)

    def test_an_unreadable_repo_is_said_once(self):
        w = self.watch('[org]\nrepos = ["open-agentos/gone"]\n')
        w.tick(NOW)
        w.tick(NOW)
        self.assertEqual(self.lines.count("swarm watch: can't read open-agentos/gone (gh failed); "
                                          "its triggers wait"), 1)


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
        self.assertEqual([x["key"] for x in watch.waiting(self.l)[1]],      # [review] not listed as held,
                         ["build:60:12"])                                  # only #60's live session (#488)

    def test_off_or_missing_starts_the_review(self):
        for value in (False, None):
            with self.subTest(review_in_actions=value):
                watch.state_path(self.l).unlink(missing_ok=True)
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

    def test_changes_on_an_analyst_pr_start_the_analyst_and_an_overstep_starts_none(self):
        """#738 (Option 1 of the owner's answer on #777): [respond] starts the PR's author role."""
        self.scene.prs[0]["author"] = {"login": "productswarm-analyst[bot]"}
        self.manifest(ALL_CAPPED, extra='[[session]]\nrole = "analyst"\ncount = 1\n'
                                        'model = "m-analyst"\nspend_cap_usd = 10\n')
        roles = ROLES | {"analyst"}
        self.watcher = lambda: watch.Watch(self.l, REPO, OWNER, roles, dry_run=False,
                                           manifest_path=self.path, read=self.scene.read,
                                           get_issue=self.scene.get_issue,
                                           get_heartbeat=self.scene.heartbeat,
                                           get_reader=self.scene.get_reader)
        self.request(SHA1)
        [t] = self.watcher().tick(NOW)
        self.assertEqual((t.kind, t.role, t.issue, t.pr), ("respond", "analyst", 73, 72))
        self.assertEqual(self.started(), [("analyst-pr-72", "analyst", "m-analyst", 73, "watch")])
        self.assertIn("You are the analyst for productswarm. Read CLAUDE.md, PRODUCT.md and "
                      "roles/analyst.md, then respond to the requested changes on PR #72",
                      self.fake.commands[0])
        self.exit("analyst-pr-72")
        self.scene.prs[0]["headRefOid"] = SHA2                  # the analyst pushed
        self.watcher().tick(NOW)
        self.exit("reviewer-watch")
        self.request(SHA2, authority="fail")                     # an overstep on the new head
        self.assertEqual(self.watcher().tick(NOW), [])
        self.assertEqual(len(self.fake.commands), 2)            # the analyst, then a reviewer
        self.assertEqual(self.needs_you(), ["overstep: needs the owner, closes #73"])

    def test_a_docs_record_pr_on_a_ruled_question_starts_docs(self):
        """#738: a docs ruling PR closes a gov:question, which the owner's gov:ruled makes go."""
        self.scene.issues = [issue(73, ["gov:question", "gov:ruled"])]
        self.scene.events = {73: [ev("gov:ruled", eid=15)]}
        self.scene.prs[0]["author"] = {"login": "app/productswarm-docs"}
        self.request(SHA1)
        self.assertEqual([(t.kind, t.role) for t in self.watcher().tick(NOW)], [("respond", "docs")])
        self.assertEqual(self.started(), [("docs-pr-72", "docs", "m-docs", 73, "watch")])

    def test_changes_on_a_pr_no_role_opened_start_nothing_and_list_the_pr(self):
        """#178: a PR the owner (or any non-swarm login) opened stays the owner's."""
        for login, who in [(OWNER, "non-swarm"), ("productswarm-stranger[bot]", "stranger")]:
            self.scene.prs[0]["author"] = {"login": login}
            self.scene.reviews = {}
            self.request(SHA1)
            self.assertEqual(self.watcher().tick(NOW), [])
            self.assertEqual(self.needs_you(), [f"changes requested on a {who} PR: needs the owner, closes #73"])
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
        w = watch.Watch(self.l, REPO, OWNER, ROLES, manifest_path=self.path, read=self.scene.read)
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


class RulingTest(unittest.TestCase):
    """#739 (Option 1 of the owner's answer on #781): the owner's comment on a PR after an
    Authority: fail review at its head starts the builder once. PR #72 closes #73."""

    setUp_start = StartTest.setUp
    manifest, watcher, started, exit = StartTest.manifest, StartTest.watcher, StartTest.started, StartTest.exit

    def setUp(self):
        self.setUp_start()
        sc = self.scene
        sc.issues, sc.events = [issue(73, ["ready"])], {73: [ev("ready", eid=15)]}
        sc.prs, sc.reviewed = [pr(72, SHA1, closes=[73])], {}
        self.overstep()

    def overstep(self, commit=SHA1, authority="fail", minutes_ago=30):
        self.scene.reviews[72] = [{**review("COMMENTED", commit, authority), "submitted_at": ts(minutes_ago)}]

    def say(self, cid, body="Don't mount the shared .git read-write; use a copy.", who=OWNER, minutes_ago=10):
        self.scene.comments.setdefault(72, []).append(
            {"id": cid, "user": {"login": who}, "body": body, "created_at": ts(minutes_ago)})

    def test_the_owners_comment_after_an_overstep_starts_one_builder(self):
        self.say(901)
        done = self.watcher().tick(NOW)
        self.assertEqual([(t.kind, t.ref) for t in done], [("ruling", "PR #72")])
        self.assertEqual(self.started(), [("builder-pr-72", "builder", "m-builder", 73, "watch")])
        e = self.l.load()[0]
        self.assertEqual((e.pr, e.ruling_comment), (72, 901))
        argv = headless_argv(self.fake.commands[0])
        self.assertEqual(argv[argv.index("-p") + 1],
                         swarm.opener("builder", 73, 72, ruling="Don't mount the shared .git read-write; "
                                      "use a copy.", ruling_comment=901))
        self.assertIn("then apply the owner's ruling on the overstep on PR #72, which closes issue #73.",
                      argv[argv.index("-p") + 1])
        self.assertIn("[ruling] PR #72 the owner commented after the overstep at aaaaaaa (comment 901) "
                      "-> starting builder-pr-72", self.lines)
        self.exit("builder-pr-72")
        self.assertEqual(self.watcher().tick(NOW), [])          # keyed on the comment: once
        self.say(902, "And keep the token read-only.", minutes_ago=5)
        self.assertEqual([t.kind for t in self.watcher().tick(NOW)], ["ruling"])   # a new comment
        self.assertEqual(len(self.fake.commands), 2)

    def test_a_non_owner_comment_starts_nothing(self):
        self.say(901, who="productswarm-planner[bot]")
        self.say(902, who="someone")
        self.assertEqual(self.watcher().tick(NOW), [])
        self.assertEqual(self.fake.commands, [])

    def test_a_comment_before_the_overstep_starts_nothing(self):
        self.say(901, minutes_ago=40)
        self.assertEqual(self.watcher().tick(NOW), [])

    def test_no_overstep_at_head_starts_nothing(self):
        self.say(901)
        self.overstep(authority="pass")                          # a plain comment review
        self.assertEqual(self.watcher().tick(NOW), [])
        self.overstep(commit=SHA2)                               # an overstep on an older head
        self.assertEqual([t.kind for t in self.watcher().tick(NOW)], ["review"])
        self.assertEqual([c for c in self.fake.commands if "ruling" in c], [])

    def test_another_roles_pr_starts_that_role(self):
        """#738: a ruling starts the PR's author role, as [respond] does."""
        self.say(901)
        self.scene.prs[0]["author"] = {"login": "app/productswarm-docs"}
        self.assertEqual([(t.kind, t.role) for t in self.watcher().tick(NOW)], [("ruling", "docs")])
        self.assertEqual(self.started(), [("docs-pr-72", "docs", "m-docs", 73, "watch")])
        self.assertIn("as roles/docs.md says", self.fake.commands[0])

    def test_a_non_swarm_pr_or_one_closing_no_issue_is_skipped(self):
        self.say(901)
        self.scene.prs[0]["author"] = {"login": OWNER}
        self.assertEqual([t.kind for t in self.watcher().tick(NOW)], ["ruling"])
        self.assertIn("skipped: it is a non-swarm PR, and a ruling starts only builder, planner",
                      self.lines[-1])
        self.scene.prs, self.scene.issues = [pr(72, SHA1)], []
        self.say(902, minutes_ago=5)
        self.watcher().tick(NOW)
        self.assertIn("skipped: it closes 0 issues", self.lines[-1])
        self.assertEqual(self.fake.commands, [])

    def test_a_live_session_on_the_issue_holds_it(self):
        self.say(901)
        self.scene.tracking[0], self.scene.comments[200] = tracking(200, "busy-sid", "builder", 73)
        self.assertEqual(self.watcher().tick(NOW), [])
        self.scene.tracking, self.scene.comments[200] = [], []
        self.assertEqual([t.kind for t in self.watcher().tick(NOW)], ["ruling"])

    def test_dry_run_prints_it(self):
        self.say(901, "See issue #5 first.\n\nThen   fix it.")
        w = watch.Watch(self.l, REPO, OWNER, ROLES, manifest_path=self.path, read=self.scene.read)
        w.tick(NOW)
        self.assertEqual(trigger_lines(self.lines),
                         ["[ruling] PR #72 the owner commented after the overstep at aaaaaaa (comment 901) "
                          "-> would start `launcher/swarm launch builder --issue 73 --pr 72`"])
        argv = headless_argv(self.lines[1].strip())
        self.assertIn('(comment 901): "See #5 first. Then fix it."', argv[argv.index("-p") + 1])
        self.assertEqual(self.fake.commands, [])

    def test_ruling_text_is_folded_and_capped(self):
        self.assertEqual(watch.ruling_text(" a\n\n b  issue #4 "), "a b #4")
        self.assertEqual(len(watch.ruling_text("x" * 5000)), watch.RULING_MAX)

    def test_gather_reads_the_comments_of_an_overstepped_pr_only(self):
        self.say(901)
        self.scene.prs.append(pr(74, SHA2, closes=[73]))
        self.scene.comments[74] = [{"id": 1}]

        def run(argv, **kw):
            return subprocess.CompletedProcess(argv, 0, self.scene.gh(argv), "")
        fake_sub = types.SimpleNamespace(run=run, SubprocessError=subprocess.SubprocessError)
        with mock.patch.object(G, "subprocess", fake_sub), mock.patch.object(G.ghql, "subprocess", fake_sub):
            w = watch.gather(REPO, 15, NOW)
        self.assertEqual([c["id"] for c in w.comments[72]], [901])
        self.assertNotIn(74, w.comments)


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


def limited_json(message="You've hit your 5-hour limit · resets 1pm (Europe/London)", sid="run-sid"):
    """The result of #410's run on 5 Nov (#489), trimmed: a 429 that Claude Code reports as
    subtype success with is_error set, in 2 seconds at $0.00."""
    return json.dumps({"type": "result", "subtype": "success", "is_error": True, "num_turns": 1,
                       "session_id": sid, "total_cost_usd": 0, "duration_ms": 1861,
                       "terminal_reason": "api_error", "api_error_status": 429,
                       "api_error_origin": "first_party", "api_error": "usage_limit_reached",
                       "result": message}) + "\n"


def hhmm(t: dt.datetime) -> str:
    """How the loop shows a hold's end: this machine's local time."""
    return t.astimezone().strftime("%H:%M")


class WaitsOnTest(unittest.TestCase):
    """#490: a [build] waits until the issues its body's `**Waits on:**` line names are closed."""

    setUp_start = StartTest.setUp
    manifest, watcher, started, exit, inbox = (StartTest.manifest, StartTest.watcher, StartTest.started,
                                               StartTest.exit, StartTest.inbox)

    def setUp(self):
        self.setUp_start()
        sc = self.scene
        sc.issues = [issue(49, ["ready"], body="**Files:** `x.py`\n**Waits on:** #456.\n"),
                     issue(456, title="the blocker")]
        sc.events = {49: [ev("ready", eid=11)]}
        sc.prs, sc.reviewed, sc.tracking, sc.comments = [], {}, [], {}

    def close(self, n):
        self.scene.issues = [i for i in self.scene.issues if i["number"] != n]

    def test_waits_on_reads_the_line(self):
        for body, want in [
            ("", []),
            (None, []),
            ("**Files:** `a.py`\n", []),                               # no line
            ("**Waits on:** nothing.\n", []),
            ("**Waits on:** Nothing\n", []),
            ("**Waits on:** #456.\n", [456]),
            ("x\n**Waits on:** #457 (the record) and #456, #457\n", [456, 457]),
            ("We hit #12 earlier.\n**Waits on:** nothing.\n", []),    # refs elsewhere don't count
            ("**waits on:** #3\n", [3]),
            # #487's line: prose after "nothing" or after the first sentence isn't a blocker.
            ("**Waits on:** nothing. Do this before #480's stage 1 makes tests required.\n", []),
            ("**Waits on:** #456. Then #480 can go.\n", [456]),
            ("Blockers are named (`**Waits on:** #456`) in prose.\n", []),   # not at line start
        ]:
            self.assertEqual(watch.waits_on(body), want, body)

    def test_blocked_names_only_the_open_ones(self):
        w = watch.World(model={}, issues=[issue(456), issue(458)])
        self.assertIsNone(watch.blocked("**Waits on:** nothing.", w))
        self.assertIsNone(watch.blocked("no line here", w))
        self.assertIsNone(watch.blocked("**Waits on:** #457", w))            # closed
        self.assertEqual(watch.blocked("**Waits on:** #456", w), "held: waits on #456")
        self.assertEqual(watch.blocked("**Waits on:** #458, #457, #456", w),
                         "held: waits on #456, #458")                         # a mix

    def test_dry_run_holds_then_fires_on_the_tick_after_the_blocker_closes(self):
        w = watch.Watch(self.l, REPO, OWNER, ROLES, read=self.scene.read, manifest_path=self.path)
        self.assertEqual(w.tick(NOW), [])                    # printed, not returned (#488)
        self.assertEqual(self.lines, ["[build] #49 ready by the owner -> held: waits on #456"])
        self.assertEqual(w.tick(NOW), [])                    # logged once while held
        self.assertEqual(len(self.lines), 1)
        self.close(456)
        (t,) = w.tick(NOW)
        self.assertIsNone(t.held)
        self.assertEqual(self.lines[1],
                         "[build] #49 ready by the owner -> would start `launcher/swarm launch builder --issue 49`")
        self.assertEqual(len(self.lines), 3)                 # with its headless command

    def test_holds_without_acting_then_starts_once_every_blocker_is_closed(self):
        self.scene.issues[0]["body"] = "**Waits on:** #456, #457\n"
        self.scene.issues.append(issue(457))
        w = self.watcher()
        self.assertEqual(w.tick(NOW), [])
        self.assertEqual(self.started(), [])
        self.assertEqual(watch.load_state(self.l)["acted"], {})
        self.assertIn("- [build] #49 ready by the owner · held: waits on #456, #457", self.inbox())
        self.close(457)
        self.assertEqual(w.tick(NOW), [])                    # #456 is still open
        self.assertIn("- [build] #49 ready by the owner · held: waits on #456", self.inbox())
        self.close(456)
        self.assertEqual([t.ref for t in w.tick(NOW)], ["#49"])
        self.assertEqual([s[0] for s in self.started()], ["builder-issue-49"])
        self.assertEqual(self.inbox(), "Nothing is waiting on you.")

    def test_an_open_blocker_with_an_open_pr_closing_it_still_holds(self):
        # #550, 6 Nov 12:33: #457 waited on #456, and PR #546 (open) closed #456.
        self.scene.prs, self.scene.reviewed = [pr(546, closes=[456])], {546: {SHA1}}
        w = self.watcher()
        for minutes in (0, 5):
            self.assertEqual(w.tick(NOW + dt.timedelta(minutes=minutes)), [])
        self.assertEqual(self.started(), [])
        self.assertEqual(watch.load_state(self.l)["acted"], {})
        self.assertIn("- [build] #49 ready by the owner · held: waits on #456", self.inbox())
        self.close(456)
        self.scene.prs = []                                     # PR #546 merged
        self.assertEqual([t.ref for t in w.tick(NOW + dt.timedelta(minutes=10))], ["#49"])

    def test_no_line_or_nothing_starts_as_usual(self):
        for body in ("", "**Waits on:** nothing.\n"):
            self.setUp()
            self.scene.issues[0]["body"] = body
            self.assertEqual([t.ref for t in self.watcher().tick(NOW)], ["#49"])


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

    def test_a_usage_limit_is_limited_with_its_message(self):
        r = self.read(BANNER + limited_json())
        self.assertEqual(r, {"ending": "limited", "cost_usd": 0.0, "subtype": "success",
                             "detail": "You've hit your 5-hour limit · resets 1pm (Europe/London)"})

    def test_any_429_or_usage_limit_is_limited(self):
        for extra in ({"api_error_status": 429}, {"api_error": "usage_limit_reached"}):
            with self.subTest(extra=extra):
                d = {"type": "result", "subtype": "success", "is_error": True, "total_cost_usd": 0, **extra}
                r = self.read(json.dumps(d))
                self.assertEqual(r["ending"], "limited")
                self.assertTrue(r["detail"])

    def test_a_non_number_cost_is_no_cost(self):
        self.assertIsNone(self.read(result_json("success", "lots"))["cost_usd"])
        self.assertIsNone(self.read(result_json("success", True))["cost_usd"])


class LimitUntilTest(unittest.TestCase):
    """watch.limit_until(): when a limited run's hold ends (#489)."""

    def test_the_next_reset_time_in_the_named_zone(self):
        london = dt.timezone.utc                                 # GMT in November
        self.assertEqual(watch.limit_until("resets 1pm (Europe/London)", NOW),
                         dt.datetime(2026, 11, 3, 13, 0, tzinfo=london))
        self.assertEqual(watch.limit_until("· resets 12:30am (America/New_York)", NOW),   # 07:00 there
                         dt.datetime(2026, 11, 4, 5, 30, tzinfo=dt.timezone.utc))

    def test_a_reset_time_already_past_today_is_tomorrow(self):
        self.assertEqual(watch.limit_until("resets 12pm (Europe/London)", NOW),
                         dt.datetime(2026, 11, 4, 12, 0, tzinfo=dt.timezone.utc))

    def test_no_zone_is_this_machines(self):
        got = watch.limit_until("resets 3pm", NOW).astimezone()
        self.assertEqual((got.hour, got.minute), (15, 0))
        self.assertTrue(NOW < got <= NOW + dt.timedelta(days=1))

    def test_no_readable_reset_time_holds_thirty_minutes(self):
        for msg in (None, "", "rate limited", "resets soon", "resets 13pm", "resets 1pm (Not/AZone)"):
            with self.subTest(msg=msg):
                self.assertEqual(watch.limit_until(msg, NOW), NOW + dt.timedelta(minutes=30))


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
        self.exit(name, ran=False)
        return e

    def state(self):
        return watch.load_state(self.l)

    def transcript(self, sid):
        """Claude Code wrote a transcript for sid: it got as far as starting (#550)."""
        p = self.home / "claude" / "projects" / "-repo-.worktrees-x" / f"{sid}.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("{}\n")

    def inbox(self, now=NOW):
        return swarm.inbox_text([], now, G, watch.waiting(self.l), watch.runs(self.l))

    def test_each_ending_is_recorded_against_its_trigger_and_nothing_restarts(self):
        self.watcher().tick(NOW)
        ends = {"builder-issue-49": BANNER + CANNED["budget"], "docs-issue-87": BANNER + CANNED["success"],
                "planner-issue-88": BANNER + CANNED["error"], "reviewer-watch": BANNER}
        sids = {name: self.end(name, text).session_id for name, text in ends.items()}
        self.transcript(sids["reviewer-watch"])     # it ran, so it isn't tried again (#550)
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
        self.scene.tracking, self.scene.comments = [], {}       # nothing held on #60 (#488)
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

    def starts(self, needle):
        """How many sessions the loop has started whose command contains `needle`."""
        return sum(needle in c for c in self.fake.commands)

    def test_a_limited_run_fires_again_after_the_reset_with_no_label_change(self):
        self.watcher().tick(NOW)
        self.end("builder-issue-49", BANNER + limited_json())
        self.scene.issues.append(issue(50, ["ready"]))           # new work arrives while limited
        self.scene.events[50] = [ev("ready", eid=15)]
        later = NOW + dt.timedelta(minutes=5)
        self.assertEqual(self.watcher().tick(later), [])
        st = self.state()
        self.assertNotIn("build:49:11", st["acted"])
        self.assertEqual(st["runs"]["build:49:11"]["ending"], "limited")
        self.assertEqual(st["runs"]["build:49:11"]["until"], "2026-11-03T13:00:00+00:00")
        reason = f"held: usage limit (until {hhmm(NOW.replace(hour=13))})"
        self.assertEqual({x["ref"]: x["reason"] for x in st["waiting"]},
                         {"#49": reason, "#50": reason,   # #60's live builder holds it (#488)
                          "#60": "held: builder session busy-sid is live on #60 (active)"})
        self.assertIn("[build] #49 builder-issue-49 · limited (You've hit your 5-hour limit · resets 1pm "
                      "(Europe/London)) · $0.00 (est.) -> recorded; trying again after the hold", self.lines)
        self.watcher().tick(later + dt.timedelta(minutes=5))       # said once, across checks
        self.assertEqual([x for x in self.lines if "usage limit" in x and "[build]" not in x],
                         [f"swarm watch: a run hit the account's usage limit; {reason}, for every start (#489)"])
        self.assertEqual(self.starts("work on issue #49."), 1)
        self.assertEqual(self.starts("work on issue #50."), 0)
        self.assertIn(reason, self.inbox(later))
        done = self.watcher().tick(NOW.replace(hour=13, minute=1))
        self.assertEqual([t.ref for t in done], ["#49", "#50"])      # held longest first
        self.assertEqual((self.starts("work on issue #49."), self.starts("work on issue #50.")), (2, 1))
        self.assertEqual(self.scene.events[49], [ev("ready", eid=11)])   # no label change

    def test_no_reset_time_holds_thirty_minutes(self):
        self.watcher().tick(NOW)
        self.end("builder-issue-49", BANNER + limited_json("Rate limited"))
        self.watcher().tick(NOW)
        self.assertEqual(self.watcher().tick(NOW + dt.timedelta(minutes=29)), [])
        self.assertEqual(self.state()["waiting"][0]["reason"],
                         f"held: usage limit (until {hhmm(NOW + dt.timedelta(minutes=30))})")
        self.assertEqual([t.ref for t in self.watcher().tick(NOW + dt.timedelta(minutes=30))], ["#49"])

    def test_a_limited_reviewer_pass_fires_every_review_it_covered_again(self):
        self.scene.prs.append(pr(72, SHA2))
        self.scene.reviewed[72] = set()
        self.watcher().tick(NOW)
        self.assertIn("covered by reviewer-watch", self.state()["acted"].values())
        self.end("reviewer-watch", BANNER + limited_json())
        later = NOW.replace(hour=13, minute=1)
        self.watcher().tick(NOW)
        done = self.watcher().tick(later)
        self.assertEqual([t.ref for t in done], ["PR #70", "PR #72"])
        self.assertEqual(sum(e.role == "reviewer" for e in self.l.load()), 1)   # one pass covers both again
        self.assertEqual(len(self.fake.commands), 5)

    def test_an_ordinary_error_is_still_not_retried_or_held(self):
        self.watcher().tick(NOW)
        self.end("builder-issue-49", BANNER + CANNED["error"])
        self.scene.issues.append(issue(50, ["ready"]))
        self.scene.events[50] = [ev("ready", eid=15)]
        self.assertEqual([t.ref for t in self.watcher().tick(NOW + dt.timedelta(minutes=5))], ["#50"])
        self.assertTrue(self.state()["acted"]["build:49:11"].startswith("started "))
        self.assertEqual(self.watcher().tick(NOW + dt.timedelta(hours=2)), [])
        self.assertEqual(self.starts("work on issue #49."), 1)
        self.assertFalse(any("usage limit" in x for x in self.lines))

    def test_old_state_without_runs_still_loads(self):
        (self.home / "launcher" / "watch.json").write_text(json.dumps({"checked": None, "acted": {}, "waiting": []}))
        self.assertEqual(watch.load_state(self.l)["runs"], {})
        self.assertEqual(watch.runs(self.l), [])


class HeldTest(unittest.TestCase):
    """#488: a trigger a live session holds is listed with who holds it, and called stale
    with the `swarm stop` that frees it once that session has been idle past stale_minutes."""

    setUp_start = StartTest.setUp
    manifest, watcher, exit, inbox = StartTest.manifest, StartTest.watcher, StartTest.exit, StartTest.inbox
    RECORD = "[record] #87 gov:ruled by the owner, needs a record (domain governance) -> "

    def setUp(self):
        self.setUp_start()
        sc = self.scene
        sc.issues, sc.events = [sc.issues[2]], {87: sc.events[87]}       # just the ruled question
        sc.prs, sc.reviewed, sc.tracking, sc.comments = [], {}, [], {}

    def docs_on_87(self, minutes_ago, by_launcher=True):
        """docs on #87, quiet for minutes_ago: swarm-launched as docs-issue-87, or by hand."""
        if by_launcher:
            self.l.start(swarm.Started("docs-issue-87", "docs", "m", "docs-sid", self.fake.t, issue=87), [])
            self.lines.clear()                                  # the launcher's own `started:` line
        it, comments = tracking(201, "docs-sid", "docs", 87, minutes_ago)
        self.scene.tracking, self.scene.comments = [it], {201: comments}

    def dry(self, **kw):
        path = write_manifest(self.home, ALL_CAPPED, **kw)
        return watch.Watch(self.l, REPO, OWNER, ROLES, read=self.scene.read, manifest_path=path)

    def test_dry_run_prints_the_held_record_with_its_holder_and_idle_time(self):
        self.docs_on_87(30)
        w = self.dry()
        self.assertEqual(w.tick(NOW), [])
        self.assertEqual(self.lines, [self.RECORD + "held: docs-issue-87 is live on #87 (idle since 11:30 UTC)"])
        self.assertEqual(w.tick(NOW), [])                       # once per holder state
        self.assertEqual(len(self.lines), 1)

    def test_past_stale_minutes_it_says_stale_and_gives_the_stop_command(self):
        self.docs_on_87(600)
        self.dry().tick(NOW)
        self.assertEqual(self.lines, [self.RECORD + "stale: docs-issue-87 idle 10h; "
                                                    "swarm stop docs-issue-87 frees #87"])
        self.lines.clear()
        self.dry(stale_minutes=720).tick(NOW)                   # [watch] stale_minutes = 720
        self.assertEqual(self.lines, [self.RECORD + "held: docs-issue-87 is live on #87 (idle since 02:00 UTC)"])

    def test_a_holder_not_started_by_swarm_names_no_swarm_stop(self):
        self.docs_on_87(90, by_launcher=False)
        self.dry().tick(NOW)
        self.assertEqual(self.lines, [self.RECORD + "stale: docs session docs-sid idle 1h; it wasn't "
                                                    "started by swarm, so stop it where it runs to free #87"])

    def test_an_active_holder_and_one_with_no_heartbeat_yet(self):
        self.docs_on_87(1)
        self.dry().tick(NOW)
        self.assertEqual(self.lines, [self.RECORD + "held: docs-issue-87 is live on #87 (active)"])
        self.lines.clear()
        self.scene.tracking, self.scene.comments = [], {}
        self.dry().tick(NOW)
        self.assertEqual(self.lines, [self.RECORD + "held: docs-issue-87 is live on #87 "
                                                    "(starting, no heartbeat yet)"])

    def test_held_then_stale_is_listed_logged_once_each_and_fires_when_the_holder_stops(self):
        self.manifest(ALL_CAPPED)
        self.docs_on_87(30)
        w = self.watcher()
        self.assertEqual(w.tick(NOW), [])
        held = "held: docs-issue-87 is live on #87 (idle since 11:30 UTC)"
        self.assertEqual(self.lines, [self.RECORD + held])
        self.assertIn(f"- [record] #87 gov:ruled by the owner, needs a record (domain governance) · {held}",
                      self.inbox())
        self.assertEqual(w.tick(NOW), [])
        self.assertEqual(len(self.lines), 1)                    # logged once per reason
        later = NOW + dt.timedelta(hours=10)
        self.assertEqual(w.tick(later), [])
        stale = "stale: docs-issue-87 idle 10h; swarm stop docs-issue-87 frees #87"
        self.assertEqual(self.lines[-1], self.RECORD + stale)
        self.assertIn(stale, self.inbox())
        self.assertEqual(w.tick(later + dt.timedelta(hours=1)), [])   # 11h: still the same state
        self.assertEqual(len(self.lines), 2)
        self.assertEqual(len(self.fake.commands), 1)            # only the docs started by hand
        self.exit("docs-issue-87")                              # the owner ran swarm stop
        self.scene.tracking[0]["state"] = "closed"
        self.assertEqual([t.kind for t in w.tick(later)], ["record"])
        self.assertEqual(self.l.load()[-1].name, "docs-issue-87")
        self.assertEqual(self.inbox(), "Nothing is waiting on you.")

    def test_respond_and_answer_are_held_too(self):
        sc = self.scene
        sc.issues = [issue(73, ["ready"]),
                     issue(88, ["gov:question", "ready"], question_body(raised="planner, on #87"))]
        sc.events = {73: [ev("ready", eid=15)], 88: [ev("ready", eid=14)]}
        sc.prs, sc.reviews = [pr(72, SHA1, closes=[73])], {72: [review("CHANGES_REQUESTED", SHA1)]}
        sc.reviewed = {72: {SHA1}}
        a, ac = tracking(201, "b-sid", "builder", 73, 30)
        b, bc = tracking(202, "p-sid", "planner", 88, 30)
        sc.tracking, sc.comments = [a, b], {201: ac, 202: bc}
        self.dry().tick(NOW)
        self.assertEqual(self.lines, [
            "[respond] PR #72 changes requested at aaaaaaa (round 1 of 2) -> held: builder session "
            "b-sid is live on #73 (idle since 11:30 UTC)",
            "[answer] #88 ready by the owner -> held: planner session p-sid is live on #88 "
            "(idle since 11:30 UTC)"])

    def test_stale_minutes_is_a_positive_whole_number_and_defaults_to_60(self):
        import manifest
        base = '[watch]\ninterval_minutes = 5\nmax_live = 2\n%s\n[[session]]\nrole = "builder"\ncount = 1\nmodel = "m"\n'
        self.assertEqual(manifest.parse_all(base % "")[1].stale_minutes, 60)
        self.assertEqual(manifest.parse_all(base % "stale_minutes = 90")[1].stale_minutes, 90)
        for v in ("0", "-3", "1.5", '"60"', "true"):
            with self.assertRaises(manifest.ManifestError, msg=v) as c:
                manifest.parse_all(base % f"stale_minutes = {v}")
            self.assertEqual(c.exception.problems,
                             [f"watch: stale_minutes must be a whole number of at least 1, got {manifest.tomllib.loads('v = ' + v)['v']!r}"])


BUILDER_APP, PLANNER_APP = "productswarm-builder[bot]", "productswarm-planner[bot]"


def call(cid, body, who=BUILDER_APP, at=None):
    """A comment on an issue, posted 5 minutes ago unless `at` says when."""
    return {"id": cid, "body": body, "user": {"login": who}, "created_at": at or ts(5)}


class CallInTest(unittest.TestCase):
    """GOV-0023's [call-in] trigger (#520). In the Scene, a builder is live on ready #60."""

    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        (self.home / "launcher").mkdir()
        self.fake = Fake(self.home / "launcher")
        self.lines = []
        self.l = swarm.Launcher(self.home, run=self.fake.run, proc=self.fake.proc, kill=self.fake.kill,
                                clock=self.fake.clock, sleep=lambda s: None, out=self.lines.append,
                                root=self.home / "repo", git=FakeGit(), claude_dir=self.home / "claude")
        self.scene = Scene()
        self.manifest(ALL_CAPPED, call_ins=True)

    def manifest(self, caps, max_live=10, **kw):
        self.path = write_manifest(self.home, caps, max_live, **kw)

    def watcher(self, dry_run=False):
        return watch.Watch(self.l, REPO, OWNER, ROLES, dry_run=dry_run, manifest_path=self.path,
                           read=self.scene.read, get_issue=self.scene.get_issue,
                           get_heartbeat=self.scene.heartbeat)

    def tick(self, dry_run=False):
        """The [call-in] triggers one check acted on or printed for the first time."""
        return [t for t in self.watcher(dry_run).tick(NOW) if t.kind == "call-in"]

    def called(self):
        return [(e.name, e.role, e.issue, e.called_by, e.call_why) for e in self.l.load()
                if e.called_by]

    def say(self, *comments, n=60):
        self.scene.comments[n] = list(comments)

    def call_lines(self):
        return [x for x in self.lines if x.startswith("[call-in]")]

    def test_a_call_starts_each_named_role_once_beside_the_live_caller(self):
        self.say(call(501, "Need a second view.\nCall in: docs, planner: check the wording\nThanks"))
        self.assertEqual([t.key for t in self.tick()], ["call-in:60:501:docs", "call-in:60:501:planner"])
        who = "the builder (productswarm-builder[bot])"
        self.assertEqual(self.called(), [("docs-issue-60", "docs", 60, who, "check the wording"),
                                         ("planner-issue-60", "planner", 60, who, "check the wording")])
        cmd = [c for c in self.fake.commands if "docs-issue-60" in c or "roles/docs.md" in c][-1]
        self.assertIn("answer a call-in on issue #60: the builder (productswarm-builder[bot]) called "
                      "you in (GOV-0023) because: check the wording.", cmd)
        self.assertIn("post one comment on it", cmd)
        argv = headless_argv(cmd)          # GOV-0012's budget and turns, GOV-0013's denies
        self.assertEqual(argv[argv.index("--max-budget-usd") + 1], "10")
        self.assertEqual(argv[argv.index("--max-turns") + 1], "50")
        self.assertIn("Bash(gh pr merge *)", argv)
        n = len(self.fake.commands)
        self.assertEqual(self.tick(), [])                 # keyed on the comment: once per call
        for name in ("docs-issue-60", "planner-issue-60"):
            StartTest.exit(self, name)
        self.assertEqual(self.tick(), [])                 # and not again once they stop
        self.assertEqual(len(self.fake.commands), n)

    def test_the_owner_may_call_and_anyone_else_is_skipped(self):
        self.say(call(501, "Call in: docs: drive-by", who="stranger"),
                 call(502, "call in: planner: please plan", who=OWNER))
        done = self.tick()
        self.assertEqual([(t.key, t.skipped) for t in done], [
            ("call-in:60:501", "stranger isn't a swarm App or the owner, so the call doesn't count (GOV-0023)"),
            ("call-in:60:502:planner", None)])
        self.assertEqual([c[:4] for c in self.called()], [("planner-issue-60", "planner", 60, "the owner")])
        self.assertIn("[call-in] #60 call in by stranger (comment 501) -> skipped: stranger isn't a swarm "
                      "App or the owner, so the call doesn't count (GOV-0023)", self.lines)

    def test_a_role_cant_call_itself_and_unknown_names_are_skipped(self):
        self.say(call(501, "Call in: builder, designer, docs: x"))
        done = self.tick()
        self.assertEqual([(t.key, t.skipped) for t in done], [
            ("call-in:60:501:builder", "a role can't call itself in (GOV-0023)"),
            ("call-in:60:501:designer", "'designer' isn't a role with a prompt in roles/"),
            ("call-in:60:501:docs", None)])
        self.assertEqual([c[0] for c in self.called()], ["docs-issue-60"])

    def test_at_most_two_calls_count_per_issue_per_utc_day(self):
        self.say(call(500, "Call in: builder: only myself", at="2026-11-03T08:00:00Z"),  # doesn't count
                 call(501, "Call in: docs: one", at="2026-11-03T09:00:00Z"),
                 call(502, "Call in: reviewer: two", who=PLANNER_APP, at="2026-11-03T10:00:00Z"),
                 call(503, "Call in: planner: three", at="2026-11-03T11:00:00Z"),
                 call(504, "Call in: planner: next day", at="2026-11-04T00:00:00Z"))
        done = {t.key: t.skipped for t in self.tick()}
        self.assertEqual(done["call-in:60:503"], "#60 already has 2 calls on 2026-11-03 (UTC), the most "
                                                 "that count per issue per day (GOV-0023)")
        self.assertEqual(sorted(c[0] for c in self.called()),
                         ["docs-issue-60", "planner-issue-60", "reviewer-issue-60"])
        self.assertEqual([c[4] for c in self.called() if c[1] == "planner"], ["next day"])

    def test_the_switch_off_starts_nothing_records_nothing_and_on_starts_it(self):
        self.manifest(ALL_CAPPED)                         # no call_ins: off by default
        self.say(call(501, "Call in: docs: x"))
        w = self.watcher()
        self.assertEqual([t for t in w.tick(NOW) if t.kind == "call-in"], [])
        self.assertEqual(self.called(), [])
        off = f"[call-in] #60 call in by {BUILDER_APP} (comment 501): docs -> skipped: {watch.CALL_INS_OFF}"
        self.assertEqual(self.call_lines(), [off])
        w.tick(NOW)
        self.assertEqual(self.call_lines(), [off])       # said once
        self.assertFalse(any(k.startswith("call-in") for k in watch.load_state(self.l)["acted"]))
        self.manifest(ALL_CAPPED, call_ins=False)
        self.assertEqual(self.tick(), [])
        self.manifest(ALL_CAPPED, call_ins=True)
        self.assertEqual([t.key for t in self.tick()], ["call-in:60:501:docs"])

    def test_a_live_session_of_the_called_role_holds_it(self):
        self.scene.prs.append(pr(72, SHA2, closes=(60,)))  # no [build] on #60 to take the slot
        self.say(call(501, "Call in: builder: a second pair of hands", who=PLANNER_APP))
        self.assertEqual(self.tick(), [])
        self.assertEqual(self.called(), [])
        (held,) = [x for x in watch.waiting(self.l)[1] if x["kind"] == "call-in"]
        self.assertEqual(held["reason"], "held: builder session busy-sid is live on #60 (active)")
        self.scene.tracking, self.scene.comments[200] = [], []     # the builder stops
        self.assertEqual([t.key for t in self.tick()], ["call-in:60:501:builder"])

    def test_a_call_from_before_the_owners_ready_doesnt_count(self):
        self.scene.events[60] = [{**ev("ready", eid=12), "created_at": ts(10)}]
        self.say(call(501, "Call in: docs: old", at=ts(20)), call(502, "Call in: planner: new", at=ts(5)))
        self.assertEqual([t.key for t in self.tick()], ["call-in:60:502:planner"])

    def test_a_ready_question_counts_too(self):
        self.say(call(502, "Call in: docs: x", who=PLANNER_APP), n=88)
        self.assertEqual([t.key for t in self.tick()], ["call-in:88:502:docs"])

    def test_not_ready_or_not_the_owners_ready_starts_nothing(self):
        self.scene.events[60] = [ev("ready", actor="someone", eid=12)]
        self.say(call(501, "Call in: docs: x"))
        self.scene.issues.append(issue(90))
        self.say(call(503, "Call in: docs: x"), n=90)
        self.assertEqual(self.tick(), [])
        self.assertEqual(self.call_lines(), [])

    def test_runs_stay_inside_gov_0010(self):
        self.manifest({r: 10 for r in ROLES if r != "docs"}, call_ins=True)
        self.say(call(501, "Call in: docs: x"))
        self.tick()
        (held,) = [x for x in watch.waiting(self.l)[1] if x["kind"] == "call-in"]
        self.assertIn("docs has no spend_cap_usd", held["reason"])
        self.manifest(ALL_CAPPED, max_live=4, call_ins=True)     # the other four triggers fill it
        self.tick()
        (held,) = [x for x in watch.waiting(self.l)[1] if x["kind"] == "call-in"]
        self.assertEqual(held["reason"], "held: 4 of 4 sessions swarm watch started are live (GOV-0010)")

    def test_dry_run_prints_it_with_the_headless_command(self):
        self.say(call(501, "Call in: docs: x"))
        self.assertEqual([t.key for t in self.tick(dry_run=True)], ["call-in:60:501:docs"])
        i = self.lines.index(f"[call-in] #60 call in by {BUILDER_APP} (comment 501): docs -> would start "
                             f"docs on #60, called in")
        self.assertIn("answer a call-in on issue #60", self.lines[i + 1])
        self.assertEqual(self.l.load(), [])

    def test_gather_reads_the_comments_of_ready_issues(self):
        self.say(call(501, "Call in: docs: x"))

        def run(argv, **kw):
            return subprocess.CompletedProcess(argv, 0, self.scene.gh(argv), "")
        fake_sub = types.SimpleNamespace(run=run, SubprocessError=subprocess.SubprocessError)
        with mock.patch.object(G, "subprocess", fake_sub), mock.patch.object(G.ghql, "subprocess", fake_sub):
            w = watch.gather(REPO, 15, NOW)
        self.assertEqual([c["id"] for c in w.comments[60]], [501])
        self.assertNotIn(200, w.comments)                 # not tracking issues

    def test_call_line(self):
        self.assertEqual(watch.call_line("hi\n  CALL IN: Docs , `planner`, docs:  why  this \nbye"),
                         (["docs", "planner"], "why this"))
        self.assertEqual(watch.call_line("Call in: docs"), (["docs"], ""))
        self.assertEqual(watch.call_line("Call in: docs: a: b"), (["docs"], "a: b"))
        self.assertIsNone(watch.call_line("Recall in: docs: x"))
        self.assertIsNone(watch.call_line("We could `Call in: docs: x` here"))
        self.assertEqual(len(watch.call_line("Call in: docs: " + "x" * 999)[1]), watch.WHY_MAX)

    def test_swarm_apps_come_from_jurisdictions(self):
        apps, why = watch.swarm_apps()
        self.assertIsNone(why)
        self.assertEqual(apps[BUILDER_APP], "builder")
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(watch.swarm_apps(Path(d) / "nope.yml")[0], {})



class MilestoneCallInTest(unittest.TestCase):
    """#594 (GOV-0029): `Call in:` lines count on an issue under an open PLAN.md milestone,
    not only on a `ready` one. #90 is under M1 with no `ready`; #60 is ready."""

    setUp_call = CallInTest.setUp
    manifest, tick, called, say = CallInTest.manifest, CallInTest.tick, CallInTest.called, CallInTest.say

    def setUp(self):
        self.setUp_call()
        sc = self.scene
        sc.plan = MILESTONE_PLAN
        sc.prs.append(pr(73, SHA2, closes=(90,)))        # no [build] on #90 to take a slot
        self.put(milestone_issue(90))

    def put(self, it, events=()):
        self.scene.issues = [i for i in self.scene.issues if i["number"] != it["number"]] + [it]
        self.scene.events[it["number"]] = list(events)

    def watcher(self, dry_run=False):
        return watch.Watch(self.l, REPO, OWNER, ROLES, dry_run=dry_run, manifest_path=self.path,
                           read=self.scene.read, get_issue=self.scene.get_issue,
                           get_heartbeat=self.scene.heartbeat, get_reader=self.scene.get_reader)

    def test_a_call_on_a_milestone_issue_without_ready_starts_the_role(self):
        self.say(call(501, "Call in: docs: check the wording"), n=90)
        self.assertEqual([t.key for t in self.tick()], ["call-in:90:501:docs"])
        self.assertEqual(self.called(), [("docs-issue-90", "docs", 90,
                                          "the builder (productswarm-builder[bot])", "check the wording")])
        self.assertEqual(self.tick(), [])                 # once per call

    def test_the_owners_call_and_a_blocked_issue_still_count(self):
        self.put(milestone_issue(90, waits="#456."))
        self.scene.issues.append(issue(456, title="the blocker"))
        self.say(call(501, "Call in: planner: plan it", who=OWNER), n=90)
        self.assertEqual([t.key for t in self.tick()], ["call-in:90:501:planner"])

    def test_no_milestone_or_a_closed_one_doesnt_count(self):
        no_plan = lambda: setattr(self.scene, "plan", None)
        cases = {
            "no milestone line": lambda: self.put(issue(90, body="**Milestone:** no milestone yet\n")),
            "done milestone": lambda: self.put(milestone_issue(90, "M2")),
            "milestone not in PLAN.md": lambda: self.put(milestone_issue(90, "M9")),
            "no PLAN.md on main": no_plan,
            "non-swarm author": lambda: self.put(milestone_issue(90, author="stranger")),
            "hold label": lambda: self.put(milestone_issue(90, labels=("hold",))),
            "gov:question": lambda: self.put(milestone_issue(90, labels=("gov:question",))),
        }
        for case, change in cases.items():
            with self.subTest(case):
                self.setUp()
                change()
                self.say(call(501, "Call in: docs: x"), n=90)
                self.assertEqual(self.tick(), [], case)
                self.assertEqual(self.called(), [], case)

    def test_a_ready_milestone_issue_starts_each_role_once(self):
        self.put(milestone_issue(90, labels=("ready",)), [{**ev("ready", eid=15), "created_at": ts(10)}])
        self.say(call(501, "Call in: docs: before ready", at=ts(20)),
                 call(502, "Call in: planner: after ready", at=ts(5)), n=90)
        self.assertEqual([t.key for t in self.tick()], ["call-in:90:501:docs", "call-in:90:502:planner"])
        self.assertEqual(sorted(c[0] for c in self.called()), ["docs-issue-90", "planner-issue-90"])
        self.assertEqual(self.tick(), [])

    def test_the_per_day_limit_counts_across_both(self):
        self.put(milestone_issue(90, labels=("ready",)),
                 [{**ev("ready", eid=15), "created_at": "2026-11-03T09:30:00Z"}])
        self.say(call(501, "Call in: docs: before ready", at="2026-11-03T09:00:00Z"),
                 call(502, "Call in: reviewer: after ready", at="2026-11-03T10:00:00Z"),
                 call(503, "Call in: planner: third", at="2026-11-03T11:00:00Z"), n=90)
        done = {t.key: t.skipped for t in self.tick()}
        self.assertEqual(done["call-in:90:503"], "#90 already has 2 calls on 2026-11-03 (UTC), the most "
                                                 "that count per issue per day (GOV-0023)")
        self.assertEqual(sorted(c[0] for c in self.called()), ["docs-issue-90", "reviewer-issue-90"])

    def test_the_switch_off_covers_milestone_calls(self):
        self.manifest(ALL_CAPPED)
        self.say(call(501, "Call in: docs: x"), n=90)
        self.assertEqual(self.tick(), [])
        self.assertEqual(self.called(), [])

    def test_a_milestone_marked_done_before_the_start_refuses_it(self):
        self.say(call(501, "Call in: docs: x"), n=90)
        w = self.watcher()
        real = self.scene.get_reader
        done = MILESTONE_PLAN.replace("## M1: Daily report runs without the owner",
                                      "## M1: Daily report runs without the owner\n\n- **Status:** done")
        self.scene.get_reader = lambda repo, n: swarm.GoReader(plan=lambda: done,
                                                               state=real(repo, n).state,
                                                               comments=real(repo, n).comments)
        w.get_reader = self.scene.get_reader
        w.tick(NOW)
        self.assertEqual(self.called(), [])
        self.assertTrue(any("marked done" in x for x in self.lines if x.startswith("[call-in] #90")),
                        self.lines)


DAILY_ON = 'daily = true\ndaily_at = "08:30"\nreport_issue = 600\n'
TUE = dt.datetime(2026, 11, 3, 12, 0, tzinfo=dt.timezone.utc)    # NOW: a Tuesday
UTC = dt.timezone.utc


class DailyTest(unittest.TestCase):
    """GOV-0029's [daily] trigger (#588): the planner on report issue #600, once each
    working day at or after daily_at. The Watch's time zone is UTC here."""

    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        (self.home / "launcher").mkdir()
        self.fake = Fake(self.home / "launcher")
        self.lines = []
        self.l = swarm.Launcher(self.home, run=self.fake.run, proc=self.fake.proc, kill=self.fake.kill,
                                clock=self.fake.clock, sleep=lambda s: None, out=self.lines.append,
                                root=self.home / "repo", git=FakeGit(), claude_dir=self.home / "claude")
        self.scene = Scene()
        self.scene.issues.append(issue(600, title="Daily report"))   # no label: it needs none
        self.manifest(DAILY_ON)

    def manifest(self, extra=""):
        self.path = write_manifest(self.home, ALL_CAPPED, 10, extra=extra)

    def watcher(self, dry_run=False, tz=UTC):
        return watch.Watch(self.l, REPO, OWNER, ROLES, dry_run=dry_run, manifest_path=self.path,
                           read=self.scene.read, get_issue=self.scene.get_issue,
                           get_heartbeat=self.scene.heartbeat, get_reader=self.scene.get_reader,
                           tz=tz)

    def tick(self, now, dry_run=False, tz=UTC):
        return [t for t in self.watcher(dry_run, tz).tick(now) if t.kind == "daily"]

    def dailies(self):
        return [(e.name, e.role, e.issue, e.daily) for e in self.l.load() if e.daily]

    def at(self, day, hh, mm=0):
        return dt.datetime(2026, 11, day, hh, mm, tzinfo=UTC)

    def test_fires_once_on_a_weekday_after_daily_at(self):
        self.assertEqual([t.key for t in self.tick(TUE)], ["daily:600:2026-11-03"])
        self.assertEqual(self.dailies(), [("planner-issue-600", "planner", 600, "the daily report")])
        cmd = [c for c in self.fake.commands if "roles/planner.md" in c][-1]
        self.assertIn("write the daily report on issue #600, as roles/planner.md says", cmd)
        self.assertNotIn("check-in", cmd)
        self.assertIn("run launcher/swarm trouble --json and build the Trouble section from it", cmd)
        argv = headless_argv(cmd)          # GOV-0012's budget and turns, GOV-0013's denies
        self.assertEqual(argv[argv.index("--max-turns") + 1], "50")
        self.assertIn("Bash(gh pr merge *)", argv)
        self.assertIn("[daily] #600 Tue 2026-11-03, due at 08:30 -> starting planner-issue-600",
                      self.lines)
        StartTest.exit(self, "planner-issue-600")
        n = len(self.fake.commands)
        self.assertEqual(self.tick(self.at(3, 18)), [])           # not twice in a day
        self.assertEqual(len(self.fake.commands), n)
        self.assertEqual([t.key for t in self.tick(self.at(4, 9))], ["daily:600:2026-11-04"])

    def test_not_before_daily_at(self):
        self.assertEqual(self.tick(self.at(3, 8, 29)), [])
        self.assertEqual(self.dailies(), [])
        self.assertEqual([t.key for t in self.tick(self.at(3, 8, 30))], ["daily:600:2026-11-03"])

    def test_a_missed_poll_fires_late_the_same_day(self):
        self.assertEqual([t.key for t in self.tick(self.at(3, 23, 55))], ["daily:600:2026-11-03"])

    def test_not_on_a_weekend(self):
        for day in (7, 8):                                       # Saturday, Sunday
            self.assertEqual(self.tick(self.at(day, 12)), [])
        self.assertEqual(self.dailies(), [])

    def test_mondays_prompt_names_the_check_in(self):
        self.tick(self.at(9, 9))
        self.assertEqual(self.dailies(), [("planner-issue-600", "planner", 600,
                                           "the daily report and the Monday check-in")])
        cmd = [c for c in self.fake.commands if "roles/planner.md" in c][-1]
        self.assertIn("write the daily report and the Monday check-in on issue #600", cmd)
        # #804: the check-in's Trouble section, like the daily report's, comes from swarm trouble.
        self.assertIn("run launcher/swarm trouble --json and build the Trouble section from it", cmd)

    def test_off_by_default(self):
        self.manifest()
        self.assertEqual(self.tick(TUE), [])
        self.assertEqual(self.tick(TUE, dry_run=True), [])
        self.assertFalse(any(x.startswith("[daily]") for x in self.lines))
        self.manifest('daily = false\ndaily_at = "08:30"\nreport_issue = 600\n')
        self.assertEqual(self.tick(TUE), [])

    def test_missing_report_issue_starts_nothing(self):
        self.manifest('daily = true\ndaily_at = "08:30"\n')
        with self.assertRaises(RuntimeError) as c:
            self.watcher().tick(TUE)
        self.assertIn("daily = true needs 'report_issue'", str(c.exception))
        self.assertEqual(self.l.load(), [])

    def test_uses_the_local_time_zone(self):
        la = watch.zoneinfo.ZoneInfo("America/Los_Angeles")      # 12:00 UTC is 04:00 there
        self.assertEqual(self.tick(TUE, tz=la), [])
        self.assertEqual([t.key for t in self.tick(self.at(3, 17), tz=la)], ["daily:600:2026-11-03"])
        # Saturday 03:00 UTC is still Friday evening there: a working day.
        self.assertEqual(watch.daily_trigger(self.at(7, 3), dt.time(8, 30), 600, la).key,
                         "daily:600:2026-11-06")

    def test_a_live_planner_on_the_report_issue_holds_it_and_a_missed_day_is_logged(self):
        t_issue, t_comments = tracking(201, "planner-sid", "planner", 600)
        self.scene.tracking.append(t_issue)
        self.scene.comments[201] = t_comments
        self.assertEqual(self.tick(TUE), [])
        (held,) = [x for x in watch.waiting(self.l)[1] if x["kind"] == "daily"]
        self.assertEqual(held["reason"], "held: planner session planner-sid is live on #600 (active)")
        self.tick(self.at(4, 8))                                  # next day, before daily_at
        missed = [x for x in self.lines if "no daily report run that day" in x]
        self.assertEqual(missed, ["[daily] #600 2026-11-03: no daily report run that day (held: planner "
                                  "session planner-sid is live on #600 (active)); not caught up (GOV-0029)"])
        self.assertEqual(watch.waiting(self.l)[1], [x for x in watch.waiting(self.l)[1]
                                                     if x["kind"] != "daily"])
        self.tick(self.at(4, 8, 10))
        self.assertEqual(len([x for x in self.lines if "no daily report run" in x]), 1)   # once
        self.assertEqual(self.dailies(), [])                      # not caught up

    def test_another_roles_session_on_the_report_issue_doesnt_hold_it(self):
        t_issue, t_comments = tracking(201, "docs-sid", "docs", 600)
        self.scene.tracking.append(t_issue)
        self.scene.comments[201] = t_comments
        self.assertEqual([t.key for t in self.tick(TUE)], ["daily:600:2026-11-03"])

    def test_a_closed_report_issue_is_refused(self):
        self.scene.issues[-1]["state"] = "closed"
        self.tick(TUE)
        self.assertIn("[daily] #600 Tue 2026-11-03, due at 08:30 -> refused: #600 is closed", self.lines)
        self.assertEqual(self.dailies(), [])

    def test_runs_stay_inside_gov_0010(self):
        self.path = write_manifest(self.home, {r: 10 for r in ROLES if r != "planner"}, 10,
                                   extra=DAILY_ON)
        self.tick(TUE)
        (held,) = [x for x in watch.waiting(self.l)[1] if x["kind"] == "daily"]
        self.assertIn("planner has no spend_cap_usd", held["reason"])

    def test_dry_run_prints_it_with_the_headless_command(self):
        self.assertEqual([t.key for t in self.tick(TUE, dry_run=True)], ["daily:600:2026-11-03"])
        i = self.lines.index("[daily] #600 Tue 2026-11-03, due at 08:30 -> would start planner on #600, "
                             "the daily report")
        self.assertIn("write the daily report on issue #600", self.lines[i + 1])
        self.assertEqual(self.l.load(), [])

    def test_next_daily(self):
        at = dt.time(8, 30)
        self.assertEqual(watch.next_daily(TUE, at, 600, {}, UTC), "due now")
        done = {"daily:600:2026-11-03": "started planner-issue-600"}
        self.assertEqual(watch.next_daily(TUE, at, 600, done, UTC), "next due Wed 2026-11-04 at 08:30")
        self.assertEqual(watch.next_daily(self.at(3, 7), at, 600, {}, UTC),
                         "next due Tue 2026-11-03 at 08:30")
        self.assertEqual(watch.next_daily(self.at(6, 9), at, 600, {"daily:600:2026-11-06": "x"}, UTC),
                         "next due Mon 2026-11-09 at 08:30")
        self.assertEqual(watch.next_daily(self.at(7, 7), at, 600, {}, UTC),
                         "next due Mon 2026-11-09 at 08:30")

    def test_inbox_says_when_it_is_next_due(self):
        limits = swarm.manifest.load_watch(self.path)
        line = watch.daily_text(limits, {}, TUE, UTC)
        self.assertEqual(line, "swarm watch's [daily]: the planner writes the daily report on #600 each "
                               "working day at 08:30 local time (GOV-0029); due now")
        self.assertIn(line, swarm.inbox_text([], NOW, G, daily=line))
        self.manifest()
        self.assertIsNone(watch.daily_text(swarm.manifest.load_watch(self.path), {}, TUE, UTC))


ASKS_ON = "asks = true\nreport_issue = 600\n"
ON_SINCE = (NOW - dt.timedelta(hours=1)).isoformat()      # asks turned on an hour before NOW


class AskTest(unittest.TestCase):
    """GOV-0029's [ask] trigger (#590): an owner's `Ask: <role>: <question>` comment on
    report issue #600 starts that role there once. In the Scene, a builder is live on #60."""

    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        (self.home / "launcher").mkdir()
        self.fake = Fake(self.home / "launcher")
        self.lines = []
        self.l = swarm.Launcher(self.home, run=self.fake.run, proc=self.fake.proc, kill=self.fake.kill,
                                clock=self.fake.clock, sleep=lambda s: None, out=self.lines.append,
                                root=self.home / "repo", git=FakeGit(), claude_dir=self.home / "claude")
        self.scene = Scene()
        self.scene.issues.append(issue(600, title="Daily report"))   # no label: it needs none
        self.manifest(ASKS_ON)
        watch.save_state(self.l, {**watch.load_state(self.l), "asks_since": {"600": ON_SINCE}})
        self.fetched = []

    def manifest(self, extra=""):
        self.path = write_manifest(self.home, ALL_CAPPED, 10, extra=extra)

    def get_comments(self, repo, n):
        self.fetched.append(n)
        return list(self.scene.comments.get(n, []))

    def watcher(self, dry_run=False):
        return watch.Watch(self.l, REPO, OWNER, ROLES, dry_run=dry_run, manifest_path=self.path,
                           read=self.scene.read, get_issue=self.scene.get_issue,
                           get_heartbeat=self.scene.heartbeat, get_comments=self.get_comments)

    def tick(self, dry_run=False, now=NOW):
        return [t for t in self.watcher(dry_run).tick(now) if t.kind == "ask"]

    def asked(self):
        return [(e.name, e.role, e.issue, e.ask, e.ask_comment) for e in self.l.load() if e.ask]

    def say(self, *comments, n=600):
        self.scene.comments[n] = list(comments)

    def ask_lines(self):
        return [x for x in self.lines if x.startswith("[ask]")]

    def test_an_owner_ask_starts_the_role_once(self):
        self.say(call(901, "Quick one.\nAsk: Docs: is the README right about issue #588?\nThanks",
                      who=OWNER))
        self.assertEqual([t.key for t in self.tick()], ["ask:600:901"])
        self.assertEqual(self.asked(), [("docs-issue-600", "docs", 600,
                                         "is the README right about issue #588?", 901)])
        cmd = [c for c in self.fake.commands if "roles/docs.md" in c][-1]
        argv = headless_argv(cmd)
        prompt = argv[argv.index("-p") + 1]
        self.assertIn("answer the owner's question on issue #600 (comment 901): \"is the README right "
                      "about #588?\"", prompt)
        self.assertIn("Answer in plain words in one comment on #600, and stop", prompt)          # GOV-0012's budget and turns, GOV-0013's denies
        self.assertEqual(argv[argv.index("--max-budget-usd") + 1], "10")
        self.assertEqual(argv[argv.index("--max-turns") + 1], "50")
        self.assertIn("Bash(gh pr merge *)", argv)
        self.assertIn("[ask] #600 ask by mattmcalister (comment 901): docs -> starting docs-issue-600",
                      self.lines)
        n = len(self.fake.commands)
        self.assertEqual(self.tick(), [])                 # keyed on the comment: once
        StartTest.exit(self, "docs-issue-600")
        self.assertEqual(self.tick(), [])                 # and not again once it stops
        self.assertEqual(len(self.fake.commands), n)

    def test_asking_the_planner_is_allowed(self):
        self.say(call(901, "ask: planner: what slipped this week?", who=OWNER))
        self.assertEqual([t.key for t in self.tick()], ["ask:600:901"])
        self.assertEqual([a[1] for a in self.asked()], ["planner"])

    def test_a_non_owner_comment_is_skipped(self):
        self.say(call(901, "Ask: docs: drive-by", who="stranger"),
                 call(902, "Ask: docs: as the planner", who=PLANNER_APP))
        done = self.tick()
        self.assertEqual([(t.key, t.skipped) for t in done], [
            ("ask:600:901", "stranger isn't the owner, and only the owner's asks count (GOV-0029)"),
            ("ask:600:902", f"{PLANNER_APP} isn't the owner, and only the owner's asks count (GOV-0029)")])
        self.assertIn("[ask] #600 ask by stranger (comment 901): docs -> skipped: stranger isn't the "
                      "owner, and only the owner's asks count (GOV-0029)", self.lines)
        self.assertEqual(self.asked(), [])
        self.assertEqual(self.tick(), [])                 # logged once

    def test_unknown_role_no_question_and_two_roles_are_skipped(self):
        self.say(call(901, "Ask: designer: x", who=OWNER),
                 call(902, "Ask: docs:", who=OWNER),
                 call(903, "Ask: docs", who=OWNER),
                 call(904, "Ask: docs, planner: both?", who=OWNER),
                 call(905, "Ask: : no role", who=OWNER))
        self.assertEqual([(t.key, t.skipped) for t in self.tick()], [
            ("ask:600:901", "'designer' isn't a role with a prompt in roles/"),
            ("ask:600:902", "the line asks no question"),
            ("ask:600:903", "the line asks no question"),
            ("ask:600:904", "the line names 2 roles; an ask names one"),
            ("ask:600:905", "the line names no role")])
        self.assertEqual(self.asked(), [])

    def test_a_comment_on_another_issue_starts_nothing(self):
        self.say(call(901, "Ask: docs: wrong place?", who=OWNER), n=60)
        self.assertEqual(self.tick(), [])
        self.assertEqual(self.ask_lines(), [])

    def test_the_switch_off_starts_nothing_and_reads_nothing(self):
        self.manifest()                                   # no asks: off by default
        self.say(call(901, "Ask: docs: x", who=OWNER))
        self.assertEqual(self.tick(), [])
        self.assertEqual(self.tick(dry_run=True), [])
        self.assertEqual(self.ask_lines(), [])
        self.assertEqual(self.asked(), [])
        self.assertEqual(watch.load_state(self.l)["asks_since"], {})     # dropped while off
        self.manifest("asks = false\nreport_issue = 600\n")
        self.assertEqual(self.tick(), [])
        self.assertNotIn(600, self.fetched)

    def test_only_asks_since_it_was_turned_on_count(self):
        self.manifest()
        self.tick()                                       # off: asks_since dropped
        self.say(call(901, "Ask: docs: asked while off", who=OWNER, at=ts(30)))
        self.manifest(ASKS_ON)
        on = NOW - dt.timedelta(minutes=10)
        (t,) = self.tick(now=on)                          # turned on: it was posted before
        self.assertEqual(t.skipped, "posted before asks was turned on in swarm.toml's [watch]")
        self.assertEqual(watch.load_state(self.l)["asks_since"], {"600": on.isoformat()})
        self.say(call(901, "Ask: docs: asked while off", who=OWNER, at=ts(30)),
                 call(902, "Ask: docs: asked once on", who=OWNER, at=ts(5)))
        self.assertEqual([t.key for t in self.tick()], ["ask:600:902"])   # a later check keeps `on`
        self.assertEqual([a[3] for a in self.asked()], ["asked once on"])

    def test_a_live_session_of_the_asked_role_holds_it_and_others_dont(self):
        self.scene.prs.append(pr(72, SHA2, closes=(60,)))  # no [build] on #60 to take the slot
        t_issue, t_comments = tracking(201, "docs-sid", "docs", 600)
        self.scene.tracking.append(t_issue)
        self.scene.comments[201] = t_comments
        self.say(call(901, "Ask: docs: one", who=OWNER), call(902, "Ask: planner: two", who=OWNER))
        self.assertEqual([t.key for t in self.tick()], ["ask:600:902"])
        (held,) = [x for x in watch.waiting(self.l)[1] if x["kind"] == "ask"]
        self.assertEqual(held["reason"], "held: docs session docs-sid is live on #600 (active)")
        self.scene.tracking.pop()                        # docs stops
        del self.scene.comments[201]
        self.assertEqual([t.key for t in self.tick()], ["ask:600:901"])

    def test_a_closed_report_issue_is_refused(self):
        self.scene.issues[-1]["state"] = "closed"
        self.say(call(901, "Ask: docs: x", who=OWNER))
        self.tick()
        self.assertIn("[ask] #600 ask by mattmcalister (comment 901): docs -> refused: #600 is closed",
                      self.lines)
        self.assertEqual(self.asked(), [])

    def test_runs_stay_inside_gov_0010(self):
        self.path = write_manifest(self.home, {r: 10 for r in ROLES if r != "docs"}, 10, extra=ASKS_ON)
        self.say(call(901, "Ask: docs: x", who=OWNER))
        self.tick()
        (held,) = [x for x in watch.waiting(self.l)[1] if x["kind"] == "ask"]
        self.assertIn("docs has no spend_cap_usd", held["reason"])

    def test_reads_the_report_issues_comments(self):
        self.say(call(901, "Ask: docs: x", who=OWNER))
        w = watch.World(model=self.scene.read(REPO, 15, NOW).model, issues=[])
        n, since = self.watcher().asks(w, swarm.manifest.load_watch(self.path),
                                       {"600": ON_SINCE}, NOW)
        self.assertEqual((n, since.isoformat(), self.fetched), (600, ON_SINCE, [600]))
        self.assertEqual([c["id"] for c in w.comments[600]], [901])

    def test_dry_run_prints_it_with_the_headless_command(self):
        self.say(call(901, "Ask: docs: x?", who=OWNER))
        self.assertEqual([t.key for t in self.tick(dry_run=True)], ["ask:600:901"])
        i = self.lines.index("[ask] #600 ask by mattmcalister (comment 901): docs -> would start "
                             "docs on #600, to answer the ask")
        argv = headless_argv(self.lines[i + 1].strip())
        self.assertIn("answer the owner's question on issue #600 (comment 901)", argv[argv.index("-p") + 1])
        self.assertEqual(self.l.load(), [])

    def test_ask_line(self):
        self.assertEqual(watch.ask_line("hi\n  ASK: `Docs` :  why  this?: really \nbye"),
                         (["docs"], "why this?: really"))
        self.assertEqual(watch.ask_line("Ask: docs"), (["docs"], ""))
        self.assertEqual(watch.ask_line("Ask: docs, planner: x"), (["docs", "planner"], "x"))
        self.assertIsNone(watch.ask_line("Task: docs: x"))
        self.assertIsNone(watch.ask_line("Asks: docs: x"))
        self.assertIsNone(watch.ask_line("We could `Ask: docs: x` here"))
        self.assertEqual(len(watch.ask_line("Ask: docs: " + "x" * 999)[1]), watch.WHY_MAX)


RESEARCH_ON = "research = true\n"
ANALYST = '[[session]]\nrole = "analyst"\ncount = 1\nmodel = "m-analyst"\nspend_cap_usd = 10\n'


def said(n, cid, body, who=OWNER, at=None):
    """A comment on #n as the repo-wide comments list returns it (with its issue_url)."""
    return {**call(cid, body, who=who, at=at), "issue_url": f"https://api.github.com/repos/{REPO}/issues/{n}"}


class ResearchTest(unittest.TestCase):
    """GOV-0029's [research] trigger (#591): a `Research: <question>` line from the owner or
    the planner App on an open issue starts the analyst there once. #300 is an open,
    unlabelled issue; #600 is the report issue."""

    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        (self.home / "launcher").mkdir()
        self.fake = Fake(self.home / "launcher")
        self.lines = []
        self.l = swarm.Launcher(self.home, run=self.fake.run, proc=self.fake.proc, kill=self.fake.kill,
                                clock=self.fake.clock, sleep=lambda s: None, out=self.lines.append,
                                root=self.home / "repo", git=FakeGit(), claude_dir=self.home / "claude")
        self.scene = Scene()
        self.scene.issues += [issue(300, title="Which agent fleets ship a daily report?"),
                              issue(600, title="Daily report")]
        self.manifest(RESEARCH_ON + "report_issue = 600\n")
        watch.save_state(self.l, {**watch.load_state(self.l), "research_since": ON_SINCE})
        self.recent, self.fetched = [], []

    def manifest(self, extra="", analyst=True):
        self.path = write_manifest(self.home, ALL_CAPPED, 10, extra=extra)
        if analyst:
            self.path.write_text(self.path.read_text() + ANALYST)

    def get_recent(self, repo, since):
        self.fetched.append(since)
        return list(self.recent)

    def watcher(self, dry_run=False):
        return watch.Watch(self.l, REPO, OWNER, ROLES | {"analyst"}, dry_run=dry_run,
                           manifest_path=self.path, read=self.scene.read,
                           get_issue=self.scene.get_issue, get_heartbeat=self.scene.heartbeat,
                           get_recent=self.get_recent)

    def tick(self, dry_run=False, now=NOW):
        return [t for t in self.watcher(dry_run).tick(now) if t.kind == "research"]

    def started(self):
        return [(e.name, e.role, e.issue, e.research, e.research_comment)
                for e in self.l.load() if e.research]

    def research_lines(self):
        return [x for x in self.lines if x.startswith("[research]")]

    def test_an_owner_line_starts_the_analyst_once(self):
        self.recent = [said(300, 901, "Context first.\nResearch: which tools ship a daily report, "
                                      "as in issue #12?\nThanks")]
        self.assertEqual([t.key for t in self.tick()], ["research:300:901"])
        q = "which tools ship a daily report, as in issue #12?"
        self.assertEqual(self.started(), [("analyst-issue-300", "analyst", 300, q, 901)])
        cmd = [c for c in self.fake.commands if "roles/analyst.md" in c][-1]
        argv = headless_argv(cmd)
        prompt = argv[argv.index("-p") + 1]
        self.assertIn("research the question posted on issue #300 (comment 901): \"which tools ship "
                      "a daily report, as in #12?\"", prompt)
        self.assertIn("Write the brief in research/<slug>.md as roles/analyst.md says, open a PR "
                      "that closes #300", prompt)
        # GOV-0012's budget and turns, GOV-0013's denies
        self.assertEqual(argv[argv.index("--max-budget-usd") + 1], "10")
        self.assertEqual(argv[argv.index("--max-turns") + 1], "50")
        self.assertIn("Bash(gh pr merge *)", argv)
        self.assertIn("[research] #300 Research: by mattmcalister (comment 901) -> starting "
                      "analyst-issue-300", self.lines)
        n = len(self.fake.commands)
        self.assertEqual(self.tick(), [])                 # keyed on the comment: once
        StartTest.exit(self, "analyst-issue-300")
        self.assertEqual(self.tick(), [])                 # and not again once it stops
        self.assertEqual(len(self.fake.commands), n)

    def test_a_planner_line_starts_the_analyst_once(self):
        self.recent = [said(300, 902, "research: what do agent dashboards charge?", who=PLANNER_APP)]
        self.assertEqual([t.key for t in self.tick()], ["research:300:902"])
        self.assertEqual([x[3] for x in self.started()], ["what do agent dashboards charge?"])
        self.assertEqual(self.tick(), [])

    def test_another_app_or_user_starts_nothing(self):
        self.recent = [said(300, 901, "Research: drive-by", who="stranger"),
                       said(300, 902, "Research: as the builder", who=BUILDER_APP)]
        self.assertEqual([(t.key, t.skipped) for t in self.tick()], [
            ("research:300:901", "stranger is neither the owner nor the planner, and only their "
                                 "Research: lines count (GOV-0029)"),
            ("research:300:902", f"{BUILDER_APP} is neither the owner nor the planner, and only "
                                 f"their Research: lines count (GOV-0029)")])
        self.assertEqual(self.started(), [])
        self.assertEqual(self.tick(), [])                 # logged once

    def test_lines_that_dont_count_are_skipped(self):
        self.scene.issues.append(issue(310, ["gov:question"]))
        self.recent = [said(300, 901, "Research:"),
                       said(600, 902, "Research: on the report issue"),
                       said(310, 903, "Research: on a question"),
                       said(70, 904, "Research: on a PR"),
                       said(999, 905, "Research: on a closed issue")]
        self.assertEqual([(t.key, t.skipped) for t in self.tick()], [
            ("research:300:901", "the line asks no question"),
            ("research:600:902", "#600 is the report issue, which stays open, so no research PR "
                                 "can close it; post the line on an issue of its own (#591)"),
            ("research:310:903", "#310 is a gov:question, which a research PR mustn't close; post "
                                 "the line on an issue of its own (#591)"),
            ("research:70:904", "#70 isn't an open issue"),
            ("research:999:905", "#999 isn't an open issue")])
        self.assertEqual(self.started(), [])

    def test_the_switch_off_starts_nothing_and_reads_nothing(self):
        self.manifest("report_issue = 600\n")             # no research: off by default
        self.recent = [said(300, 901, "Research: x")]
        self.assertEqual(self.tick(), [])
        self.assertEqual(self.tick(dry_run=True), [])
        self.assertEqual((self.research_lines(), self.started(), self.fetched), ([], [], []))
        self.assertIsNone(watch.load_state(self.l)["research_since"])   # dropped while off
        self.manifest("research = false\n")
        self.assertEqual(self.tick(), [])
        self.assertEqual(self.fetched, [])

    def test_only_lines_since_it_was_turned_on_count(self):
        self.manifest()
        self.tick()                                       # off: research_since dropped
        self.recent = [said(300, 901, "Research: asked while off", at=ts(30))]
        self.manifest(RESEARCH_ON)
        on = NOW - dt.timedelta(minutes=10)
        (t,) = self.tick(now=on)                          # turned on: it was posted before
        self.assertEqual(t.skipped, "posted before research was turned on in swarm.toml's [watch]")
        self.assertEqual(watch.load_state(self.l)["research_since"], on.isoformat())
        self.recent.append(said(300, 902, "Research: asked once on", at=ts(5)))
        self.assertEqual([t.key for t in self.tick()], ["research:300:902"])   # later check keeps `on`
        self.assertEqual([x[3] for x in self.started()], ["asked once on"])

    def test_reads_at_most_research_days_back(self):
        old = (NOW - dt.timedelta(days=30)).isoformat()
        watch.save_state(self.l, {**watch.load_state(self.l), "research_since": old})
        self.tick()
        self.assertEqual(self.fetched, [NOW - dt.timedelta(days=watch.RESEARCH_DAYS)])
        self.assertEqual(watch.load_state(self.l)["research_since"], old)    # kept as it was

    def test_a_live_analyst_on_the_issue_holds_it_and_others_dont(self):
        self.scene.issues.append(issue(301))
        t_issue, t_comments = tracking(201, "analyst-sid", "analyst", 300)
        self.scene.tracking.append(t_issue)
        self.scene.comments[201] = t_comments
        self.recent = [said(300, 901, "Research: one"), said(301, 902, "Research: two")]
        self.assertEqual([t.key for t in self.tick()], ["research:301:902"])
        (held,) = [x for x in watch.waiting(self.l)[1] if x["kind"] == "research"]
        self.assertEqual(held["reason"], "held: analyst session analyst-sid is live on #300 (active)")
        self.scene.tracking.pop()                        # the analyst stops
        del self.scene.comments[201]
        self.assertEqual([t.key for t in self.tick()], ["research:300:901"])

    def test_a_live_builder_on_the_issue_doesnt_hold_it(self):
        self.recent = [said(60, 901, "Research: on the busy issue")]   # a builder is live on #60
        self.assertEqual([t.key for t in self.tick()], ["research:60:901"])

    def test_runs_stay_inside_gov_0010(self):
        self.manifest(RESEARCH_ON, analyst=False)
        self.path.write_text(self.path.read_text() + ANALYST.replace("spend_cap_usd = 10\n", ""))
        self.recent = [said(300, 901, "Research: x")]
        self.tick()
        (held,) = [x for x in watch.waiting(self.l)[1] if x["kind"] == "research"]
        self.assertIn("analyst has no spend_cap_usd", held["reason"])

    def test_dry_run_prints_it_with_the_headless_command(self):
        self.recent = [said(300, 901, "Research: x?")]
        self.assertEqual([t.key for t in self.tick(dry_run=True)], ["research:300:901"])
        i = self.lines.index("[research] #300 Research: by mattmcalister (comment 901) -> would "
                             "start analyst on #300, to write the brief")
        argv = headless_argv(self.lines[i + 1].strip())
        self.assertIn("research the question posted on issue #300 (comment 901)", argv[argv.index("-p") + 1])
        self.assertEqual(self.l.load(), [])

    def test_research_line(self):
        self.assertEqual(watch.research_line("hi\n  RESEARCH:   why  this?: really \nbye"),
                         "why this?: really")
        self.assertEqual(watch.research_line("Research:"), "")
        self.assertIsNone(watch.research_line("Researcher: x"))
        self.assertIsNone(watch.research_line("We could `Research: x` here"))
        self.assertEqual(len(watch.research_line("Research: " + "x" * 999)), watch.WHY_MAX)


class RetryTest(unittest.TestCase):
    """#550: a run that never started is tried again, at most MAX_RETRIES times, then
    `swarm inbox` lists it as failed with its session ids."""

    setUp_start = StartTest.setUp
    manifest, watcher, exit = StartTest.manifest, StartTest.watcher, StartTest.exit
    end, entry, state, transcript, inbox = (RunRecordTest.end, RunRecordTest.entry, RunRecordTest.state,
                                            RunRecordTest.transcript, RunRecordTest.inbox)

    def setUp(self):
        self.setUp_start()
        sc = self.scene
        sc.issues, sc.events = [sc.issues[0]], {49: sc.events[49]}          # just the build on #49
        sc.prs, sc.reviewed, sc.tracking, sc.comments = [], {}, [], {}

    def test_no_result_file_is_retried_twice_once_per_check_then_listed_as_failed(self):
        w, t = self.watcher(), NOW
        w.tick(t)
        sids = []
        for attempt in range(1, watch.MAX_RETRIES + 2):
            sids.append(self.end("builder-issue-49").session_id)            # no result file
            t += dt.timedelta(minutes=5)
            done = w.tick(t)
            run = self.state()["runs"]["build:49:11"]
            if attempt <= watch.MAX_RETRIES:
                self.assertEqual([x.ref for x in done], ["#49"])             # started again this check
                self.assertEqual(len(self.fake.commands), attempt + 1)
                self.assertEqual(run["tries"], attempt + 1)
                self.assertEqual(run["never_started"], sids)
                self.assertIn(f"-> recorded; it never started, so trying again (retry {attempt} of "
                              f"{watch.MAX_RETRIES})", self.lines[-3])
            else:
                self.assertEqual(done, [])
                self.assertTrue(run["gave_up"])
                self.assertIn("build:49:11", self.state()["acted"])
        self.assertEqual(len(self.fake.commands), watch.MAX_RETRIES + 1)
        self.assertEqual(w.tick(t + dt.timedelta(minutes=5)), [])            # and never again
        self.assertEqual(len(self.fake.commands), watch.MAX_RETRIES + 1)
        text = self.inbox(t)
        failed = text.split("swarm watch runs that failed: they never started, after 2 retries "
                            "(#550; re-add the label to try again):\n")[1].splitlines()[0]
        self.assertTrue(failed.startswith("- [build] #49 builder-issue-49 · no result (no result file)"))
        self.assertTrue(failed.endswith(f" · sessions {', '.join(sids)}"))
        self.assertNotIn("Nothing is waiting on you.", text)

    def test_no_json_and_no_transcript_is_retried_but_with_a_transcript_it_is_not(self):
        w = self.watcher()
        w.tick(NOW)
        self.end("builder-issue-49", BANNER)                                # no JSON, no transcript
        self.assertEqual([x.ref for x in w.tick(NOW + dt.timedelta(minutes=5))], ["#49"])
        e = self.end("builder-issue-49", BANNER)
        self.transcript(e.session_id)                                       # claude ran, then died
        self.assertEqual(w.tick(NOW + dt.timedelta(minutes=10)), [])
        self.assertEqual(len(self.fake.commands), 2)

    def test_a_run_that_ran_is_not_retried(self):
        w = self.watcher()
        w.tick(NOW)
        self.end("builder-issue-49", BANNER + CANNED["error"])
        self.assertEqual(w.tick(NOW + dt.timedelta(minutes=5)), [])
        self.assertEqual(len(self.fake.commands), 1)


class ReholdTest(unittest.TestCase):
    """#550: a [build] whose builder says it waits on an open issue goes back to held, and
    starts again once that issue closes, with no new label."""

    setUp_start = StartTest.setUp
    manifest, watcher, exit, started, inbox = (StartTest.manifest, StartTest.watcher, StartTest.exit,
                                               StartTest.started, StartTest.inbox)
    end, entry, state = RunRecordTest.end, RunRecordTest.entry, RunRecordTest.state

    def setUp(self):
        self.setUp_start()
        sc = self.scene
        sc.issues = [issue(457, ["ready"], body="**Waits on:** nothing.\n"), issue(456, title="blocker")]
        sc.events = {457: [ev("ready", eid=11)]}
        sc.prs, sc.reviewed, sc.tracking, sc.comments = [], {}, [], {}

    def say(self, body, who=watch.BUILDER_APP, minutes=1):
        self.scene.comments.setdefault(457, []).append(
            {"user": {"login": who}, "body": body,
             "created_at": (NOW + dt.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")})

    def test_said_waits_reads_the_builders_last_comment_since_the_run_started(self):
        c = lambda body, who=watch.BUILDER_APP, at="2026-11-06T12:40:00Z": {
            "user": {"login": who}, "body": body, "created_at": at}
        since, me = "2026-11-06T12:33:00+00:00", {watch.BUILDER_APP}
        self.assertEqual(watch.said_waits([c("This waits on #456, which is still open. See #12.")],
                                          since, me), [456])
        self.assertEqual(watch.said_waits([c("Waiting for #456 and #458: PR #546 closes #456.")],
                                          since, me), [456, 458])
        self.assertEqual(watch.said_waits([c("Opened PR #600.")], since, me), [])
        self.assertEqual(watch.said_waits([c("waits on #456"), c("Done: PR #600.")], since, me), [])
        self.assertEqual(watch.said_waits([c("waits on #456", who=OWNER)], since, me), [])
        self.assertEqual(watch.said_waits([c("waits on #456", at="2026-11-06T12:00:00Z")], since, me), [])

    def test_a_build_that_waits_is_held_then_starts_when_the_issue_closes(self):
        w = self.watcher()
        self.assertEqual([t.ref for t in w.tick(NOW)], ["#457"])
        self.say("#457 waits on #456, which is still open (PR #546 closes it). Stopping.\n"
                 "-- builder (claude-opus-5-5)")
        self.end("builder-issue-457", BANNER + CANNED["success"])
        later = NOW + dt.timedelta(minutes=5)
        self.assertEqual(w.tick(later), [])
        self.assertEqual(len(self.fake.commands), 1)
        st = self.state()
        self.assertEqual(st["runs"]["build:457:11"]["waits_on"], [456])
        self.assertNotIn("build:457:11", st["acted"])
        self.assertIn("-> recorded; the builder says it waits on #456: held until it closes", self.lines[-2])
        self.assertEqual(self.lines[-1], "[build] #457 ready by the owner -> held: waits on #456 "
                                         "(the builder said so on #457)")
        self.assertIn("- [build] #457 ready by the owner · held: waits on #456 (the builder said so on #457)",
                      self.inbox())
        self.assertEqual(w.tick(later + dt.timedelta(minutes=5)), [])     # still held, said once
        self.assertEqual(sum("held: waits on #456" in x for x in self.lines), 1)
        self.scene.issues = [i for i in self.scene.issues if i["number"] != 456]
        self.assertEqual([t.ref for t in w.tick(later + dt.timedelta(minutes=10))], ["#457"])
        self.assertEqual(len(self.fake.commands), 2)

    def test_a_build_that_opened_a_pr_or_said_nothing_stays_done(self):
        for case in ("pr", "nothing", "closed"):
            self.setUp()
            w = self.watcher()
            w.tick(NOW)
            if case == "nothing":
                self.say("Opened PR #600.")
            else:
                self.say("This waits on #456.")
            if case == "pr":
                self.scene.prs, self.scene.reviewed = [pr(600, closes=[457])], {600: {SHA1}}
            if case == "closed":
                self.scene.issues = self.scene.issues[:1]                   # #456 closed meanwhile
            self.end("builder-issue-457", BANNER + CANNED["success"])
            self.watcher().tick(NOW + dt.timedelta(minutes=5))
            self.assertIn("build:457:11", self.state()["acted"], case)
            self.assertNotIn("waits_on", self.state()["runs"]["build:457:11"], case)
            self.assertEqual(len(self.fake.commands), 1, case)


PLANNER_APP = "productswarm-planner[bot]"
MILESTONE_PLAN = """# Plan: x

## M1: Daily report runs without the owner

- **Done test:** 5 working days in a row.

## M2: Merges under delegation

- **Status:** done
"""


def milestone_issue(n, m="M1", author=PLANNER_APP, labels=(), waits="nothing."):
    it = issue(n, labels, body=f"Do it.\n\n**Milestone:** {m}\n\n**Files:** `x.py`\n**Waits on:** {waits}\n")
    it["user"] = {"login": author}
    return it


class MilestoneBuildTest(unittest.TestCase):
    """#583 (GOV-0026): `swarm watch` starts [build] on an issue that is go by its PLAN.md
    milestone, as it does on a `ready` one."""

    setUp_start = StartTest.setUp
    manifest, started, exit, inbox = StartTest.manifest, StartTest.started, StartTest.exit, StartTest.inbox

    def setUp(self):
        self.setUp_start()
        sc = self.scene
        sc.issues, sc.events = [milestone_issue(49)], {49: []}
        sc.prs, sc.reviewed, sc.tracking, sc.comments = [], {}, [], {}
        sc.plan = MILESTONE_PLAN

    def watcher(self, dry_run=False):
        return watch.Watch(self.l, REPO, OWNER, ROLES, dry_run=dry_run, manifest_path=self.path,
                           read=self.scene.read, get_issue=self.scene.get_issue,
                           get_heartbeat=self.scene.heartbeat, get_reader=self.scene.get_reader)

    def builds(self, w=None, at=NOW):
        return [(t.key, t.why) for t in (w or self.watcher()).tick(at) if t.kind == "build"]

    def test_a_milestone_issue_builds_once(self):
        self.assertEqual(self.builds(), [("build:49:M1", "go by milestone M1 (GOV-0026)")])
        self.assertEqual(self.started(), [("builder-issue-49", "builder", "m-builder", 49, "watch")])
        self.assertIn("work on issue #49.", self.fake.commands[0])
        self.assertIn("[build] #49 go by milestone M1 (GOV-0026) -> starting builder-issue-49", self.lines)
        self.exit("builder-issue-49")
        self.assertEqual(self.builds(), [])                       # acted on: never twice

    def test_dry_run_prints_it(self):
        self.assertEqual(self.builds(self.watcher(dry_run=True)), [("build:49:M1", "go by milestone M1 (GOV-0026)")])
        self.assertEqual(trigger_lines(self.lines), [
            "[build] #49 go by milestone M1 (GOV-0026) -> would start `launcher/swarm launch builder --issue 49`"])

    def test_the_owners_ready_builds_as_before_and_wins(self):
        self.scene.issues = [issue(49, ["ready"]), milestone_issue(50, "M2", labels=("ready",))]
        self.scene.events = {49: [ev("ready", eid=11)], 50: [ev("ready", eid=12)]}
        self.assertEqual(self.builds(), [("build:49:11", "ready by the owner"),
                                         ("build:50:12", "ready by the owner")])   # M2 is done: ready wins

    def test_a_ready_someone_else_added_falls_back_to_the_milestone(self):
        self.scene.issues = [milestone_issue(49, labels=("ready",))]
        self.scene.events = {49: [ev("ready", PLANNER_APP, eid=11)]}
        self.assertEqual(self.builds(), [("build:49:M1", "go by milestone M1 (GOV-0026)")])

    def test_each_of_these_stops_it(self):
        def owner_comment():
            self.scene.comments[49] = [{"user": {"login": OWNER}, "body": "not yet"}]

        def no_plan():
            self.scene.plan = None
        cases = {
            "hold": lambda: self.scene.issues[0]["labels"].append({"name": "hold"}),
            "owner comment": owner_comment,
            "done milestone": lambda: self.scene.issues.__setitem__(0, milestone_issue(49, "M2")),
            "milestone not in PLAN.md": lambda: self.scene.issues.__setitem__(0, milestone_issue(49, "M9")),
            "no PLAN.md on main": no_plan,
            "non-swarm author": lambda: self.scene.issues.__setitem__(0, milestone_issue(49, author="stranger")),
            "gov:question": lambda: self.scene.issues[0]["labels"].append({"name": "gov:question"}),
            "no milestone line": lambda: self.scene.issues[0].update(body="**Milestone:** no milestone yet\n"),
            "open PR closing it": lambda: setattr(self.scene, "prs", [pr(70, closes=[49])]),
        }
        for why, change in cases.items():
            self.setUp()
            self.scene.reviewed = {70: {SHA1}}
            change()
            self.assertEqual(self.builds(), [], why)
            self.assertEqual(self.started(), [], why)

    def test_an_owner_issue_with_a_milestone_builds(self):
        self.scene.issues = [milestone_issue(49, author=OWNER)]
        self.assertEqual(self.builds(), [("build:49:M1", "go by milestone M1 (GOV-0026)")])

    def test_an_open_waits_on_holds_it_until_it_closes(self):
        self.scene.issues = [milestone_issue(49, waits="#456."), issue(456, title="the blocker")]
        w = self.watcher()
        self.assertEqual(self.builds(w), [])
        self.assertEqual(watch.load_state(self.l)["acted"], {})
        self.assertIn("- [build] #49 go by milestone M1 (GOV-0026) · held: waits on #456", self.inbox())
        self.scene.issues = self.scene.issues[:1]
        self.assertEqual(self.builds(w), [("build:49:M1", "go by milestone M1 (GOV-0026)")])

    def test_a_veto_then_a_lift_starts_at_most_one_new_build(self):
        w = self.watcher()
        self.assertEqual([k for k, _ in self.builds(w)], ["build:49:M1"])
        self.exit("builder-issue-49")
        self.scene.issues[0]["labels"].append({"name": "hold"})
        self.scene.events[49] = [ev("hold", eid=21)]
        self.assertEqual(self.builds(w), [])                       # vetoed
        self.scene.issues[0]["labels"] = []
        self.scene.events[49].append(ev("hold", eid=22, kind="unlabeled"))
        self.assertEqual([k for k, _ in self.builds(w)], ["build:49:M1:22"])   # lifted: one new build
        self.exit("builder-issue-49")
        self.assertEqual(self.builds(w), [])                       # and only one
        self.assertEqual(len(self.fake.commands), 2)

    def test_a_new_milestone_is_a_new_trigger(self):
        self.scene.plan = MILESTONE_PLAN + "\n## M3: The desk\n"
        w = self.watcher()
        self.assertEqual([k for k, _ in self.builds(w)], ["build:49:M1"])
        self.exit("builder-issue-49")
        self.scene.issues[0] = milestone_issue(49, "M3")
        self.assertEqual([k for k, _ in self.builds(w)], ["build:49:M3"])

    def test_a_veto_on_fresh_data_refuses_the_start(self):
        real = self.scene.get_reader

        def fresh(repo, n):            # the owner comments between the read and the start
            self.scene.comments[49] = [{"user": {"login": OWNER}, "body": "hold on"}]
            return real(repo, n)
        self.scene.get_reader = fresh
        self.builds()
        self.assertEqual(self.started(), [])
        self.assertTrue(watch.load_state(self.l)["acted"]["build:49:M1"].startswith("refused: "))
        self.assertIn("[build] #49 go by milestone M1 (GOV-0026) -> refused: @mattmcalister commented "
                      "on #49: that's a veto until @mattmcalister labels it `ready`", self.lines)

    def test_respond_on_a_milestone_issue_isnt_refused_for_lacking_ready(self):
        t = watch.Trigger(key="respond:70:x", kind="respond", ref="PR #70", why="x", role="builder",
                          issue=49, pr=70)
        self.assertEqual(self.watcher().refusal(t, [], NOW), (None, False))
        self.scene.issues[0]["labels"].append({"name": "hold"})
        self.assertIn("labelled `hold`", self.watcher().refusal(t, [], NOW)[0])

    def test_gather_reads_plan_and_the_milestone_issues_events_and_comments(self):
        self.scene.comments[49] = [{"id": 501, "user": {"login": PLANNER_APP}, "body": "x"}]
        self.scene.events[49] = [ev("hold", eid=22, kind="unlabeled")]

        def run(argv, **kw):
            return subprocess.CompletedProcess(argv, 0, self.scene.gh(argv), "")
        fake_sub = types.SimpleNamespace(run=run, SubprocessError=subprocess.SubprocessError)
        with mock.patch.object(G, "subprocess", fake_sub), mock.patch.object(G.ghql, "subprocess", fake_sub):
            w = watch.gather(REPO, 15, NOW)
        self.assertEqual(w.plan, MILESTONE_PLAN)
        self.assertEqual([c["id"] for c in w.comments[49]], [501])
        self.assertEqual([e["id"] for e in w.events[49]], [22])


class CodeCheckTest(unittest.TestCase):
    """#550: swarm watch says when origin/main has new launcher code, and restarts on it
    between checks once nothing it started is still starting."""

    setUp_start = StartTest.setUp
    manifest, watcher = StartTest.manifest, StartTest.watcher

    def setUp(self):
        self.setUp_start()
        self.git_calls, self.answers = [], {}
        self.l.git = self.git
        self.set(tree="new", branch="main", status="", merge=(0, ""), count="3")
        self.w = self.watcher()
        self.w.loaded = "old"

    def set(self, tree=None, branch=None, status=None, merge=None, count=None):
        for k, v in (("origin/main:launcher", tree), ("symbolic-ref", branch), ("status", status),
                     ("merge", merge), ("rev-list", count)):
            if v is not None:
                self.answers[k] = v if isinstance(v, tuple) else (0, v)

    def git(self, args):
        self.git_calls.append(args)
        for k, v in self.answers.items():
            if k in args:
                return v
        return 0, ""

    def merged(self):
        return any("merge" in a for a in self.git_calls)

    def test_same_code_does_nothing(self):
        self.set(tree="old")
        self.assertFalse(self.w.code_check())
        self.assertEqual(self.lines, [])
        self.assertTrue(any("fetch" in a for a in self.git_calls))          # every check

    def test_new_code_is_said_once_and_waits_while_a_run_is_starting(self):
        self.l.add(swarm.Started("builder-issue-49", "builder", "m", "s1", self.fake.t, issue=49,
                                 by="watch", budget_usd=1, max_turns=5))     # no pid yet: starting
        self.assertFalse(self.w.code_check())
        self.assertFalse(self.w.code_check())
        self.assertEqual(self.lines, ["swarm watch: origin/main has 3 new commits under launcher/; restarting "
                                      "on them once nothing it started is still starting (#550)"])
        self.assertFalse(self.merged())
        self.fake.t += swarm.START_GRACE + 1                                   # it never started
        self.assertTrue(self.w.code_check())
        self.assertTrue(self.merged())

    def test_a_checkout_off_main_or_with_changes_is_left_alone(self):
        for kw, why in (({"branch": "feature"}, "is on feature, not main"),
                        ({"status": " M launcher/watch.py"}, "has changes to tracked files"),
                        ({"merge": (1, "fatal: Not possible to fast-forward")}, "can't fast-forward")):
            self.setUp()
            self.set(**kw)
            self.assertFalse(self.w.code_check())
            self.assertIn(why, self.lines[-1])
            self.assertIn("Pull and restart swarm watch by hand", self.lines[-1])
            self.assertEqual(self.merged(), "merge" in kw)

    def test_run_restarts_between_checks_after_releasing_the_lock(self):
        restarted = []

        def restart():
            fd, _ = watch.take_lock(self.l)             # the old process has let go of it
            restarted.append(fd is not None)
            os.close(fd)
        self.answers["HEAD:launcher"] = (0, "old")
        w = self.watcher()
        w.restart = restart
        self.scene.issues, self.scene.prs, self.scene.tracking = [], [], []
        self.assertEqual(w.run(5, ticks=3, sleep=lambda s: None), 0)
        self.assertEqual(restarted, [True])
        self.assertEqual(self.scene.reads, 1)                                  # after the first check
        self.assertEqual(self.lines[-1], "swarm watch: restarting on origin/main's launcher code (#550)")

    def test_dry_run_never_restarts(self):
        w = watch.Watch(self.l, REPO, OWNER, ROLES, read=self.scene.read, manifest_path=self.path,
                        loaded="old", restart=lambda: self.fail("restarted"))
        w.run(5, ticks=2, sleep=lambda s: None)
        self.assertFalse(self.merged())


class PublicStateTest(unittest.TestCase):
    """#456: watch-public.json, watch.json's no-cost form, beside it after every tick."""

    setUp = StartTest.setUp
    manifest, watcher = StartTest.manifest, StartTest.watcher
    end = RunRecordTest.end
    entry = RunRecordTest.entry
    exit = StartTest.exit

    def public(self):
        return json.loads((self.home / "launcher" / watch.PUBLIC_FILE).read_text())

    def assert_no_cost(self, data):
        text = json.dumps(data)
        for word in ("cost_usd", "detail", "why", "$"):
            self.assertNotIn(word, text)

    def test_a_tick_writes_the_five_lists_with_running_and_live_and_limit(self):
        self.manifest(ALL_CAPPED, max_live=2)
        self.watcher().tick(NOW)
        pub = self.public()
        self.assertEqual(sorted(pub), ["checked", "failed", "held", "running", "skipped"])
        self.assertEqual(pub["checked"], NOW.isoformat())
        self.assertEqual([(r["role"], r["kind"], r["ref"], r["started"]) for r in pub["running"]],
                         [("reviewer", "review", "PR #70", NOW.isoformat()),
                          ("docs", "record", "#87", NOW.isoformat())])
        held = {x["ref"]: x for x in pub["held"]}
        self.assertEqual(held["#88"], {"ref": "#88", "kind": "answer", "code": "limit",
                                       "reason": "held: 2 of 2 running", "since": NOW.isoformat()})
        self.assertEqual(held["#60"]["code"], "live")             # busy-sid is on #60 (#488)
        self.assertEqual(pub["skipped"], [])
        self.assertEqual(pub["failed"], [])
        self.assert_no_cost(pub)

    def test_a_role_without_a_cap_is_skipped_with_its_code(self):
        self.manifest({r: 10 for r in ROLES if r != "builder"})
        self.watcher().tick(NOW)
        skipped = {x["ref"]: x for x in self.public()["skipped"]}
        self.assertEqual(skipped["#49"]["code"], "no_cap")
        self.assertEqual(skipped["#49"]["reason"], "skipped: the role has no spend_cap_usd in swarm.toml")

    def test_failed_runs_carry_their_ending_but_no_cost_or_detail(self):
        self.watcher().tick(NOW)
        self.end("builder-issue-49", BANNER + CANNED["budget"])
        self.end("docs-issue-87", BANNER + CANNED["success"])
        self.end("planner-issue-88", BANNER + CANNED["error"])
        later = NOW + dt.timedelta(minutes=5)
        self.watcher().tick(later)
        pub = self.public()
        self.assertEqual(sorted((f["ref"], f["kind"], f["ending"], f["ended"]) for f in pub["failed"]),
                         [("#49", "build", "at_cap", later.isoformat()),
                          ("#88", "answer", "error", later.isoformat())])
        self.assertEqual([r["role"] for r in pub["running"]], ["reviewer"])
        self.assertTrue(any(r.get("cost_usd") is not None for r in watch.load_state(self.l)["runs"].values()))
        self.assert_no_cost(pub)

    def test_dry_run_writes_nothing(self):
        watch.Watch(self.l, REPO, OWNER, ROLES, read=self.scene.read, manifest_path=self.path).tick(NOW)
        self.assertFalse((self.home / "launcher" / watch.PUBLIC_FILE).exists())


class PublicStatePureTest(unittest.TestCase):
    """#456: watch.public_state() from a canned watch.json."""

    def waiting(self, code, args=None, reason="text from #9: <script>", kind="build", ref="#9"):
        x = {"key": f"k-{code}", "kind": kind, "ref": ref, "why": "why from an issue",
             "reason": reason, "code": code, "since": NOW.isoformat()}
        if args is not None:
            x["args"] = args
        return x

    def test_every_code_has_its_sentence_and_list(self):
        codes = [c for c in watch.REASONS if c != "limit"]
        st = {"checked": NOW.isoformat(), "runs": {},
              "waiting": [self.waiting(c) for c in codes] + [self.waiting("limit", {"live": 2, "max": 2})]}
        pub = watch.public_state(st, [], NOW)
        got = {x["code"]: x["reason"] for x in pub["held"] + pub["skipped"]}
        self.assertEqual(set(got), set(watch.REASONS))
        self.assertEqual(got["limit"], "held: 2 of 2 running")
        self.assertEqual({x["code"] for x in pub["skipped"]}, {"raised_by", "no_role", "no_cap"})
        self.assertNotIn("script", json.dumps(pub))
        self.assertNotIn("why", json.dumps(pub))

    def test_an_unknown_code_or_bad_args_is_other(self):
        st = {"waiting": [self.waiting("made-up"), self.waiting("limit", {"live": "<b>", "max": 2}),
                          self.waiting("limit", {}), {**self.waiting("live"), "code": None}], "runs": {}}
        pub = watch.public_state(st, [], NOW)
        self.assertEqual([(x["code"], x["reason"]) for x in pub["held"]], [("other", "held")] * 4)

    def test_held_code_reads_the_holds_triggers_sets(self):
        self.assertEqual(watch.held_code("held: docs-issue-87 is live on #87 (idle since 11:30 UTC)"), "live")
        self.assertEqual(watch.held_code("stale: docs-issue-87 idle 10h; swarm stop docs-issue-87 frees #87"),
                         "stale")
        self.assertEqual(watch.held_code("held: waits on #12, #13"), "waits_on")

    def test_running_needs_a_live_session_and_failed_keeps_runs_days(self):
        old = (NOW - dt.timedelta(days=watch.RUNS_DAYS + 1)).isoformat()
        recent = (NOW - dt.timedelta(hours=1)).isoformat()
        run = {"name": "n", "kind": "build", "ref": "#1", "started": recent}
        st = {"runs": {
            "a": {**run, "session_id": "live-sid"},
            "b": {**run, "session_id": "gone-sid", "ref": "#2"},
            "c": {**run, "session_id": "s3", "ref": "#3", "ending": watch.LIMITED, "ended": recent,
                  "detail": "You've hit your limit", "cost_usd": 4.5, "until": recent},
            "d": {**run, "session_id": "s4", "ref": "#4", "ending": watch.NO_RESULT, "ended": old},
            "e": {**run, "session_id": "s5", "ref": "#5", "ending": watch.DONE, "ended": recent,
                  "cost_usd": 1.0},
        }, "waiting": []}
        live = [types.SimpleNamespace(session_id="live-sid", role="builder")]
        pub = watch.public_state(st, live, NOW)
        self.assertEqual(pub["running"], [{"role": "builder", "kind": "build", "ref": "#1", "started": recent}])
        self.assertEqual(pub["failed"], [{"ref": "#3", "kind": "build", "ending": "limited", "ended": recent}])
        self.assertNotIn("cost", json.dumps(pub))


class PublishTest(unittest.TestCase):
    """#458: after a tick whose state changed, one PATCH of the [watch] issue's body."""

    setUp = StartTest.setUp
    manifest = StartTest.manifest

    def watcher(self, issues=None, fail=None):
        """A watcher whose GitHub is `issues` (the owner's open issues) and a list of edits."""
        self.issues = issues if issues is not None else [self.watch_issue()]
        self.edits, self.reads = [], 0

        def list_issues(repo, owner):
            self.reads += 1
            self.assertEqual((repo, owner), (REPO, OWNER))
            if fail == "read":
                raise RuntimeError("gh api failed: HTTP 502")
            return self.issues

        def edit_issue(repo, n, body):
            if fail == "edit":
                raise RuntimeError(f"editing #{n} failed: HTTP 403")
            self.edits.append((n, body))
            for i in self.issues:
                if i["number"] == n:
                    i["body"] = body
        w = StartTest.watcher(self)
        w.list_issues, w.edit_issue = list_issues, edit_issue
        return w

    def watch_issue(self, n=300, body=watch.WATCH_MARKER):
        return {**issue(n, body=body, title=watch.WATCH_TITLE)}

    def published(self, k=-1):
        return watch.body_state(self.edits[k][1])

    def test_a_changed_tick_edits_the_issue_once_and_an_unchanged_one_reads_nothing(self):
        w = self.watcher()
        w.tick(NOW)
        self.assertEqual([n for n, _ in self.edits], [300])
        self.assertEqual(self.published(), json.loads((self.home / "launcher" / watch.PUBLIC_FILE).read_text()))
        self.assertIn("published its state to #300", "\n".join(self.lines))
        w.tick(NOW + dt.timedelta(minutes=5))          # same state, only `checked` moved
        self.assertEqual((len(self.edits), self.reads), (1, 1))

    def test_a_tick_that_changes_the_state_edits_again(self):
        w = self.watcher()
        w.tick(NOW)
        self.scene.prs.clear()                         # PR #70 goes: a different state
        for e in self.l.load():
            self.fake.procs.pop(self.l.pid(e))         # and every run ends
        w.tick(NOW + dt.timedelta(minutes=5))
        self.assertEqual(len(self.edits), 2)
        self.assertNotEqual(watch.changes(self.published(0)), watch.changes(self.published(1)))

    def test_after_a_restart_an_issue_already_current_is_not_edited(self):
        self.watcher().tick(NOW)
        issues = self.issues
        w = self.watcher(issues)                       # a new process: nothing in memory
        w.tick(NOW + dt.timedelta(minutes=5))
        self.assertEqual((self.edits, self.reads), ([], 1))

    def test_the_body_is_the_marker_and_the_public_state_only(self):
        self.manifest(ALL_CAPPED, max_live=2)
        self.watcher().tick(NOW)
        body = self.edits[0][1]
        self.assertTrue(body.startswith(watch.WATCH_MARKER + " "))
        self.assertEqual(body.count("```"), 2)
        for word in ("cost_usd", "detail", "why", "$", "issue 49", "issue 60"):   # no titles either
            self.assertNotIn(word, body)

    def test_a_missing_issue_prints_the_command_once_and_carries_on(self):
        w = self.watcher(issues=[issue(5, body="not it")])
        done = w.tick(NOW)
        self.assertTrue(done)                          # the tick still started its runs
        w.tick(NOW + dt.timedelta(minutes=5))
        told = [x for x in self.lines if "gh issue create" in x]
        self.assertEqual(len(told), 1)
        self.assertIn(f"--repo {REPO} --title \"{watch.WATCH_TITLE}\" --body '{watch.WATCH_MARKER}'", told[0])
        self.assertEqual(self.edits, [])
        self.issues.append(self.watch_issue())         # the owner opens it: the next tick publishes
        w.tick(NOW + dt.timedelta(minutes=10))
        self.assertEqual([n for n, _ in self.edits], [300])

    def test_two_marked_issues_edit_neither(self):
        w = self.watcher(issues=[self.watch_issue(300), self.watch_issue(301)])
        w.tick(NOW)
        self.assertEqual(self.edits, [])
        self.assertIn("2 open issues start with", "\n".join(self.lines))

    def test_a_failed_edit_or_read_is_printed_and_tried_again(self):
        for fail in ("edit", "read"):
            with self.subTest(fail):
                w = self.watcher(fail=fail)
                w.tick(NOW)                            # no exception: the loop carries on
                self.assertIn("publishing its state failed", self.lines[-1])
                self.assertIn("trying again next check", self.lines[-1])
                self.assertEqual(self.edits, [])
                self.assertIsNone(w.published)
                self.assertTrue((self.home / "launcher" / watch.PUBLIC_FILE).exists())
                ok = self.watcher(self.issues)          # GitHub is back: the next tick publishes
                w.list_issues, w.edit_issue = ok.list_issues, ok.edit_issue
                w.tick(NOW + dt.timedelta(minutes=5))
                self.assertEqual(len(self.edits), 1)

    def test_off_by_default_and_in_dry_run(self):
        StartTest.watcher(self).tick(NOW)              # no list_issues/edit_issue: no GitHub writes
        w = self.watcher()
        w.dry_run = True
        w.tick(NOW)
        self.assertEqual((self.edits, self.reads), ([], 0))

    def test_body_state_reads_back_what_watch_body_writes(self):
        pub = {"checked": "t", "running": [], "held": [], "skipped": [], "failed": []}
        self.assertEqual(watch.body_state(watch.watch_body(pub).replace("\n", "\r\n")), pub)
        self.assertIsNone(watch.body_state(watch.WATCH_MARKER))
        self.assertIsNone(watch.body_state("```json\n{bad\n```"))
        self.assertEqual(watch.changes(pub), {"running": [], "held": [], "skipped": [], "failed": []})

    def test_the_dashboard_uses_the_same_marker(self):
        sys.path.insert(0, str(HERE.parent / "dashboard"))
        import activity
        self.assertEqual(activity.WATCH_MARKER, watch.WATCH_MARKER)
