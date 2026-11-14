"""Tests for classify/effort_data.py and the effort label set (#1011). No network, no model:
PRs come from in-memory fixtures and the model is a fake runner."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import classifier
import effort_data as ed
import labelset as lsmod

HERE = Path(__file__).resolve().parent


def pr(n, title, merged, body="", paths=("launcher/watch.py",), issues=()):
    return {"number": n, "title": title, "body": body, "mergedAt": merged,
            "files": {"totalCount": len(paths), "nodes": [{"path": p} for p in paths]},
            "closingIssuesReferences": {"nodes": [{"number": i, "title": f"Issue {i}"}
                                                  for i in issues]}}


PRS = [
    pr(10, "Add swarm acts", "2026-11-02T10:00:00Z", "Adds a command.", issues=[9]),
    pr(12, "Fix swarm acts on an empty day", "2026-11-05T10:00:00Z", "Fixes #10's crash."),
    pr(14, "GOV-0099: a ruling", "2026-11-06T10:00:00Z", paths=("governance/x.md",)),
    pr(16, "Brief: what the Desk needs", "2026-11-07T10:00:00Z", paths=("research/x.md",)),
    pr(18, "Tests no longer pin the manifest", "2026-11-08T10:00:00Z",
       paths=("launcher/test_watch.py",)),
    pr(20, "Fix an old bug", "2026-11-30T10:00:00Z", "Fixes #10."),   # after the cut-off
] + [pr(30 + i, f"Desk panel {i}", f"2026-11-{3 + i % 9:02d}T10:00:00Z") for i in range(24)]


def fake_runner(calls):
    def run(model, system, user, budget):
        calls.append(budget)
        title = user.split("Title: ", 1)[1].split("\n", 1)[0]
        label = ("governance" if title.startswith("GOV") else "knowledge" if "Brief" in title
                 else "upkeep" if "Tests" in title else "capability")
        fix = title.startswith("Fix")
        return json.dumps({"label": label, "flags": {"fix": fix}, "evidence": title}), 0.001
    return run


class Base(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        (self.root / "labelsets").mkdir()
        shutil.copy(HERE / "labelsets" / "effort.yml", self.root / "labelsets")
        self.ls = lsmod.load_labelset(self.root / "labelsets" / "effort.yml")
        self.said, self.calls = [], []

    def build(self, live=True, prs=PRS):
        return ed.build(self.root, prs, live, "m", fake_runner(self.calls), self.said.append)

    def rows(self):
        return ed.read_rows(self.root / "data" / "effort.jsonl")

    @property
    def review(self):
        return self.root / "review" / "effort.md"

    def edit(self, item_id, **fields):
        lines, cur = self.review.read_text().splitlines(), None
        for i, line in enumerate(lines):
            if line.startswith("## pr-"):
                cur = line.split(" ")[1]
            for k, v in fields.items():
                if cur == item_id and line.startswith(f"{k}:"):
                    lines[i] = f"{k}: {v}"
        self.review.write_text("\n".join(lines) + "\n")


class LabelSetTest(unittest.TestCase):
    def test_four_labels_one_flag_and_a_boundary_rule_on_each_label(self):
        ls = lsmod.load_labelset(HERE / "labelsets" / "effort.yml")
        self.assertEqual(ls.label_names, ["capability", "upkeep", "governance", "knowledge"])
        self.assertEqual(ls.flag_names, ["fix"])
        for lb in ls.labels:
            self.assertTrue(lb.boundary, lb.name)
            self.assertGreaterEqual(len(lb.examples), 2, lb.name)
        self.assertEqual(set(ed.rule_names(ls)), {
            "feature-and-fix", "role-prompt-capability", "tests-only", "ruling-implementation",
            "brief-for-capability"})

    def test_the_checked_in_labelled_set_loads_and_keeps_its_drafts_apart(self):
        ls = lsmod.load_labelset(HERE / "labelsets" / "effort.yml")
        items = lsmod.load_items(HERE / "data" / "effort.jsonl", ls)
        self.assertTrue(items)
        self.assertLessEqual({it.labelled_by for it in items}, {"draft", "owner"})
        rules = set(ed.rule_names(ls))
        for it in items:
            self.assertTrue(it.week and it.text.startswith("Title: "), it.id)
            if it.hard:
                self.assertIn(it.hard, rules)
                self.assertEqual(it.split, "test", it.id)


class ItemTest(unittest.TestCase):
    def test_text_has_title_issue_paths_and_body(self):
        t = ed.item_text(PRS[0])
        self.assertEqual(t.splitlines()[:4], [
            "Title: Add swarm acts", "Linked issue: #9 Issue 9",
            "Paths touched (1): launcher/watch.py", "Body:"])

    def test_long_bodies_and_path_lists_are_cut(self):
        p = pr(1, "t", "2026-11-02T00:00:00Z", "x" * 9000, paths=[f"f{i}" for i in range(50)])
        p["files"]["totalCount"] = 120
        t = ed.item_text(p)
        self.assertIn("Paths touched (120):", t)
        self.assertIn("and 80 more", t)
        self.assertLess(len(t), ed.BODY_MAX + 600)

    def test_week_and_cutoff(self):
        self.assertEqual(ed.iso_week("2026-11-02T10:00:00Z"), "2026-W45")
        self.assertTrue(ed.merged_on_or_before({"mergedAt": "2026-11-13T23:59:59Z"}))
        self.assertFalse(ed.merged_on_or_before({"mergedAt": "2026-11-14T00:00:00Z"}))

    def test_fixed_pr_is_a_named_pr_merged_in_the_14_days_before(self):
        merged = {p["number"]: p for p in PRS}
        self.assertEqual(ed.fixed_pr(PRS[1], merged), 10)
        self.assertIsNone(ed.fixed_pr(PRS[5], merged))      # 28 days later
        self.assertIsNone(ed.fixed_pr(PRS[0], merged))      # names no PR


class BuildTest(Base):
    def test_build_drafts_every_pr_up_to_the_cutoff(self):
        self.assertEqual(self.build(), 0)
        rows = self.rows()
        self.assertEqual(len(rows), len(PRS) - 1)
        self.assertNotIn("pr-20", rows)
        self.assertTrue(all(r["labelled_by"] == "draft" for r in rows.values()))
        self.assertEqual(rows["pr-12"]["fixes"], 10)
        self.assertTrue(rows["pr-12"]["flags"]["fix"])
        self.assertEqual(rows["pr-14"]["label"], "governance")
        self.assertTrue(all(b <= ed.PER_PR_USD for b in self.calls))
        lsmod.load_items(self.root / "data" / "effort.jsonl", self.ls)

    def test_split_is_about_30_percent_test(self):
        self.build()
        test = sum(r["split"] == "test" for r in self.rows().values())
        self.assertEqual(test, int(len(self.rows()) * ed.TEST_SHARE))

    def test_replay_rebuild_calls_nothing_and_keeps_existing_items(self):
        self.build()
        first = (self.root / "data" / "effort.jsonl").read_text()
        (self.root / "data" / "effort.jsonl").unlink()
        n = len(self.calls)
        self.assertEqual(self.build(live=False), 0)
        self.assertEqual(len(self.calls), n)
        self.assertEqual((self.root / "data" / "effort.jsonl").read_text(), first)
        self.assertEqual(self.build(live=True), 0)
        self.assertEqual(len(self.calls), n)

    def test_replay_without_recordings_drafts_nothing(self):
        self.assertEqual(self.build(live=False), 1)
        self.assertEqual(self.rows(), {})
        self.assertIn("--live drafts them", self.said[-1])

    def test_a_reply_with_no_label_is_retried(self):
        replies = iter(["not json", '{"label": "upkeep", "flags": {}, "evidence": "x"}'])
        def runner(*a):
            self.calls.append(a)
            return next(replies), 0.0
        ed.build(self.root, PRS[:1], True, "m", runner, self.said.append)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.rows()["pr-10"]["label"], "upkeep")


class ReviewTest(Base):
    def setUp(self):
        super().setUp()
        self.build()
        self.assertEqual(ed.write_review(self.root, model="m", say=self.said.append), 0)

    def apply(self):
        return ed.main(["--dir", str(self.root), "apply"], say=self.said.append)

    def test_review_lists_test_items_first_with_draft_and_fields(self):
        text = self.review.read_text()
        self.assertLess(text.index("# Test split"), text.index("# Dev split"))
        self.assertIn("Draft: capability, fix yes. \"Fix swarm acts on an empty day\"", text)
        self.assertIn("[#12](https://github.com/open-agentos/productswarm/pull/12)", text)
        self.assertIn("fix: #10\n", text)

    def test_reviewed_items_become_owner_labels(self):
        self.edit("pr-12", label="upkeep", fix="#10", reviewed="yes")
        self.assertEqual(self.apply(), 0)
        r = self.rows()["pr-12"]
        self.assertEqual((r["label"], r["labelled_by"], r["fixes"], r["flags"]),
                         ("upkeep", "owner", 10, {"fix": True}))
        self.edit("pr-12", fix="no")
        self.assertEqual(self.apply(), 0)
        self.assertNotIn("fixes", self.rows()["pr-12"])
        self.assertIn("reviewed: yes", self.review.read_text())

    def test_a_label_change_without_reviewed_is_refused_and_nothing_changes(self):
        before = (self.root / "data" / "effort.jsonl").read_text()
        self.edit("pr-12", label="upkeep")
        self.edit("pr-14", label="nonsense", reviewed="yes")
        self.assertEqual(self.apply(), 2)
        self.assertIn("set reviewed: yes", self.said[-1])
        self.assertIn("label 'nonsense'", self.said[-1])
        self.assertEqual((self.root / "data" / "effort.jsonl").read_text(), before)

    def test_an_owner_label_cant_go_back_to_draft(self):
        self.edit("pr-12", reviewed="yes")
        self.apply()
        self.edit("pr-12", reviewed="no")
        self.assertEqual(self.apply(), 2)
        self.assertIn("can't go back to a draft", self.said[-1])

    def test_a_hard_case_moves_to_test_and_a_same_label_draft_moves_out(self):
        rows = self.rows()
        dev = next(i for i, r in rows.items() if r["split"] == "dev" and r["label"] == "capability")
        n_test = sum(r["split"] == "test" for r in rows.values())
        self.edit(dev, hard="feature-and-fix")
        self.assertEqual(self.apply(), 0)
        rows = self.rows()
        self.assertEqual((rows[dev]["split"], rows[dev]["hard"]), ("test", "feature-and-fix"))
        self.assertEqual(sum(r["split"] == "test" for r in rows.values()), n_test)
        self.assertIn(f"## {dev} · test", self.review.read_text())

    def test_an_unknown_hard_rule_is_refused(self):
        self.edit("pr-12", hard="made-up")
        self.assertEqual(self.apply(), 2)
        self.assertIn("isn't a boundary rule", self.said[-1])

    def test_review_refuses_to_overwrite_unapplied_edits(self):
        self.edit("pr-12", reviewed="yes")
        with self.assertRaises(ed.Problem):
            ed.write_review(self.root, model="m")
        self.assertEqual(ed.write_review(self.root, force=True, model="m", say=self.said.append), 0)

    def test_check_fails_until_test_items_are_owner_labelled_with_hard_cases(self):
        self.assertEqual(ed.check(self.root, self.said.append), 1)
        self.assertTrue(any("labelled by the owner: 0 of" in s for s in self.said))
        rows = self.rows()
        for r in rows.values():
            if r["split"] == "test":
                r["labelled_by"] = "owner"
        for k, rule in enumerate(ed.rule_names(self.ls) * 5):
            r = list(rows.values())[k]
            r["split"], r["labelled_by"], r["hard"] = "test", "owner", rule
        ed.write_rows(self.root / "data" / "effort.jsonl", rows)
        self.said.clear()
        self.assertEqual(ed.check(self.root, self.said.append), 0, self.said)


if __name__ == "__main__":
    unittest.main()
