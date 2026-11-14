"""Each metric against values worked out by hand (#1010)."""
import unittest

import labelset as l
import metrics as m
from metrics import Prediction as P

LS = """
threshold: 0.5
max_calls: 10
labels:
  - name: a
    definition: Is a.
    examples: [p, q]
  - name: b
    definition: Is b.
    examples: [p, q]
  - name: c
    definition: Is c.
    examples: [p, q]
flags:
  - name: hot
    definition: Is hot.
pass_mark:
  accuracy: 0.5
  min_recall:
    c: 0.5
"""


def item(i, gold, week=None, hot=False):
    return l.Item(i, "t", gold, "dev", "owner", {"hot": hot}, week)


class MetricsTest(unittest.TestCase):
    """Ten items. Gold: a x4, b x4, c x2. By hand:

        id  gold  pred         week  hot gold/pred
        1   a     a            W1    T/T
        2   a     a            W1    F/T
        3   a     b            W1
        4   a     needs human  W1    T/-
        5   b     b            W2    T/F
        6   b     b            W2
        7   b     b            W2
        8   b     a            W2
        9   c     a            -
        10  c     needs human  -

    correct 5 (1, 2, 5, 6, 7); covered 8; accuracy 5/10; coverage 8/10; covered acc 5/8.
    a: support 4, predicted 4 (1, 2, 8, 9), correct 2 -> P 0.5, R 0.5
    b: support 4, predicted 4 (3, 5, 6, 7), correct 3 -> P 0.75, R 0.75
    c: support 2, predicted 0, correct 0 -> P None, R 0
    hot over answered items: gold true 1, 5 (4 is unanswered) = 2; predicted true 1, 2 = 2;
    both 1 -> P 0.5, R 0.5.
    W1 (1-4, answered 1-3): pred a 2/3, b 1/3, c 0; gold a 4/4, b 0, c 0.
    W2 (5-8, all answered): pred a 1/4, b 3/4; gold b 4/4.
    """

    def setUp(self):
        self.ls, problems = l.parse_labelset("x", LS)
        self.assertEqual(problems, [])
        self.items = [item("1", "a", "W1", True), item("2", "a", "W1"), item("3", "a", "W1"),
                      item("4", "a", "W1", True), item("5", "b", "W2", True), item("6", "b", "W2"),
                      item("7", "b", "W2"), item("8", "b", "W2"), item("9", "c"), item("10", "c")]
        self.preds = {"1": P("a", flags={"hot": True}), "2": P("a", flags={"hot": True}),
                      "3": P("b"), "4": P(None, 0.3), "5": P("b", flags={"hot": False}),
                      "6": P("b"), "7": P("b"), "8": P("a"), "9": P("a"), "10": P(None, 0.0)}
        self.m = m.compute(self.ls, self.items, self.preds)

    def test_accuracy_and_coverage(self):
        self.assertEqual((self.m.n, self.m.correct, self.m.covered), (10, 5, 8))
        self.assertEqual(self.m.accuracy, 0.5)
        self.assertEqual(self.m.coverage, 0.8)
        self.assertEqual(self.m.covered_accuracy, 5 / 8)

    def test_per_label_precision_and_recall(self):
        a, b, c = (self.m.labels[k] for k in "abc")
        self.assertEqual((a.support, a.predicted, a.correct, a.precision, a.recall), (4, 4, 2, 0.5, 0.5))
        self.assertEqual((b.precision, b.recall), (0.75, 0.75))
        self.assertEqual((c.support, c.predicted, c.precision, c.recall), (2, 0, None, 0.0))

    def test_confusion_matrix(self):
        nh = l.NEEDS_HUMAN
        self.assertEqual(self.m.confusion, {
            "a": {"a": 2, "b": 1, "c": 0, nh: 1},
            "b": {"a": 1, "b": 3, "c": 0, nh: 0},
            "c": {"a": 1, "b": 0, "c": 0, nh: 1}})

    def test_flags(self):
        hot = self.m.flags["hot"]
        self.assertEqual((hot.support, hot.predicted, hot.correct, hot.precision, hot.recall),
                         (2, 2, 1, 0.5, 0.5))

    def test_share_error_by_week(self):
        self.assertEqual(list(self.m.shares), ["W1", "W2"])
        self.assertEqual(self.m.shares["W1"], {"a": (2 / 3, 1.0), "b": (1 / 3, 0.0), "c": (0.0, 0.0)})
        self.assertEqual(self.m.shares["W2"], {"a": (0.25, 0.0), "b": (0.75, 1.0), "c": (0.0, 0.0)})

    def test_a_week_with_nothing_answered_has_no_predicted_share(self):
        mm = m.compute(self.ls, [item("1", "a", "W9")], {"1": P(None)})
        self.assertEqual(mm.shares["W9"]["a"], (None, 1.0))

    def test_min_recall_fails_a_run_whose_accuracy_passes(self):
        """The lopsided bar: accuracy 0.5 meets its 0.5 bar, but c's recall 0 misses 0.5."""
        checks = {c.what: c for c in m.check(self.ls, self.m)}
        self.assertTrue(checks["accuracy"].ok)
        self.assertFalse(checks["recall of c"].ok)
        self.assertFalse(all(c.ok for c in checks.values()))

    def test_a_label_with_no_gold_items_fails_its_min_recall(self):
        ls, _ = l.parse_labelset("x", LS)
        mm = m.compute(ls, [item("1", "a")], {"1": P("a")})
        self.assertIsNone(mm.labels["c"].recall)
        self.assertFalse([c for c in m.check(ls, mm) if c.what == "recall of c"][0].ok)


if __name__ == "__main__":
    unittest.main()
