"""Tests for dashboard/committees.py. Run: python3 -m unittest discover -s dashboard

Canned GraphQL and REST data modelled on Discussion #314 and gov:question #311, so nothing
touches GitHub.
"""
import datetime as dt
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import committees as c  # noqa: E402
import generate as g    # noqa: E402

REPO = "open-agentos/productswarm"
OWNER = "mattmcalister"
DURL = "https://github.com/open-agentos/productswarm/discussions/314"
QURL = "https://github.com/open-agentos/productswarm/issues/311"
COST = "Cost: about $2.89 across the six posts."

MEMBERS = """## Members

| Role | Member | Model | Main evidence |
|---|---|---|---|
| **Proposer** | reviewer (`productswarm-reviewer[bot]`) | `claude-opus-5-5` | its own review history, GOV-0011 |
| **Challenger** | builder (`productswarm-builder[bot]`) | `claude-sonnet-5-5` (this committee only) | the reviews it received |
| **Domain reviewer** | planner (`productswarm-planner[bot]`) | `claude-opus-5-5` | the B eval |

Convener: the owner (`mattmcalister`), who also ratifies. Diversity rule (§7.2): two models **and** three evidence bases.
"""

RULES = """## Rules

1. **Rounds:** at most 3. In each round, members post in order: proposer, challenger, domain reviewer.
2. **One post per member per round,** as a **top-level comment** in this Discussion, headed `Round N: <role>`.
6. **Stop early** if, after a round, all three recommendations agree. The convener then posts the summary on #311.

Sign every post as usual: `-- <role> (<model>)`.
"""

BODY_314 = ("Committee deliberation for **#311: What should make the reviewer request changes?**\n\n"
            "Read #311 first.\n\n" + MEMBERS + "\n" + RULES)

SEATS = {"proposer": ("reviewer", "claude-opus-5-5"), "challenger": ("builder", "claude-sonnet-5-5"),
         "domain reviewer": ("planner", "claude-opus-5-5")}

# #314's six posts: round, seat, minute after 14:00 UTC on 2026-11-04, Recommendation.
POSTS_314 = [(1, "proposer", 18, "**Option 3, with changes 1 and 2 (3b).** Amend GOV-0011."),
             (1, "challenger", 20, "**Option 3, as the proposer's 3b, plus these four amendments (3c):**"),
             (1, "domain reviewer", 22, "**Option 3 as 3c** (the proposer's 3b plus four amendments)"),
             (2, "proposer", 23, "**Option 3 as 3c**, adopted as an amendment to GOV-0011"),
             (2, "challenger", 24, "**Option 3 as 3c+E**, as the proposer's Round 2 recommendation lists it"),
             (2, "domain reviewer", 25, "**Option 3 as 3c+E.** That's the proposer's Round 2 list.")]


def at(minute: int, day: int = 4, hour: int = 14) -> str:
    return f"2026-11-{day:02d}T{hour:02d}:{minute:02d}:00Z"


def post(rnd, seat, minute, reco, model=None, login=None, day=4, hour=14):
    role, table_model = SEATS[seat]
    body = (f"## Round {rnd}: {seat} ({role})\n\n### Position\n\nI back **something else** here.\n\n"
            f"### Evidence\n\n**Not this.**\n\n### Recommendation\n\n{reco}\n\n"
            f"-- {role} ({model or table_model})")
    return {"author": {"login": login or f"productswarm-{role}"}, "createdAt": at(minute, day, hour),
            "url": f"{DURL}#discussioncomment-{rnd}{minute}", "body": body}


def discussion(number=314, title="Committee for #311: when should the reviewer request changes?",
               body=BODY_314, comments=None):
    return {"id": f"D_{number}", "number": number, "title": title, "body": body,
            "url": f"https://github.com/open-agentos/productswarm/discussions/{number}",
            "createdAt": at(4), "author": {"login": OWNER},
            "comments": [post(*p) for p in POSTS_314] if comments is None else comments}


def owner_comment(minute, text, login=OWNER):
    return {"user": {"login": login}, "created_at": at(minute), "body": text,
            "html_url": f"{QURL}#issuecomment-{minute}"}


