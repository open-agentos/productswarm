---
id: GOV-0036
title: One launcher starts sessions on go work in every repo of the org; a bare #N keeps meaning this repo
status: in-force
kind: ruling
question: "#820"
domain: architecture
shape: authoritative
classification:
  reversibility: costly
  blast_radius: org
  nature: preference
  knowledge: shared
decided_by: humans.owner
ratified_by: humans.owner
date: 2026-11-11
review_by: 2027-02-28
supersedes: []
applies_to:
  paths: ["launcher/"]
  roles: []
  situations:
    - starting, listing, holding or stopping a session on an issue in another repo of the org
    - changing how the launcher, its state DB, the opener, `holders()` or the stop hook key work
    - deciding whether to run a second `swarm watch` or launcher home for another repo
---

## Ruling

Run **one launcher for every repo of the org** (option 1 of #820). Each launch entry carries the repo (`owner/name`) as well as the issue number; the launcher keeps a clone per repo under its home and cuts worktrees from it; `swarm launch` takes `owner/name#N`; holders, the opener and the stop hook key on repo plus number. A bare `#N` keeps meaning this repo, so current commands don't change. Build it in the stages #820 lists: repo-qualified refs and holders first, then per-repo clones and worktrees, then the opener and stop hook.

## Applies when / does not apply when

- Applies when: an agent builds or changes how `swarm launch`, `swarm watch`, the launcher's state DB, the opener, `holders()` or the stop hook identify work, or starts a session on go work (GOV-0031) outside this repo.
- One loop and one concurrency ceiling (GOV-0010) cover the whole org; this ruling doesn't raise or split them.
- Does not decide: where a session in another repo gets its `CLAUDE.md` and role prompts, which #820 raised but the answer left open; how the engine host (GOV-0032) is set up for more than one repo; or which repos are in the org. Those need their own question if not plainly inside a builder's task.

## Context

#786 (M4 gate 9): `swarm watch` finds go work in other org repos (#772) but can only list it as `not started`. The launcher assumed one repo everywhere: `swarm launch --issue N` takes a bare number, worktrees are cut from this checkout, and the opener, `holders()` and the stop hook key work by number alone, so starting a builder on `open-agentos/scratch#5` would have worked on this repo's #5. GOV-0031 already makes work in any org repo go; nothing decided how the launcher models more than one repo. Architecture has no `decide` role, so the planner raised #820.

## Options considered

1. **One launcher, many repos** (chosen). Repo-qualified launch entries, a clone per repo, `owner/name#N`, and holders, opener and stop hook keyed on repo plus number. One loop and one ceiling for the org. Cost: touches most of `swarm.py`, the state DB and the stop hook, in staged PRs.
2. **One launcher per repo.** A separate `swarm watch` and launcher home per repo. Little code; two loops, two ceilings, two desks, and setup for every new repo.
3. **Do nothing.** Gate 9 is met by the owner starting a builder by hand in the second repo, and the outside project (GOV-0035) the same way.

## Deliberation

n/a. The question suggested a committee, the domain's default shape; the owner ruled directly instead, answering on #820: "Option 1. A bare #N keeps meaning this repo. Build it in the stages the question lists." with `Record: yes`. The planner recommended option 1: the outside project will be another repo, and one loop keeps one ceiling, one desk and one daily report over all of it.

## Consequences

- #786 is unblocked on this path; builders may open the staged work under it.
- The launcher's state DB, the stop hook and `swarm.py` change shape across several PRs; until the last stage lands, other repos' work can still only be listed, not started.
- The team accepts one concurrency ceiling (GOV-0010) shared across all repos, so work in one repo can wait on another's.
- Revisit if one loop can't keep up across repos, or when the engine host (GOV-0032) needs a different per-repo model.
