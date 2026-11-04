# evals: quality evals for merged PRs

Stage B of v3 (GOV-0015). These evals check whether merged PRs did what their issues asked, and whether the reviewer's verdicts match. Their results gate C stage 2: running builders and docs in GitHub Actions.

| Part | Issue | What | File |
|---|---|---|---|
| B1 | #172 | The rubric and the pre-registered bar (this file) | `evals/README.md` |
| B2 | #173 | Pick the sample and gather its inputs | `evals/gather.py`, `evals/data/sample.json` |
| B3 | #174 | Score each sampled PR against the rubric | `evals/results.md` |
| B4 | #175 | Reviewer calibration and the result against the bar | `evals/results.md` |

## Public, and no cost figures

The repo is public (GOV-0004), so everything in `evals/` is public: the rubric, the sample, the scores and the calibration. Don't put prompt text, local heartbeat data or anything else GOV-0002 keeps local into `evals/`.

`evals/` holds **no cost figures**. Run cost stays local (GOV-0014), and `swarm cost` (#176) only prints it. Putting cost into `evals/` or a PR would need a `security` question first.

## What a PR is scored on

Each PR in `evals/data/sample.json` is scored at its merge head (`head_sha`) on three things.

### 1. "Done when" items

Take each item in the "Done when" / "Acceptance" section of the issue the PR closes (`issue.done_when`). Mark each one:

| Mark | Meaning |
|---|---|
| `met` | The PR does what the item asks. |
| `unmet` | The PR doesn't do it, or does something that contradicts it. |
| `unclear` | The evidence can't settle it: for example, the item is vague, or it depends on something outside the repo. |

Every mark cites its evidence: a file (`path:line`), a test (name, and whether it passes at the merge head) or a diff hunk. An `unmet` mark without evidence doesn't count.

### 2. Governance records

Take each `GOV-NNNN` that the PR body or its issue cites (`gov_ids`). Mark each one:

| Mark | Meaning |
|---|---|
| `followed` | The change does what the ruling says. |
| `broken` | The change does something the ruling forbids, or skips something the ruling requires. |
| `n/a` | The ruling is cited, but it says nothing about what this change does. |

A `broken` mark cites the ruling's line and the evidence in the change.

### 3. Scope

- **Closes one issue:** `yes` if the PR closes exactly one issue, otherwise `no` (with the issues it closes).
- **Stays inside it:** `yes` if every changed file and behaviour is something the issue asked for, otherwise `no`, with each change outside the issue.

Scope findings are listed, but they don't change the verdict.

## The eval's verdict

For each PR:

- **`would request changes`** if any "Done when" item is `unmet` or any record is `broken`;
- **`would approve`** otherwise.

`unclear` items and scope findings are listed with the PR, but they don't change its verdict.

## The reviewer's verdict

The reviewer's verdict on a PR is the state of the last review `productswarm-reviewer[bot]` submitted before the PR merged: `APPROVED`, `COMMENTED` or `CHANGES_REQUESTED`. A PR with no such review gets `none`.

Note whether that review was at the merge head (`at_merge_head` in `sample.json`). That doesn't change the verdict, but #175 uses it to explain disagreements.

**Blocking.** The reviewer blocked a PR if its verdict is `CHANGES_REQUESTED`, or if it's `COMMENTED` and that review has an `Overstep:` finding (`overstep_comments`), because GOV-0011 sends an `Overstep:` finding to the owner. `APPROVED`, a `COMMENTED` review with no `Overstep:` finding, and `none` don't block.

## Agreement

On a PR the reviewer reviewed, the eval and the reviewer **agree** when both block (`would request changes` and a blocking review) or neither does (`would approve` and a non-blocking review). Otherwise they **disagree**.

A PR with reviewer verdict `none` has no agreement, either way. It is scored and listed, but it doesn't count in N or in any line of the bar. An unreviewed PR the eval would block is reported as **unreviewed defect**.

## Totals

`evals/results.md` (#174) counts these. **N** is the number of sampled PRs whose reviewer verdict isn't `none`. Every total except the last is counted over those N PRs.

| Total | Count of PRs where |
|---|---|
| agree | the eval and the reviewer agree |
| eval blocks | the eval says `would request changes` |
| reviewer blocks | the reviewer blocked |
| false blocks | the reviewer blocked, and the eval says `would approve` |
| misses | the eval says `would request changes`, and the reviewer didn't block |
| unreviewed defects | the reviewer verdict is `none`, and the eval says `would request changes` (outside N) |

## Pre-registered bar for C stage 2

The owner set these numbers on #172 before #174 ran. #175 reports against them. C stage 2 is proposed only if all three hold:

1. **Agreement: at least 12 of 14** of the reviewed PRs (85%). If the final sample's N differs, use 85% of N, rounded up.
2. **Misses: 0.** On every PR where the eval finds an `unmet` "Done when" item or a `broken` record, the reviewer must have blocked.
3. **False blocks: at most 2.** A false block only costs a builder round, so it's tolerable. A miss is not.

**One more condition:** if the eval finds no `unmet` item and no `broken` record in the whole sample, condition 2 hasn't been tested. In that case the bar is **inconclusive, not passed**, and C stage 2 waits until the reviewer has been shown to block a real defect. #175 should say how that would be shown, for example a PR with a planted defect.

For the committed `sample.json` (20 PRs, 15 of them with a reviewer review), N is 15, so line 1 needs at least 13 of 15 (85% of 15 is 12.75, rounded up).

Whether C stage 2 goes ahead is the owner's call. The bar only says whether it may be proposed.

## Red cost check (outside the bar)

`python3 evals/red_check.py [--repo owner/name]` (#330) is part C of the owner's ruling on #311: after the first **5** builder-App reds under the new reviewer rule, revisit the rule if **more than 2** reach GOV-0011's 2-round bound. It measures what red costs, not whether red is right, so it's reported on its own and isn't part of the bar above.

- **Start:** the merge time of the PR that closes #329 (the reviewer prompt), looked up from GitHub. Until that merges it says so and counts nothing.
- **A red:** a `CHANGES_REQUESTED` review by `productswarm-reviewer[bot]`, submitted after the start, on a PR `productswarm-builder[bot]` opened. A PR counts once however many reds it gets, and only reds after the start count. The first 5 such PRs, by the time of their first red, are counted.
- **The bound:** `past_bound()` in `dashboard/generate.py`, the rule `needs_owner()` uses: a third red reaches it.
- **Per PR:** number, state, how many reds (with any `Block N` numbers they cite), and one of `fixed in 1 round`, `fixed in 2 rounds` (the reviewer's latest review isn't a red), `reached the bound`, `still open`, `ended while red` (merged or closed with a red as the latest review), or `not responded: [respond] skips it` (the PR doesn't close exactly one issue, so the loop leaves it to the owner).
- **Summary:** `red check (#311): k of 5 counted, m reached the 2-round bound; revisit if more than 2`, then `revisit: yes|no` once all 5 have settled (merged, closed or at the bound). The 5 and the 2 are the owner's numbers (`COUNT`, `REVISIT_OVER`).

It's read-only (every call goes through `gather.py`'s guard), prints no review text, counts rounds rather than dollars, and doesn't read `watch.json`. When it first prints `revisit: …`, whoever ran it posts that line on #330 for the owner.
