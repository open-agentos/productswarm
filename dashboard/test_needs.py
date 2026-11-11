"""Tests for the "Needs you" list (generate.needs_you) and its place on the page.

Run: python3 -m unittest discover -s dashboard
"""
import html
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import generate as g  # noqa: E402
from test_generate import NOW, ev, tracking, issue, comment, build, ts  # noqa: E402

GOV_BODY = "### Domain\n\narchitecture\n\n### Time to live\n\n2026-11-09\n\n### Suggested shape\n\nadvice\n"


def question(n, title, minutes_ago, body=GOV_BODY, labels=()):
    it = issue(n, title, ["gov:question", *labels])
    it["created_at"], it["body"] = ts(minutes_ago), body
    return it


def pr(n, minutes_ago, draft=False, review="", closes=()):
    return {"number": n, "title": f"PR {n}", "url": f"https://x/pull/{n}",
            "author": {"login": "app/productswarm-builder"}, "isDraft": draft,
            "createdAt": ts(minutes_ago), "reviewDecision": review,
            "closingIssuesReferences": [{"number": c} for c in closes]}


def model():
    issues = [
        tracking(50, "blocked-new"), tracking(51, "blocked-old"), tracking(52, "idle-short"),
        tracking(53, "idle-long"), tracking(54, "active"), tracking(55, "gone", state="closed"),
        issue(4, "Dashboard"),
        question(26, "GOV-Q: old unwaited", 600, labels=["gov:ruled"]),
        question(27, "GOV-Q: new unwaited", 60, body="no template"),
        question(28, "GOV-Q: someone waits", 30),
        question(29, "GOV-Q: another waits", 20),
    ]
    comments = {
        50: [comment([ev("blocked-new", "blocked", 5, issue=4, gov_question=29)])],
        51: [comment([ev("blocked-old", "blocked", 50, gov_question=28)])],
        52: [comment([ev("idle-short", "working_on", 20, issue=4)])],
        53: [comment([ev("idle-long", "session_started", 300)])],
        54: [comment([ev("active", "working_on", 1, issue=4)])],
        55: [comment([ev("gone", "stopped", 400)])],
    }
    prs = [pr(31, 10, closes=[4]), pr(30, 90, review="CHANGES_REQUESTED"), pr(32, 500, draft=True)]
    return build(issues, comments, prs)


