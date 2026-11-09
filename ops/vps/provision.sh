#!/usr/bin/env bash
# ops/vps/provision.sh: one-time hardening and setup of the productswarm engine host.
# Run as root on a fresh Ubuntu 24.04 or 26.04 Hetzner server, after adding your SSH key in Hetzner's console:
#   DESK_HOST=desk.example.com bash provision.sh
# Idempotent: safe to run again. It never reads or writes any secret's value.
set -euo pipefail

: "${DESK_HOST:?set DESK_HOST to the Desk DNS name, whose A record must point here first}"
# Password login is about to go: refuse to lock the owner out.
if [ ! -s /root/.ssh/authorized_keys ]; then
  echo "No key in /root/.ssh/authorized_keys; add yours first or you will be locked out" >&2
  exit 1
fi
SVC=swarm

# 1. Packages and unattended upgrades
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -yq ufw unattended-upgrades sqlite3 git python3 python3-venv \
  debian-keyring debian-archive-keyring apt-transport-https curl gnupg
dpkg-reconfigure -f noninteractive unattended-upgrades

# 1b. Swap: the box has 4 GB RAM and role sessions run in containers alongside the services
if [ ! -f /swapfile ]; then
  fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# 2. SSH: keys only, no root password login
install -d -m 755 /etc/ssh/sshd_config.d
cat > /etc/ssh/sshd_config.d/10-productswarm.conf <<'CONF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
CONF
systemctl reload ssh

# 3. Firewall: SSH and HTTPS (80 only for Caddy's certificate challenge and redirect)
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# 4. Docker, for role sessions (no agent shell on the host itself)
# A Docker snap was already on the first box; replace any snap with Docker's own packages.
if snap list docker >/dev/null 2>&1; then
  snap remove --purge docker
  hash -r
fi
if ! [ -x /usr/bin/docker ]; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -q && apt-get install -yq docker-ce docker-ce-cli containerd.io
fi

# 5. Caddy, for TLS in front of the Desk and the webhook receiver
if ! command -v caddy >/dev/null; then
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -q && apt-get install -yq caddy
fi
sed "s/{\$DESK_HOST}/$DESK_HOST/" "$(dirname "$0")/Caddyfile" > /etc/caddy/Caddyfile
systemctl reload caddy

# 5b. GitHub CLI from GitHub's own repo: Ubuntu's gh is too old for the fields swarm watch reads
if [ ! -f /etc/apt/sources.list.d/github-cli.list ]; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg -o /etc/apt/keyrings/githubcli-archive-keyring.gpg
  chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    > /etc/apt/sources.list.d/github-cli.list
  apt-get update -q
fi
apt-get install -yq gh

# 6. Service user, state directory and an empty secrets file the owner fills by hand
id "$SVC" >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin "$SVC"
usermod -aG docker "$SVC"
install -d -o "$SVC" -g "$SVC" -m 700 "/home/$SVC/.productswarm"
install -d -o root -g "$SVC" -m 750 /etc/productswarm
if [ ! -e /etc/productswarm/secrets.env ]; then
  install -o root -g "$SVC" -m 640 /dev/null /etc/productswarm/secrets.env
  echo "Created an empty /etc/productswarm/secrets.env: add ANTHROPIC_API_KEY, WEBHOOK_SECRET and the App keys yourself."
fi

echo "Done. Check: https://$DESK_HOST/healthz"
