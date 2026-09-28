#!/bin/bash
# The setup script of the owner's Claude Code cloud environment for Carl.
# It runs as root before the repo is cloned, so it can't be run from here:
# its text is pasted into the environment's settings (Setup script). What it
# installs is cached with the environment. The SessionStart hook,
# .claude/hooks/session-start.sh, does the rest in every session. See
# docs/operations.md.
#
# It never fails the setup: whatever it can't install, it names on stderr,
# and the session's hook names it again.
set -uo pipefail

# scw, for deploy/deploy.sh and the logs. GitHub's release downloads are
# blocked there, so it comes out of Scaleway's own image on Google's mirror
# of Docker Hub, or else is built with Go (about 2.5 minutes).
if ! command -v scw >/dev/null; then
    started=
    if ! docker info >/dev/null 2>&1; then
        setsid nohup dockerd >/tmp/dockerd-setup.log 2>&1 </dev/null &
        started=$!
        for _ in $(seq 30); do docker info >/dev/null 2>&1 && break; sleep 1; done
    fi
    if id=$(docker create mirror.gcr.io/scaleway/cli:latest); then
        docker cp "$id:/usr/bin/scw" /usr/local/bin/scw
        docker rm "$id" >/dev/null
        docker rmi mirror.gcr.io/scaleway/cli:latest >/dev/null
    fi
    # Stop it again, so no stale pid file is cached to trip up the hook's.
    if [ -n "$started" ]; then
        kill "$started"
        for _ in $(seq 30); do [ -e /var/run/docker.pid ] || break; sleep 1; done
    fi
fi
if ! command -v scw >/dev/null && command -v go >/dev/null; then
    tmp=$(mktemp -d)
    GOBIN=/usr/local/bin GOPATH=$tmp GOCACHE=$tmp/cache GOFLAGS=-modcacherw \
        go install github.com/scaleway/scaleway-cli/v2/cmd/scw@latest
    rm -rf "$tmp"
fi
scw version >/dev/null 2>&1 || echo "setup: scw couldn't be installed" >&2

# wrangler, for deploy/worker.sh, into npx's cache.
npx -y wrangler@4 --version >/dev/null || echo "setup: wrangler couldn't be fetched" >&2

exit 0
