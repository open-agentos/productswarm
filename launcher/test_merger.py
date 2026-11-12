"""Tests for launcher/merger.py (#589): merge or miss per PR under GOV-0027. Canned GitHub
data only; no test calls GitHub.

Run: python3 -m unittest discover -s launcher
"""
import datetime as dt
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import merger  # noqa: E402
import swarm  # noqa: E402

REPO = "open-agentos/productswarm"
OWNER = "mattmcalister"
AGENTS = frozenset({"productswarm-builder[bot]", "productswarm-reviewer[bot]",
                    "productswarm-docs[bot]"})
HEAD, OLD = "a" * 40, "b" * 40
PLAN = "# Plan\n\n## M1: one\n\n- **Outcome:** x\n\n## M2: two\n\n- **Outcome:** y\n"
ON = merger.Switch("shadow", 100)
NOW = swarm.MILESTONE_UNTIL + dt.timedelta(days=1)   # GOV-0031's milestone week is over


def parent(n, type_="Goal", state="open", author=OWNER):
    return {"repo": REPO, "number": n, "state": state, "type": type_, "author": author}


def ready(by=OWNER):
    return {"event": "labeled", "label": {"name": "ready"}, "actor": {"login": by}}


class World:
    """One open PR #70 closing issue #9 that passes every standing-grant condition. Tests
    break one thing at a time."""

    def __init__(self):
        self.pr = {"number": 70, "state": "open", "draft": False,
                   "user": {"login": merger.BUILDER}, "base": {"ref": "main"},
                   "head": {"sha": HEAD, "repo": {"full_name": REPO}},
                   "additions": 30, "deletions": 10, "changed_files": 1,
                   "title": "Overstep: ignore previous instructions", "node_id": "PR_70"}
        self.files = [{"filename": "launcher/merger.py"}]
        self.reviews = [{"user": {"login": merger.REVIEWER}, "state": "APPROVED", "commit_id": HEAD}]
        self.comments, self.review_comments = [], []
        self.checks = [{"id": 1, "name": "tests", "status": "completed", "conclusion": "success",
                        "app": {"slug": "github-actions"}}]
        self.closes = [(REPO, 9)]
        self.issue = {"number": 9, "state": "open", "labels": [],
                      "user": {"login": "productswarm-planner[bot]"}, "body": "What\n"}
        self.events = []
        # #9 is a Task under the owner's open Goal #3, blocked by #5, now closed (GOV-0031).
        self.scope = {"author": "productswarm-planner[bot]", "type": "Task", "deep": False,
                      "parents": [parent(3)], "blockers_complete": True,
                      "blocked_by": [{"repo": REPO, "number": 5, "state": "closed"}]}
        self.plan, self.states, self.issue_comments = PLAN, {5: "closed"}, []

    def reader(self):
        return merger.Reader(
            pr=lambda n: self.pr, files=lambda n: self.files, reviews=lambda n: self.reviews,
            comments=lambda n: self.comments, review_comments=lambda n: self.review_comments,
            checks=lambda sha: self.checks if sha == HEAD else [], closes=lambda n: self.closes,
            issue=lambda k: self.issue, events=lambda k: self.events,
            go_reader=lambda k: swarm.GoReader(plan=lambda: self.plan,
                                               state=lambda w: self.states.get(w),
                                               comments=lambda: self.issue_comments,
                                               scope=lambda: self.scope))

    def decide(self, switch=ON, agents=AGENTS | {"productswarm-planner[bot]"}, now=NOW):
        ctx = merger.Context(REPO, OWNER, frozenset(agents), switch, now)
        return merger.decide(self.pr, ctx, self.reader())

    def protect(self, path="roles/builder.md"):
        """Turn the PR into an approved ask that passes: a protected path, owner approval."""
        self.files = [{"filename": "launcher/merger.py"}, {"filename": path}]
        self.pr["changed_files"] = 2
        self.reviews = [{"user": {"login": OWNER}, "state": "APPROVED", "commit_id": HEAD}]


