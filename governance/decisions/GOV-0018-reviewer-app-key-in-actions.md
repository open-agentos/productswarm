---
id: GOV-0018
title: Move the reviewer App's private key into a protected Actions environment and mint a narrowly scoped token from it
status: in-force
kind: ruling
question: "#207"
domain: security
shape: authoritative
classification:
  reversibility: one-way
  blast_radius: external
  nature: values
  knowledge: held
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-03
review_by: 2027-01-31
supersedes: []
applies_to:
  paths: [".github/workflows/**"]
  roles: [reviewer]
  situations:
    - building or changing the GitHub Actions job that runs the reviewer (v3 C stage 1)
    - storing, reading or rotating the `productswarm-reviewer` App ID and private key for Actions
    - choosing the scopes of the installation token a reviewer run in Actions uses
---

## Ruling

Store `productswarm-reviewer`'s App ID and private key as secrets of a GitHub environment (for example `reviewer`), restricted to the default branch and used only by the reviewer job. The job mints an installation token limited to this repo and to `pull_requests: write`, `contents: read` and `issues: read`. Mint it with `actions/create-github-app-token` pinned to a commit SHA, or with a small stdlib step that mirrors `ops/swarm-token`'s JWT flow. Rotate the key if anyone but the owner ever changes the environment or the workflow.

## Applies when / does not apply when

- Applies when: a reviewer runs in GitHub Actions (C stage 1, GOV-0015) and needs to act as `productswarm-reviewer[bot]`.
- Does not apply when: builder or docs run in Actions (C stage 2). Their keys stay on the owner's Mac; moving them needs its own question.
- Does not apply when: sessions run on the owner's Mac. `ops/swarm-token` and the local reviewer key are unchanged.
- It does not choose between `actions/create-github-app-token` and a stdlib step. Option 1 allows either. Adding the third-party action is a `dependencies` choice and goes through that domain.
- It does not change the Apps' permissions. They still have no `workflows` permission (#32).

## Context

GOV-0015 makes C stage 1 the reviewer running in GitHub Actions, and names App private keys in Actions secrets as one of its sub-questions. To review as `productswarm-reviewer[bot]`, the job needs an installation token for the reviewer App. GOV-0011's stoplight, the dashboard and `swarm watch` all key on that identity. Until now `ops/swarm-token` minted the token on the owner's Mac, from a private key that had never left it.

Putting an App private key in Actions secrets is one-way: once a key has been on a runner, you have to assume it could have leaked, and the only undo is rotating it.

The planner raised #207 from the C stage 1 planning on #167. It recommended option 1: it keeps one reviewer identity so nothing downstream changes; the reviewer's key is the lowest-risk one to move, because the reviewer can't push; the token's scopes can be narrower than the App's; and an environment limits which workflow and branch can read the key. It preferred `actions/create-github-app-token` pinned by SHA, and left that supply-chain choice to the owner.

The owner answered on #207: "Option 1".

## Options considered

1. **Move the reviewer key, scoped and protected**: environment secrets restricted to the default branch, a token limited to this repo with `pull_requests: write`, `contents: read` and `issues: read`, and rotation if anyone but the owner changes the environment or the workflow (chosen).
2. **No App key, review as `github-actions[bot]`**: no key moves, but reviews come from a different identity, so GOV-0011's round count, the dashboard's reviewer state and `swarm watch`'s `[review]`/`[respond]` triggers stop seeing them. A `GITHUB_TOKEN` review also doesn't trigger other workflows.
3. **A separate "reviewer-actions" App**: the local key stays on the Mac, but it has option 2's identity problem and adds a role identity to `jurisdictions.yml`, which is a governance change.
4. **Do nothing**: no Actions reviewer runs.

## Deliberation

n/a. This is an authoritative decision by the owner, matching the planner's recommendation.

## Consequences

- The C stage 1 reviewer job can act as `productswarm-reviewer[bot]`, so GOV-0011, the dashboard and `swarm watch` need no change.
- The token is narrower than the App. A reviewer run in Actions can write reviews and comments but can't push, and can't edit labels or merge at the API. That enforces part of GOV-0013 below the tool layer.
- The team accepts that the reviewer key is now exposed to runners. Rotation is the only undo, and it is required if anyone but the owner changes the environment or the workflow.
- GOV-0016 (what the job log prints) and GOV-0017, if merged (which events and authors start the job), still apply to the same job.
- Revisit for C stage 2, or if the reviewer ever needs a scope beyond these three.
