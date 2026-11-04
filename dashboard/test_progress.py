"""Tests for dashboard/progress.py (#357). Canned text and API data only; nothing calls GitHub.

Run: python3 -m unittest discover -s dashboard
"""
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import progress as p  # noqa: E402

REPO = "open-agentos/productswarm"

PRODUCT = """# Product brief

## v2: wake-up loop

### Stage Z: not v3

| # | Issue | What | PR |
|---|---|---|---|
| Z1 | #1 | outside v3 | |

## v3: evals, digest and Actions

GOV-0015 makes v3 three stages. C stage 2 (builders and docs in Actions) comes after these and is not planned.

### Stage B: evals (done)

| # | Issue | What | PR |
|---|---|---|---|
| B1 | #172 | Eval rubric | #197 |
| B2 | #173 | gather.py, see #999 in the What column | #181 |

Result: inconclusive.

### Stage F: needs-you digest

| # | Issue | What | PR |
|---|---|---|---|
| F1 | #210 | TTL | |
| — | — | a row with no issue | |
| F2 | #211 | digest.py | |

### Stage C1: reviewer in Actions

| # | Issue | What | PR |
|---|---|---|---|
| C1.1 | #214 | check | |

C1.5 to C1.9 are the reconciler, see #255.

### Non-goals for v3 now

| # | Issue |
|---|---|
| X | #500 |

## Open decisions
"""

RESULTS = """# Results

### Against the bar

| Bar line | Result |
|---|---|
| 1. Agreement | pass |

**Result: inconclusive, not passed.** The eval found no `unmet` item.

### Calibration

**Result: pass.** Not the bar.
"""


def red_data(start=None, prs=()):
    return {"start": start, "prs": list(prs)}


START = {"number": 336, "mergedAt": "2026-11-04T16:37:07Z",
         "closingIssuesReferences": [{"number": 329}]}


def red_pr(n, reds, state="OPEN"):
    reviews = [{"user": {"login": "productswarm-reviewer[bot]"}, "state": "CHANGES_REQUESTED",
                "body": "", "submitted_at": f"2026-11-05T{h:02d}:00:00Z"} for h in range(reds)]
    return {"number": n, "state": state, "author": {"login": "app/productswarm-builder"},
            "reviews": reviews, "closingIssuesReferences": [{"number": 1}]}


def model(states=None, results=RESULTS, red=None, product=PRODUCT):
    if states is None:
        states = {172: "CLOSED", 173: "CLOSED", 210: "CLOSED", 211: "OPEN", 214: "OPEN", 331: "OPEN"}
    return p.build({"product": product, "results": results, "states": states,
                    "red": red_data() if red is None else red})


class Stages(unittest.TestCase):
    def test_parses_v3_stages_only(self):
        st = p.parse_stages(PRODUCT)
        self.assertEqual([s["name"] for s in st], ["B: evals", "F: needs-you digest",
                                                   "C1: reviewer in Actions"])
        self.assertEqual([s["done"] for s in st], [True, False, False])

    def test_issue_column_only_and_rows_without_a_number_skipped(self):
        st = p.parse_stages(PRODUCT)
        self.assertEqual(st[0]["issues"], [172, 173])     # not #197 (PR) nor #999 (What)
        self.assertEqual(st[1]["issues"], [210, 211])     # the "—" row is skipped
        self.assertEqual(st[2]["issues"], [214])          # not #255 in prose, not #500 below

    def test_no_v3_section(self):
        self.assertEqual(p.parse_stages("# nothing"), [])
        self.assertEqual(p.c_stage_2("# nothing"), "see PRODUCT.md")

    def test_counts_and_c_stage_2(self):
        m = model()
        b, f, c1 = m["stages"]
        self.assertEqual((b["closed"], f["closed"], f["open"], c1["open"]), ([172, 173], [210], [211], [214]))
        self.assertEqual(m["c2"], "not planned (GOV-0015)")
        page = p.render(m, REPO)
        self.assertIn("<td>B: evals</td><td>done · 2 of 2 issues closed</td>", page)
        self.assertIn("1 of 2 issues closed · open: "
                      f'<a href="https://github.com/{REPO}/issues/211">#211</a>', page)
        self.assertIn("<td>C stage 2</td><td>not planned (GOV-0015)</td>", page)

    def test_states_unread(self):
        m = p.build({"product": PRODUCT, "results": RESULTS, "states": None, "red": None})
        page = p.render(m, REPO)
        self.assertIn(p.UNREAD, page)
        self.assertIn("): unknown</li>", page)        # the gate


