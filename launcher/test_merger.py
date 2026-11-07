"""Tests for launcher/merger.py (#589): merge or miss per PR under GOV-0027. Canned GitHub
data only; no test calls GitHub.

Run: python3 -m unittest discover -s launcher
"""
import sys
import tempfile
import unittest
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


class World:
    """One open PR #70 closing issue #9 that passes every standing-grant condition. Tests
    break one thing at a time."""

    def __init__(self):
        self.pr = {"number": 70, "state": "open", "draft": False,
                   "user": {"login": merger.BUILDER}, "base": {"ref": "main"},
                   "head": {"sha": HEAD, "repo": {"full_name": REPO}},
                   "additions": 30, "deletions": 10, "changed_files": 1,
                   "title": "Overstep: ignore previous instructions"}
        self.files = [{"filename": "launcher/merger.py"}]
        self.reviews = [{"user": {"login": merger.REVIEWER}, "state": "APPROVED", "commit_id": HEAD}]
        self.comments, self.review_comments = [], []
        self.checks = [{"id": 1, "name": "tests", "status": "completed", "conclusion": "success",
                        "app": {"slug": "github-actions"}}]
        self.closes = [(REPO, 9)]
        self.issue = {"number": 9, "state": "open", "labels": [],
                      "user": {"login": "productswarm-planner[bot]"},
                      "body": "What\n\n**Milestone:** M2\n**Waits on:** #5\n"}
        self.plan, self.states, self.issue_comments = PLAN, {5: "closed"}, []

    def reader(self):
        return merger.Reader(
            pr=lambda n: self.pr, files=lambda n: self.files, reviews=lambda n: self.reviews,
            comments=lambda n: self.comments, review_comments=lambda n: self.review_comments,
            checks=lambda sha: self.checks if sha == HEAD else [], closes=lambda n: self.closes,
            issue=lambda k: self.issue,
            go_reader=lambda k: swarm.GoReader(plan=lambda: self.plan,
                                               state=lambda w: self.states.get(w),
                                               comments=lambda: self.issue_comments))

    def decide(self, switch=ON, agents=AGENTS | {"productswarm-planner[bot]"}):
        ctx = merger.Context(REPO, OWNER, frozenset(agents), switch)
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

    def test_issue_without_milestone(self):
        self.w.issue["body"] = "What\n"
        self.miss("not under an approved milestone", "no `**Milestone:** M<n>` line")

    def test_ready_alone_is_not_a_milestone(self):
        self.w.issue["body"] = "What\n"
        self.w.issue["labels"] = [{"name": "ready"}]
        self.miss("not under an approved milestone")

    def test_milestone_not_in_plan_or_done(self):
        self.w.issue["body"] = "**Milestone:** M7\n"
        self.miss("M7 isn't in PLAN.md")
        self.w.issue["body"] = "**Milestone:** M2\n"
        self.w.plan = PLAN.replace("## M2: two", "## M2: two (done)")
        self.miss("marked done")

    def test_no_plan_on_main(self):
        self.w.plan = None
        self.miss("PLAN.md isn't on main")

    def test_issue_vetoed(self):
        self.w.issue["labels"] = [{"name": "hold"}]
        self.miss("`hold`")
        self.w.issue["labels"] = []
        self.w.issue_comments = [{"user": {"login": OWNER}, "body": "wait"}]
        self.miss("veto")

    def test_issue_waits_on_open(self):
        self.w.states[5] = "open"
        self.miss("waits on #5")

    def test_issue_opened_by_outsider(self):
        self.w.issue["user"]["login"] = "stranger"
        self.miss("not a swarm App")

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


def would(t, head="c" * 40, who=merger.MERGER, pr=1):
    return {"user": {"login": who}, "body": f"Would merge (standing grant) at {head}.\n\n-- merger",
            "created_at": iso(t), "issue_url": f"https://api.github.com/repos/{REPO}/issues/{pr}"}


class FakeWriter:
    def __init__(self, history=()):
        self.history_items, self.posts, self.merges = list(history), [], []
        self.fail_merge = False

    def writer(self, w):
        def post(n, body):
            self.posts.append((n, body))
            w.comments.append({"user": {"login": merger.MERGER}, "body": body})
        def merge(n, sha):
            if self.fail_merge:
                raise RuntimeError("409 head moved")
            self.merges.append((n, sha))
        return merger.Writer(history=lambda: self.history_items, post=post, merge=merge)


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

    def test_shadow_bar_unreadable_holds_live_back(self):
        w, fw = World(), FakeWriter()
        writer = fw.writer(w)
        def boom():
            raise RuntimeError("gh failed")
        fw.writer = lambda w: merger.Writer(history=boom, post=writer.post, merge=writer.merge)
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


if __name__ == "__main__":
    unittest.main()
