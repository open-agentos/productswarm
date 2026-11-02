# Launcher

The v1 local launcher (GOV-0005). It starts sessions through `ops/swarm-session` unchanged. So far this directory holds only the manifest loader (L1). `swarm up / ls / stop` comes next (L2).

## The swarm manifest

`swarm.toml` at the repo root lists the sessions to run. It is TOML, read with stdlib `tomllib` (Python 3.11+), per the owner's answer on #44.

```toml
[[session]]
role = "builder"          # required: needs roles/builder.md
count = 2                 # required: at least 1
model = "claude-opus-5-5" # required
spend_cap_usd = 15        # optional, per session; no cap if left out (#45)
```

- Each role gets one `[[session]]` table. Use `count` to run more than one session of a role.
- Any other key is an error, so a typo fails loudly instead of being ignored.
- The spend cap is warn-only: the launcher never stops a session (GOV-0008).
- Changing a role's model changes cost per run. That is a `spend` decision for the owner.

Check the manifest and see what it would start:

```bash
python3 launcher/manifest.py            # or: python3 launcher/manifest.py path/to/swarm.toml
```

It prints one line per session (`builder-1  claude-opus-5-5  no cap`). If the manifest is bad, it exits 1 and lists every problem it found.

From Python, `manifest.load()` returns a list of `Session(role, index, model, spend_cap_usd)` or raises `ManifestError`.

## Tests

```bash
python3 -m unittest discover -s launcher
```
