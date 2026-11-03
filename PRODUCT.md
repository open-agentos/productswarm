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

## Open decisions

The swarm decides these through `GOVERNANCE.md`, not up front. Expect questions on where heartbeat events are stored, how the page is built and hosted, who can see it, what the hook may capture, how cost is estimated, and the Action's schedule and permissions.

## Working agreements

- Every PR targets `main` and closes exactly one issue (`Closes #N`).
- Sessions open PRs; only Matt merges.
- New implementation issues are created unlabelled. Matt triages them and labels the ones to build `ready`; sessions take only `ready` issues (GOV-0006).