class NeedsYouTest(unittest.TestCase):
    def test_order(self):
        items = g.needs_you(model())
        self.assertEqual([(i["kind"], i["ref"]) for i in items], [
            ("blocked", "#28"), ("blocked", "#29"),             # longest blocked first
            ("question", "#27"),                                # unwaited; #26 is gov:ruled
            ("pr", "PR #30"), ("pr", "PR #31"),                 # not drafts, oldest first
        ])                                                      # idle sessions: not listed (#469)

    def test_details_and_links(self):
        items = {i["ref"]: i for i in g.needs_you(model())}
        b = items["#29"]
        self.assertEqual(b["url"], "https://github.com/open-agentos/productswarm/issues/29")
        self.assertEqual(b["session_url"], "https://github.com/open-agentos/productswarm/issues/50")
        self.assertEqual(b["detail"], "builder session blocked- is blocked on it (working on #4)")
        self.assertEqual(items["#27"]["detail"], "no time to live given")
        self.assertEqual(items["PR #30"]["detail"], "changes requested")
        self.assertEqual(items["PR #31"]["detail"], "awaiting review, closes #4")

    def test_line(self):
        items = g.needs_you(model())
        self.assertEqual(g.needs_line(items[0], NOW),
                         "[blocked] #28 GOV-Q: someone waits · builder session blocked- is blocked on it · 50m ago")
        self.assertEqual(g.needs_line(items[-1], NOW),
                         "[PR to review] PR #31 PR 31 · awaiting review, closes #4 · 10m ago")

    def test_todays_shape_lists_neither_idle_nor_ruled(self):
        # #469: 19 idle reviewer sessions that never sent an event past session_started,
        # and one question the owner has ruled. Neither is the owner's to act on.
        issues = [tracking(100 + i, f"rev{i:05d}") | {"title": f"[heartbeat] reviewer rev{i:05d}"}
                  for i in range(19)]
        issues += [question(396, "GOV-Q: ruled", 600, labels=["gov:ruled", "ready"])]
        m = build(issues, {})
        self.assertEqual(sum(s["status"] == "idle" for s in m["sessions"]), 19)
        self.assertEqual([q["number"] for q in m["gov"]], [396])
        self.assertEqual(g.needs_you(m), [])
        self.assertIn(g.NEEDS_EMPTY, g.render(m)["operations.html"])

    def test_never_acted_sessions_are_left_out(self):
        # #454: the same 19, with no events at all and tracking issues older than the
        # idle threshold. Marked never_acted; even one flagged over cap isn't listed.
        issues = [tracking(100 + i, f"rev{i:05d}") for i in range(19)]
        m = build(issues, {})
        self.assertTrue(all(s["never_acted"] for s in m["sessions"]))
        self.assertEqual(g.needs_you(m), [])
        m["sessions"][0].update(over_cap=True, cost=20.0, cap=15.0)
        self.assertEqual(g.needs_you(m), [])
        m["sessions"][0]["never_acted"] = False
        self.assertEqual([i["kind"] for i in g.needs_you(m)], ["over_cap"])

    def test_ruled_question_with_a_blocked_session_still_shows_as_blocked(self):
        m = build([question(396, "GOV-Q: ruled", 600, labels=["gov:ruled"]), tracking(50, "blocked")],
                  {50: [comment([ev("blocked", "blocked", 5, gov_question=396)])]})
        self.assertEqual([(i["kind"], i["ref"]) for i in g.needs_you(m)], [("blocked", "#396")])

    def test_empty(self):
        m = build([tracking(54, "active")], {54: [comment([ev("active", "working_on", 1, issue=4)])]})
        self.assertEqual(g.needs_you(m), [])
        self.assertIn(g.NEEDS_EMPTY, g.render(m)["operations.html"])

    def test_time_to_live(self):
        self.assertEqual(g.time_to_live(GOV_BODY), "2026-11-09")
        self.assertEqual(g.time_to_live("### Time to live\n\n_No response_\n"), None)
        self.assertEqual(g.time_to_live(None), None)


def review(state, commit, authority="pass", login=g.REVIEWER):
    return {"user": {"login": login}, "state": state, "commit_id": commit,
            "body": f"- **Bugs:** pass\n- **Scope:** pass\n- **Authority:** {authority}\n\nx"}


