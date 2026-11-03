# Product brief: productswarm

**Owner:** @mattmcalister · **Status:** v0 (swarm dashboard) done · v1 (local launcher) done

## Problem

Matt runs several agent sessions at once, each with a different role, working across GitHub. He can't see at a glance which sessions are running, what each one is doing, which are stuck, or what they cost. Everything he learns comes from reading issues, PRs and terminals one at a time.

## Users

Matt first. Later, anyone running a fleet on GitHub primitives.

## v0: swarm dashboard

### What we're building

Two parts that work together:

1. **Session heartbeat.** A Claude Code hook that runs in every agent session. It records lightweight events: session started, working on issue N, opened PR N, blocked on a `gov:question`, stopped. Each event carries the role, the model and a rough cost if one is available.
2. **Swarm dashboard.** A read-only page, regenerated on a schedule. It combines heartbeat events with GitHub state (issues, PRs, `gov:` questions) and shows:
   - each session: its role, current issue, last activity and status (active, idle, blocked or stopped);
   - open PRs and the issues they close;
   - open `gov:question` issues, and which sessions are waiting on them;
   - rough spend per session and per day.

### Goals for v0

- Within 10 seconds of opening the dashboard, Matt can tell what every session is doing and which ones need him.
- Adding the heartbeat to a session is one step.
- It's lightweight: little or no infrastructure beyond GitHub.

### Non-goals for v0

- ~~Starting, stopping or steering sessions.~~ Superseded by GOV-0005: v1 builds the launcher (below).
- Editing anything from the dashboard. It's read-only.
- Multi-user access, auth or alerting.

## v1: local launcher

GOV-0005 makes v1 a lightweight launcher that runs on Matt's machine. It calls `ops/swarm-session` unchanged and reuses the heartbeat and the dashboard. It lives outside `ops/`.

### What we're building

| # | Issue | What | PR |
|---|---|---|---|
| L1 | #47 | Swarm manifest: a committed file listing roles, how many of each, the model per role and an optional per-session spend cap | #64 |
| L2 | #48 | `swarm up / ls / stop`: start every session in the manifest, list live sessions from heartbeat data, stop one | #65 |
| L3 | #49 | Issue handoff: start a session on a given issue; refuse if a live session is already working on it | #70 |
| L4 | #52 | Spend cap per session | #74 |
| L5 | #50 | "Needs you" list: one ordered list of what's waiting on Matt (PRs to merge, open `gov:question`s, blocked or idle sessions), as `swarm inbox` and at the top of the dashboard | #71 |
| L6 | #51 | The reviewer runs by default and reviews each open PR once | #72 |

Order: L1 → L2 → L3, then L5 and L6, then L4.

### Goals for v1

- Matt no longer starts and routes every session by hand: one command starts the swarm, and one hands a session its issue.
- What needs Matt is one ordered list, not a scan of issues, PRs and terminals.
- The reviewer is in the loop by default.
- Still lightweight: local, with no new infrastructure.

### Non-goals for v1

Each of these needs its own `product-scope` question:

- other repos;
- new roles;
- cloud or unattended runs;
- any workflow change;
- editing anything from the dashboard.

### v1 design decisions

The owner answered each of these on its question:

- #43 How launcher sessions run: one new Terminal window per session.
- #44 Manifest format and location: `swarm.toml` at the repo root, read with stdlib `tomllib`.
- #45 Default spend cap: none for v1; a session has a cap only if the manifest sets one.
- #46 Whether the launcher may stop a session without the owner: no; for v1 the cap only warns (record GOV-0008).

## v2: wake-up loop

GOV-0009 makes v2 a wake-up loop: `launcher/swarm watch`. It runs on Matt's machine in the foreground and stops with Ctrl-C. Every few minutes it reads the same GitHub and heartbeat state as `swarm inbox` and starts the right session for each new trigger. It only ever starts sessions. It reuses `needs_you()`, `swarm launch` and the launcher's refusal checks.

### Triggers

