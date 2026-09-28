#!/bin/sh
# Build Carl's image, push it to the Scaleway registry and redeploy the
# container with it. Never during a dinner: a redeploy drops live sessions.
# See docs/operations.md.
#
#   deploy/deploy.sh
#   CA_BUNDLE=/path/to/ca.crt deploy/deploy.sh   # behind a TLS-intercepting proxy
#
# Needs a clean checkout of a pushed commit (the image is tagged with it),
# `docker` (or DOCKER=podman) logged in to rg.fr-par.scw.cloud/carl, and `scw`
# with the owner's Scaleway API key.
set -eu
cd "$(dirname "$0")/.."

if [ -n "$(git status --porcelain)" ]; then
    echo "commit first: the image is tagged with the commit it was built from" >&2
    exit 1
fi
docker=${DOCKER:-docker}
tag=$(git rev-parse --short HEAD)
image=rg.fr-par.scw.cloud/carl/carl:$tag

set -- --build-arg "GIT_COMMIT=$tag" -f deploy/Dockerfile -t "$image"
if [ -n "${CA_BUNDLE:-}" ]; then
    set -- "$@" --network host --secret "id=ca,src=$CA_BUNDLE"
fi
"$docker" build "$@" .
"$docker" push "$image"

namespace=$(scw container namespace list name=carl region=fr-par -o template='{{ .ID }}')
container=$(scw container container list namespace-id="$namespace" name=carl region=fr-par -o template='{{ .ID }}')
# A new image redeploys the container by itself; the same one needs a redeploy.
if [ "$(scw container container get "$container" region=fr-par -o template='{{ .Image }}')" = "$image" ]; then
    scw container container redeploy "$container" region=fr-par -o template='{{ .Name }}: {{ .Status }}'
else
    scw container container update "$container" image="$image" region=fr-par -o template='{{ .Name }}: {{ .Status }}'
fi
# The container's own endpoint stays out of the repo: scanners that know it
# wake the container (ticket 40).
endpoint=$(scw container container get "$container" region=fr-par -o template='{{ .PublicEndpoint }}')
echo "deploying $image; check with: curl $endpoint/api/health"
