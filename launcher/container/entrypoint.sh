#!/usr/bin/env bash
# The entrypoint of a run's container (#661): ops/swarm-session's identity setup, from the
# environment instead of the App's key. The watcher mints the role App's token on the host
# and passes only it (GH_TOKEN) and ANTHROPIC_API_KEY in; then this exec's claude with
# the args docker run was given (--model, --session-id, -p and the headless flags).
set -euo pipefail
role="${SWARM_ROLE:?swarm-run: SWARM_ROLE not set}"
: "${GH_TOKEN:?swarm-run: GH_TOKEN not set (the watcher mints it on the host)}"
: "${ANTHROPIC_API_KEY:?swarm-run: ANTHROPIC_API_KEY not set}"

# gh reads GH_TOKEN itself. App slugs are productswarm-<role> (ops/create-apps.py).
slug="productswarm-$role"
uid=$(gh api "users/${slug}%5Bbot%5D" --jq .id)
export GIT_AUTHOR_NAME="$slug[bot]" GIT_COMMITTER_NAME="$slug[bot]"
email="$uid+$slug[bot]@users.noreply.github.com"
export GIT_AUTHOR_EMAIL="$email" GIT_COMMITTER_EMAIL="$email"
# git push authenticates with the same token; single quotes: read when git asks, never stored.
export GIT_CONFIG_COUNT=2
export GIT_CONFIG_KEY_0=credential.helper GIT_CONFIG_VALUE_0=""
export GIT_CONFIG_KEY_1=credential.helper
export GIT_CONFIG_VALUE_1='!f() { test "$1" = get && printf "username=x-access-token\npassword=%s\n" "$GH_TOKEN"; }; f'

echo "swarm-run: $role as $slug[bot], in a container" >&2
exec claude "$@"
