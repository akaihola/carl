"""The owner-only script (spec section 2, The owner-only script): `carl owner …`.

Run by the owner from their own computer with the bucket key, so the server
needs no admin route. Step 2 brings `list`, `export <id>` and `delete <id>`.
"""

from __future__ import annotations

import argparse


def add_parser(sub: argparse._SubParsersAction) -> None:
    owner = sub.add_parser("owner", help="the owner's recording sessions in the bucket")
    owner.set_defaults(run=run)


def run(args: argparse.Namespace) -> int:
    raise NotImplementedError
