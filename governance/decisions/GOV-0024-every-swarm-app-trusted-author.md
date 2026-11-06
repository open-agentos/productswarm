---
id: GOV-0024
title: Every swarm App is a trusted author for the Actions reviewer, read from `identities.agents`
status: in-force
kind: ruling
question: "#491"
domain: security
shape: authoritative
classification:
  reversibility: two-way
  blast_radius: repo
  nature: values
  knowledge: held
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-06
review_by: 2027-01-31
supersedes: []
applies_to:
  paths: ["launcher/actions_review.py", "governance/jurisdictions.yml"]
  roles: []
  situations:
    - deciding whose PRs the Actions reviewer's reconciler may start a run with secrets for
    - a role is added to or removed from `identities.agents` and its PRs need, or must lose, Actions reviews
    - wondering whether to add a per-role path check to the reconciler's trust list
---

## Ruling

Every swarm App is a trusted author for the Actions reviewer (option 4 of #491). `AUTHORS` in `launcher/actions_review.py` is read from `identities.agents` in `governance/jurisdictions.yml`, not hard-coded, so a role the owner adds there has its PRs reviewed with no further change. The owner stays a trusted author.

## Applies when / does not apply when

- Applies when: the reconciler (GOV-0020) decides whether a PR's author may start a reviewer run with secrets, or anyone changes how that list is built.
- It amends GOV-0017's trust list: "`productswarm-{planner,builder,docs}[bot]` or the owner" becomes "any App in `identities.agents`, or the owner". GOV-0017's same-repo and non-draft checks, and its ban on `pull_request_target`, `issue_comment` or `workflow_run` on untrusted input, are unchanged. GOV-0018 and GOV-0020 are otherwise unchanged.
- Does not apply when: limiting what a role's PR may touch. Those limits stay in each role's prompt (the analyst touches only `research/`), in the reviewer's rubric and in CODEOWNERS. Merging stays the owner's.
- Does not decide: fork PRs, per-author quotas, trust tiers or a spend ceiling (GOV-0020's later stages).

## Context

The reconciler starts a run holding the reviewer App's key (GOV-0018) only for PRs by a trusted author (GOV-0017, GOV-0020). `AUTHORS` listed planner, builder and docs. #473 and #460 added the analyst and designer roles; `roles/analyst.md` lets the analyst open PRs touching only `research/`, and those got no review (#479). The owner raised #491 and recommended option 1, then changed the recommendation in a comment to a new option 4: the trust list exists to keep forks and strangers away from the key, and "all six Apps are equally the swarm's, so there's no reason to trust some roles' PRs and not others." The owner answered "Confirmed, go with Option 4".

## Options considered

1. **Add the analyst only**, with a check in `plan` that refuses an analyst PR touching anything outside `research/`.
2. **Add the analyst and designer.**
3. **Change nothing** (the default): analyst PRs go to the owner unreviewed, or the builder opens them.
4. **Every swarm App is a trusted author** (chosen): `AUTHORS` is read from `identities.agents`; scope limits stay in role prompts, the rubric and CODEOWNERS.

## Deliberation

n/a. This is an authoritative decision by the owner, who added option 4 in a comment on #491 and confirmed it.

## Consequences

- Analyst and designer PRs get Actions reviews, and so does any role added later to `identities.agents`. Since only the owner edits `jurisdictions.yml` (GOVERNANCE.md §10), the owner still controls who can start a run that holds the key.
- `launcher/actions_review.py` must read the list from `jurisdictions.yml`; that is follow-up work for the builder, by its own issue.
- The reconciler does not enforce per-role paths, so an analyst PR outside `research/` is caught by the reviewer's rubric and the owner, not refused by `plan`.
- Revisit if an App's PRs need a different trust level, or if a role is added that should not hold this trust.
