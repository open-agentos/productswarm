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
import unittest.mock
from unittest import mock
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import committees as c  # noqa: E402
import generate as g    # noqa: E402
import live  # noqa: E402

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

# The body .github/DISCUSSION_TEMPLATE/committees.yml posts, filled in for #311 (#371).
FORM_311 = """### Question marker

<!-- productswarm-committee question=311 -->

### Question

Committee deliberation for **#311: What should make the reviewer request changes rather than comment or approve?**

The question, its options and the evidence are on #311; read it first. The convening comment, the convener's summary and the owner's ruling stay on #311.

### Members

| Role | Member | Model | Main evidence |
|---|---|---|---|
| **Proposer** | reviewer (`productswarm-reviewer[bot]`) | `claude-opus-5-5` | its own review history, `roles/reviewer.md`, GOV-0011 |
| **Challenger** | builder (`productswarm-builder[bot]`) | `claude-sonnet-5-5` (this committee only) | the reviews it received and how it responded; GOV-0011's `[respond]` loop |
| **Domain reviewer** | planner (`productswarm-planner[bot]`) | `claude-opus-5-5` | the B eval: `evals/README.md`, `evals/results.md`, the C stage 2 bar |

Convener: the owner (`mattmcalister`), who also ratifies. Diversity rule (§7.2): two models **and** three evidence bases.

### Rules

1. **Rounds:** at most 3. In each round, members post in order: proposer, challenger, domain reviewer.
2. **One post per member per round,** as a **top-level comment** in this Discussion, headed `Round N: <role>`. Replies to other members' points go inside that one post, quoting what they answer. No replies to your own post, and no extra posts (§8).
3. **Structure:** **Position** / **Evidence** / **Concerns** / **Recommendation**. Evidence cites PRs, review links, record lines or `evals/results.md` cases, not recollection.
4. **The goal is a rule the reviewer can apply mechanically,** with an answer for each of #175's nine cases and for #251 vs #289. Say which option (on #311) you back, or propose a variant.
5. **No vote.** `product-scope` has no `vote_eligible` identities, so the committee recommends and the owner ratifies. State any dissent plainly; it goes into the record.
6. **Stop early** if, after a round, all three recommendations agree. The convener then posts the summary on #311.

Sign every post as usual: `-- <role> (<model>)`."""

# The same form posted without filling in the members (placeholders left as they are).
FORM_BLANK = FORM_311.replace("question=311", "question=NNN").replace(
    "reviewer (`productswarm-reviewer[bot]`) | `claude-opus-5-5`",
    "<role> (`productswarm-<role>[bot]`) | `<model>`")

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


# The opening of each #314 post's Position section, in POSTS_314's order (#404).
POSITIONS_314 = [
    "I back **option 3 with two changes** (call it 3b). The test for red is the evidence attached to a finding.",
    "I back **option 3, in the proposer's 3b form**, with four amendments (3c below). I tried to break the rule\n"
    "and couldn't.",
    "I back **option 3 in the proposer's 3b form, with the challenger's four amendments (3c)**, plus one "
    "condition from the eval's side (call it **3c+E**): **the eval rubric has to change in step with the "
    "reviewer's rule, and the C stage 2 bar has to stay what the owner pre-registered.**\n\nThe reason is "
    "measurability.",
    "I now back **3c+E**: my 3b, plus all four of the challenger's amendments, plus the planner's E1–E3 as a "
    "separate eval issue. I add one precedence rule.",
    "I now back **3c+E** as the proposer restated it in Round 2, with one added condition on the "
    "Overstep-over-red precedence rule (below). No dissent on the red test or on the block list.",
    "I back **option 3 as 3c+E**, as the proposer restated it in Round 2, plus both of the challenger's Round 2 "
    "additions. I drop my one point of dispute."]
DEFAULT_POSITION = "I back **something else** here. Nothing more from this post."