def question(summary=True, ruling=True):
    comments = [owner_comment(4, "**Convening a committee** (GOVERNANCE.md §7.1). (owner)\n\n- Proposer: reviewer"),
                owner_comment(10, "**Convener's summary** from someone else", login="productswarm-planner[bot]")]
    if summary:
        comments.append(owner_comment(25, "**Convener's summary** (GOVERNANCE.md §7.4). (owner, as convener)\n\n"
                                          "The committee met in Discussion #314: 2 rounds of 3.\n\n" + COST))
    if ruling:
        comments.append(owner_comment(32, '**Ruling: ratified as recommended, option 3 as "3c+E".** (owner)'))
    return {"issue": {"number": 311, "state": "closed" if ruling else "open", "html_url": QURL,
                      "labels": [{"name": "gov:question"}] + ([{"name": "gov:ruled"}] if ruling else [])},
            "comments": comments}


class Fixture(unittest.TestCase):
    """GOV-0021 recorded for #311, and build() over canned data."""
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.decisions = Path(tmp.name)
        (self.decisions / "GOV-0021-when.md").write_text(
            '---\nid: GOV-0021\ntitle: x\nstatus: in-force\nkind: ruling\nquestion: "#311"\ndate: 2026-11-04\n---\n\nBody.\n')
        (self.decisions / "GOV-0001-other.md").write_text('---\nid: GOV-0001\nstatus: in-force\nquestion: "#3"\n---\n')

    def build(self, discussions, questions=None, notes=None):
        raw = {"discussions": discussions, "questions": questions if questions is not None else {311: question()},
               "notes": notes or []}
        return c.build(raw, decisions=self.decisions, owner=OWNER)

    def one(self, *a, **kw):
        (com,) = self.build(*a, **kw)["committees"]
        return com


