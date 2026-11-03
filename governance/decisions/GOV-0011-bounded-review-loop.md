---
id: GOV-0011
title: The reviewer uses review states as a stoplight, and swarm watch starts the builder on requested changes, for at most 2 rounds per PR
status: in-force
kind: ruling
question: "#105"
domain: product-scope
shape: authoritative
classification:
  reversibility: costly
  blast_radius: repo
  nature: values
  knowledge: held
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-03
review_by: 2027-01-31
supersedes: []
applies_to:
  paths:
    - launcher/**
    - roles/reviewer.md
    - roles/builder.md
  roles: [reviewer, builder]
  situations:
    - the reviewer posts a review on a PR
    - the builder's own PR has a "changes requested" review at its current head
    - building or changing `swarm watch` triggers
---

## Ruling

Adopt a bounded review loop with three parts:

1. **The reviewer uses review states as a stoplight:**
   - red: `--request-changes` for bugs or scope problems the builder can fix;
   - amber: `--comment` for notes that need no change;
   - green: `--approve` when the review rubric passes at this head.
2. **The builder responds to requested changes** on its own PR. It pushes fixes inside the PR's issue, or replies where it disagrees. It doesn't widen scope.
3. **`swarm watch` gets a fifth trigger:** when the latest reviewer review at a PR's current head is "changes requested", it starts the builder on that PR. The builder's new push then starts a fresh reviewer pass through GOV-0009's PR-head trigger.

**Approve means "the rubric passed at this commit".** It is not a merge decision and not a recommendation to merge. All three items of the reviewer's checklist must pass:

- **Bugs:** the change does what its issue's "Done when" says, and the tests pass.
- **Scope:** it closes exactly one issue and stays inside it.
- **Authority:** there are no `Overstep:` findings.

Every review body lists the three items with pass or fail. An approval's body says "Rubric passed at `<sha>`. Not a merge decision; the owner reviews and merges." An approval covers one head only.

**Bound:** at most 2 builder rounds per PR, counted from GitHub review history so the count holds across `swarm watch` restarts. If the reviewer requests changes a third time, the loop starts nothing more on that PR and lists it in `swarm inbox` as needing the owner.

**Oversteps go to the owner.** An `Overstep:` finding needs a `gov:question` or the owner, not a code push, so it goes to the needs-you list and doesn't start the builder.

## Applies when / does not apply when

- Applies when: the reviewer reviews a PR, the builder's PR has changes requested, or `swarm watch` decides what to start.
- Does not apply when: merging. "Never merge" holds for every role, and merging stays the owner's act alone. The approval exception is for the reviewer only; every other role still never approves.
- Does not decide: #101 (a fresh session or re-prompting one) or #102 (who polls for reviews). They stay open questions.

## Context

The reviewer posted findings with `--comment` only (`roles/reviewer.md` step 4; "never approve" in CLAUDE.md and every role prompt). Only the owner read those findings and prodded the builder by hand. GOV-0009's `swarm watch` starts a reviewer for each new PR head, but had no trigger for acting on what the reviewer found. GOV-0009 says any trigger outside its table needs its own `product-scope` question, and GOV-0005 says the same of any workflow change. At the owner's request, the planner raised #105 and, at the owner's direction, redefined approve as "rubric passed". The owner answered "Option 1" in a comment, and later asked for this record.

## Options considered

1. **Adopt the proposal with approve defined as "rubric passed"** (chosen): a three-state stoplight, the builder responds, a new watch trigger, and a 2-round bound before the owner steps in.
2. **The same loop without approve:** red = `--request-changes`, and everything else stays `--comment`. "Never approve" stays for every role, which avoids the branch-rule question.
3. **Do nothing:** the reviewer stays comment-only, and the owner relays findings to the builder by hand.

## Deliberation

n/a. This is an authoritative decision by the owner. The planner recommended option 1 **if** the owner confirmed that the `main` ruleset doesn't count a bot's approval towards required reviews, and option 2 otherwise. The planner couldn't read the ruleset (403 for the app). The owner's answer, "Option 1", doesn't mention the ruleset.

## Consequences

- `roles/reviewer.md` step 4 and the "never approve" rule in CLAUDE.md and the reviewer prompt change for the reviewer only. `roles/builder.md` gains the response step. `swarm watch` gains the trigger and the round count. Each needs its own issue.
- Builder response sessions count towards GOV-0010's ceiling (2 live loop-started sessions) and need a `spend_cap_usd` like any other loop start. With the 2-round bound, one PR costs at most 1 build, 3 reviews and 2 builder responses.
- The bound, together with GOV-0009's "never acts on the same trigger twice", is what stops reviewer↔builder ping-pong.
- If the `main` ruleset counts a bot's approval towards required reviews, a reviewer approval is a step towards merging, whatever this record says approve means. Whether it does is the owner's to confirm; the record doesn't assume an answer.
- Revisit if PRs often hit the 2-round bound, or if approvals are read as merge signals.