class ReviewerStateTest(unittest.TestCase):
    """GOV-0011 (#113): the reviewer's reviews on a PR, as swarm watch and needs_you read them."""
    HEAD = "h" * 40

    def detail(self, reviews, author="app/productswarm-builder"):
        p = {**pr(40, 30, closes=[4]), "headRefOid": self.HEAD, "author": {"login": author}}
        m = g.build({"repo": "open-agentos/productswarm", "issues": [issue(4, "x")], "comments": {},
                     "prs": [p], "reviews": {40: reviews}}, NOW, g.dt.timedelta(minutes=15))
        (item,) = g.needs_you(m)
        return m["prs"][0]["reviewer"], item["detail"]

    def test_round_count_and_latest_at_head(self):
        r, detail = self.detail([review("CHANGES_REQUESTED", "c1"), review("COMMENTED", "c1"),
                                 review("CHANGES_REQUESTED", self.HEAD),
                                 review("CHANGES_REQUESTED", self.HEAD, login="someone")])
        self.assertEqual(r, {"changes_requested": 2, "at_head": "CHANGES_REQUESTED", "authority": "pass",
                             "at_head_at": None})
        self.assertEqual(detail, "awaiting review, closes #4")

    def test_third_request_needs_the_owner(self):
        _, detail = self.detail([review("CHANGES_REQUESTED", c) for c in ("c1", "c2", self.HEAD)])
        self.assertEqual(detail, "changes requested 3 times: needs the owner, closes #4")

    def test_third_request_on_an_older_head_is_back_with_the_reviewer(self):
        _, detail = self.detail([review("CHANGES_REQUESTED", c) for c in ("c1", "c2", "c3")])
        self.assertEqual(detail, "no reviewer review at hhhhhhh, closes #4")   # #332

    def test_overstep_at_head_needs_the_owner_whatever_the_state(self):
        for state in ("COMMENTED", "CHANGES_REQUESTED"):
            _, detail = self.detail([review(state, self.HEAD, authority="fail")])
            self.assertEqual(detail, "overstep: needs the owner, closes #4")
        _, detail = self.detail([review("COMMENTED", "old", authority="fail")])  # an older head
        self.assertEqual(detail, "no reviewer review at hhhhhhh, closes #4")   # #332

    def test_changes_on_a_pr_no_role_opened_need_the_owner(self):
        """#178: a role responds only on its own PR (GOV-0011); #738 made that any author role."""
        for author, who in [("mattmcalister", "non-swarm"), ("app/productswarm-reviewer", "reviewer"),
                            ("productswarm-stranger[bot]", "stranger")]:
            _, detail = self.detail([review("CHANGES_REQUESTED", self.HEAD)], author)
            self.assertEqual(detail, f"changes requested on a {who} PR: needs the owner, closes #4")
            _, detail = self.detail([review("COMMENTED", self.HEAD)], author)
            self.assertEqual(detail, "awaiting review, closes #4")
        for author in ("productswarm-builder[bot]", "app/productswarm-docs", "productswarm-docs[bot]",
                       "productswarm-analyst[bot]", "app/productswarm-planner"):
            _, detail = self.detail([review("CHANGES_REQUESTED", self.HEAD)], author)
            self.assertEqual(detail, "awaiting review, closes #4", author)

    def test_comment_or_approve_is_not_the_owners(self):
        for state in ("COMMENTED", "APPROVED"):
            r, detail = self.detail([review(state, self.HEAD)])
            self.assertEqual((r["at_head"], detail), (state, "awaiting review, closes #4"))

    def test_authority_line_forms(self):
        for body, want in [("- **Authority:** fail", "fail"), ("**Authority**: FAIL", "fail"),
                           ("Authority: pass — none", "pass"), ("no rubric here", None),
                           ("The Authority: fail line is quoted mid-sentence", None)]:
            m = g.AUTHORITY_RE.search(body)
            self.assertEqual(m.group(1).lower() if m else None, want, body)

    def test_data_without_reviews_still_builds(self):
        m = g.build({"repo": "r", "issues": [], "comments": {}, "prs": [pr(40, 30)]}, NOW,
                    g.dt.timedelta(minutes=15))
        self.assertEqual(m["prs"][0]["reviewer"]["at_head"], None)


class UnreviewedHeadTest(unittest.TestCase):
    """#332: a non-draft builder PR with no reviewer-App review at its head is flagged, so
    the owner sees it before merging (#200, #269 and #275 were merged unreviewed)."""
    HEAD = "abcdef0" + "1" * 33

    def details(self, reviews, author="app/productswarm-builder", draft=False, decision=""):
        p = {**pr(40, 30, draft=draft, review=decision, closes=[4]), "headRefOid": self.HEAD,
             "author": {"login": author}}
        m = g.build({"repo": "open-agentos/productswarm", "issues": [issue(4, "x")], "comments": {},
                     "prs": [p], "reviews": {40: reviews}}, NOW, g.dt.timedelta(minutes=15))
        return [i["detail"] for i in g.needs_you(m) if i["kind"] == "pr"]

    def test_no_reviewer_review(self):
        self.assertEqual(self.details([]), ["no reviewer review at abcdef0, closes #4"])

    def test_reviewed_at_an_older_head_only(self):
        self.assertEqual(self.details([review("APPROVED", "old"), review("COMMENTED", "older")]),
                         ["no reviewer review at abcdef0, closes #4"])

    def test_owner_approval_only(self):
        owner = review("APPROVED", self.HEAD, login="mattmcalister")
        self.assertEqual(self.details([owner], decision="APPROVED"),
                         ["no reviewer review at abcdef0, closes #4"])

    def test_reviewed_at_head_is_not_flagged(self):
        for state, decision, want in [("APPROVED", "APPROVED", "approved"),
                                      ("COMMENTED", "", "awaiting review")]:
            self.assertEqual(self.details([review(state, self.HEAD)], decision=decision),
                             [f"{want}, closes #4"])

    def test_rest_login_form_is_a_builder_pr(self):
        self.assertEqual(self.details([], author="productswarm-builder[bot]"),
                         ["no reviewer review at abcdef0, closes #4"])

    def test_draft_is_not_flagged(self):
        self.assertEqual(self.details([], draft=True), [])

    def test_non_builder_pr_is_not_flagged(self):
        for author in ("app/productswarm-docs", "mattmcalister"):
            self.assertEqual(self.details([], author=author), ["awaiting review, closes #4"])

    def test_digest_line_shows_it(self):
        p = {**pr(40, 30, closes=[4]), "headRefOid": self.HEAD}
        m = g.build({"repo": "r", "issues": [issue(4, "x")], "comments": {}, "prs": [p],
                     "reviews": {40: []}}, NOW, g.dt.timedelta(minutes=15))
        (item,) = g.needs_you(m)
        self.assertIn("no reviewer review at abcdef0", g.needs_line(item, NOW))


