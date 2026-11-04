---
id: GOV-0021
title: The reviewer requests changes only for an evidenced block-list finding the builder can fix inside the PR's issue
status: in-force
kind: ruling
question: "#311"
domain: product-scope
shape: committee
classification:
  reversibility: two-way
  blast_radius: repo
  nature: values
  knowledge: shared
decided_by: humans.owner, ratifying the committee's recommendation (Discussion #314)
ratified_by: humans.owner
date: 2026-11-04
review_by: 2027-01-31
supersedes: []
applies_to:
  paths:
    - roles/reviewer.md
    - roles/builder.md
    - evals/**
    - launcher/**
  roles: [reviewer, builder, planner]
  situations:
    - the reviewer chooses between request changes, comment and approve on a PR
    - the builder responds to a red review, or disputes one
    - scoring reviews in the eval, or setting the C stage 2 gate
---

## Ruling

This amends GOV-0011's red and amber definitions. The rest of GOV-0011 is unchanged, including approve meaning "rubric passed at this head", the 2-round bound and the overstep path to the owner.

**Red (`--request-changes`) only when a finding is all of:**

- **on the block list:**
  1. an unmet "Done when" item;
  2. a broken ruling;
  3. a test the PR causes to fail, using the canonical test command (`python3 -m unittest discover -s <dir>`), checked against the merge base so inherited failures don't count;
  4. a behaviour bug;
  5. a factual error in a file agents act on, where the review cites a merged record, an issue's state, or another line of the same file;
  6. a scope failure: the PR closes no issue or more than one, or does work outside its issue;
- **backed by evidence:** a failing command, a reproduction, or a cited line with the source it contradicts;
- **fixable inside the issue:** the fix is a change to files in the diff or to a test, with no change to the issue text, a ruling or an owner choice.

**Amber (`--comment`)** for everything else: style, wording, inherited failures, merge-order notes, findings without evidence, and findings whose fix needs the owner.

Also:

- **Every red finding is labelled with its block number** (e.g. "Block 4: …") and carries its evidence.
- **A fix needs a new commit** to be re-reviewed. Editing the PR body doesn't start a review. A rebase is a new head and gets a fresh review.
- **Intent doesn't change the state; draft does.** A PR that isn't for merging should be a draft; drafts get no review.
- **Overstep outranks red.** A review with both a block finding and an `Overstep:` is posted as `COMMENTED`, Authority fail, with the block findings still listed and numbered. After the owner resolves the overstep, a new commit on the PR (or the owner asking by hand) brings the builder's response and a fresh review at the new head.
- **A merged ruling outranks a role prompt that lags it.** The review follows the ruling, cites it, and notes the lag.
- **Block 6 reds on builder PRs go to `needs_you()`.** `[respond]` skips a PR that doesn't close exactly one issue, so this is expected, not a fault in the loop.

### Worked examples

| Case | Answer |
|---|---|
| #72: a "Done when" item unmet | **Red**, Block 1 |
| #104: `[build]` fires on an issue an open PR already closes | **Red**, Block 4, with the dry-run repro given verbatim |
| #103: `PRODUCT.md` says #101 and #102 are answered | **Red**, Block 5, citing #101/#102's state and lines 103, 124 and 126, checked at the head |
| #120, #143, #144: a dashboard failure inherited from `main` | **Approve with a note** showing the merge-base result. If the merge base passes, it's red under Block 3 |
| #120: tests after `unittest.main()` | **Approve with a note.** Red under Block 1 only if the "Done when" names the direct run |
| #152 + #153: a break only when combined | **Approve both with a merge-order note.** The rebased head is a new head and gets a fresh review, which can be red under Block 3 |
| #156: does less than its issue's Scope but meets every "Done when" | **Approve** if the body states the narrowing; **`COMMENTED` + `Overstep:`** if it's silent. The fix needs a new commit |
| #143: a "Done when" item that can't be met as written | **Comment**, with no `Overstep:`, naming the reading used. The owner or planner fixes the issue |
| #104, #116, #117: a merged ruling ahead of the role prompt | **Follow the merged ruling**, cite it, and note the lag in the prompt |
| #251 and #289: owner PRs that close no issue | **Both red**, Block 6. #251's "a agentic" is a comment, not Bugs. #289 should have been a draft |

### Eval (a separate issue, landing before or with the prompt change)

- **E1:** marks for the new block items: a `test` mark at the head and the merge base; Scope sets the verdict; an Authority mark; Overstep-over-red scored as one block.
- **E2:** the pre-registered C stage 2 bar is unchanged. Line 2 stays on `unmet` + `broken`. Misses on Blocks 3 and 6, justified blocks on Blocks 4 and 5, and the count of unreviewed merged PRs are reported beside it.
- **E3:** an **unannounced planted-defect PR, opened by someone who is neither the reviewer nor the builder,** gates C stage 2. It passes only on `CHANGES_REQUESTED` with a `Block 1` finding naming the unmet item; `COMMENTED` + `Overstep:` is a fail. A second planted PR with a broken record passes only on `Block 2`. Replaying #72@`b14116a` and #104@`48ab1fd` is an optional smoke test, not scored.
- **Scorer separation:** whoever scores the next sample is neither the reviewer nor the author of the PRs scored.

### Cost check

After the first **5** builder-App reds under this rule, revisit it if **more than 2** reach GOV-0011's 2-round bound.

## Applies when / does not apply when

- Applies when: the reviewer picks a review state, the builder responds to a red review, or the eval scores reviews and sets the C stage 2 gate.
- Does not change: approve's meaning, the three rubric items and their format in the review body, the 2-round bound, `[respond]`'s rules in `swarm watch`, or the overstep path to the owner (GOV-0011). Merging stays the owner's act alone.
- Does not decide: what to do about builder PRs that merged with no reviewer review (#200, #269, #275). The committee raised it in passing; it may need its own issue.

## Context

GOV-0011 defined red as "bugs or scope problems the builder can fix" and amber as "notes that need no change". The B eval (#175, `evals/results.md`, "Inputs for a committee") listed nine real cases that wording didn't settle, and two Actions reviews disagreed on the same kind of PR: #251 (red) and #289 (amber) both closed no issue. The B result was inconclusive because nothing had yet shown the reviewer blocking a real unmet "Done when" item, and C stage 2 depends on that gate (GOV-0015, `evals/README.md`).

The owner raised #311 and convened the swarm's first deliberate committee (GOVERNANCE.md §7), with the rounds piloted in Discussion #314.

## Options considered

1. **Keep GOV-0011's wording:** the reviewer keeps judging case by case.
2. **Block on the eval's rubric:** red exactly for `unmet` or `broken`. Measurable, but misses bugs no "Done when" names (#104).
3. **A written block list** (chosen, as "3c+E"): red for listed findings with evidence; everything else amber.
4. **Block on any fixable finding:** the most thorough, but reaches the 2-round bound most often.

## Deliberation

Committee convened by the owner on #311, rounds in Discussion #314:

- **Proposer:** reviewer, `claude-opus-5-5`, from its own review history.
- **Challenger:** builder, `claude-sonnet-5-5`, from the reviews it received and GOV-0011's `[respond]` loop.
- **Domain reviewer:** planner, `claude-opus-5-5`, from the B eval.

Two models and three evidence bases (§7.2). Two of three rounds ran; the convener stopped early under the Discussion's rule 6 because all three recommendations matched after Round 2.

- Round 1: the proposer put forward option 3 with two changes ("3b": Block 5 for factual errors, and Block 6 red whatever the PR body says). The challenger added four amendments ("3c": block numbers on red findings, a narrowed Block 5, the fixable-inside-the-issue test with "a fix needs a new commit", and "draft decides, intent doesn't"). The planner added the eval conditions E1–E3 ("3c+E").
- Round 2: the proposer added Overstep-over-red. The challenger added who moves next after an overstep. The planner withdrew the replay as gating evidence and tightened E3's pass condition.

**Recommendation:** option 3 as "3c+E", 3 of 3 (reviewer, builder, planner).

**Dissent:** none remains. Two disputes were resolved: the planner withdrew the E3 replay as gating evidence after the proposer and challenger argued that a replay shows red *can* be produced, not that it's *found*; and the challenger accepted Overstep-over-red once the "who moves next" sentence was added.

**Tally:** no vote. `product-scope` has no `vote_eligible` identities (§7.5), so the committee recommended and the owner ratified it as recommended, with the cost-check defaults (5 reds, revisit at more than 2).

## Consequences

- `roles/reviewer.md` step 4 changes to this rule, and steps 3–4 gain the canonical test command, the merge-base check, block numbers and evidence on red findings. `roles/builder.md` may need "a fix needs a new commit". Each needs its own issue.
- The eval issue (E1–E3) lands before or with the prompt change. Otherwise every Block 6 red scores as a false block under today's rubric.
- Owner experiments that close no issue are marked red unless they're drafts. That's honest noise, and it starts no session.
- A review costs one more test run when a suite fails, for the merge-base check.
- Revisit under the cost check above, if the planted-defect PR fails, or if reds often reach the 2-round bound.