class EvalBar(unittest.TestCase):
    def test_result_line_under_against_the_bar(self):
        self.assertEqual(p.bar_result(RESULTS), "inconclusive, not passed")
        self.assertIn(f'<a href="https://github.com/{REPO}/blob/main/evals/results.md">Eval bar</a>: '
                      "inconclusive, not passed", p.render(model(), REPO))

    def test_missing_result_line_is_unknown(self):
        no_line = RESULTS.replace("**Result: inconclusive, not passed.**", "Inconclusive.")
        self.assertIsNone(p.bar_result(no_line))       # not the Calibration section's line
        self.assertIsNone(p.bar_result(None))
        self.assertIn("Eval bar</a>: unknown", p.render(model(results=no_line), REPO))


class Gate(unittest.TestCase):
    def test_open_is_not_run(self):
        self.assertEqual(model()["gate"], "not run")

    def test_closed_is_done(self):
        m = model(states={331: "CLOSED"})
        self.assertEqual(m["gate"], "done, see #331")

    def test_unknown_state(self):
        self.assertIsNone(model(states={})["gate"])


class RedCheck(unittest.TestCase):
    def test_before_329_merged(self):
        m = model()
        self.assertEqual(m["red"]["start_pr"], None)
        self.assertIn("not started: no reds count until", p.render(m, REPO))

    def test_counts_and_revisit_pending(self):
        m = model(red=red_data(START, [red_pr(400, 1), red_pr(401, 2)]))
        self.assertEqual((m["red"]["counted"], m["red"]["at_bound"], m["red"]["revisit"]), (2, 0, None))
        self.assertIn("2 of 5 reds counted, 0 reached the 2-round bound; revisit if more than 2 · "
                      "not yet decided", p.render(m, REPO))

    def test_revisit_yes_once_settled(self):
        prs = [red_pr(400 + i, 3 if i < 3 else 1, state="MERGED") for i in range(5)]
        m = model(red=red_data(START, prs))
        self.assertEqual((m["red"]["counted"], m["red"]["at_bound"], m["red"]["revisit"]), (5, 3, True))
        self.assertIn("revisit: yes", p.render(m, REPO))

    def test_shows_no_cost(self):
        page = p.render(model(red=red_data(START, [red_pr(400, 1)])), REPO)
        self.assertNotIn("$", page)
        self.assertNotIn("cost", page.lower())


class Fetch(unittest.TestCase):
    def test_one_graphql_query_and_errors_dont_stop_the_page(self):
        calls = []

        def gh_json(*args):
            calls.append(args)
            return {"data": {"repository": {"i172": {"state": "CLOSED"}, "i331": {"state": "OPEN"},
                                            "i173": None}}}
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "PRODUCT.md").write_text(PRODUCT)
            orig = p._red_check
            p._red_check = lambda: (_ for _ in ()).throw(RuntimeError("no network"))
            try:
                data = p.fetch(REPO, gh_json, root=root)
            finally:
                p._red_check = orig
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][:2], ("api", "graphql"))
        self.assertIn("owner=open-agentos", calls[0])
        self.assertEqual(data["states"], {172: "CLOSED", 331: "OPEN"})
        self.assertIsNone(data["results"])                # no evals/results.md in this root
        self.assertIn("red", data["errors"])
        page = p.render(p.build(data), REPO)
        self.assertIn(f"Red check (<a href=\"https://github.com/{REPO}/issues/330\">#330</a>): "
                      f"{p.UNREAD}", page)


class RealFiles(unittest.TestCase):
    def test_this_checkout_parses(self):
        """The real PRODUCT.md and results.md still have the shape the section reads."""
        st = p.parse_stages((p.ROOT / "PRODUCT.md").read_text())
        self.assertEqual([s["name"].split(":")[0] for s in st], ["B", "F", "C1"])
        self.assertTrue(st[0]["done"])
        self.assertTrue(all(s["issues"] for s in st))
        self.assertEqual(p.c_stage_2((p.ROOT / "PRODUCT.md").read_text()), "not planned (GOV-0015)")
        self.assertIsNotNone(p.bar_result((p.ROOT / p.RESULTS).read_text()))


if __name__ == "__main__":
    unittest.main()
