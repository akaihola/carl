#!/bin/bash
# SessionStart hook: what every Claude Code cloud session for Carl needs
# before its first command (.scratch/session-retro/report.md, failure 2).
# Tools that can be cached with the environment (scw, wrangler) come from
# its setup script, deploy/cloud-setup.sh. Local sessions skip all of this.
set -euo pipefail
[ "${CLAUDE_CODE_REMOTE:-}" = true ] || exit 0
cd "$CLAUDE_PROJECT_DIR"

# The tests run before any commit that changes code (.githooks/pre-commit).
git config core.hooksPath .githooks

uv sync --locked --quiet

# The proxy re-signs TLS, so deploy/deploy.sh builds with its CA; and
# aiohttp takes a wss:// connection's proxy only from WSS_PROXY, which a
# local server needs to reach Soniox (docs/operations.md).
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
    if [ -f /root/.ccr/ca-bundle.crt ]; then
        echo 'export CA_BUNDLE=/root/.ccr/ca-bundle.crt' >>"$CLAUDE_ENV_FILE"
    fi
    echo '[ -n "${HTTPS_PROXY:-}" ] && export WSS_PROXY="$HTTPS_PROXY"' >>"$CLAUDE_ENV_FILE"
fi

# Docker's daemon, for deploy/deploy.sh. It starts in the background.
if command -v dockerd >/dev/null && ! docker info >/dev/null 2>&1; then
    setsid nohup dockerd >/tmp/dockerd.log 2>&1 </dev/null &
fi

if ! command -v scw >/dev/null; then
    echo "scw isn't installed, so the environment's setup script (deploy/cloud-setup.sh) is missing or failed. docs/operations.md says how to get it by hand."
fi