def post(rnd, seat, minute, reco, model=None, login=None, day=4, hour=14, position=DEFAULT_POSITION):
    role, table_model = SEATS[seat]
    pos = "" if position is None else f"### Position\n\n{position}\n\n"
    body = (f"## Round {rnd}: {seat} ({role})\n\n{pos}"
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
                                         "date": "2026-11-04", "shape": None})
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

    def test_form_body_for_311(self):
        """The Discussion form's body parses like #314's, linked by its marker alone (#371)."""
        com = self.one([discussion(title="Committee for #N: reviewer", body=FORM_311)])
        ref = self.one([discussion()])
        self.assertEqual((com["question"], com["status"]), (311, "record GOV-0021"))
        drop = lambda ms: [{k: v for k, v in m.items() if k != "evidence"} for m in ms]
        self.assertEqual(drop(com["members"]), drop(ref["members"]))
        for key in ("diversity", "rounds_used", "next_seat", "missed", "notes"):
            self.assertEqual(com[key], ref[key], key)
        self.assertEqual(len(com["posts"]), 6)

    def test_unfilled_form_is_unparsed(self):
        com = self.one([discussion(number=405, title="Committee for #N: ", body=FORM_BLANK)])
        self.assertEqual(com["status"], "unparsed")

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
        pages = g.render(model)
        self.assertNotIn('class="desk"', pages["index.html"])            # it ended: no desk (#404)
        self.assertIn("<h2>Past committees</h2>", pages["decisions.html"])   # it ended
        page = "".join(pages.values())
        self.assertNotIn("<script", page.replace(f"<script>{live.script()}</script>", "").lower())
        for text in (repr(model), page):
            self.assertNotIn("2.89", text)
            self.assertNotIn("Cost", text)
            self.assertNotIn("2 rounds of 3", text)   # nor any other summary text
            self.assertNotIn("Nothing more", text)    # nor round-post text beyond the phrase
            self.assertNotIn("Not this", text)        # and the Position's first sentence (#404)

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
        for page in g.render(g.build(data, now, dt.timedelta(minutes=15))).values():
            self.assertNotIn("Committees", page)

    def test_open_committees_are_on_the_desk(self):
        # g.build reads the checkout's records, where #311 has GOV-0021: use a question without one.
        data = {"repo": REPO, "issues": [], "comments": {}, "prs": [], "reviews": {},
                "committees": {"discussions": [discussion(title="Committee for #9999: x",
                                                          comments=[post(*POSTS_314[0])])],
                               "questions": {9999: question(False, False)}, "notes": []}}
        now = dt.datetime(2026, 11, 4, 15, 0, tzinfo=dt.timezone.utc)
        pages = g.render(g.build(data, now, dt.timedelta(minutes=15)))
        self.assertIn('<section class="desk">', pages["index.html"])     # the desk (#404)
        self.assertNotIn('<table class="grid">', pages["index.html"])
        self.assertIn("<h2>Committees</h2>", pages["decisions.html"])     # the grid moved (#404)
        self.assertIn('<table class="grid">', pages["decisions.html"])
        self.assertNotIn("Committees</h2>", pages["operations.html"])

    def test_parts(self):
        open_one = discussion(comments=[post(*POSTS_314[0])])
        (self.decisions / "GOV-0021-when.md").unlink()
        m = self.build([open_one], {311: question(False, False)}, [])
        self.assertIn("<h2>Committees</h2>", c.render(m, REPO, part="open"))
        self.assertEqual(c.render(m, REPO, part="ended"), "")


def posts_314(n: int, **kw) -> list[dict]:
    """#314's first n posts, with their real Position openings."""
    return [post(*p, position=pos, **kw) for p, pos in list(zip(POSTS_314, POSITIONS_314))[:n]]


