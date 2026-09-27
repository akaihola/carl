"""Set the container's secret environment variables, all of them in one update.

Scaleway replaces a container's whole set of secret variables on every
update, so a secret left out of an update is deleted, and the server then
refuses to start. This sends every secret in SECRETS together, read from the
gitignored `.secrets.*` files at the repo root (a variable already in the
environment wins), and refuses to send an incomplete set. The update
redeploys the container. See docs/operations.md.

    python3 deploy/secrets.py            # set them all; the container redeploys
    python3 deploy/secrets.py --check    # only check that every one is at hand

Needs SCW_SECRET_KEY, the owner's Scaleway API key.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.scaleway.com/containers/v1/regions/fr-par"
NAMESPACE = CONTAINER = "carl"

# Every secret the container holds. A provider's key joins the list with the
# build step that first calls the provider.
SECRETS = [
    "CARL_PASSWORDS",  # .secrets.carl.env
    "TOKEN_SECRET",  # .secrets.carl.env
    "S3_ACCESS_KEY",  # .secrets.bucket.env
    "S3_SECRET_KEY",  # .secrets.bucket.env
]


def read_secret_files() -> dict[str, str]:
    values: dict[str, str] = {}
    for path in sorted(ROOT.glob(".secrets.*")):
        if not path.is_file():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                name, value = line.removeprefix("export ").split("=", 1)
                values[name.strip()] = value.strip().strip("'\"")
    return values


def api(method: str, path: str, body: dict | None = None) -> dict:
    request = urllib.request.Request(
        API + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"X-Auth-Token": os.environ["SCW_SECRET_KEY"], "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {path}: HTTP {e.code}: {e.read().decode(errors='replace')[:500]}")


def find_container() -> dict:
    namespaces = api("GET", f"/namespaces?name={NAMESPACE}")["namespaces"]
    if len(namespaces) != 1:
        sys.exit(f"expected one containers namespace called {NAMESPACE}, found {len(namespaces)}")
    containers = api("GET", f"/containers?namespace_id={namespaces[0]['id']}&name={CONTAINER}")["containers"]
    if len(containers) != 1:
        sys.exit(f"expected one container called {CONTAINER}, found {len(containers)}")
    return containers[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="only check that every secret is at hand")
    args = parser.parse_args()

    values = read_secret_files() | {name: os.environ[name] for name in SECRETS if os.environ.get(name)}
    missing = [name for name in SECRETS if not values.get(name)]
    if missing:
        sys.exit(f"not sending an incomplete set: missing {', '.join(missing)}")
    if args.check:
        print(f"all {len(SECRETS)} secrets are at hand")
        return 0
    if not os.environ.get("SCW_SECRET_KEY"):
        sys.exit("SCW_SECRET_KEY isn't set")
    container = find_container()
    secrets = {name: values[name] for name in SECRETS}
    # The update redeploys the container by itself.
    updated = api("PATCH", f"/containers/{container['id']}", {"secret_environment_variables": secrets})
    print(f"set {len(secrets)} secrets on {CONTAINER}, which is now {updated['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
