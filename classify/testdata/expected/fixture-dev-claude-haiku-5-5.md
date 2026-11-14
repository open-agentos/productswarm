# Classify eval: fixture, dev split

- **Classifier:** model `claude-haiku-5-5`, 3 samples per item, threshold 60.0%
- **Mode:** replay (recordings only)
- **Label set:** `labelsets/fixture.yml` sha256 `19e0033857d54c0cfe207aa674cc2bb9172884698246713a1c2dca43e3a0bd42`
- **Labelled set:** `data/fixture.jsonl` sha256 `31d3829c60aa07eb1685874224b090b8219e59c67662137ab79dab067a43293c`
- **Items:** 8

**Result: PASS**

## Pass mark

| Check | Value | Bar | |
|---|---|---|---|
| accuracy | 62.5% | 60.0% | pass |
| coverage | 87.5% | 80.0% | pass |
| recall of bug | 66.7% | 60.0% | pass |

## Overall

| Measure | Value |
|---|---|
| Accuracy | 62.5% (5 of 8) |
| Coverage | 87.5% (7 of 8 answered) |
| Accuracy on covered items | 71.4% |

## Per label

| Label | Gold | Predicted | Correct | Precision | Recall |
|---|---|---|---|---|---|
| bug | 3 | 3 | 2 | 66.7% | 66.7% |
| feature | 2 | 2 | 1 | 50.0% | 50.0% |
| docs | 3 | 2 | 2 | 100.0% | 66.7% |

## Confusion matrix

Rows are gold labels, columns predicted.

| Gold \ Predicted | bug | feature | docs | needs human |
|---|---|---|---|---|
| bug | 2 | 1 | 0 | 0 |
| feature | 0 | 1 | 0 | 1 |
| docs | 1 | 0 | 2 | 0 |

## Flags

On answered items.

| Flag | Gold true | Predicted true | Both | Precision | Recall |
|---|---|---|---|---|---|
| urgent | 2 | 2 | 2 | 100.0% | 100.0% |

## Share error by week

Each label's share of the answered items, its share of the gold labels, and the difference.

| Week | bug | feature | docs |
|---|---|---|---|
| 2026-W45 | 50.0% vs 75.0% (-25.0 pts) | 50.0% vs 25.0% (+25.0 pts) | 0.0% vs 0.0% (0.0 pts) |
| 2026-W46 | 33.3% vs 0.0% (+33.3 pts) | 0.0% vs 25.0% (-25.0 pts) | 66.7% vs 75.0% (-8.3 pts) |

## Items

| Item | Gold | Predicted | Confidence | Evidence |
|---|---|---|---|---|
| d1 | bug | bug | 100.0% | “Fix the crash when a Goal has no sub-issues.” |
| d2 | bug | bug | 66.7% | “Stop the merger counting a revert twice.” |
| d3 | bug | feature ✗ | 100.0% | “Handle a missing week field” |
| d4 | feature | feature | 66.7% | “Add a --json flag to swarm trouble.” |
| d5 | feature | needs human ✗ | 33.3% |  |
| d6 | docs | docs | 100.0% | “Rewrite the launcher README's watch section.” |
| d7 | docs | docs | 66.7% | “Explain the pass mark in classify/README.md.” |
| d8 | docs | bug ✗ | 100.0% | “Correct the wrong example” |