class StandingGrant(unittest.TestCase):
    def setUp(self):
        self.w = World()

    def miss(self, *words):
        got = self.w.decide()
        self.assertTrue(got.startswith("miss: "), got)
        self.assertNotIn("approved ask", got)
        for word in words:
            self.assertIn(word, got)

    def test_passes(self):
        self.assertEqual(self.w.decide(), merger.GRANT)

    def test_author_not_builder(self):
        self.w.pr["user"]["login"] = "productswarm-docs[bot]"
        self.miss("not opened by productswarm-builder[bot]")

    def test_base_not_main(self):
        self.w.pr["base"]["ref"] = "other"
        self.miss("base isn't main")

    def test_closes_none_or_two(self):
        self.w.closes = []
        self.miss("closes 0 issues")
        self.w.closes = [(REPO, 9), (REPO, 10)]
        self.miss("closes 2 issues")

    def test_closes_issue_in_another_repo(self):
        self.w.closes = [("someone/else", 9)]
        self.miss("another repo")

    def test_issue_closed(self):
        self.w.issue["state"] = "closed"
        self.miss("#9 isn't an open issue")

    def test_goal_issue_is_go(self):
        """The default World: a Task under the owner's open Goal, its blocker closed."""
        self.assertEqual(self.w.decide(), merger.GRANT)
        self.w.scope["type"] = None                       # untyped counts too
        self.assertEqual(self.w.decide(), merger.GRANT)
        self.w.scope["parents"] = [parent(20, "Mission", author="productswarm-lead[bot]"),
                                   parent(4, "Area")]     # at any depth, and an Area counts
        self.assertEqual(self.w.decide(), merger.GRANT)

    def test_ready_issue_is_go(self):
        """GOV-0034's option 3: the owner's most recent `ready` counts with no Goal above."""
        self.w.scope["parents"] = []
        self.w.issue["labels"] = [{"name": "ready"}]
        self.w.events = [ready()]
        self.assertEqual(self.w.decide(), merger.GRANT)
        self.w.events = [ready(), ready("productswarm-planner[bot]")]
        self.miss("not go under GOV-0031", "added by productswarm-planner[bot], not @mattmcalister")

    def test_not_a_sub_issue(self):
        self.w.scope["parents"] = []
        self.assertEqual(self.w.decide(),
                         "miss: not go under GOV-0031: #9 isn't a sub-issue of anything, "
                         "so no Goal or Area makes it go")

    def test_scope_unreadable(self):
        self.w.scope = None
        self.miss("not go under GOV-0031", "sub-issue links couldn't be read")

    def test_brief_under_a_goal_is_refused(self):
        self.w.scope["type"] = "Brief"
        self.miss("not go under GOV-0031", "#9 is a Brief, not an implementation issue")

    def test_goal_closed_or_not_the_owners(self):
        self.w.scope["parents"] = [parent(3, state="closed")]
        self.miss("not go under GOV-0031", "Goal #3 is closed")
        self.w.scope["parents"] = [parent(3, author="productswarm-lead[bot]")]
        self.miss("not go under GOV-0031", "opened by productswarm-lead[bot]")

    def test_issue_blocked(self):
        self.w.scope["blocked_by"][0]["state"] = "open"
        self.miss("not go under GOV-0031", "#9 is blocked by #5, still open")
        self.w.scope["blocked_by"][0]["state"] = "closed"
        self.w.scope["blockers_complete"] = False
        self.miss("not all could be read")

    def test_issue_vetoed(self):
        self.w.issue["labels"] = [{"name": "hold"}]
        self.miss("not go under GOV-0031", "`hold`")
        self.w.issue["labels"] = []
        self.w.issue_comments = [{"user": {"login": OWNER}, "body": "wait"}]
        self.miss("not go under GOV-0031", "veto")

    def test_issue_opened_by_outsider(self):
        self.w.issue["user"]["login"] = "stranger"
        self.miss("not go under GOV-0031", "not a swarm App")

    def test_milestone_counts_only_in_gov_0031s_week(self):
        """The go is the watcher's: a GOV-0026 milestone line counts until MILESTONE_UNTIL."""
        self.w.scope["parents"] = []
        self.w.issue["body"] = "What\n\n**Milestone:** M2\n"
        before = swarm.MILESTONE_UNTIL - dt.timedelta(hours=1)
        self.assertEqual(self.w.decide(now=before), merger.GRANT)
        got = self.w.decide()
        self.assertTrue(got.startswith("miss: not go under GOV-0031: #9's `**Milestone:**` "
                                       "line stopped counting"), got)

    def test_gov_question(self):
        self.w.issue["labels"] = [{"name": "gov:question"}]
        self.miss("gov:question")

    def test_no_reviewer_approval(self):
        self.w.reviews = []
        self.miss("hasn't approved at head aaaaaaa")

    def test_approval_not_at_head(self):
        """A head pushed after the approval is a miss."""
        self.w.reviews[0]["commit_id"] = OLD
        self.miss("hasn't approved at head")

    def test_approval_dismissed(self):
        self.w.reviews[0]["state"] = "DISMISSED"
        self.miss("hasn't approved at head")

    def test_owner_approval_does_not_count_for_a_grant(self):
        self.w.reviews[0]["user"]["login"] = OWNER
        self.miss("productswarm-reviewer[bot] hasn't approved")

    def test_open_request_for_changes(self):
        self.w.reviews.insert(0, {"user": {"login": OWNER}, "state": "CHANGES_REQUESTED",
                                  "commit_id": OLD})
        self.w.reviews.append({"user": {"login": OWNER}, "state": "COMMENTED", "commit_id": HEAD})
        self.miss("changes requested by mattmcalister")

    def test_request_for_changes_cleared_by_later_approval(self):
        self.w.reviews.insert(0, {"user": {"login": merger.REVIEWER}, "state": "CHANGES_REQUESTED",
                                  "commit_id": OLD})
        self.assertEqual(self.w.decide(), merger.GRANT)

    def test_overstep(self):
        for where in ("comments", "review_comments"):
            w = World()
            setattr(w, where, [{"user": {"login": merger.REVIEWER}, "body": "Overstep: chose X"}])
            self.assertTrue(w.decide().startswith("miss: an `Overstep:`"), where)
        self.w.reviews[0]["body"] = "Rubric\n\n**Overstep:** chose X"
        self.miss("Overstep")

    def test_overstep_in_title_or_mid_line_is_not_a_finding(self):
        self.w.comments = [{"body": "No Overstep: found"}]
        self.assertEqual(self.w.decide(), merger.GRANT)

    def test_tests(self):
        self.w.checks = []
        self.miss("no `tests` check")
        self.w.checks = [dict(World().checks[0], status="in_progress", conclusion=None)]
        self.miss("hasn't finished")
        self.w.checks = [dict(World().checks[0], conclusion="failure")]
        self.miss("concluded failure")

    def test_tests_newest_run_counts(self):
        self.w.checks = [dict(World().checks[0], id=2, conclusion="failure"), World().checks[0]]
        self.miss("concluded failure")

    def test_tests_from_another_app_dont_count(self):
        self.w.checks[0]["app"] = {"slug": "productswarm-builder"}
        self.miss("no `tests` check")

    def test_tests_on_old_head_dont_count(self):
        self.w.pr["head"]["sha"] = OLD
        self.w.reviews[0]["commit_id"] = OLD
        self.miss("no `tests` check")

    def test_protected_path_makes_it_an_ask(self):
        self.w.files.append({"filename": "ops/swarm-session"})
        self.w.pr["changed_files"] = 2
        got = self.w.decide()
        self.assertTrue(got.startswith("miss: approved ask: touches `ops/swarm-session`"), got)
        self.assertIn("mattmcalister hasn't approved", got)

    def test_size(self):
        self.w.pr["additions"] = 91
        self.miss("101 changed lines, over [merger] max_changed_lines 100")
        self.w.pr["additions"] = 90
        self.assertEqual(self.w.decide(), merger.GRANT)

    def test_unseen_files(self):
        self.w.pr["changed_files"] = 2
        self.miss("can't see every changed file")

    def test_off(self):
        got = self.w.decide(switch=merger.Switch("off", None, "swarm.toml has no [merger] table"))
        self.assertEqual(got, "miss: the merger is off (swarm.toml has no [merger] table)")