class DeskTest(Fixture):
    """The committee desk (#404), over #314's posts with #311 still open."""
    def setUp(self):
        super().setUp()
        (self.decisions / "GOV-0021-when.md").unlink()

    def open(self, comments):
        return self.build([discussion(comments=comments)], {311: question(False, False)})

    def desk(self, comments):
        (d,) = c.desk_states(self.open(comments))
        return d

    def test_summary_is_the_positions_first_sentence(self):
        com = self.one([discussion(comments=posts_314(6))], {311: question(False, False)})
        self.assertEqual([p["summary"] for p in com["posts"]], [
            "I back option 3 with two changes (call it 3b).",
            "I back option 3, in the proposer's 3b form, with four amendments (3c below).",
            "I back option 3 in the proposer's 3b form, with the challenger's four amendments (3c), plus one "
            "condition from the eval's side (call it…",
            "I now back 3c+E: my 3b, plus all four of the challenger's amendments, plus the planner's E1–E3 as "
            "a separate eval issue.",
            "I now back 3c+E as the proposer restated it in Round 2, with one added condition on the "
            "Overstep-over-red precedence rule (below).",
            "I back option 3 as 3c+E, as the proposer restated it in Round 2, plus both of the challenger's "
            "Round 2 additions."])
        self.assertTrue(all(len(p["summary"]) <= c.SUMMARY_LEN for p in com["posts"]))

    def test_missing_position_section(self):
        comments = posts_314(1) + [post(*POSTS_314[1], position=None)]
        d = self.desk(comments)
        self.assertIsNone(d["seats"][1]["summary"])
        self.assertEqual(d["seats"][1]["recommendation"], "Option 3, as the proposer's 3b, plus these four "
                         "amendments (3c)")
        html = c.desk(self.open(comments), REPO)
        self.assertIn('<p class="muted">no Position section</p>', html)
        self.assertEqual(c.summary("### Position\n\n\n### Evidence\n\nx"), None)

    def test_band_and_cards_mid_round_2(self):
        d = self.desk(posts_314(4))
        self.assertEqual((d["round"], d["max_rounds"], d["waiting_on"]), (2, 3, "challenger"))
        proposer, challenger, domain = d["seats"]
        self.assertEqual(proposer["recommendation"], "Option 3 as 3c")
        self.assertEqual(proposer["swing"], "moved")
        self.assertEqual(proposer["moved_from"], "Option 3, with changes 1 and 2 (3b)")
        self.assertEqual(proposer["round"], 2)
        self.assertEqual((challenger["swing"], challenger["round"]), (None, 1))   # no round 2 post yet
        html = c.desk(self.open(posts_314(4)), REPO)
        self.assertIn('<div class="band"><span class="live">LIVE</span><span class="tag">Committee</span>'
                      f'<span class="q"><a href="{QURL}">#311</a></span><span>Round 2 of 3</span>'
                      '<span>waiting on challenger</span>', html)
        self.assertIn('<div class="reco">Option 3 as 3c</div>'
                      '<div class="swing">moved from Option 3, with changes 1 and 2 (3b)</div>'
                      "<blockquote>“I now back 3c+E: my 3b, plus all four of the challenger&#x27;s amendments, "
                      "plus the planner&#x27;s E1–E3 as a separate eval issue.”</blockquote>"
                      f'<div class="when"><a href="{DURL}#discussioncomment-223">round 2 · 11-04 14:23 UTC</a>'
                      "</div>", html)
        self.assertIn('<div class="seat up">', html)                  # the challenger is up next
        self.assertEqual(html.count('<div class="seat">') + html.count('<div class="seat up">'), 3)
        self.assertEqual(html.count("var(--red)"), 0)                 # red comes from the CSS, LIVE only

    def test_bar_for_each_round(self):
        # Round 1: three different phrases. Round 2: 3c, 3c+E, 3c+E (two agree, up from one).
        self.assertEqual(self.desk(posts_314(3))["consensus"]["text"], "1 of 3")
        self.assertEqual(self.desk(posts_314(6))["consensus"],
                         {"agree": 2, "seats": 3, "converging": True, "consensus": False,
                          "text": "2 of 3 · converging"})
        # Round 3: the proposer joins the others.
        third = posts_314(6) + [post(3, "proposer", 40, "**Option 3 as 3c+E**")]
        self.assertEqual(self.desk(third)["consensus"]["text"], "consensus")
        self.assertEqual(self.desk(third)["seats"][0]["moved_from"], "Option 3 as 3c")
        html = c.desk(self.open(third), REPO)
        self.assertIn('<div class="bar done"><span class="marks"><span class="on"></span>'
                      '<span class="on"></span><span class="on"></span></span><b>consensus</b></div>', html)

    def test_bar_without_a_rise_and_held(self):
        held = posts_314(3) + [post(2, "proposer", 30, "**Option 3, with changes 1 and 2 (3b).**")]
        d = self.desk(held)
        self.assertEqual(d["consensus"]["text"], "1 of 3")                # no rise: no "converging"
        self.assertEqual((d["seats"][0]["swing"], d["seats"][0]["moved_from"]), ("held", None))
        self.assertIn('<div class="swing">held</div>', c.desk(self.open(held), REPO))

    def test_convened_with_no_posts(self):
        d = self.desk([])
        self.assertEqual((d["round"], d["waiting_on"], d["consensus"]["text"]), (1, "proposer", "0 of 3"))
        html = c.desk(self.open([]), REPO)
        self.assertEqual(html.count('<div class="reco none">no recommendation yet</div>'), 3)
        self.assertIn('<div class="when muted">up next</div>', html)
        self.assertEqual(html.count('<div class="when muted">not posted yet</div>'), 2)

    def test_no_open_committee_no_desk(self):
        (self.decisions / "GOV-0021-when.md").write_text('---\nid: GOV-0021\nquestion: "#311"\n---\n')
        m = self.build([discussion()])
        self.assertEqual(c.desk_states(m), [])
        self.assertEqual(c.desk(m, REPO), "")
        self.assertEqual(c.desk(None, REPO), "")
        self.assertEqual(c.desk(self.build([discussion(number=400, title="chat", body="x")]), REPO), "")

    def test_state_json_carries_the_desk(self):
        import json
        import state as st
        data = {"repo": REPO, "issues": [], "comments": {}, "prs": [], "reviews": {},
                "committees": {"discussions": [discussion(title="Committee for #9999: x", comments=posts_314(4))],
                               "questions": {9999: question(False, False)}, "notes": []}}
        now = dt.datetime(2026, 11, 4, 15, 0, tzinfo=dt.timezone.utc)
        out = json.loads(json.dumps(st.state(g.build(data, now, dt.timedelta(minutes=15)))))
        (d,) = out["committee_desk"]
        self.assertEqual(sorted(d), ["consensus", "discussion", "max_rounds", "question", "question_title",
                                     "question_url", "round", "seats", "url", "waiting_on"])
        self.assertEqual(sorted(d["seats"][0]), ["model", "moved_from", "posted", "recommendation", "role",
                                                 "round", "seat", "summary", "swing", "url"])
        self.assertEqual(d["seats"][0]["posted"], "2026-11-04T14:23:00Z")
        self.assertEqual(d["consensus"]["text"], "2 of 3 · converging")
        data["committees"]["discussions"] = []
        self.assertEqual(st.state(g.build(data, now, dt.timedelta(minutes=15)))["committee_desk"], [])


