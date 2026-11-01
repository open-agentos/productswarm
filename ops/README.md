# ops: role identities for agent sessions

Each agent role acts on GitHub as its own GitHub App, so GitHub, not a signature, says who wrote what.

| Role | App | Permissions (plus metadata: read) |
|---|---|---|
| planner | `productswarm-planner[bot]` | issues: write · contents, pull requests: read |
| builder | `productswarm-builder[bot]` | contents, issues, pull requests: write |
| reviewer | `productswarm-reviewer[bot]` | issues, pull requests: write · contents: read |
| docs | `productswarm-docs[bot]` | contents, issues, pull requests: write |

No App gets `workflows` or `administration`, so agents can't change `.github/workflows/` or repo settings.

## One-time setup (owner)

```bash
ops/create-apps.py
```

1. Open the URL it prints and click **Create productswarm-<role>**. GitHub asks you to confirm and then sends you back.
2. On the page you return to, click **Install it on productswarm**, choose **Only select repositories**, and pick productswarm.
3. Repeat for each role, then press Ctrl-C.

Credentials are saved to `~/.config/productswarm/apps/<role>.json` and `<role>.pem` (mode 0600). Nothing is committed.

## Starting a session

```bash
ops/swarm-session builder
```

This starts Claude Code in the repo root with the role's opener prompt. Inside the session:

- `gh` runs through `ops/shims/gh` with a fresh installation token for the role's App;
- `git push` authenticates as the App, replacing any keychain helper;
- commits are authored by `productswarm-<role>[bot]`;
- `GH_CONFIG_DIR` points at an empty per-role directory, so a `gh` that somehow bypasses the shim has no login and fails instead of acting as you.

Tokens last an hour. `ops/swarm-token` caches them and mints a new one when under 10 minutes are left, so long sessions keep working.

## Caveats

- MCP servers you've configured globally (for example a GitHub MCP with your own token) still run as you inside a swarm session. Don't enable a GitHub MCP for swarm sessions.
- If your shell profile puts a directory containing another `gh` ahead of `ops/shims`, the shim is skipped. `gh` then fails closed instead of acting as you.
