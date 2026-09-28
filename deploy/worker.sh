#!/bin/sh
# Deploy the loading Worker in deploy/cloudflare/. Needed only when
# deploy/cloudflare/ or src/carl/pass.html (which it bundles) changes; see
# docs/operations.md.
#
#   deploy/worker.sh
#
# Takes CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID from the environment,
# or else from .secrets.cloudflare.env.
set -eu
cd "$(dirname "$0")/.."

if [ -n "$(git status --porcelain -- deploy/cloudflare src/carl/pass.html)" ]; then
    echo "commit first: the deployed Worker should match a commit" >&2
    exit 1
fi
if [ -z "${CLOUDFLARE_API_TOKEN:-}" ] && [ -f .secrets.cloudflare.env ]; then
    set -a
    . ./.secrets.cloudflare.env
    set +a
fi
cd deploy/cloudflare
exec npx -y wrangler@4 deploy
