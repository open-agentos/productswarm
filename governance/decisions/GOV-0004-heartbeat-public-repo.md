---
id: GOV-0004
title: GOV-0002 and GOV-0003 hold unchanged now that the repo is public
status: in-force
kind: ruling
question: "#36"
domain: security
shape: authoritative
classification:
  reversibility: one-way
  blast_radius: external
  nature: values
  knowledge: held
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-02
review_by: 2026-11-30
supersedes: []
applies_to:
  paths: ["heartbeat/**", "dashboard/**"]
  roles: []
  situations:
    - asking whether heartbeat events may be public
    - changing repo or dashboard visibility
---

## Ruling

GOV-0002 (what a heartbeat event captures) and GOV-0003 (events go to comments on a per-session tracking issue) stay in force as written for a **public** repo. Events posted to GitHub, and therefore visible to anyone, carry every GOV-0002 field except prompt text; prompt text stays in the local spool.

## Applies when / does not apply when

- Applies when: deciding whether a heartbeat field may be posted to GitHub, or whether the public dashboard may show it.
- Does not apply when: adding a field GOV-0002 doesn't list. That is a new question, and it must now consider that the field will be public.

## Context

GOV-0002 and GOV-0003 were ruled on 2026-11-01, while productswarm was private. The repo has since been made public, and the dashboard is on public Pages (#33). Tracking issues such as #25 now show role, model, session id, issue and PR numbers, tool names, token counts and session timing to anyone. #36 asked whether the rulings still hold. The owner chose option 1 in a comment on #36.

## Options considered

1. **Reaffirm both as they stand** (chosen): nothing changes; the records say they hold for a public repo.
2. **Reaffirm, but trim what's public**: keep `tools` and `token_counts` local only. The dashboard loses tool activity and spend.
3. **Move events to a private companion repo**: supersedes GOV-0003; the Apps and the dashboard workflow need access there.
4. **Do nothing**: the rulings apply silently to a situation they didn't consider.

## Deliberation

n/a. This is an authoritative decision by the owner, matching the recommendation in #36.

## Consequences

- Everything in a tracking-issue comment is public. The redaction and local-only rule for prompt text (GOV-0002) is now the only thing keeping prompts private, so the hook's guarantee that `prompt` never leaves the machine matters more than before.
- Any future field proposed for the GitHub copy of an event is a public disclosure and is rated `external`.
- Reviewed with GOV-0002 and GOV-0003 by 2026-11-30.
