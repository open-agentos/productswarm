---
id: GOV-0022
title: A PR may merge without the owner's click only through an owner label and a merger in code, staged
status: in-force
kind: ruling
question: "#480"
domain: security
shape: authoritative
classification:
  reversibility: one-way
  blast_radius: repo
  nature: values
  knowledge: held
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-06
review_by: 2027-01-31
supersedes: []
applies_to:
  paths: [".github/", "launcher/", "swarm.toml", "CODEOWNERS", ".github/CODEOWNERS"]
  roles: []
  situations:
    - deciding whether, or how, a PR may merge without the owner pressing the merge button
    - building or changing the merger, its conditions, its App, the `merge:agent` label or its `swarm.toml` switch
    - planning a stage of agent merging, or widening what it covers
---

## Ruling

A PR may merge without the owner pressing the button only by option 2 of #480: the owner adds `merge:agent` to an issue at triage, and plain code in the Actions reconciler merges the builder PR that closes it once every condition below passes, using a `productswarm-merger` App that no Claude session holds. No Claude session merges. It is built in stages, and until a stage is reached the owner merges every PR as today.

The label counts only if the owner added it (checked as GOV-0006 sets out). The merger merges only when all of these pass:

- the author is `productswarm-builder[bot]`, and the PR closes exactly the labelled issue;
- the reviewer approved at the current head commit;
- there's no `Overstep:` finding and no open request for changes;
- required tests pass;
- it touches no protected path: `ops/`, `.github/`, `governance/`, `GOVERNANCE.md`, `roles/`, `CLAUDE.md`, `swarm.toml`, or dependency files;
- it's under a size limit.

Any miss leaves the PR for the owner, with the reason posted on it. Each merge is commented on the PR, shown on the wire and counted in the digest. A `swarm.toml` switch turns it all off.

Stages, in order:

1. Add a required test check.
2. Run the merger in shadow for a week: it posts "would merge", and the owner still merges.
3. Narrow CODEOWNERS to the protected paths, and turn on stale-review dismissal.
4. Enable it for low-risk paths first.
5. Widen by ruling.

The merger App's permissions and the test workflow are sub-questions, raised when their stage comes up.

## Applies when / does not apply when

- Applies when: any role proposes, builds or changes a way for a PR to merge without the owner's click, or works on a stage above.
- It amends GOV-0006: `merge:agent` joins `ready` and `gov:ruled` as a label that counts only if the owner added it, and agents never add or remove it.
- It amends GOV-0011: "merging stays the owner's act alone" now has one exception, the merger in this ruling. An approval still means only that the rubric passed at that head; it is one of the merger's conditions, not a decision to merge.
- It amends GOV-0013 as #480 lists. GOV-0013's `--disallowedTools` for `gh pr merge` still applies to every headless run, since no Claude session merges; the merger is code with its own App.
- Does not apply when: the owner merges a PR by hand, which stays allowed at every stage. It doesn't let a builder merge its own PR (option 3) or turn on GitHub's native auto-merge (option 4).
- Does not decide: the merger App's permissions, the test workflow, the size limit's value, which paths are low-risk in stage 4, or any widening in stage 5. Each needs its own question or ruling when its stage comes up.

## Context

Every PR waits for the owner's merge, and builder PRs are most of the needs-you list (#464, builder's bet). #464's committee says that going over the ceiling should mean fewer owner-only acts. Merging is gated today by the `main` ruleset (a code-owner review and one approval), CODEOWNERS `* @mattmcalister`, CLAUDE.md ("Never merge a PR"), GOV-0011 and GOV-0013's deny list. No required check runs tests: `main`'s only checks are `nudge`, `publish` and `update`.

The owner raised #480 directly, after #464, and asked the analyst first how comparable tools handle it. The analyst's brief on #480 found that no tool surveyed lets the authoring agent merge, that all of them wait for required checks, and that option 2 is the usual shape (Kodiak and Mergify: an owner label, then the ruleset plus extra conditions). The owner answered on #480: "Option 2".

## Options considered

1. **Do nothing:** the owner merges every PR.
2. **An owner label plus a merger in code** (chosen): the owner adds `merge:agent` at triage; code in the Actions reconciler merges the builder PR under the conditions above, with an App no Claude session holds.
3. **The builder merges its own PR** under the same conditions: simpler, but the author lands its own work, and GOV-0013's "no session merges" ends.
4. **GitHub's native auto-merge** on labelled PRs, with the ruleset as the only gate: no path, size or overstep checks, since rulesets can't express them.

## Deliberation

n/a. This is an authoritative decision by the owner, who answered "Option 2" on #480. The conditions, staging and off switch are those of the question's recommendation, which was option 2.

## Consequences

- Nothing merges without the owner until stage 4. Stages 1 to 3 add a required test check, a week of shadow runs and narrower CODEOWNERS, while the owner keeps merging.
- From stage 4, some builder PRs on issues the owner labelled `merge:agent` land without the owner's click. The owner's control moves to triage (the label), the merger's code on `main`, and the off switch.
- Code-owner review stops covering every path in stage 3. The protected paths keep it.
- #480 lists CLAUDE.md and `PRODUCT.md`'s non-goals as amended. This record doesn't edit them; that is follow-up work, by its own issue.
- The team accepts that a merged defect reaches `main` without the owner reading it first, bounded by the conditions, the size limit and the protected paths.
- Revisit if the shadow week shows wrong "would merge" calls, if a merged PR has to be reverted, or before widening in stage 5.
