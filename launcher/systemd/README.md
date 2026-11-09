# systemd drafts for the engine host (#660)

These are **drafts for the owner to commit under `ops/`**. `ops/` is the owner's (a protected path), so the builder proposes them here, as workflow files are proposed.

| Unit | Runs |
|---|---|
| `swarm-watch.service` | `swarm watch --serve`: a check on each webhook nudge, and a backstop sweep every `[watch] interval_minutes` |
| `swarm-webhooks.service` | `swarm webhooks` on `127.0.0.1:8081`, behind Caddy; `WEBHOOK_SECRET` from `~/.config/productswarm/webhooks.env` |
| `swarm-backup.service` + `.timer` | `swarm backup` nightly at 03:15 (plus up to 10 minutes), caught up at boot if missed |

They are user units, so the state stays in `~/.productswarm` and the checkout at `~/productswarm`:

```sh
cp launcher/systemd/swarm-*.service launcher/systemd/swarm-*.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now swarm-watch swarm-webhooks swarm-backup.timer
loginctl enable-linger "$USER"
journalctl --user -u swarm-watch -f
```

`swarm-watch.service` restarts 30 seconds after any failure, including a start that refused (GitHub unreachable, a `swarm.toml` with no usable `[watch]`). `watch.lock` (#273) means a restart never runs two watchers.

**Not yet on Linux.** `swarm watch` still opens each session it starts in a macOS Terminal window (#43), so on a Linux host it can check, hold and halt but each start fails. Running sessions on the engine host is a separate step of #651.

**Halting.** To stop all dispatch, the owner puts the `swarm:halt` label on `[watch] report_issue`. The watcher reads it on every check, so it takes effect at the next one: within a second of the label's webhook, or at the next sweep. Taking it off resumes. A `swarm:halt` that anyone else added is ignored (GOV-0006). Stopping the service also stops dispatch, but needs the host.