class CommitteeTest(Fixture):
    def test_314_with_311(self):
        com = self.one([discussion()])
        self.assertEqual(com["question"], 311)
        self.assertEqual(com["status"], "record GOV-0021")
        self.assertEqual([m["seat"] for m in com["members"]], ["proposer", "challenger", "domain reviewer"])
        self.assertEqual([m["app"] for m in com["members"]],
                         ["productswarm-reviewer[bot]", "productswarm-builder[bot]", "productswarm-planner[bot]"])
        self.assertEqual(com["members"][1]["model"], "claude-sonnet-5-5")
        self.assertEqual(com["diversity"], {"models": 2, "evidence": 3, "met": True})
        self.assertEqual((com["rounds_used"], com["max_rounds"]), (2, 3))
        self.assertEqual(len(com["posts"]), 6)
        self.assertTrue(all(p["url"].startswith(DURL + "#discussioncomment-") for p in com["posts"]))
        self.assertEqual([p["recommendation"] for p in com["posts"]],
                         ["Option 3, with changes 1 and 2 (3b)",
                          "Option 3, as the proposer's 3b, plus these four amendments (3c)",
                          "Option 3 as 3c", "Option 3 as 3c", "Option 3 as 3c+E", "Option 3 as 3c+E"])
        self.assertIsNone(com["next_seat"])
        self.assertEqual(com["missed"], [])
        self.assertEqual(com["over_limit"], [])
        self.assertFalse(any(p["model_differs"] for p in com["posts"]))
        self.assertTrue(com["ruled"])
        self.assertEqual(com["record"], {"id": "GOV-0021", "status": "in-force", "file": "GOV-0021-when.md",
                                         "date": "2026-11-04"})
        self.assertEqual(set(com["owner_comments"]), {"convening", "summary", "ruling"})
        self.assertEqual(com["owner_comments"]["summary"]["url"], f"{QURL}#issuecomment-25")
        self.assertEqual(com["notes"], [])

    def test_status_before_the_record(self):
        self.assertEqual(self.one([discussion()])["status"], "record GOV-0021")
        (self.decisions / "GOV-0021-when.md").unlink()
        self.assertEqual(self.one([discussion()])["status"], "ratified")
        self.assertEqual(self.one([discussion()], {311: question(ruling=False)})["status"], "summary")
        com = self.one([discussion()], {311: question(summary=False, ruling=False)})
        self.assertEqual(com["status"], "round 2")
        self.assertEqual(self.one([discussion(comments=[])], {311: question(False, False)})["status"], "convened")

    def test_summary_only_counts_from_the_owner(self):
        (self.decisions / "GOV-0021-when.md").unlink()
        com = self.one([discussion(comments=[post(*POSTS_314[0])])], {311: question(summary=False, ruling=False)})
        self.assertIsNone(com["owner_comments"]["summary"])   # the planner's look-alike doesn't count
        self.assertEqual(com["next_seat"], "challenger")

    def test_mid_round_waits_on_the_challenger(self):
        (self.decisions / "GOV-0021-when.md").unlink()
        com = self.one([discussion(comments=[post(*POSTS_314[0])])], {311: question(False, False)})
        self.assertEqual(com["status"], "round 1")
        self.assertEqual(com["next_seat"], "challenger")
        self.assertEqual(com["rounds_used"], 1)
        self.assertEqual(com["missed"], [])

    def test_member_who_missed_a_round(self):
        (self.decisions / "GOV-0021-when.md").unlink()
        posts = [post(*p) for p in POSTS_314[:3]] + [post(*POSTS_314[3]), post(*POSTS_314[5])]
        com = self.one([discussion(comments=posts)], {311: question(False, False)})
        self.assertEqual(com["missed"], [{"round": 2, "seat": "challenger"}])
        self.assertEqual(com["next_seat"], "proposer")   # round 2 is over; round 3 starts
        posts.append(post(3, "proposer", 40, "**Option 3**"))
        com = self.one([discussion(comments=posts)], {311: question(False, False)})
        self.assertEqual(com["missed"], [{"round": 2, "seat": "challenger"}])
        self.assertEqual(com["next_seat"], "challenger")

    def test_early_stop_and_round_limit(self):
        (self.decisions / "GOV-0021-when.md").unlink()
        agree = [post(1, s, m, "**Option 3 as 3c+E.**") for s, m in
                 (("proposer", 18), ("challenger", 20), ("domain reviewer", 22))]
        com = self.one([discussion(comments=agree)], {311: question(False, False)})
        self.assertTrue(com["stopped_early"])          # rule 6: all three agree after round 1
        self.assertIsNone(com["next_seat"])
        com = self.one([discussion(comments=[post(*p) for p in POSTS_314])], {311: question(False, False)})
        self.assertFalse(com["stopped_early"])         # 3c vs 3c+E: not the same phrase
        self.assertEqual(com["next_seat"], "proposer")
        three = [post(r, s, m, f"**Option {i}**") for r in (1, 2, 3)
                 for i, (s, m) in enumerate((("proposer", 10 * r), ("challenger", 10 * r + 1),
                                             ("domain reviewer", 10 * r + 2)))]
        com = self.one([discussion(comments=three)], {311: question(False, False)})
        self.assertEqual((com["rounds_used"], com["next_seat"]), (3, None))

    def test_posts_that_are_not_round_posts(self):
        posts = [post(*p) for p in POSTS_314]
        posts.append(post(1, "proposer", 50, "**Again**"))                          # a second round-1 post
        posts.append(post(2, "proposer", 51, "**Imposter**", login="someone"))      # not the seat's App
        posts.append({**post(1, "challenger", 52, "**x**"), "body": "Thanks!\n\n## Round 1: challenger"})
        com = self.one([discussion(comments=posts)])
        self.assertEqual(len(com["posts"]), 6)
        self.assertNotIn("Again", str(com))
        self.assertNotIn("Imposter", str(com))

    def test_post_model_differs_from_the_table(self):
        posts = [post(*p) for p in POSTS_314]
        posts[1] = post(*POSTS_314[1], model="claude-opus-5-5")
        com = self.one([discussion(comments=posts)])
        self.assertEqual([p["model_differs"] for p in com["posts"]], [False, True, False, False, False, False])
        self.assertEqual(com["posts"][1]["model"], "claude-opus-5-5")

    def test_more_than_six_posts_by_one_member_in_a_day(self):
        posts = [post(*p) for p in POSTS_314]
        extra = [{"user": {"login": "productswarm-builder[bot]"}, "created_at": at(40 + i), "body": "note",
                  "html_url": f"{QURL}#issuecomment-b{i}"} for i in range(4)]
        q = question()
        q["comments"] += extra
        com = self.one([discussion(comments=posts)], {311: q})
        self.assertEqual(com["over_limit"], [])        # 2 round posts + 4 on the question: 6 is allowed
        q["comments"].append({**extra[0], "created_at": at(50)})
        com = self.one([discussion(comments=posts)], {311: q})
        self.assertEqual(com["over_limit"], [{"app": "productswarm-builder[bot]", "day": dt.date(2026, 11, 4),
                                              "count": 7}])
        q["comments"][-1]["created_at"] = at(1, day=5)  # the next UTC day starts a new count
        self.assertEqual(self.one([discussion(comments=posts)], {311: q})["over_limit"], [])

    def test_unparsed_discussion(self):
        cases = [discussion(number=400, title="Committee chat", body=BODY_314.replace("#311", "the question")),
                 discussion(number=401, body="Committee for #311, no table.\n\n" + RULES),
                 discussion(number=402, body=MEMBERS + "\n## Rules\n\nAnyone may post.\n"),
                 discussion(number=403, body=MEMBERS.replace("(`productswarm-builder[bot]`)", "<member>")
                            + "\n" + RULES)]
        m = self.build(cases)
        self.assertEqual([x["status"] for x in m["committees"]], ["unparsed"] * 4)
        self.assertEqual(m["notes"], ["#403: unparsed", "#402: unparsed", "#401: unparsed", "#400: unparsed"])

    def test_one_bad_discussion_leaves_the_rest(self):
        m = self.build([discussion(), discussion(number=500, title=None, body=None, comments=None)])
        self.assertEqual([x["status"] for x in m["committees"]], ["unparsed", "record GOV-0021"])

    def test_marker_wins_over_any_title(self):
        body = "<!-- productswarm-committee question=311 -->\n\n### Intro\n\nSee #311.\n\n" + \
            MEMBERS.replace("## Members", "### Members") + "\n" + RULES.replace("## Rules", "### Rules")
        com = self.one([discussion(title="Reviewer committee", body=body)])
        self.assertEqual((com["question"], com["status"]), (311, "record GOV-0021"))
        self.assertEqual(com["notes"], [])

    def test_placeholder_marker_falls_back_to_the_title(self):
        body = "<!-- productswarm-committee question=NNN -->\n\n" + BODY_314
        com = self.one([discussion(body=body)])
        self.assertEqual((com["question"], com["status"]), (311, "record GOV-0021"))

    def test_marker_and_title_disagree(self):
        body = "<!-- productswarm-committee question=311 -->\n\n" + BODY_314
        com = self.one([discussion(title="Committee for #999: oops", body=body)])
        self.assertEqual(com["question"], 311)
        self.assertEqual(com["notes"], ["#314: marker says #311, title says #999; using #311"])

    def test_recommendation_phrase_is_cut(self):
        long = "**" + "word " * 40 + "**"
        com = self.one([discussion(comments=[post(1, "proposer", 18, long)])])
        self.assertLessEqual(len(com["posts"][0]["recommendation"]), 80)
        self.assertTrue(com["posts"][0]["recommendation"].endswith("…"))

    def test_diversity_rule(self):
        one_model = MEMBERS.replace("`claude-sonnet-5-5`", "`claude-opus-5-5`")
        com = self.one([discussion(body=one_model + "\n" + RULES)])
        self.assertEqual(com["diversity"], {"models": 1, "evidence": 3, "met": True})
        same = one_model.replace("the reviews it received", "the B eval").replace(
            "its own review history, GOV-0011", "the B eval")
        com = self.one([discussion(body=same + "\n" + RULES)])
        self.assertEqual(com["diversity"], {"models": 1, "evidence": 1, "met": False})

    def test_cost_line_never_reaches_the_output(self):
        data = {"repo": REPO, "issues": [], "comments": {}, "prs": [], "reviews": {},
                "committees": {"discussions": [discussion()], "questions": {311: question()}, "notes": []}}
        now = dt.datetime(2026, 11, 4, 15, 0, tzinfo=dt.timezone.utc)
        model = g.build(data, now, dt.timedelta(minutes=15))
        self.assertEqual(model["committees"]["committees"][0]["status"], "record GOV-0021")
        page = g.render(model)
        self.assertIn("<h2>Committees</h2>", page)
        self.assertNotIn("<script", page.lower())
        for text in (repr(model), page):
            self.assertNotIn("2.89", text)
            self.assertNotIn("Cost", text)
            self.assertNotIn("2 rounds of 3", text)   # nor any other summary text
            self.assertNotIn("I back", text)          # nor round-post text beyond the phrase

    def test_records_and_owner_from_the_checkout(self):
        self.assertEqual(c.records()[311]["id"], "GOV-0021")
        self.assertEqual(c.owner_login(), OWNER)

    def test_no_committee_data(self):
        self.assertEqual(c.build(None), {"committees": [], "notes": []})