The loop acts only on labels the owner added (checked in the issue's events, per GOV-0006), on new PR heads and on the reviewer's requested changes. Each trigger counts once.

| Trigger | Session it starts |
|---|---|
| `[review]` An open, non-draft PR whose head the reviewer hasn't reviewed | a reviewer pass |
| `[build]` An issue whose latest `ready` the owner added, with no live session on it | `swarm launch builder --issue N` (or the issue's role) |
| `[record]` A `gov:question` the owner labelled `gov:ruled` that needs a record and has no ruling PR | docs, on that question (GOV-0007) |
| `[answer]` A `gov:question` the owner labelled `ready` | the role that asked it, on that question |
| `[respond]` An open, non-draft PR whose latest reviewer review at its current head is "changes requested", with no `Overstep:` finding, for at most 2 rounds | the builder, on that PR (GOV-0011) |

### What we're building

| # | Issue | What | PR |
|---|---|---|---|
| W1 | #89 | `swarm watch --dry-run`: works out the triggers and prints the `swarm launch …` command it would run for each, but starts nothing | #94 |
| W2 | #90 | `swarm watch` starts sessions, within GOV-0010's limits | #104 |
| R1 | #111 | The reviewer uses review states as a stoplight (request changes / comment / approve), with rubric lines; approve means "rubric passed at this head", never a merge decision (GOV-0011) | #117 |
| R2 | #112 | The builder responds to requested changes on its own PR (GOV-0011) | #116 |
| R3 | #113 | The `[respond]` trigger, at most 2 rounds per PR, then the owner (GOV-0011) | #120 |
| H1 | #147 | Loop-started runs are one-shot `claude -p` runs (GOV-0014) with auto permission mode and explicit denies (GOV-0013) and a hard per-run budget and turn ceiling (GOV-0012) | #153 |
| H2 | #148 | A Stop hook keeps a loop-started run going until its role's done-condition is met (GOV-0014) | #152 |
| H3 | #149 | The loop records each run's result and cost in `watch.json`, and `swarm inbox` lists runs that ended at cap (GOV-0012, GOV-0014) | #156 |
| — | #132 | Only reviewers the loop started keep `[review]` triggers quiet; an idle owner-started reviewer doesn't hold reviews up | #143 |
| — | #136 | A `[build]` is held while a live builder or open PR shares its GOV record (the owner's answer on #127) | #144 |

Order: W1 → W2, then R1–R3, then H1–H3.

### Goals for v2

- An owner signal (`ready`, `gov:ruled` or a new PR push) starts the right session without Matt starting it by hand.
- A reviewer's requested changes reach the builder without Matt relaying them, and the review loop is bounded so it ends with Matt.
- Spend while nobody is watching stays bounded by limits Matt sets.
- Still lightweight: local, with no new infrastructure.

### Non-goals for v2

Each of these needs its own `product-scope` question:

- a cloud or GitHub Actions trigger;
- re-prompting a session that is already running;
- the loop stopping a session itself. A loop-started run ends at its budget or turn ceiling because Claude Code ends it (GOV-0012); sessions Matt starts stay warn-only (GOV-0008);
- any trigger or action not in the table above. The loop never adds or removes labels, and never comments, approves or merges.

### v2 design decisions

GOV-0009 named three design questions. The owner has answered each, and later questions added more rulings:

- #101 How a nudge reaches a session: a fresh session per trigger; the loop never re-prompts a running one. GOV-0014 then made each loop-started run one-shot, so there is no idle session to re-prompt.
- #88 / GOV-0010 Interval, concurrency ceiling and cap rule: the interval is 5 minutes, and at most 2 loop-started sessions run at once. The loop starts only roles that have a `spend_cap_usd`, and says why it skipped any other. The numbers live in `swarm.toml`, and changing them is a `spend` change. Sessions Matt starts by hand don't count towards the ceiling.
- #102 Whether the reviewer's "don't poll on a timer" rule changes: it doesn't. The loop does the polling, and a reviewer it starts runs one pass and stops.
- #105 / GOV-0011 Bounded review loop: the reviewer uses request changes, comment and approve as a stoplight, and approve means only that the rubric passed at that head. The builder responds to requested changes on its own PR, and the loop starts it through `[respond]` for at most 2 rounds per PR. A third request, or an `Overstep:` finding, goes to the owner.
- #125 / GOV-0014 How loop-started sessions run: each is a one-shot `claude -p` run that exits when its role is done, kept going by a Stop hook, with its result and cost recorded in `watch.json`. Sessions Matt starts stay interactive.
- #126 / GOV-0012 Hard budget: a loop-started run gets `--max-budget-usd` from its role's `spend_cap_usd`, plus a `--max-turns` ceiling, and ends at either. Sessions Matt starts stay warn-only (GOV-0008).
- #131 / GOV-0013 Headless permissions: loop-started runs use `--permission-mode auto`, plus `--disallowedTools` for `gh pr merge` and label edits.
- #127 Overlapping builders: hold a `[build]` while a live builder or open PR shares its GOV record. This is the owner's direction on that question, not a ruling (GOV-0006).

## Open decisions

The swarm decides these through `GOVERNANCE.md`, not up front. Expect questions on where heartbeat events are stored, how the page is built and hosted, who can see it, what the hook may capture, how cost is estimated, and the Action's schedule and permissions.

## Working agreements

- Every PR targets `main` and closes exactly one issue (`Closes #N`).
- Sessions open PRs; only Matt merges.
- New implementation issues are created unlabelled. Matt triages them and labels the ones to build `ready`; sessions take only `ready` issues (GOV-0006).
