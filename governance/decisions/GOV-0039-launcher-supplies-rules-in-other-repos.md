---
id: GOV-0039
title: In another org repo, the launcher supplies CLAUDE.md and the role prompt from this repo's origin/main; ours wins over that repo's CLAUDE.md
status: in-force
kind: ruling
question: "#854"
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
    - starting a session in a worktree of another org repo (GOV-0036's stage 3)
    - deciding what instructions a session outside this repo reads, or how its opening prompt names them
    - a session in another repo finding that repo's CLAUDE.md disagrees with this repo's rules
---

## Ruling

When the launcher starts a session in another org repo, it **supplies `CLAUDE.md` and `roles/<role>.md` from this repo's `origin/main`** (option 1 of #854). The other repo's own `CLAUDE.md`, if it has one, still loads and covers that repo's code conventions. **Where the two disagree, ours wins.**

## Applies when / does not apply when

- Applies when: the launcher or `swarm watch` starts a session in a worktree cut from another org repo's clone (GOV-0036), or an agent builds or changes how such a session gets its instructions or its opening prompt.
- Applies to a session in another repo reading a rule there: this repo's `CLAUDE.md` and role prompt win over that repo's `CLAUDE.md` where they disagree; that repo's `CLAUDE.md` governs only what ours doesn't cover, such as its code conventions.
- Does not apply when: a session runs in this repo; nothing changes there.
- Does not decide: how the launcher passes the files in (the question's examples were `--append-system-prompt` or untracked copies in the worktree's `.claude/`), or the opening prompt's wording for another repo. Those are inside the stage 3 builder's task. Governance and rulings stay in this repo, and the session reaches them through `gh` as it does now.

## Context

#786 (M4 gate 9), stage 3 of GOV-0036: once the launcher cuts a worktree from another org repo's clone (stage 2, #853), `swarm watch` will start a session there. A session reads the `CLAUDE.md` in its working directory, and the launcher's opening prompt says "Read CLAUDE.md, PRODUCT.md and roles/<role>.md" (`launcher/swarm.py`). A worktree of another repo has none of these unless that repo carries them, so a builder there would run without our working rules (one issue per PR, never merge, the `-- role (model)` sign-off, governance), or under whatever that repo's own `CLAUDE.md` says. GOV-0036 left this open in its "Does not decide". The first outside project (GOV-0035) will hit the same thing. Architecture has no `decide` role, so the planner raised #854.

## Options considered

1. **The launcher supplies them from this repo** (chosen). It reads `CLAUDE.md` and `roles/<role>.md` from this repo's `origin/main` and passes them in at start. Nothing to set up per repo, one source for our rules, and an outside client's repo stays free of our process files. Cost: two instruction sources can disagree, and the opening prompt names files that aren't in the session's repo, so it needs per-repo wording.
2. **Each repo carries its own copies.** Every org repo the swarm works in commits a `CLAUDE.md` and `roles/`, or a short `CLAUDE.md` pointing here. Cost: per-repo setup, copies drift, and an outside client's repo would carry our process files.
3. **A shared org source.** Move the rules and role prompts to one org-level place (a `.github` repo or a package the launcher fetches). Cost: moves files every session reads today, and the governance files would have to say where they live.

## Deliberation

n/a. The question suggested the owner rule directly; the owner answered on #854: "Option 1. The launcher supplies CLAUDE.md and the role prompt from this repo's origin/main. The other repo's own CLAUDE.md still loads for its code conventions; where the two disagree, ours wins." with `Record: yes`. The planner recommended option 1: no per-repo setup, one source for our rules, and an outside client's repo left free of our process files.

## Consequences

- GOV-0036's stage 3 (the opener and stop hook for other repos) may be opened under #786.
- A session in another repo reads our rules from `origin/main` at start, so a rule change reaches it only once merged.
- The team accepts two instruction sources in those sessions, with ours taking precedence where they conflict.
- Revisit if conflicts between our rules and a repo's own `CLAUDE.md` become common, or when the engine host (GOV-0032) starts sessions without the launcher.