class ApprovedAsk(unittest.TestCase):
    def setUp(self):
        self.w = World()
        self.w.protect()

    def miss(self, *words):
        got = self.w.decide()
        self.assertTrue(got.startswith("miss: approved ask: "), got)
        for word in words:
            self.assertIn(word, got)

    def test_passes(self):
        self.assertEqual(self.w.decide(), merger.ASK)

    def test_any_swarm_app_and_no_milestone(self):
        self.w.pr["user"]["login"] = "productswarm-docs[bot]"
        self.w.closes, self.w.issue["body"] = [], ""
        self.w.pr["additions"] = 5000
        self.assertEqual(self.w.decide(), merger.ASK)

    def test_excluded_files(self):
        for path in ("GOVERNANCE.md", "governance/jurisdictions.yml", ".github/workflows/tests.yml"):
            w = World()
            w.protect(path)
            got = w.decide()
            self.assertEqual(got, f"miss: approved ask: touches `{path}`, which the owner merges "
                                  "(GOV-0027)")

    def test_excluded_by_rename(self):
        self.w.files[1]["previous_filename"] = "GOVERNANCE.md"
        self.miss("`GOVERNANCE.md`")

    def test_not_a_swarm_app(self):
        self.w.pr["user"]["login"] = OWNER
        self.miss("not opened by a swarm App")

    def test_no_owner_approval(self):
        self.w.reviews = [{"user": {"login": merger.REVIEWER}, "state": "APPROVED", "commit_id": HEAD}]
        self.miss("mattmcalister hasn't approved at head")

    def test_owner_approval_not_at_head(self):
        """A head pushed after the owner's approval is a miss."""
        self.w.reviews[0]["commit_id"] = OLD
        self.miss("hasn't approved at head")

    def test_open_request_for_changes(self):
        self.w.reviews.insert(0, {"user": {"login": merger.REVIEWER}, "state": "CHANGES_REQUESTED",
                                  "commit_id": HEAD})
        self.miss("changes requested by productswarm-reviewer[bot]")

    def test_overstep(self):
        self.w.comments = [{"body": "Overstep: touched roles/"}]
        self.miss("Overstep")

    def test_tests(self):
        self.w.checks[0]["conclusion"] = "failure"
        self.miss("concluded failure")

    def test_base_not_main(self):
        self.w.pr["base"]["ref"] = "other"
        self.assertEqual(self.w.decide(), "miss: its base isn't main")


class Paths(unittest.TestCase):
    def test_protected(self):
        for p in ("ops/x", ".github/CODEOWNERS", "governance/INDEX.md", "GOVERNANCE.md",
                  "roles/builder.md", "CLAUDE.md", "launcher/CLAUDE.md", "swarm.toml",
                  "requirements.txt", "dashboard/requirements-dev.txt", "package.json",
                  "pyproject.toml", "PLAN.md"):
            self.assertTrue(merger.is_protected(p), p)
        for p in ("launcher/merger.py", "docs/PLAN.md", "PRODUCT.md", "launcher/swarm.toml.md",
                  "opsx/y", "dashboard/static/app.js"):
            self.assertFalse(merger.is_protected(p), p)

    def test_unusual_path_not_printed(self):
        self.assertEqual(merger.show("ops/a\n::warning::x"), "a path with unusual characters")


class Switch(unittest.TestCase):
    def load(self, text):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "swarm.toml"
            p.write_text(text)
            return merger.load_switch(p)

    def test_values(self):
        self.assertEqual(self.load('[merger]\nmode = "shadow"\nmax_changed_lines = 300\n'),
                         merger.Switch("shadow", 300))
        self.assertEqual(self.load('[merger]\nmode = "live"\nmax_changed_lines = 1\n').mode, "live")

    def test_missing_or_bad_means_off(self):
        for text in ("", "[merger]\n", '[merger]\nmode = "shadow"\n',
                     '[merger]\nmax_changed_lines = 5\n', '[merger]\nmode = "on"\nmax_changed_lines = 5\n',
                     '[merger]\nmode = "live"\nmax_changed_lines = 0\n',
                     '[merger]\nmode = "live"\nmax_changed_lines = true\n',
                     '[merger]\nmode = "live"\nmax_changed_lines = "5"\n',
                     '[merger]\nmode = "off"\nmax_changed_lines = 5\n', 'merger = 3\n'):
            s = self.load(text)
            self.assertEqual(s.mode, "off", text)
            self.assertTrue(s.why_off, text)

    def test_unreadable_raises(self):
        with self.assertRaises(ValueError):
            self.load("not toml [")
        with self.assertRaises(OSError):
            merger.load_switch("/nonexistent/swarm.toml")

    def test_manifest_accepts_merger_table(self):
        import manifest
        text = ('[merger]\nmode = "shadow"\nmax_changed_lines = 300\n\n'
                '[[session]]\nrole = "builder"\ncount = 1\nmodel = "m"\n')
        self.assertEqual(len(manifest.parse(text, roles_dir=HERE.parent / "roles")), 1)