def ttl_body(ttl):
    return f"### Domain\n\narchitecture\n\n### Time to live\n\n{ttl}\n\n### Suggested shape\n\nadvice\n"


class PastTimeToLiveTest(unittest.TestCase):
    """#210 (v3 F1): flag a question whose time to live has passed. NOW is 2026-11-02."""

    def model(self):
        return build([
            question(60, "GOV-Q: future", 900, body=ttl_body("2026-11-09")),
            question(61, "GOV-Q: today", 800, body=ttl_body("2026-11-02")),
            question(62, "GOV-Q: past recently", 700, body=ttl_body("2026-11-01")),
            question(63, "GOV-Q: past long ago", 10, body=ttl_body("2026-10-20 (with a note)"),
                     labels=["gov:lapsed"]),
            question(64, "GOV-Q: not a date", 600, body=ttl_body("when F ships")),
            question(65, "GOV-Q: missing", 500, body="no template"),
            question(66, "GOV-Q: impossible date", 400, body=ttl_body("2026-13-40")),
            tracking(50, "blocked"),
        ], {50: [comment([ev("blocked", "blocked", 5, gov_question=60)])]})

    def test_details(self):
        items = {i["ref"]: i for i in g.needs_you(self.model())}
        self.assertEqual(items["#62"]["detail"], "past time to live (2026-11-01)")
        self.assertEqual(items["#63"]["detail"], "past time to live (2026-10-20), gov:lapsed")
        self.assertEqual(items["#61"]["detail"], "time to live 2026-11-02")
        self.assertEqual(items["#64"]["detail"], "time to live when F ships")
        self.assertEqual(items["#65"]["detail"], "no time to live given")
        self.assertEqual(items["#66"]["detail"], "time to live 2026-13-40")

    def test_order(self):
        items = g.needs_you(self.model())
        self.assertEqual([(i["kind"], i["ref"]) for i in items], [
            ("blocked", "#60"),                         # blocked still comes first
            ("question", "#63"), ("question", "#62"),   # past time to live, oldest first
            ("question", "#61"), ("question", "#64"),   # then the rest, longest waiting first
            ("question", "#65"), ("question", "#66"),
        ])

    def test_shown_on_page_and_line(self):
        m = self.model()
        item = next(i for i in g.needs_you(m) if i["ref"] == "#62")
        line = g.needs_line(item, NOW)
        self.assertTrue(line.startswith("[gov question] #62 GOV-Q: past recently · past time to live (2026-11-01)"))
        self.assertIn(html.escape(line), g.render(m)["operations.html"])

    def test_ttl_date(self):
        self.assertEqual(g.ttl_date("2026-11-30"), g.dt.date(2026, 11, 30))
        self.assertEqual(g.ttl_date("2026-11-30 (the rulings' review date)"), g.dt.date(2026, 11, 30))
        for text in (None, "", "soon", "2026-11-30x", "2026-02-30"):
            self.assertIsNone(g.ttl_date(text), text)


class PageTest(unittest.TestCase):
    def test_first_section_matches_the_list(self):
        m = model()
        page = g.render(m)["operations.html"]
        self.assertLess(page.index("<h2>Needs you (5)</h2>"), page.index("<h2>Sessions</h2>"))
        section = page[page.index('<ol class="inbox">'):page.index("</ol>")]
        shown = [html.unescape(re.sub(r"<[^>]+>", "", li)).split(" · session")[0]
                 for li in re.findall(r"<li[^>]*>(.*?)</li>", section)]
        self.assertEqual(shown, [g.needs_line(i, m["now"]) for i in g.needs_you(m)])
        self.assertIn('<a href="https://github.com/open-agentos/productswarm/issues/50">session</a>', section)


if __name__ == "__main__":
    unittest.main()