class RenderTest(Fixture):
    def page(self, discussions, questions=None, notes=None):
        return c.render(self.build(discussions, questions, notes), REPO)

    def test_314_with_311(self):
        html = self.page([discussion()])
        self.assertIn("<details><summary>1 ended</summary>", html)    # record merged: collapsed
        self.assertIn("No open committees.", html)
        self.assertIn(f'<a href="{QURL}">#311</a>', html)               # no title in the canned issue
        self.assertIn(f'<a href="{DURL}">#314</a>', html)
        self.assertIn(f'<b class="now" title="current step"><a href="https://github.com/{REPO}/blob/main/'
                      'governance/decisions/GOV-0021-when.md">record GOV-0021</a> '
                      '<span class="muted">2026-11-04</span></b>', html)
        for step in ("convened", "round 1", "round 2", "summary", "ratified"):
            self.assertRegex(html, rf'<a href="[^"]+">{step}</a> <span class="muted">2026-11-04</span>')
        self.assertEqual(html.count("</td><td><code>claude-"), 3)        # 3 members
        self.assertIn("§7.2 diversity met: 2 models, 3 evidence bases", html)
        grid = html[html.index('<table class="grid">'):]
        grid = grid[:grid.index("</table>")]
        self.assertEqual(grid.count("<th>Round "), 2)
        self.assertEqual(grid.count("<tr>"), 4)                          # header + 3 members
        self.assertEqual(grid.count(f'<a href="{DURL}#discussioncomment-'), 6)
        self.assertIn(">11-04 14:18 UTC</a><br>Option 3, with changes 1 and 2 (3b)", grid)
        # The proposer's round-2 phrase is "Option 3 as 3c", the others' "Option 3 as 3c+E".
        self.assertIn("dissent: proposer · rounds used: 2 of 3 · nobody over 6 posts a day", html)

    def test_all_agree_and_stopped_early(self):
        (self.decisions / "GOV-0021-when.md").unlink()
        agree = [post(1, s, m, "**Option 3 as 3c+E.**") for s, m in
                 (("proposer", 18), ("challenger", 20), ("domain reviewer", 22))]
        html = self.page([discussion(comments=agree)], {311: question(ruling=False)})
        self.assertNotIn("<details>", html)                              # question still open
        self.assertIn("all agree after round 1", html)
        self.assertIn('<b class="now" title="current step"><a href="' + QURL + '#issuecomment-25">summary</a>', html)
        self.assertEqual(html.count('<span class="muted">stopped early</span>'), 6)   # rounds 2 and 3
        self.assertIn('<span class="muted">record</span>', html)

    def test_mid_round_waiting_on_the_challenger(self):
        (self.decisions / "GOV-0021-when.md").unlink()
        html = self.page([discussion(comments=[post(*POSTS_314[0])])], {311: question(False, False)})
        self.assertIn("<td><b>waiting on challenger</b></td>", html)
        self.assertEqual(html.count("<th>Round "), 1)
        self.assertNotIn("<details>", html)
        self.assertIn('<b class="now" title="current step"><a href="', html)
        self.assertIn('<span class="muted">summary</span> → <span class="muted">ratified</span>', html)

    def test_waiting_cell_opens_the_next_round(self):
        (self.decisions / "GOV-0021-when.md").unlink()
        posts = [post(*p) for p in POSTS_314[:3]] + [post(*POSTS_314[3]), post(*POSTS_314[5])]
        html = self.page([discussion(comments=posts)], {311: question(False, False)})
        self.assertEqual(html.count("<th>Round "), 3)
        self.assertIn("<tr><th>proposer</th>", html)
        self.assertIn("<td><b>waiting on proposer</b></td>", html)
        self.assertIn('<td><span class="muted">missed</span></td>', html)   # the challenger's round 2

    def test_dissent(self):
        (self.decisions / "GOV-0021-when.md").unlink()
        posts = [post(1, "proposer", 18, "**Option 3**"), post(1, "challenger", 20, "**Option 1**"),
                 post(1, "domain reviewer", 22, "**option  3**")]
        html = self.page([discussion(comments=posts)], {311: question(False, False)})
        self.assertIn("dissent: challenger · rounds used: 1 of 3", html)
        posts[2] = post(1, "domain reviewer", 22, "**Option 2**")
        html = self.page([discussion(comments=posts)], {311: question(False, False)})
        self.assertIn("no majority after round 1", html)

    def test_member_over_six_posts_a_day(self):
        q = question()
        q["comments"] += [{"user": {"login": "productswarm-builder[bot]"}, "created_at": at(40 + i),
                           "body": "note", "html_url": f"{QURL}#issuecomment-b{i}"} for i in range(5)]
        html = self.page([discussion()], {311: q})
        self.assertIn('<span class="pill s-blocked">over 6 posts a day</span> challenger 7 on 2026-11-04', html)
        self.assertNotIn("nobody over", html)

    def test_unparsed_discussion(self):
        html = self.page([discussion(), discussion(number=400, title="Committee chat", body="Anyone may post.")])
        self.assertIn('<p class="muted">Unparsed: <a href="https://github.com/open-agentos/productswarm/'
                      'discussions/400">#400 Committee chat</a></p>', html)
        self.assertNotIn("#400: unparsed", html)

    def test_cant_read_discussions(self):
        html = self.page([], notes=[c.NO_ACCESS])
        self.assertEqual(html, "<h2>Committees</h2>\n" + '<p class="muted">No open committees.</p>\n'
                         f'<p class="muted">{g.esc(c.NO_ACCESS)}</p>')

    def test_no_committees_no_section(self):
        self.assertEqual(c.render(None, REPO), "")
        self.assertEqual(self.page([]), "")
        self.assertEqual(self.page([], notes=["no Committees Discussion category"]), "")
        data = {"repo": REPO, "issues": [], "comments": {}, "prs": [], "reviews": {}, "committees": None}
        now = dt.datetime(2026, 11, 4, 15, 0, tzinfo=dt.timezone.utc)
        self.assertNotIn("Committees", g.render(g.build(data, now, dt.timedelta(minutes=15))))

    def test_open_committees_come_after_needs_you(self):
        (self.decisions / "GOV-0021-when.md").unlink()
        data = {"repo": REPO, "issues": [], "comments": {}, "prs": [], "reviews": {},
                "committees": {"discussions": [discussion(comments=[post(*POSTS_314[0])])],
                               "questions": {311: question(False, False)}, "notes": []}}
        now = dt.datetime(2026, 11, 4, 15, 0, tzinfo=dt.timezone.utc)
        page = g.render(g.build(data, now, dt.timedelta(minutes=15)))
        self.assertLess(page.index("Needs you"), page.index("<h2>Committees</h2>"))
        self.assertLess(page.index("<h2>Committees</h2>"), page.index("<h2>Sessions</h2>"))