class Plan(unittest.TestCase):
    def run_plan(self, w, prs, toml='[merger]\nmode = "shadow"\nmax_changed_lines = 100\n',
                 authors=(AGENTS | {"productswarm-planner[bot]"}, None), pr=None):
        out = []
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "swarm.toml"
            p.write_text(toml)
            code = merger.plan(REPO, pr=pr, manifest_path=p, reader=w.reader(),
                               owner=lambda: OWNER, authors=lambda: (frozenset(authors[0]), authors[1]),
                               list_prs=lambda: prs, out=out.append)
        return code, out

    def test_lines(self):
        code, out = self.run_plan(World(), [{"number": 70}])
        self.assertEqual(code, 0)
        self.assertEqual(out, [f"#70 {HEAD} merge (standing grant)",
                               "merger: mode shadow: 1 PR(s) would merge"])

    def test_skips_draft_fork_closed(self):
        for change, why in ((("draft", True), "a draft"), (("state", "closed"), "closed"),
                            (("head", {"sha": HEAD, "repo": {"full_name": "x/y"}}), "isn't in this repo")):
            w = World()
            w.pr[change[0]] = change[1]
            code, out = self.run_plan(w, [{"number": 70}])
            self.assertEqual(code, 0)
            self.assertTrue(out[0].startswith(f"#70 {HEAD} skip: "), out)
            self.assertIn(why, out[0])

    def test_outsider_is_a_miss(self):
        w = World()
        w.pr["user"]["login"] = "stranger"
        _, out = self.run_plan(w, [{"number": 70}])
        self.assertTrue(out[0].startswith(f"#70 {HEAD} miss: "), out)

    def test_off_is_a_miss_for_every_pr(self):
        code, out = self.run_plan(World(), [{"number": 70}], toml="")
        self.assertEqual(code, 0)
        self.assertEqual(out[0], f"#70 {HEAD} miss: the merger is off (swarm.toml has no [merger] table)")
        self.assertEqual(out[-1], "merger: mode off: 0 PR(s) would merge")

    def test_pr_flag(self):
        code, out = self.run_plan(World(), None, pr=70)
        self.assertEqual(code, 0)
        self.assertEqual(out[-1], "merger: mode shadow: 1 PR(s) would merge (--pr 70)")

    def test_github_unreadable(self):
        w = World()
        r = w.reader()
        def boom(n):
            raise RuntimeError("gh api failed")
        r.reviews = boom
        out = []
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "swarm.toml"
            p.write_text('[merger]\nmode = "live"\nmax_changed_lines = 100\n')
            code = merger.plan(REPO, manifest_path=p, reader=r, owner=lambda: OWNER,
                               authors=lambda: (AGENTS | {"productswarm-planner[bot]"}, None),
                               list_prs=lambda: [{"number": 70}],
                               out=out.append)
        self.assertEqual(code, 1)
        self.assertEqual(out, ["merger: can't decide (RuntimeError): every PR is a miss"])

    def test_files_unreadable(self):
        code, out = self.run_plan(World(), [{"number": 70}], toml="not toml [")
        self.assertEqual(code, 1)
        code, out = self.run_plan(World(), [{"number": 70}],
                                  authors=(frozenset(), "can't read jurisdictions.yml (OSError)"))
        self.assertEqual(code, 1)
        self.assertIn("every PR is a miss", out[0])


T0 = 1_800_000_000.0   # a fixed "now" for the shadow bar


def iso(t):
    return merger.actions_review.utc(t)


def would(t, head="c" * 40, who=merger.MERGER, pr=1, kind="standing grant"):
    return {"user": {"login": who}, "body": f"Would merge ({kind}) at {head}.\n\n-- merger",
            "created_at": iso(t), "issue_url": f"https://api.github.com/repos/{REPO}/issues/{pr}"}


class FakeWriter:
    def __init__(self, history=()):
        self.history_items, self.posts, self.merges = list(history), [], []
        self.fail_merge = False
        self.queued, self.enqueues = False, []    # whether main requires a merge queue (#663)

    def writer(self, w):
        def post(n, body):
            self.posts.append((n, body))
            w.comments.append({"user": {"login": merger.MERGER}, "body": body})
        def merge(n, sha):
            if self.fail_merge:
                raise RuntimeError("409 head moved")
            self.merges.append((n, sha))
        def queue():
            if isinstance(self.queued, Exception):
                raise self.queued
            return self.queued
        def enqueue(node_id, sha):
            if self.fail_merge:
                raise RuntimeError("head moved")
            self.enqueues.append((node_id, sha))
        return merger.Writer(history=lambda: self.history_items, post=post, merge=merge,
                             queue=queue, enqueue=enqueue)


