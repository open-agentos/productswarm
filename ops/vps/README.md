# ops/vps: the engine host (owner only)

1. In Hetzner, create an Ubuntu 24.04 or 26.04 server with your SSH key, and point the Desk's DNS name at it.
2. Copy this folder over and run: `DESK_HOST=<name> bash provision.sh` as root.
3. Put the secrets in `/etc/productswarm/secrets.env` (root:swarm, 0640) yourself: `ANTHROPIC_API_KEY`, `WEBHOOK_SECRET`, `GH_TOKEN` and each App's key. No agent or session ever sees this file.
   - `GH_TOKEN` is what the watcher reads GitHub with. Use a fine-grained token with read-only access to the repo (Contents, Issues, Pull requests, Metadata) and the org Project. Nothing on the host writes with it.
4. In each role App's settings, set the webhook URL to `https://<name>/webhooks/github` with the same `WEBHOOK_SECRET`.

## The services (#660)

`systemd/` has four units. All run as the `swarm` user from a checkout at `/home/swarm/productswarm`, with state in `/home/swarm/.productswarm/launcher/swarm.db`:

| Unit | Runs | Reads |
|---|---|---|
| `productswarm-webhooks.service` | `swarm webhooks` on 127.0.0.1:8081, behind Caddy | `webhooks.env`: only `WEBHOOK_SECRET` |
| `productswarm-watch.service` | `swarm watch --serve --dry-run`: a check on each webhook nudge (at most every 30 s) and every `interval_minutes` | `secrets.env` |
| `productswarm-backup.service` and `.timer` | `swarm backup` nightly at 03:30 UTC | nothing secret |

The watcher runs with `--dry-run` until #661: starting role sessions here needs #661's containers. Take `--dry-run` off then.

Install, as root:

```bash
sudo -u swarm git clone https://github.com/open-agentos/productswarm /home/swarm/productswarm
grep '^WEBHOOK_SECRET=' /etc/productswarm/secrets.env > /etc/productswarm/webhooks.env
chown root:swarm /etc/productswarm/webhooks.env && chmod 640 /etc/productswarm/webhooks.env
cp /root/vps/systemd/productswarm-* /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now productswarm-webhooks productswarm-watch productswarm-backup.timer
```

Check: `systemctl status productswarm-webhooks productswarm-watch` and `journalctl -u productswarm-watch -f`. To stop everything starting work, add `swarm:halt` to the report issue (#249); only your label counts.