def fake_gh_json(pages: dict, fail: str | None = None):
    """A gh_json for fetch(): answers each GraphQL query from `pages` and records calls."""
    calls = []

    def gh_json(*args):
        calls.append(args)
        if args[:2] == ("api", "graphql"):
            if fail:
                raise RuntimeError(fail)
            q = args[3]
            fields = dict(a.split("=", 1) for a in args[5::2])
            if "discussionCategory" in q:
                return {"data": {"repository": {"discussionCategory": pages.get("category")}}}
            if "node(id" in q:
                return {"data": {"node": {"comments": pages["more"][fields.get("after")]}}}
            return {"data": {"repository": {"discussions": pages["discussions"][fields.get("after")]}}}
        if args == ("api", f"repos/{REPO}/issues/311"):
            return question()["issue"]
        raise RuntimeError(f"unexpected {args}")
    return gh_json, calls


def conn(nodes, cursor=None):
    return {"pageInfo": {"hasNextPage": cursor is not None, "endCursor": cursor}, "nodes": nodes}


class FetchTest(unittest.TestCase):
    def items(self, path):
        self.assertEqual(path, f"repos/{REPO}/issues/311/comments?per_page=100")
        return question()["comments"]

    def test_pages_discussions_and_comments(self):
        d = discussion()
        posts = d.pop("comments")
        other = discussion(number=315, title="Committee for #311: again", comments=[])
        other.pop("comments")
        pages = {"category": {"id": "CAT"},
                 "discussions": {None: conn([{**d, "comments": conn(posts[:2], "c2")}], "d2"),
                                 "d2": conn([{**other, "comments": conn([])}])},
                 "more": {"c2": conn(posts[2:4], "c4"), "c4": conn(posts[4:])}}
        gh_json, calls = fake_gh_json(pages)
        raw = c.fetch(REPO, self.items, gh_json)
        self.assertEqual(raw["notes"], [])
        self.assertEqual([x["number"] for x in raw["discussions"]], [314, 315])
        self.assertEqual(len(raw["discussions"][0]["comments"]), 6)
        self.assertEqual(list(raw["questions"]), [311])            # read once for both
        self.assertTrue(all(a[0] == "api" for a in calls))
        self.assertFalse(any("-X" in a or "--method" in a for a in calls))
        m = c.build(raw, owner=OWNER)
        self.assertEqual([x["status"] for x in m["committees"]], ["record GOV-0021", "record GOV-0021"])

    def test_token_without_discussions_access(self):
        gh_json, _ = fake_gh_json({}, fail="gh api graphql failed: GraphQL: Resource not accessible by integration")
        raw = c.fetch(REPO, self.items, gh_json)
        self.assertEqual(raw, {"discussions": [], "questions": {}, "notes": [c.NO_ACCESS]})
        self.assertEqual(c.build(raw)["notes"], [c.NO_ACCESS])

    def test_other_failures_and_no_category(self):
        gh_json, _ = fake_gh_json({}, fail="timeout")
        self.assertEqual(c.fetch(REPO, self.items, gh_json)["notes"], ["can't read Discussions"])
        gh_json, _ = fake_gh_json({"category": None})
        self.assertEqual(c.fetch(REPO, self.items, gh_json)["notes"], ["no Committees Discussion category"])

    def test_unreadable_question(self):
        d = discussion(title="Committee for #77: x")
        d["comments"] = conn(d["comments"])
        gh_json, _ = fake_gh_json({"category": {"id": "CAT"}, "discussions": {None: conn([d])}})
        raw = c.fetch(REPO, self.items, gh_json)
        self.assertEqual(raw["notes"], ["#314: can't read question #77"])
        self.assertEqual(len(raw["discussions"]), 1)


