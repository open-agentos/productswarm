"""Tests for the Stop hook on loop-started runs (#148). Canned GitHub data; no network."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stophook  # noqa: E402
import swarm  # noqa: E402
from test_swarm import Base, S  # noqa: E402

R = "o/r"
OWNER = "boss"
T0 = 1_800_000_000.0                       # when the run started
BEFORE, AFTER = "2027-01-15T07:00:00Z", "2027-01-15T09:00:00Z"   # T0 is 08:00:00Z
SID = "11111111-2222-3333-4444-555555555555"
ME = {"builder": "productswarm-builder[bot]", "docs": "productswarm-docs[bot]",
      "reviewer": "productswarm-reviewer[bot]", "planner": "productswarm-planner[bot]"}


def issue(n, labels=("ready",), state="open"):
    return {"number": n, "state": state, "labels": [{"name": x} for x in labels]}


def labeled(name, who=OWNER):
    return {"event": "labeled", "label": {"name": name}, "actor": {"login": who}}


class FakeGitHub:
    """Canned REST data keyed by path (query string ignored), plus closing PRs per issue."""

    def __init__(self):
        self.data: dict[str, object] = {}
        self.closing: dict[int, list] = {}
        self.fail = False
        self.calls: list[str] = []

    def _look(self, path):
        self.calls.append(path)
        if self.fail:
            raise RuntimeError("gh api failed: could not resolve host")
        return self.data.get(path.split("?")[0])

    def gh(self):
        return stophook.GitHub(get=self._look, items=lambda p: list(self._look(p) or []),
                               closing_prs=lambda repo, n: self._look(f"closing/{n}") or [])

    def put(self, path, value):
        self.data[f"repos/{R}/{path}"] = value

    def closes(self, n, *prs):
        self.data[f"closing/{n}"] = [{"number": p} for p in prs]


class HookCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        (self.home / "launcher").mkdir()
        self.gh = FakeGitHub()

    def run_as(self, role, issue_n=None, pr=None, by="watch", called_by=None, daily=None,
               ask=None, ask_comment=None):
        e = swarm.Started(name=f"{role}-x", role=role, model="m", session_id=SID, started=T0,
                          issue=issue_n, pr=pr, by=by, called_by=called_by, daily=daily,
                          ask=ask, ask_comment=ask_comment)
        (self.home / "launcher" / "sessions.json").write_text(json.dumps([e.__dict__]))

    def decide(self, active=False):
        return stophook.decide({"session_id": SID, "stop_hook_active": active}, self.home, R,
                               self.gh.gh(), owner=lambda: OWNER)

    def assertBlocks(self, *words):
        out = self.decide()
        self.assertIsNotNone(out, "expected the stop to be blocked")
        self.assertEqual(out["decision"], "block")
        for w in words:
            self.assertIn(w, out["reason"])

    def assertAllows(self):
        self.assertIsNone(self.decide())

    # -- builder on an issue

    def builder_on(self, n=7, labels=("ready",), state="open", who=OWNER):
        self.run_as("builder", n)
        self.gh.put(f"issues/{n}", issue(n, labels, state))
        self.gh.put(f"issues/{n}/events", [labeled("ready", who)])


class BuilderTest(HookCase):
    def test_no_pr_blocks_naming_the_issue(self):
        self.builder_on()
        self.assertBlocks("No PR closes #7", "Open the PR for #7")

    def test_opened_pr_is_done(self):
        self.builder_on()
        self.gh.closes(7, 50)
        self.assertAllows()

    def test_ready_not_added_by_the_owner_is_done(self):
        self.builder_on(who="someone")
        self.assertAllows()

    def milestone_on(self, m="M1", plan=True, comments=()):
        import base64
        self.run_as("builder", 7)
        it = issue(7, ())
        it.update(user={"login": ME["planner"]}, body=f"**Milestone:** {m}\n**Waits on:** nothing.\n")
        self.gh.put("issues/7", it)
        self.gh.put("issues/7/events", [])
        self.gh.put("issues/7/comments", list(comments))
        if plan:
            text = "## M1: Report\n\n- **Done test:** x\n\n## M2: Merges (done)\n"
            self.gh.put("contents/PLAN.md", {"content": base64.b64encode(text.encode()).decode()})

    def test_milestone_issue_without_ready_blocks_until_its_pr(self):
        self.milestone_on()
        self.assertBlocks("No PR closes #7")
        self.gh.closes(7, 50)
        self.assertAllows()

    def test_milestone_issue_that_isnt_go_is_done(self):
        self.milestone_on("M2")                     # marked done
        self.assertAllows()
        self.milestone_on(plan=False)               # no PLAN.md on main
        self.gh.data.pop(f"repos/{R}/contents/PLAN.md", None)
        self.assertAllows()
        self.milestone_on(comments=[{"user": {"login": OWNER}, "body": "wait"}])   # veto
        self.assertAllows()

    def test_closed_issue_is_done(self):
        self.builder_on(state="closed")
        self.assertAllows()

    def test_opened_a_gov_question_is_done(self):
        self.builder_on()
        self.gh.put("issues", [{"number": 9, "created_at": AFTER, "user": {"login": ME["builder"]},
                                "body": "Blocks #7."}])
        self.assertAllows()

    def test_commented_on_a_gov_question_is_done(self):
        self.builder_on()
        self.gh.put("issues/comments", [{"issue_url": f"https://api.github.com/repos/{R}/issues/9",
                                         "created_at": AFTER, "user": {"login": ME["builder"]},
                                         "body": "This blocks #7 too."}])
        self.gh.put("issues/9", issue(9, ("gov:question",)))
        self.assertAllows()

    def test_another_builders_gov_question_does_not_count(self):
        # Same App, different session: its question names its own issue, not #7 (or #70).
        self.builder_on()
        self.gh.put("issues", [{"number": 9, "created_at": AFTER, "user": {"login": ME["builder"]},
                                "body": "Blocks #70."}])
        self.gh.put("issues/comments", [{"issue_url": f"https://api.github.com/repos/{R}/issues/9",
                                         "created_at": AFTER, "user": {"login": ME["builder"]},
                                         "body": "Also #71."}])
        self.gh.put("issues/9", issue(9, ("gov:question",)))
        self.assertBlocks("No PR closes #7", "naming #7")

    def test_gov_question_activity_before_the_run_or_by_others_does_not_count(self):
        self.builder_on()
        self.gh.put("issues", [{"number": 9, "created_at": BEFORE, "user": {"login": ME["builder"]},
                                "body": "#7"},
                               {"number": 10, "created_at": AFTER, "user": {"login": "someone"},
                                "body": "#7"}])
        self.gh.put("issues/comments", [
            {"issue_url": f"https://api.github.com/repos/{R}/issues/11", "created_at": AFTER,
             "user": {"login": ME["builder"]}, "body": "#7"}])
        self.gh.put("issues/11", issue(11, ("enhancement",)))     # not a gov:question
        self.assertBlocks("No PR closes #7")

    # -- blocked on an unfinished prerequisite (#184)

    def said_on_7(self, body, when=AFTER, who=ME["builder"]):
        self.gh.put("issues/7/comments", [{"created_at": when, "user": {"login": who},
                                           "body": body}])

    def test_no_pr_block_says_how_to_report_a_prerequisite(self):
        self.builder_on()
        self.assertBlocks("comment on #7 naming that issue")

    def test_commented_naming_an_open_prerequisite_is_done(self):
        self.builder_on()
        self.said_on_7("This needs `evals/results.md`, which #174 creates. Stopping until #174 is done.")
        self.gh.put("issues/174", issue(174, ()))
        self.assertAllows()

    def test_a_closed_prerequisite_does_not_count(self):
        self.builder_on()
        self.said_on_7("Blocked on #174.")
        self.gh.put("issues/174", issue(174, (), state="closed"))
        self.assertBlocks("No PR closes #7")

    def test_naming_an_open_pr_or_its_own_issue_does_not_count(self):
        self.builder_on()
        self.said_on_7("Working on #7; see PR #50.")
        self.gh.put("issues/7", {**issue(7), "body": ""})
        self.gh.put("issues/50", {**issue(50, ()), "pull_request": {"url": "x"}})
        self.assertBlocks("No PR closes #7")

    def test_prerequisite_comment_before_the_run_or_by_others_does_not_count(self):
        self.builder_on()
        self.gh.put("issues/174", issue(174, ()))
        self.said_on_7("Blocked on #174.", when=BEFORE)
        self.assertBlocks("No PR closes #7")
        self.said_on_7("Blocked on #174.", who="someone")
        self.assertBlocks("No PR closes #7")

    def test_links_and_other_repos_do_not_count(self):
        self.builder_on()
        self.gh.put("issues/174", issue(174, ()))
        self.said_on_7("See https://github.com/o/r/issues/7#174 and other/repo#174.")
        self.assertBlocks("No PR closes #7")


class RespondTest(HookCase):
    def setUp(self):
        super().setUp()
        self.run_as("builder", 7, pr=50)
        self.gh.put("pulls/50", {"state": "open", "head": {"sha": "h1"}})

    def review(self, state, sha="h1"):
        self.gh.put("pulls/50/reviews", [{"user": {"login": ME["reviewer"]}, "state": state,
                                          "commit_id": sha}])

    def test_changes_requested_at_head_blocks(self):
        self.review("CHANGES_REQUESTED")
        self.assertBlocks("PR #50", "Push a fix")

    def test_pushed_is_done(self):
        self.review("CHANGES_REQUESTED", sha="h0")      # the head moved on since the review
        self.assertAllows()

    def test_nothing_to_respond_to_is_done(self):
        self.review("COMMENTED")
        self.assertAllows()

    def test_replied_on_the_pr_is_done(self):
        self.review("CHANGES_REQUESTED")
        self.gh.put("pulls/50/comments", [{"user": {"login": ME["builder"]}, "created_at": AFTER}])
        self.assertAllows()

    def test_gov_question_naming_the_pr_is_done(self):
        self.review("CHANGES_REQUESTED")
        self.gh.put("issues", [{"number": 9, "created_at": AFTER, "user": {"login": ME["builder"]},
                                "body": "Raised while responding on #50."}])
        self.assertAllows()

    def test_merged_or_closed_pr_is_done(self):
        self.review("CHANGES_REQUESTED")
        self.gh.put("pulls/50", {"state": "closed", "head": {"sha": "h1"}})
        self.assertAllows()


class ReviewerTest(HookCase):
    def setUp(self):
        super().setUp()
        self.run_as("reviewer")
        self.gh.put("pulls", [
            {"number": 50, "draft": False, "created_at": BEFORE, "head": {"sha": "a"}},
            {"number": 51, "draft": False, "created_at": BEFORE, "head": {"sha": "b"}},
            {"number": 52, "draft": True, "created_at": BEFORE, "head": {"sha": "c"}},
            {"number": 53, "draft": False, "created_at": AFTER, "head": {"sha": "d"}},
        ])

    def test_unreviewed_prs_it_was_started_for_block(self):
        self.gh.put("pulls/50/reviews", [{"user": {"login": ME["reviewer"]}, "commit_id": "a"}])
        out = self.decide()
        self.assertIn("PR #51", out["reason"])
        for skipped in ("#50", "#52", "#53"):     # reviewed, draft, opened after the start
            self.assertNotIn(skipped, out["reason"])

    def test_every_pr_reviewed_is_done(self):
        self.gh.put("pulls/50/reviews", [{"user": {"login": ME["reviewer"]}, "commit_id": "a"}])
        # reviewed during the run, then pushed to: still counts for this run
        self.gh.put("pulls/51/reviews", [{"user": {"login": ME["reviewer"]}, "commit_id": "old",
                                          "submitted_at": AFTER}])
        self.assertAllows()

    def test_someone_elses_review_does_not_count(self):
        self.gh.put("pulls/50/reviews", [{"user": {"login": ME["reviewer"]}, "commit_id": "a"}])
        self.gh.put("pulls/51/reviews", [{"user": {"login": "boss"}, "commit_id": "b"}])
        self.assertBlocks("PR #51")



class ActionsReviewerTest(HookCase):
    """A reviewer run in Actions (#215): by="actions", on one PR."""
    def setUp(self):
        super().setUp()
        self.run_as("reviewer", pr=50, by="actions")
        self.gh.put("pulls/50", {"number": 50, "state": "open", "draft": False, "head": {"sha": "a"}})
        # another open, unreviewed PR: not this run's to review
        self.gh.put("pulls", [{"number": 51, "draft": False, "created_at": BEFORE, "head": {"sha": "b"}}])

    def test_its_pr_unreviewed_blocks(self):
        out = self.decide()
        self.assertIn("PR #50", out["reason"])
        self.assertNotIn("#51", out["reason"])

    def test_its_pr_reviewed_is_done_whatever_else_is_open(self):
        self.gh.put("pulls/50/reviews", [{"user": {"login": ME["reviewer"]}, "commit_id": "a"}])
        self.assertAllows()

    def test_its_pr_closed_or_draft_is_done(self):
        for pr in ({"state": "closed", "draft": False}, {"state": "open", "draft": True}):
            self.gh.put("pulls/50", {"number": 50, "head": {"sha": "a"}, **pr})
            self.assertAllows()

    def test_other_starters_still_get_no_hook(self):
        self.run_as("reviewer", pr=50, by=None)
        self.assertAllows()

class DocsTest(HookCase):
    def setUp(self):
        super().setUp()
        self.run_as("docs", 9)
        self.gh.put("issues/9", issue(9, ("gov:question", "gov:ruled")))
        self.gh.put("issues/9/events", [labeled("gov:ruled")])

    def test_no_record_pr_blocks(self):
        self.assertBlocks("Open the record PR for #9")

    def test_record_pr_opened_is_done(self):
        self.gh.closes(9, 60)
        self.assertAllows()

    def test_ruled_by_someone_else_is_done(self):
        self.gh.put("issues/9/events", [labeled("gov:ruled", "someone")])
        self.assertAllows()

    def test_commenting_on_its_own_question_is_not_blocked(self):
        self.gh.put("issues/comments", [{"issue_url": f"https://api.github.com/repos/{R}/issues/9",
                                         "created_at": AFTER, "user": {"login": ME["docs"]},
                                         "body": "Opening the record PR for #9."}])
        self.assertBlocks("record PR")

    def test_docs_on_an_answer_has_no_condition(self):
        self.gh.put("issues/9", issue(9, ("gov:question", "ready")))
        self.assertAllows()


class OtherRolesTest(HookCase):
    def test_planner_on_an_answer_has_no_condition(self):
        self.run_as("planner", 9)
        self.gh.put("issues/9", issue(9, ("gov:question", "ready")))
        self.assertAllows()
        self.assertEqual(self.gh.calls, [])

    def test_builder_on_its_own_answered_question_has_no_condition(self):
        self.run_as("builder", 9)
        self.gh.put("issues/9", issue(9, ("gov:question", "ready")))
        self.assertAllows()


class CallInTest(HookCase):
    def test_a_called_in_builder_needs_no_pr(self):
        # #520: a call-in run posts one comment; the [build] condition doesn't apply.
        self.run_as("builder", 7, called_by="the planner")
        self.gh.put("issues/7", issue(7))
        self.gh.put("issues/7/events", [labeled("ready")])
        self.assertAllows()
        self.assertEqual(self.gh.calls, [])

    def test_the_same_builder_not_called_in_still_blocks(self):
        self.builder_on()
        self.assertBlocks("No PR closes #7")


class DailyTest(HookCase):
    def test_a_daily_run_may_always_stop(self):
        # #588: the planner posts the report (and on Mondays the check-in); no PR, no condition.
        for what in ("the daily report", "the daily report and the Monday check-in"):
            with self.subTest(what=what):
                self.run_as("planner", 600, daily=what)
                self.assertAllows()
                self.assertEqual(self.gh.calls, [])

    def test_the_entry_keeps_daily_across_a_save(self):
        self.run_as("planner", 600, daily="the daily report")
        self.assertEqual(stophook.entry_for(self.home, SID).daily, "the daily report")


class AskTest(HookCase):
    def test_an_ask_run_may_always_stop_whatever_its_role(self):
        # #590: the asked role posts one comment on the report issue; no PR, no condition.
        for role in ("builder", "reviewer", "planner"):
            with self.subTest(role=role):
                self.run_as(role, 600, ask="why is M1 late?", ask_comment=901)
                self.assertAllows()
                self.assertEqual(self.gh.calls, [])

    def test_the_entry_keeps_the_ask_across_a_save(self):
        self.run_as("builder", 600, ask="why is M1 late?", ask_comment=901)
        e = stophook.entry_for(self.home, SID)
        self.assertEqual((e.ask, e.ask_comment), ("why is M1 late?", 901))


class GuardTest(HookCase):
    def setUp(self):
        super().setUp()
        self.builder_on()          # not done: no PR closes #7

    def test_stop_hook_active_allows(self):
        self.assertIsNone(self.decide(active=True))
        self.assertEqual(self.gh.calls, [])

    def test_allows_after_max_blocks(self):
        for _ in range(stophook.MAX_BLOCKS):
            self.assertIsNotNone(self.decide())
        self.assertIsNone(self.decide())
        got = json.loads((self.home / "launcher" / f"{SID}.stop.json").read_text())
        self.assertEqual(got, {"blocks": stophook.MAX_BLOCKS})

    def test_failed_github_read_allows(self):
        self.gh.fail = True
        self.assertIsNone(self.decide())
        self.assertIn("check failed", (self.home / "launcher" / "stophook.log").read_text())

    def test_owner_started_run_is_never_blocked(self):
        self.run_as("builder", 7, by=None)
        self.assertIsNone(self.decide())
        self.assertEqual(self.gh.calls, [])

    def test_unknown_session_is_never_blocked(self):
        (self.home / "launcher" / "sessions.json").unlink()
        self.assertIsNone(self.decide())


class SettingsTest(Base):
    """The launcher writes the Stop hook only into loop-started worktrees."""

    def settings(self, e):
        return json.loads((self.root / ".worktrees" / e.session_id / ".claude" / "settings.local.json")
                          .read_text())

    def stop_commands(self, e):
        return [h["command"] for g in self.settings(e)["hooks"]["Stop"] for h in g["hooks"]]

    def test_owner_started_worktrees_get_no_stop_hook(self):
        self.l.up([S("builder")])
        (e,) = self.l.load()
        self.assertFalse(any(stophook.MARK in c for c in self.stop_commands(e)))

    def test_launch_worktrees_get_no_stop_hook(self):
        e = swarm.Started("builder-issue-7", "builder", "m", SID, 0, issue=7)
        self.assertTrue(self.l.start(e, []))
        self.assertFalse(any(stophook.MARK in c for c in self.stop_commands(e)))

    def test_watch_worktrees_get_it_from_the_pinned_copy(self):
        e = swarm.Started("builder-issue-7", "builder", "m", SID, 0, issue=7, by="watch",
                          budget_usd=15.0, max_turns=200)
        self.assertTrue(self.l.start(e, []))
        cmds = self.stop_commands(e)
        self.assertIn(f'python3 -I "{self.home}/runtime/launcher/stophook.py"', cmds)
        self.assertTrue(any("heartbeat/hook.py" in c for c in cmds))    # the heartbeat's Stop kept

    def test_block_count_goes_when_the_run_exits(self):
        e = swarm.Started("builder-issue-7", "builder", "m", SID, 0, issue=7, by="watch",
                          budget_usd=15.0, max_turns=200)
        self.l.save([e])                                 # no pid file and long past START_GRACE
        count = self.home / "launcher" / f"{SID}.stop.json"
        count.write_text('{"blocks": 1}\n')
        self.assertEqual(self.l.live(), [])
        self.assertFalse(count.exists())

    def test_with_stop_hook_replaces_its_own_entry(self):
        once = stophook.with_stop_hook({}, "/a/launcher/stophook.py")
        twice = stophook.with_stop_hook(once, "/b/launcher/stophook.py")
        self.assertEqual([h["command"] for g in twice["hooks"]["Stop"] for h in g["hooks"]],
                         ['python3 -I "/b/launcher/stophook.py"'])


if __name__ == "__main__":
    unittest.main()