class Run(unittest.TestCase):
    def run_run(self, w, fw, mode="shadow", dry_run=False, reader=None):
        out = []
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "swarm.toml"
            p.write_text(f'[merger]\nmode = "{mode}"\nmax_changed_lines = 100\n')
            code = merger.run(REPO, dry_run=dry_run, manifest_path=p, reader=reader or w.reader(),
                              writer=fw.writer(w), owner=lambda: OWNER,
                              authors=lambda: (AGENTS | {"productswarm-planner[bot]"}, None),
                              list_prs=lambda: [{"number": 70}], clock=lambda: T0,
                              out=out.append)
        return code, out

    def test_shadow_posts_once_per_head(self):
        w, fw = World(), FakeWriter()
        code, out = self.run_run(w, fw)
        self.assertEqual(code, 0)
        self.assertEqual(fw.posts, [(70, f"Would merge (standing grant) at {HEAD}.\n\n-- merger")])
        self.assertEqual(fw.merges, [])
        self.run_run(w, fw)                       # the next sweep repeats nothing
        self.assertEqual(len(fw.posts), 1)

    def test_shadow_posts_again_for_a_new_head(self):
        w, fw = World(), FakeWriter()
        self.run_run(w, fw)
        # A "would merge" at the old head doesn't count for a new one.
        w.comments = [{"user": {"login": merger.MERGER},
                       "body": f"Would merge (standing grant) at {OLD}.\n\n-- merger"}]
        self.run_run(w, fw)
        self.assertEqual(len(fw.posts), 2)

    def test_someone_elses_would_merge_doesnt_count(self):
        w, fw = World(), FakeWriter()
        w.comments = [{"user": {"login": "stranger"},
                       "body": f"Would merge (standing grant) at {HEAD}.\n\n-- merger"}]
        self.run_run(w, fw)
        self.assertEqual(len(fw.posts), 1)

    def test_approved_ask_wording(self):
        w, fw = World(), FakeWriter()
        w.protect()
        self.run_run(w, fw)
        self.assertEqual(fw.posts, [(70, f"Would merge (approved ask) at {HEAD}.\n\n-- merger")])

    def test_miss_on_an_approved_pr_posts_reason_once(self):
        w, fw = World(), FakeWriter()
        w.pr["additions"] = 500
        self.run_run(w, fw)
        self.assertEqual(len(fw.posts), 1)
        n, body = fw.posts[0]
        self.assertTrue(body.startswith(f"Left for the owner at {HEAD}: 510 changed lines"), body)
        self.assertTrue(body.endswith("\n\n-- merger"))
        self.run_run(w, fw)
        self.assertEqual(len(fw.posts), 1)

    def test_miss_approved_by_owner_posts(self):
        w, fw = World(), FakeWriter()
        w.protect(".github/workflows/x.yml")      # excluded: the owner merges it
        self.run_run(w, fw)
        self.assertEqual(len(fw.posts), 1)
        self.assertIn("which the owner merges", fw.posts[0][1])

    def test_miss_without_approval_posts_nothing(self):
        w, fw = World(), FakeWriter()
        w.reviews = []
        code, _ = self.run_run(w, fw)
        self.assertEqual((code, fw.posts, fw.merges), (0, [], []))
        w.reviews = [{"user": {"login": merger.REVIEWER}, "state": "APPROVED", "commit_id": OLD}]
        self.run_run(w, fw)
        self.assertEqual(fw.posts, [])

    def test_miss_while_tests_run_posts_nothing(self):
        w, fw = World(), FakeWriter()
        w.checks[0]["status"] = "in_progress"
        self.run_run(w, fw)
        self.assertEqual(fw.posts, [])

    def test_live_held_back_by_shadow_bar(self):
        w, fw = World(), FakeWriter([would(T0 - 3600 * i, pr=i) for i in range(9)])
        code, out = self.run_run(w, fw, mode="live")
        self.assertEqual(code, 0)
        self.assertEqual(fw.merges, [])
        self.assertTrue(fw.posts[0][1].startswith("Would merge"))
        self.assertTrue(any("live acts as shadow" in line and "9 of 10" in line for line in out), out)

    def test_live_merges_after_ten(self):
        w, fw = World(), FakeWriter([would(T0 - 60 * i, pr=i) for i in range(10)])
        code, out = self.run_run(w, fw, mode="live")
        self.assertEqual(code, 0)
        self.assertEqual(fw.merges, [(70, HEAD)])
        self.assertEqual(fw.posts, [(70, f"Merged under standing grant (GOV-0027) at {HEAD}.\n\n-- merger")])

    def test_live_merges_a_day_after_the_first(self):
        w, fw = World(), FakeWriter([would(T0 - merger.SHADOW_SECONDS)])
        self.run_run(w, fw, mode="live")
        self.assertEqual(fw.merges, [(70, HEAD)])
        w, fw = World(), FakeWriter([would(T0 - merger.SHADOW_SECONDS + 60)])
        self.run_run(w, fw, mode="live")
        self.assertEqual(fw.merges, [])

    def test_shadow_bar_counts_only_the_merger(self):
        w, fw = World(), FakeWriter([would(T0 - 60 * i, who="stranger", pr=i) for i in range(10)])
        self.run_run(w, fw, mode="live")
        self.assertEqual(fw.merges, [])

    def test_shadow_bar_counts_prs_not_heads(self):
        # GOV-0027's bar is 10 PRs: ten heads of one PR, or of nine, don't meet it.
        for history in ([would(T0 - 60 * i, head=f"{i:040x}") for i in range(10)],
                        [would(T0 - 60 * i, head=f"{i:040x}", pr=i % 9) for i in range(20)]):
            w, fw = World(), FakeWriter(history)
            code, out = self.run_run(w, fw, mode="live")
            self.assertEqual(fw.merges, [])
            self.assertTrue(any("live acts as shadow" in line for line in out), out)

    def test_shadow_bar_ignores_comments_naming_no_pr(self):
        history = [dict(would(T0 - 60 * i, pr=i), issue_url=None) for i in range(10)]
        w, fw = World(), FakeWriter(history)
        self.run_run(w, fw, mode="live")
        self.assertEqual(fw.merges, [])

    def test_grant_shadow_holds_only_the_standing_grant(self):
        """GOV-0034: GOV-0027's bar met by approved asks alone leaves standing grants in shadow."""
        asks = [would(T0 - 60 * i, pr=i, kind="approved ask") for i in range(10)]
        grants = [would(T0 - 60 * i, pr=100 + i) for i in range(9)]
        w, fw = World(), FakeWriter(asks + grants)
        code, out = self.run_run(w, fw, mode="live")
        self.assertEqual(code, 0)
        self.assertEqual(fw.merges, [])
        self.assertEqual(fw.posts, [(70, f"Would merge (standing grant) at {HEAD}.\n\n-- merger")])
        self.assertIn("merger: live acts as shadow for the standing grant (GOV-0034): the shadow bar "
                      "isn't met (9 of 10 PRs with a \"would merge (standing grant)\" comment, the "
                      f"first at {iso(T0 - 8 * 60)}; or a day since the first)", out)
        self.assertEqual(out[-1], "merger: mode live: 0 PR(s) merged, 1 would merge")
        # The same history doesn't hold an approved ask back.
        w, fw = World(), FakeWriter(asks + grants)
        w.protect()
        self.run_run(w, fw, mode="live")
        self.assertEqual(fw.merges, [(70, HEAD)])

    def test_grant_shadow_count(self):
        """Ten distinct PRs with a standing-grant "would merge", or a day since the first."""
        for history, merges in (([would(T0 - 60 * i, pr=i) for i in range(10)], True),
                                ([would(T0 - 60 * i, pr=i % 9) for i in range(10)], False),
                                ([would(T0 - merger.SHADOW_SECONDS, pr=1),
                                  would(T0 - 60, pr=2, kind="approved ask")], True),
                                ([would(T0 - merger.SHADOW_SECONDS, pr=1, kind="approved ask"),
                                  would(T0 - 60, pr=2)], False)):
            w, fw = World(), FakeWriter(history)
            _, out = self.run_run(w, fw, mode="live")
            self.assertEqual(fw.merges, [(70, HEAD)] if merges else [], (history, out))
            self.assertEqual(any("live acts as shadow" in x for x in out), not merges)

    def test_shadow_bar_unreadable_holds_live_back(self):
        w, fw = World(), FakeWriter()
        writer = fw.writer(w)
        def boom():
            raise RuntimeError("gh failed")
        fw.writer = lambda w: merger.Writer(history=boom, post=writer.post, merge=writer.merge,
                                            queue=writer.queue, enqueue=writer.enqueue)
        code, out = self.run_run(w, fw, mode="live")
        self.assertEqual(fw.merges, [])
        self.assertTrue(fw.posts[0][1].startswith("Would merge"))

    def test_head_pin(self):
        w, fw = World(), FakeWriter([would(T0 - 60 * i, pr=i) for i in range(10)])
        r = w.reader()
        calls = []
        def pr(n):
            calls.append(n)          # the second read, just before merging, sees a new head
            return w.pr if len(calls) == 1 else dict(w.pr, head={"sha": OLD, "repo": {"full_name": REPO}})
        r.pr = pr
        code, out = self.run_run(w, fw, mode="live", reader=r)
        self.assertEqual((fw.merges, fw.posts), ([], []))
        self.assertTrue(any("head moved" in line for line in out), out)

    def test_merge_refused_by_github_posts_nothing(self):
        w, fw = World(), FakeWriter([would(T0 - 60 * i, pr=i) for i in range(10)])
        fw.fail_merge = True
        code, out = self.run_run(w, fw, mode="live")
        self.assertEqual(code, 1)
        self.assertEqual(fw.posts, [])

    def test_off_writes_nothing(self):
        w, fw = World(), FakeWriter([would(T0 - 60 * i, pr=i) for i in range(10)])
        w.pr["additions"] = 500
        for mode in ("off", "bogus"):
            code, out = self.run_run(w, fw, mode=mode)
            self.assertEqual((code, fw.posts, fw.merges), (0, [], []))
            self.assertIn("nothing posted or merged", out[-1])

    def test_dry_run_writes_nothing(self):
        for mode in ("shadow", "live"):
            w, fw = World(), FakeWriter([would(T0 - 60 * i, pr=i) for i in range(10)])
            code, out = self.run_run(w, fw, mode=mode, dry_run=True)
            self.assertEqual((code, fw.posts, fw.merges), (0, [], []))
            self.assertTrue(any(line.startswith("dry run: would ") for line in out), out)
        self.assertIn(f"dry run: would merge #70 at {HEAD}", out)

    def test_cant_decide_writes_nothing(self):
        w, fw = World(), FakeWriter()
        r = w.reader()
        def boom(n):
            raise RuntimeError("gh api failed")
        r.reviews = boom
        code, out = self.run_run(w, fw, reader=r)
        self.assertEqual((code, fw.posts, fw.merges), (1, [], []))