FAKE_GH = r"""#!/usr/bin/env python3
import sys
a = sys.argv[1:]
if a[:2] == ["api", "graphql"]:
    sys.stderr.write("GraphQL: Resource not accessible by integration (repository.discussionCategory)\n")
    sys.exit(1)
if a[:2] == ["pr", "list"]:
    print("[]")
"""


class PageStillBuildsTest(unittest.TestCase):
    def test_main_without_discussions_access(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            fake = d / "gh"
            fake.write_text(FAKE_GH)
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
            old = os.environ.get("PATH")
            os.environ["PATH"] = f"{d}{os.pathsep}{old}"
            try:
                now = dt.datetime.now(dt.timezone.utc)
                data = g.fetch(REPO, now, 14, with_committees=True)
                rc = g.main(["--repo", REPO, "--out", str(d / "index.html")])
                plain = g.fetch(REPO, now, 14)
            finally:
                os.environ["PATH"] = old
            self.assertEqual(data["committees"]["notes"], [c.NO_ACCESS])
            self.assertEqual(g.build(data, now, dt.timedelta(minutes=15))["committees"]["notes"], [c.NO_ACCESS])
            self.assertEqual(rc, 0)
            self.assertTrue((d / "index.html").read_text().startswith("<!doctype html>"))
            self.assertIsNone(plain["committees"])   # inbox, watch and the digest skip it


if __name__ == "__main__":
    unittest.main()
