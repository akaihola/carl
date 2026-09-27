"""The dev file source (spec section 14, Ground rules): `carl dev-send <file>`.

A local-only development aid: it sends an audio file over the WebSocket in
place of the microphone, as the page would. It is not the replay and scoring
harness.
"""

from __future__ import annotations

import argparse


def add_parser(sub: argparse._SubParsersAction) -> None:
    send = sub.add_parser("dev-send", help="send an audio file to a local Carl as if from the microphone")
    send.set_defaults(run=run)


def run(args: argparse.Namespace) -> int:
    raise NotImplementedError