class Queue(unittest.TestCase):
    """#663: when main requires a merge queue, the merger enqueues instead of merging."""

    run_run = Run.run_run

    def setUp(self):
        self.live = [would(T0 - 60 * i, pr=i) for i in range(10)]   # both shadow bars met

    def test_no_queue_merges_directly(self):
        w, fw = World(), FakeWriter(self.live)
        code, out = self.run_run(w, fw, mode="live")
        self.assertEqual((code, fw.merges, fw.enqueues), (0, [(70, HEAD)], []))
        self.assertIn(f"#70 {HEAD} merge (standing grant)", out)
        self.assertEqual(out[-1], "merger: mode live: 1 PR(s) merged")

    def test_queue_enqueues(self):
        w, fw = World(), FakeWriter(self.live)
        fw.queued = True
        code, out = self.run_run(w, fw, mode="live")
        self.assertEqual((code, fw.merges, fw.enqueues), (0, [], [("PR_70", HEAD)]))
        self.assertEqual(fw.posts, [(70, f"Enqueued under standing grant (GOV-0027) at {HEAD}.\n\n-- merger")])
        self.assertIn(f"#70 {HEAD} enqueue (standing grant)", out)
        self.assertEqual(out[-1], "merger: mode live: 1 PR(s) enqueued")
        # The PR stays open until the queue merges it: the next sweep doesn't enqueue it again.
        code, out = self.run_run(w, fw, mode="live")
        self.assertEqual((code, len(fw.enqueues), len(fw.posts)), (0, 1, 1))
        self.assertTrue(any("already enqueued" in x for x in out), out)

    def test_queue_enqueues_an_approved_ask(self):
        w, fw = World(), FakeWriter(self.live)
        w.protect()
        fw.queued = True
        self.run_run(w, fw, mode="live")
        self.assertEqual(fw.enqueues, [("PR_70", HEAD)])
        self.assertEqual(fw.posts, [(70, f"Enqueued under approved ask (GOV-0027) at {HEAD}.\n\n-- merger")])

    def test_queue_new_head_enqueues_again(self):
        w, fw = World(), FakeWriter(self.live)
        fw.queued = True
        w.comments = [{"user": {"login": merger.MERGER},
                       "body": f"Enqueued under standing grant (GOV-0027) at {OLD}.\n\n-- merger"}]
        self.run_run(w, fw, mode="live")
        self.assertEqual(fw.enqueues, [("PR_70", HEAD)])

    def test_queue_head_pin(self):
        w, fw = World(), FakeWriter(self.live)
        fw.queued = True
        r, calls = w.reader(), []
        def pr(n):
            calls.append(n)
            return w.pr if len(calls) == 1 else dict(w.pr, head={"sha": OLD, "repo": {"full_name": REPO}})
        r.pr = pr
        _, out = self.run_run(w, fw, mode="live", reader=r)
        self.assertEqual((fw.enqueues, fw.merges, fw.posts), ([], [], []))
        self.assertTrue(any("head moved" in x and "not enqueuing" in x for x in out), out)

    def test_queue_refused_by_github_posts_nothing(self):
        w, fw = World(), FakeWriter(self.live)
        fw.queued, fw.fail_merge = True, True
        code, _ = self.run_run(w, fw, mode="live")
        self.assertEqual((code, fw.posts, fw.merges), (1, [], []))

    def test_shadow_says_enqueue(self):
        w, fw = World(), FakeWriter()
        fw.queued = True
        code, out = self.run_run(w, fw)
        self.assertEqual((code, fw.merges, fw.enqueues), (0, [], []))
        self.assertIn(f"#70 {HEAD} enqueue (standing grant)", out)
        self.assertEqual(out[-1], "merger: mode shadow: 1 PR(s) would enqueue")
        # The comment keeps the shadow's wording, which the shadow bars and the desk count.
        self.assertEqual(fw.posts, [(70, f"Would merge (standing grant) at {HEAD}.\n\n-- merger")])

    def test_dry_run_says_enqueue(self):
        w, fw = World(), FakeWriter(self.live)
        fw.queued = True
        code, out = self.run_run(w, fw, mode="live", dry_run=True)
        self.assertEqual((code, fw.posts, fw.merges, fw.enqueues), (0, [], [], []))
        self.assertIn(f"dry run: would enqueue #70 at {HEAD}", out)

    def test_queue_unreadable_holds_live_back(self):
        w, fw = World(), FakeWriter(self.live)
        fw.queued = RuntimeError("gh failed")
        code, out = self.run_run(w, fw, mode="live")
        self.assertEqual((fw.merges, fw.enqueues), ([], []))
        self.assertTrue(fw.posts[0][1].startswith("Would merge"))
        self.assertTrue(any("live acts as shadow: can't tell whether main requires a merge queue"
                            in x for x in out), out)

    def test_queue_not_read_without_a_merge(self):
        w, fw = World(), FakeWriter(self.live)
        w.pr["additions"] = 500
        fw.queued = RuntimeError("must not be read")
        code, _ = self.run_run(w, fw, mode="live")
        self.assertEqual(code, 0)