class PastTest(Fixture):
    """Past committees as desk cards (#409), over #314 with #311 closed."""
    INDEX = (HERE.parent / "governance" / "INDEX.md").read_text()

    def model(self, discussions, questions=None):
        data = {"repo": REPO, "issues": [], "comments": {}, "prs": [], "reviews": {}, "index": self.INDEX,
                "committees": {"discussions": discussions,
                               "questions": questions if questions is not None else {311: question()},
                               "notes": []}}
        now = dt.datetime(2026, 11, 5, 9, 0, tzinfo=dt.timezone.utc)
        orig = c.build      # read records from the fixture's decisions, not the checkout's
        with unittest.mock.patch.object(c, "build", lambda raw: orig(raw, decisions=self.decisions, owner=OWNER)):
            return g.build(data, now, dt.timedelta(minutes=15))

    def test_314_card(self):
        m = self.model([discussion()])
        (p,) = c.past_states(m["committees"], g.rulings(m), REPO)
        self.assertEqual(p["record"], {"id": "GOV-0021", "url": f"https://github.com/{REPO}/blob/main/"
                                                                  "governance/decisions/GOV-0021-when.md"})
        self.assertTrue(p["summary"].startswith("Reviewer requests changes only for a numbered block-list"))
        self.assertEqual(p["consensus"], {"text": "dissent: proposer", "consensus": False,
                                          "dissent": ["proposer"]})
        self.assertEqual((p["rounds_used"], p["max_rounds"], p["stopped_early"]), (2, 3, False))
        self.assertEqual(p["models"], ["claude-opus-5-5", "claude-sonnet-5-5"])
        self.assertTrue(p["diversity_met"])
        self.assertEqual(p["minutes"], 7)          # 14:18 to 14:25
        self.assertEqual((p["swing"], p["seats"]), (3, 3))   # every seat moved from round 1

        desk = g.render(m)["index.html"]
        self.assertIn("<h2>Past committees</h2>", desk)
        self.assertIn(f'<div class="past"><div class="rec"><a href="https://github.com/{REPO}/blob/main/'
                      'governance/decisions/GOV-0021-when.md">GOV-0021</a></div>', desk)
        self.assertIn("<blockquote>“Reviewer requests changes only for a numbered block-list finding", desk)
        self.assertIn('<div class="call split">dissent: proposer</div>', desk)
        self.assertIn("<li>2 of 3 rounds</li>", desk)
        self.assertIn("<li><code>claude-opus-5-5</code>, <code>claude-sonnet-5-5</code> · §7.2 met</li>", desk)
        self.assertIn("<li>7 minutes first to last post</li>", desk)
        self.assertIn("<li>swing: 3 of 3 seats changed</li>", desk)
        self.assertNotIn('<table class="grid">', desk)                 # the grids stay on decisions
        self.assertIn('<table class="grid">', g.render(m)["decisions.html"])

    def test_no_record_yet(self):
        (self.decisions / "GOV-0021-when.md").unlink()
        m = self.model([discussion()])                     # #311 closed, but no record merged
        (p,) = c.past_states(m["committees"], g.rulings(m), REPO)
        self.assertIsNone(p["record"])
        self.assertIsNone(p["summary"])
        self.assertEqual(p["consensus"]["text"], "dissent: proposer")
        desk = g.render(m)["index.html"]
        self.assertIn('<div class="rec"><span class="muted">no record yet</span></div>', desk)
        self.assertIn('<p class="muted">no ruling recorded</p>', desk)

    def test_record_not_in_the_index(self):
        m = self.model([discussion()])
        (p,) = c.past_states(m["committees"], {}, REPO)
        self.assertIsNone(p["summary"])
        self.assertIn("not in governance/INDEX.md yet", c.past(m["committees"], {}, REPO))

    def test_stopped_early(self):
        agree = [post(1, "proposer", 18, "**Option 3.**"), post(1, "challenger", 21, "**Option 3**"),
                 post(1, "domain reviewer", 30, "**option 3.**")]
        m = self.model([discussion(comments=agree)])
        (p,) = c.past_states(m["committees"], g.rulings(m), REPO)
        self.assertEqual(p["consensus"], {"text": "consensus after round 1", "consensus": True, "dissent": []})
        self.assertEqual((p["rounds_used"], p["stopped_early"], p["minutes"], p["swing"]), (1, True, 12, 0))
        desk = g.render(m)["index.html"]
        self.assertIn('<div class="call">consensus after round 1</div>', desk)
        self.assertIn("<li>1 of 3 rounds · stopped early</li>", desk)
        self.assertIn("<li>swing: 0 of 3 seats changed</li>", desk)

    def test_open_committee_has_no_card(self):
        (self.decisions / "GOV-0021-when.md").unlink()
        m = self.model([discussion()], {311: question(False, False)})
        self.assertEqual(c.past_states(m["committees"], g.rulings(m), REPO), [])
        self.assertNotIn("Past committees", g.render(m)["index.html"])
        self.assertEqual(c.past(None, {}, REPO), "")

    def test_state_json_carries_the_cards(self):
        import state as st
        out = json.loads(json.dumps(st.state(self.model([discussion()]))))
        (p,) = out["past_committees"]
        self.assertEqual(sorted(p), ["consensus", "discussion", "diversity_met", "max_rounds", "minutes",
                                     "models", "question", "question_title", "question_url", "record",
                                     "rounds_used", "seats", "stopped_early", "summary", "swing", "url"])
        self.assertEqual(p["record"]["id"], "GOV-0021")
        self.assertNotIn("2.89", json.dumps(out))


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
                with mock.patch.object(g.precedent, "published", return_value=None):   # no Pages fetch in tests
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
