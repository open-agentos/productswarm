"""Tests for launcher/trouble.py and `swarm trouble` (#803): per Goal and Area, progress, stuck
work, what waits on the owner and authority used. Synthetic fixtures stand in for cases that
haven't happened yet (a missed Goal date, a question open a week, a failed Area target)."""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import swarm  # noqa: E402
import trouble  # noqa: E402
import watch  # noqa: E402

swarm.dashboard()   # puts generate on the path, as gather() does

UTC = dt.timezone.utc
OWNER = "mattmcalister"
REPO = "o/r"
NOW = dt.datetime(2026, 11, 11, 18, 0, tzinfo=UTC)
REVIEWER = "productswarm-reviewer"     # as `gh pr list` shows it
HEAD = "a" * 40


def ago(hours: float) -> str:
    return (NOW - dt.timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def issue(n: int, *, kind: str | None = "Task", author: str = "productswarm-planner[bot]",
          labels: tuple[str, ...] = (), body: str = "", created: float = 10, pr: bool = False) -> dict:
    it = {"number": n, "title": f"issue {n}", "html_url": f"https://github.com/{REPO}/issues/{n}",
          "user": {"login": author}, "labels": [{"name": x} for x in labels], "body": body,
          "created_at": ago(created), "type": {"name": kind} if kind else None, "state": "open"}
    if pr:
        it["pull_request"] = {}
        it["html_url"] = f"https://github.com/{REPO}/pull/{n}"
    return it


def goal(n: int, body: str, kind: str = "Goal", author: str = OWNER) -> dict:
    return issue(n, kind=kind, author=author, body=body)


def under(g: int | None, blocked_by: tuple[int, ...] = ()) -> dict:
    parents = [{"repo": REPO, "number": g, "state": "open", "type": "Goal", "author": OWNER}] if g else []
    return {"author": "productswarm-planner[bot]", "type": "Task", "parents": parents, "deep": False,
            "blocked_by": [{"repo": REPO, "number": b, "state": "open"} for b in blocked_by],
            "blockers_complete": True}


def review(state: str, hours: float, commit: str = HEAD, author: str = REVIEWER, body: str = "") -> dict:
    return {"author": {"login": author}, "state": state, "submittedAt": ago(hours),
            "commit": {"oid": commit}, "body": body}


def pr(n: int, closes: int, *, author: str = "app/productswarm-builder", reviews=(), comments=(),
       files=("launcher/x.py",)) -> dict:
    return {"number": n, "title": f"pr {n}", "url": f"https://github.com/{REPO}/pull/{n}",
            "author": {"login": author}, "isDraft": False, "headRefOid": HEAD, "createdAt": ago(30),
            "reviews": list(reviews), "comments": list(comments), "files": [{"path": f} for f in files],
            "closingIssuesReferences": [{"number": closes}]}


def merged(n: int, closes: int, hours: float, by: str = "productswarm-merger",
           author: str = "app/productswarm-builder", body: str = "", comments=(), reviews=()) -> dict:
    return {"number": n, "title": f"pr {n}", "url": f"https://github.com/{REPO}/pull/{n}",
            "author": {"login": author}, "body": body, "mergedAt": ago(hours),
            "mergedBy": {"login": by}, "headRefOid": HEAD, "comments": list(comments),
            "reviews": list(reviews), "closingIssuesReferences": [{"number": closes}]}


def said(who: str, body: str, hours: float) -> dict:
    """A PR conversation comment as `gh pr list` shows it."""
    return {"author": {"login": who}, "createdAt": ago(hours), "body": body}


def left(reason: str, hours: float = 1, head: str = HEAD) -> dict:
    return said("productswarm-merger", f"Left for the owner at {head}: {reason}.\n\n-- merger", hours)


def comment(n: int, body: str, hours: float = 2, author: str = OWNER, on_pr: bool = False) -> dict:
    kind = "pull" if on_pr else "issues"
    return {"user": {"login": author}, "body": body, "created_at": ago(hours),
            "issue_url": f"https://api.github.com/repos/{REPO}/issues/{n}",
            "html_url": f"https://github.com/{REPO}/{kind}/{n}#issuecomment-1"}


M1 = goal(1, "**Criteria**\n- [ ] a daily report posts without the owner starting it\n"
             "- [x] each Monday in that run has its check-in\n- [ ] something nobody measures\n\n"
             "**Date:** when ready\n")


def data(**kw) -> trouble.Data:
    base = dict(repo=REPO, owner=OWNER, now=NOW, issues=[M1], scopes={},
                switches={"asks": True, "call_ins": True, "research": True}, report_issue=249)
    base.update(kw)
    return trouble.Data(**base)


def scope(r: dict, n: int = 1) -> dict:
    return next(s for s in r["scopes"] if s["ref"] == f"{REPO}#{n}")


class Progress(unittest.TestCase):
    def test_ticked_met_unticked_unmeasured_never_on_track(self):
        p = scope(trouble.report(data()))["progress"]
        self.assertEqual([c["status"] for c in p], ["unmeasured", "met", "unmeasured"])
        self.assertNotIn("on track", json.dumps(p))

    def test_daily_report_shown_once_not_a_streak(self):
        # GOV-0040: one report [daily] started meets M1's criterion; no "N of 5" or "N of 10".
        mon, fri, thu = dt.date(2026, 11, 9), dt.date(2026, 11, 6), dt.date(2026, 11, 5)
        rows = [{"day": mon, "posted": None, "by": None, "ran": False},
                {"day": fri, "posted": NOW, "by": "by hand", "ran": False},
                {"day": thu, "posted": NOW, "by": "[daily]", "ran": True}]
        p = scope(trouble.report(data(daily_rows=rows)))["progress"]
        self.assertEqual(p[0]["status"], "met")
        self.assertIn("Thu 2026-11-05", p[0]["detail"])
        self.assertNotRegex(p[0]["detail"], r"\d+ of \d+")
        p = scope(trouble.report(data(daily_rows=rows[:2])))["progress"]
        self.assertEqual(p[0]["status"], "progress")
        self.assertNotRegex(p[0]["detail"], r"\d+ of \d+")

    def test_missed_goal_date(self):
        g = goal(2, "**Criteria**\n- [ ] ship it\n\n**Date:** 2026-11-04\n")
        s = scope(trouble.report(data(issues=[g])), 2)
        self.assertEqual(s["date"], "2026-11-04")
        self.assertTrue(s["date_missed"])
        g = goal(2, "**Criteria**\n- [ ] ship it\n\n**Date:** 2026-12-04\n")
        self.assertFalse(scope(trouble.report(data(issues=[g])), 2)["date_missed"])

    def test_area_targets_and_failed_target(self):
        a = goal(3, "**Area:** the host.\n\n**Target:** the host does the work.\n- checks run on the host\n"
                    "- a nightly backup exists for each of the last 7 days\n\n**Why:** x\n", kind="Area")
        failing = (re.compile(r"nightly backup"), lambda m, d: ("failing", "no backup on 2026-11-09"))
        s = scope(trouble.report(data(issues=[a]), measures=[failing]), 3)
        self.assertEqual([(c["criterion"][:6], c["status"]) for c in s["progress"]],
                         [("checks", "unmeasured"), ("a nigh", "failing")])
        self.assertNotIn("delivered", json.dumps(s))

    def test_area_target_without_bullets(self):
        a = goal(3, "**Target:** every check runs on the host\n\nmore", kind="Area")
        self.assertEqual(trouble.criteria(a["body"], "Area"), [("every check runs on the host", False)])

    def test_m2_merge_share_and_reverts_from_swarm_merges(self):
        g = goal(2, "**Criteria**\n- [ ] over half of a week's merges happen without the owner's click\n"
                    "- [ ] no unreviewed revert in that week\n")
        enq = said("productswarm-merger", f"Enqueued under standing grant (GOV-0027) at {HEAD}.", 3)
        week = [merged(10, 6, 2), merged(11, 6, 3, by="github-merge-queue", comments=[enq]),
                merged(12, 6, 4, by=OWNER), merged(9, 6, 24 * 5, by=OWNER)]   # Nov 6: last week
        p = scope(trouble.report(data(issues=[g])), 2)["progress"]
        self.assertEqual([c["status"] for c in p], ["unmeasured", "unmeasured"])
        p = scope(trouble.report(data(issues=[g], week_merges=week)), 2)["progress"]
        self.assertEqual([c["status"] for c in p], ["met", "met"])
        self.assertIn("2 of 3 merges this week", p[0]["detail"])
        week.append(merged(13, 6, 1, by=OWNER, body="Reverts o/r#10"))
        p = scope(trouble.report(data(issues=[g], week_merges=week)), 2)["progress"]
        self.assertEqual([c["status"] for c in p], ["progress", "failing"])
        self.assertIn("PR #13", p[1]["detail"])
        week[-1]["reviews"] = [review("APPROVED", 1.5)]
        p = scope(trouble.report(data(issues=[g], week_merges=week)), 2)["progress"]
        self.assertEqual(p[1]["status"], "met")

    def test_m4_acts_are_counted_never_met_or_failing(self):
        g = goal(4, "**Criteria**\n- [ ] my acts in the drill are counted and reported by "
                    "`swarm acts`, with no budget\n")
        day = {"status": "counted", "count": 2, "other": 0, "c_team": True}
        busy = {"status": "counted", "count": 40, "other": 12, "c_team": False}
        today = {"status": "in progress", "count": 7, "other": 1, "c_team": None}
        p = scope(trouble.report(data(issues=[g], owner_days=[today, busy] + [day] * 9)), 4)["progress"]
        self.assertEqual(p[0]["status"], "counted")              # 40 in a day still isn't failing
        self.assertEqual(p[0]["detail"], "58 owner acts on 10 counted working days, 12 not C-team "
                                         "(swarm acts)")         # today, unfinished, is left out
        p = scope(trouble.report(data(issues=[g], owner_days=[day] * 11)), 4)["progress"]
        self.assertEqual(p[0]["status"], "counted")              # 11 quiet days still aren't met
        self.assertEqual(scope(trouble.report(data(issues=[g])), 4)["progress"][0]["status"], "unmeasured")

    def test_m4_reports_days_not_counted(self):
        g = goal(4, "- [ ] my acts are counted for each of the 10 working days\n")
        day = {"status": "counted", "count": 1, "other": 1, "c_team": False}
        gap = {"status": "not counted", "count": None, "other": None, "c_team": None}
        p = scope(trouble.report(data(issues=[g], owner_days=[day] * 2 + [gap] + [day] * 7)), 4)["progress"]
        self.assertEqual((p[0]["status"], p[0]["detail"]),
                         ("counted", "9 owner acts on 9 counted working days, 9 not C-team; "
                                     "1 not counted (swarm acts)"))

    def test_m4_unmeasured_on_an_empty_swarm_db(self):
        import acts
        g = goal(4, "- [ ] my acts in the drill are counted and reported by `swarm acts`\n")
        with tempfile.TemporaryDirectory() as tmp:
            days = acts.per_day(acts.stored(Path(tmp)),
                                swarm.working_days(NOW.date(), swarm.ACTS_DAYS + 1),
                                dt.timezone.utc, NOW, acts.backfilled(Path(tmp)))
        self.assertEqual({d["status"] for d in days[1:]}, {"not counted"})
        p = scope(trouble.report(data(issues=[g], owner_days=days)), 4)["progress"]
        self.assertEqual((p[0]["status"], p[0]["detail"]), ("unmeasured", "no working day counted yet (swarm acts)"))

    def test_only_owner_opened_scopes(self):
        r = trouble.report(data(issues=[M1, goal(9, "- [ ] x", author="productswarm-planner[bot]")]))
        self.assertEqual([s["ref"] for s in r["scopes"]], [f"{REPO}#1"])


class Stuck(unittest.TestCase):
    def test_rule1_changes_on_a_pr_no_role_opened(self):
        p = pr(704, 692, author="someone", reviews=[review("CHANGES_REQUESTED", 13.5)])
        r = trouble.report(data(issues=[M1, issue(692)], scopes={692: under(1)}, prs=[p]))
        [x] = scope(r)["stuck"]
        self.assertEqual((x["kind"], x["ref"], x["age_hours"]), ("changes-no-restart", "PR #704", 13.5))
        self.assertIn("no trigger restarts the author", x["reason"])

    def test_rule1_analyst_pr_is_restarted_by_respond(self):
        # #704's shape: since #738, [respond] restarts the analyst on its own PR.
        p = pr(704, 692, author="app/productswarm-analyst", reviews=[review("CHANGES_REQUESTED", 13.5)])
        r = trouble.report(data(issues=[M1, issue(692)], scopes={692: under(1)}, prs=[p]))
        self.assertEqual(scope(r)["stuck"] + scope(r)["waiting"], [])

    def test_rule1_builder_pr_is_restarted_by_respond(self):
        p = pr(5, 692, reviews=[review("CHANGES_REQUESTED", 2)])
        r = trouble.report(data(issues=[M1, issue(692)], scopes={692: under(1)}, prs=[p]))
        self.assertEqual(scope(r)["stuck"] + scope(r)["waiting"], [])

    def test_rule1_overstep_waits_then_stuck_once_owner_answers(self):
        # An overstep is a COMMENTED review with Authority: fail; [ruling] starts no role on a
        # PR no role's App opened.
        rv = review("COMMENTED", 20, body="**Authority:** fail")
        p = pr(679, 661, author="someone", reviews=[rv])
        r = trouble.report(data(issues=[M1, issue(661)], scopes={661: under(1)}, prs=[p]))
        self.assertEqual(scope(r)["stuck"], [])
        [w] = scope(r)["waiting"]
        self.assertIn("overstep", w["reason"])
        p["comments"].append(said(OWNER, "fine", 13.5))
        r = trouble.report(data(issues=[M1, issue(661)], scopes={661: under(1)}, prs=[p]))
        [x] = scope(r)["stuck"]
        self.assertEqual((x["ref"], x["age_hours"]), ("PR #679", 13.5))
        self.assertIn("answered", x["reason"])
        self.assertIn("[ruling] restarts only builder and planner and docs", x["reason"])
        self.assertEqual(scope(r)["waiting"], [])

    def test_rule1_overstep_679_shape(self):
        # #679: a builder PR, the reviewer's COMMENTED review at head says Authority: fail.
        rv = review("COMMENTED", 27, body="Overstep: mounts .git read-write\n\n**Authority:** fail")
        p = pr(679, 661, reviews=[rv], comments=[said("productswarm-reviewer", "Overstep: x", 27)])
        d = dict(issues=[M1, issue(661)], scopes={661: under(1)}, prs=[p])
        [w] = scope(trouble.report(data(**d)))["waiting"]
        self.assertEqual((w["ref"], w["reason"], w["age_hours"]), ("PR #679", "overstep: needs the owner", 27))
        p["comments"].append(said(OWNER, "don't mount the shared .git read-write", 23))
        r = trouble.report(data(**d))
        self.assertEqual(scope(r)["stuck"] + scope(r)["waiting"], [])     # [ruling] starts the builder
        p["comments"].append(said("productswarm-builder", "Which mount do you want?", 22))
        r = trouble.report(data(**d))
        [w] = scope(r)["waiting"]
        self.assertIn("the builder replied", w["reason"])
        self.assertEqual(scope(r)["stuck"], [])

    def test_rule1_overstep_on_pr_closing_two_issues_is_stuck_once_answered(self):
        p = pr(5, 661, reviews=[review("COMMENTED", 5, body="Authority: fail")],
               comments=[said(OWNER, "ok", 4)])
        p["closingIssuesReferences"].append({"number": 662})
        [x] = scope(trouble.report(data(issues=[M1, issue(661)], scopes={661: under(1)}, prs=[p])))["stuck"]
        self.assertIn("closes 2 issues", x["reason"])

    def test_rule1_restart_roles_come_from_watch(self):
        p = pr(704, 692, author="app/productswarm-analyst", reviews=[review("CHANGES_REQUESTED", 13.5)])
        d = dict(issues=[M1, issue(692)], scopes={692: under(1)}, prs=[p])
        self.assertEqual(scope(trouble.report(data(**d)))["stuck"], [])
        old = watch.RESPOND_ROLES
        try:
            watch.RESPOND_ROLES = ("builder",)
            r = trouble.report(data(**d))
        finally:
            watch.RESPOND_ROLES = old
        self.assertEqual(len(scope(r)["stuck"]), 1)

    def test_rule1_past_round_bound_waits_then_stuck(self):
        rvs = [review("CHANGES_REQUESTED", h, commit=c) for h, c in ((9, "b" * 40), (6, "c" * 40))]
        p = pr(5, 692, reviews=[*rvs, review("CHANGES_REQUESTED", 2)])
        d = dict(issues=[M1, issue(692)], scopes={692: under(1)}, prs=[p])
        [w] = scope(trouble.report(data(**d)))["waiting"]
        self.assertIn("3 times", w["reason"])
        p["comments"].append(said(OWNER, "try again", 1))
        [x] = scope(trouble.report(data(**d)))["stuck"]
        self.assertIn("answered", x["reason"])

    def test_rule1_push_since_review_is_not_stuck(self):
        p = pr(704, 692, author="app/productswarm-analyst",
               reviews=[review("CHANGES_REQUESTED", 13.5, commit="b" * 40)])
        r = trouble.report(data(issues=[M1, issue(692)], scopes={692: under(1)}, prs=[p]))
        self.assertEqual(scope(r)["stuck"], [])

    def test_rule2_merged_issue_still_open(self):
        r = trouble.report(data(issues=[M1, issue(663)], scopes={663: under(1)},
                                merged=[merged(700, 663, 30), merged(701, 999, 30)]))
        [x] = scope(r)["stuck"]
        self.assertEqual((x["kind"], x["ref"], x["pr"]), ("merged-issue-open", "#663", 700))

    def test_rule3_waits_on_unplanned_issue(self):
        gate = issue(773, body="**Waits on:** #786.")
        r = trouble.report(data(issues=[M1, gate, issue(786, created=36), issue(800)],
                                scopes={773: under(1, blocked_by=(800,)), 786: under(None),
                                        800: under(None)}))
        stuck = scope(r)["stuck"]
        self.assertEqual([(x["ref"], x["waited_on_by"]) for x in stuck], [("#786", 773), ("#800", 773)])
        self.assertEqual(stuck[0]["age_hours"], 36)

    def test_rule3_planned_blocker_is_not_stuck(self):
        r = trouble.report(data(issues=[M1, issue(773, body="**Waits on:** #786."), issue(786)],
                                scopes={773: under(1), 786: under(1)}))
        self.assertEqual(scope(r)["stuck"], [])

    def test_unheard_commands(self):
        issues = [M1, issue(5), issue(6), issue(7, pr=True), issue(249, kind=None), issue(8)]
        comments = [comment(7, "Ask: analyst: why?", on_pr=True),
                    comment(7, "Call in: planner: look", on_pr=True),
                    comment(6, "Call in: planner: look"),          # not ready, under no Goal
                    comment(5, "Call in: planner: look"),          # under M1: heard
                    comment(249, "Ask: builder: what?"),           # heard
                    comment(8, "Research: what?", author="someone"),   # not the owner's
                    comment(99, "Ask: builder: on a closed issue")]
        r = trouble.report(data(issues=issues, scopes={5: under(1), 6: under(None), 8: under(None)},
                                comments=comments))
        got = [(x["ref"], x["reason"]) for x in r["outside"]["stuck"]]
        self.assertEqual(len(got), 3)
        self.assertTrue(any(ref == "PR #7" and "report issue #249" in why for ref, why in got))
        self.assertTrue(any(ref == "PR #7" and "not PRs" in why for ref, why in got))
        self.assertTrue(any(ref == "#6" and "neither `ready`" in why for ref, why in got))

    def test_rule4_approved_by_the_owner_but_conflicting_839(self):
        # PR #839: the reviewer approved at head, the merger left it for the owner (a protected
        # path), the owner approved at head 53 minutes later, and it conflicts with main.
        why = "approved ask: touches `governance/INDEX.md`, and mattmcalister hasn't approved at head"
        p = pr(839, 731, reviews=[review("APPROVED", 3), review("APPROVED", 2.1, author=OWNER)],
               comments=[left(why, 3)], files=("governance/INDEX.md",))
        p["mergeable"] = "CONFLICTING"
        r = trouble.report(data(issues=[M1, issue(731)], scopes={731: under(1)}, prs=[p]))
        self.assertEqual(scope(r)["waiting"], [])
        [x] = scope(r)["stuck"]
        self.assertEqual((x["kind"], x["ref"], x["age_hours"]), ("conflict", "PR #839", 2.1))
        self.assertIn(f"approved at head by the reviewer and @{OWNER}", x["reason"])
        self.assertIn("conflicts with main", x["reason"])
        self.assertIn("nothing will start a fix", x["reason"])

    def test_rule4_owner_approval_after_left_no_longer_waits(self):
        p = pr(839, 731, reviews=[review("APPROVED", 3), review("APPROVED", 2, author=OWNER)],
               comments=[left("the owner hasn't approved at head", 2.5)])
        p["mergeable"] = "MERGEABLE"
        r = trouble.report(data(issues=[M1, issue(731)], scopes={731: under(1)}, prs=[p]))
        self.assertEqual(scope(r)["stuck"] + scope(r)["waiting"], [])     # the merger acts next
        p["reviews"][-1] = review("APPROVED", 2, author=OWNER, commit="b" * 40)   # an older head's
        [w] = scope(trouble.report(data(issues=[M1, issue(731)], scopes={731: under(1)}, prs=[p])))["waiting"]
        self.assertIn("the merger left it for the owner", w["reason"])

    def test_rule4_conflict_without_the_owner(self):
        p = pr(5, 731, reviews=[review("APPROVED", 4)])
        p["mergeable"] = "CONFLICTING"
        [x] = scope(trouble.report(data(issues=[M1, issue(731)], scopes={731: under(1)}, prs=[p])))["stuck"]
        self.assertIn("approved at head by the reviewer, but", x["reason"])

    def test_rule5_quiet_hand_started_session_773(self):
        # #773: the analyst run, started by hand, posted nothing for 75 minutes.
        s = {"name": "analyst-issue-773", "role": "analyst", "issue": 773, "pr": None, "started": ago(3)}
        posted = comment(773, "Starting the gate run.", hours=1.25, author="productswarm-analyst[bot]")
        d = dict(issues=[M1, issue(773)], scopes={773: under(1)}, sessions=[s], comments=[posted])
        [x] = scope(trouble.report(data(**d)))["stuck"]
        self.assertEqual((x["kind"], x["ref"], x["session"], x["age_hours"]),
                         ("quiet-session", "#773", "analyst-issue-773", 1.2))
        self.assertIn("posted nothing for 75 min", x["reason"])
        self.assertIn("last posted at 2026-11-11 16:45 UTC", x["reason"])
        self.assertIn(f"flagged after {trouble.QUIET_MINUTES} min", x["reason"])
        d["comments"] = [comment(773, "Halfway.", hours=0.5, author="productswarm-analyst[bot]")]
        self.assertEqual(scope(trouble.report(data(**d)))["stuck"], [])   # posted 30 min ago
        d["comments"] = [comment(773, "Halfway.", hours=0.5)]               # the owner's, not its own
        [x] = scope(trouble.report(data(**d)))["stuck"]
        self.assertIn("nothing since it started at 2026-11-11 15:00 UTC", x["reason"])

    def test_rule5_post_on_its_pr_counts_and_finished_work_is_skipped(self):
        s = {"name": "builder-issue-773", "role": "builder", "issue": 773, "pr": None, "started": ago(3)}
        p = pr(900, 773)
        on_pr = comment(900, "Pushed a fix.", hours=0.2, author="productswarm-builder[bot]", on_pr=True)
        d = dict(issues=[M1, issue(773)], scopes={773: under(1)}, sessions=[s], prs=[p], comments=[on_pr])
        self.assertEqual(scope(trouble.report(data(**d)))["stuck"], [])
        d.update(prs=[], comments=[], merged=[merged(900, 773, 1)])      # its PR merged: work over
        self.assertEqual([x["kind"] for x in scope(trouble.report(data(**d)))["stuck"]], ["merged-issue-open"])
        d.update(merged=[], issues=[M1])                                  # its issue closed
        self.assertEqual(trouble.report(data(**d))["outside"]["stuck"], [])
        s.update(issue=None, pr=839)                                      # a PR session, PR gone
        self.assertEqual(trouble.report(data(**d))["outside"]["stuck"], [])

    def test_rule5_session_on_another_repo_is_not_this_repo_s_issue(self):
        # A session on open-agentos/other-repo#773 isn't working on this repo's #773 (#829).
        e = swarm.Started(name="builder-other-773", role="builder", model="m", session_id="s",
                          issue=773, repo="o/other", started=(NOW - dt.timedelta(hours=3)).timestamp())

        class L:
            def running(self):
                return [e]

            def state(self, _):
                return "running"
        [s] = trouble.hand_sessions(L())
        self.assertEqual(s["repo"], "o/other")
        d = dict(issues=[M1, issue(773)], scopes={773: under(1)}, sessions=[s])
        self.assertEqual(scope(trouble.report(data(**d)))["stuck"], [])
        for this in (None, REPO):                                         # this repo's: still flagged
            s["repo"] = this
            [x] = scope(trouble.report(data(**d)))["stuck"]
            self.assertEqual((x["kind"], x["ref"]), ("quiet-session", "#773"))

    def test_rule5_pr_session_counts_only_posts_on_its_pr(self):
        s = {"name": "builder-pr-900", "role": "builder", "issue": None, "pr": 900, "started": ago(3)}
        elsewhere = comment(12, "On another issue.", hours=0.2, author="productswarm-builder[bot]")
        d = dict(issues=[M1, issue(773), issue(12)], scopes={773: under(1), 12: under(1)},
                 sessions=[s], prs=[pr(900, 773)], comments=[elsewhere])
        [x] = trouble.report(data(**d))["outside"]["stuck"]
        self.assertEqual((x["kind"], x["ref"]), ("quiet-session", "builder-pr-900"))
        d["comments"] = [comment(900, "Pushed.", hours=0.2, author="productswarm-builder[bot]", on_pr=True)]
        self.assertEqual(trouble.report(data(**d))["outside"]["stuck"], [])

    def test_rule6_stopped_because_next_stage_has_no_issue_786(self):
        stop = comment(786, "Started on this, and stopping without code.\n\n- **Stage 2** (a clone per "
                            "repo) has no issue yet. The planner said it would open one.\n\n-- builder",
                       hours=2.2, author="productswarm-builder[bot]")
        d = dict(issues=[M1, issue(786)], scopes={786: under(1)}, comments=[stop])
        [x] = scope(trouble.report(data(**d)))["stuck"]
        self.assertEqual((x["kind"], x["ref"], x["age_hours"]), ("stopped-no-issue", "#786", 2.2))
        self.assertIn("the builder stopped: the next piece it needs has no issue yet", x["reason"])
        self.assertIn("nothing will start it", x["reason"])
        # Stage 2 opened as #853, naming #786: nothing is stuck any more.
        d["issues"] = [M1, issue(786), issue(853, created=1, body="Stage 2 of #786 (#820).")]
        self.assertEqual(scope(trouble.report(data(**d)))["stuck"], [])

    def test_rule6_only_a_role_s_last_word_without_a_pr(self):
        stop = comment(786, "Stage 2 isn't opened, so I stopped.", hours=2, author="productswarm-builder[bot]")
        base = dict(issues=[M1, issue(786)], scopes={786: under(1)})
        later = comment(786, "Opened it.", hours=1)
        self.assertEqual(scope(trouble.report(data(**base, comments=[stop, later])))["stuck"], [])
        merger = comment(786, "Stage 2 has no issue yet.", hours=2, author="productswarm-merger[bot]")
        self.assertEqual(scope(trouble.report(data(**base, comments=[merger])))["stuck"], [])
        self.assertEqual(scope(trouble.report(data(**base, comments=[stop], prs=[pr(900, 786)])))["stuck"], [])
        plain = comment(786, "Stopping: waits on #12.", hours=2, author="productswarm-builder[bot]")
        self.assertEqual(scope(trouble.report(data(**base, comments=[plain])))["stuck"], [])

    def test_switch_off_is_unheard(self):
        r = trouble.report(data(issues=[M1, issue(249, kind=None)], comments=[comment(249, "Ask: builder: x")],
                                switches={"asks": False}))
        [x] = r["outside"]["stuck"]
        self.assertIn("asks are off", x["reason"])


class Waiting(unittest.TestCase):
    def test_question_open_a_week(self):
        q = issue(731, kind=None, labels=("gov:question",), created=24 * 8)
        r = trouble.report(data(issues=[M1, q, issue(732, kind=None, labels=("gov:question", "ready"))]))
        [x] = r["outside"]["waiting"]
        self.assertEqual((x["kind"], x["ref"], x["age_hours"]), ("question", "#731", 192))

    def test_untriaged(self):
        r = trouble.report(data(issues=[M1, issue(731, created=36), issue(5, labels=("ready",)),
                                        issue(6, author=OWNER), issue(7)],
                                scopes={7: under(1)}))
        self.assertEqual([x["ref"] for x in r["outside"]["waiting"]], ["#731"])

    def test_approved_prs_the_merger_left_for_any_reason(self):
        why = "it touches a protected path (ops/x) and the owner hasn't approved at head"
        prs = [pr(796, 5, files=("ops/x",), reviews=[review("APPROVED", 2)], comments=[left(why, 1.5)]),
               pr(797, 5, reviews=[review("APPROVED", 2)],
                  comments=[left("the `tests` check failed at head", 1)]),
               pr(798, 5, reviews=[review("APPROVED", 2)])]                 # merger hasn't judged it
        r = trouble.report(data(issues=[M1, issue(5)], scopes={5: under(1)}, prs=prs))
        got = [(x["ref"], x["reason"], x["age_hours"]) for x in scope(r)["waiting"]]
        self.assertEqual(got, [
            ("PR #796", f"approved at head; the merger left it for the owner: {why}", 1.5),
            ("PR #797", "approved at head; the merger left it for the owner: the `tests` check failed at head", 1)])

    def test_left_is_read_at_head_and_superseded(self):
        old = left("an `Overstep:` finding is on the PR", 3, head="b" * 40)
        would = said("productswarm-merger", f"Would merge (approved ask) at {HEAD}.\n\n-- merger", 0.5)
        p = pr(796, 5, reviews=[review("APPROVED", 2)], comments=[old])
        d = dict(issues=[M1, issue(5)], scopes={5: under(1)}, prs=[p])
        self.assertEqual(scope(trouble.report(data(**d)))["waiting"], [])      # an older head's
        p["comments"] += [left("the owner hasn't approved at head", 1), would]
        self.assertEqual(scope(trouble.report(data(**d)))["waiting"], [])      # superseded
        p["comments"].append(said(OWNER, f"Left for the owner at {HEAD}: fake.", 0.2))
        self.assertEqual(scope(trouble.report(data(**d)))["waiting"], [])      # not the merger


class Authority(unittest.TestCase):
    def test_merges_by_the_merger_and_call_ins_only(self):
        enq = said("productswarm-merger", f"Enqueued under standing grant (GOV-0027) at {HEAD}.", 3)
        r = trouble.report(data(
            issues=[M1, issue(5)], scopes={5: under(1), 6: under(1)},
            merged=[merged(10, 6, 2, body="Default per GOV-0031."),
                    merged(11, 6, 2, by=OWNER, author="app/productswarm-docs", body="per GOV-0027"),
                    merged(12, 6, 30),
                    merged(13, 6, 2, by="github-merge-queue", comments=[enq])],
            comments=[comment(5, "Call in: analyst: check", author="productswarm-planner[bot]")]))
        got = sorted((x["kind"], x["ref"]) for x in scope(r)["authority"])
        self.assertEqual(got, [("call-in", "#5"), ("grant", "PR #10"), ("grant", "PR #13")])


class Spend(unittest.TestCase):
    def test_reported_never_flagged(self):
        spend = {"today": 1.234, "month": 500.0, "unscoped": 0.0, "no_cost": 0,
                 "spent": {f"{REPO}#1": 99.999}}
        r = trouble.report(data(spend=spend))
        self.assertEqual(scope(r)["spend_usd"], 100.0)
        self.assertEqual(r["spend"]["month_usd"], 500.0)
        self.assertEqual(scope(r)["stuck"] + scope(r)["waiting"], [])

    def test_unread_spend_is_none(self):
        r = trouble.report(data())
        self.assertIsNone(scope(r)["spend_usd"])
        self.assertIsNone(r["spend"])


class Cli(unittest.TestCase):
    def test_json_and_text(self):
        class L:
            lines: list[str] = []

            def out(self, s):
                self.lines.append(s)
        d = data(issues=[M1, issue(731, created=36)])
        launcher = L()
        self.assertEqual(swarm.trouble(launcher, REPO, as_json=True, owner=OWNER, read=lambda *a: d), 0)
        r = json.loads(launcher.lines[-1])
        self.assertEqual(r["scopes"][0]["ref"], f"{REPO}#1")
        self.assertEqual(swarm.trouble(launcher, REPO, owner=OWNER, read=lambda *a: d), 0)
        self.assertIn("#731  no label", launcher.lines[-1])
        self.assertIn("[unmeasured] something nobody measures", launcher.lines[-1])

    def test_parser_knows_trouble(self):
        with self.assertRaises(SystemExit) as e:
            swarm.main(["trouble", "--help"])
        self.assertEqual(e.exception.code, 0)



class GatherWithoutActsTest(unittest.TestCase):
    """#903: the desk's build reads the report without the owner-acts sync."""

    def test_no_acts_sync_and_says_so(self):
        from unittest import mock
        import acts
        fake = mock.Mock()
        fake.gh_items.return_value = []
        fake.gh_json.return_value = []
        with tempfile.TemporaryDirectory() as home, \
                mock.patch.object(swarm, "dashboard", return_value=fake), \
                mock.patch.object(swarm, "gh_merged", return_value=[]), \
                mock.patch.object(watch, "gh_recent_comments", return_value=[]), \
                mock.patch.object(watch, "gh_comments", return_value=[]), \
                mock.patch.object(acts, "refresh", side_effect=AssertionError("synced acts")) as refresh:
            d = trouble.gather(swarm.Launcher(Path(home)), REPO, OWNER, swarm.ROOT / "swarm.toml",
                               now=NOW, sync_acts=False)
        refresh.assert_not_called()
        self.assertIsNone(d.owner_days)
        self.assertTrue(any(e.startswith("swarm acts: not synced") for e in d.errors), d.errors)
        self.assertEqual(trouble.report(d)["scopes"], [])

if __name__ == "__main__":
    unittest.main()
