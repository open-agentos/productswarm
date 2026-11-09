# The image every run swarm watch starts goes in on the engine host (#661).
#
#   docker build --build-arg CLAUDE_CODE_VERSION=<x.y.z> -t productswarm-run launcher/container
#   docker image inspect productswarm-run --format '{{.Id}}'    # sha256:... for --container
#
# swarm watch --container takes the image by digest only, so a rebuild changes nothing
# until the owner points the service at the new id. Claude Code's version is pinned at
# build time; there is no default, so a build never picks up "latest" by accident.
FROM node:22-bookworm-slim

ARG CLAUDE_CODE_VERSION
RUN test -n "$CLAUDE_CODE_VERSION" || { echo "pass --build-arg CLAUDE_CODE_VERSION=<x.y.z>" >&2; exit 1; }

# git and gh for the session, python3 and procps (ps) for the heartbeat and Stop hooks, jq
# for the role prompts' gh --jq habits. gh from GitHub's own apt repo: Debian's is too old.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git jq procps python3 \
 && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
      > /etc/apt/sources.list.d/github-cli.list \
 && apt-get update && apt-get install -y --no-install-recommends gh \
 && rm -rf /var/lib/apt/lists/*

RUN npm install -g "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" && npm cache clean --force

COPY entrypoint.sh /usr/local/bin/swarm-run
ENTRYPOINT ["/usr/local/bin/swarm-run"]
