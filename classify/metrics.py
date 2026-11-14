"""The eval's numbers, from gold items and predictions (#1010). Definitions are in
classify/README.md; in short:

- accuracy: correct / all items. An item answered "needs human" counts as wrong.
- coverage: answered / all items, where "needs human" isn't an answer.
- covered accuracy: correct / answered.
- precision of a label: correct / items predicted as it (answered items only).
- recall of a label: correct / items whose gold label it is ("needs human" is a miss).
- confusion: gold label -> predicted label (or "needs human") -> count.
- share error, per week: a label's share of the answered items minus its share of the gold
  labels, over the items carrying that week.
- flags: per flag, precision and recall of `true` over answered items.

check() scores a pass mark: every bar must hold, so a label below its minimum recall fails a
run whose overall accuracy passes.

Each figure is a float, or None when its denominator is 0. Standard library only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from labelset import NEEDS_HUMAN, Item, LabelSet


@dataclass(frozen=True)
class Prediction:
    label: Optional[str]        # None means "needs human"
    confidence: float = 1.0     # the share of samples that agree with label
    evidence: str = ""          # a quoted line from the item's text
    flags: dict = field(default_factory=dict)


def ratio(num: int, den: int) -> Optional[float]:
    return num / den if den else None


@dataclass
class LabelScore:
    support: int        # items with this gold label
    predicted: int      # answered items predicted as this label
    correct: int

    @property
    def precision(self) -> Optional[float]:
        return ratio(self.correct, self.predicted)

    @property
    def recall(self) -> Optional[float]:
        return ratio(self.correct, self.support)


@dataclass
class Metrics:
    n: int
    correct: int
    covered: int
    labels: dict            # label -> LabelScore, in label-set order
    confusion: dict         # gold label -> {predicted label or NEEDS_HUMAN -> count}
    shares: dict            # week -> {label -> (predicted share or None, gold share)}
    flags: dict             # flag -> LabelScore over answered items (support = gold true)

    @property
    def accuracy(self) -> Optional[float]:
        return ratio(self.correct, self.n)

    @property
    def coverage(self) -> Optional[float]:
        return ratio(self.covered, self.n)

    @property
    def covered_accuracy(self) -> Optional[float]:
        return ratio(self.correct, self.covered)


def compute(labelset: LabelSet, items: list[Item], preds: dict) -> Metrics:
    """The metrics for items, with preds mapping item id -> Prediction."""
    names = labelset.label_names
    scores = {lb: LabelScore(0, 0, 0) for lb in names}
    confusion = {lb: {p: 0 for p in names + [NEEDS_HUMAN]} for lb in names}
    flag_scores = {f: LabelScore(0, 0, 0) for f in labelset.flag_names}
    correct = covered = 0
    weeks: dict = {}
    for it in items:
        p = preds[it.id]
        got = p.label if p.label is not None else NEEDS_HUMAN
        scores[it.label].support += 1
        confusion[it.label][got] += 1
        if it.week:
            weeks.setdefault(it.week, []).append((it, p))
        if p.label is None:
            continue
        covered += 1
        scores[p.label].predicted += 1
        if p.label == it.label:
            correct += 1
            scores[p.label].correct += 1
        for f, s in flag_scores.items():
            gold, said = bool(it.flags.get(f)), bool(p.flags.get(f))
            s.support += gold
            s.predicted += said
            s.correct += gold and said

    shares = {}
    for week in sorted(weeks):
        pairs = weeks[week]
        answered = [p for _, p in pairs if p.label is not None]
        shares[week] = {
            lb: (ratio(sum(p.label == lb for p in answered), len(answered)),
                 ratio(sum(it.label == lb for it, _ in pairs), len(pairs)))
            for lb in names}
    return Metrics(len(items), correct, covered, scores, confusion, shares, flag_scores)


@dataclass(frozen=True)
class Check:
    what: str
    value: Optional[float]
    bar: float

    @property
    def ok(self) -> bool:
        return self.value is not None and self.value >= self.bar


def check(labelset: LabelSet, m: Metrics) -> list[Check]:
    """Every bar of the label set's pass mark against m; the run passes only if all are ok."""
    pm = labelset.pass_mark
    out = [Check("accuracy", m.accuracy, pm.accuracy)]
    if pm.coverage is not None:
        out.append(Check("coverage", m.coverage, pm.coverage))
    for lb in labelset.label_names:
        if lb in pm.min_recall:
            out.append(Check(f"recall of {lb}", m.labels[lb].recall, pm.min_recall[lb]))
    return out
