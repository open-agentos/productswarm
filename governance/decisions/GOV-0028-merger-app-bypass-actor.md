---
id: GOV-0028
title: The merger App holds only the rights it needs to merge and is the only extra bypass actor on the main ruleset
status: in-force
kind: ruling
question: "#601"
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
  paths: ["ops/create-apps.py", ".github/workflows/merger.yml", "CODEOWNERS", ".github/CODEOWNERS"]
  roles: []
  situations:
    - creating, changing or rotating the `productswarm-merger` App or its key
    - choosing the permissions of the merger App or of the token `merger.yml` mints
    - changing the `main` ruleset's bypass list, required approvals or code-owner review
---

## Ruling

By option 1 of #601, the `productswarm-merger` App (GOV-0022, GOV-0027) holds only `contents: write`, `pull_requests: write`, `checks: read`, `issues: read` and `metadata: read`. It holds no `workflows`, `administration` or `actions` permission. It is the only bypass actor added to the `main` ruleset, in "pull_request" mode. CODEOWNERS (`* @mattmcalister`) and the ruleset's required approval and code-owner review stay as they are, so no other App can merge. The App's key lives only in an Actions secret used by `merger.yml`; no session or launcher reads it.

## Applies when / does not apply when

- Applies when: setting up the merger App, its key, or the `main` ruleset so that #592's merger can go live.
- Does not apply when: deciding what the merger may merge. GOV-0022 and GOV-0027 set its conditions, and the merger checks them in code.
- It does not change any other App's permissions, or #32 (no App holds `workflows`).

## Context

GOV-0022 (#480) and GOV-0027 (#576) have the merger merge PRs with a `productswarm-merger` App that no Claude session holds, and both left its permissions to their own question. #592 can't go live without the App, and `ops/create-apps.py`'s `ROLES` had no merger.

The `main` ruleset requires one approval and a code-owner review, and CODEOWNERS is `* @mattmcalister`, so every PR needs the owner's review. That required review is what stops the builder App merging: it holds `contents: write` and `pull_requests: write`, and only GOV-0013's deny list keeps each session off the merge API.

The merger needs to read PRs, reviews, comments, check runs and the issue each PR closes, post comments, and merge with the head SHA pinned (#589, #592).

The owner raised #601 and answered: "Confirmed. Option 1."

## Options considered

1. **Minimal App, bypass actor** (chosen): the permissions above; the App is the only extra bypass actor on `main`, in "pull_request" mode; CODEOWNERS and the required owner review are unchanged.
2. **Minimal App, narrowed CODEOWNERS** (GOV-0022's stage 3): the same permissions, CODEOWNERS narrowed to the protected paths and required approvals set to 0. Any App with `contents: write` (builder, docs, analyst) could then merge non-protected PRs through the API, held back only by the deny list.
3. **Do nothing**: no merger App; the owner merges every PR, and nothing from GOV-0027 goes live.

## Deliberation

n/a. This is an authoritative decision by the owner, matching the question's recommendation.

## Consequences

- The ruleset stays the barrier for every App but the merger. The merger skips the ruleset's own checks, and checks `tests`, the reviewer's approval at head, paths and size itself (GOV-0022, GOV-0027), so a bug in the merger's code is not caught by the ruleset.
- It replaces GOV-0022's stage 3 (narrow CODEOWNERS): CODEOWNERS stays `* @mattmcalister`, and the bypass actor is how the merger gets past the required review.
- The merger's key is exposed to Actions runners. Rotation is the only undo.
- Revisit if the merger needs a right beyond these five, or if another App ever needs to bypass the ruleset.
