---
id: GOV-0020
title: A reconciler on main starts Actions reviewer runs from repo state; PR events may only nudge it
status: in-force
kind: ruling
question: "#255"
domain: security
shape: authoritative
classification:
  reversibility: two-way
  blast_radius: repo
  nature: values
  knowledge: held
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-04
review_by: 2027-01-31
supersedes: []
applies_to:
  paths: [".github/workflows/reviewer.yml", "launcher/", "swarm.toml"]
  roles: [reviewer, builder, planner]
  situations:
    - deciding how an Actions reviewer run is started now that its secrets live in a main-only environment (GOV-0018)
    - building or changing the reconciler workflow, its plan step, or anything that wakes it early
    - choosing whether a pull-request event may start a run with the reviewer's secrets
---

## Ruling

Actions reviewer runs that use the reviewer's secrets start only from a reconciler on `main`: one workflow that wakes on a schedule (and on `workflow_dispatch`), reads repo state, and starts a review for each PR the rules allow. PR events may only nudge the reconciler to wake early; they never start a privileged run or decide which PRs are reviewed. This is stage 1 and covers the reviewer only, with GOV-0017's trust list: swarm Apps and the owner, same-repo, non-draft.

## Applies when / does not apply when

- Applies when: starting, changing or waking the Actions reviewer (C stage 1, GOV-0015).
- It amends GOV-0017: "starts only on `pull_request`" becomes "privileged runs start only from `main`'s reconciler; events only nudge it". GOV-0017's check of authors, forks and drafts moves into the reconciler's policy and is otherwise unchanged. Its ban on `pull_request_target`, and on `issue_comment` or `workflow_run` with untrusted input, still holds.
- It amends GOV-0019's events: `pull_request` no longer starts a review job, since "PR events may only nudge" the reconciler.
- GOV-0018 is unchanged: the environment stays restricted to the default branch, and every run that reads its secrets starts from `main`.
- Does not apply when: deciding a daily spend ceiling, per-author quotas or trust tiers (stage 2, a `spend` question), letting fork PRs in (stage 3, a `security` question), or moving builder and docs runs into the reconciler (stage 4, C stage 2). Each needs its own question.
- It does not change GOV-0016 (what the job log prints), the local loop (`swarm watch`) beyond GOV-0019's existing switch, or `ops/`.

## Context

The Actions reviewer (`.github/workflows/reviewer.yml`, from #217) worked when the owner started it by `workflow_dispatch` ([run 41810863373](https://github.com/open-agentos/productswarm/actions/runs/41810863373)). On a `pull_request` event its `review` job was refused before its first step ([run 41807886321](https://github.com/open-agentos/productswarm/actions/runs/41807886321)), because a `pull_request` run's ref is `refs/pull/N/merge` and GOV-0018's environment accepts only the default branch. GOV-0017 (`pull_request` only) and GOV-0018 (secrets on `main` only) together meant no automatic run could reach the secrets.

The owner raised #255 with options 1–4 and recommended option 1. The owner then added option 5 in a comment on #255, arguing that the question is where authority lives, not how an event reaches the secrets: "limit what each actor can do, not who can ask." It sets out five layers of safety (where code comes from, what each token can do, who decides, spend, content as data). A reconciler also works for fork PRs later, heals itself when GitHub drops an event, keeps policy in one place on `main`, and extends to C stage 2. Its cost is speed: scheduled runs fire every 5 minutes at best and are often late.

The owner ruled on #255: "option 5, stage 1, as set out in my comment above: a reconciler workflow on `main` starts reviewer runs from repo state, with today's GOV-0017 trust list (swarm Apps and owner). PR events may only nudge it. GOV-0018 is unchanged. Stages 2–4 (the spend question, forks, C stage 2) come later as their own questions."

## Options considered

1. **The check job hands off to a dispatch on `main`:** the `pull_request` run's secret-free check job starts `reviewer.yml` by `workflow_dispatch` using a `GITHUB_TOKEN` with `actions: write`. Keeps GOV-0018; extends GOV-0019's dispatch. Fork PRs get a read-only token, so it can never serve outside contributors.
2. **Let the environment accept PR merge refs:** amends GOV-0018; the environment stops being a second line of defence for PR runs.
3. **Switch to `pull_request_target`:** supersedes part of GOV-0017; the trigger most often behind leaked secrets in public repos.
4. **Do nothing:** owner dispatch only; `review_in_actions` stays `false` and `swarm watch` keeps reviewing.
5. **A reconciler on `main`** (chosen, stage 1): a scheduled workflow on `main` starts runs from repo state; PR events only nudge it.

## Deliberation

n/a. This is an authoritative decision by the owner, who proposed option 5 in a comment on #255 and ruled for it. The question's original recommendation was option 1, which the owner's comment keeps as "a reasonable stopgap if the reconciler is slow to build".

## Consequences

- Every privileged reviewer run starts from code on `main` at that moment, so GOV-0018's environment works unchanged and runs never need a restart after a merge.
- Correctness doesn't depend on events: a missed or delayed event is caught on the next sweep.
- Trust, draft and fork checks, and any limit on how many runs start, live in the reconciler's code on `main`, so changing them is a PR the owner ratifies.
- The team accepts slower reviews: a sweep fires every 5 minutes at best and is often late. A same-repo nudge can wake it early; forks would wait for the next sweep.
- `review_in_actions` stays `false` locally until the reconciler is working, so `swarm watch` keeps reviewing bot PRs meanwhile.
- The owner's comment on #255 names the remaining risks as cost abuse and noise, and the missing pieces as a daily spend ceiling and per-author quotas. Those are stage 2.
- Revisit if the lag matters more than expected, for stages 2–4, or if the reconciler ever needs to start a run with secrets from anything but `main`.