SCRATCH = "open-agentos/scratch"


class OtherRepos(unittest.TestCase):
    """#772: the merger works swarm.toml's [org] repos after this one."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.calls = []

    def main(self, org="", argv=("plan",)):
        path = self.dir / "swarm.toml"
        path.write_text('[merger]\nmode = "shadow"\nmax_changed_lines = 100\n' + org)
        out = []
        self.homes = []
        fake = lambda repo, *a, home=None: self.calls.append(repo) or self.homes.append(home) or 0  # noqa: E731
        with unittest.mock.patch.object(merger, "plan", fake), \
                unittest.mock.patch.object(merger, "run", fake), \
                unittest.mock.patch("builtins.print", out.append):
            code = merger.main([*argv, "--manifest", str(path)], env={"GITHUB_REPOSITORY": REPO})
        return code, out

    def test_one_repo_listed_is_unchanged(self):
        self.assertEqual(self.main(), (0, []))
        self.assertEqual(self.calls, [REPO])

    def test_two_repos_are_each_worked(self):
        code, out = self.main(f'[org]\nrepos = ["{SCRATCH}"]\n', ("run", "--dry-run"))
        self.assertEqual((code, self.calls), (0, [REPO, SCRATCH]))
        self.assertEqual(out, [f"merger: repo {REPO}", f"merger: repo {SCRATCH}"])
        self.assertEqual(self.homes, [None, REPO])      # #913: scratch inherits home's shadow

    def test_repo_alone_inherits_no_shadow(self):
        self.main(f'[org]\nrepos = ["{SCRATCH}"]\n', ("run", "--repo", SCRATCH))
        self.assertEqual((self.calls, self.homes), ([SCRATCH], [None]))

    def test_repo_or_pr_works_one_repo(self):
        org = f'[org]\nrepos = ["{SCRATCH}"]\n'
        self.main(org, ("plan", "--repo", SCRATCH))
        self.main(org, ("plan", "--pr", "70"))
        self.assertEqual(self.calls, [SCRATCH, REPO])

    def test_home_listed_again_is_dropped_and_another_org_is_left_out(self):
        code, out = self.main(f'[org]\nrepos = ["{REPO}", "elsewhere/x", "{SCRATCH}"]\n')
        self.assertEqual(self.calls, [REPO, SCRATCH])
        self.assertIn("merger: elsewhere/x isn't in the open-agentos org, so it is left out "
                      "(GOV-0031 covers one org)", out)

    def test_a_bad_org_table_works_home_only(self):
        code, out = self.main('[org]\nrepos = ["not a repo"]\n')
        self.assertEqual(self.calls, [REPO])
        self.assertTrue(out[0].startswith("merger: swarm.toml org: each repo must be"), out)

    def test_a_goal_in_this_repo_makes_a_task_in_another_go(self):
        w = World()
        w.pr["head"]["repo"]["full_name"] = SCRATCH
        w.closes = [(SCRATCH, 9)]
        w.scope["blocked_by"] = []
        self.assertEqual(w.scope["parents"][0]["repo"], REPO)     # the Goal is here
        ctx = merger.Context(SCRATCH, OWNER, frozenset(AGENTS | {"productswarm-planner[bot]"}), ON, NOW)
        self.assertEqual(merger.make_plan([{"number": 70}], ctx, w.reader()),
                         [f"#70 {HEAD} {merger.GRANT}"])
        w.closes = [(REPO, 9)]                  # a PR there closing an issue here is a miss
        self.assertIn("the issue it closes is in another repo",
                      merger.make_plan([{"number": 70}], ctx, w.reader())[0])


class HomeShadow(unittest.TestCase):
    """#913: an [org] repo inherits the home repo's passed shadow bars."""

    @staticmethod
    def scratch_world():
        w = World()                       # a PR in scratch closing a scratch issue under a Goal here
        w.pr["head"]["repo"]["full_name"] = SCRATCH
        w.closes = [(SCRATCH, 9)]
        w.scope["blocked_by"] = []
        return w

    def run_scratch(self, own=(), home_items=(), protect=False):
        w, fw = self.scratch_world(), FakeWriter(list(own))
        if protect:
            w.protect()
        out = []
        def home_history():
            if isinstance(home_items, Exception):
                raise home_items
            return list(home_items)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "swarm.toml"
            p.write_text('[merger]\nmode = "live"\nmax_changed_lines = 100\n')
            code = merger.run(SCRATCH, manifest_path=p, reader=w.reader(), writer=fw.writer(w),
                              owner=lambda: OWNER,
                              authors=lambda: (AGENTS | {"productswarm-planner[bot]"}, None),
                              list_prs=lambda: [{"number": 70}], clock=lambda: T0, out=out.append,
                              home=REPO, home_history=home_history)
        return code, fw, out

    def test_home_passed_bar_carries_over(self):
        code, fw, out = self.run_scratch(home_items=[would(T0 - 60 * i, pr=i) for i in range(10)])
        self.assertEqual((code, fw.merges), (0, [(70, HEAD)]))
        self.assertIn(f"merger: the shadow bar (GOV-0027) is met by the home repo {REPO}", out)
        self.assertIn(f"merger: the standing grant's shadow bar (GOV-0034) is met by the home repo "
                      f"{REPO}", out)
        self.assertFalse(any("live acts as shadow" in x for x in out), out)

    def test_home_a_day_after_the_first_carries_over(self):
        _, fw, _ = self.run_scratch(home_items=[would(T0 - merger.SHADOW_SECONDS)])
        self.assertEqual(fw.merges, [(70, HEAD)])

    def test_home_not_passed_leaves_scratch_in_shadow(self):
        code, fw, out = self.run_scratch(home_items=[would(T0 - 60 * i, pr=i) for i in range(9)])
        self.assertEqual((code, fw.merges), (0, []))
        self.assertEqual(fw.posts, [(70, f"Would merge (standing grant) at {HEAD}.\n\n-- merger")])
        self.assertTrue(any("live acts as shadow" in x and "0 of 10" in x for x in out), out)
        self.assertFalse(any("met by the home repo" in x for x in out), out)

    def test_own_comments_still_count(self):
        _, fw, out = self.run_scratch(own=[would(T0 - 60 * i, pr=i) for i in range(10)])
        self.assertEqual(fw.merges, [(70, HEAD)])
        self.assertFalse(any("home repo" in x for x in out), out)     # home isn't needed

    def test_home_grant_bar_unmet_holds_only_grants(self):
        asks = [would(T0 - 60 * i, pr=i, kind="approved ask") for i in range(10)]
        _, fw, out = self.run_scratch(home_items=asks)
        self.assertEqual(fw.merges, [])
        self.assertIn(f"merger: the shadow bar (GOV-0027) is met by the home repo {REPO}", out)
        self.assertTrue(any("live acts as shadow for the standing grant" in x for x in out), out)
        _, fw, _ = self.run_scratch(home_items=asks, protect=True)
        self.assertEqual(fw.merges, [(70, HEAD)])

    def test_home_unreadable_fails_closed(self):
        code, fw, out = self.run_scratch(home_items=RuntimeError("gh failed"))
        self.assertEqual((code, fw.merges), (0, []))
        self.assertIn(f"merger: can't read the home repo {REPO}'s shadow comments (RuntimeError); "
                      f"this repo's own count holds", out)
        self.assertTrue(any("live acts as shadow" in x for x in out), out)

    def test_own_unreadable_still_holds_grants(self):
        w, fw = self.scratch_world(), FakeWriter()
        writer = fw.writer(w)
        def boom():
            raise RuntimeError("gh failed")
        fw.writer = lambda w: merger.Writer(history=boom, post=writer.post, merge=writer.merge,
                                            queue=writer.queue, enqueue=writer.enqueue)
        asks = [would(T0 - 60 * i, pr=i, kind="approved ask") for i in range(10)]
        out = []
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "swarm.toml"
            p.write_text('[merger]\nmode = "live"\nmax_changed_lines = 100\n')
            merger.run(SCRATCH, manifest_path=p, reader=w.reader(), writer=fw.writer(w),
                       owner=lambda: OWNER, authors=lambda: (AGENTS | {"productswarm-planner[bot]"}, None),
                       list_prs=lambda: [{"number": 70}], clock=lambda: T0, out=out.append,
                       home=REPO, home_history=lambda: asks)
        self.assertEqual(fw.merges, [])           # a standing grant: GOV-0034's bar isn't met
        self.assertTrue(any("standing grant" in x and "can't count" in x for x in out), out)

    def test_home_itself_reads_no_other_history(self):
        def never():
            raise AssertionError("read")
        w, fw = World(), FakeWriter()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "swarm.toml"
            p.write_text('[merger]\nmode = "live"\nmax_changed_lines = 100\n')
            merger.run(REPO, manifest_path=p, reader=w.reader(), writer=fw.writer(w),
                       owner=lambda: OWNER, authors=lambda: (AGENTS | {"productswarm-planner[bot]"}, None),
                       list_prs=lambda: [{"number": 70}], clock=lambda: T0, out=lambda x: None,
                       home=REPO, home_history=never)
        self.assertEqual(fw.merges, [])


