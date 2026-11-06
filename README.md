# productswarm

A swarm of agent sessions building tools for running agent swarms. This repo is also the Phase 0 test bed for [open-agentos/agent-governance](https://github.com/open-agentos/agent-governance).

Each session is a Claude Code session with one role: planner, builder, reviewer, docs, designer or analyst. Each role acts on GitHub as its own GitHub App. The tools here let the owner start the swarm, see what every session is doing, and see what's waiting on them. [PRODUCT.md](PRODUCT.md) says what we're building and why.

## What's here

| Path | What it is | Docs |
|---|---|---|
| `heartbeat/` | A Claude Code hook that records what each session is doing, as comments on a `[heartbeat]` tracking issue per session | [heartbeat/README.md](heartbeat/README.md), [SCHEMA.md](heartbeat/SCHEMA.md) |
| `dashboard/` | A read-only page built from heartbeat events and GitHub state: sessions, open PRs, `gov:question`s, spend and a "Needs you" list | [dashboard/README.md](dashboard/README.md) |
| `launcher/` | The `swarm` command: start the sessions in `swarm.toml`, list them, stop one, hand one an issue, and print what needs you | [launcher/README.md](launcher/README.md) |
| `swarm.toml` | The swarm manifest: which roles to run, how many of each, their model and an optional spend cap | [launcher/README.md](launcher/README.md#the-swarm-manifest) |
| `ops/` | Role identities: one GitHub App per role, and `ops/swarm-session`, which starts a session as that App | [ops/README.md](ops/README.md) |
| `roles/` | The prompt each role starts from | |
| `research/` | The analyst's record of the landscape outside productswarm: similar and adjacent products, and platform changes | [research/landscape.md](research/landscape.md) |
| `GOVERNANCE.md`, `governance/` | Who decides what, the rulings so far (`governance/INDEX.md`) and the Phase 0 log | [GOVERNANCE.md](GOVERNANCE.md) |

Everything is Python stdlib plus the `gh` CLI. The launcher needs Python 3.11+ (for `tomllib`) and macOS Terminal.

## Quickstart

1. **Create the role Apps (once).** Run `ops/create-apps.py` and follow [ops/README.md](ops/README.md#one-time-setup-owner). Credentials stay on your machine.
2. **Install the heartbeat (once per checkout).** Run `python3 heartbeat/install.py`. It only affects sessions started with `ops/swarm-session`. See [heartbeat/README.md](heartbeat/README.md#enable-it-one-step).
3. **Set up the manifest.** Edit `swarm.toml` to choose the roles, counts, models and any spend caps, then check it with `python3 launcher/manifest.py`. Changing a model changes cost, which is the owner's `spend` decision.
4. **Start the swarm.** `launcher/swarm up` opens one Terminal window per session. Run it again and it starts only the sessions that aren't running.
5. **See what's happening.**
   - `launcher/swarm inbox`: one ordered list of what's waiting on you (blocked sessions, open `gov:question`s, PRs to merge, idle sessions, sessions over their spend cap).
   - `launcher/swarm ls`: every live session, with its status, current issue, last activity and spend.
   - The dashboard: <https://open-agentos.github.io/productswarm/>, rebuilt every 15 minutes. To build it locally, run `python3 dashboard/generate.py`. It opens with the same "Needs you" list.
6. **Hand a session an issue.** `launcher/swarm launch builder --issue N` starts a session on #N. It refuses if the owner hasn't labelled #N `ready`, or if a live session is already working on it.
7. **Stop a session.** `launcher/swarm stop builder-1`. Sessions never stop on their own, even when they go over a spend cap (GOV-0008). If you close a session's window instead, the next session of that role records it as stopped.

To start a single session without the launcher, run `ops/swarm-session <role>`.

## How the swarm works

- Sessions take only issues the owner has labelled `ready`, and open one PR per issue. Only the owner merges (GOV-0006, [CLAUDE.md](CLAUDE.md)).
- When a session faces a choice outside its task, it checks the rulings in `governance/INDEX.md`, then `governance/jurisdictions.yml`, and otherwise asks in a `gov:question` issue. A ruling exists only once its decision record is merged ([GOVERNANCE.md](GOVERNANCE.md)).
- The reviewer reviews each open PR once per push (L6). The docs role writes the decision record for each ruling, and the owner merges it (GOV-0007).

## Tests

```bash
python3 run_tests.py              # every test_*.py in launcher/, dashboard/, evals/, heartbeat/
python3 run_tests.py launcher     # one directory
```

Python 3.11 or later, stdlib only. The tests never call GitHub, so they run without `gh` or a token. `.github/workflows/tests.yml` runs `run_tests.py` on every PR to `main`, as GOV-0022 stage 1's test check (#521).
