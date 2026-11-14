"""Tests for the label-set and labelled-set formats and the YAML subset (#1010)."""
import unittest
from pathlib import Path

import labelset as l

HERE = Path(__file__).resolve().parent
GOOD = """
threshold: 0.5
max_calls: 10
labels:
  - name: a
    definition: Is a.
    examples: ["one", "two"]
  - name: b
    definition: Is b.
    examples:
      - one
      - "two, quoted"
pass_mark:
  accuracy: 0.5
"""


class YamlSubsetTest(unittest.TestCase):
    def test_nested_mappings_lists_and_scalars(self):
        self.assertEqual(l.read_yaml("a: 1\nb:\n  c: 'it''s'  # note\n  d: [x, \"y, z\"]\ne:\n  - k: true\n    m: 0.5\n  - plain text\n"),
                         {"a": 1, "b": {"c": "it's", "d": ["x", "y, z"]},
                          "e": [{"k": True, "m": 0.5}, "plain text"]})

    def test_a_colon_inside_a_value_is_kept(self):
        self.assertEqual(l.read_yaml("a: see: this\nb: http://x/y"), {"a": "see: this", "b": "http://x/y"})

    def test_unsupported_yaml_is_refused_not_guessed(self):
        for text in ("a: |\n  block", "a: {x: 1}", "a: 1\n   b: 2", "a: 1\na: 2", "a:\nb: 1", "a: &x 1"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                l.read_yaml(text)


class LabelSetTest(unittest.TestCase):
    def test_the_fixture_loads_with_defaults_and_its_hash(self):
        ls = l.load_labelset(HERE / "testdata" / "labelsets" / "fixture.yml")
        self.assertEqual(ls.name, "fixture")
        self.assertEqual(ls.label_names, ["bug", "feature", "docs"])
        self.assertEqual(ls.flag_names, ["urgent"])
        self.assertEqual((ls.threshold, ls.runs, ls.max_calls), (0.6, 3, 30))
        self.assertEqual(ls.pass_mark.min_recall, {"bug": 0.6})
        self.assertEqual(len(ls.sha), 64)

    def test_runs_defaults_to_three(self):
        ls, problems = l.parse_labelset("x", GOOD)
        self.assertEqual(problems, [])
        self.assertEqual(ls.runs, 3)

    def test_every_problem_is_listed(self):
        bad = GOOD.replace("threshold: 0.5", "threshold: 2").replace(
            'examples: ["one", "two"]', 'examples: ["one"]').replace(
            "accuracy: 0.5", "accuracy: 0.5\n  min_recall:\n    zz: 0.5") + "colour: red\n"
        ls, problems = l.parse_labelset("x", bad)
        self.assertIsNone(ls)
        text = "\n".join(problems)
        for want in ("threshold", "examples must be a list of 2 or 3", "unknown label 'zz'",
                     "unknown key 'colour'"):
            self.assertIn(want, text)

    def test_required_keys(self):
        _, problems = l.parse_labelset("x", "labels:\n  - name: a\n    definition: d\n    examples: [p, q]\n")
        for k in ("threshold", "max_calls", "pass_mark"):
            self.assertIn(f"'{k}' is required", problems)
        self.assertIn("labels: at least two labels are needed", problems)

    def test_needs_human_is_not_a_label_name(self):
        _, problems = l.parse_labelset("x", GOOD.replace("name: b", "name: needs human"))
        self.assertTrue(any("other than 'needs human'" in p for p in problems))


class ItemsTest(unittest.TestCase):
    def setUp(self):
        self.ls, _ = l.parse_labelset("x", GOOD)

    def test_items_parse(self):
        items, problems = l.parse_items(
            '{"id": "1", "text": "t", "label": "a", "split": "dev", "labelled_by": "owner", "week": "2026-W45"}\n\n', self.ls)
        self.assertEqual(problems, [])
        self.assertEqual(items[0].week, "2026-W45")
        self.assertEqual(items[0].flags, {})

    def test_bad_items_are_refused(self):
        text = "\n".join([
            '{"id": "1", "text": "t", "label": "zz", "split": "dev", "labelled_by": "o"}',
            '{"id": "2", "text": "t", "label": "a", "split": "train", "labelled_by": "o"}',
            '{"id": "3", "text": "t", "label": "a", "split": "dev"}',
            '{"id": "4", "text": "t", "label": "a", "split": "dev", "labelled_by": "o", "flags": {"hot": true}}',
            '{"id": "4", "text": "t", "label": "a", "split": "dev", "labelled_by": "o"}',
            'not json'])
        items, problems = l.parse_items(text, self.ls)
        joined = "\n".join(problems)
        for want in ("label 'zz'", "split must be dev or test", "'labelled_by' must be",
                     "flag 'hot'", "id '4' appears twice", "line 6: not JSON"):
            self.assertIn(want, joined)

    def test_load_raises_format_error(self):
        with self.assertRaises(l.FormatError):
            l.load_items(HERE / "testdata" / "data" / "missing.jsonl", self.ls)


if __name__ == "__main__":
    unittest.main()