class Paused(unittest.TestCase):
    """#892: a repo in swarm.toml's [org] paused gets no merge and no comment; the rest go on."""

    def run_live(self, repo, paused, w, fw, cmd="run"):
        out = []
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "swarm.toml"
            p.write_text('[merger]\nmode = "live"\nmax_changed_lines = 100\n'
                         f'[org]\nrepos = ["{SCRATCH}"]\npaused = {paused}\n')
            kw = dict(manifest_path=p, reader=w.reader(), owner=lambda: OWNER,
                      authors=lambda: (AGENTS | {"productswarm-planner[bot]"}, None),
                      list_prs=lambda: [{"number": 70}], out=out.append)
            if cmd == "plan":
                return merger.plan(repo, **kw), out
            code = merger.run(repo, writer=fw.writer(w), clock=lambda: T0, **kw)
        return code, out

    def test_a_paused_repo_gets_no_merge_and_an_unpaused_one_does(self):
        history = [would(T0 - 60 * i, pr=i) for i in range(10)]
        w, fw = World(), FakeWriter(history)
        code, out = self.run_live(REPO, f'["{REPO}"]', w, fw)
        self.assertEqual((code, fw.merges, fw.posts), (0, [], []))
        self.assertEqual(out, [f"merger: {REPO} is paused in swarm.toml's [org] paused (#892): "
                               f"nothing posted or merged"])
        w, fw = World(), FakeWriter(history)            # the same run with only scratch paused
        code, out = self.run_live(REPO, f'["{SCRATCH}"]', w, fw)
        self.assertEqual((code, fw.merges), (0, [(70, HEAD)]))
        code, out = self.run_live(SCRATCH, f'["{SCRATCH}"]', World(), fw)
        self.assertEqual((code, fw.merges), (0, [(70, HEAD)]))     # nothing more
        self.assertIn("paused", out[0])

    def test_plan_says_paused_and_considers_no_pr(self):
        code, out = self.run_live(REPO, f'["{REPO.upper()}"]', World(), None, cmd="plan")
        self.assertEqual(code, 0)
        self.assertEqual(out, [f"merger: {REPO} is paused in swarm.toml's [org] paused (#892): "
                               f"no PR is considered"])

    def test_a_bad_paused_list_pauses_every_repo(self):
        history = [would(T0 - 60 * i, pr=i) for i in range(10)]
        w, fw = World(), FakeWriter(history)
        code, out = self.run_live(REPO, '"scratch"', w, fw)
        self.assertEqual((code, fw.merges, fw.posts), (0, [], []))
        self.assertIn("every repo is until it is fixed", out[0])


if __name__ == "__main__":
    unittest.main()
