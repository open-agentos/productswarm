# Product brief: swarm dashboard

**Owner:** @mattmcalister · **Status:** v0 scope

## Problem

Matt runs several agent sessions at once, each with a different role, working across GitHub. He can't see at a glance which sessions are running, what each one is doing, which are stuck, or what they cost. Everything he learns comes from reading issues, PRs and terminals one at a time.

## What we're building

Two parts that work together:

1. **Session heartbeat.** A Claude Code hook that runs in every agent session. It records lightweight events: session started, working on issue N, opened PR N, blocked on a `gov:question`, stopped. Each event carries the role, the model and a rough cost if one is available.
2. **Swarm dashboard.** A read-only page, regenerated on a schedule. It combines heartbeat events with GitHub state (issues, PRs, `gov:` questions) and shows:
   - each session: its role, current issue, last activity and status (active, idle, blocked or stopped);
   - open PRs and the issues they close;
   - open `gov:question` issues, and which sessions are waiting on them;
   - rough spend per session and per day.

## Users

Matt first. Later, anyone running a fleet on GitHub primitives.

## Goals for v0

- Within 10 seconds of opening the dashboard, Matt can tell what every session is doing and which ones need him.
- Adding the heartbeat to a session is one step.
- It's lightweight: little or no infrastructure beyond GitHub.

## Non-goals for v0

- Starting, stopping or steering sessions. That's the launcher, a possible later milestone; whether and when to build it is a `product-scope` question.
- Editing anything from the dashboard. It's read-only.
- Multi-user access, auth or alerting.

## Open decisions

The swarm decides these through `GOVERNANCE.md`, not up front. Expect questions on where heartbeat events are stored, how the page is built and hosted, who can see it, what the hook may capture, how cost is estimated, and the Action's schedule and permissions.

## Working agreements

- Every PR targets `main` and closes exactly one issue (`Closes #N`).
- Sessions open PRs; only Matt merges.
- New implementation issues are created unlabelled, for Matt to triage.
