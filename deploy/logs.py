"""Show the container's newest log lines, or wait until it has gone quiet.

Traffic keeps the container warm without anyone noticing: scanners at its
own address, the loading page's health polls, a tab left open. So judge
whether it is idle from its logs, never from how long you have waited
(.scratch/session-retro/report.md, failure 1).

    python3 deploy/logs.py                  # the last hour's newest 20 lines
    python3 deploy/logs.py -n 100 --since 6h
    python3 deploy/logs.py --until-quiet    # wait until no line for 16 minutes

The container scales to zero about 15 minutes after its last request
(docs/operations.md). `--until-quiet` checks once a minute, prints each new
line, and exits once the newest line is older than `--quiet` minutes, or
with status 1 after `--max-wait` minutes. Quiet isn't proof of cold: the
next request is a cold start only if the logs show `carl.cli: starting` on
a new instance just before it.

Needs `scw` with the owner's Scaleway API key.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta

REGION = "region=fr-par"


def scw(*args: str) -> str:
    return subprocess.run(["scw", *args, REGION], check=True, capture_output=True, text=True).stdout


def container_id() -> str:
    namespace = scw("container", "namespace", "list", "name=carl", "-o", "template={{ .ID }}").strip()
    return scw(
        "container", "container", "list", f"namespace-id={namespace}", "name=carl", "-o", "template={{ .ID }}"
    ).strip()


def fetch(container: str, since: str, count: int) -> list[tuple[datetime, str]]:
    """The lines of the last `since` (as `30m` or `6h`), oldest first."""
    try:
        output = scw(
            "container", "container", "logs", container, f"time-span={since}", f"entry-count={count}", "-o", "json"
        )
    except subprocess.CalledProcessError as error:
        if "no results found" in error.stdout + error.stderr:
            return []
        raise
    entries = json.loads(output or "[]")
    lines = []
    for entry in entries:
        at = datetime.strptime(entry["timestamp"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC)
        # The instance's name changes with every start; its end tells them apart.
        lines.append((at, f"{entry['resource_instance'][-5:]}  {entry['message']}"))
    return sorted(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("-n", type=int, default=20, help="how many lines (default 20)")
    parser.add_argument("--since", default="1h", help="how far back, as 30m or 6h (default 1h)")
    parser.add_argument("--until-quiet", action="store_true", help="wait until no line comes for --quiet minutes")
    parser.add_argument("--quiet", type=int, default=16, help="minutes without a line (default 16)")
    parser.add_argument("--max-wait", type=int, default=120, help="give up after this many minutes (default 120)")
    args = parser.parse_args()
    container = container_id()

    if not args.until_quiet:
        for _, line in fetch(container, args.since, args.n):
            print(line)
        return 0

    quiet = timedelta(minutes=args.quiet)
    give_up = datetime.now(UTC) + timedelta(minutes=args.max_wait)
    seen = datetime.min.replace(tzinfo=UTC)
    while True:
        try:
            lines = fetch(container, f"{args.quiet + 5}m", 200)
        except subprocess.CalledProcessError as error:
            print(f"couldn't read the logs: {error.stderr.strip()}", file=sys.stderr)
            if datetime.now(UTC) >= give_up:
                return 1
            time.sleep(60)
            continue
        for at, line in lines:
            if at > seen:
                print(line, flush=True)
        seen = max([seen, *(at for at, _ in lines)])
        now = datetime.now(UTC)
        if now - seen >= quiet:
            newest = "none in the window" if seen.year == 1 else f"newest {seen:%H:%M:%S} UTC"
            print(f"quiet for {args.quiet} min ({newest}); the next request should start a new instance")
            return 0
        if now >= give_up:
            print(f"still not quiet after {args.max_wait} min; newest line {seen:%H:%M:%S} UTC", file=sys.stderr)
            return 1
        time.sleep(60)


if __name__ == "__main__":
    sys.exit(main())
