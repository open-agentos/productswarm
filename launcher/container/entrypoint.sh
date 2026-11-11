#!/usr/bin/env bash
# The entrypoint of a run's container (#661): ops/swarm-session's identity setup, from a
# token file instead of the App's key. The watcher mints the role App's token on the host
# and rewrites it into a read-only mounted file while the run lives (#680), so gh (through
# the gh wrapper, /usr/local/bin/gh) and git read it fresh on every call. Only that file
# and ANTHROPIC_API_KEY come in; then this exec's claude with the args docker run was
# given (--model, --session-id, -p and the headless flags).
set -euo pipefail
role="${SWARM_ROLE:?swarm-run: SWARM_ROLE not set}"
: "${SWARM_TOKEN_FILE:?swarm-run: SWARM_TOKEN_FILE not set}"
test -s "$SWARM_TOKEN_FILE" || { echo "swarm-run: no token in $SWARM_TOKEN_FILE (the watcher writes it on the host)" >&2; exit 1; }
unset GH_TOKEN   # a token in the environment would go stale; the gh wrapper reads the file
: "${ANTHROPIC_API_KEY:?swarm-run: ANTHROPIC_API_KEY not set}"

# App slugs are productswarm-<role> (ops/create-apps.py).
slug="productswarm-$role"
uid=$(gh api "users/${slug}%5Bbot%5D" --jq .id)
export GIT_AUTHOR_NAME="$slug[bot]" GIT_COMMITTER_NAME="$slug[bot]"
email="$uid+$slug[bot]@users.noreply.github.com"
export GIT_AUTHOR_EMAIL="$email" GIT_COMMITTER_EMAIL="$email"
# git push authenticates with the same token; single quotes: the file is read each time git
# asks, so a push late in a run gets the token the host last wrote. Never stored.
export GIT_CONFIG_COUNT=2
export GIT_CONFIG_KEY_0=credential.helper GIT_CONFIG_VALUE_0=""
export GIT_CONFIG_KEY_1=credential.helper
export GIT_CONFIG_VALUE_1='!f() { test "$1" = get && printf "username=x-access-token\npassword=%s\n" "$(cat "$SWARM_TOKEN_FILE")"; }; f'

echo "swarm-run: $role as $slug[bot], in a container" >&2
exec claude "$@"
